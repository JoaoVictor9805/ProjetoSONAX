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

import traceback

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
