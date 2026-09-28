# -*- coding: utf-8 -*-
"""
============================================================================
Módulo de Análise e Qualidade Acústica de Áudio do SONAX.

Responsabilidades:
    1. Extração de métricas de processamento de sinal digital (DSP):
       taxa de amostragem, canais, duração, volume RMS, silêncio e clipping.
    2. Classificação heurística da qualidade do sinal acústico (de 0 a 100).
============================================================================
"""
from __future__ import annotations

import librosa
import numpy
import soundfile


def analisar_audio(caminho):
    """Extrai informações técnicas e métricas acústicas do arquivo de áudio."""
    info = soundfile.info(caminho)

    taxa_amostragem = info.samplerate  # Quantidade de amostras por segundo (Hz)
    canais = info.channels              # Mono | Stereo
    duracao = info.duration             # Segundos

    # Carrega o áudio como mono
    audio, _ = librosa.load(
        caminho,
        sr=None,       # Mantém a taxa de amostragem original do arquivo
        mono=True,     # Converte para mono (apenas um canal)
        duration=duracao,
    )

    # Volume em RMS ao longo do tempo e média
    rms = librosa.feature.rms(y=audio)[0]
    rms_media = float(numpy.mean(rms))

    # Converte RMS para decibéis
    decibeis = librosa.amplitude_to_db(rms, ref=1.0)

    # Percentual de silêncio (abaixo de -40 dB)
    silencio_limite = -40
    silencio_porcentagem = float(numpy.mean(decibeis < silencio_limite) * 100)

    # Detecta clipping (amplitudes próximas do limite de saturação >= 0.99)
    clipping_area = numpy.sum(numpy.abs(audio) >= 0.99)
    clipping_porcentagem = (clipping_area / len(audio)) * 100

    return {
        "duracao": round(duracao, 2),
        "taxa_amostragem": taxa_amostragem,
        "canais": canais,
        "rms": round(rms_media, 4),
        "silencio_porcentagem": round(silencio_porcentagem, 2),
        "clipping_porcentagem": round(clipping_porcentagem, 4),
    }


def classificar_qualidade_audio(dados: dict) -> str:
    """Classifica a qualidade acústica em 5 níveis com base em silêncio, volume e clipping."""
    pontuacao = 100

    # Penaliza excesso de silêncio
    if dados["silencio_porcentagem"] > 90:
        pontuacao -= 70
    elif dados["silencio_porcentagem"] > 85:
        pontuacao -= 45
    elif dados["silencio_porcentagem"] > 70:
        pontuacao -= 30
    elif dados["silencio_porcentagem"] > 50:
        pontuacao -= 20
    elif dados["silencio_porcentagem"] > 30:
        pontuacao -= 10

    # Penaliza volume muito baixo
    if dados["rms"] < 0.01:
        pontuacao -= 25
    elif dados["rms"] < 0.03:
        pontuacao -= 10

    # Penaliza clipping
    if dados["clipping_porcentagem"] > 1:
        pontuacao -= 30
    elif dados["clipping_porcentagem"] > 0.1:
        pontuacao -= 15

    pontuacao = max(0, min(100, pontuacao))

    if pontuacao >= 90:
        return "Excelente"
    if pontuacao >= 75:
        return "Bom"
    if pontuacao >= 60:
        return "Médio"
    if pontuacao >= 40:
        return "Ruim"
    return "Péssimo"
