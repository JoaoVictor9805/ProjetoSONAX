from pathlib import Path

def resolver_destino(diretorio: Path) -> Path:
    """Devolve a pasta `audios_maiores_1min` a ser usada como destino.

    Se o `diretorio` for ele mesmo uma pasta de ramal (nome numérico,
    ex.: "00011687"), o destino vai no nível acima (junto das outras
    pastas de ramal). Caso contrário, fica dentro do próprio `diretorio`.
    """
    if diretorio.name.isdigit():
        return diretorio.parent / "audios_maiores_1min"
    return diretorio / "audios_maiores_1min"


def coletar_wavs(diretorio: Path) -> list:
    """Varre `diretorio` recursivamente e devolve os .wav ordenados."""
    return sorted(
        p for p in diretorio.glob("**/*")
        if p.is_file() and p.suffix.lower() == ".wav"
    )