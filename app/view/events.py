# -*- coding: utf-8 -*-
"""
============================================================================
Esse arquivo define os tipos de bilhete que a cozinha pode mandar pro balcão, e a própria espeteira.

Três tipos de bilhete (chamados de "eventos"):

python
@dataclass
class LogEvent:
    line: str          # uma linha de texto, tipo "Transcrevendo arquivo 3..."
    stream: str = "out" # "out" (normal) ou "err" (erro)

@dataclass
class ProgressEvent:
    done: int    # quanto já foi feito
    total: int   # quanto falta no total
    phase: str   # em que etapa: "scanning", "copying", "transcribing", "inserting"

@dataclass
class DoneEvent:
    exit_code: int      # 0 = deu certo, 1 = pasta inválida, 2 = erro no banco
    summary: str         # resumo pro usuário ler
    error: str | None    # mensagem de erro, se tiver

Pensa em @dataclass como um "formulário pronto": em vez de você escrever uma classe inteira na mão, o Python gera automático o __init__ e tudo mais, só de você listar os campos.

queue.Queue já é uma fila thread-safe pronta do Python — ou seja, uma thread pode colocar coisa nela e outra pode tirar, sem risco de os dois mexerem ao mesmo tempo e corromper tudo (isso é o problema clássico de threads: duas coisas escrevendo no mesmo lugar ao mesmo tempo e dando pau). put_event/get_event são só apelidos mais bonitos pra put/get.

get_event(timeout=0.05): tenta pegar um bilhete, espera até 50ms, e se não vier nada, devolve None em vez de travar esperando pra sempre. É o "olhei na espeteira, não tinha nada novo, tudo bem, volto depois".
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
