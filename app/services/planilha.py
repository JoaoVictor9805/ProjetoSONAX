# -*- coding: utf-8 -*-
"""
============================================================================
Serviço de Exportação de Transcrições e Diarizações para Planilha (.xlsx).

Responsabilidades:
    1. Resolver o caminho padrão da planilha na raiz do projeto.
    2. Criar ou anexar registros em `transcricoes_modo_teste.xlsx`.
    3. Aplicar formatação legível (cabeçalho destacado, quebra de linha,
       largura de colunas e filtro automático).
    4. Tratar bloqueio de arquivo aberto no Excel salvando cópia alternativa
       com timestamp na raiz.
============================================================================
"""
from __future__ import annotations

import sys
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

NOME_PLANILHA_PADRAO = "transcricoes_modo_teste.xlsx"
NOME_ABA_PADRAO = "Transcrições"
_EXCEL_MAX_ROW_HEIGHT = 409.5
_EXCEL_MAX_COL_WIDTH = 255.0

_COLUNAS: list[tuple[str, str, int]] = [
    ("Duração (s)", "duracao_segundos", 14),
    ("Transcrição", "transcricao_bruta", 120),
    ("Revisão", "transcricao_diarizada", 160),
]


def obter_raiz_projeto() -> Path:
    """Retorna o diretório raiz do projeto (ou pasta do executável se congelado)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def obter_caminho_planilha_raiz(nome_arquivo: str = NOME_PLANILHA_PADRAO) -> Path:
    """Retorna o caminho completo da planilha na raiz do projeto."""
    return obter_raiz_projeto() / nome_arquivo


def _criar_workbook_formatado() -> tuple[openpyxl.Workbook, Any]:
    """Cria um novo Workbook com cabeçalho estilizado e larguras configuradas."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = NOME_ABA_PADRAO

    cabecalhos = [titulo for titulo, _, _ in _COLUNAS]
    ws.append(cabecalhos)

    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_align = Alignment(horizontal="left", vertical="center", wrap_text=True)

    for col_idx, (_, _, largura) in enumerate(_COLUNAS, start=1):
        celula = ws.cell(row=1, column=col_idx)
        celula.fill = header_fill
        celula.font = header_font
        celula.alignment = header_align
        col_letter = openpyxl.utils.get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = largura

    ws.row_dimensions[1].height = 24
    ws.freeze_panes = "A2"
    ultima_col = openpyxl.utils.get_column_letter(len(_COLUNAS))
    ws.auto_filter.ref = f"A1:{ultima_col}1"

    return wb, ws


def _carregar_ou_criar_workbook(destino: Path) -> tuple[openpyxl.Workbook, Any]:
    """Carrega a planilha existente ou cria uma nova formatada."""
    if destino.is_file():
        try:
            wb = openpyxl.load_workbook(destino)
            ws = wb[NOME_ABA_PADRAO] if NOME_ABA_PADRAO in wb.sheetnames else wb.active
            return wb, ws
        except Exception:
            pass
    return _criar_workbook_formatado()


def _contar_linhas_visuais(texto: str, largura_coluna: float, font_size: int) -> int:
    """Estima quantas linhas visuais o texto ocupará na célula com quebra automática."""
    if not texto:
        return 1
    escala_fonte = 11.0 / max(font_size, 6)
    chars_por_linha = max(20, int(largura_coluna * escala_fonte * 0.92))
    total = 0
    for paragrafo in texto.splitlines():
        if not paragrafo:
            total += 1
        else:
            total += len(
                textwrap.wrap(
                    paragrafo,
                    width=chars_por_linha,
                    break_long_words=True,
                    break_on_hyphens=False,
                )
            ) or 1
    return max(1, total)


def ajustar_layout_planilha(ws: Any) -> None:
    """Ajusta larguras de coluna, fonte e altura das linhas sem alterar valores das células.

    Garante que textos longos fiquem totalmente visíveis sem precisar clicar na célula,
    respeitando o limite máximo do Excel (409.5 pt de altura por linha e 255 de largura).
    """
    alinhamento = Alignment(horizontal="left", vertical="top", wrap_text=True)

    # Define largura ideal por coluna de texto (entre mínimo padrão e 255)
    larguras: dict[int, float] = {1: 14.0, 2: 120.0, 3: 160.0}
    for col_idx in (2, 3):
        candidatas = [120.0, 160.0, 200.0, 235.0, _EXCEL_MAX_COL_WIDTH]
        largura_escolhida = candidatas[0]
        for w in candidatas:
            cabe_em_9pt = True
            for r in range(2, ws.max_row + 1):
                txt = str(ws.cell(row=r, column=col_idx).value or "")
                linhas = _contar_linhas_visuais(txt, w, font_size=9)
                if (linhas * 12.2 + 8.0) > _EXCEL_MAX_ROW_HEIGHT:
                    cabe_em_9pt = False
                    break
            largura_escolhida = w
            if cabe_em_9pt:
                break
        larguras[col_idx] = largura_escolhida

    for col_idx, largura in larguras.items():
        col_letter = openpyxl.utils.get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = largura

    # Ajusta fonte e altura de cada linha de dados preservando integralmente o conteúdo
    for r in range(2, ws.max_row + 1):
        # Primeiro testa altura com fonte 9pt; se ultrapassar 409.5pt, usa 8pt para caber tudo
        font_size = 9
        max_linhas = 1
        for col_idx in (2, 3):
            txt = str(ws.cell(row=r, column=col_idx).value or "")
            linhas = _contar_linhas_visuais(txt, larguras[col_idx], font_size=9)
            max_linhas = max(max_linhas, linhas)

        altura_9pt = max_linhas * 12.2 + 8.0
        if altura_9pt > _EXCEL_MAX_ROW_HEIGHT:
            font_size = 8
            max_linhas = 1
            for col_idx in (2, 3):
                txt = str(ws.cell(row=r, column=col_idx).value or "")
                linhas = _contar_linhas_visuais(txt, larguras[col_idx], font_size=8)
                max_linhas = max(max_linhas, linhas)
            altura_final = min(_EXCEL_MAX_ROW_HEIGHT, max(22.0, max_linhas * 10.8 + 8.0))
        else:
            altura_final = max(22.0, altura_9pt)

        fonte_linha = Font(size=font_size)
        for col_idx in range(1, min(ws.max_column, len(_COLUNAS)) + 1):
            celula = ws.cell(row=r, column=col_idx)
            celula.alignment = alinhamento
            celula.font = fonte_linha

        ws.row_dimensions[r].height = round(altura_final, 1)


def salvar_transcricoes_planilha(
    registros: list[dict[str, Any]],
    caminho: Path | None = None,
) -> Path:
    """Salva ou anexa os registros de transcrição/diarização em planilha `.xlsx`.

    Caso o arquivo padrão esteja aberto/bloqueado (PermissionError), salva em
    um novo arquivo com timestamp no mesmo diretório e retorna o caminho final.
    """
    destino = caminho if caminho is not None else obter_caminho_planilha_raiz()
    destino.parent.mkdir(parents=True, exist_ok=True)

    wb, ws = _carregar_ou_criar_workbook(destino)

    for reg in registros:
        duracao = reg.get("duracao_segundos")
        duracao_fmt = round(float(duracao), 2) if duracao is not None else ""

        linha = [
            duracao_fmt,
            reg.get("transcricao_bruta") or "",
            reg.get("transcricao_diarizada") or "",
        ]
        ws.append(linha)

    ajustar_layout_planilha(ws)

    ultima_col = openpyxl.utils.get_column_letter(len(_COLUNAS))
    ws.auto_filter.ref = f"A1:{ultima_col}{max(1, ws.max_row)}"

    try:
        wb.save(destino)
        return destino
    except PermissionError:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino_alt = destino.with_name(f"{destino.stem}_{ts}{destino.suffix}")
        wb.save(destino_alt)
        return destino_alt
