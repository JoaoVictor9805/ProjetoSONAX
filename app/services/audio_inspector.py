# -*- coding: utf-8 -*-
"""
============================================================================
Módulo de Inspeção de Áudio do SONAX.

Responsabilidades:
    1. Parsing binário de baixo nível do contêiner RIFF/WAVE (sem decodificar
       o áudio em memória nem depender de bibliotecas pesadas).
    2. Classificação de arquivos por duração (>60s, <=60s, corrompidos).
    3. Análise de integridade acústica com retries e descarte de arquivos
       com qualidade 'Péssimo'.
============================================================================
"""
from __future__ import annotations

import struct
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.logs import log_dev_exc
from app.services.qualidade_audio import (
    analisar_audio,
    classificar_qualidade_audio,
)

OnProgressCallback = Callable[[int, int, Path], None]


@dataclass(frozen=True)
class AudioMetadata:
    """Informações técnicas e duração de um arquivo WAV inspecionado."""
    path: Path
    duracao: float
    byte_rate: int | None = None
    data_size: int | None = None


@dataclass(frozen=True)
class InspecaoLoteResult:
    """Resultado da categorização de arquivos WAV por integridade e duração."""
    longos: list[AudioMetadata]      # Áudios > 60 segundos
    curtos: list[AudioMetadata]      # Áudios <= 60 segundos
    invalidos: list[Path]            # Arquivos corrompidos ou não-WAV


class AudioInspector:
    """Módulo profundo para inspeção estrutural e acústica de áudios."""

    def inspecionar(self, caminho: Path) -> AudioMetadata | None:
        """Lê os cabeçalhos RIFF/WAVE e extrai duração em segundos ou None se inválido."""
        try:
            with open(caminho, "rb") as f:
                riff, _, wave = struct.unpack("<4sI4s", f.read(12))
                if riff != b"RIFF" or wave != b"WAVE":
                    return None

                byte_rate: int | None = None
                data_size: int | None = None

                while True:
                    cabecalho = f.read(8)
                    if len(cabecalho) < 8:
                        break
                    chunk_id, chunk_size = struct.unpack("<4sI", cabecalho)
                    if chunk_id == b"fmt ":
                        fmt = f.read(chunk_size)
                        if len(fmt) < 16:
                            return None
                        byte_rate = struct.unpack("<I", fmt[8:12])[0]
                    elif chunk_id == b"data":
                        data_size = chunk_size
                        f.seek(chunk_size, 1)
                    else:
                        f.seek(chunk_size, 1)

                    if chunk_size % 2:
                        f.read(1)

                    if byte_rate and data_size is not None:
                        break

            if byte_rate and data_size:
                duracao = data_size / byte_rate
                return AudioMetadata(
                    path=caminho,
                    duracao=duracao,
                    byte_rate=byte_rate,
                    data_size=data_size,
                )
            return None

        except Exception:
            return None

    def classificar_lote(
        self,
        caminhos: list[Path],
        cancel: threading.Event | None = None,
    ) -> InspecaoLoteResult:
        """Separa uma lista de arquivos em longos (>60s), curtos (<=60s) e inválidos."""
        longos: list[AudioMetadata] = []
        curtos: list[AudioMetadata] = []
        invalidos: list[Path] = []

        for w in caminhos:
            if cancel is not None and cancel.is_set():
                break

            meta = self.inspecionar(w)
            if meta is None:
                invalidos.append(w)
            elif meta.duracao > 60:
                longos.append(meta)
            else:
                curtos.append(meta)

        return InspecaoLoteResult(longos=longos, curtos=curtos, invalidos=invalidos)

    def filtrar_qualidade_acustica(
        self,
        audios: list[AudioMetadata],
        cancel: threading.Event | None = None,
        on_progress: OnProgressCallback | None = None,
    ) -> tuple[list[AudioMetadata], list[Path]]:
        """Analisa a qualidade acústica com até 3 tentativas, descartando áudios 'Péssimo'.

        Returns:
            tuple[list[AudioMetadata], list[Path]]: (aprovados, rejeitados)
        """
        aprovados: list[AudioMetadata] = []
        rejeitados: list[Path] = []
        total = len(audios)

        for idx, meta in enumerate(audios, 1):
            if cancel is not None and cancel.is_set():
                break

            rotulo_audio = f"Audio {idx:02d}"

            if on_progress is not None:
                try:
                    on_progress(idx, total, meta.path)
                except Exception:
                    pass

            classificacao: str | None = None

            for tentativa in range(1, 4):
                try:
                    dados = analisar_audio(meta.path)
                    classificacao = classificar_qualidade_audio(dados)
                    break
                except Exception:
                    print(
                        f"[AVISO] Não foi possível analisar a qualidade "
                        f"de '{rotulo_audio}' (tentativa {tentativa}/3)"
                    )
                    log_dev_exc()
                    if tentativa < 3:
                        print(f"  [INFO] Tentando novamente ({tentativa + 1}/3) ...")
            else:
                print(
                    f"[ERRO] Não foi possível analisar a qualidade "
                    f"de '{rotulo_audio}' após 3 tentativas — excluído do processamento."
                )
                rejeitados.append(meta.path)
                continue

            if classificacao == "Péssimo":
                print(f"  [INFO] {rotulo_audio} reprovado ({classificacao}) — excluído do processamento")
                rejeitados.append(meta.path)
            else:
                print(f"  [INFO] {rotulo_audio} aprovado ({classificacao})")
                aprovados.append(meta)

        return aprovados, rejeitados


def obter_duracao_wav(caminho: Path | str) -> float:
    """Calcula e retorna a duração em segundos de um arquivo WAV, ou 0.0 se inválido."""
    meta = AudioInspector().inspecionar(Path(caminho))
    return meta.duracao if meta is not None else 0.0

