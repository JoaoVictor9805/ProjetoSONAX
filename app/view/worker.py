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
from app.database.config import get_database_url
from app.services.archives import (
    DescompactacaoError,
    descompactar_arquivo,
    eh_arquivo_compactado,
)
from app.services.io import coletar_wavs, resolver_destino
from app.services.script import (
    classificar_wavs,
    copiar_longos_para_pasta,
    salvar_no_banco,
    filtrar_por_qualidade_audio,
    deletar_pasta,
    gerar_revisao_transcricao,
    gerar_analise_revisao
)

from app.services.transcricao import TranscricaoCancelada
from app.view.events import DoneEvent, EventQueue, LogEvent, ProgressEvent
from app.view.stream import redirect_stdio


def run_pipeline(
    entrada: Path,
    queue: EventQueue,
    cancel: threading.Event, 
    dev_event: threading.Event | None = None,
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
            queue.put_event(LogEvent(f"[INFO] Excluindo pasta temporária: {destino} ..."))
            deletar_pasta(destino)
        if pasta_extracao is not None and pasta_extracao.exists():
            queue.put_event(LogEvent(f"[INFO] Excluindo pasta temporária extraída: {pasta_extracao} ..."))
            deletar_pasta(pasta_extracao)

    def _rotular(i: int, caminho: Path) -> str:
        """Rótulo de exibição do arquivo — sempre o genérico "Audio NN".

        A troca para o nome real (quando o Log Dev está ligado) é feita
        inteiramente em `app.py`, a partir do `path` que viaja junto no
        `ProgressEvent`. Decidir aqui deixaria o texto congelado no
        formato de quando foi impresso, impedindo o toggle de reverter.
        """
        return f"Audio {i:02d}"

    try:
        # Se a GUI passou um .zip ou .rar, extrai na mesma pasta do arquivo.
        if eh_arquivo_compactado(entrada):
            queue.put_event(LogEvent(
                f"[INFO] Descompactando {entrada.name} ...",
                stream="out",
            ))
            try:
                pasta_extracao, diretorio = descompactar_arquivo(entrada)
            except DescompactacaoError as e:
                _limpar_temporarios()
                queue.put_event(LogEvent(
                    "[FALHA TOTAL] Não foi possível descompactar o arquivo enviado.",
                    stream="err",
                ))
                queue.put_event(LogEvent(
                    f"{type(e).__name__}: {e}", stream="err", dev_only=True,
                ))
                queue.put_event(LogEvent(
                    traceback.format_exc(), stream="err", dev_only=True,
                ))
                queue.put_event(DoneEvent(
                    exit_code=1,
                    summary="",
                    error="Arquivo compactado inválido ou corrompido.",
                ))
                return
                
            queue.put_event(LogEvent(
                f"[INFO] Extraído em: {diretorio}", stream="out",
            ))
        else:
            diretorio = entrada

        # Pre-check do .env — se faltar variável, aborta cedo com mensagem clara.
        try:
            get_database_url()
        except KeyError as e:
            _limpar_temporarios()
            queue.put_event(LogEvent(
                "[FALHA TOTAL] Configuração do sistema ausente ou incompleta (.env).",
                stream="err",
            ))
            queue.put_event(LogEvent(
                f"{type(e).__name__}: {e}", stream="err", dev_only=True,
            ))
            queue.put_event(LogEvent(
                traceback.format_exc(), stream="err", dev_only=True,
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
                message="[INFO] Varrendo arquivos .wav ...",
            ))
            wavs = coletar_wavs(diretorio)
            queue.put_event(ProgressEvent(
                done=1, total=1, phase="scanning",
                message=f"[INFO] Varredura concluída: {len(wavs)} arquivo(s) .wav encontrado(s).",
            ))

            if not wavs:
                _limpar_temporarios()
                queue.put_event(LogEvent("[INFO] Nenhum .wav encontrado no diretório."))
                queue.put_event(DoneEvent(
                    exit_code=0,
                    summary="[INFO] Nenhum .wav encontrado.",
                ))
                return

            if cancel.is_set():
                _limpar_temporarios()
                queue.put_event(DoneEvent(
                    exit_code=0,
                    summary="[CANCELADO] Cancelado antes de iniciar classificação.",
                ))
                return

            # 2) Classificação por duração
            queue.put_event(ProgressEvent(
                done=0, total=1, phase="classifying",
                message="[INFO] Classificando arquivos por duração ...",
            ))
            longos, curtos, invalidos = classificar_wavs(wavs, cancel=cancel)
            queue.put_event(LogEvent(
                f"[INFO] Total: {len(wavs)}  •  >1min: {len(longos)}  •  "
                f"<=1min: {len(curtos)}  •  inválidos: {len(invalidos)}"
            ))
            queue.put_event(ProgressEvent(
                done=1, total=1, phase="classifying",
                message=f"[INFO] Classificação concluída: {len(longos)} áudio(s) >1min elegível(is).",
            ))
                    
            if not longos:
                _limpar_temporarios()
                queue.put_event(LogEvent("[AVISO] Nenhum áudio com mais de 1 minuto encontrado."))
                queue.put_event(DoneEvent(
                    exit_code=0,
                    summary="[AVISO] Nenhum áudio >1min encontrado.",
                ))
                return

            if cancel.is_set():
                _limpar_temporarios()
                queue.put_event(DoneEvent(
                    exit_code=0,
                    summary="[CANCELADO] Cancelado antes de iniciar cópia.",
                ))
                return

            # 2.5) Filtragem de qualidade de áudio
            def on_quality_progress(idx: int, tot: int, p: Path) -> None:
                # Evento "silencioso": não aparece como linha própria no
                # log (quem já imprime as linhas visíveis é a própria
                # filtrar_por_qualidade_audio, via print). Serve só para
                # ensinar app.py._rotulos o mapa "Audio NN" -> nome real,
                # do mesmo jeito que on_copy_progress faz para a cópia.
                queue.put_event(ProgressEvent(
                    done=1, total=1, phase="classifying",
                    message=f"[INFO] {_rotular(idx, p)}",
                    path=p.name,
                    silent=True,
                ))

            longos, rejeitados = filtrar_por_qualidade_audio(
                longos, cancel=cancel, modo_dev=dev_event,
                on_progress=on_quality_progress,
            )
            invalidos.extend(rejeitados)
            if rejeitados:
                queue.put_event(LogEvent(
                    f"[AVISO] {len(rejeitados)} áudio(s) reprovados e excluídos do processamento."
                ))

            # 3) Cópia para a pasta destino
            destino = resolver_destino(diretorio)
            queue.put_event(LogEvent(f"[INFO] Pasta de destino: {destino}"))
            queue.put_event(ProgressEvent(
                done=0, total=len(longos), phase="copying",
                message=f"[INFO] Copiando {len(longos)} arquivo(s) para a pasta de trabalho ...",
            ))

            def on_copy_progress(idx: int, tot: int, p: Path) -> None:
                queue.put_event(ProgressEvent(
                    done=idx, total=tot, phase="copying",
                    message=f"[INFO] Copiado ({idx}/{tot}): {_rotular(idx, p)}",
                    path=p.name,
                ))

            copiados = copiar_longos_para_pasta(
                longos, destino, cancel=cancel, on_progress=on_copy_progress,
            )
            queue.put_event(LogEvent(
                f"[INFO] {len(copiados)} arquivo(s) copiado(s) para: {destino}"
            ))
            queue.put_event(ProgressEvent(
                done=len(copiados), total=len(copiados), phase="copying",
                message=f"[INFO] {len(copiados)} arquivo(s) copiado(s) com sucesso.",
            ))

            if cancel.is_set():
                _limpar_temporarios()
                queue.put_event(DoneEvent(
                    exit_code=0,
                    summary="[CANCELADO] Cancelado antes de iniciar transcrição.",
                ))
                return

            # 4) Transcrição (NVIDIA Nemotron via OpenRouter) + INSERT no banco
            total = len(copiados)
            queue.put_event(ProgressEvent(
                done=0, total=total, phase="transcribing",
                message=f"[INFO] Iniciando transcrição (NVIDIA Nemotron) de {total} arquivo(s) ...",
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
                    message=msg if msg else f"[INFO] [{i}/{tot}] Processando: {_rotular(i, caminho)}",
                    path=caminho.name,
                ))

            inseridos, ja_existentes, mapa_diarizacao = salvar_no_banco(
                copiados, cancel=cancel, on_progress=on_progress, modo_dev=dev_event,
            )

            detalhes_existentes = f" | [INFO] {ja_existentes} já existente(s)" if ja_existentes > 0 else ""

            if cancel.is_set():
                _limpar_temporarios()
                queue.put_event(DoneEvent(
                    exit_code=0,
                    summary=f"[CANCELADO] Cancelado após {inseridos} registro(s) "
                            f"inserido(s) com transcrição {detalhes_existentes}.",
                ))
                return

            queue.put_event(ProgressEvent(
                done=total, total=total, phase="inserting",
                message=f"[INFO] Transcrição finalizada: {inseridos} registro(s) processado(s) {detalhes_existentes}.",
            ))

            # 4.5) Diarização e revisão (Qwen Instruct) + inserção no banco
            total_copiados = len(copiados)

            for idx, (caminho, _) in enumerate(copiados, 1):
                if cancel.is_set():
                    break

                rotulo_audio = _rotular(idx, caminho)
                queue.put_event(ProgressEvent(
                    done=idx - 1, total=total_copiados, phase="reviewing",
                    message=f"[INFO] [{idx}/{total_copiados}] Diarizando e revisando (Qwen Instruct): {rotulo_audio} ...",
                    path=caminho.name,
                ))

                dados_audio = mapa_diarizacao.get(caminho.name, {})
                texto_diarizado = dados_audio.get("texto_diarizado")
                agente_nome = dados_audio.get("agente_nome")

                gerar_revisao_transcricao(
                    caminho.name,
                    texto_diarizado=texto_diarizado,
                    agente_nome=agente_nome,
                    rotulo_audio=rotulo_audio,
                    cancel=cancel,
                )
                if cancel.wait(1.2):
                    break

            if cancel.is_set():
                _limpar_temporarios()
                queue.put_event(DoneEvent(
                    exit_code=0,
                    summary=f"[CANCELADO] Cancelado durante a diarização e revisão ({inseridos} registro(s) inserido(s)).",
                ))
                return

            queue.put_event(ProgressEvent(
                done=total_copiados, total=total_copiados, phase="reviewing",
                message="[INFO] Diarização e revisão das transcrições finalizada.",
            ))

            # 4.75) Realizar análise com IA (GPT-4o-mini)
            for idx, (caminho, _) in enumerate(copiados, 1):
                if cancel.is_set():
                    break

                rotulo_audio = _rotular(idx, caminho)

                queue.put_event(ProgressEvent(
                    done = idx - 1,
                    total = total_copiados,
                    phase="analyzing",
                    message= f"[INFO] [{idx}/{total_copiados}] Analisando critérios PEAH (GPT-4o-mini): {rotulo_audio} ...",
                    path=caminho.name,
                ))

                gerar_analise_revisao(
                    caminho.name,
                    rotulo_audio=rotulo_audio,
                    cancel=cancel,
                )
                
                if cancel.wait(1.2):
                        break


            if cancel.is_set():
                _limpar_temporarios()
                queue.put_event(DoneEvent(
                    exit_code=0,
                    summary=f"[CANCELADO] Cancelado durante a análise ({inseridos} registro(s) inserido(s)).",
                ))
                return

            queue.put_event(ProgressEvent(
                done=total_copiados,
                total=total_copiados,
                phase="analyzing",
                message="[INFO] Análise das ligações finalizada.",
            ))

            # 5) Exclusão das pastas temporárias geradas
            queue.put_event(ProgressEvent(
                done=0, total=1, phase="cleanup",
                message="[INFO] Limpando arquivos temporários ...",
            ))
            _limpar_temporarios()
            queue.put_event(ProgressEvent(
                done=1, total=1, phase="cleanup",
                message="[INFO] Limpeza concluída.",
            ))
            queue.put_event(DoneEvent(
                exit_code=0,
                summary=f"[INFO] {inseridos} registro(s) inserido(s) com transcrição {detalhes_existentes}.",
            ))

    except FileNotFoundError as e:
        _limpar_temporarios()
        queue.put_event(LogEvent(
            "[FALHA TOTAL] Diretório de arquivos inválido ou inacessível.",
            stream="err",
        ))
        queue.put_event(LogEvent(
            f"{type(e).__name__}: {e}", stream="err", dev_only=True,
        ))
        queue.put_event(LogEvent(
            traceback.format_exc(), stream="err", dev_only=True,
        ))
        queue.put_event(DoneEvent(
            exit_code=1,
            summary="",
            error="Diretório de arquivos inválido ou inacessível.",
        ))
    except TranscricaoCancelada as e:
        # Caso o `salvar_no_banco` não tenha capturado (não deveria
        # acontecer — ele trata — mas é uma segurança a mais).
        _limpar_temporarios()
        queue.put_event(LogEvent(f"[CANCELADO] Cancelado durante transcrição"))
        queue.put_event(DoneEvent(
            exit_code=0,
            summary="[CANCELADO] Cancelado durante transcrição.",
        ))
    except Exception as e:  # noqa: BLE001 — captura ampla de propósito
        _limpar_temporarios()
        tb = traceback.format_exc()
        queue.put_event(LogEvent(
            "[FALHA TOTAL] Ocorreu um erro inesperado e o processamento foi interrompido.",
            stream="err",
        ))
        queue.put_event(LogEvent(
            f"{type(e).__name__}: {e}", stream="err", dev_only=True,
        ))
        queue.put_event(LogEvent(tb, stream="err", dev_only=True))
        queue.put_event(DoneEvent(
            exit_code=2,
            summary="",
            error="Erro inesperado durante o processamento.",
        ))

