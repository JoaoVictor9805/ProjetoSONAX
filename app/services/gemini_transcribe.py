# -*- coding: utf-8 -*-

"""
Serviço independente de transcrição e diarização de áudio via Google Gemini.

Utiliza o modelo:
    gemini-3.5-transcribe

Recursos utilizados:
    - Transcrição verbatim
    - Diarização de locutores
    - Timestamps por palavra
    - Português do Brasil

Importante:
    O gemini-3.5-transcribe não deve ser tratado como um modelo genérico
    de Structured Output com response_schema/response_mime_type.

    A diarização é obtida através das anotações word_info retornadas pela
    API Interactions.

Exemplo:
    from app.services.gemini_transcribe import diarizar_audio_gemini

    resultado = diarizar_audio_gemini("caminho/arquivo.wav")

    print(resultado["texto_formatado"])
    print(resultado["speakers"])
"""

import os
import re
import sys
import time
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from dotenv import load_dotenv

from google import genai

load_dotenv()


# ============================================================================
# CONFIGURAÇÕES
# ============================================================================

MODELO_PADRAO = os.getenv(
    "GEMINI_TRANSCRIBE_MODEL",
    "gemini-3.5-transcribe",
)


# ============================================================================
# EXCEÇÕES
# ============================================================================

class GeminiTranscribeErro(Exception):
    """Exceção base para erros da rota Gemini Transcribe."""

    pass


class ChaveGeminiNaoConfigurada(GeminiTranscribeErro):
    """Lançada quando GEMINI_API_KEY não foi configurada."""

    pass


class TranscricaoGeminiCancelada(GeminiTranscribeErro):
    """Lançada quando o processamento é cancelado."""

    pass


class DiarizacaoSemAnotacoesErro(GeminiTranscribeErro):
    """Lançada quando a API não retorna informações de speaker."""

    pass


# ============================================================================
# CLIENTE GEMINI
# ============================================================================

def obter_cliente_gemini(
    api_key: Optional[str] = None,
) -> genai.Client:
    """
    Instancia o cliente oficial do Google GenAI.
    """

    chave = api_key or os.getenv("GEMINI_API_KEY")

    if not chave:
        raise ChaveGeminiNaoConfigurada(
            "Chave 'GEMINI_API_KEY' não encontrada no .env "
            "ou nas variáveis de ambiente."
        )

    return genai.Client(api_key=chave)


# ============================================================================
# MIME TYPE
# ============================================================================

def _determinar_mime_type(caminho: Path) -> str:
    """
    Retorna o MIME type adequado para o arquivo de áudio.
    """

    mapa = {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".ogg": "audio/ogg",
        ".m4a": "audio/mp4",
        ".flac": "audio/flac",
        ".aac": "audio/aac",
        ".opus": "audio/opus",
    }

    return mapa.get(caminho.suffix.lower(), "audio/wav")


# ============================================================================
# CONVERSÃO DE TIMESTAMPS
# ============================================================================

def _offset_para_segundos(valor: Any) -> float:
    """
    Converte diferentes representações de timestamp para segundos.

    O SDK pode representar offsets como strings ou objetos de duração.
    """

    if valor is None:
        return 0.0

    # Já é número
    if isinstance(valor, (int, float)):
        return float(valor)

    # datetime.timedelta
    if hasattr(valor, "total_seconds"):
        try:
            return float(valor.total_seconds())
        except Exception:
            pass

    # Objetos semelhantes a protobuf Duration
    if hasattr(valor, "seconds"):
        try:
            segundos = float(valor.seconds)

            nanos = float(
                getattr(valor, "nanos", 0)
            )

            return segundos + nanos / 1_000_000_000

        except Exception:
            pass

    texto = str(valor).strip()

    if not texto:
        return 0.0

    # Exemplo:
    # 1.25s
    # 0.450s
    if texto.endswith("s"):
        texto_sem_s = texto[:-1]

        try:
            return float(texto_sem_s)

        except ValueError:
            pass

    # Exemplo:
    # 00:01.250
    # 01:32.400
    match = re.fullmatch(
        r"(\d+):(\d{2})[.:](\d+)",
        texto,
    )

    if match:
        minutos = int(match.group(1))
        segundos = int(match.group(2))
        fracao = match.group(3)

        valor_fracao = float(f"0.{fracao}")

        return minutos * 60 + segundos + valor_fracao

    # Tenta conversão direta
    try:
        return float(texto)

    except ValueError:
        raise GeminiTranscribeErro(
            f"Não foi possível interpretar o timestamp retornado "
            f"pelo Gemini: {valor!r}"
        )


# ============================================================================
# EXTRAÇÃO DAS ANOTAÇÕES DE PALAVRAS
# ============================================================================

def _extrair_word_annotations(
    interaction: Any,
) -> list[Any]:
    """
    Extrai as anotações word_info da resposta do Gemini.

    Cada word_info pode conter:
        - text
        - speaker
        - start_offset
        - end_offset
    """

    palavras: list[Any] = []

    for step in getattr(interaction, "steps", []) or []:

        for content in getattr(step, "content", []) or []:

            for annotation in (
                getattr(content, "annotations", []) or []
            ):

                if getattr(annotation, "type", None) == "word_info":
                    palavras.append(annotation)

    return palavras


# ============================================================================
# NORMALIZAÇÃO DOS WORD INFO
# ============================================================================

def _normalizar_word_annotation(
    annotation: Any,
) -> dict[str, Any]:
    """
    Converte uma annotation word_info em dict simples.
    """

    texto = str(
        getattr(annotation, "text", "") or ""
    ).strip()

    speaker = getattr(
        annotation,
        "speaker",
        None,
    )

    speaker = (
        str(speaker).strip()
        if speaker
        else "SPEAKER_00"
    )

    start = _offset_para_segundos(
        getattr(
            annotation,
            "start_offset",
            0.0,
        )
    )

    end = _offset_para_segundos(
        getattr(
            annotation,
            "end_offset",
            start,
        )
    )

    return {
        "text": texto,
        "speaker": speaker,
        "start": round(start, 3),
        "end": round(end, 3),
    }


# ============================================================================
# JUNÇÃO DAS PALAVRAS
# ============================================================================

def _juntar_palavras(
    palavras: list[str],
) -> str:
    """
    Junta palavras tentando evitar espaços antes de pontuação.
    """

    texto = ""

    pontuacao_sem_espaco = {
        ".",
        ",",
        ";",
        ":",
        "!",
        "?",
        "%",
        ")",
        "]",
        "}",
    }

    abertura = {
        "(",
        "[",
        "{",
    }

    for palavra in palavras:

        palavra = palavra.strip()

        if not palavra:
            continue

        if not texto:
            texto = palavra
            continue

        # Não coloca espaço antes de pontuação
        if palavra[0] in pontuacao_sem_espaco:
            texto += palavra
            continue

        # Não coloca espaço depois de abertura
        if texto[-1:] in abertura:
            texto += palavra
            continue

        texto += " " + palavra

    return texto.strip()


# ============================================================================
# AGRUPAMENTO POR SPEAKER
# ============================================================================

def _agrupar_palavras_em_turnos(
    palavras: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Agrupa palavras consecutivas do mesmo speaker.

    Exemplo:

        SPEAKER_00:
            Bom dia

        SPEAKER_01:
            Bom dia

    vira:

        [
            {
                "speaker": "SPEAKER_00",
                "start": 0.2,
                "end": 1.2,
                "texto": "Bom dia"
            },
            {
                "speaker": "SPEAKER_01",
                "start": 1.3,
                "end": 2.0,
                "texto": "Bom dia"
            }
        ]
    """

    if not palavras:
        return []

    turnos: list[dict[str, Any]] = []

    turno_atual: Optional[dict[str, Any]] = None

    for palavra in palavras:

        texto = palavra["text"].strip()

        if not texto:
            continue

        speaker = palavra["speaker"]
        start = float(palavra["start"])
        end = float(palavra["end"])

        if turno_atual is None:

            turno_atual = {
                "speaker": speaker,
                "start": start,
                "end": end,
                "_palavras": [texto],
            }

            continue

        # Mesmo speaker continua falando
        if turno_atual["speaker"] == speaker:

            turno_atual["end"] = end
            turno_atual["_palavras"].append(texto)

            continue

        # Mudança real de speaker
        turno_atual["texto"] = _juntar_palavras(
            turno_atual["_palavras"]
        )

        del turno_atual["_palavras"]

        turnos.append(turno_atual)

        turno_atual = {
            "speaker": speaker,
            "start": start,
            "end": end,
            "_palavras": [texto],
        }

    # Fecha o último turno
    if turno_atual is not None:

        turno_atual["texto"] = _juntar_palavras(
            turno_atual["_palavras"]
        )

        del turno_atual["_palavras"]

        turnos.append(turno_atual)

    return turnos


# ============================================================================
# ORDENAÇÃO
# ============================================================================

def _ordenar_turnos(
    turnos: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Garante ordem cronológica.
    """

    turnos.sort(
        key=lambda x: float(
            x.get("start", 0.0)
        )
    )

    return turnos


# ============================================================================
# FORMATAÇÃO DO DIÁLOGO
# ============================================================================

def formatar_dialogo_para_texto(
    turnos: list[dict[str, Any]],
) -> str:
    """
    Converte os turnos para texto legível.

    Exemplo:

    SPEAKER_00 (0.40s - 3.20s): Bom dia, tudo bem?
    SPEAKER_01 (3.30s - 5.10s): Tudo.
    """

    linhas: list[str] = []

    for turno in turnos:

        speaker = turno.get(
            "speaker",
            "SPEAKER_00",
        )

        start = float(
            turno.get("start", 0.0)
        )

        end = float(
            turno.get("end", 0.0)
        )

        texto = str(
            turno.get("texto", "")
        ).strip()

        linhas.append(
            f"{speaker} "
            f"({start:.2f}s - {end:.2f}s): "
            f"{texto}"
        )

    return "\n".join(linhas)


# ============================================================================
# FUNÇÃO PRINCIPAL
# ============================================================================

def diarizar_audio_gemini(
    caminho_audio: Path | str,
    *,
    modelo: str = MODELO_PADRAO,
    nome_atendente_sugerido: Optional[str] = None,
    contexto_adicional: Optional[str] = None,
    temperatura: float = 0.2,
    cancel: Optional[threading.Event] = None,
    on_progress: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    """
    Transcreve e diariza um áudio usando Gemini 3.5 Transcribe.

    Recursos:

        - Português brasileiro
        - Verbatim
        - Diarização
        - Word-level timestamps

    Retorna:

        {
            "turnos": [...],
            "texto_formatado": "...",
            "speakers": [...],
            "transcricao_completa": "...",
            "resumo": "",
            "motivo_contato": "",
            "sentimento_geral": "",
            "metadados": {...}
        }

    Observação:

        nome_atendente_sugerido, contexto_adicional e temperatura são
        mantidos na assinatura para compatibilidade com chamadas existentes,
        mas não são enviados como Structured Output ao modelo Transcribe.
    """

    if cancel is not None and cancel.is_set():
        raise TranscricaoGeminiCancelada(
            "Cancelamento solicitado antes de iniciar a chamada."
        )

    caminho = Path(caminho_audio)

    if not caminho.exists() or not caminho.is_file():
        raise GeminiTranscribeErro(
            f"Arquivo de áudio não encontrado: {caminho}"
        )

    if on_progress:
        on_progress(
            f"Enviando áudio '{caminho.name}' "
            f"para o Gemini..."
        )

    client = obter_cliente_gemini()

    inicio = time.perf_counter()

    uploaded_file = None

    try:

        # ------------------------------------------------------------
        # UPLOAD
        # ------------------------------------------------------------

        mime_type = _determinar_mime_type(caminho)

        uploaded_file = client.files.upload(
            file=str(caminho),
        )

        if on_progress:
            on_progress(
                f"Áudio enviado. Executando transcrição "
                f"e diarização com {modelo}..."
            )

        if cancel is not None and cancel.is_set():
            raise TranscricaoGeminiCancelada(
                "Cancelamento solicitado após envio do áudio."
            )

        # ------------------------------------------------------------
        # CONFIGURAÇÃO DO TRANSCRIBE
        # ------------------------------------------------------------
        #
        # IMPORTANTÍSSIMO:
        #
        # Não utilizamos:
        #
        # response_mime_type="application/json"
        # response_schema=...
        #
        # O modelo Transcribe retorna a transcrição e as annotations
        # word_info através da Interactions API.
        #
        # ------------------------------------------------------------

        interaction = client.interactions.create(
            model=modelo,
            input=[
                {
                    "type": "audio",
                    "uri": uploaded_file.uri,
                    "mime_type": mime_type,
                }
            ],
            generation_config={
                "transcription_config": {
                    "language_codes": ["pt-BR"],
                    "mode": {
                        "type": "verbatim",
                        "diarization_mode": "speaker",
                        "timestamp_granularities": ["word"],
                    },
                }
            },
        )

        if cancel is not None and cancel.is_set():
            raise TranscricaoGeminiCancelada(
                "Cancelamento solicitado após processamento do Gemini."
            )

        # ------------------------------------------------------------
        # TEXTO COMPLETO
        # ------------------------------------------------------------

        texto_completo = str(
            getattr(
                interaction,
                "output_text",
                "",
            )
            or ""
        ).strip()

        # ------------------------------------------------------------
        # EXTRAÇÃO DAS PALAVRAS + SPEAKERS
        # ------------------------------------------------------------

        annotations_brutas = _extrair_word_annotations(
            interaction
        )

        if not annotations_brutas:
            raise DiarizacaoSemAnotacoesErro(
                "O Gemini retornou a transcrição, mas não retornou "
                "anotações 'word_info' com dados de diarização. "
                "Não é seguro montar os interlocutores apenas "
                "a partir do texto."
            )

        palavras = [
            _normalizar_word_annotation(
                annotation
            )
            for annotation in annotations_brutas
        ]

        # Remove palavras vazias
        palavras = [
            palavra
            for palavra in palavras
            if palavra["text"]
        ]

        # ------------------------------------------------------------
        # AGRUPAMENTO
        # ------------------------------------------------------------

        turnos = _agrupar_palavras_em_turnos(
            palavras
        )

        turnos = _ordenar_turnos(turnos)

        # ------------------------------------------------------------
        # SPEAKERS
        # ------------------------------------------------------------

        speakers: list[str] = []

        for turno in turnos:

            speaker = turno["speaker"]

            if speaker not in speakers:
                speakers.append(speaker)

        # ------------------------------------------------------------
        # TEXTO FORMATADO
        # ------------------------------------------------------------

        texto_formatado = formatar_dialogo_para_texto(
            turnos
        )

        # ------------------------------------------------------------
        # TEMPO
        # ------------------------------------------------------------

        tempo_total = round(
            time.perf_counter() - inicio,
            2,
        )

        if on_progress:
            on_progress(
                f"Processamento concluído em "
                f"{tempo_total}s. "
                f"{len(speakers)} speakers identificados "
                f"e {len(turnos)} turnos gerados."
            )

        # ------------------------------------------------------------
        # RESULTADO
        # ------------------------------------------------------------

        return {
            "turnos": turnos,

            "texto_formatado": texto_formatado,

            "speakers": speakers,

            "transcricao_completa": texto_completo,

            # Mantidos para compatibilidade com o restante do SONAX.
            # O Transcribe não realiza essa análise nessa chamada.
            "resumo": "",

            "motivo_contato": "",

            "sentimento_geral": "",

            # Útil para debugging/alinhamento.
            "palavras": palavras,

            "metadados": {
                "modelo": modelo,
                "tempo_processamento_s": tempo_total,
                "arquivo": caminho.name,
                "mime_type": mime_type,
                "total_speakers": len(speakers),
                "total_turnos": len(turnos),
                "diarizacao": True,
                "timestamps_palavra": True,
                "idioma": "pt-BR",
            },
        }

    except GeminiTranscribeErro:
        raise

    except Exception as exc:
        raise GeminiTranscribeErro(
            f"Falha durante a transcrição/diarização via Gemini "
            f"({modelo}): {exc}"
        ) from exc

    finally:

        # ------------------------------------------------------------
        # LIMPEZA DO ARQUIVO REMOTO
        # ------------------------------------------------------------

        if uploaded_file is not None:

            try:
                client.files.delete(
                    name=uploaded_file.name
                )

            except Exception:
                # Falha na limpeza não deve mascarar o resultado.
                pass


# ============================================================================
# CLI PARA TESTE
# ============================================================================

if __name__ == "__main__":

    print("=" * 70)
    print("SONAX - Gemini Transcribe + Diarização")
    print("=" * 70)

    print(
        f"Modelo configurado: {MODELO_PADRAO}"
    )

    print()

    if len(sys.argv) < 2:

        print(
            "Uso:"
        )

        print(
            "python -m app.services.gemini_transcribe "
            "<caminho_do_audio.wav>"
        )

        print()

        print(
            "Exemplo:"
        )

        print(
            "python -m app.services.gemini_transcribe "
            "\"C:\\audios\\chamada.wav\""
        )

        print()

        try:

            cliente = obter_cliente_gemini()

            print(
                "[OK] Cliente Gemini inicializado."
            )

        except Exception as exc:

            print(
                f"[ERRO] Falha ao inicializar Gemini: {exc}"
            )

            sys.exit(1)

        sys.exit(0)

    audio_teste = Path(
        sys.argv[1]
    )

    if not audio_teste.exists():

        print(
            f"[ERRO] Arquivo não encontrado: "
            f"{audio_teste}"
        )

        sys.exit(1)

    print(
        f"Arquivo: {audio_teste.name}"
    )

    print()

    try:

        resultado = diarizar_audio_gemini(
            audio_teste,
            on_progress=lambda mensagem: print(
                f"  -> {mensagem}"
            ),
        )

        print()
        print(
            "=" * 70
        )
        print(
            "RESULTADO DA DIARIZAÇÃO"
        )
        print(
            "=" * 70
        )

        print()

        print(
            f"Speakers: {resultado['speakers']}"
        )

        print(
            f"Quantidade de speakers: "
            f"{len(resultado['speakers'])}"
        )

        print(
            f"Quantidade de turnos: "
            f"{len(resultado['turnos'])}"
        )

        print()

        print(
            "--- DIÁLOGO ---"
        )

        print()

        print(
            resultado["texto_formatado"]
        )

        print()

        print(
            "=" * 70
        )
        print(
            "METADADOS"
        )
        print(
            "=" * 70
        )

        print()

        for chave, valor in (
            resultado["metadados"]
            .items()
        ):
            print(
                f"{chave}: {valor}"
            )

    except Exception as exc:

        print()
        print(
            "[FALHA NO TESTE]"
        )
        print(
            str(exc)
        )

        sys.exit(1)