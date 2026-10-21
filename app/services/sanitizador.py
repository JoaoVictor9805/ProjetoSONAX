# -*- coding: utf-8 -*-
"""
============================================================================
Módulo de Sanitização e Higienização Textual de Saídas de IA.

Responsabilidades:
    1. Detecção e recuperação de textos UTF-8 corrompidos (Mojibake).
    2. Conversão de pontuação oriental/fullwidth (，、。：；) para ocidental.
    3. Remoção determinística de ideogramas CJK (chinês, japonês),
       caracteres cirílicos, árabes e hangul resultantes de vazamento de
       tokens multilíngues (cross-lingual token bleeding/code-switching).
    4. Normalização de pontuação e espaçamento pós-remoção.
    5. Sanitização recursiva de estruturas de dados (dicionários e listas).
============================================================================
"""
from __future__ import annotations

import re
from typing import Any

# Mapeamento de pontuações e símbolos fullwidth/orientais frequentes em modelos chineses
MAPA_PONTUACAO_ORIENTAL = {
    "，": ", ",
    "。": ". ",
    "、": ", ",
    "：": ": ",
    "；": "; ",
    "？": "? ",
    "！": "! ",
    "（": " (",
    "）": ") ",
    "【": " [",
    "】": "] ",
    "《": " <",
    "》": "> ",
    "“": '"',
    "”": '"',
    "‘": "'",
    "’": "'",
}

# Regex cobrindo scripts não latinos suscetíveis a vazamento:
# - CJK Unified Ideographs e extensões (Mandarim/Kanji)
# - Hiragana e Katakana (Japonês)
# - Hangul (Coreano)
# - Cirílico (Russo/Eslavo)
# - Árabe e persa
# - Símbolos e formas de pontuação CJK / Fullwidth adicionais
PADRAO_SCRIPTS_ESTRANGEIROS = re.compile(
    r"["
    r"\u4e00-\u9fff"   # CJK Unified Ideographs
    r"\u3400-\u4dbf"   # CJK Extension A
    r"\uf900-\ufaff"   # CJK Compatibility
    r"\u2e80-\u2eff"   # CJK Radicals
    r"\u3040-\u30ff"   # Hiragana & Katakana
    r"\uac00-\ud7af"   # Hangul Syllables
    r"\u1100-\u11ff\u3130-\u318f"  # Hangul Jamo
    r"\u0400-\u052f"   # Cirílico
    r"\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff"  # Árabe
    r"\u3000-\u303f"   # CJK Symbols & Punctuation
    r"\uff00-\uffef"   # Halfwidth & Fullwidth Forms
    r"]+"
)


def corrigir_mojibake(texto: str) -> str:
    """Detecta e recupera textos UTF-8 corrompidos por interpretação em Latin-1/CP1252 (Mojibake)."""
    if not texto or ("Ã" not in texto and "Â" not in texto):
        return texto
    try:
        return texto.encode("latin1").decode("utf-8")
    except Exception:
        def _desfazer(m: re.Match[str]) -> str:
            try:
                return m.group(0).encode("latin1").decode("utf-8")
            except Exception:
                return m.group(0)
        return re.sub(r"[\xc2-\xf4][\x80-\xbf]+", _desfazer, texto)


def sanitizar_texto_estrangeiro(texto: str | None) -> str:
    """Remove caracteres de scripts estrangeiros (CJK, árabe, cirílico) e normaliza pontuação."""
    if not texto:
        return "" if texto is not None else ""

    res = corrigir_mojibake(str(texto))

    # 1. Substitui pontuação oriental por ocidental equivalente
    for ori, ocid in MAPA_PONTUACAO_ORIENTAL.items():
        if ori in res:
            res = res.replace(ori, ocid)

    # 2. Remove ideogramas e caracteres de scripts estrangeiros
    res = PADRAO_SCRIPTS_ESTRANGEIROS.sub(" ", res)

    # 3. Normaliza espaçamentos e pontuações remanescentes
    res = re.sub(r"[ \t]+", " ", res)
    # Remove espaços que ficaram antes de pontuação (ex: 'palavra ,' -> 'palavra,')
    res = re.sub(r"\s+([,\.:;\?!])", r"\1", res)
    # Deduplica vírgulas ou pontuações mistas coladas, preservando reticências ('...')
    res = re.sub(r",[\s,]+", ", ", res)
    res = re.sub(r"\.{4,}", "...", res)
    res = re.sub(r",\s*\.", ".", res)
    res = re.sub(r"\.\s*,", ",", res)
    # Garante espaço após pontuação se colado diretamente em letra (ex: 'bom,dia' -> 'bom, dia')
    res = re.sub(r"([,;:?!])([a-zA-ZáéíóúÁÉÍÓÚãõÃÕâêîôûÂÊÎÔÛçÇ])", r"\1 \2", res)
    res = re.sub(r"(\.)([a-zA-ZáéíóúÁÉÍÓÚãõÃÕâêîôûÂÊÎÔÛçÇ])", r"\1 \2", res)

    res = res.strip()
    return res


def sanitizar_estrutura_analise(dado: Any) -> Any:
    """Aplica recursivamente a higienização de texto em dicionários e listas."""
    if isinstance(dado, str):
        return sanitizar_texto_estrangeiro(dado)
    elif isinstance(dado, dict):
        return {k: sanitizar_estrutura_analise(v) for k, v in dado.items()}
    elif isinstance(dado, list):
        return [sanitizar_estrutura_analise(item) for item in dado]
    return dado
