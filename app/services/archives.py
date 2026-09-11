# -*- coding: utf-8 -*-
"""
============================================================================
Serviço de manipulação e extração de arquivos compactados (.zip e .rar).

Responsabilidades:
    1. Localizar e configurar executáveis unrar/7z para o rarfile no Windows.
    2. Validar e descompactar arquivos .zip e .rar com segurança (anti path-traversal).
    3. Normalizar pastas extraídas (lidando com raiz única).
============================================================================
"""
from __future__ import annotations

from pathlib import Path
import shutil
import zipfile
import rarfile

EXTENSOES_SUPORTADAS = {".zip", ".rar"}


class DescompactacaoError(Exception):
    """Exceção levantada quando ocorre falha ao validar ou extrair arquivo compactado."""
    pass


def eh_arquivo_compactado(caminho: Path) -> bool:
    """Verifica se o caminho aponta para um arquivo com extensão compactada suportada."""
    return caminho.is_file() and caminho.suffix.lower() in EXTENSOES_SUPORTADAS


def configurar_rarfile() -> None:
    """Configura o executável unrar/7z para o rarfile no Windows, caso não esteja no PATH."""
    if shutil.which("unrar") or shutil.which("WinRAR") or shutil.which("7z"):
        return
    candidatos = [
        r"C:\Program Files\WinRAR\UnRAR.exe",
        r"C:\Program Files\WinRAR\WinRAR.exe",
        r"C:\Program Files (x86)\WinRAR\UnRAR.exe",
        r"C:\Program Files (x86)\WinRAR\WinRAR.exe",
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ]
    for c in candidatos:
        if Path(c).is_file():
            if "7z" in c.lower():
                setattr(rarfile, "SEVENZIP_TOOL", c)
                setattr(rarfile, "FORCE_TOOL", "7zip")
            else:
                setattr(rarfile, "UNRAR_TOOL", c)
            return


def descompactar_arquivo(
    entrada: Path,
    destino: Path | None = None,
) -> tuple[Path, Path]:
    """Descompacta um arquivo .zip ou .rar em uma pasta de destino.

    Args:
        entrada: Caminho para o arquivo .zip ou .rar.
        destino: Pasta de destino para extração. Se None, usa `entrada.parent / entrada.stem`.

    Returns:
        Tupla `(pasta_extracao, pasta_trabalho)`:
        - `pasta_extracao`: A pasta raiz criada para a extração (usada para limpeza).
        - `pasta_trabalho`: A pasta que contém diretamente os arquivos/subpastas
          (se houver uma única pasta interna sem WAVs na raiz, entra nela).

    Raises:
        DescompactacaoError: Se o arquivo estiver corrompido, contiver caminhos maliciosos
                             ou falhar durante a extração.
    """
    ext = entrada.suffix.lower()
    if ext not in EXTENSOES_SUPORTADAS:
        raise DescompactacaoError(f"Formato não suportado: {ext}. Esperado .zip ou .rar.")

    pasta_extracao = destino if destino is not None else entrada.parent / entrada.stem
    if pasta_extracao.exists():
        shutil.rmtree(pasta_extracao, ignore_errors=True)
    pasta_extracao.mkdir(parents=True, exist_ok=True)

    try:
        if ext == ".zip":
            with zipfile.ZipFile(entrada, "r") as zf:
                # Validação defensiva contra zip bomb e path traversal.
                membros_invalidos = [
                    m for m in zf.namelist()
                    if m.startswith("/") or ".." in Path(m).parts
                ]
                if membros_invalidos:
                    raise zipfile.BadZipFile(
                        f"Arquivo ZIP contém caminhos inválidos: {membros_invalidos[:3]}..."
                    )
                zf.extractall(pasta_extracao)

        elif ext == ".rar":
            configurar_rarfile()
            with rarfile.RarFile(entrada, "r") as rf:
                membros_invalidos = [
                    m for m in rf.namelist()
                    if m.startswith("/") or ".." in Path(m).parts
                ]
                if membros_invalidos:
                    raise rarfile.BadRarFile(
                        f"Arquivo RAR contém caminhos inválidos: {membros_invalidos[:3]}..."
                    )
                rf.extractall(pasta_extracao)

    except Exception as e:
        # Se falhou, limpa a pasta parcialmente criada e repassa como DescompactacaoError
        shutil.rmtree(pasta_extracao, ignore_errors=True)
        raise DescompactacaoError(f"Falha ao descompactar '{entrada.name}': {e}") from e

    # Se o arquivo compactado tiver uma única pasta raiz sem .wav no topo, "entra" nela
    subdirs = [p for p in pasta_extracao.iterdir() if p.is_dir()]
    if len(subdirs) == 1 and not any(pasta_extracao.glob("*.wav")):
        pasta_trabalho = subdirs[0]
    else:
        pasta_trabalho = pasta_extracao

    return pasta_extracao, pasta_trabalho
