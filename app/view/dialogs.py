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

from datetime import datetime
from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from app.services.fechamento_ciclo import mes_anterior_padrao


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


class ModalFechamentoMensal(ctk.CTkToplevel):
    """Janela modal para seleção de Mês/Ano e execução do Fechamento Mensal Macro."""

    def __init__(
        self,
        parent: ctk.CTk,
        on_confirm: Callable[[int, int, bool], None],
    ) -> None:
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("Fechamento Mensal de Qualidade")
        self.geometry("400x320")
        self.resizable(False, False)

        self._parent = parent
        self._on_confirm = on_confirm

        ano_padrao, mes_padrao = mes_anterior_padrao()

        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=24, pady=20)

        ctk.CTkLabel(
            container,
            text="📊 Fechamento Mensal (Macro)",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w")

        ctk.CTkLabel(
            container,
            text="Consolida médias dos critérios, pontos fortes, fragilidades e\nplano de ação de cada atendente para o Power BI.",
            text_color="#bdc3c7",
            font=ctk.CTkFont(size=12),
            justify="left",
        ).pack(anchor="w", pady=(4, 16))

        # Seletores de Mês e Ano
        row_sel = ctk.CTkFrame(container, fg_color="transparent")
        row_sel.pack(fill="x", pady=(0, 12))

        col_mes = ctk.CTkFrame(row_sel, fg_color="transparent")
        col_mes.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkLabel(col_mes, text="Mês:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(0, 4))

        self._meses_nomes = [
            "01 - Janeiro", "02 - Fevereiro", "03 - Março", "04 - Abril",
            "05 - Maio", "06 - Junho", "07 - Julho", "08 - Agosto",
            "09 - Setembro", "10 - Outubro", "11 - Novembro", "12 - Dezembro"
        ]
        self._combo_mes = ctk.CTkComboBox(
            col_mes,
            values=self._meses_nomes,
            state="readonly",
        )
        self._combo_mes.set(self._meses_nomes[mes_padrao - 1])
        self._combo_mes.pack(fill="x")

        col_ano = ctk.CTkFrame(row_sel, fg_color="transparent")
        col_ano.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(col_ano, text="Ano:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(0, 4))

        ano_atual = datetime.now().year
        anos = [str(a) for a in range(ano_atual - 2, ano_atual + 2)]
        self._combo_ano = ctk.CTkComboBox(
            col_ano,
            values=anos,
            state="readonly",
        )
        self._combo_ano.set(str(ano_padrao))
        self._combo_ano.pack(fill="x")

        # Checkbox forçar
        self._chk_forcar = ctk.CTkCheckBox(
            container,
            text="Atualizar atendentes já consolidados no ciclo",
            font=ctk.CTkFont(size=12),
        )
        self._chk_forcar.pack(anchor="w", pady=(6, 20))
        self._chk_forcar.select()

        # Botões de Ação
        row_btn = ctk.CTkFrame(container, fg_color="transparent")
        row_btn.pack(fill="x")

        btn_cancelar = ctk.CTkButton(
            row_btn,
            text="Cancelar",
            width=100,
            fg_color="#7f8c8d",
            hover_color="#95a5a6",
            command=self.destroy,
        )
        btn_cancelar.pack(side="left")

        btn_iniciar = ctk.CTkButton(
            row_btn,
            text="Iniciar Consolidação",
            fg_color="#D17004",
            hover_color="#B5650D",
            command=self._on_iniciar,
        )
        btn_iniciar.pack(side="right", fill="x", expand=True, padx=(8, 0))

    def _on_iniciar(self) -> None:
        idx_mes = self._meses_nomes.index(self._combo_mes.get()) + 1
        ano = int(self._combo_ano.get())
        forcar = bool(self._chk_forcar.get())
        self.destroy()
        self._on_confirm(ano, idx_mes, forcar)

