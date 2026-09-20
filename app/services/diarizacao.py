# -*- coding: utf-8 -*-
"""
Serviço Macro de Diarização e Alinhamento Temporal de Locutores via WhisperX.

Integração com:
1. Alinhamento Forçado acústico por fonemas (Wav2Vec2 em Português do Brasil).
2. Diarização Acústica via Pyannote.audio 3.1.
3. Atribuição precisa de locutor por palavra (evitando inversões de Agente/Cliente).
4. Otimização para execução em CPU (Intel Core i3, 16GB RAM) e GPU (NVIDIA RTX).
"""

import gc
import os
import sys
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, List, Optional, Union

from dotenv import load_dotenv

load_dotenv()


class DiarizacaoErro(Exception):
    """Exceção base para erros durante o processo de diarização."""
    pass


class TokenHuggingFaceNaoConfigurado(DiarizacaoErro):
    """Lançada quando a chave/token do Hugging Face não está no .env."""
    pass


def _obter_dispositivo() -> tuple[str, str]:
    """Detecta o melhor dispositivo (GPU CUDA ou CPU) e tipo de computação."""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda", "float16"
    except Exception:
        pass

    # Em CPU (ex: Core i3), limita threads para não travar a máquina ou interface
    try:
        import torch
        qtd_cores = os.cpu_count() or 4
        torch.set_num_threads(max(1, min(4, qtd_cores - 1)))
    except Exception:
        pass

    return "cpu", "int8"


@lru_cache(maxsize=1)
def carregar_modelo_alinhamento(
    language_code: str = "pt",
    device: Optional[str] = None,
) -> tuple[Any, Any]:
    """Carrega e mantém em cache o modelo de Alinhamento Forçado Wav2Vec2."""
    import whisperx

    dev = device or _obter_dispositivo()[0]
    return whisperx.load_align_model(language_code=language_code, device=dev)


@lru_cache(maxsize=1)
def carregar_pipeline_diarizacao(
    hf_token: Optional[str] = None,
    device: Optional[str] = None,
) -> Any:
    """Carrega o pipeline do Pyannote integrado via WhisperX."""
    token = hf_token or os.getenv("HUGGINGFACE_TOKEN") or os.getenv("HF_TOKEN")
    if not token:
        raise TokenHuggingFaceNaoConfigurado(
            "Token do Hugging Face não encontrado no arquivo .env "
            "(defina HUGGINGFACE_TOKEN=hf_...)."
        )

    from whisperx.diarize import DiarizationPipeline

    dev = device or _obter_dispositivo()[0]
    try:
        pipeline = DiarizationPipeline(token=token, device=dev)
        return pipeline
    except Exception as e:
        raise DiarizacaoErro(
            f"Falha ao carregar modelo de diarização do Hugging Face. "
            f"Verifique se o token é válido e se os termos de "
            f"'pyannote/speaker-diarization-3.1' e 'pyannote/segmentation-3.0' "
            f"foram aceitos no Hugging Face: {e}"
        ) from e


def formatar_dialogo_para_texto(turnos: list[dict]) -> str:
    """Converte a lista estruturada de turnos em string formatada para prompts de IA.

    Exemplo de saída:
    SPEAKER_00 (0.40s - 3.20s): Bom dia, Sonax Telecomunicações.
    SPEAKER_01 (3.50s - 7.10s): Olá, gostaria de informações...
    """
    linhas = []
    for t in turnos:
        texto = t.get("texto", "").strip()
        if not texto:
            continue
        start = t.get("start", 0.0)
        end = t.get("end", 0.0)
        speaker = t.get("speaker", "SPEAKER_00")
        linhas.append(f"{speaker} ({start:.2f}s - {end:.2f}s): {texto}")
    return "\n".join(linhas)


def _reconstruir_segmentos_de_palavras(palavras: list[dict]) -> list[dict]:
    """Agrupa palavras soltas do Whisper em blocos/frases para o alinhador."""
    if not palavras:
        return []

    segmentos = []
    bloco_atual = []

    for item in palavras:
        bloco_atual.append(item)
        w = item.get("word", "")
        # Quebra por pontuação ou quando o bloco atinge 15 palavras
        if w.endswith((".", "?", "!", ":", ";")) or len(bloco_atual) >= 15:
            segmentos.append({
                "start": bloco_atual[0].get("start", 0.0),
                "end": bloco_atual[-1].get("end", 0.0),
                "text": " ".join(p.get("word", "").strip() for p in bloco_atual).strip(),
            })
            bloco_atual = []

    if bloco_atual:
        segmentos.append({
            "start": bloco_atual[0].get("start", 0.0),
            "end": bloco_atual[-1].get("end", 0.0),
            "text": " ".join(p.get("word", "").strip() for p in bloco_atual).strip(),
        })

    return segmentos


def _extrair_turnos_de_segmentos_alinhados(segmentos_alinhados: list[dict]) -> list[dict]:
    """Processa o resultado do assign_word_speakers e agrupa falas consecutivas."""
    turnos: list[dict] = []
    turno_atual: Optional[dict] = None

    for seg in segmentos_alinhados:
        words = seg.get("words", [])

        # Se houver palavras com speaker atribuído individualmente
        if words:
            for w in words:
                palavra_texto = w.get("word", "").strip()
                if not palavra_texto:
                    continue

                speaker = w.get("speaker", seg.get("speaker", "SPEAKER_00"))
                w_start = w.get("start", seg.get("start", 0.0))
                w_end = w.get("end", seg.get("end", w_start))

                if turno_atual is None:
                    turno_atual = {
                        "speaker": speaker,
                        "start": w_start,
                        "end": w_end,
                        "palavras": [palavra_texto],
                    }
                elif turno_atual["speaker"] == speaker:
                    turno_atual["end"] = w_end
                    turno_atual["palavras"].append(palavra_texto)
                else:
                    turno_atual["texto"] = " ".join(turno_atual["palavras"]).strip()
                    del turno_atual["palavras"]
                    turnos.append(turno_atual)
                    turno_atual = {
                        "speaker": speaker,
                        "start": w_start,
                        "end": w_end,
                        "palavras": [palavra_texto],
                    }
        else:
            # Fallback por segmento inteiro
            speaker = seg.get("speaker", "SPEAKER_00")
            seg_text = seg.get("text", "").strip()
            if not seg_text:
                continue

            seg_start = seg.get("start", 0.0)
            seg_end = seg.get("end", seg_start)

            if turno_atual is None:
                turno_atual = {
                    "speaker": speaker,
                    "start": seg_start,
                    "end": seg_end,
                    "palavras": [seg_text],
                }
            elif turno_atual["speaker"] == speaker:
                turno_atual["end"] = seg_end
                turno_atual["palavras"].append(seg_text)
            else:
                turno_atual["texto"] = " ".join(turno_atual["palavras"]).strip()
                del turno_atual["palavras"]
                turnos.append(turno_atual)
                turno_atual = {
                    "speaker": speaker,
                    "start": seg_start,
                    "end": seg_end,
                    "palavras": [seg_text],
                }

    if turno_atual:
        turno_atual["texto"] = " ".join(turno_atual.get("palavras", [])).strip()
        turno_atual.pop("palavras", None)
        turnos.append(turno_atual)

    return turnos


def processar_diarizacao_completa(
    caminho_wav: Union[Path, str],
    palavras_whisper: Optional[list[dict]] = None,
    *,
    segmentos_whisper: Optional[list[dict]] = None,
    min_speakers: int = 1,
    max_speakers: int = 4,
    cancel: Optional[threading.Event] = None,
    on_progress: Optional[Callable[[float], None]] = None,
) -> dict:
    """Função macro de diarização acústica e alinhamento forçado via WhisperX.

    Etapas:
    1. Carrega o áudio e ajusta recursos para CPU/GPU.
    2. Executa Alinhamento Forçado (Wav2Vec2 em Português) para obter precisão milimétrica.
    3. Executa Diarização Acústica (Pyannote 3.1).
    4. Cruza palavras alinhadas com locutores de forma exata.
    5. Agrupa o diálogo em turnos estruturados.
    """
    if cancel is not None and cancel.is_set():
        raise DiarizacaoErro("Cancelamento solicitado antes de iniciar a diarização.")

    import whisperx
    from whisperx.diarize import assign_word_speakers

    device, _ = _obter_dispositivo()
    caminho_str = str(caminho_wav)

    # 1. Carrega áudio
    audio = whisperx.load_audio(caminho_str)

    # 2. Prepara segmentos para alinhamento
    segmentos = list(segmentos_whisper) if segmentos_whisper else []
    if not segmentos and palavras_whisper:
        segmentos = _reconstruir_segmentos_de_palavras(palavras_whisper)

    if not segmentos:
        # Sem transcrição prévia, gera texto simples
        return {
            "turnos": [],
            "texto_formatado": "",
            "speakers": ["SPEAKER_00"],
            "segmentos_brutos": [],
        }

    # 3. Alinhamento Forçado via Wav2Vec2 (PT)
    try:
        model_a, metadata = carregar_modelo_alinhamento(language_code="pt", device=device)
        aligned_result = whisperx.align(
            segmentos,
            model_a,
            metadata,
            audio,
            device,
            return_char_alignments=False,
        )
    except Exception as e:
        print(f"  [AVISO] Falha no alinhamento forçado WhisperX ({e}). Mantendo timestamps originais.")
        aligned_result = {"segments": segmentos}

    if cancel is not None and cancel.is_set():
        raise DiarizacaoErro("Cancelamento solicitado após o alinhamento.")

    # 4. Diarização Acústica (Pyannote)
    try:
        diarize_pipeline = carregar_pipeline_diarizacao(device=device)

        def _diarize_callback(pct: float) -> None:
            if on_progress is not None:
                try:
                    on_progress(pct / 100.0)
                except Exception:
                    pass

        diarize_df = diarize_pipeline(
            audio,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
            progress_callback=_diarize_callback,
        )

        # 5. Mesclagem de locutor por palavra
        assigned_result = assign_word_speakers(diarize_df, aligned_result, fill_nearest=True)
        segmentos_finais = assigned_result.get("segments", [])

        # Turnos agrupados
        turnos = _extrair_turnos_de_segmentos_alinhados(segmentos_finais)
        speakers = sorted(list(set(t["speaker"] for t in turnos if "speaker" in t)))
        if not speakers:
            speakers = ["SPEAKER_00"]

        texto_formatado = formatar_dialogo_para_texto(turnos)

        # Segmentos brutos para compatibilidade
        segmentos_brutos = []
        for _, row in diarize_df.iterrows():
            segmentos_brutos.append({
                "start": round(float(row["start"]), 3),
                "end": round(float(row["end"]), 3),
                "speaker": str(row["speaker"]),
            })

    except TokenHuggingFaceNaoConfigurado as te:
        print(f"  [AVISO] Diarização não realizada: {te}")
        turnos = [{
            "speaker": "SPEAKER_00",
            "start": segmentos[0]["start"] if segmentos else 0.0,
            "end": segmentos[-1]["end"] if segmentos else 0.0,
            "texto": " ".join(s.get("text", "") for s in segmentos).strip(),
        }]
        speakers = ["SPEAKER_00"]
        texto_formatado = formatar_dialogo_para_texto(turnos)
        segmentos_brutos = []

    except Exception as exc:
        print(f"  [AVISO] Erro durante a diarização acústica: {exc}")
        turnos = [{
            "speaker": "SPEAKER_00",
            "start": segmentos[0]["start"] if segmentos else 0.0,
            "end": segmentos[-1]["end"] if segmentos else 0.0,
            "texto": " ".join(s.get("text", "") for s in segmentos).strip(),
        }]
        speakers = ["SPEAKER_00"]
        texto_formatado = formatar_dialogo_para_texto(turnos)
        segmentos_brutos = []

    # Limpeza de memória
    try:
        import torch
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass

    return {
        "turnos": turnos,
        "texto_formatado": texto_formatado,
        "speakers": speakers,
        "segmentos_brutos": segmentos_brutos,
    }


# ============================================================================
# CLI / TESTE MANUAL
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("TESTE DO SERVIÇO DE DIARIZAÇÃO WHISPERX (Forced Alignment + Pyannote)")
    print("=" * 70)
    print()

    if len(sys.argv) < 2:
        print("Uso:")
        print("  python -m app.services.diarizacao <caminho_audio.wav>")
        print()
        print("Verificando credenciais e dispositivos...")
        dev, compute = _obter_dispositivo()
        print(f"  Dispositivo selecionado: {dev} ({compute})")
        token = os.getenv("HUGGINGFACE_TOKEN") or os.getenv("HF_TOKEN")
        if token:
            print("  Token do Hugging Face encontrado no .env.")
        else:
            print("  [AVISO] HUGGINGFACE_TOKEN não encontrado no .env.")
        sys.exit(0)

    audio_teste = Path(sys.argv[1])
    if not audio_teste.exists():
        print(f"[ERRO] Arquivo de áudio não encontrado: {audio_teste}")
        sys.exit(1)

    try:
        from app.services.transcrever import transcrever_arquivo

        print(f"Processando: {audio_teste.name} ...")
        texto_bruto, _, palavras, segmentos = transcrever_arquivo(
            audio_teste,
            retornar_segmentos=True,
        )
        print(f"Transcrição inicial concluída: {len(segmentos)} segmentos.")

        print("Executando WhisperX (Alinhamento Forçado + Diarização)...")
        res = processar_diarizacao_completa(
            audio_teste,
            palavras_whisper=palavras,
            segmentos_whisper=segmentos,
        )

        print()
        print("=" * 70)
        print("RESULTADO DO DIÁLOGO:")
        print("=" * 70)
        print(res["texto_formatado"])
        print("=" * 70)

    except Exception as exc:
        print(f"[FALHA] {exc}")
        sys.exit(1)
