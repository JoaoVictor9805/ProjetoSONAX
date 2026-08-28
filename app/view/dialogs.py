# -*- coding: utf-8 -*-
"""
============================================================================
Helpers de diálogo nativo (seleção de pasta).

Encapsula o uso de `tkinter.filedialog` para manter `app.py` limpo
e desacoplado do toolkit. A janela do `App` já existe no momento em
que o botão é clicado, então passamos ela como `parent` para o diálogo
ficar modal em relação à janela principal.
============================================================================
"""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk


def pick_folder(
    parent: ctk.CTk,
    initial: Path | None = None,
) -> str | None:
    """Abre o diálogo nativo de seleção de pasta.

    Retorna o caminho escolhido como `str`, ou `None` se o usuário
    cancelar. `initial` é o diretório inicial exibido pelo diálogo.
    """
    initialdir = str(initial) if initial is not None else str(Path.cwd())
    return filedialog.askdirectory(
        parent=parent,
        initialdir=initialdir,
        title="Selecione a pasta com os .wav",
        mustexist=True,
    )
