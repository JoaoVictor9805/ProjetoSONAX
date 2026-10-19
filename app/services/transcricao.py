# -*- coding: utf-8 -*-
"""
============================================================================
Serviço de Transcrição de Áudio Local via Faster-Whisper (CTranslate2).
============================================================================

Recursos:
    - Transcrição 100% local e offline utilizando o modelo 'small' (CTranslate2)
    - Carregamento lazy singleton do modelo com fallback inteligente de aceleração (CUDA/CPU)
    - Filtro VAD (Silero) para ignorar silêncios e ruídos de fundo
    - Controle de cancelamento imediato via threading.Event durante o streaming de segmentos
    - Coleta de métricas acústicas reais (avg_logprob, compression_ratio, no_speech_prob)
    - Cálculo contínuo de progresso para a UI do SONAX
    - Suporte retrocompatível com OpenRouter ASR caso configurado no ambiente
============================================================================
"""

from __future__ import annotations

import base64
import os
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Optional

import requests
from dotenv import load_dotenv

from app.services.audio_inspector import obter_duracao_wav

load_dotenv()


class TranscricaoErro(Exception):
    """Exceção base para erros do serviço de transcrição."""
    pass


class ChaveOpenRouterNaoConfigurada(TranscricaoErro):
    """Lançada quando a chave OPENROUTER_API_KEY não foi configurada."""
    pass


class ChaveAssemblyAINaoConfigurada(TranscricaoErro):
    """Lançada quando a chave ASSEMBLY_API_KEY não foi configurada (compatibilidade)."""
    pass


class TranscricaoCancelada(TranscricaoErro):
    """Lançada quando a operação de transcrição é cancelada pelo usuário."""
    pass


calcular_duracao_wav = obter_duracao_wav


@lru_cache(maxsize=1)
def obter_modelo_whisper(
    nome: str = "small",
    device: str = "auto",
    compute_type: str = "auto",
) -> Any:
    """Carrega o modelo Faster-Whisper uma única vez por processo (singleton em cache)."""
    from faster_whisper import WhisperModel
    try:
        return WhisperModel(nome, device=device, compute_type=compute_type)
    except Exception:
        # Fallback para execução segura em CPU
        try:
            return WhisperModel(nome, device="cpu", compute_type="int8")
        except Exception:
            return WhisperModel(nome, device="cpu", compute_type="float32")


def transcrever_audio_faster_whisper(
    caminho: Path | str,
    *,
    cancel: Optional[threading.Event] = None,
    on_progress: Optional[Callable[[float, str], None]] = None,
    timeout: Optional[int] = None,
    language: str = "pt",
    beam_size: int = 5,
    vad_filter: bool = True,
    modelo: Any = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Transcreve um arquivo de áudio utilizando Faster-Whisper (modelo small local).

    Parâmetros:
        caminho: Caminho local do arquivo de áudio (.wav).
        cancel: Flag de cancelamento threading.Event para abortar a inferência.
        on_progress: Callback de progresso f(frac, mensagem) para a UI.
        timeout: Não aplicável diretamente na inferência local, mantido por compatibilidade.
        language: Idioma para transcrição (padrão 'pt').
        beam_size: Tamanho do feixe de busca para decodificação (padrão 5).
        vad_filter: Ativação de VAD Silero para remover ruído/silêncio.
        modelo: Instância opcional de WhisperModel para testes ou injeção direta.

    Retorno:
        dict contendo:
            - texto: texto completo contínuo da transcrição
            - texto_formatado: texto formatado
            - texto_simples: texto simples
            - duracao_segundos: duração calculada do áudio
            - confidence: confiança estimada baseada no logprob médio
            - metricas: dict com logprob_media, taxa_compressao_media, probabilidade_media_sem_fala
            - turnos: []
            - speakers: []
    """
    caminho_path = Path(caminho)
    if not caminho_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho_path}")

    if cancel is not None and cancel.is_set():
        raise TranscricaoCancelada("Cancelamento solicitado antes do início da transcrição.")

    duracao_segundos = 0.0
    try:
        duracao_segundos = calcular_duracao_wav(caminho_path)
    except Exception:
        duracao_segundos = 0.0

    if on_progress:
        on_progress(0.05, "Preparando modelo Faster-Whisper (small)...")

    if modelo is None:
        nome_modelo = os.getenv("WHISPER_MODEL", "small")
        modelo = obter_modelo_whisper(nome=nome_modelo)

    if cancel is not None and cancel.is_set():
        raise TranscricaoCancelada("Cancelamento solicitado antes da inferência.")

    if on_progress:
        on_progress(0.15, "Transcrevendo áudio via Faster-Whisper local (small)...")

    try:
        segments, info = modelo.transcribe(
            str(caminho_path),
            language=language,
            beam_size=beam_size,
            vad_filter=vad_filter,
        )
    except Exception as exc:
        raise TranscricaoErro(f"Erro durante inferência do Faster-Whisper: {exc}") from exc

    duracao_info = getattr(info, "duration", 0.0) or duracao_segundos or 0.0
    partes: list[str] = []
    logprobs: list[float] = []
    taxas_compressao: list[float] = []
    sem_falas: list[float] = []
    ultimo_pct_relatado = -1

    for segment in segments:
        if cancel is not None and cancel.is_set():
            raise TranscricaoCancelada("Cancelamento solicitado durante a transcrição.")

        texto_seg = (segment.text or "").strip()
        if texto_seg:
            partes.append(texto_seg)

        if hasattr(segment, "avg_logprob") and segment.avg_logprob is not None:
            logprobs.append(float(segment.avg_logprob))
        if hasattr(segment, "compression_ratio") and segment.compression_ratio is not None:
            taxas_compressao.append(float(segment.compression_ratio))
        if hasattr(segment, "no_speech_prob") and segment.no_speech_prob is not None:
            sem_falas.append(float(segment.no_speech_prob))

        if on_progress and duracao_info > 0:
            frac = min(segment.end / duracao_info, 0.95)
            pct = round(frac * 100)
            if pct != ultimo_pct_relatado:
                ultimo_pct_relatado = pct
                on_progress(frac, "Transcrevendo áudio via Faster-Whisper local (small)...")

    if cancel is not None and cancel.is_set():
        raise TranscricaoCancelada("Cancelamento solicitado após transcrição.")

    texto_transcrito = " ".join(partes).strip()

    # Cálculo das métricas acústicas consolidadas
    logprob_media = sum(logprobs) / len(logprobs) if logprobs else -0.10
    taxa_compressao_media = sum(taxas_compressao) / len(taxas_compressao) if taxas_compressao else 1.0
    probabilidade_media_sem_fala = sum(sem_falas) / len(sem_falas) if sem_falas else 0.0

    # Confiança normalizada no intervalo [0.1, 1.0]
    confidence = round(max(0.1, min(1.0, 1.0 + (logprob_media / 2.0))), 2)

    if on_progress:
        on_progress(1.0, "Transcrição Faster-Whisper concluída com sucesso.")

    return {
        "texto": texto_transcrito,
        "texto_formatado": texto_transcrito,
        "texto_simples": texto_transcrito,
        "duracao_segundos": duracao_info or duracao_segundos,
        "confidence": confidence,
        "metricas": {
            "confidence": confidence,
            "logprob_media": round(logprob_media, 4),
            "taxa_compressao_media": round(taxa_compressao_media, 4),
            "probabilidade_media_sem_fala": round(probabilidade_media_sem_fala, 4),
        },
        "turnos": [],
        "speakers": [],
    }


def obter_api_key_openrouter() -> str:
    """Retorna a chave do OpenRouter definida no ambiente."""
    chave = os.getenv("OPENROUTER_API_KEY")
    if not chave or not chave.strip():
        raise ChaveOpenRouterNaoConfigurada(
            "Chave 'OPENROUTER_API_KEY' não configurada no arquivo .env."
        )
    return chave.strip()


def transcrever_audio_openrouter(
    caminho: Path | str,
    *,
    cancel: Optional[threading.Event] = None,
    on_progress: Optional[Callable[[float, str], None]] = None,
    timeout: int = 90,
    **kwargs: Any,
) -> dict[str, Any]:
    """Transcreve um arquivo de áudio utilizando a API do OpenRouter."""
    caminho_path = Path(caminho)
    if not caminho_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho_path}")

    if cancel is not None and cancel.is_set():
        raise TranscricaoCancelada("Cancelamento solicitado antes do envio.")

    api_key = obter_api_key_openrouter()
    modelo_padrao = os.getenv(
        "TRANSCRICAO_MODEL",
        "nvidia/nemotron-3.5-asr-streaming-multilingual-0.6b",
    )
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    headers = {"Authorization": f"Bearer {api_key}"}
    duracao_segundos = calcular_duracao_wav(caminho_path)

    if on_progress:
        on_progress(0.15, "Preparando áudio para OpenRouter...")

    texto_transcrito = ""

    if cancel is not None and cancel.is_set():
        raise TranscricaoCancelada("Cancelamento solicitado.")

    try:
        if on_progress:
            on_progress(0.35, "Enviando áudio para OpenRouter...")

        with open(caminho_path, "rb") as f:
            files = {"file": (caminho_path.name, f, "audio/wav")}
            data = {"model": modelo_padrao}

            resp = requests.post(
                f"{base_url}/audio/transcriptions",
                files=files,
                data=data,
                headers=headers,
                timeout=timeout,
            )

        if resp.status_code == 200:
            resultado_json = resp.json()
            texto_transcrito = resultado_json.get("text", "") or ""
        elif resp.status_code == 402:
            raise TranscricaoErro(
                "Saldo insuficiente no OpenRouter para processar áudio."
            )
        else:
            erro_msg = resp.text
            if on_progress:
                on_progress(0.50, "Tentando rota alternativa de áudio via OpenRouter...")

            with open(caminho_path, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode("utf-8")

            payload = {
                "model": modelo_padrao,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "audio_url",
                                "audio_url": {"url": f"data:audio/wav;base64,{audio_b64}"},
                            }
                        ],
                    }
                ],
            }

            resp_chat = requests.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=timeout,
            )

            if resp_chat.status_code == 200:
                texto_transcrito = resp_chat.json()["choices"][0]["message"]["content"]
            else:
                raise TranscricaoErro(
                    f"Falha na transcrição OpenRouter (HTTP {resp.status_code}): {erro_msg}"
                )

    except requests.exceptions.RequestException as exc:
        if cancel is not None and cancel.is_set():
            raise TranscricaoCancelada("Cancelamento solicitado durante a transmissão.")
        raise TranscricaoErro(f"Erro de rede ao conectar com OpenRouter: {exc}") from exc

    if cancel is not None and cancel.is_set():
        raise TranscricaoCancelada("Cancelamento solicitado após recebimento da transcrição.")

    texto_transcrito = (texto_transcrito or "").strip()

    if on_progress:
        on_progress(1.0, "Transcrição OpenRouter concluída com sucesso.")

    return {
        "texto": texto_transcrito,
        "texto_formatado": texto_transcrito,
        "texto_simples": texto_transcrito,
        "duracao_segundos": duracao_segundos,
        "confidence": 0.95,
        "metricas": {
            "confidence": 0.95,
            "logprob_media": -0.05,
            "taxa_compressao_media": 1.0,
            "probabilidade_media_sem_fala": 0.0,
        },
        "turnos": [],
        "speakers": [],
    }


# Provedor padrão: Faster-Whisper local (small)
def transcrever_audio(
    caminho: Path | str,
    *,
    cancel: Optional[threading.Event] = None,
    on_progress: Optional[Callable[[float, str], None]] = None,
    timeout: Optional[int] = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Encaminha para o provedor de transcrição configurado (padrão: faster_whisper local)."""
    provedor = os.getenv("TRANSCRICAO_PROVIDER", "faster_whisper").lower().strip()
    if provedor == "openrouter":
        return transcrever_audio_openrouter(
            caminho,
            cancel=cancel,
            on_progress=on_progress,
            timeout=timeout or 90,
            **kwargs,
        )
    return transcrever_audio_faster_whisper(
        caminho,
        cancel=cancel,
        on_progress=on_progress,
        timeout=timeout,
        **kwargs,
    )


# Aliases para compatibilidade total entre módulos e branches
transcrever_audio_faster = transcrever_audio_faster_whisper
transcrever_audio_openrouter_alias = transcrever_audio_openrouter
transcrever_audio_assembly = transcrever_audio
transcrever_audio_assemblyai = transcrever_audio
