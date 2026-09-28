# -*- coding: utf-8 -*-
"""
============================================================================
Redirecionamento de Streams (stdout / stderr) para a Engine.

Captura saídas de `print()` e bibliotecas de terceiros durante a execução
do pipeline e as converte em chamadas thread-safe de log da Engine.
============================================================================
"""
from __future__ import annotations

import contextlib
import sys
from typing import Callable, Literal

from app.logs import DEV_PREFIX

LogCallback = Callable[[str, Literal["out", "err"], bool], None]


class StreamCaptureWriter:
    """Adapter file-like que redireciona dados para um callback de log."""

    def __init__(self, callback: LogCallback, stream: Literal["out", "err"]) -> None:
        self._callback = callback
        self._stream: Literal["out", "err"] = stream
        self._buffer = ""

    def write(self, data: str) -> int:
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
        if self._buffer:
            line = self._buffer.strip()
            self._buffer = ""
            if line:
                self._emitir(line)

    def _emitir(self, line: str) -> None:
        if line.startswith(DEV_PREFIX):
            self._callback(line[len(DEV_PREFIX):], self._stream, True)
            return

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

        self._callback(line, self._stream, is_dev)

    def isatty(self) -> bool:
        return False


@contextlib.contextmanager
def redirect_engine_stdio(callback: LogCallback):
    """Substitui sys.stdout e sys.stderr temporariamente direcionando ao callback."""
    orig_out, orig_err = sys.stdout, sys.stderr
    writer_out = StreamCaptureWriter(callback, "out")
    writer_err = StreamCaptureWriter(callback, "err")
    sys.stdout = writer_out
    sys.stderr = writer_err
    try:
        yield
    finally:
        writer_out.flush()
        writer_err.flush()
        sys.stdout = orig_out
        sys.stderr = orig_err
