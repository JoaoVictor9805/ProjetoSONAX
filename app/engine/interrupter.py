# -*- coding: utf-8 -*-
"""
============================================================================
Interrupção Assíncrona de Threads (ctypes).

Fornece interrupção preemptiva segura para threads Python injetando uma
exceção assíncrona via `PyThreadState_SetAsyncExc`.
Utilizado pela Engine para interromper imediatamente inferências de IA
(ex: Whisper) sem expor ponteiros ou bibliotecas C para camadas superiores.
============================================================================
"""
from __future__ import annotations

import ctypes
import logging

logger = logging.getLogger(__name__)


class ThreadInterrupter:
    """Controlador de interrupção assíncrona de threads."""

    @staticmethod
    def interrupt(thread_id: int | None, exc_type: type[BaseException]) -> bool:
        """Injeta uma exceção assíncrona na thread indicada por `thread_id`.

        Args:
            thread_id: Identificador nativo da thread (`threading.Thread.ident`).
            exc_type: Tipo da exceção a ser injetada (ex: `TranscricaoCancelada`).

        Returns:
            bool: True se a exceção foi entregue com sucesso, False caso contrário.
        """
        if thread_id is None:
            return False

        try:
            api = ctypes.pythonapi.PyThreadState_SetAsyncExc
        except AttributeError:
            logger.warning("PyThreadState_SetAsyncExc não disponível nesta plataforma.")
            return False

        # Compatibilidade com plataformas 32-bit e 64-bit (Windows/Linux)
        for id_type in (ctypes.c_ulonglong, ctypes.c_ulong):
            try:
                api.argtypes = [id_type, ctypes.py_object]
                api.restype = ctypes.c_int
                res = api(id_type(thread_id), ctypes.py_object(exc_type))
                if res == 1:
                    return True
                if res > 1:
                    # Inversão: efeito colateral indesejado em múltiplas threads; reverte.
                    api(id_type(thread_id), None)
                    return False
            except Exception as e:
                logger.debug("Tentativa com tipo %s falhou: %s", id_type, e)
                continue

        return False
