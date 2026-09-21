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

from app.logs import DEV_PREFIX
from app.view.events import EventQueue, LogEvent


class QueueWriter:
    """Adapter file-like que enfileira linhas em uma `EventQueue`."""

    def __init__(self, queue: EventQueue, stream: Literal["out", "err"]) -> None:
        self._queue = queue
        self._stream: Literal["out", "err"] = stream
        self._buffer = ""

    def write(self, data: str) -> int:
        """Acumula `data` e enfileira um `LogEvent` por linha terminada em `\\n` ou `\\r`."""
        if not data:
            return 0
        self._buffer += data
        while True:
            idx_n = self._buffer.find("\n")
            idx_r = self._buffer.find("\r")

            if idx_n == -1 and idx_r == -1:
                break

            if idx_n != -1 and (idx_r == -1 or idx_n < idx_r):
                idx = idx_n
                line = self._buffer[:idx].rstrip("\r")
                self._buffer = self._buffer[idx + 1:]
            else:
                idx = idx_r
                line = self._buffer[:idx]
                self._buffer = self._buffer[idx + 1:]

            line = line.strip()
            if line:
                self._emitir(line)
        return len(data)

    def flush(self) -> None:
        """Despeja qualquer texto remanescente no buffer para a fila."""
        if self._buffer:
            line = self._buffer.strip()
            self._buffer = ""
            if line:
                self._emitir(line)

    def _emitir(self, line: str) -> None:
        """Enfileira a linha, reconhecendo o marcador de mensagem técnica.

        Linhas escritas por `app.logs.log_dev()` chegam aqui prefixadas
        com `DEV_PREFIX`. O prefixo é removido e a linha vira um
        `LogEvent(dev_only=True)` — ou seja, só aparece no Log Dev.
        """
        if line.startswith(DEV_PREFIX):
            self._queue.put_event(
                LogEvent(line[len(DEV_PREFIX):], self._stream, dev_only=True)
            )
            return

        # Redireciona saídas técnicas de bibliotecas de terceiros para o Log Dev
        is_dev = False
        if self._stream == "err":
            is_dev = True
        elif any(
            indicador in line
            for indicador in (
                "whisperx",
                "pyannote",
                "Loading diarization model",
                "UserWarning",
                "FutureWarning",
                "DeprecationWarning",
                "huggingface_hub",
                "automatic function calling",
                "(AFC)",
                "symlink",
                "torchcodec",
            )
        ):
            is_dev = True

        if is_dev:
            self._queue.put_event(LogEvent(line, self._stream, dev_only=True))
        else:
            self._queue.put_event(LogEvent(line, self._stream))

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
        # Flush do que sobrou no buffer antes de restaurar.
        for fake in (sys.stdout, sys.stderr):
            if isinstance(fake, QueueWriter):
                fake.flush()
        sys.stdout = original_out
        sys.stderr = original_err
