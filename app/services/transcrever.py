# -*- coding: utf-8 -*-
"""
Transcrição de áudios .wav via OpenAI Whisper.

Carrega o modelo uma única vez (carregamento é caro) e expõe
`transcrever_arquivo(path)` que devolve o texto + segmentos.

Suporte a **cancelamento imediato**: se `transcrever_arquivo` for
chamado com `cancel=threading.Event`, a função checa o flag entre as
janelas internas do Whisper via hook em `tqdm.tqdm.update`. O Whisper
20250625 não aceita `progress_callback` no `.transcribe()`, então o
`update()` do tqdm é o único ponto de preempção de granularidade fina
— ele é chamado a cada janela de ~30s de áudio. Na GUI, o botão
"Cancelar" vai além: injeta `TranscricaoCancelada` **diretamente na
thread** em execução (via `PyThreadState_SetAsyncExc` em `app.py`), o
que interrompe a inferência imediatamente, sem esperar a próxima
janela. Se o usuário setar `cancel.is_set()` durante a transcrição,
uma `TranscricaoCancelada` sobe imediatamente e o
`transcrever_arquivo` retorna o que já tinha sido acumulado (pode
estar vazio se o cancel chegar no início).
"""

import sys
import threading
from functools import lru_cache
from pathlib import Path
from time import perf_counter

import tqdm as _tqdm_mod
import whisper


class TranscricaoCancelada(Exception):
    """Levantada quando o usuário cancela a transcrição no meio.

    Distinta de qualquer outra exceção para que `salvar_no_banco` possa
    distinguir "cancelado" de "erro de I/O / OOM / etc.".
    """
    pass


@lru_cache(maxsize=1)
def carregar_modelo(nome: str = "small"):
    """Carrega o modelo Whisper uma única vez por processo."""
    return whisper.load_model(nome)


def _emit(msg: str) -> None:
    """Escreve no stderr sem buffering, para feedback em tempo real."""
    print(msg, file=sys.stderr, flush=True)


def transcrever_arquivo(
    caminho: Path,
    *,
    modelo=None,
    cancel: "threading.Event | None" = None,
) -> str:
    """Transcreve um .wav e devolve só o texto (sem timestamps).

    `verbose=False` silencia o cabeçalho e a barra interna do Whisper,
    já que emitimos nosso próprio progresso no `transcrever_pasta`.

    Suporte a cancelamento imediato:
    1. Checagem prévia antes de iniciar o processamento.
    2. Hook `register_forward_pre_hook` no modelo PyTorch que interrompe
       a inferência do Whisper no exato milissegundo em que `cancel.is_set()`
       for ativado (entre tokens individuais).
    3. Hook de fallback no `tqdm.update` entre janelas de 30s.
    """
    if cancel is not None and cancel.is_set():
        raise TranscricaoCancelada(
            f"Cancelamento solicitado antes de iniciar {caminho.name}",
        )

    if modelo is None:
        modelo = carregar_modelo()

    if cancel is None:
        # Caminho "normal" — sem hook, sem custo extra.
        resultado = modelo.transcribe(
            str(caminho),
            language="pt",
            fp16=False,
            verbose=False,
        )
        return str(resultado.get("text", "")).strip()

    hook_handle = None
    if hasattr(modelo, "register_forward_pre_hook"):
        def _cancel_hook(module, inputs):  # noqa: ARG001
            if cancel is not None and cancel.is_set():
                raise TranscricaoCancelada(
                    f"Cancelamento solicitado durante a inferência de {caminho.name}",
                )
        hook_handle = modelo.register_forward_pre_hook(_cancel_hook)

    original_update = _tqdm_mod.tqdm.update

    def _patched_update(self, n=1):  # type: ignore[no-untyped-def]
        if cancel is not None and cancel.is_set():
            raise TranscricaoCancelada(
                f"Cancelamento solicitado durante {caminho.name}",
            )
        return original_update(self, n)

    _tqdm_mod.tqdm.update = _patched_update  # type: ignore[method-assign]
    try:
        resultado = modelo.transcribe(
            str(caminho),
            language="pt",
            fp16=False,
            verbose=False,
        )
    except TranscricaoCancelada:
        # Propaga limpo — nada do que foi parcialmente transcrito vai
        # para o `text` retornado, e o `salvar_no_banco` não chega a
        # inserir no banco.
        raise
    finally:
        _tqdm_mod.tqdm.update = original_update  # type: ignore[method-assign]
        if hook_handle is not None:
            hook_handle.remove()

    return str(resultado.get("text", "")).strip()


"""
def transcrever_pasta(pasta: Path, *, recursivo: bool = False) -> list:
    Transcreve todos os .wav de uma pasta. Retorna [(path, texto), ...].

    Imprime progresso antes/depois de cada arquivo para que o usuário
    saiba que o processo não travou (a transcrição no CPU é lenta).
    
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
"""