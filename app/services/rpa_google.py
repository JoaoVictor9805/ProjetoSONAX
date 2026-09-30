# -*- coding: utf-8 -*-
"""
============================================================================
Serviço de Coleta RPA de Informações no Google via Pywinauto / Navegador.

Responsabilidades:
    1. Formatação e normalização do telefone da empresa contatada.
    2. Pesquisa automatizada no Google via navegador padrão do sistema
       (mantendo a sessão/cookies reais do usuário para evitar bloqueios anti-bot).
    3. Cópia do conteúdo da página via automação de teclado (Ctrl+A, Ctrl+C, Ctrl+W)
       e leitura segura da área de transferência via pyperclip.
    4. Cache por número de telefone para evitar requisições repetidas no mesmo lote.
    5. Suporte a cancelamento cooperativo e tratamento de falhas sem travar o pipeline.
============================================================================
"""
from __future__ import annotations

import re
import threading
import time
import urllib.parse
from typing import Callable


def formatar_telefone_busca(numero: str | None, estado_ddd: str | None = None) -> str | None:
    """Formata o número de telefone e DDD para a busca no Google.

    Exemplos:
        numero='33101010', estado_ddd='41' -> '41 3310-1010'
        numero='41 3310-1010', estado_ddd='41' -> '41 3310-1010'
        numero='0800 591 2117' -> '0800 591 2117'
    """
    if not numero:
        return None

    num_str = str(numero).strip()
    ddd_str = str(estado_ddd).strip() if estado_ddd else ""

    # Remove caracteres não alfanuméricos exceto espaços e traços
    num_limpo = re.sub(r"[^\d]", "", num_str)
    ddd_limpo = re.sub(r"[^\d]", "", ddd_str)

    if not num_limpo:
        return None

    # Se começa com 0800 ou 0300
    if num_limpo.startswith("0800") or num_limpo.startswith("0300"):
        if len(num_limpo) == 11:
            return f"{num_limpo[:4]} {num_limpo[4:7]} {num_limpo[7:]}"
        return num_limpo

    # Se o número já contém o DDD embutido (10 ou 11 dígitos)
    if len(num_limpo) in (10, 11) and (not ddd_limpo or num_limpo.startswith(ddd_limpo)):
        ddd = num_limpo[:2]
        resto = num_limpo[2:]
        if len(resto) == 8:
            return f"{ddd} {resto[:4]}-{resto[4:]}"
        elif len(resto) == 9:
            return f"{ddd} {resto[:5]}-{resto[5:]}"
        return f"{ddd} {resto}"

    # Se o número tem 8 ou 9 dígitos e temos DDD separado
    if len(num_limpo) in (8, 9) and ddd_limpo:
        if len(num_limpo) == 8:
            return f"{ddd_limpo} {num_limpo[:4]}-{num_limpo[4:]}"
        else:
            return f"{ddd_limpo} {num_limpo[:5]}-{num_limpo[5:]}"

    # Fallback: combina o que houver
    if ddd_str and not num_str.startswith(ddd_str):
        return f"{ddd_str} {num_str}".strip()
    return num_str


def coletar_texto_google_telefone(
    telefone: str,
    *,
    cancel: threading.Event | None = None,
    tempo_espera_pagina: float = 6.0,
) -> str:
    """Abre o navegador padrão, busca o telefone no Google, copia o texto e fecha a aba.

    Retorna o texto capturado ou 'Não encontrado' em caso de erro/timeout.
    """
    if cancel is not None and cancel.is_set():
        return "Não encontrado"

    if not telefone or not telefone.strip():
        return "Não encontrado"

    import webbrowser
    import pyperclip
    from pywinauto import keyboard

    query = f"{telefone.strip()} telefone"
    url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"

    try:
        # 1. Limpa área de transferência
        pyperclip.copy("")

        # 2. Abre a aba no navegador padrão
        webbrowser.open(url)

        # 3. Espera a página carregar com verificação periódica de cancelamento
        passo_espera = 0.2
        decorrido = 0.0
        while decorrido < tempo_espera_pagina:
            if cancel is not None and cancel.is_set():
                # Tenta fechar a aba aberta antes de sair
                try:
                    keyboard.send_keys('^w')
                except Exception:
                    pass
                return "Não encontrado"
            time.sleep(passo_espera)
            decorrido += passo_espera

        if cancel is not None and cancel.is_set():
            return "Não encontrado"

        # 4. Seleciona Tudo (Ctrl + A)
        keyboard.send_keys('^a')
        time.sleep(0.6)

        # 5. Copia (Ctrl + C)
        keyboard.send_keys('^c')
        time.sleep(0.6)

        # 6. Fecha a aba atual (Ctrl + W)
        keyboard.send_keys('^w')
        time.sleep(0.5)

        # 7. Captura o texto do clipboard
        texto_copiado = pyperclip.paste()
        if texto_copiado and texto_copiado.strip():
            return texto_copiado.strip()

        return "Não encontrado"

    except Exception as exc:
        print(f"  [AVISO] Falha ao coletar dados do Google para '{telefone}': {exc}")
        return "Não encontrado"


def coletar_textos_google_lote(
    telefones_por_chave: dict[str, str | None],
    *,
    cancel: threading.Event | None = None,
    tempo_espera_pagina: float = 6.0,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, str]:
    """Coleta o texto do Google para um dicionário de chaves -> telefones.

    Aplica cache por telefone para evitar abrir o navegador mais de uma vez
    para o mesmo número de telefone no mesmo lote.
    """
    resultado_por_chave: dict[str, str] = {}
    cache_por_telefone: dict[str, str] = {}

    # Filtra telefones únicos válidos
    telefones_unicos: list[str] = []
    for tel in telefones_por_chave.values():
        if tel and tel.strip() and tel not in telefones_unicos:
            telefones_unicos.append(tel)

    total_unicos = len(telefones_unicos)

    for idx, tel in enumerate(telefones_unicos, 1):
        if cancel is not None and cancel.is_set():
            break

        if on_progress is not None:
            on_progress(idx, total_unicos, tel)

        texto = coletar_texto_google_telefone(
            tel,
            cancel=cancel,
            tempo_espera_pagina=tempo_espera_pagina,
        )
        cache_por_telefone[tel] = texto

        # Pequena pausa entre buscas se houver mais de uma
        if idx < total_unicos and cancel is not None and not cancel.is_set():
            time.sleep(1.0)

    # Mapeia de volta para cada chave
    for chave, tel in telefones_por_chave.items():
        if not tel:
            resultado_por_chave[chave] = "Não encontrado"
        else:
            resultado_por_chave[chave] = cache_por_telefone.get(tel, "Não encontrado")

    return resultado_por_chave
