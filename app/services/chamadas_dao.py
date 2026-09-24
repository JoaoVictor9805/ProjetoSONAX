# -*- coding: utf-8 -*-
"""
Acesso a dados (INSERTs/SELECTs) das tabelas `origem` e `registro_chamadas`.
Mantém todo SQL isolado do resto do script.
"""

from datetime import date, datetime


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
        ON CONFLICT (log) DO NOTHING
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

def buscar_revisao(
    cur: psycopg.Cursor,
    log: str
) -> str | None:
    """ Busca a revisão na coluna revisao do banco de dados """
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

    if not resultado:
        return False

    return True


def garantir_schema_atualizado(cur: psycopg.Cursor) -> None:
    """Garante que as colunas e tabelas das avaliações Micro e Macro existam no banco."""
    cur.execute(
        """
        ALTER TABLE avaliacao_ia ALTER COLUMN nota_final DROP NOT NULL;
        ALTER TABLE avaliacao_criterio ALTER COLUMN nota_criterio DROP NOT NULL;

        ALTER TABLE avaliacao_ia 
        ADD COLUMN IF NOT EXISTS titulo VARCHAR(255),
        ADD COLUMN IF NOT EXISTS resumo_chamada TEXT,
        ADD COLUMN IF NOT EXISTS pontos_fortes TEXT,
        ADD COLUMN IF NOT EXISTS fragilidades TEXT,
        ADD COLUMN IF NOT EXISTS oportunidades TEXT;

        CREATE TABLE IF NOT EXISTS perfil_agente (
            id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            agente_nome VARCHAR(100) NOT NULL REFERENCES origem(agente_nome),
            mes_referencia DATE NOT NULL,
            total_chamadas_mes INT NOT NULL DEFAULT 0,
            nota_media_mes NUMERIC(4,2),
            resumo_evolutivo TEXT,
            principais_pontos_fortes TEXT,
            principais_fragilidades TEXT,
            plano_acao_oportunidades TEXT,
            data_processamento TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uk_perfil_agente_mes UNIQUE (agente_nome, mes_referencia)
        );

        ALTER TABLE perfil_agente
        ADD COLUMN IF NOT EXISTS principais_pontos_fortes TEXT;

        ALTER TABLE perfil_agente ALTER COLUMN nota_media_mes DROP NOT NULL;
        ALTER TABLE perfil_agente ALTER COLUMN resumo_evolutivo DROP NOT NULL;
        ALTER TABLE perfil_agente ALTER COLUMN principais_pontos_fortes DROP NOT NULL;
        ALTER TABLE perfil_agente ALTER COLUMN principais_fragilidades DROP NOT NULL;
        ALTER TABLE perfil_agente ALTER COLUMN plano_acao_oportunidades DROP NOT NULL;
        ALTER TABLE avaliacao_criterio ALTER COLUMN justificativa_criterio DROP NOT NULL;
        """
    )
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = 'perfil_agente' AND column_name IN ('ciclo_inicio', 'ciclo_fim', 'total_chamadas_ciclo', 'nota_media_ciclo');
        """
    )
    cols = [r[0] for r in cur.fetchall()]
    if "ciclo_inicio" in cols:
        cur.execute("ALTER TABLE perfil_agente RENAME COLUMN ciclo_inicio TO mes_referencia;")
    if "ciclo_fim" in cols:
        cur.execute("ALTER TABLE perfil_agente DROP COLUMN ciclo_fim;")
    if "total_chamadas_ciclo" in cols:
        cur.execute("ALTER TABLE perfil_agente RENAME COLUMN total_chamadas_ciclo TO total_chamadas_mes;")
    if "nota_media_ciclo" in cols:
        cur.execute("ALTER TABLE perfil_agente RENAME COLUMN nota_media_ciclo TO nota_media_mes;")
    cur.execute("ALTER TABLE perfil_agente DROP CONSTRAINT IF EXISTS uk_perfil_agente_ciclo;")
    cur.execute("SELECT 1 FROM pg_constraint WHERE conname = 'uk_perfil_agente_mes';")
    if not cur.fetchone():
        cur.execute("ALTER TABLE perfil_agente ADD CONSTRAINT uk_perfil_agente_mes UNIQUE (agente_nome, mes_referencia);")


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
) -> int | None:
    garantir_schema_atualizado(cur)

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
            "Revisão: gemini-3.1-flash-lite | Análise: gemini-3.5-flash-lite",
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