# -*- coding: utf-8 -*-
"""
============================================================================
Redirecionamento de stdout/stderr para a fila de eventos.

`QueueWriter` é um objeto *file-like* mínimo: cada `write()` acumula um
buffer e, a cada `\\n` encontrado, enfileira um `LogEvent` com a linha
completa. O context manager `redirect_stdio` troca `sys.stdout` /
`sys.stderr` por dois `QueueWriter` durante a execução do worker, e
restaura no `__exit__` — mesmo se houver exceção.

Isso permite reaproveitar **todos** os `print()` existentes em
`app.services.*` e `app.main` sem precisar alterá-los. O `_emit()` em
[app/services/transcrever.py:23-25](app/services/transcrever.py#L23-L25)
já usa `flush=True`, então as linhas do Whisper chegam em tempo real.
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
