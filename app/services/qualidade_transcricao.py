# -*- coding: utf-8 -*-
"""
============================================================================
Módulo de Avaliação de Qualidade de Transcrição do SONAX.

Responsabilidades:
    1. Análise heurística de texto (contagem de palavras, caracteres, taxa
       de repetições consecutivas e anomalias de caracteres).
    2. Avaliação de qualidade e confiabilidade da transcrição (penalizações
       por textos truncados, alucinações e métricas do modelo ASR).
============================================================================
"""
from __future__ import annotations

import re


def analisar_transcricao(transcricao: str) -> dict:
    """Extrai métricas e contagens estruturadas da transcrição em texto puro."""
    transcricao = transcricao.strip()
    palavras = transcricao.split()
    quantidade_palavras = len(palavras)
    quantidade_caracteres = len(transcricao)

    # Remove pontuação para análise de repetições
    palavras_limpa = [
        re.sub(r"[^\wÀ-ÿ]", "", palavra.lower())
        for palavra in palavras
    ]
    palavras_limpa = [palavra for palavra in palavras_limpa if palavra]

    quantidade_repeticoes = 0
    for i in range(1, len(palavras_limpa)):
        if palavras_limpa[i] == palavras_limpa[i - 1]:
            quantidade_repeticoes += 1

    if quantidade_palavras > 0:
        taxa_repeticao = (quantidade_repeticoes / quantidade_palavras) * 100
    else:
        taxa_repeticao = 0

    caracteres_invalidos = len(re.findall(r"[^\wÀ-ÿ\s.,!?;:()\-]", transcricao))

    return {
        "quantidade_palavras": quantidade_palavras,
        "quantidade_caracteres": quantidade_caracteres,
        "quantidade_repeticoes": quantidade_repeticoes,
        "taxa_repeticao": round(taxa_repeticao, 2),
        "caracteres_invalidos": caracteres_invalidos,
    }


def avaliar_qualidade_transcricao(dados: dict) -> dict:
    """Avalia a transcrição com base em critérios textuais e métricas de ASR.

    Retorna um dicionário com:
        - pontuacao: int (0 a 100)
        - classificacao: str ('Excelente', 'Bom', 'Médio', 'Ruim', 'Péssimo')
        - penalizacoes: list[str] (detalhes de cada critério penalizado)
        - motivo: str (resumo formatado das penalizações)
    """
    pontuacao = 100
    penalizacoes: list[str] = []

    # Penaliza transcrições muito curtas
    qtd_palavras = dados.get("quantidade_palavras", 0)
    if qtd_palavras < 10:
        pontuacao -= 70
        penalizacoes.append(f"Menos de 10 palavras ({qtd_palavras}) [-70]")
    elif qtd_palavras < 40:
        pontuacao -= 50
        penalizacoes.append(f"Menos de 40 palavras ({qtd_palavras}) [-50]")

    # Penaliza muitas repetições consecutivas (alucinações de repetição)
    taxa_rep = dados.get("taxa_repeticao", 0)
    if taxa_rep > 10:
        pontuacao -= 30
        penalizacoes.append(f"Taxa de repetição muito alta: {taxa_rep}% [-30]")
    elif taxa_rep > 5:
        pontuacao -= 15
        penalizacoes.append(f"Taxa de repetição moderada: {taxa_rep}% [-15]")

    # Penaliza caracteres inválidos
    carac_inv = dados.get("caracteres_invalidos", 0)
    if carac_inv > 5:
        pontuacao -= 20
        penalizacoes.append(f"Muitos caracteres inválidos: {carac_inv} [-20]")
    elif carac_inv > 0:
        pontuacao -= 10
        penalizacoes.append(f"Caracteres inválidos: {carac_inv} [-10]")

    # Métricas do ASR (quando disponíveis)
    logprob = dados.get("logprob_media", 0)
    if logprob < -1.0:
        pontuacao -= 30
        penalizacoes.append(f"Confiança (logprob) muito baixa: {logprob:.2f} [-30]")
    elif logprob < -0.7:
        pontuacao -= 15
        penalizacoes.append(f"Confiança (logprob) baixa: {logprob:.2f} [-15]")

    taxa_comp = dados.get("taxa_compressao_media", 0)
    if taxa_comp > 2.4:
        pontuacao -= 25
        penalizacoes.append(f"Taxa de compressão muito alta: {taxa_comp:.2f} [-25]")
    elif taxa_comp > 2.0:
        pontuacao -= 10
        penalizacoes.append(f"Taxa de compressão alta: {taxa_comp:.2f} [-10]")

    sem_fala = dados.get("probabilidade_media_sem_fala", 0)
    if sem_fala > 0.6:
        pontuacao -= 20
        penalizacoes.append(f"Alta probabilidade de silêncio/sem fala: {sem_fala:.2f} [-20]")
    elif sem_fala > 0.4:
        pontuacao -= 10
        penalizacoes.append(f"Probabilidade de silêncio moderada: {sem_fala:.2f} [-10]")

    pontuacao = max(0, min(100, pontuacao))

    if pontuacao >= 90:
        classificacao = "Excelente"
    elif pontuacao >= 75:
        classificacao = "Bom"
    elif pontuacao >= 60:
        classificacao = "Médio"
    elif pontuacao >= 40:
        classificacao = "Ruim"
    else:
        classificacao = "Péssimo"

    return {
        "pontuacao": pontuacao,
        "classificacao": classificacao,
        "penalizacoes": penalizacoes,
        "motivo": "; ".join(penalizacoes) if penalizacoes else "Nenhuma penalização (qualidade excelente)",
    }
