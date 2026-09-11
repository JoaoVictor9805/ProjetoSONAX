# -*- coding: utf-8 -*-
"""
Acesso a dados (INSERTs/SELECTs) das tabelas `origem` e `registro_chamadas`.
Mantém todo SQL isolado do resto do script.
"""

from datetime import datetime
from datetime import date

import psycopg


# ----------------------------
# Consultas
# ----------------------------

def buscar_nome_atendente(
    cur: psycopg.Cursor, 
    ramal: int,
    data_ligacao: datetime
    ) -> str | None:
    """Resolve nome_atendente pelo ramal na tabela origem."""
    cur.execute(
        """
        SELECT agente_nome FROM origem 
        WHERE ramal = %s
            AND dt_inicio <= %s
            AND dt_fim >= %s
        """,
        (ramal, data_ligacao, data_ligacao),  # A vírgula é obrigatória para criar uma tupla de um único elemento. Isso é usado pelo driver do banco para fazer a substituição parametrizada do %s. Apenas para o psycopg.
    )

    row = cur.fetchone()
    return row[0] if row else None


def registro_ja_existe(cur: psycopg.Cursor, log_arquivo: str) -> bool:
    cur.execute("""SELECT 1 FROM registro_chamadas 
                    WHERE log = %s LIMIT 1""", 
                    (log_arquivo,))
                    
    return cur.fetchone() is not None


def inserir_registro_chamada(
    cur: psycopg.Cursor,
    *,  # Determina que: Você é obrigado a escrever o nome dos parâmetros para os parâmetros a baixo:
    ramal: int,
    agente_nome: str,
    data_ligacao: datetime | date,
    log_arquivo: str,
    transcricao: str | None = None,
) -> int | None:
    """Insere em registro_chamadas e devolve o id gerado."""
    cur.execute(
        """
        INSERT INTO registro_chamadas
            (ramal, agente_nome, data_ligacao, log, transcricao)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (ramal, agente_nome, data_ligacao, log_arquivo, transcricao),
    )
    resultado = cur.fetchone()

    if resultado is not None:
        return resultado[0]

    return None

def buscar_transcricao(
    cur: psycopg.Cursor,
    log: str
) -> str | None:
    """ Busca a transcricao na coluna transcricao do banco de dados """
    cur.execute(
        """
        SELECT transcricao FROM registro_chamadas 
        WHERE log = %s 
        LIMIT 1
        """,
        (log,)
    )
    resultado = cur.fetchone()
    return resultado[0] if resultado else None


def verificar_coluna_revisao(
    cur: psycopg.Cursor,
    log: str
) -> bool | None:
    """ Verifica se a coluna de revisão está vazia no BD """
    cur.execute(
        """
        SELECT revisao FROM registro_chamadas 
        WHERE log = %s 
        LIMIT 1
        """,
        (log,)
    )
    resultado = cur.fetchone()
    return resultado[0] if resultado else None


def inserir_revisao(
    cur: psycopg.Cursor,
    log: str,
    revisao: str
) -> str | None:
    """ Insere a revisao na coluna revisao do banco de dados """
    cur.execute(
        """
        UPDATE registro_chamadas
        SET revisao = %s
        WHERE log = %s
        RETURNING revisao
        """,
        (revisao, log),
    )
    resultado = cur.fetchone()
    
    return resultado[0] if resultado else None