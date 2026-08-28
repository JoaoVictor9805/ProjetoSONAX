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
from app.main import coletar_wavs, resolver_destino
from app.services.script import (
    classificar_wavs,
    copiar_longos_para_pasta,
    salvar_no_banco,
)
from app.services.transcrever import TranscricaoCancelada
from app.view.events import DoneEvent, EventQueue, LogEvent, ProgressEvent
from app.view.stream import redirect_stdio


def run_pipeline(
    diretorio: Path,
    queue: EventQueue,
    cancel: threading.Event,  # noqa: ARG001 — reservado para cancelamento futuro
) -> None:
    """Executa o pipeline completo. Enfileira eventos; termina com `DoneEvent`.

    Esta função é **bloqueante** e deve rodar em uma thread separada
    para não congelar a main loop do Tk.
    """
    try:
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

            # 3) Cópia para a pasta destino
            destino = resolver_destino(diretorio)
            queue.put_event(LogEvent(f"Pasta de destino: {destino}"))
            queue.put_event(ProgressEvent(done=0, total=1, phase="copying"))
            copiados = copiar_longos_para_pasta(longos, destino)
            queue.put_event(LogEvent(
                f"{len(copiados)} arquivo(s) copiado(s) para: {destino}"
            ))
            queue.put_event(ProgressEvent(done=1, total=1, phase="copying"))

            # 4) Transcrição (Whisper) + INSERT.
            #    A barra agora é **granular por arquivo**: o callback
            #    `on_progress` é chamado antes de cada transcrição em
            #    [app/services/script.py](app/services/script.py) com
            #    `(i, total, caminho)`, e nós emitimos um ProgressEvent
            #    determinável a partir dele. A fase final ("inserting")
            #    é apenas o fecho para 100% — o INSERT por arquivo é
            #    rápido e não tem hook próprio.
            #
            #    Cancelamento: `cancel` é checado entre cada arquivo
            #    em `transcrever_dict` e no loop de INSERT de
            #    `salvar_no_banco`. O botão "Cancelar" da GUI, além de
            #    marcar o flag, injeta `TranscricaoCancelada` direto em
            #    **esta** thread (via `PyThreadState_SetAsyncExc` em
            #    `app.py`), o que derruba já a inferência do Whisper em
            #    andamento. `salvar_no_banco` captura e encerra limpo.
            total = len(copiados)
            queue.put_event(LogEvent(
                f"Transcrevendo e gravando {total} arquivo(s) no banco ..."
            ))

            def on_progress(i: int, tot: int, caminho) -> None:  # noqa: ARG001
                # ARG001: 'caminho' não usado aqui (vai no LogEvent
                # via _emit do transcrever). A interface usa o i/total.
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
