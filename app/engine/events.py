# -*- coding: utf-8 -*-
"""
============================================================================
Eventos de alto nível e tipos do Módulo de Execução (Engine) do SONAX.

A Engine comunica seu progresso, logs e status final por meio destes eventos
estritamente desacoplados de qualquer framework de UI.
============================================================================
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class ExecutionState(str, Enum):
    """Estados do ciclo de vida da Engine."""
    IDLE = "idle"
    RUNNING = "running"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class ProgressUpdateEvent:
    """Evento de progresso já normalizado (0.0 a 1.0) pronto para exibição."""
    fraction: float             # Valor cumulativo entre 0.0 e 1.0
    label: str                  # Texto formatado (ex: "4/10 arquivos  •  45%")
    phase: str                  # Nome da fase ("scanning", "transcribing", etc.)
    done: float = 0.0           # Passo bruto da fase atual
    total: float = 0.0          # Total bruto da fase atual
    message: str | None = None  # Mensagem descritiva associada
    is_indeterminate: bool = False  # True quando o progresso for indeterminado


@dataclass(frozen=True)
class LogMessageEvent:
    """Linha de log emitida durante a execução."""
    text: str                              # Mensagem (já tratada ou mascarada)
    stream: Literal["out", "err"] = "out"   # Origem do stream
    dev_only: bool = False                 # True = mensagem estritamente técnica


@dataclass(frozen=True)
class ExecutionFinishedEvent:
    """Sinaliza conclusão, interrupção ou falha do pipeline."""
    exit_code: int                         # 0 = sucesso, 1 = entrada inválida, 2 = erro
    summary: str                           # Resumo textual
    error: str | None = None               # Mensagem de erro amigável se houver
    was_cancelled: bool = False            # True se foi interrompido pelo usuário


EngineEvent = ProgressUpdateEvent | LogMessageEvent | ExecutionFinishedEvent
