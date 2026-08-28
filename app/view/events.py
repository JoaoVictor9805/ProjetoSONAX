# -*- coding: utf-8 -*-
"""
============================================================================
Contrato de comunicação entre a thread de trabalho (`worker.py`) e a
main loop do Tk (`app.py`).

Toda mensagem trocada entre as duas pontas é uma instância de uma das
três dataclasses abaixo. A fila é um wrapper de `queue.Queue` apenas
para dar nome semântico (`put_event` / `get_event`).
============================================================================
"""

from __future__ import annotations

import queue
from dataclasses import dataclass
from typing import Literal


# ----------------------------------------------------------------------------
# Tipos de evento
# ----------------------------------------------------------------------------

@dataclass
class LogEvent:
    """Uma linha de texto emitida pelo worker (geralmente via `print`)."""
    line: str
    stream: Literal["out", "err"] = "out"


@dataclass
class ProgressEvent:
    """Atualização de progresso.

    `total == 0` indica progresso **indeterminado** (ex.: transcrição
    com Whisper, onde não temos contagem confiável de sub-passos).
    """
    done: int
    total: int
    phase: str   # "scanning" | "copying" | "transcribing" | "inserting"


@dataclass
class DoneEvent:
    """Sinaliza o fim do pipeline.

    `exit_code` segue a convenção do CLI:
        0  Sucesso (com ou sem WAVs longos).
        1  Diretório inválido.
        2  Falha ao gravar no banco / erro inesperado.
    """
    exit_code: int
    summary: str
    error: str | None = None


# ----------------------------------------------------------------------------
# Fila
# ----------------------------------------------------------------------------

class EventQueue(queue.Queue):
    """Fila thread-safe com nomes semânticos."""

    def put_event(self, event) -> None:  # type: ignore[no-untyped-def]
        """Enfileira um evento (LogEvent | ProgressEvent | DoneEvent)."""
        self.put(event)

    def get_event(self, timeout: float = 0.05):
        """Tenta ler um evento; devolve `None` se nada chegar no timeout."""
        try:
            return self.get(timeout=timeout)
        except queue.Empty:
            return None
