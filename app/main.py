# -*- coding: utf-8 -*-
"""
============================================================================
Ponto de entrada executável do projeto SONAX.

Orquestra o fluxo: varre WAVs em um diretório (recursivamente), separa
os áudios com mais de 1 minuto, copia para `audios_maiores_1min`,
transcreve via Whisper e persiste no Postgres.

Toda a lógica de domínio (leitura de WAV, parsing, classificação, cópia,
persistência) vive em `app.services`. Este módulo só lê `sys.argv`, valida
o diretório de entrada, imprime mensagens para o usuário e devolve
códigos de saída.

Uso:
    python -m app.main [DIRETORIO]

Códigos de saída:
    0  Sucesso (com ou sem WAVs longos encontrados).
    1  Diretório inválido.
    2  Falha ao gravar no banco de dados.
============================================================================
"""

import sys
from pathlib import Path

# Permite rodar este arquivo de dentro de app/ (`python main.py ...`) além
# do uso padrão da raiz do projeto (`python -m app.main ...`).
_RAIZ_PROJETO = Path(__file__).resolve().parents[1]
if str(_RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_PROJETO))

from app.services.script import (
    classificar_wavs,
    copiar_longos_para_pasta,
    salvar_no_banco,
)


def parse_args(argv: list) -> tuple:
    """Lê argv e retorna (diretorio, recursivo).

    O flag `-r` / `--recursive` é aceito por compatibilidade, mas a
    varredura é sempre recursiva (a estrutura de pastas é
    `<raiz>/<ramal>/<ano>/<mes>/<dia>/<arquivo>.wav`).
    """
    recursivo = "-r" in argv or "--recursive" in argv
    args = [a for a in argv if a not in ("-r", "--recursive")]
    diretorio = Path(args[0]).resolve() if args else Path.cwd()
    return diretorio, recursivo


def resolver_destino(diretorio: Path) -> Path:
    """Devolve a pasta `audios_maiores_1min` a ser usada como destino.

    Se o `diretorio` for ele mesmo uma pasta de ramal (nome numérico,
    ex.: "00011687"), o destino vai no nível acima (junto das outras
    pastas de ramal). Caso contrário, fica dentro do próprio `diretorio`.
    """
    if diretorio.name.isdigit():
        return diretorio.parent / "audios_maiores_1min"
    return diretorio / "audios_maiores_1min"


def avaliar_profundidade(wavs: list, diretorio: Path) -> list:
    """Devolve a lista de WAVs com profundidade menor que
    `ramal/ano/mes/dia` (esperado: 4 segmentos). A validação é leve —
    apenas um aviso, não bloqueia o processamento.
    """
    profundidade_esperada = 4
    return [
        w for w in wavs
        if len(w.relative_to(diretorio).parts) < profundidade_esperada
    ]


def coletar_wavs(diretorio: Path) -> list:
    """Varre `diretorio` recursivamente e devolve os .wav ordenados."""
    return sorted(
        p for p in diretorio.glob("**/*")
        if p.is_file() and p.suffix.lower() == ".wav"
    )


def main() -> int:
    diretorio, _recursivo = parse_args(sys.argv[1:])

    if not diretorio.is_dir():
        print(f"[ERRO] Diretório não encontrado: {diretorio}", file=sys.stderr)
        return 1

    wavs = coletar_wavs(diretorio)

    suspeitos = avaliar_profundidade(wavs, diretorio)
    if suspeitos:
        exemplos = ", ".join(c.name for c in suspeitos[:3])
        print(f"[AVISO] {len(suspeitos)} arquivo(s) em profundidade "
              f"menor que 4 (esperado: ramal/ano/mes/dia). "
              f"Exemplos: {exemplos}")
        print("[AVISO] O processamento segue usando o nome do arquivo como "
              "fonte dos metadados.\n")

    longos, curtos, invalidos = classificar_wavs(wavs)

    print(f"Diretório: {diretorio}")
    print(f"Total: {len(wavs)}   >1min: {len(longos)}   "
          f"<=1min: {len(curtos)}   inválidos: {len(invalidos)}\n")

    if not longos:
        print("Nenhum áudio com mais de 1 minuto encontrado.")
        return 0

    destino = resolver_destino(diretorio)
    print(f"Pasta de destino: {destino}\n")

    copiados = copiar_longos_para_pasta(longos, destino)
    print(f"\n{len(copiados)} arquivo(s) copiado(s) para: {destino}")

    print("\nTranscrevendo e gravando no banco de dados...")
    try:
        inseridos = salvar_no_banco(copiados)
        print(f"\n{inseridos} registro(s) inserido(s) com transcrição.")
    except Exception as e:
        print(f"\n[ERRO BD] Falha ao gravar no banco: {e}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
