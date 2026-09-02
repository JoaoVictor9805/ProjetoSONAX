# -*- coding: utf-8 -*-
"""
============================================================================
4. dialogs.py — o balconista que pergunta o endereço

Bem pequeno, faz uma coisa só: abrir aquela janelinha do sistema operacional onde você navega e escolhe uma pasta.

python
def pick_folder(parent, initial=None) -> str | None:
    return filedialog.askdirectory(
        parent=parent,
        initialdir=...,
        title="Selecione a pasta com os .wav",
        mustexist=True,
    )

filedialog.askdirectory já vem pronto do Python — não é código nosso, é o seletor de pasta nativo do Windows/Linux/Mac. mustexist=True trava pra você não conseguir "inventar" um caminho que não existe. Se você cancelar, ele devolve vazio, e o app.py entende isso como "ok, não fez nada, seguimos esperando".

Existir separado do app.py é só organização: se um dia quiserem trocar esse seletor por outro, mexe só aqui, sem bagunçar o resto.
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

def pick_archive(
    parent: ctk.CTk, 
    initial: Path | None = None
    ) -> str | None:
    
    initialdir = str(initial) if initial is not None else str(Path.cwd())
    return filedialog.askopenfilename(
        parent=parent,
        initialdir=initialdir,
        title="Selecione o arquivo .zip ou .rar com os áudios",
        filetypes=[("Arquivos Compactados (*.zip, *.rar)", "*.zip *.rar"), ("Todos", "*.*")],
    )
