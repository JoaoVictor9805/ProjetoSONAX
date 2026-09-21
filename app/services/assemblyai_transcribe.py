# -*- coding: utf-8 -*-
"""
============================================================================
Serviço de transcrição e diarização de áudios via AssemblyAI (Universal-3.5 Pro).
============================================================================

Utiliza o modelo:
    universal-3-5-pro

Recursos:
    - Transcrição precisa com suporte a código-linguagem e português (pt)
    - Diarização de locutores nativa (speaker_labels=True)
    - Limitação/estimativa de participantes (speakers_expected=3)
    - Formatação estruturada das falas (Participante 1, Participante 2, ...)
    - Preservação de timestamps e ordem cronológica
    - Controle de cancelamento imediato via threading.Event
    - Cálculo de progresso contínuo para UI
"""

import math
import os
import sys
import time
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from dotenv import load_dotenv
import assemblyai as aai

load_dotenv()


# ============================================================================
# CONFIGURAÇÕES E CONSTANTES
# ============================================================================

MODELO_PADRAO = os.getenv("ASSEMBLY_MODEL", "universal-3-5-pro")


# ============================================================================
# EXCEÇÕES
# ============================================================================

class AssemblyAIErro(Exception):
    """Exceção base para erros da rota AssemblyAI."""
    pass


class ChaveAssemblyAINaoConfigurada(AssemblyAIErro):
    """Lançada quando ASSEMBLY_API_KEY ou ASSEMBLYAI_API_KEY não foi configurada."""
    pass


class TranscricaoCancelada(AssemblyAIErro):
    """Lançada quando a transcrição é cancelada pelo usuário."""
    pass


# ============================================================================
# INICIALIZAÇÃO DO CLIENTE
# ============================================================================

def obter_api_key() -> str:
    """Retorna a chave da AssemblyAI definida no ambiente."""
    chave = os.getenv("ASSEMBLY_API_KEY") or os.getenv("ASSEMBLYAI_API_KEY")
    if not chave or not chave.strip():
        raise ChaveAssemblyAINaoConfigurada(
            "Chave 'ASSEMBLY_API_KEY' não encontrada no arquivo .env "
            "ou nas variáveis de ambiente."
        )
    return chave.strip()


def configurar_cliente(api_key: Optional[str] = None) -> None:
    """Configura as credenciais globais da SDK AssemblyAI."""
    chave = api_key or obter_api_key()
    aai.settings.api_key = chave


# ============================================================================
# FORMATAÇÃO TEMPORAL
# ============================================================================

def formatar_tempo(ms: int | float) -> str:
    """Converte milissegundos para formato MM:SS ou HH:MM:SS."""
    if ms is None or ms < 0:
        return "00:00"
    total_seg = int(ms / 1000)
    minutos = total_seg // 60
    segundos = total_seg % 60
    horas = minutos // 60
    minutos = minutos % 60
    if horas > 0:
        return f"{horas:02d}:{minutos:02d}:{segundos:02d}"
    return f"{minutos:02d}:{segundos:02d}"


# ============================================================================
# PROCESSAMENTO DE TURNOS E FALANTES
# ============================================================================

def normalizar_turnos(
    utterances: list[Any],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Mapeia os falantes da AssemblyAI (A, B, C, ...) para Participante 1, 2, 3...
    
    Preserva a ordem cronológica estrita de quem falou primeiro.
    """
    mapa_speakers: dict[str, str] = {}
    turnos: list[dict[str, Any]] = []

    for utt in utterances:
        rotulo_bruto = str(getattr(utt, "speaker", "") or "").strip()
        if not rotulo_bruto:
            rotulo_bruto = "A"

        if rotulo_bruto not in mapa_speakers:
            num = len(mapa_speakers) + 1
            mapa_speakers[rotulo_bruto] = f"Participante {num}"

        speaker_nome = mapa_speakers[rotulo_bruto]
        start_ms = getattr(utt, "start", 0) or 0
        end_ms = getattr(utt, "end", start_ms) or start_ms
        texto = str(getattr(utt, "text", "") or "").strip()

        words_data = []
        for w in getattr(utt, "words", []) or []:
            words_data.append({
                "word": getattr(w, "text", ""),
                "start": getattr(w, "start", 0),
                "end": getattr(w, "end", 0),
                "confidence": getattr(w, "confidence", 1.0),
            })

        turnos.append({
            "speaker": speaker_nome,
            "speaker_raw": rotulo_bruto,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "start_s": round(start_ms / 1000.0, 2),
            "end_s": round(end_ms / 1000.0, 2),
            "texto": texto,
            "words": words_data,
            "confidence": getattr(utt, "confidence", None),
        })

    # Ordena cronologicamente
    turnos.sort(key=lambda t: t["start_ms"])
    return turnos, mapa_speakers


def formatar_dialogo_estruturado(
    turnos: list[dict[str, Any]],
    incluir_timestamps: bool = True,
) -> str:
    """Converte os turnos de fala no formato estruturado especificado.
    
    Exemplo:
        Participante 1 (00:00 - 00:05):
        Bom dia, vamos iniciar a reunião.

        Participante 2 (00:06 - 00:15):
        Perfeito. Gostaria de começar falando sobre as pendências do projeto.
    """
    blocos: list[str] = []

    for t in turnos:
        speaker = t["speaker"]
        texto = t["texto"]
        if not texto:
            continue

        if incluir_timestamps:
            tempo_inicio = formatar_tempo(t["start_ms"])
            tempo_fim = formatar_tempo(t["end_ms"])
            cabecalho = f"{speaker} ({tempo_inicio} - {tempo_fim}):"
        else:
            cabecalho = f"{speaker}:"

        blocos.append(f"{cabecalho}\n{texto}")

    return "\n\n".join(blocos)


# ============================================================================
# SERVIÇO PRINCIPAL DE TRANSCRIÇÃO
# ============================================================================

def transcrever_audio_assemblyai(
    caminho: Path | str,
    *,
    cancel: Optional[threading.Event] = None,
    on_progress: Optional[Callable[[float, str], None]] = None,
    speakers_expected: int = 3,
    incluir_timestamps: bool = True,
    deletar_apos_transcricao: bool = True,
) -> dict[str, Any]:
    """Transcreve e diariza um arquivo de áudio via AssemblyAI Universal-3.5 Pro.
    
    Parâmetros:
        caminho: Path do arquivo .wav / áudio local.
        cancel: Evento de cancelamento threading.Event para abortar imediatamente.
        on_progress: Callback de progresso f(frac, mensagem).
        speakers_expected: Estimativa de locutores (padrão 3).
        incluir_timestamps: Se True, insere timestamps no cabeçalho das falas.
        deletar_apos_transcricao: Se True, solicita remoção do áudio na nuvem após o processamento.
        
    Retorno:
        dict contendo:
            - texto_formatado: diálogo estruturado por participante
            - texto_simples: diálogo sem timestamps
            - texto: texto corrido completo
            - turnos: lista de turnos com timestamps e metadados
            - speakers: lista de falantes identificados
            - metricas: dict com logprob_media, taxa_compressao_media, etc.
    """
    caminho_path = Path(caminho)
    if not caminho_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho_path}")

    if cancel is not None and cancel.is_set():
        raise TranscricaoCancelada("Cancelamento solicitado antes do upload.")

    configurar_cliente()

    config = aai.TranscriptionConfig(
        speaker_labels=True,
        speakers_expected=speakers_expected,
        speech_models=[MODELO_PADRAO],
        language_code="pt",
    )

    transcriber = aai.Transcriber()

    if on_progress:
        on_progress(0.05, "Enviando áudio para AssemblyAI...")

    # 1) Submissão assíncrona para permitir monitorar cancelamento
    try:
        transcript_init = transcriber.submit(str(caminho_path), config=config)
    except Exception as e:
        if cancel is not None and cancel.is_set():
            raise TranscricaoCancelada("Processamento cancelado durante envio.")
        raise AssemblyAIErro(f"Falha ao enviar áudio para AssemblyAI: {e}") from e

    transcript_id = transcript_init.id

    if on_progress:
        on_progress(0.25, "Áudio enviado. Transcrevendo na AssemblyAI...")

    # 2) Polling com suporte a cancelamento imediato
    inicio_polling = time.time()

    while True:
        if cancel is not None and cancel.is_set():
            if deletar_apos_transcricao:
                try:
                    aai.Transcript.delete_by_id(transcript_id)
                except Exception:
                    pass
            raise TranscricaoCancelada("Cancelamento solicitado pelo usuário.")

        try:
            status_obj = aai.Transcript.get_by_id(transcript_id)
        except Exception as e:
            if cancel is not None and cancel.is_set():
                raise TranscricaoCancelada("Cancelamento solicitado.")
            raise AssemblyAIErro(f"Erro ao consultar status da transcrição: {e}") from e

        if status_obj.status == aai.TranscriptStatus.completed:
            transcript = status_obj
            break
        elif status_obj.status == aai.TranscriptStatus.error:
            msg_erro = status_obj.error or "Erro desconhecido retornado pela AssemblyAI"
            raise AssemblyAIErro(f"Erro na transcrição da AssemblyAI: {msg_erro}")

        # Avanço gradual simulado de progresso (de 25% a 90%)
        tempo_decorrido = time.time() - inicio_polling
        frac_progresso = min(0.90, 0.25 + (tempo_decorrido * 0.02))
        
        status_nome = "Fila" if status_obj.status == aai.TranscriptStatus.queued else "Processando"
        if on_progress:
            on_progress(frac_progresso, f"AssemblyAI ({status_nome}): transcrevendo...")

        # Aguarda 2 segundos checando cancelamento
        if cancel is not None and cancel.wait(2.0):
            if deletar_apos_transcricao:
                try:
                    aai.Transcript.delete_by_id(transcript_id)
                except Exception:
                    pass
            raise TranscricaoCancelada("Cancelamento solicitado durante processamento.")
        elif cancel is None:
            time.sleep(2.0)

    if on_progress:
        on_progress(0.95, "Processando falantes e estruturando falas...")

    # 3) Extração e normalização dos dados retornados
    utterances = transcript.utterances or []
    texto_puro = transcript.text or ""

    if not utterances and texto_puro:
        # Fallback caso não haja separação de falantes
        turnos = [{
            "speaker": "Participante 1",
            "speaker_raw": "A",
            "start_ms": 0,
            "end_ms": int((transcript.audio_duration or 0) * 1000),
            "start_s": 0.0,
            "end_s": float(transcript.audio_duration or 0.0),
            "texto": texto_puro,
            "words": [],
            "confidence": transcript.confidence,
        }]
        mapa_speakers = {"A": "Participante 1"}
    else:
        turnos, mapa_speakers = normalizar_turnos(utterances)

    texto_formatado = formatar_dialogo_estruturado(turnos, incluir_timestamps=incluir_timestamps)
    texto_simples = formatar_dialogo_estruturado(turnos, incluir_timestamps=False)

    confidence = transcript.confidence if transcript.confidence is not None else 0.95
    # Mapeia confidence (0 a 1) para logprob_media equivalente do Whisper (ex: log(0.95) = -0.05)
    logprob_media = math.log(max(confidence, 0.001))

    metricas = {
        "logprob_media": logprob_media,
        "taxa_compressao_media": 1.0,
        "probabilidade_media_sem_fala": 0.0,
        "confidence": confidence,
    }

    # 4) Limpeza do áudio na nuvem (se solicitado)
    if deletar_apos_transcricao:
        try:
            aai.Transcript.delete_by_id(transcript_id)
        except Exception:
            pass

    if on_progress:
        on_progress(1.0, "Transcrição AssemblyAI concluída com sucesso.")

    return {
        "texto_formatado": texto_formatado,
        "texto_simples": texto_simples,
        "texto": texto_puro,
        "turnos": turnos,
        "speakers": list(mapa_speakers.values()),
        "duracao_segundos": transcript.audio_duration,
        "confidence": confidence,
        "metricas": metricas,
    }


# ============================================================================
# CLI PARA TESTES
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("SONAX — Teste AssemblyAI (Universal-3.5 Pro + Diarização)")
    print("=" * 70)

    if len(sys.argv) < 2:
        print("Uso:")
        print("    python -m app.services.assemblyai_transcribe <caminho_do_audio.wav>")
        try:
            chave = obter_api_key()
            print(f"[OK] Chave AssemblyAI configurada: {chave[:6]}...{chave[-4:]}")
        except Exception as exc:
            print(f"[ERRO] {exc}")
        sys.exit(0)

    audio_teste = Path(sys.argv[1])
    if not audio_teste.exists():
        print(f"[ERRO] Arquivo não encontrado: {audio_teste}")
        sys.exit(1)

    print(f"Arquivo selecionado: {audio_teste.name}")
    print("Iniciando transcrição com Universal-3.5 Pro...")

    try:
        resultado = transcrever_audio_assemblyai(
            audio_teste,
            on_progress=lambda frac, msg: print(f"  [{int(frac*100)}%] {msg}"),
            speakers_expected=3,
        )

        print("\n" + "=" * 70)
        print("RESULTADO ESTRUTURADO:")
        print("=" * 70)
        print(resultado["texto_formatado"])

        print("\n" + "=" * 70)
        print("METADADOS:")
        print("=" * 70)
        print(f"Participantes identificados: {resultado['speakers']}")
        print(f"Quantidade de turnos: {len(resultado['turnos'])}")
        print(f"Duração: {resultado['duracao_segundos']}s")
        print(f"Confiança: {resultado['confidence']}")
        print(f"Métricas estimadas: {resultado['metricas']}")

    except Exception as exc:
        print(f"\n[FALHA NO TESTE] {exc}")
        sys.exit(1)
