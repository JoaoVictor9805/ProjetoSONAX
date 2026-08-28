# -*- coding: utf-8 -*-
"""
Acesso a dados (INSERTs/SELECTs) das tabelas `origem` e `registro_chamadas`.
Mantém todo SQL isolado do resto do script.
"""

from datetime import date, time
from pathlib import Path

import psycopg


# ----------------------------
# Conversores a partir do parse
# ----------------------------

def _parse_data(data_ddmmaaaa: str) -> date | None:
    """26082026 -> date(2026, 8, 26)"""
    if len(data_ddmmaaaa) != 8:
        return None
    return date(
        int(data_ddmmaaaa[4:8]),   # ano
        int(data_ddmmaaaa[2:4]),   # mês
        int(data_ddmmaaaa[0:2]),   # dia
    )


def _parse_hora(hora_hhmmss: str) -> time | None:
    """113047 -> time(11, 30, 47)"""
    if len(hora_hhmmss) != 6:
        return None
    return time(
        int(hora_hhmmss[0:2]),
        int(hora_hhmmss[2:4]),
        int(hora_hhmmss[4:6]),
    )


def _parse_timestamp(ts_15_digitos: str) -> float | None:
    """178775464634775 -> 1787754646.34775"""
    if len(ts_15_digitos) != 15:
        return None
    return float(f"{ts_15_digitos[:10]}.{ts_15_digitos[10:]}")


# ----------------------------
# Consultas
# ----------------------------

def buscar_nome_atendente(cur: psycopg.Cursor, ramal: int) -> str | None:
    """Resolve nome_atendente pelo ramal na tabela origem."""
    cur.execute(
        "SELECT nome_atendente FROM origem WHERE ramal = %s",
        (ramal,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def inserir_registro_chamada(
    cur: psycopg.Cursor,
    *,
    ramal: int,
    nome_atendente: str,
    data_ligacao: date,
    log_arquivo: str,
    transcricao: str | None = None,
) -> int | None:
    """Insere em registro_chamadas e devolve o id gerado."""
    cur.execute(
        """
        INSERT INTO registro_chamadas
            (ramal, nome_atendente, data_ligacao, log, transcricao)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (ramal, nome_atendente, data_ligacao, log_arquivo, transcricao),
    )
    resultado = cur.fetchone()

    if resultado is not None:
        return resultado[0]

    return None
