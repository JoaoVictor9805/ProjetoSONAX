# -*- coding: utf-8 -*-
"""
Pacote `app.engine` — Módulo de Execução Profundo do SONAX.

Exporta a Engine de Execução e os tipos de eventos normalizados.
"""
from app.engine.engine import PipelineEngine
from app.engine.events import (
    EngineEvent,
    ExecutionFinishedEvent,
    ExecutionState,
    LogMessageEvent,
    ProgressUpdateEvent,
)
from app.engine.normalizer import ProgressNormalizer

__all__ = [
    "PipelineEngine",
    "EngineEvent",
    "ProgressUpdateEvent",
    "LogMessageEvent",
    "ExecutionFinishedEvent",
    "ExecutionState",
    "ProgressNormalizer",
]
