# -*- coding: utf-8 -*-
"""
Serviço Macro de Diarização e Alinhamento Temporal de Locutores.

Integração com Pyannote.audio (Speaker Diarization 3.1) e alinhamento
fino por palavra (word-level) com as transcrições do Faster-Whisper.
"""

import os
import sys
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

load_dotenv()


class DiarizacaoErro(Exception):
    """Exceção base para erros durante o processo de diarização."""
    pass


class TokenHuggingFaceNaoConfigurado(DiarizacaoErro):
    """Lançada quando a chave/token do Hugging Face não está no .env."""
    pass


@lru_cache(maxsize=1)
def carregar_pipeline_diarizacao(hf_token: str | None = None) -> Any:
    """Carrega o pipeline do Pyannote uma única vez por processo."""
    token = hf_token or os.getenv("HUGGINGFACE_TOKEN") or os.getenv("HF_TOKEN")
    if not token:
        raise TokenHuggingFaceNaoConfigurado(
            "Token do Hugging Face não encontrado no arquivo .env "
            "(defina HUGGINGFACE_TOKEN=hf_...)."
        )

    try:
        import torch
        from pyannote.audio import Pipeline
    except ImportError as exc:
        raise DiarizacaoErro(
            "Bibliotecas 'pyannote.audio' e/ou 'torch' não estão instaladas. "
            "Execute: pip install pyannote.audio torch torchaudio"
        ) from exc

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type == "cpu":
        # Evita consumir 100% de todas as threads no Windows
        torch.set_num_threads(max(1, min(4, (os.cpu_count() or 4) - 1)))

    MODEL_ID = "pyannote/speaker-diarization-3.1"
    try:
        pipeline = Pipeline.from_pretrained(
            MODEL_ID,
            token=token,
        )
    except Exception as e:
        raise DiarizacaoErro(
            f"Falha ao carregar modelo do Hugging Face. Verifique se o token é válido "
            f"e se você aceitou os termos de uso de '{MODEL_ID}' "
            f"e 'pyannote/segmentation-3.0' no Hugging Face: {e}"
        ) from e

    if pipeline is None:
        raise DiarizacaoErro(
            f"Pipeline.from_pretrained retornou None para '{MODEL_ID}'. "
            "Verifique se o modelo existe, se o token tem permissão de acesso "
            "e se você aceitou os termos de uso no site do Hugging Face."
        )

    return pipeline.to(device)


def diarizar_audio(
    caminho_wav: Path | str,
    *,
    min_speakers: int = 1,
    max_speakers: int = 4,
    cancel: "threading.Event | None" = None,
) -> list[dict]:
    """Executa a diarização acústica no arquivo WAV.

    Retorna uma lista de intervalos ordenados:
    [
        {"start": 0.35, "end": 4.80, "speaker": "SPEAKER_00"},
        {"start": 4.90, "end": 9.70, "speaker": "SPEAKER_01"}
    ]
    """
    if cancel is not None and cancel.is_set():
        raise DiarizacaoErro("Cancelamento solicitado antes de iniciar a diarização.")

    pipeline = carregar_pipeline_diarizacao()

    caminho_str = str(caminho_wav)
    diarization_result = pipeline(
        caminho_str,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
    )

    segmentos: list[dict] = []
    for turn, _, speaker in diarization_result.itertracks(yield_label=True):
        segmentos.append({
            "start": round(turn.start, 3),
            "end": round(turn.end, 3),
            "speaker": str(speaker),
        })

    # Garante ordenação cronológica
    segmentos.sort(key=lambda x: x["start"])
    return segmentos


def _atribuir_locutor(tempo_central: float, segmentos_diarizacao: list[dict]) -> str:
    """Encontra o locutor ativo para um timestamp específico."""
    if not segmentos_diarizacao:
        return "SPEAKER_00"

    # 1. Procura sobreposição direta
    for seg in segmentos_diarizacao:
        if seg["start"] <= tempo_central <= seg["end"]:
            return seg["speaker"]

    # 2. Se cair em uma micropausa/silêncio, busca o segmento temporalmente mais próximo
    melhor_distancia = float("inf")
    melhor_speaker = segmentos_diarizacao[0]["speaker"]

    for seg in segmentos_diarizacao:
        distancia = min(abs(tempo_central - seg["start"]), abs(tempo_central - seg["end"]))
        if distancia < melhor_distancia:
            melhor_distancia = distancia
            melhor_speaker = seg["speaker"]

    return melhor_speaker


def alinhar_transcricao_e_diarizacao(
    palavras_whisper: list[dict],
    segmentos_diarizacao: list[dict],
) -> list[dict]:
    """Cruza palavras individuais com os intervalos de locutores do Pyannote.

    Agrupa palavras contínuas do mesmo locutor em turnos de fala coesos:
    [
        {
            "speaker": "SPEAKER_00",
            "start": 0.40,
            "end": 3.20,
            "texto": "Bom dia, Sonax Telecomunicações."
        },
        ...
    ]
    """
    if not palavras_whisper:
        return []

    if not segmentos_diarizacao:
        # Sem dados de diarização: consolida tudo em um único speaker padrão
        texto_completo = " ".join(p["word"] for p in palavras_whisper)
        return [{
            "speaker": "SPEAKER_00",
            "start": palavras_whisper[0]["start"],
            "end": palavras_whisper[-1]["end"],
            "texto": texto_completo,
        }]

    turnos: list[dict] = []
    turno_atual: dict | None = None

    for item in palavras_whisper:
        palavra = item.get("word", "").strip()
        if not palavra:
            continue

        start_p = item.get("start", 0.0)
        end_p = item.get("end", start_p)
        tempo_central = (start_p + end_p) / 2.0

        speaker = _atribuir_locutor(tempo_central, segmentos_diarizacao)

        if turno_atual is None:
            turno_atual = {
                "speaker": speaker,
                "start": start_p,
                "end": end_p,
                "palavras": [palavra],
            }
        elif turno_atual["speaker"] == speaker:
            # Mesmo locutor continua falando
            turno_atual["end"] = end_p
            turno_atual["palavras"].append(palavra)
        else:
            # Mudança de locutor detectada: fecha turno anterior e inicia novo
            turno_atual["texto"] = " ".join(turno_atual["palavras"])
            del turno_atual["palavras"]
            turnos.append(turno_atual)

            turno_atual = {
                "speaker": speaker,
                "start": start_p,
                "end": end_p,
                "palavras": [palavra],
            }

    if turno_atual:
        turno_atual["texto"] = " ".join(turno_atual["palavras"])
        del turno_atual["palavras"]
        turnos.append(turno_atual)

    return turnos


def formatar_dialogo_para_texto(turnos: list[dict]) -> str:
    """Converte a lista estruturada de turnos em string formatada para prompts de IA.

    Exemplo de saída:
    SPEAKER_00 (0.40s - 3.20s): Bom dia, Sonax Telecomunicações.
    SPEAKER_01 (3.50s - 7.10s): Olá, gostaria de informações...
    """
    linhas = []
    for t in turnos:
        linhas.append(
            f"{t['speaker']} ({t['start']:.2f}s - {t['end']:.2f}s): {t['texto']}"
        )
    return "\n".join(linhas)


def processar_diarizacao_completa(
    caminho_wav: Path | str,
    palavras_whisper: list[dict],
    *,
    min_speakers: int = 1,
    max_speakers: int = 4,
    cancel: "threading.Event | None" = None,
) -> dict:
    """Função macro para executar a diarização e o alinhamento com o Whisper.

    Retorna um dicionário com:
    - 'turnos': lista de blocos de diálogo estruturados
    - 'texto_formatado': diálogo completo em formato texto com timestamps
    - 'speakers': lista única de identificadores encontrados (ex: ['SPEAKER_00', 'SPEAKER_01'])
    - 'segmentos_brutos': lista de segmentos brutos do Pyannote
    """
    segmentos = diarizar_audio(
        caminho_wav,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
        cancel=cancel,
    )

    turnos = alinhar_transcricao_e_diarizacao(palavras_whisper, segmentos)
    texto_formatado = formatar_dialogo_para_texto(turnos)
    speakers = sorted(list({s["speaker"] for s in segmentos}))

    return {
        "turnos": turnos,
        "texto_formatado": texto_formatado,
        "speakers": speakers,
        "segmentos_brutos": segmentos,
    }


# ============================================================================
# CLI / TESTE MANUAL
# ============================================================================

if __name__ == "__main__":
    import json

    print("=" * 70)
    print("TESTE DO SERVIÇO DE DIARIZAÇÃO PADRÃO (Pyannote + Whisper)")
    print("=" * 70)
    print()

    if len(sys.argv) < 2:
        print("Uso:")
        print("  python -m app.services.diarizacao <caminho_audio.wav> [caminho_palavras.json]")
        print()
        print("Exemplos:")
        print("  1. Transcrever com Whisper + Diarizar com Pyannote:")
        print("     python -m app.services.diarizacao meu_audio.wav")
        print()
        print("  2. Diarizar usando JSON de palavras já existente:")
        print("     python -m app.services.diarizacao meu_audio.wav palavras.json")
        print()
        print("Verificando credenciais do Hugging Face...")
        try:
            pipeline = carregar_pipeline_diarizacao()
            print("  [OK] Pipeline do Pyannote carregado com sucesso no dispositivo configurado.")
        except Exception as exc:
            print(f"  [ERRO] Falha ao carregar pipeline Pyannote: {exc}")
            sys.exit(1)

        sys.exit(0)

    audio_teste = Path(sys.argv[1])
    if not audio_teste.exists():
        print(f"[ERRO] Arquivo de áudio não encontrado: {audio_teste}")
        sys.exit(1)

    palavras_whisper = None

    # Se um segundo argumento for passado, tenta carregar as palavras a partir do JSON
    if len(sys.argv) >= 3:
        json_path = Path(sys.argv[2])
        if json_path.exists():
            print(f"Carregando palavras prévias de: {json_path.name}")
            with open(json_path, "r", encoding="utf-8") as f:
                palavras_whisper = json.load(f)
        else:
            print(f"[AVISO] Arquivo JSON '{json_path}' não encontrado. Whisper será executado.")

    try:
        if palavras_whisper is None:
            print(f"Arquivo: {audio_teste.name}")
            print("\n[1/2] Executando transcrição e extração de timestamps (Faster-Whisper)...")
            from app.services.transcrever import transcrever_arquivo

            texto_bruto, _, palavras_whisper = transcrever_arquivo(
                audio_teste,
                word_timestamps=True,
            )
            print(f"  -> Transcrição concluída ({len(palavras_whisper)} palavras identificadas).")

        print("\n[2/2] Executando diarização acústica e alinhamento (Pyannote)...")
        resultado = processar_diarizacao_completa(
            audio_teste,
            palavras_whisper,
        )

        print()
        print("=" * 70)
        print("RESULTADO DA DIARIZAÇÃO")
        print("=" * 70)
        print()
        print(f"Speakers identificados: {resultado['speakers']}")
        print(f"Quantidade de speakers: {len(resultado['speakers'])}")
        print(f"Quantidade de turnos:   {len(resultado['turnos'])}")
        print()
        print("--- DIÁLOGO FORMATADO ---")
        print()
        print(resultado["texto_formatado"])
        print()
        print("=" * 70)

    except Exception as exc:
        print()
        print("[FALHA NO TESTE]")
        print(str(exc))
        sys.exit(1)

