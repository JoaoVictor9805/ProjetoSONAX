# -*- coding: utf-8 -*-
"""
============================================================================
Worker puro (sem Tk) que orquestra o pipeline SONAX em uma thread
separada e comunica progresso via `EventQueue`.

Responsabilidades:
    1. Validar `.env` e `get_database_url()` antes de gastar tempo
       copiando/ transcrevendo.
    2. Rodar dentro de `with redirect_stdio(q):` para que todos os
       `print()` de `app.services.*` virem `LogEvent` em tempo real.
    3. Reusar as funções já existentes em `app.main` e
       `app.services.script` — **nenhuma lógica de domínio aqui**.
    4. Encerrar sempre com um único `DoneEvent` (sucesso ou erro).

Erros são capturados e transformados em `DoneEvent(exit_code=...)` com
a mesma convenção do CLI original (0 ok, 1 diretório, 2 banco).
============================================================================
"""
from __future__ import annotations

import threading
import traceback
from pathlib import Path
import zipfile
import rarfile
import shutil

from app.database.config import get_database_url
from app.services.io import coletar_wavs, resolver_destino
from app.services.script import (
    classificar_wavs,
    copiar_longos_para_pasta,
    salvar_no_banco,
    deletar_pasta
)
from app.services.transcrever import TranscricaoCancelada
from app.view.events import DoneEvent, EventQueue, LogEvent, ProgressEvent
from app.view.stream import redirect_stdio


def _configurar_rarfile() -> None:
    """Configura o executável unrar para o rarfile no Windows, caso não esteja no PATH."""
    if shutil.which("unrar") or shutil.which("WinRAR") or shutil.which("7z"):
        return
    candidatos = [
        r"C:\Program Files\WinRAR\UnRAR.exe",
        r"C:\Program Files\WinRAR\WinRAR.exe",
        r"C:\Program Files (x86)\WinRAR\UnRAR.exe",
        r"C:\Program Files (x86)\WinRAR\WinRAR.exe",
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ]
    for c in candidatos:
        if Path(c).is_file():
            if "7z" in c.lower():
                setattr(rarfile, "SEVENZIP_TOOL", c)
                setattr(rarfile, "FORCE_TOOL", "7zip")
            else:
                setattr(rarfile, "UNRAR_TOOL", c)
            return


def run_pipeline(
    entrada: Path,
    queue: EventQueue,
    cancel: threading.Event,  # noqa: ARG001 — reservado para cancelamento futuro
) -> None:
    """Executa o pipeline completo. Enfileira eventos; termina com `DoneEvent`.

    `entrada` pode ser um diretório com os .wav ou um arquivo `.zip` / `.rar`
    contendo esse diretório. Se for compactado, é extraído para uma pasta
    ao lado do arquivo compactado.

    Esta função é **bloqueante** e deve rodar em uma thread separada
    para não congelar a main loop do Tk.
    """
    pasta_extracao: Path | None = None
    destino: Path | None = None

    def _limpar_temporarios() -> None:
        """Exclui com segurança as pastas temporárias geradas no processo."""
        if destino is not None and destino.exists():
            queue.put_event(LogEvent(f"Excluindo pasta temporária: {destino} ..."))
            deletar_pasta(destino)
        if pasta_extracao is not None and pasta_extracao.exists():
            queue.put_event(LogEvent(f"Excluindo pasta temporária extraída: {pasta_extracao} ..."))
            deletar_pasta(pasta_extracao)

    try:
        # Se a GUI passou um .zip ou .rar, extrai na mesma pasta do arquivo.
        ext = entrada.suffix.lower() if entrada.is_file() else ""
        if ext in [".zip", ".rar"]:
            pasta_extracao = entrada.parent / entrada.stem
            if pasta_extracao.exists():
                shutil.rmtree(pasta_extracao, ignore_errors=True)
            pasta_extracao.mkdir(parents=True, exist_ok=True)
            queue.put_event(LogEvent(
                f"Descompactando {entrada.name} em: {pasta_extracao} ...",
                stream="out",
            ))
            try:
                if ext == ".zip":
                    with zipfile.ZipFile(entrada, "r") as zf:
                        # Validação defensiva contra zip bomb e path traversal.
                        membros_invalidos = [
                            m for m in zf.namelist()
                            if m.startswith("/") or ".." in Path(m).parts
                        ]
                        if membros_invalidos:
                            raise zipfile.BadZipFile(
                                f"Arquivo ZIP contém caminhos inválidos: "
                                f"{membros_invalidos[:3]}..."
                            )
                        zf.extractall(pasta_extracao)
                elif ext == ".rar":
                    _configurar_rarfile()
                    with rarfile.RarFile(entrada, "r") as rf:
                        membros_invalidos = [
                            m for m in rf.namelist()
                            if m.startswith("/") or ".." in Path(m).parts
                        ]
                        if membros_invalidos:
                            raise rarfile.BadRarFile(
                                f"Arquivo RAR contém caminhos inválidos: "
                                f"{membros_invalidos[:3]}..."
                            )
                        rf.extractall(pasta_extracao)
            except Exception as e:
                _limpar_temporarios()
                queue.put_event(LogEvent(
                    f"[ERRO] Falha ao descompactar arquivo: {e}", stream="err",
                ))
                queue.put_event(DoneEvent(
                    exit_code=1,
                    summary="",
                    error=f"Arquivo compactado inválido: {e}",
                ))
                return

            # Se o arquivo compactado tiver uma única pasta raiz, "entra" nela para
            # que o resto do pipeline não precise saber que veio de compactado.
            subdirs = [p for p in pasta_extracao.iterdir() if p.is_dir()]
            if len(subdirs) == 1 and not any(pasta_extracao.glob("*.wav")):
                diretorio = subdirs[0]
            else:
                diretorio = pasta_extracao

            queue.put_event(LogEvent(
                f"Extraído em: {diretorio}", stream="out",
            ))
        else:
            diretorio = entrada

        # Pre-check do .env — se faltar variável, aborta cedo com mensagem clara.
        try:
            get_database_url()
        except KeyError as e:
            _limpar_temporarios()
            queue.put_event(LogEvent(
                f"[ERRO] Variável de ambiente ausente: {e}. "
                f"Verifique o arquivo .env antes de continuar.",
                stream="err",
            ))
            queue.put_event(DoneEvent(
                exit_code=2,
                summary="",
                error="Configuração do banco ausente (.env).",
            ))
            return

        # Roda o pipeline existente dentro de `with redirect_stdio(q):`
        # para que todos os `print()` de `app.services.*` virem
        # `LogEvent` em tempo real.
        with redirect_stdio(queue):
            queue.put_event(LogEvent(f"[INFO] Diretório selecionado: {diretorio}"))

            # 1) Varredura
            queue.put_event(ProgressEvent(
                done=0, total=1, phase="scanning",
                message="Varrendo arquivos .wav ...",
            ))
            wavs = coletar_wavs(diretorio)
            queue.put_event(ProgressEvent(
                done=1, total=1, phase="scanning",
                message=f"Varredura concluída: {len(wavs)} arquivo(s) .wav encontrado(s).",
            ))

            if not wavs:
                _limpar_temporarios()
                queue.put_event(LogEvent("Nenhum .wav encontrado no diretório."))
                queue.put_event(DoneEvent(
                    exit_code=0,
                    summary="Nenhum .wav encontrado.",
                ))
                return

            if cancel.is_set():
                _limpar_temporarios()
                queue.put_event(DoneEvent(
                    exit_code=0,
                    summary="Cancelado antes de iniciar classificação.",
                ))
                return

            # 2) Classificação por duração
            queue.put_event(ProgressEvent(
                done=0, total=1, phase="classifying",
                message="Classificando arquivos por duração ...",
            ))
            longos, curtos, invalidos = classificar_wavs(wavs, cancel=cancel)
            queue.put_event(LogEvent(
                f"Total: {len(wavs)}  •  >1min: {len(longos)}  •  "
                f"<=1min: {len(curtos)}  •  inválidos: {len(invalidos)}"
            ))
            queue.put_event(ProgressEvent(
                done=1, total=1, phase="classifying",
                message=f"Classificação concluída: {len(longos)} áudio(s) >1min elegível(is).",
            ))

            if not longos:
                _limpar_temporarios()
                queue.put_event(LogEvent("Nenhum áudio com mais de 1 minuto encontrado."))
                queue.put_event(DoneEvent(
                    exit_code=0,
                    summary="Nenhum áudio >1min encontrado.",
                ))
                return

            if cancel.is_set():
                _limpar_temporarios()
                queue.put_event(DoneEvent(
                    exit_code=0,
                    summary="Cancelado antes de iniciar cópia.",
                ))
                return

            # 3) Cópia para a pasta destino
            destino = resolver_destino(diretorio)
            queue.put_event(LogEvent(f"Pasta de destino: {destino}"))
            queue.put_event(ProgressEvent(
                done=0, total=len(longos), phase="copying",
                message=f"Copiando {len(longos)} arquivo(s) para a pasta de trabalho ...",
            ))

            def on_copy_progress(idx: int, tot: int, p: Path) -> None:
                queue.put_event(ProgressEvent(
                    done=idx, total=tot, phase="copying",
                    message=f"Copiado ({idx}/{tot}): {p.name}",
                ))

            copiados = copiar_longos_para_pasta(
                longos, destino, cancel=cancel, on_progress=on_copy_progress,
            )
            queue.put_event(LogEvent(
                f"{len(copiados)} arquivo(s) copiado(s) para: {destino}"
            ))
            queue.put_event(ProgressEvent(
                done=len(copiados), total=len(copiados), phase="copying",
                message=f"{len(copiados)} arquivo(s) copiado(s) com sucesso.",
            ))

            if cancel.is_set():
                _limpar_temporarios()
                queue.put_event(DoneEvent(
                    exit_code=0,
                    summary="Cancelado antes de iniciar transcrição.",
                ))
                return

            # 4) Transcrição (Whisper) + INSERT no banco
            total = len(copiados)
            queue.put_event(ProgressEvent(
                done=0, total=total, phase="transcribing",
                message=f"Iniciando transcrição e gravação de {total} arquivo(s) ...",
            ))

            def on_progress(
                i: int,
                tot: int,
                caminho: Path,
                frac: float = 0.0,
                msg: str = "",
            ) -> None:
                done_cumulativo = (i - 1) + frac
                queue.put_event(ProgressEvent(
                    done=done_cumulativo,
                    total=tot,
                    phase="transcribing",
                    message=msg if msg else f"[{i}/{tot}] Processando: {caminho.name}",
                ))

            inseridos, ja_existentes = salvar_no_banco(
                copiados, cancel=cancel, on_progress=on_progress,
            )

            detalhes_existentes = f" ({ja_existentes} já existente(s))" if ja_existentes > 0 else ""

            if cancel.is_set():
                _limpar_temporarios()
                queue.put_event(DoneEvent(
                    exit_code=0,
                    summary=f"Cancelado após {inseridos} registro(s) "
                            f"inserido(s) com transcrição{detalhes_existentes}.",
                ))
                return

            queue.put_event(ProgressEvent(
                done=total, total=total, phase="inserting",
                message=f"Transcrição finalizada: {inseridos} registro(s) processado(s){detalhes_existentes}.",
            ))

            # 5) Exclusão das pastas temporárias geradas
            _limpar_temporarios()
            queue.put_event(DoneEvent(
                exit_code=0,
                summary=f"{inseridos} registro(s) inserido(s) com transcrição{detalhes_existentes}.",
            ))

    except FileNotFoundError as e:
        _limpar_temporarios()
        queue.put_event(LogEvent(f"[ERRO] Diretório inválido: {e}", stream="err"))
        queue.put_event(DoneEvent(
            exit_code=1,
            summary="",
            error=f"Diretório inválido: {e}",
        ))
    except TranscricaoCancelada as e:
        # Caso o `salvar_no_banco` não tenha capturado (não deveria
        # acontecer — ele trata — mas é uma segurança a mais).
        _limpar_temporarios()
        queue.put_event(LogEvent(f"  [cancelado] {e}", stream="err"))
        queue.put_event(DoneEvent(
            exit_code=0,
            summary="Cancelado durante transcrição.",
        ))
    except Exception as e:  # noqa: BLE001 — captura ampla de propósito
        _limpar_temporarios()
        tb = traceback.format_exc()
        queue.put_event(LogEvent(f"[ERRO] {type(e).__name__}: {e}", stream="err"))
        queue.put_event(LogEvent(tb, stream="err"))
        queue.put_event(DoneEvent(
            exit_code=2,
            summary="",
            error=f"{type(e).__name__}: {e}",
        ))

