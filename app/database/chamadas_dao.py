# -*- coding: utf-8 -*-
"""
Acesso a dados (INSERTs/SELECTs/UPDATEs) das tabelas `chamadas`, `registro_chamadas`,
`empresa`, `avaliacao_ia` e `avaliacao_criterio`.
Mantém todo SQL e mapeamento relacional isolado na camada de persistência (`app/database/`).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import psycopg


# ----------------------------
# Consultas
# ----------------------------

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
    telefone: str | None = None,
) -> int | None:
    """Insere ou busca empresa existente, usando o telefone como âncora principal.

    Estratégia em camadas:
    1. Âncora por Telefone: se 'telefone' for fornecido, busca na tabela empresa.
       - Se já existir, reaproveita o id_empresa (evitando duplicar 'Abima' e 'Abima calçados').
       - Se o nome atual for mais rico/completo que o anterior (ou se o anterior era 'Não encontrado'),
         atualiza o nome e fonte_dados da empresa.
    2. Busca por Nome: se não achou por telefone (ou telefone ausente) e o nome for identificado,
       busca por LOWER(nome). Se encontrar, preenche o telefone se estiver vazio.
    3. Inserção: se for um novo cadastro (ou se o nome for 'Não encontrado' sem telefone pré-existente),
       insere novo registro e retorna o id_empresa gerado.
    """
    nome_limpo = (nome or "").strip()[:100]
    if not nome_limpo:
        nome_limpo = "Não encontrado"

    tel_limpo = (telefone or "").strip()[:20] if telefone else None
    eh_nao_encontrado = nome_limpo.lower() in ("não encontrado", "nao encontrado")

    # 1. Âncora por Telefone (Regra de Ouro)
    if tel_limpo:
        cur.execute(
            """
            SELECT id_empresa, nome, fonte_dados 
            FROM empresa 
            WHERE telefone = %s 
            LIMIT 1;
            """,
            (tel_limpo,),
        )
        row = cur.fetchone()
        if row:
            id_existente, nome_existente, fonte_existente = row[0], row[1], row[2]

            # Enriquecimento inteligente do nome:
            deve_atualizar_nome = False
            if not eh_nao_encontrado:
                if (nome_existente or "").strip().lower() in ("não encontrado", "nao encontrado"):
                    deve_atualizar_nome = True
                elif len(nome_limpo) > len((nome_existente or "").strip()):
                    deve_atualizar_nome = True

            deve_atualizar_fonte = (
                bool(fonte_dados and fonte_dados.strip())
                and not bool(fonte_existente and fonte_existente.strip())
            )

            if deve_atualizar_nome and deve_atualizar_fonte:
                cur.execute(
                    "UPDATE empresa SET nome = %s, fonte_dados = %s WHERE id_empresa = %s;",
                    (nome_limpo, fonte_dados, id_existente),
                )
            elif deve_atualizar_nome:
                cur.execute(
                    "UPDATE empresa SET nome = %s WHERE id_empresa = %s;",
                    (nome_limpo, id_existente),
                )
            elif deve_atualizar_fonte:
                cur.execute(
                    "UPDATE empresa SET fonte_dados = %s WHERE id_empresa = %s;",
                    (fonte_dados, id_existente),
                )

            return id_existente

    # 2. Busca secundária por Nome (apenas se for empresa identificada)
    if not eh_nao_encontrado:
        cur.execute(
            """
            SELECT id_empresa, telefone, fonte_dados 
            FROM empresa 
            WHERE LOWER(nome) = LOWER(%s) 
            LIMIT 1;
            """,
            (nome_limpo,),
        )
        row = cur.fetchone()
        if row:
            id_existente, tel_existente, fonte_existente = row[0], row[1], row[2]

            deve_atualizar_tel = bool(tel_limpo and not (tel_existente and tel_existente.strip()))
            deve_atualizar_fonte = bool(
                fonte_dados and fonte_dados.strip() and not (fonte_existente and fonte_existente.strip())
            )

            if deve_atualizar_tel and deve_atualizar_fonte:
                cur.execute(
                    "UPDATE empresa SET telefone = %s, fonte_dados = %s WHERE id_empresa = %s;",
                    (tel_limpo, fonte_dados, id_existente),
                )
            elif deve_atualizar_tel:
                cur.execute(
                    "UPDATE empresa SET telefone = %s WHERE id_empresa = %s;",
                    (tel_limpo, id_existente),
                )
            elif deve_atualizar_fonte:
                cur.execute(
                    "UPDATE empresa SET fonte_dados = %s WHERE id_empresa = %s;",
                    (fonte_dados, id_existente),
                )

            return id_existente

    # 3. Novo Cadastro
    cur.execute(
        """
        INSERT INTO empresa (nome, telefone, fonte_dados)
        VALUES (%s, %s, %s)
        RETURNING id_empresa;
        """,
        (nome_limpo, tel_limpo, fonte_dados),
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
    """Insere a revisão e opcionalmente o id_empresa em registro_chamadas."""
    if id_empresa is not None:
        cur.execute(
            """
            UPDATE registro_chamadas
            SET revisao = %s,
                id_empresa = %s
            WHERE log = %s
            RETURNING revisao;
            """,
            (revisao, id_empresa, log),
        )
    else:
        cur.execute(
            """
            UPDATE registro_chamadas
            SET revisao = %s
            WHERE log = %s
            RETURNING revisao;
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
        SELECT 1
        FROM avaliacao_ia
        WHERE log = %s
        LIMIT 1
        """,
        (log,)
    )
    resultado = cur.fetchone()
    return resultado is not None


def inserir_analise(
    cur: psycopg.Cursor,
    log: str,
    analise: dict[str, Any],
) -> str | None:
    """
    Persiste a análise comercial completa nas 7 tabelas normalizadas
    dentro da transação ativa do cursor.
    """
    av_ia = analise.get("avaliacao_ia", {})
    av_sdr = analise.get("avaliacao_sdr", {})
    av_criterios = analise.get("avaliacao_criterio", [])
    spin = analise.get("analise_spin", {})
    bant = analise.get("analise_bant", {})
    interlocutor = analise.get("interlocutor", {})
    crm = analise.get("crm", {})

    # Data da avaliação
    dt_av_str = av_ia.get("data_avaliacao")
    dt_av: date
    if dt_av_str:
        try:
            dt_av = datetime.strptime(str(dt_av_str)[:10], "%Y-%m-%d").date()
        except Exception:
            dt_av = date.today()
    else:
        dt_av = date.today()

    # Validação segura de empresa_contatada contra FK
    empresa_id = av_ia.get("empresa_contatada")
    if empresa_id:
        try:
            empresa_id = int(empresa_id)
            cur.execute("SELECT 1 FROM empresa WHERE id_empresa = %s LIMIT 1;", (empresa_id,))
            if not cur.fetchone():
                empresa_id = None
        except Exception:
            empresa_id = None

    lig_rel = "s" if str(av_ia.get("ligacao_relevante", "n")).lower() == "s" else "n"
    reun_conf = "s" if str(av_ia.get("reuniao_confirmada", "n")).lower() == "s" else "n"
    data_conf = "s" if str(av_ia.get("data_confirmada", "n")).lower() == "s" else "n"

    # 1. Inserir / Atualizar avaliacao_ia
    cur.execute(
        """
        INSERT INTO avaliacao_ia (
            log, data_avaliacao, modelo_ia, interlocutor, cargo,
            empresa_contatada, resultado, ligacao_relevante,
            reuniao_confirmada, data_confirmada, resultado_frase
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (log) DO UPDATE SET
            data_avaliacao = EXCLUDED.data_avaliacao,
            modelo_ia = EXCLUDED.modelo_ia,
            interlocutor = EXCLUDED.interlocutor,
            cargo = EXCLUDED.cargo,
            empresa_contatada = EXCLUDED.empresa_contatada,
            resultado = EXCLUDED.resultado,
            ligacao_relevante = EXCLUDED.ligacao_relevante,
            reuniao_confirmada = EXCLUDED.reuniao_confirmada,
            data_confirmada = EXCLUDED.data_confirmada,
            resultado_frase = EXCLUDED.resultado_frase
        RETURNING log;
        """,
        (
            log,
            dt_av,
            str(av_ia.get("modelo_ia", "gpt-4o-mini"))[:50],
            (av_ia.get("interlocutor") or None)[:100] if av_ia.get("interlocutor") else None,
            (av_ia.get("cargo") or None)[:100] if av_ia.get("cargo") else None,
            empresa_id,
            (av_ia.get("resultado") or None)[:255] if av_ia.get("resultado") else None,
            lig_rel,
            reun_conf,
            data_conf,
            str(av_ia.get("resultado_frase", "")),
        ),
    )
    if not cur.fetchone():
        return None

    # 2. Inserir / Atualizar avaliacao_sdr
    cod_op = av_sdr.get("codigo_oportunidade")
    if cod_op:
        cur.execute("SELECT 1 FROM dim_oportunidade_treinamento WHERE codigo = %s LIMIT 1;", (cod_op,))
        if not cur.fetchone():
            cod_op = None

    frase_alt = str(av_sdr.get("frase_alternativa", ""))[:500] if av_sdr.get("frase_alternativa") else None

    cur.execute(
        """
        INSERT INTO avaliacao_sdr (
            log, nota_final, feedback_geral, acertos, melhorias,
            frase_alternativa, codigo_oportunidade
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (log) DO UPDATE SET
            nota_final = EXCLUDED.nota_final,
            feedback_geral = EXCLUDED.feedback_geral,
            acertos = EXCLUDED.acertos,
            melhorias = EXCLUDED.melhorias,
            frase_alternativa = EXCLUDED.frase_alternativa,
            codigo_oportunidade = EXCLUDED.codigo_oportunidade;
        """,
        (
            log,
            av_sdr.get("nota_final"),
            str(av_sdr.get("feedback_geral", "")),
            str(av_sdr.get("acertos", "")) or None,
            str(av_sdr.get("melhorias", "")) or None,
            frase_alt,
            cod_op,
        ),
    )

    # 3. Inserir avaliacao_criterio
    cur.execute("DELETE FROM avaliacao_criterio WHERE log = %s;", (log,))
    for crit in av_criterios:
        cod_crit = crit.get("codigo_criterio")
        if not cod_crit:
            continue
        cur.execute("SELECT 1 FROM dim_criterio_avaliacao WHERE codigo = %s LIMIT 1;", (cod_crit,))
        if not cur.fetchone():
            continue

        cur.execute(
            """
            INSERT INTO avaliacao_criterio (
                log, criterio, nota_criterio, justificativa_criterio, codigo_criterio
            )
            VALUES (%s, %s, %s, %s, %s);
            """,
            (
                log,
                str(crit.get("criterio", ""))[:100],
                crit.get("nota_criterio"),
                str(crit.get("justificativa_criterio", "")),
                cod_crit,
            ),
        )

    # 4. Inserir / Atualizar analise_spin
    cur.execute(
        """
        INSERT INTO analise_spin (
            log, situacao, problema, implicacao, necessidade_solucao, evidencias, lacunas
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (log) DO UPDATE SET
            situacao = EXCLUDED.situacao,
            problema = EXCLUDED.problema,
            implicacao = EXCLUDED.implicacao,
            necessidade_solucao = EXCLUDED.necessidade_solucao,
            evidencias = EXCLUDED.evidencias,
            lacunas = EXCLUDED.lacunas;
        """,
        (
            log,
            spin.get("situacao"),
            spin.get("problema"),
            spin.get("implicacao"),
            spin.get("necessidade_solucao"),
            spin.get("evidencias"),
            spin.get("lacunas"),
        ),
    )

    # 5. Inserir / Atualizar analise_bant
    cur.execute(
        """
        INSERT INTO analise_bant (
            log, budget_classificacao, budget_evidencia, authority_classificacao, authority_evidencia,
            need_classificacao, need_evidencia, timeline_classificacao, timeline_evidencia
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (log) DO UPDATE SET
            budget_classificacao = EXCLUDED.budget_classificacao,
            budget_evidencia = EXCLUDED.budget_evidencia,
            authority_classificacao = EXCLUDED.authority_classificacao,
            authority_evidencia = EXCLUDED.authority_evidencia,
            need_classificacao = EXCLUDED.need_classificacao,
            need_evidencia = EXCLUDED.need_evidencia,
            timeline_classificacao = EXCLUDED.timeline_classificacao,
            timeline_evidencia = EXCLUDED.timeline_evidencia;
        """,
        (
            log,
            (bant.get("budget_classificacao") or None)[:50] if bant.get("budget_classificacao") else None,
            bant.get("budget_evidencia"),
            (bant.get("authority_classificacao") or None)[:50] if bant.get("authority_classificacao") else None,
            bant.get("authority_evidencia"),
            (bant.get("need_classificacao") or None)[:50] if bant.get("need_classificacao") else None,
            bant.get("need_evidencia"),
            (bant.get("timeline_classificacao") or None)[:50] if bant.get("timeline_classificacao") else None,
            bant.get("timeline_evidencia"),
        ),
    )

    # 6. Inserir / Atualizar interlocutor
    cur.execute(
        """
        INSERT INTO interlocutor (
            log, interesse_expresso, duvidas, objecoes, resposta_sdr, reacao_interlocutor
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (log) DO UPDATE SET
            interesse_expresso = EXCLUDED.interesse_expresso,
            duvidas = EXCLUDED.duvidas,
            objecoes = EXCLUDED.objecoes,
            resposta_sdr = EXCLUDED.resposta_sdr,
            reacao_interlocutor = EXCLUDED.reacao_interlocutor;
        """,
        (
            log,
            interlocutor.get("interesse_expresso"),
            interlocutor.get("duvidas"),
            interlocutor.get("objecoes"),
            interlocutor.get("resposta_sdr"),
            interlocutor.get("reacao_interlocutor"),
        ),
    )

    # 7. Inserir / Atualizar crm
    cur.execute(
        """
        INSERT INTO crm (
            log, acao, responsavel, prazo, dados_extras, resumo
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (log) DO UPDATE SET
            acao = EXCLUDED.acao,
            responsavel = EXCLUDED.responsavel,
            prazo = EXCLUDED.prazo,
            dados_extras = EXCLUDED.dados_extras,
            resumo = EXCLUDED.resumo;
        """,
        (
            log,
            (crm.get("acao") or None)[:255] if crm.get("acao") else None,
            (crm.get("responsavel") or None)[:100] if crm.get("responsavel") else None,
            (crm.get("prazo") or None)[:100] if crm.get("prazo") else None,
            crm.get("dados_extras"),
            crm.get("resumo"),
        ),
    )

    # 8. Enriquecer status_comercial na tabela empresa caso exista
    resultado_comercial = av_ia.get("resultado")
    if empresa_id and resultado_comercial:
        cur.execute(
            """
            UPDATE empresa
            SET status_comercial = %s
            WHERE id_empresa = %s;
            """,
            (str(resultado_comercial)[:100], empresa_id),
        )

    return log
