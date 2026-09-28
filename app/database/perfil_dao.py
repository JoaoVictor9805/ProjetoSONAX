# -*- coding: utf-8 -*-
"""
============================================================================
Data Access Object (DAO) para o Fechamento Mensal e Perfil de Agentes.
============================================================================

Responsabilidades:
    1. Consultas de agregação de desempenho e métricas PEAH no ciclo mensal.
    2. Seleção de amostras extremas de chamadas (menores e maiores notas).
    3. Verificação de existência e persistência na tabela `perfil_agente`.
============================================================================
"""
from __future__ import annotations

from datetime import date
from typing import Any

import psycopg


def buscar_agentes_no_ciclo(
    cur: psycopg.Cursor,
    inicio: date,
    fim: date,
) -> list[str]:
    """Lista todos os atendentes que possuem chamadas avaliadas dentro do ciclo."""
    cur.execute(
        """
        SELECT DISTINCT r.agente_nome
        FROM registro_chamadas r
        INNER JOIN avaliacao_ia a ON r.log = a.registro_chamadas_log
        WHERE r.data_ligacao >= %s AND r.data_ligacao < (%s::date + INTERVAL '1 day')
        ORDER BY r.agente_nome;
        """,
        (inicio, fim),
    )
    return [row[0] for row in cur.fetchall()]


def obter_estatisticas_agente(
    cur: psycopg.Cursor,
    agente_nome: str,
    inicio: date,
    fim: date,
) -> dict[str, Any]:
    """Calcula total de chamadas, nota média geral e médias por critério PEAH."""
    # Total de chamadas, nota média geral e total de chamadas válidas com nota
    cur.execute(
        """
        SELECT 
            COUNT(DISTINCT a.id_avaliacao) as total_chamadas,
            ROUND(AVG(a.nota_final::numeric), 2) as nota_media,
            COUNT(DISTINCT CASE WHEN a.nota_final IS NOT NULL THEN a.id_avaliacao END) as chamadas_validas
        FROM avaliacao_ia a
        INNER JOIN registro_chamadas r ON a.registro_chamadas_log = r.log
        WHERE r.agente_nome = %s
          AND r.data_ligacao >= %s AND r.data_ligacao < (%s::date + INTERVAL '1 day');
        """,
        (agente_nome, inicio, fim),
    )
    res_geral = cur.fetchone()
    total_chamadas = res_geral[0] if res_geral else 0
    nota_media = float(res_geral[1]) if res_geral and res_geral[1] is not None else None
    chamadas_validas = res_geral[2] if res_geral and len(res_geral) > 2 else 0

    # Médias dos critérios PEAH
    cur.execute(
        """
        SELECT 
            c.criterio,
            ROUND(AVG(c.nota_criterio::numeric), 2) as media
        FROM avaliacao_criterio c
        INNER JOIN avaliacao_ia a ON c.id_avaliacao = a.id_avaliacao
        INNER JOIN registro_chamadas r ON a.registro_chamadas_log = r.log
        WHERE r.agente_nome = %s
          AND r.data_ligacao >= %s AND r.data_ligacao < (%s::date + INTERVAL '1 day')
          AND c.nota_criterio IS NOT NULL
        GROUP BY c.criterio
        ORDER BY c.criterio;
        """,
        (agente_nome, inicio, fim),
    )
    medias_criterios = {row[0]: float(row[1]) for row in cur.fetchall()}

    return {
        "total_chamadas": total_chamadas,
        "nota_media": nota_media,
        "chamadas_validas": chamadas_validas,
        "medias_criterios": medias_criterios,
    }


def obter_amostras_extremos(
    cur: psycopg.Cursor,
    agente_nome: str,
    inicio: date,
    fim: date,
    limite: int = 15,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Coleta as até `limite` chamadas com menor nota e as até `limite` chamadas com maior nota."""
    # Menores notas
    cur.execute(
        """
        SELECT a.nota_final, a.titulo, a.resumo_chamada, a.pontos_fortes, a.fragilidades, a.oportunidades
        FROM avaliacao_ia a
        INNER JOIN registro_chamadas r ON a.registro_chamadas_log = r.log
        WHERE r.agente_nome = %s
          AND r.data_ligacao >= %s AND r.data_ligacao < (%s::date + INTERVAL '1 day')
          AND a.nota_final IS NOT NULL
          AND (a.fragilidades IS NOT NULL OR a.oportunidades IS NOT NULL OR a.pontos_fortes IS NOT NULL)
        ORDER BY a.nota_final::numeric ASC
        LIMIT %s;
        """,
        (agente_nome, inicio, fim, limite),
    )
    menores = [
        {
            "nota": row[0],
            "titulo": row[1] or "Sem título",
            "resumo": row[2] or "Sem resumo",
            "pontos_fortes": row[3] or "Nenhum informado",
            "fragilidades": row[4] or "Nenhuma informada",
            "oportunidades": row[5] or "Nenhuma informada",
        }
        for row in cur.fetchall()
    ]

    # Maiores notas
    cur.execute(
        """
        SELECT a.nota_final, a.titulo, a.resumo_chamada, a.pontos_fortes, a.fragilidades, a.oportunidades
        FROM avaliacao_ia a
        INNER JOIN registro_chamadas r ON a.registro_chamadas_log = r.log
        WHERE r.agente_nome = %s
          AND r.data_ligacao >= %s AND r.data_ligacao < (%s::date + INTERVAL '1 day')
          AND a.nota_final IS NOT NULL
          AND (a.pontos_fortes IS NOT NULL OR a.fragilidades IS NOT NULL OR a.oportunidades IS NOT NULL)
        ORDER BY a.nota_final::numeric DESC
        LIMIT %s;
        """,
        (agente_nome, inicio, fim, limite),
    )
    maiores = [
        {
            "nota": row[0],
            "titulo": row[1] or "Sem título",
            "resumo": row[2] or "Sem resumo",
            "pontos_fortes": row[3] or "Nenhum informado",
            "fragilidades": row[4] or "Nenhuma informada",
            "oportunidades": row[5] or "Nenhuma informada",
        }
        for row in cur.fetchall()
    ]

    return menores, maiores


def perfil_ja_existe(
    cur: psycopg.Cursor,
    agente_nome: str,
    mes_referencia: date,
) -> bool:
    """Verifica se já existe fechamento registrado para este atendente no mês de referência."""
    cur.execute(
        """
        SELECT 1 FROM perfil_agente
        WHERE agente_nome = %s AND mes_referencia = %s
        LIMIT 1;
        """,
        (agente_nome, mes_referencia),
    )
    return cur.fetchone() is not None


def gravar_perfil_agente(
    cur: psycopg.Cursor,
    agente_nome: str,
    mes_referencia: date,
    total_chamadas_mes: int,
    nota_media_mes: float | None,
    resumo_evolutivo: str,
    principais_pontos_fortes: str | None,
    principais_fragilidades: str | None,
    plano_acao_oportunidades: str | None,
) -> int | None:
    """Insere ou atualiza o fechamento mensal na tabela `perfil_agente`."""
    cur.execute(
        """
        INSERT INTO perfil_agente (
            agente_nome,
            mes_referencia,
            total_chamadas_mes,
            nota_media_mes,
            resumo_evolutivo,
            principais_pontos_fortes,
            principais_fragilidades,
            plano_acao_oportunidades,
            data_processamento
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (agente_nome, mes_referencia)
        DO UPDATE SET
            total_chamadas_mes = EXCLUDED.total_chamadas_mes,
            nota_media_mes = EXCLUDED.nota_media_mes,
            resumo_evolutivo = EXCLUDED.resumo_evolutivo,
            principais_pontos_fortes = EXCLUDED.principais_pontos_fortes,
            principais_fragilidades = EXCLUDED.principais_fragilidades,
            plano_acao_oportunidades = EXCLUDED.plano_acao_oportunidades,
            data_processamento = CURRENT_TIMESTAMP
        RETURNING id;
        """,
        (
            agente_nome,
            mes_referencia,
            total_chamadas_mes,
            nota_media_mes,
            resumo_evolutivo,
            principais_pontos_fortes,
            principais_fragilidades,
            plano_acao_oportunidades,
        ),
    )
    res = cur.fetchone()
    return res[0] if res else None
