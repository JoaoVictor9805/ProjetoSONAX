# -*- coding: utf-8 -*-
"""
============================================================================
PipelineEngine — Módulo de Execução Profundo do SONAX.

Fornece uma interface mínima de alto nível (`start`, `cancel`, `subscribe`,
`set_dev_mode`, `is_running`) encapsulando:
    1. Gerenciamento seguro de threads de background.
    2. Cancelamento cooperativo e preemptivo via `ThreadInterrupter` (ctypes).
    3. Normalização contínua das 8 fases do pipeline via `ProgressNormalizer`.
    4. Gerenciamento de privacidade e modo de desenvolvimento via `LogSessionManager`.
    5. Execução unificada de tarefas (Pipeline de Transcrição e Fechamento Mensal).
============================================================================
"""
from __future__ import annotations

import logging
import threading
import traceback
from pathlib import Path
from typing import Callable, Literal

from app.engine.events import (
    EngineEvent,
    ExecutionFinishedEvent,
    ExecutionState,
    LogMessageEvent,
    ProgressUpdateEvent,
)
from app.engine.interrupter import ThreadInterrupter
from app.engine.log_session import LogSessionManager
from app.engine.normalizer import ProgressNormalizer
from app.engine.runner import PipelineRunner
from app.engine.stream import redirect_engine_stdio
from app.services.fechamento_ciclo import executar_fechamento_ciclo
from app.services.ia import ProvedorIA
from app.services.transcricao import TranscricaoCancelada

logger = logging.getLogger(__name__)

Listener = Callable[[EngineEvent], None]


class PipelineEngine:
    """Orquestrador do ciclo de execução do SONAX com interface mínima."""

    def __init__(self, modo_dev: bool = False, provedor_ia: ProvedorIA | None = None) -> None:
        self._modo_dev: bool = modo_dev
        self._provedor_ia: ProvedorIA | None = provedor_ia
        self._dev_event = threading.Event()
        if modo_dev:
            self._dev_event.set()

        self._normalizer = ProgressNormalizer()
        self._log_session = LogSessionManager(modo_dev=modo_dev)
        self._listeners: list[Listener] = []

        self._thread: threading.Thread | None = None
        self._cancel_event = threading.Event()
        self._state = ExecutionState.IDLE
        self._lock = threading.Lock()

    # ------------------------------------------------------------------------
    # Interface Pública Mínima
    # ------------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """Indica se há uma operação ativa no momento."""
        with self._lock:
            return self._state in (ExecutionState.RUNNING, ExecutionState.CANCELLING)

    @property
    def state(self) -> ExecutionState:
        """Retorna o estado atual do ciclo de vida."""
        with self._lock:
            return self._state

    @property
    def modo_dev(self) -> bool:
        """Indica se o modo de desenvolvimento está ativo."""
        return self._modo_dev

    def subscribe(self, listener: Listener) -> None:
        """Registra um ouvinte para receber eventos da Engine."""
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def unsubscribe(self, listener: Listener) -> None:
        """Remove um ouvinte previamente registrado."""
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def set_dev_mode(self, enabled: bool) -> None:
        """Alterna dinamicamente o modo de desenvolvimento."""
        self._modo_dev = enabled
        self._log_session.modo_dev = enabled
        if enabled:
            self._dev_event.set()
        else:
            self._dev_event.clear()

    def get_formatted_logs(self, modo_dev: bool | None = None) -> list[tuple[str, Literal["out", "err"]]]:
        """Retorna todas as linhas de log formatadas para o modo solicitado."""
        return self._log_session.obter_linhas_formatadas(modo_dev=modo_dev)

    def start(self, entrada: Path) -> None:
        """Inicia a execução do pipeline de transcrição de forma assíncrona.

        Raises:
            RuntimeError: Se já houver um processamento em andamento.
        """
        with self._lock:
            if self._state in (ExecutionState.RUNNING, ExecutionState.CANCELLING):
                raise RuntimeError("Já existe um processamento em andamento na Engine.")

            self._state = ExecutionState.RUNNING
            self._cancel_event.clear()
            self._log_session.limpar()

        runner = PipelineRunner(
            entrada=entrada,
            cancel_event=self._cancel_event,
            dev_mode_event=self._dev_event,
            on_progress=self._handle_runner_progress,
            on_log=self._handle_runner_log,
            on_finished=self._handle_runner_finished,
            provedor_ia=self._provedor_ia,
        )

        self._thread = threading.Thread(
            target=runner.run,
            daemon=True,
            name="sonax-engine-pipeline",
        )
        self._thread.start()

    def cancel(self) -> None:
        """Solicita o cancelamento imediato da execução em andamento."""
        with self._lock:
            if self._state != ExecutionState.RUNNING:
                return
            self._state = ExecutionState.CANCELLING
            self._cancel_event.set()
            thread = self._thread

        # Injeta exceção assíncrona via ctypes para derrubar inferência de IA
        if thread is not None and thread.ident is not None and thread.is_alive():
            ThreadInterrupter.interrupt(thread.ident, TranscricaoCancelada)

    def start_fechamento_mensal(self, ano: int, mes: int, forcar: bool) -> None:
        """Inicia a consolidação macro do fechamento mensal de forma assíncrona.

        Raises:
            RuntimeError: Se já houver um processamento em andamento.
        """
        with self._lock:
            if self._state in (ExecutionState.RUNNING, ExecutionState.CANCELLING):
                raise RuntimeError("Já existe um processamento em andamento na Engine.")

            self._state = ExecutionState.RUNNING
            self._cancel_event.clear()
            self._log_session.limpar()

        def _fechamento_task() -> None:
            self._notify(
                ProgressUpdateEvent(
                    fraction=0.0,
                    label=f"Consolidando ciclo {mes:02d}/{ano} ...",
                    phase="closing",
                    is_indeterminate=True,
                )
            )

            def _progress_callback(frac: float, label: str) -> None:
                self._notify(
                    ProgressUpdateEvent(
                        fraction=frac,
                        label=label,
                        phase="closing",
                        is_indeterminate=False,
                    )
                )

            def _log_callback(msg: str) -> None:
                self._handle_runner_log(msg, "out", False, None)

            def _stdio_callback(line: str, stream: Literal["out", "err"], dev: bool) -> None:
                self._handle_runner_log(line, stream, dev, None)

            try:
                with redirect_engine_stdio(_stdio_callback):
                    resultado = executar_fechamento_ciclo(
                        ano=ano,
                        mes=mes,
                        forcar=forcar,
                        cancel=self._cancel_event,
                        on_progress=_progress_callback,
                        on_log=_log_callback,
                    )

                    if resultado.cancelado or self._cancel_event.is_set():
                        self._handle_runner_finished(
                            exit_code=1,
                            summary=f"Fechamento {mes:02d}/{ano} cancelado pelo usuário.",
                            error=None,
                            was_cancelled=True,
                        )
                    elif resultado.falhas > 0:
                        self._handle_runner_finished(
                            exit_code=2,
                            summary=f"Fechamento finalizado: {resultado.processados} processado(s), {resultado.falhas} falha(s).",
                            error=None,
                            was_cancelled=False,
                        )
                    else:
                        self._handle_runner_finished(
                            exit_code=0,
                            summary=f"Fechamento {mes:02d}/{ano} concluído com sucesso ({resultado.processados} agente(s)).",
                            error=None,
                            was_cancelled=False,
                        )
            except Exception as exc:
                tb = traceback.format_exc()
                self._handle_runner_log(
                    "[FALHA TOTAL] Ocorreu uma falha no sistema e o fechamento mensal foi interrompido.",
                    "err", False, None,
                )
                self._handle_runner_log(f"{type(exc).__name__}: {exc}", "err", True, None)
                self._handle_runner_log(tb, "err", True, None)
                self._handle_runner_finished(
                    exit_code=2,
                    summary="Erro durante a consolidação mensal.",
                    error="Falha na consolidação mensal.",
                    was_cancelled=False,
                )

        self._thread = threading.Thread(
            target=_fechamento_task,
            daemon=True,
            name="sonax-engine-fechamento",
        )
        self._thread.start()

    # ------------------------------------------------------------------------
    # Handlers Internos e Notificação de Eventos
    # ------------------------------------------------------------------------

    def _handle_runner_progress(
        self,
        done: float,
        total: float,
        phase: str,
        message: str | None,
        path: str | None,
    ) -> None:
        """Normaliza o progresso bruto e propaga aos assinantes."""
        if path:
            self._log_session.aprender_rotulo(message or "", path)

        event = self._normalizer.normalize(done, total, phase, message)
        self._notify(event)

        # Se houver mensagem informativa não-silenciosa, envia também como log
        if message:
            self._handle_runner_log(message, "out", False, path)

    def _handle_runner_log(
        self,
        line: str,
        stream: Literal["out", "err"],
        dev_only: bool,
        path: str | None,
    ) -> None:
        """Registra a linha de log e notifica ouvintes."""
        entry = self._log_session.adicionar_linha(line, stream=stream, path=path, dev_only=dev_only)
        texto_formatado = self._log_session.formatar_linha(entry)
        self._notify(
            LogMessageEvent(
                text=texto_formatado,
                stream=stream,
                dev_only=dev_only,
            )
        )

    def _handle_runner_finished(
        self,
        exit_code: int,
        summary: str,
        error: str | None,
        was_cancelled: bool,
    ) -> None:
        """Conclui a execução e notifica o estado terminal."""
        with self._lock:
            if was_cancelled or self._cancel_event.is_set():
                self._state = ExecutionState.COMPLETED if exit_code == 0 else ExecutionState.FAILED
                was_cancelled = True
            elif exit_code == 0:
                self._state = ExecutionState.COMPLETED
            else:
                self._state = ExecutionState.FAILED
            self._thread = None

        self._notify(
            ExecutionFinishedEvent(
                exit_code=exit_code,
                summary=summary,
                error=error,
                was_cancelled=was_cancelled,
            )
        )

    def _notify(self, event: EngineEvent) -> None:
        """Dispara o evento para todos os observadores cadastrados."""
        with self._lock:
            listeners = list(self._listeners)

        for listener in listeners:
            try:
                listener(event)
            except Exception as e:
                logger.exception("Erro ao notificar listener na PipelineEngine: %s", e)
