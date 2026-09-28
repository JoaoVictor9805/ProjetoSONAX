# -*- coding: utf-8 -*-
"""
============================================================================
Módulo de Operações de Sistema de Arquivos e I/O do SONAX.

Responsabilidades:
    1. Resolução do caminho da pasta de trabalho temporária.
    2. Varredura recursiva e deduplicação de arquivos .wav.
    3. Cópia segura de arquivos de áudio para a pasta de trabalho com retries.
    4. Limpeza segura de pastas e arquivos temporários.
============================================================================
"""
from __future__ import annotations

import shutil
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from app.logs import log_dev_exc

if TYPE_CHECKING:
    from app.services.audio_inspector import AudioMetadata

OnCopyProgressCallback = Callable[[int, int, Path], None]


def resolver_destino(diretorio: Path) -> Path:
    """Devolve a pasta `audios_maiores_1min` a ser usada como destino.

    Se o `diretorio` for ele mesmo uma pasta de ramal (nome numérico,
    ex.: "00011687"), o destino vai no nível acima (junto das outras
    pastas de ramal). Caso contrário, fica dentro do próprio `diretorio`.
    """
    if diretorio.name.isdigit():
        return diretorio.parent / "audios_maiores_1min"
    return diretorio / "audios_maiores_1min"


def coletar_wavs(diretorio: Path) -> list[Path]:
    """Varre `diretorio` recursivamente e devolve os .wav ordenados,
    ignorando qualquer pasta temporária 'audios_maiores_1min*' e
    deduplicando arquivos com o mesmo nome.
    """
    vistos = set()
    wavs: list[Path] = []
    for p in sorted(diretorio.glob("**/*")):
        if (
            p.is_file()
            and p.suffix.lower() == ".wav"
            and not any(part.startswith("audios_maiores_1min") for part in p.parts)
        ):
            if p.name not in vistos:
                vistos.add(p.name)
                wavs.append(p)
    return wavs


def copiar_lote_trabalho(
    audios: list[AudioMetadata] | list[tuple[Path, float]],
    pasta_destino: Path,
    cancel: threading.Event | None = None,
    on_progress: OnCopyProgressCallback | None = None,
) -> list[Path]:
    """Copia os áudios elegíveis para a pasta de destino com retries.

    Ordena decrescente por duração e descarta duplicatas por nome de arquivo.
    Retorna a lista dos arquivos copiados com sucesso na pasta de destino.
    """
    pasta_destino.mkdir(exist_ok=True, parents=True)
    copiados: list[Path] = []
    vistos = set()

    # Normaliza lista para tuplas (Path, duracao)
    itens: list[tuple[Path, float]] = []
    for item in audios:
        if hasattr(item, "path") and hasattr(item, "duracao"):
            itens.append((item.path, item.duracao))
        elif isinstance(item, tuple) and len(item) >= 2:
            itens.append((item[0], item[1]))

    itens_ordenados = sorted(itens, key=lambda x: -x[1])
    total = len(itens_ordenados)

    for caminho, _ in itens_ordenados:
        if cancel is not None and cancel.is_set():
            break

        if caminho.name in vistos:
            continue
        vistos.add(caminho.name)

        destino = pasta_destino / caminho.name
        sucesso = False

        for tentativa in range(1, 4):
            try:
                shutil.copy2(caminho, destino)
                sucesso = True
                break
            except Exception:
                print(
                    f"  [AVISO] Falha ao copiar '{caminho.name}' (tentativa {tentativa}/3)"
                )
                log_dev_exc()
                if tentativa < 3:
                    print(f"  [INFO] Tentando novamente ({tentativa + 1}/3) ...")

        if not sucesso:
            print(f"  [ERRO] Não foi possível copiar '{caminho.name}' após 3 tentativas.")
            continue

        copiados.append(destino)

        if on_progress is not None:
            try:
                on_progress(len(copiados), total, caminho)
            except Exception:
                pass

    return copiados


def deletar_pasta(pasta: Path) -> bool:
    """Exclui a pasta especificada e todo o seu conteúdo recursivamente."""
    if not pasta.exists():
        return True

    shutil.rmtree(pasta, ignore_errors=True)

    if pasta.exists():
        print(f"[AVISO] Não foi possível excluir a pasta temporária: {pasta}")
        return False

    print(f"[INFO] Pasta temporária excluída com sucesso: {pasta}")
    return True