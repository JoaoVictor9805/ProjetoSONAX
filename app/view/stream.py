# -*- coding: utf-8 -*-
"""
============================================================================
Sempre que algo faz print("oi") lá na cozinha, por baixo dos panos o Python chama write("oi\n") nesse objeto. Em vez de mostrar na tela, a gente guarda o texto, espera achar uma quebra de linha (\n), e transforma aquela linha num bilhete LogEvent que vai pra fila. É tipo um funcionário da cozinha que, toda vez que alguém grita alguma coisa, escreve num bilhetinho e joga na espeteira — em vez de gritar direto pro cliente.
============================================================================
"""

from __future__ import annotations

import contextlib
import sys

from typing import Literal

from app.view.events import EventQueue, LogEvent


class QueueWriter:
    """Adapter file-like que enfileira linhas em uma `EventQueue`."""

    def __init__(self, queue: EventQueue, stream: Literal["out", "err"]) -> None:
        self._queue = queue
        self._stream: Literal["out", "err"] = stream
        self._buffer = ""

    def write(self, data: str) -> int:
        """Acumula `data` e enfileira um `LogEvent` por linha terminada em `\\n`."""
        if not data:
            return 0
        self._buffer += data
        while True:
            idx = self._buffer.find("\n")
            if idx == -1:
                break
            line, self._buffer = self._buffer[:idx], self._buffer[idx + 1:]
            if line:
                self._queue.put_event(LogEvent(line, self._stream))
        return len(data)

    def flush(self) -> None:
        """No-op: o `QueueWriter` não tem buffer próprio que precise flush."""
        return None

    def isatty(self) -> bool:
        """Sempre False — estamos roteando para uma fila, não para um TTY."""
        return False


@contextlib.contextmanager
def redirect_stdio(queue: EventQueue):
    """Substitui `sys.stdout`/`sys.stderr` por `QueueWriter`s; restaura ao final."""
    original_out, original_err = sys.stdout, sys.stderr
    sys.stdout = QueueWriter(queue, "out")
    sys.stderr = QueueWriter(queue, "err")
    try:
        yield
    finally:
        # Flush do que sobrou no buffer (linha sem \n final) antes de restaurar.
        for fake in (sys.stdout, sys.stderr):
            if isinstance(fake, QueueWriter) and fake._buffer:
                fake.write("\n")
        sys.stdout = original_out
        sys.stderr = original_err
