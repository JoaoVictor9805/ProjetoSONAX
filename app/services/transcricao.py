# -*- coding: utf-8 -*-
"""
============================================================================
Serviço de Transcrição de Áudio via AssemblyAI.
============================================================================

Recursos:
    - Reconhecimento de fala (ASR) via AssemblyAI
    - Foco exclusivo em transcrição pura de áudio (SOMENTE transcrição, sem diarização)
    - Suporte a idioma padrão pt (Português)
    - Controle de cancelamento imediato via threading.Event
    - Cálculo de progresso contínuo para a UI do SONAX
    - Limpeza automática de áudios/transcrições temporárias na nuvem
============================================================================
"""

from __future__ import annotations

import math
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

import assemblyai as aai
from dotenv import load_dotenv

from app.services.audio_inspector import obter_duracao_wav

load_dotenv()


MODELO_PADRAO = os.getenv("ASSEMBLY_MODEL", "")
IDIOMA_PADRAO = os.getenv("ASSEMBLY_LANGUAGE_CODE", "pt")


class TranscricaoErro(Exception):
    """Exceção base para erros do serviço de transcrição."""
    pass


class ChaveAssemblyAINaoConfigurada(TranscricaoErro):
    """Lançada quando a chave ASSEMBLY_API_KEY não foi configurada."""
    pass


class ChaveOpenRouterNaoConfigurada(TranscricaoErro):
    """Alias mantido para compatibilidade retroativa."""
    pass


class TranscricaoCancelada(TranscricaoErro):
    """Lançada quando a operação de transcrição é cancelada pelo usuário."""
    pass


def obter_api_key() -> str:
    """Retorna a chave da AssemblyAI definida no ambiente."""
    chave = (
        os.getenv("ASSEMBLY_API_KEY")
        or os.getenv("ASSEMBLYAI_API_KEY")
    )
    if not chave or not chave.strip():
        raise ChaveAssemblyAINaoConfigurada(
            "Chave 'ASSEMBLY_API_KEY' não configurada no arquivo .env."
        )
    return chave.strip()


def configurar_cliente(api_key: Optional[str] = None) -> None:
    """Configura credenciais globais da SDK AssemblyAI."""
    chave = api_key or obter_api_key()
    aai.settings.api_key = chave


calcular_duracao_wav = obter_duracao_wav


def transcrever_audio_assemblyai(
    caminho: Path | str,
    *,
    cancel: Optional[threading.Event] = None,
    on_progress: Optional[Callable[[float, str], None]] = None,
    timeout: int = 120,
    deletar_apos_transcricao: bool = True,
    **kwargs: Any,
) -> dict[str, Any]:
    """Transcreve um arquivo de áudio utilizando a AssemblyAI (SOMENTE transcrição pura).

    Parâmetros:
        caminho: Caminho local do arquivo de áudio (.wav).
        cancel: Flag de cancelamento threading.Event para abortar a requisição.
        on_progress: Callback de progresso f(frac, mensagem) para a UI.
        timeout: Tempo limite máximo de espera em segundos.
        deletar_apos_transcricao: Se True, remove o áudio/transcrição na nuvem ao concluir.

    Retorno:
        dict contendo:
            - texto: texto completo contínuo da transcrição
            - texto_formatado: texto completo
            - texto_simples: texto completo
            - duracao_segundos: duração calculada do áudio
            - confidence: nível de confiança do ASR (0.0 a 1.0)
            - metricas: dict com logprob e métricas de qualidade
            - turnos: [] (diarização realizada na etapa posterior de revisão)
            - speakers: []
    """
    caminho_path = Path(caminho)
    if not caminho_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho_path}")

    if cancel is not None and cancel.is_set():
        raise TranscricaoCancelada("Cancelamento solicitado antes do envio.")

    configurar_cliente()

    duracao_segundos = calcular_duracao_wav(caminho_path)

    if on_progress:
        on_progress(0.10, "Enviando áudio para AssemblyAI...")

    # Configuração estrita de SOMENTE transcrição (sem speaker_labels / diarização)
    config_args: dict[str, Any] = {
        "language_code": IDIOMA_PADRAO,
        "speaker_labels": False,
        "punctuate": True,
        "format_text": True,
    }

    if MODELO_PADRAO:
        config_args["speech_model"] = MODELO_PADRAO

    config = aai.TranscriptionConfig(**config_args)
    transcriber = aai.Transcriber()

    try:
        transcript_init = transcriber.submit(str(caminho_path), config=config)
    except Exception as exc:
        if cancel is not None and cancel.is_set():
            raise TranscricaoCancelada("Cancelamento solicitado durante envio.") from exc
        raise TranscricaoErro(f"Falha ao enviar áudio para AssemblyAI: {exc}") from exc

    transcript_id = transcript_init.id

    if on_progress:
        on_progress(0.25, "Áudio enviado. Transcrevendo na AssemblyAI...")

    inicio_polling = time.time()
    transcript = None

    while True:
        if cancel is not None and cancel.is_set():
            if deletar_apos_transcricao:
                try:
                    aai.Transcript.delete_by_id(transcript_id)
                except Exception:
                    pass
            raise TranscricaoCancelada("Cancelamento solicitado pelo usuário.")

        if (time.time() - inicio_polling) > timeout:
            if deletar_apos_transcricao:
                try:
                    aai.Transcript.delete_by_id(transcript_id)
                except Exception:
                    pass
            raise TranscricaoErro(f"Tempo limite ({timeout}s) excedido na transcrição AssemblyAI.")

        try:
            status_obj = aai.Transcript.get_by_id(transcript_id)
        except Exception as exc:
            if cancel is not None and cancel.is_set():
                raise TranscricaoCancelada("Cancelamento solicitado.") from exc
            raise TranscricaoErro(f"Erro ao consultar status da transcrição AssemblyAI: {exc}") from exc

        if status_obj.status == aai.TranscriptStatus.completed:
            transcript = status_obj
            break
        elif status_obj.status == aai.TranscriptStatus.error:
            msg_erro = status_obj.error or "Erro desconhecido retornado pela AssemblyAI"
            raise TranscricaoErro(f"Erro na transcrição da AssemblyAI: {msg_erro}")

        # Atualização proporcional de progresso estimado
        tempo_decorrido = time.time() - inicio_polling
        frac_progresso = min(0.92, 0.25 + (tempo_decorrido * 0.03))
        status_nome = "Fila" if status_obj.status == aai.TranscriptStatus.queued else "Processando"
        if on_progress:
            on_progress(frac_progresso, f"AssemblyAI ({status_nome}): transcrevendo áudio...")

        if cancel is not None and cancel.wait(1.5):
            if deletar_apos_transcricao:
                try:
                    aai.Transcript.delete_by_id(transcript_id)
                except Exception:
                    pass
            raise TranscricaoCancelada("Cancelamento solicitado durante o processamento.")
        elif cancel is None:
            time.sleep(1.5)

    texto_transcrito = (transcript.text or "").strip()
    duracao_retornada = transcript.audio_duration or duracao_segundos
    confidence = transcript.confidence if transcript.confidence is not None else 0.95
    logprob_media = math.log(max(confidence, 0.001))

    if deletar_apos_transcricao:
        try:
            aai.Transcript.delete_by_id(transcript_id)
        except Exception:
            pass

    if on_progress:
        on_progress(1.0, "Transcrição AssemblyAI concluída com sucesso.")

    return {
        "texto": texto_transcrito,
        "texto_formatado": texto_transcrito,
        "texto_simples": texto_transcrito,
        "duracao_segundos": duracao_retornada,
        "confidence": confidence,
        "metricas": {
            "confidence": confidence,
            "logprob_media": round(logprob_media, 4),
            "taxa_compressao_media": 1.0,
            "probabilidade_media_sem_fala": 0.0,
        },
        "turnos": [],
        "speakers": [],
    }


# Aliases para compatibilidade total
transcrever_audio = transcrever_audio_assemblyai
transcrever_audio_assembly = transcrever_audio_assemblyai
transcrever_audio_openrouter = transcrever_audio_assemblyai
