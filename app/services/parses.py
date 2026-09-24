# -*- coding: utf-8 -*-
"""
Funções de parsing de strings para tipos do domínio do SONAX.

Reúne em um único módulo os conversores de string para `date`/`time`/`float`
(vindos do `chamadas_dao`) e o parser do nome de arquivo `.wav` (vindo do
`script`), que decompõe o nome em blocos de identificação da chamada.

"""

from datetime import date, time
from pathlib import Path


# ----------------------------
# Conversores a partir de strings
# ----------------------------

def parse_data(data_ddmmaaaa: str) -> date | None:
    """26082026 -> date(2026, 8, 26)"""
    if len(data_ddmmaaaa) != 8:
        return None
    return date(
        int(data_ddmmaaaa[4:8]),   # ano
        int(data_ddmmaaaa[2:4]),   # mês
        int(data_ddmmaaaa[0:2]),   # dia
    )


def parse_hora(hora_hhmmss: str) -> time | None:
    """113047 -> time(11, 30, 47)"""
    if len(hora_hhmmss) != 6:
        return None
    return time(
        int(hora_hhmmss[0:2]),
        int(hora_hhmmss[2:4]),
        int(hora_hhmmss[4:6]),
    )


# ----------------------------
# Parser do nome do arquivo WAV
# ----------------------------

def parse_nome_arquivo(caminho: Path) -> dict:
    """Decompõe o nome do .wav nos 6 blocos de identificação da chamada:

        103-554130142200-26082026-113047-178775464634775-21153502152.wav
        |   |            |        |      |                 |
        |   |            |        |      |                 call_id
        |   |            |        |      timestamp_epoch   (15 dígitos, sem ponto)
        |   |            |        hora HHMMSS
        |   |            data DDMMAAAA
        |   telefone (DDI 55 + DDD + número)
        ramal / tenant

    Retorna um dict com cada campo + os blocos brutos + o stem.
    Blocos desconhecidos caem em 'extras'.
    """
    stem = caminho.stem
    blocos = [b for b in stem.split("-") if b]

    info = {
        "stem": stem,
        "blocos": blocos,
        "ramal": "",
        "telefone": "",
        "data": "",
        "hora": "",
        "timestamp": "",
        "call_id": "",
        "extras": [],
    }

    for b in blocos:
        if not b.isdigit():
            info["extras"].append(b)
            continue

        # 15 dígitos = timestamp Unix com fração (sem ponto)
        if len(b) == 15:
            info["timestamp"] = b
        # 8 dígitos = data DDMMAAAA
        elif len(b) == 8:
            info["data"] = b
        # 6 dígitos = hora HHMMSS
        elif len(b) == 6:
            info["hora"] = b
        # começa com 55 e tem >= 10 dígitos = telefone (DDI 55 + DDD + número)
        elif b.startswith("55") and len(b) >= 10:
            info["telefone"] = b
        # número grande que sobrou = call_id
        elif len(b) >= 9:
            info["call_id"] = b
        # 3-4 dígitos = ramal / tenant
        else:
            info["ramal"] = b

    return info
