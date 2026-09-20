# -*- coding: utf-8 -*-
"""
Transcrição de áudios .wav via Faster-Whisper (CTranslate2).

Carrega o modelo uma única vez (carregamento é caro) e expõe
`transcrever_arquivo(path)` que devolve o texto transcrito.

Vantagens do Faster-Whisper:
1. Até 4x-8x mais rápido na CPU com menor consumo de memória RAM.
2. Suporte nativo a VAD (Voice Activity Detection / Silero) para filtrar silêncios.
3. Transcrição baseada em gerador de segmentos, permitindo controle
   de cancelamento imediato e cálculo de progresso sem monkey patching.
"""

import sys
import threading
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from typing import Callable

from faster_whisper import WhisperModel


class TranscricaoCancelada(Exception):
    """Levantada quando o usuário cancela a transcrição no meio.

    Distinta de qualquer outra exceção para que `salvar_no_banco` possa
    distinguir "cancelado" de "erro de I/O / OOM / etc.".
    """
    pass


@lru_cache(maxsize=1)
def carregar_modelo(
    nome: str = "small",
    device: str | None = None,
    compute_type: str | None = None,
) -> WhisperModel:
    """Carrega o modelo Faster-Whisper uma única vez por processo.

    Otimizado para execução rápida e segura em CPU (Core i3) com int8,
    ou em GPU se explicitamente configurado e suportado.
    """
    import os

    dev = device or os.getenv("WHISPER_DEVICE", "cpu")
    ct = compute_type or os.getenv("WHISPER_COMPUTE_TYPE", "int8" if dev == "cpu" else "float16")

    try:
        return WhisperModel(nome, device=dev, compute_type=ct)
    except Exception:
        # Fallback garantido para CPU com int8 (ou float32)
        try:
            return WhisperModel(nome, device="cpu", compute_type="int8")
        except Exception:
            return WhisperModel(nome, device="cpu", compute_type="float32")


def _emit(msg: str) -> None:
    """Escreve no stderr sem buffering, para feedback em tempo real."""
    print(msg, file=sys.stderr, flush=True)


def transcrever_arquivo(
    caminho: Path,
    *,
    modelo: WhisperModel | None = None,
    cancel: "threading.Event | None" = None,
    on_progress: "Callable[[float], None] | None" = None,
    beam_size: int = 5,
    language: str = "pt",
    vad_filter: bool = True,
    word_timestamps: bool = True,
    retornar_segmentos: bool = False,
) -> tuple[str, list[dict], list[dict]] | tuple[str, list[dict], list[dict], list[dict]]:
    """Transcreve um .wav usando faster-whisper e devolve (texto, metricas, palavras)
    ou (texto, metricas, palavras, segmentos) se retornar_segmentos=True.

    - texto   : string com a transcrição completa.
    - metricas: lista de dicts com avg_logprob, compression_ratio e
                no_speech_prob de cada segmento, prontos para
                `calcular_metricas_whisper()` em qualidade_audio.py.
    - palavras: lista de dicts com {'start', 'end', 'word', 'probability'}
                para alinhamento preciso com diarização.
    - segmentos: lista de dicts com {'start', 'end', 'text'} por frase/trecho.

    Suporte a cancelamento e progresso granular em tempo real:
    1. Checagem prévia antes de iniciar o processamento.
    2. Iteração sobre os segmentos do CTranslate2, verificando o flag
       de cancelamento a cada trecho transcrito.
    3. Cálculo contínuo de percentual (`on_progress`) baseado no tempo do áudio.
    """
    if cancel is not None and cancel.is_set():
        raise TranscricaoCancelada(
            "Cancelamento solicitado antes de iniciar o áudio",
        )

    if modelo is None:
        modelo = carregar_modelo()

    # transcribe() retorna um gerador de segmentos e metadados sobre o áudio
    try:
        segments, info = modelo.transcribe(
            str(caminho),
            language=language,
            beam_size=beam_size,
            vad_filter=vad_filter,
            word_timestamps=word_timestamps,
        )
    except RuntimeError as re:
        if "cublas" in str(re).lower() or "cuda" in str(re).lower():
            # cuBLAS DLL não encontrada no Windows: fallback transparente para CPU
            modelo = carregar_modelo(device="cpu", compute_type="int8")
            segments, info = modelo.transcribe(
                str(caminho),
                language=language,
                beam_size=beam_size,
                vad_filter=vad_filter,
                word_timestamps=word_timestamps,
            )
        else:
            raise

    duracao_total = getattr(info, "duration", 0.0) or 0.0
    partes: list[str] = []
    last_reported_pct = -1

    metricas = []
    palavras = []
    segmentos_lista = []

    for segment in segments:
        if cancel is not None and cancel.is_set():
            raise TranscricaoCancelada(
                "Cancelamento solicitado durante a transcrição",
            )

        texto_segmento = segment.text.strip()
        if texto_segmento:
            partes.append(texto_segmento)
            segmentos_lista.append({
                "start": round(segment.start, 3),
                "end": round(segment.end, 3),
                "text": texto_segmento,
            })

        # Coleta palavras com timestamps se disponíveis
        if getattr(segment, "words", None):
            for w in segment.words:
                w_text = w.word.strip()
                if w_text:
                    palavras.append({
                        "start": round(w.start, 3),
                        "end": round(w.end, 3),
                        "word": w_text,
                        "probability": round(getattr(w, "probability", 1.0), 3)
                    })

        # Coleta as métricas de cada segmento
        metricas.append({
            "logprob_media": segment.avg_logprob,
            "taxa_compressao": segment.compression_ratio,
            "probabilidade_sem_fala": segment.no_speech_prob
        })

        if on_progress is not None and duracao_total > 0:
            frac = min(segment.end / duracao_total, 1.0)
            pct = round(frac * 100)
            if pct != last_reported_pct:
                last_reported_pct = pct
                try:
                    on_progress(frac)
                except Exception:
                    pass

    if on_progress is not None and last_reported_pct < 100:
        try:
            on_progress(1.0)
        except Exception:
            pass

    texto_completo = " ".join(partes).strip()

    if retornar_segmentos:
        return texto_completo, metricas, palavras, segmentos_lista
    return texto_completo, metricas, palavras


def transcrever_pasta(pasta: Path, *, recursivo: bool = False) -> list[tuple[Path, str]]:
    """Transcreve todos os .wav de uma pasta. Retorna [(path, texto), ...]."""
    modelo = carregar_modelo()
    padrao = "**/*" if recursivo else "*"
    wavs = sorted(
        p for p in pasta.glob(padrao)
        if p.is_file() and p.suffix.lower() == ".wav"
    )

    if not wavs:
        _emit(f"Nenhum .wav encontrado em {pasta}.")
        return []

    _emit(f"Transcrevendo {len(wavs)} áudio(s) de {pasta} ...")
    transcricoes = []
    for i, w in enumerate(wavs, start=1):
        _emit(f"  [{i}/{len(wavs)}] {w.name} ... ")
        inicio = perf_counter()
        texto, _, _ = transcrever_arquivo(w, modelo=modelo)
        duracao = perf_counter() - inicio
        _emit(f"  [{i}/{len(wavs)}] {w.name} ok ({duracao:.1f}s)")
        transcricoes.append((w, texto))
    return transcricoes