# -*- coding: utf-8 -*-
"""
============================================================================
Launcher da GUI do SONAX.

Centraliza o que `run_gui.py` faz hoje: garante CWD = raiz do projeto
(para o `.env` ser lido por `app.database.config`) e a raiz estar no
`sys.path` (para `app.*` resolver), e delega ao entrypoint da view.

Função pública:
    iniciar_gui()  — faz o setup e abre a janela principal.

Por que este módulo existe:
    O `python -m` não consegue fazer `chdir` antes de importar. O `chdir`
    precisa rodar em um script executado, e `run_gui.py` (na raiz) é o
    lugar mais óbvio para o usuário achar. Manter a lógica aqui torna a
    inicialização testável e importável por outros pontos de entrada.
============================================================================
"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


def _obter_raiz() -> Path:
    """Retorna a raiz do projeto (ou a pasta do executável se congelado)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _garantir_raiz_no_path() -> Path:
    """Coloca a raiz do projeto no `sys.path` se ainda não estiver.

    Returns:
        Path: a raiz do projeto (um nível acima de `app/`).
    """
    raiz = _obter_raiz()
    if str(raiz) not in sys.path:
        sys.path.insert(0, str(raiz))
    return raiz


def iniciar_gui() -> None:
    """Força CWD = raiz, ajusta `sys.path` e inicia o loop da janela principal."""
    raiz = _obter_raiz()
    os.chdir(raiz)
    _garantir_raiz_no_path()
    
    from app.view.app import App
    App().mainloop()
