# -*- coding: utf-8 -*-
"""
Acesso a dados (INSERTs/SELECTs/UPDATEs) das tabelas `origem`, `registro_chamadas`,
`avaliacao_ia` e `avaliacao_criterio`.
Mantém todo SQL e mapeamento relacional isolado na camada de persistência (`app/database/`).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

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
        (ramal, data_ligacao, data_ligacao),
    )

    row = cur.fetchone()
    return row[0] if row else None


def buscar_chamada_valida(
    cur: psycopg.Cursor,
    protocolo: int,
    ramal: str | int,
) -> dict[str, Any] | None:
    """Verifica se ramal e protocolo batem com um registro existente na tabela chamadas.

    Retorna um dicionário com os dados cadastrais (ex.: agente_nome, numero, estado_ddd) ou None se não bater.
    """
    cur.execute(
        """
        SELECT protocolo, ramal, agente_nome, numero, estado_ddd 
        FROM chamadas 
        WHERE protocolo = %s AND ramal = %s
        LIMIT 1;
        """,
        (protocolo, str(ramal)),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "protocolo": row[0],
        "ramal": row[1],
        "agente_nome": row[2],
        "numero": row[3],
        "estado_ddd": row[4],
    }


def inserir_empresa(
    cur: psycopg.Cursor,
    nome: str,
    fonte_dados: str | None = None,
) -> int | None:
    """Insere ou busca empresa existente por nome (evitando duplicidades)."""
    nome_limpo = (nome or "").strip()[:100]
    if not nome_limpo:
        nome_limpo = "Não encontrado"

    # 1. Verifica se já existe uma empresa com esse nome (case-insensitive)
    cur.execute(
        "SELECT id_empresa, fonte_dados FROM empresa WHERE LOWER(nome) = LOWER(%s) LIMIT 1;",
        (nome_limpo,),
    )
    row = cur.fetchone()
    if row:
        id_existente, fonte_existente = row[0], row[1]
        # Se a fonte_dados anterior estava vazia e agora temos dados, atualiza
        if fonte_dados and fonte_dados.strip() and not (fonte_existente and fonte_existente.strip()):
            cur.execute(
                "UPDATE empresa SET fonte_dados = %s WHERE id_empresa = %s;",
                (fonte_dados, id_existente),
            )
        return id_existente

    # 2. Se não existir, insere e devolve o novo id_empresa
    cur.execute(
        """
        INSERT INTO empresa (nome, fonte_dados)
        VALUES (%s, %s)
        ON CONFLICT (nome) DO UPDATE
            SET fonte_dados = COALESCE(empresa.fonte_dados, EXCLUDED.fonte_dados)
        RETURNING id_empresa;
        """,
        (nome_limpo, fonte_dados),
    )
    novo_row = cur.fetchone()
    return novo_row[0] if novo_row else None



def registro_ja_existe(cur: psycopg.Cursor, log_arquivo: str) -> bool:
    cur.execute(
        """SELECT 1 FROM registro_chamadas 
           WHERE log = %s LIMIT 1""", 
        (log_arquivo,)
    )
    return cur.fetchone() is not None


def inserir_registro_chamada(
    cur: psycopg.Cursor,
    *,
    log_arquivo: str,
    protocolo: int,
    transcricao: str | None = None,
) -> str | None:
    """Insere em registro_chamadas e devolve o log gerado/inserido."""
    cur.execute(
        """
        INSERT INTO registro_chamadas
            (log, protocolo, transcricao)
        VALUES (%s, %s, %s)
        ON CONFLICT (log) DO NOTHING
        RETURNING log
        """,
        (log_arquivo, protocolo, transcricao),
    )
    resultado = cur.fetchone()
    if resultado is not None:
        return resultado[0]
    return None


def buscar_transcricao(
    cur: psycopg.Cursor,
    log: str
) -> str | None:
    """Busca a transcrição na coluna transcricao do banco de dados."""
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
    """Verifica se a coluna de revisão está preenchida no BD."""
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
    revisao: str,
    id_empresa: int | None = None,
) -> str | None:
    """Insere a revisão e opcionalmente o id_empresa na coluna revisao do banco de dados."""
    if id_empresa is not None:
        try:
            cur.execute(
                """
                UPDATE registro_chamadas
                SET revisao = %s,
                    id_empresa = %s
                WHERE log = %s
                RETURNING revisao
                """,
                (revisao, id_empresa, log),
            )
            resultado = cur.fetchone()
            if resultado:
                return resultado[0]
        except Exception:
            # Caso a coluna id_empresa ainda não exista na base atual
            pass

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


def buscar_revisao(
    cur: psycopg.Cursor,
    log: str
) -> str | None:
    """Busca a revisão na coluna revisao do banco de dados."""
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


def verificar_tabela_analise(
    cur: psycopg.Cursor,
    log: str
) -> bool:
    """Verifica se a análise da ligação já foi realizada."""
    cur.execute(
        """
        SELECT id_avaliacao
        FROM avaliacao_ia
        WHERE registro_chamadas_log = %s
        LIMIT 1
        """,
        (log,)
    )
    resultado = cur.fetchone()
    return resultado is not None


def inserir_analise(
    cur: psycopg.Cursor,
    log: str,
    nota_final: int | None,
    feedback_geral: str,
    criterios: list,
    titulo: str | None = None,
    resumo_chamada: str | None = None,
    pontos_fortes: str | None = None,
    fragilidades: str | None = None,
    oportunidades: str | None = None,
    modelo_ia: str = "Revisão: gemini-3.1-flash-lite | Análise: gemini-3.1-flash-lite",
) -> int | None:
    cur.execute(
        """
        INSERT INTO avaliacao_ia (
            registro_chamadas_log,
            nota_final,
            feedback_geral,
            data_avaliacao,
            modelo_ia,
            titulo,
            resumo_chamada,
            pontos_fortes,
            fragilidades,
            oportunidades
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (registro_chamadas_log) DO NOTHING
        RETURNING id_avaliacao
        """,
        (
            log,
            nota_final,
            feedback_geral,
            date.today(),
            modelo_ia,
            titulo,
            resumo_chamada,
            pontos_fortes,
            fragilidades,
            oportunidades,
        ),
    )

    resultado = cur.fetchone()
    if not resultado:
        return None

    id_avaliacao = resultado[0]
    criterios_inseridos = _inserir_criterio(cur, id_avaliacao, criterios)
    if not criterios_inseridos:
        return None

    return id_avaliacao


def _inserir_criterio(
    cur: psycopg.Cursor,
    id_avaliacao: int,
    criterios: list,
) -> bool:
    for criterio in criterios:
        cur.execute(
            """
            INSERT INTO avaliacao_criterio (
                id_avaliacao,
                criterio,
                nota_criterio,
                justificativa_criterio
            )
            VALUES (%s, %s, %s, %s)
            """,
            (
                id_avaliacao,
                criterio["criterio"],
                criterio["nota_criterio"],
                criterio["justificativa_criterio"]
            )
        )
    return True
