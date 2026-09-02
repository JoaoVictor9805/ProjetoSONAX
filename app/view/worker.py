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
import tempfile
import zipfile
import rarfile

from app.database.config import get_database_url
from app.services.io import coletar_wavs, resolver_destino
from app.services.script import (
    classificar_wavs,
    copiar_longos_para_pasta,
    salvar_no_banco,
)
from app.services.transcrever import TranscricaoCancelada
from app.view.events import DoneEvent, EventQueue, LogEvent, ProgressEvent
from app.view.stream import redirect_stdio


def _configurar_rarfile() -> None:
    """Configura o executável unrar para o rarfile no Windows, caso não esteja no PATH."""
    import shutil
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
    temporária que é removida no fim (mesmo em caso de erro/cancelamento).

    Esta função é **bloqueante** e deve rodar em uma thread separada
    para não congelar a main loop do Tk.
    """
    tmp_ctx: tempfile.TemporaryDirectory | None = None
    try:
        # Se a GUI passou um .zip ou .rar, extrai para uma pasta temporária.
        ext = entrada.suffix.lower() if entrada.is_file() else ""
        if ext in [".zip", ".rar"]:
            tmp_ctx = tempfile.TemporaryDirectory(prefix="sonax_archive_")
            destino = Path(tmp_ctx.name)
            queue.put_event(LogEvent(
                f"Descompactando {entrada.name} em pasta temporária...",
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
                        zf.extractall(destino)
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
                        rf.extractall(destino)
            except Exception as e:
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
            subdirs = [p for p in destino.iterdir() if p.is_dir()]
            if len(subdirs) == 1 and not any(destino.glob("*.wav")):
                diretorio = subdirs[0]
            else:
                diretorio = destino

            queue.put_event(LogEvent(
                f"Extraído em: {diretorio}", stream="out",
            ))
        else:
            diretorio = entrada

        # Pre-check do .env — se faltar variável, aborta cedo com mensagem clara.
        try:
            get_database_url()
        except KeyError as e:
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
            queue.put_event(LogEvent("Varrendo .wav ..."))
            wavs = coletar_wavs(diretorio)
            queue.put_event(ProgressEvent(done=0, total=1, phase="scanning"))

            if not wavs:
                queue.put_event(LogEvent("Nenhum .wav encontrado no diretório."))
                queue.put_event(DoneEvent(
                    exit_code=0,
                    summary="Nenhum .wav encontrado.",
                ))
                return

            if cancel.is_set():
                queue.put_event(DoneEvent(
                    exit_code=0,
                    summary="Cancelado antes de iniciar classificação.",
                ))
                return

            # 2) Classificação por duração
            longos, curtos, invalidos = classificar_wavs(wavs)
            queue.put_event(LogEvent(
                f"Total: {len(wavs)}  •  >1min: {len(longos)}  •  "
                f"<=1min: {len(curtos)}  •  inválidos: {len(invalidos)}"
            ))

            if not longos:
                queue.put_event(LogEvent("Nenhum áudio com mais de 1 minuto encontrado."))
                queue.put_event(DoneEvent(
                    exit_code=0,
                    summary="Nenhum áudio >1min encontrado.",
                ))
                return

            if cancel.is_set():
                queue.put_event(DoneEvent(
                    exit_code=0,
                    summary="Cancelado antes de iniciar cópia.",
                ))
                return

            # 3) Cópia para a pasta destino
            destino = resolver_destino(diretorio)
            queue.put_event(LogEvent(f"Pasta de destino: {destino}"))
            queue.put_event(ProgressEvent(done=0, total=1, phase="copying"))
            copiados = copiar_longos_para_pasta(longos, destino)
            queue.put_event(LogEvent(
                f"{len(copiados)} arquivo(s) copiado(s) para: {destino}"
            ))
            queue.put_event(ProgressEvent(done=1, total=1, phase="copying"))

            if cancel.is_set():
                queue.put_event(DoneEvent(
                    exit_code=0,
                    summary="Cancelado antes de iniciar transcrição.",
                ))
                return

            # 4) Transcrição (Whisper) + INSERT no banco
            total = len(copiados)
            queue.put_event(LogEvent(
                f"Transcrevendo e gravando {total} arquivo(s) no banco ..."
            ))

            def on_progress(i: int, tot: int, caminho: Path) -> None:  # noqa: ARG001
                # ARG001: 'caminho' não usado aqui (vai no LogEvent via _emit do transcrever).
                # A interface usa o i/total para atualizar a barra de progresso.
                queue.put_event(ProgressEvent(
                    done=i, total=tot, phase="transcribing",
                ))

            inseridos = salvar_no_banco(
                copiados, cancel=cancel, on_progress=on_progress,
            )
            queue.put_event(ProgressEvent(
                done=total, total=total, phase="inserting",
            ))

            if cancel.is_set():
                queue.put_event(DoneEvent(
                    exit_code=0,
                    summary=f"Cancelado após {inseridos} registro(s) "
                            f"inserido(s) com transcrição.",
                ))
                return

            queue.put_event(DoneEvent(
                exit_code=0,
                summary=f"{inseridos} registro(s) inserido(s) com transcrição.",
            ))

    except FileNotFoundError as e:
        queue.put_event(LogEvent(f"[ERRO] Diretório inválido: {e}", stream="err"))
        queue.put_event(DoneEvent(
            exit_code=1,
            summary="",
            error=f"Diretório inválido: {e}",
        ))
    except TranscricaoCancelada as e:
        # Caso o `salvar_no_banco` não tenha capturado (não deveria
        # acontecer — ele trata — mas é uma segurança a mais).
        queue.put_event(LogEvent(f"  [cancelado] {e}", stream="err"))
        queue.put_event(DoneEvent(
            exit_code=0,
            summary="Cancelado durante transcrição.",
        ))
    except Exception as e:  # noqa: BLE001 — captura ampla de propósito
        tb = traceback.format_exc()
        queue.put_event(LogEvent(f"[ERRO] {type(e).__name__}: {e}", stream="err"))
        queue.put_event(LogEvent(tb, stream="err"))
        queue.put_event(DoneEvent(
            exit_code=2,
            summary="",
            error=f"{type(e).__name__}: {e}",
        ))
    finally:
        if tmp_ctx is not None:
            tmp_ctx.cleanup()  # apaga a pasta temporária, mesmo se erro

