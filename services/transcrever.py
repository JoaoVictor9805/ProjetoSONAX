# -*- coding: utf-8 -*-
"""
Transcrição de áudios .wav via OpenAI Whisper.

Carrega o modelo uma única vez (carregamento é caro) e expõe
`transcrever_arquivo(path)` que devolve o texto + segmentos.
"""

import sys
from pathlib import Path
from functools import lru_cache
from time import perf_counter

import whisper


@lru_cache(maxsize=1)
def carregar_modelo(nome: str = "small"):
    """Carrega o modelo Whisper uma única vez por processo."""
    return whisper.load_model(nome)


def _emit(msg: str) -> None:
    """Escreve no stderr sem buffering, para feedback em tempo real."""
    print(msg, file=sys.stderr, flush=True)


def transcrever_arquivo(caminho: Path, *, modelo=None) -> str:
    """Transcreve um .wav e devolve só o texto (sem timestamps).

    `verbose=False` silencia o cabeçalho e a barra interna do Whisper,
    já que emitimos nosso próprio progresso no `transcrever_pasta`.
    """
    if modelo is None:
        modelo = carregar_modelo()
    resultado = modelo.transcribe(
        str(caminho),
        language="pt",
        fp16=False,
        verbose=False,
    )
    return str(resultado.get("text", "")).strip()


def transcrever_pasta(pasta: Path, *, recursivo: bool = False) -> list:
    """Transcreve todos os .wav de uma pasta. Retorna [(path, texto), ...].

    Imprime progresso antes/depois de cada arquivo para que o usuário
    saiba que o processo não travou (a transcrição no CPU é lenta).
    """
    modelo = carregar_modelo()
    padrao = "**/*" if recursivo else "*"
    wavs = sorted(p for p in pasta.glob(padrao)
                  if p.is_file() and p.suffix.lower() == ".wav")

    if not wavs:
        _emit(f"Nenhum .wav encontrado em {pasta}.")
        return []

    _emit(f"Transcrevendo {len(wavs)} áudio(s) de {pasta} ...")
    transcricoes = []
    for i, w in enumerate(wavs, start=1):
        _emit(f"  [{i}/{len(wavs)}] {w.name} ... ")
        inicio = perf_counter()
        texto = transcrever_arquivo(w, modelo=modelo)
        duracao = perf_counter() - inicio
        _emit(f"  [{i}/{len(wavs)}] {w.name} ok ({duracao:.1f}s)")
        transcricoes.append((w, texto))
    return transcricoes
