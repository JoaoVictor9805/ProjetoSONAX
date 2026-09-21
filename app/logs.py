# -*- coding: utf-8 -*-
"""
============================================================================
Marcação de mensagens técnicas (visíveis somente no Log Dev).

Uma linha impressa com `log_dev(...)` continua sendo um `print()` comum:
ela percorre exatamente o mesmo caminho de sempre
(`QueueWriter` -> `LogEvent` -> GUI). A única diferença é o prefixo
`DEV_PREFIX`, que o `QueueWriter` reconhece, remove e converte em
`LogEvent(dev_only=True)`.

Com isso o mesmo erro gera duas informações:
    - mensagem curta no Log User  -> `print(...)` normal;
    - detalhe técnico no Log Dev  -> `log_dev(...)` / `log_dev_exc()`.

Este módulo mora fora de `app/view` de propósito: assim `app/services/*`
pode importá-lo sem passar a depender da camada de interface.
============================================================================
"""

from __future__ import annotations

import logging
import os
import traceback
import warnings

# Marcador interno. Nunca aparece na GUI — o `QueueWriter` o remove ao
# converter a linha em `LogEvent`.
DEV_PREFIX = "[DEV]"

# Recuo do detalhe técnico, para ele aparecer "pendurado" na mensagem
# de usuário logo acima.
_RECUO = "    "


def log_dev(mensagem: object) -> None:
    """Imprime `mensagem` apenas para o Log Dev (uma linha por quebra)."""
    texto = str(mensagem).rstrip()
    if not texto:
        return
    for linha in texto.splitlines():
        print(f"{DEV_PREFIX}{_RECUO}{linha}")


def log_dev_exc(contexto: str = "") -> None:
    """Imprime o traceback da exceção em tratamento apenas no Log Dev.

    Deve ser chamado de **dentro** de um bloco `except` — fora dele o
    Python já limpou a exceção corrente e não há traceback para formatar.
    """
    if contexto:
        log_dev(contexto)
    log_dev(traceback.format_exc())


def _custom_showwarning(
    message: Warning | str,
    category: type[Warning],
    filename: str,
    lineno: int,
    file: object | None = None,
    line: str | None = None,
) -> None:
    """Redireciona avisos internos de bibliotecas exclusivamente para o Log Dev."""
    log_dev(f"[AVISO INTERNO] {category.__name__}: {message}")


warnings.showwarning = _custom_showwarning


class _DevLoggingHandler(logging.Handler):
    """Handler do logging do Python que redireciona saídas de terceiros para o Log Dev."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            log_dev(msg)
        except Exception:
            pass


def silenciar_loggers_externos() -> None:
    """Redireciona os loggers de bibliotecas barulhentas para o Log Dev."""
    dev_handler = _DevLoggingHandler()
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    dev_handler.setFormatter(formatter)

    for nome in (
        "whisperx",
        "whisperx.diarize",
        "pyannote",
        "huggingface_hub",
        "google_genai",
        "langchain_google_genai",
        "urllib3",
        "lightning",
    ):
        l = logging.getLogger(nome)
        l.handlers.clear()
        l.addHandler(dev_handler)
        l.propagate = False


silenciar_loggers_externos()
