# -*- coding: utf-8 -*-
"""
============================================================================
Launcher da GUI do SONAX.

Use este script para abrir a interface gráfica **independentemente do
diretório em que você esteja** no terminal. Ele resolve dois problemas
comuns de `python -m app.view`:

    1. Se o CWD for `app/`, o `-m` procura `app.app.view` (não existe).
    2. O `.env` é lido a partir do CWD por `app.database.config`, então
       se você rodar de outro lugar, o banco não conecta.

Este launcher força o CWD = raiz do projeto (a mesma pasta onde está
o `.env` e o `requirements.txt`) antes de delegar ao módulo.

Uso:
    python run_gui.py
    # ou, dentro do venv:
    .venv\\Scripts\\python.exe run_gui.py
============================================================================
"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


_RAIZ = Path(__file__).resolve().parent

# 1) Garante que o CWD é a raiz do projeto (importante para o .env).
os.chdir(_RAIZ)

# 2) Garante que a raiz está no sys.path (importante para `app.*`).
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

# 3) Delega ao entry-point `app.view.__main__`.
runpy.run_module("app.view.__main__", run_name="__main__", alter_sys=True)
