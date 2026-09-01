# -*- coding: utf-8 -*-
"""
Atalho de inicialização da GUI do SONAX.

Toda a lógica de boot vive em `app.launcher`. Este arquivo existe só
porque o `python -m` não consegue fazer `chdir` antes de importar —
o `chdir` precisa rodar em um script executado, e este é o lugar mais
óbvio para o usuário achar.

Uso:
    python run_gui.py
"""

from app.launcher import iniciar_gui

if __name__ == "__main__":
    iniciar_gui()
