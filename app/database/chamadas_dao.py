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
        SELECT protocolo, ramal, agente_nome, numero, estado_ddd, identificacao_cliente 
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
        "identificacao_cliente": row[5] if len(row) > 5 else None,
    }


def buscar_identificacao_cliente(
    cur: psycopg.Cursor,
    log_arquivo: str | None = None,
    protocolo: int | None = None,
) -> str | None:
    """Busca identificacao_cliente na tabela chamadas através do protocolo ou do log de gravação."""
    if protocolo:
        cur.execute(
            "SELECT identificacao_cliente FROM chamadas WHERE protocolo = %s LIMIT 1;",
            (protocolo,),
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            return str(row[0]).strip()
    if log_arquivo:
        cur.execute(
            """
            SELECT c.identificacao_cliente
            FROM registro_chamadas r
            JOIN chamadas c ON r.protocolo = c.protocolo
            WHERE r.log = %s
            LIMIT 1;
            """,
            (log_arquivo,),
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            return str(row[0]).strip()
    return None


_SCHEMA_EMPRESA_GARANTIDO = False


def garantir_schema_empresa(cur: psycopg.Cursor) -> None:
    """Garante que a tabela empresa contenha a coluna telefone, índice e remova a restrição UNIQUE em nome."""
    global _SCHEMA_EMPRESA_GARANTIDO
    if _SCHEMA_EMPRESA_GARANTIDO:
        return
    try:
        cur.execute(
            """
            ALTER TABLE empresa ADD COLUMN IF NOT EXISTS telefone VARCHAR(20);
            CREATE INDEX IF NOT EXISTS empresa_telefone ON empresa(telefone);
            ALTER TABLE empresa DROP CONSTRAINT IF EXISTS empresa_nome_key;
            """
        )
        _SCHEMA_EMPRESA_GARANTIDO = True
    except Exception:
        pass


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
    garantir_schema_empresa(cur)
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


def garantir_schema_avaliacao(cur: psycopg.Cursor | None = None) -> None:
    """Deprecated: DDL e sementes dimensionais residem estritamente nas migrações SQL."""
    pass


def derivar_status_consolidado_empresa(
    cur: psycopg.Cursor,
    empresa_id: int,
    *,
    resultado_ligacao: str | None = None,
    regime: str | None = None,
    orig_regime: str | None = None,
    fat_mensal: float | None = None,
    orig_fat: str | None = None,
    status_atual: str | None = None,
    persistir: bool = True,
) -> str | None:
    """
    Avalia os dados consolidados da empresa no banco e calcula o status_comercial resultante:
    - 'Perfil confirmado': Lucro Real (confirmado pelo interlocutor) E faturamento mensal >= R$ 1 milhão (confirmado pelo interlocutor).
    - 'Fora do perfil desta campanha': outro regime confirmado (Simples, Presumido, MEI) OU faturamento < 1M (confirmado pelo interlocutor).
    - 'Perfil pendente': empresa possui algum contato/dado, mas falta confirmar regime ou faturamento.
    - 'Dados insuficientes': sem dados cadastrais mínimos.
    """
    if regime is None and orig_regime is None and fat_mensal is None and status_atual is None:
        cur.execute(
            """
            SELECT regime_tributario, regime_origem, faturamento_mensal, faturamento_origem, status_comercial
            FROM empresa
            WHERE id_empresa = %s
            LIMIT 1;
            """,
            (empresa_id,),
        )
        row = cur.fetchone()
        if not row or len(row) < 5:
            return None

        regime, orig_regime, fat_mensal, orig_fat, status_atual = row

    regime_str = (regime or "").strip().lower()
    regime_conf = orig_regime == "confirmado pelo interlocutor"
    eh_lucro_real = "lucro real" in regime_str
    outro_regime_conf = regime_conf and not eh_lucro_real and any(r in regime_str for r in ("simples", "presumido", "mei"))

    try:
        fat_val = float(fat_mensal) if fat_mensal is not None else None
    except (ValueError, TypeError):
        fat_val = None

    fat_conf = orig_fat == "confirmado pelo interlocutor"
    fat_minimo_ok = fat_val is not None and fat_val >= 1000000.0
    fat_abaixo_conf = fat_conf and fat_val is not None and fat_val < 1000000.0

    if outro_regime_conf or fat_abaixo_conf:
        novo_status = "Fora do perfil desta campanha"
    elif eh_lucro_real and regime_conf and fat_minimo_ok and fat_conf:
        novo_status = "Perfil confirmado"
    elif resultado_ligacao in ("Perfil confirmado", "Fora do perfil desta campanha", "Perfil pendente"):
        novo_status = resultado_ligacao
    elif regime or fat_val is not None or status_atual in ("Perfil pendente", "Perfil confirmado"):
        novo_status = "Perfil pendente"
    else:
        novo_status = status_atual or resultado_ligacao or "Dados insuficientes"

    pesos_status = {
        "Perfil confirmado": 3,
        "Fora do perfil desta campanha": 3,
        "Perfil pendente": 2,
        "Dados insuficientes": 1,
    }
    peso_novo = pesos_status.get(novo_status, 1)
    peso_atual = pesos_status.get(status_atual, 0) if status_atual else 0

    status_final = novo_status if (peso_novo >= peso_atual or status_atual is None) else status_atual

    if persistir and status_final != status_atual and (peso_novo >= peso_atual or status_atual is None):
        cur.execute(
            "UPDATE empresa SET status_comercial = %s WHERE id_empresa = %s;",
            (status_final, empresa_id),
        )

    return status_final


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

    # Trava defensiva do motor de banco: força NULL em notas se chamada for não avaliável
    fb_geral_lower = str(av_sdr.get("feedback_geral") or "").lower()
    eh_nao_avaliavel_dao = (
        av_ia.get("ligacao_relevante") == "n"
        or fb_geral_lower.startswith("não avaliável")
        or fb_geral_lower.startswith("nao avaliavel")
        or "não avaliável" in fb_geral_lower
        or "nao avaliavel" in fb_geral_lower
    )
    if eh_nao_avaliavel_dao:
        av_sdr["nota_final"] = None
        av_sdr["codigos_oportunidade"] = []
        av_sdr["codigo_oportunidade"] = None
        for crit in av_criterios:
            crit["nota_criterio"] = None


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
    conv_dec = "s" if str(av_ia.get("conversa_decisor", "n")).lower() == "s" else "n"

    # 1. Inserir / Atualizar avaliacao_ia
    cur.execute(
        """
        INSERT INTO avaliacao_ia (
            log, data_avaliacao, modelo_ia, interlocutor, cargo,
            empresa_contatada, resultado, ligacao_relevante,
            reuniao_confirmada, data_confirmada, conversa_decisor, resultado_frase
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            conversa_decisor = EXCLUDED.conversa_decisor,
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
            conv_dec,
            str(av_ia.get("resultado_frase", "")),
        ),
    )
    if not cur.fetchone():
        return None

    # 2. Inserir / Atualizar avaliacao_sdr
    frase_alt = str(av_sdr.get("frase_alternativa", ""))[:500] if av_sdr.get("frase_alternativa") else None

    cur.execute(
        """
        INSERT INTO avaliacao_sdr (
            log, nota_final, feedback_geral, acertos, melhorias,
            frase_alternativa
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (log) DO UPDATE SET
            nota_final = EXCLUDED.nota_final,
            feedback_geral = EXCLUDED.feedback_geral,
            acertos = EXCLUDED.acertos,
            melhorias = EXCLUDED.melhorias,
            frase_alternativa = EXCLUDED.frase_alternativa;
        """,
        (
            log,
            av_sdr.get("nota_final"),
            str(av_sdr.get("feedback_geral", "")),
            str(av_sdr.get("acertos", "")) or None,
            str(av_sdr.get("melhorias", "")) or None,
            frase_alt,
        ),
    )

    # 2.1 Inserir avaliacao_oportunidade_treinamento (N:N)
    cur.execute("DELETE FROM avaliacao_oportunidade_treinamento WHERE log = %s;", (log,))
    codigos_op = av_sdr.get("codigos_oportunidade")
    if not codigos_op and av_sdr.get("codigo_oportunidade"):
        codigos_op = [av_sdr.get("codigo_oportunidade")]
    if isinstance(codigos_op, list):
        for cod_op in codigos_op:
            if not cod_op:
                continue
            cur.execute("SELECT 1 FROM dim_oportunidade_treinamento WHERE codigo = %s LIMIT 1;", (cod_op,))
            if not cur.fetchone():
                continue
            cur.execute(
                """
                INSERT INTO avaliacao_oportunidade_treinamento (
                    log, codigo_oportunidade
                )
                VALUES (%s, %s)
                ON CONFLICT (log, codigo_oportunidade) DO NOTHING;
                """,
                (log, cod_op),
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
            log, situacao, situacao_investigada, problema, problema_investigado,
            implicacao, implicacao_investigada, necessidade_solucao, necessidade_investigada,
            evidencias, lacunas
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (log) DO UPDATE SET
            situacao = EXCLUDED.situacao,
            situacao_investigada = EXCLUDED.situacao_investigada,
            problema = EXCLUDED.problema,
            problema_investigado = EXCLUDED.problema_investigado,
            implicacao = EXCLUDED.implicacao,
            implicacao_investigada = EXCLUDED.implicacao_investigada,
            necessidade_solucao = EXCLUDED.necessidade_solucao,
            necessidade_investigada = EXCLUDED.necessidade_investigada,
            evidencias = EXCLUDED.evidencias,
            lacunas = EXCLUDED.lacunas;
        """,
        (
            log,
            spin.get("situacao"),
            spin.get("situacao_investigada", "n"),
            spin.get("problema"),
            spin.get("problema_investigado", "n"),
            spin.get("implicacao"),
            spin.get("implicacao_investigada", "n"),
            spin.get("necessidade_solucao"),
            spin.get("necessidade_investigada", "n"),
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

    # 8. Inserir / Atualizar analise_perfil
    perfil = analise.get("analise_perfil", {})
    fat_anual = perfil.get("faturamento_anual")
    fat_mensal = perfil.get("faturamento_mensal")
    periodo = perfil.get("periodo_meses")

    cur.execute(
        """
        INSERT INTO analise_perfil (
            log, setor, setor_origem, regime_tributario, regime_origem,
            faturamento_declarado_texto, faturamento_anual, faturamento_mensal,
            periodo_meses, faturamento_origem, faturamento_regra, detalhes_faturamento
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (log) DO UPDATE SET
            setor = EXCLUDED.setor,
            setor_origem = EXCLUDED.setor_origem,
            regime_tributario = EXCLUDED.regime_tributario,
            regime_origem = EXCLUDED.regime_origem,
            faturamento_declarado_texto = EXCLUDED.faturamento_declarado_texto,
            faturamento_anual = EXCLUDED.faturamento_anual,
            faturamento_mensal = EXCLUDED.faturamento_mensal,
            periodo_meses = EXCLUDED.periodo_meses,
            faturamento_origem = EXCLUDED.faturamento_origem,
            faturamento_regra = EXCLUDED.faturamento_regra,
            detalhes_faturamento = EXCLUDED.detalhes_faturamento;
        """,
        (
            log,
            (perfil.get("setor") or "não informado")[:50],
            str(perfil.get("setor_origem") or "não informado")[:50],
            (perfil.get("regime_tributario") or None)[:50] if perfil.get("regime_tributario") and perfil.get("regime_tributario") != "Não se aplica" else None,
            str(perfil.get("regime_origem") or "não informado")[:50],
            perfil.get("faturamento_declarado_texto"),
            fat_anual,
            fat_mensal,
            periodo,
            str(perfil.get("faturamento_origem") or "não informado")[:50],
            str(perfil.get("faturamento_regra") or "nao_informado")[:50],
            perfil.get("detalhes_faturamento"),
        ),
    )

    # 9. Sincronização inteligente com a tabela empresa respeitando hierarquia de confiança
    resultado_comercial = av_ia.get("resultado")
    if empresa_id:
        pesos_origem = {
            "confirmado pelo interlocutor": 3,
            "afirmado apenas pelo SDR": 2,
            "inferência plausível": 1,
            "não informado": 0,
        }

        pesos_status = {
            "Perfil confirmado": 3,
            "Fora do perfil desta campanha": 3,
            "Perfil pendente": 2,
            "Dados insuficientes": 1,
        }

        # Busca dados, origens e status atuais da empresa
        cur.execute(
            """
            SELECT setor_origem, regime_origem, faturamento_origem, status_comercial, regime_tributario, faturamento_mensal
            FROM empresa
            WHERE id_empresa = %s
            LIMIT 1;
            """,
            (empresa_id,),
        )
        row_emp = cur.fetchone()
        orig_setor_atual = row_emp[0] if row_emp and len(row_emp) > 0 else None
        orig_regime_atual = row_emp[1] if row_emp and len(row_emp) > 1 else None
        orig_fat_atual = row_emp[2] if row_emp and len(row_emp) > 2 else None
        status_comercial_atual = row_emp[3] if row_emp and len(row_emp) > 3 else None
        regime_atual = row_emp[4] if row_emp and len(row_emp) > 4 else None
        fat_atual = row_emp[5] if row_emp and len(row_emp) > 5 else None

        nova_orig_setor = str(perfil.get("setor_origem") or "não informado")
        nova_orig_regime = str(perfil.get("regime_origem") or "não informado")
        nova_orig_fat = str(perfil.get("faturamento_origem") or "não informado")

        setor_val = perfil.get("setor") if perfil.get("setor") and perfil.get("setor") not in ("Não se aplica", "não informado") else None
        regime_val = perfil.get("regime_tributario") if perfil.get("regime_tributario") and perfil.get("regime_tributario") != "Não se aplica" else None

        deve_atualizar_setor = (
            setor_val is not None
            and pesos_origem.get(nova_orig_setor, 0) >= pesos_origem.get(orig_setor_atual, 0)
            and pesos_origem.get(nova_orig_setor, 0) > 0
        )
        deve_atualizar_regime = (
            regime_val is not None
            and pesos_origem.get(nova_orig_regime, 0) >= pesos_origem.get(orig_regime_atual, 0)
            and pesos_origem.get(nova_orig_regime, 0) > 0
        )
        deve_atualizar_fat = (
            (fat_mensal is not None or fat_anual is not None)
            and pesos_origem.get(nova_orig_fat, 0) >= pesos_origem.get(orig_fat_atual, 0)
            and pesos_origem.get(nova_orig_fat, 0) > 0
        )

        # Consolidação inteligente de status multichamadas via função canônica do DAO
        regime_final = regime_val if deve_atualizar_regime else regime_atual
        orig_regime_final = nova_orig_regime if deve_atualizar_regime else orig_regime_atual
        fat_final = fat_mensal if deve_atualizar_fat else fat_atual
        orig_fat_final = nova_orig_fat if deve_atualizar_fat else orig_fat_atual

        resultado_consolidado = derivar_status_consolidado_empresa(
            cur,
            empresa_id,
            resultado_ligacao=resultado_comercial,
            regime=regime_final,
            orig_regime=orig_regime_final,
            fat_mensal=fat_final,
            orig_fat=orig_fat_final,
            status_atual=status_comercial_atual,
            persistir=False,
        )

        peso_novo_status = pesos_status.get(str(resultado_consolidado), 0)
        peso_atual_status = pesos_status.get(str(status_comercial_atual), 0)
        deve_atualizar_status = (
            resultado_consolidado is not None
            and resultado_consolidado != status_comercial_atual
            and (status_comercial_atual is None or peso_novo_status >= peso_atual_status)
        )

        updates = []
        params = []
        if deve_atualizar_status:
            updates.append("status_comercial = %s")
            params.append(str(resultado_consolidado)[:100])
        if deve_atualizar_setor:
            updates.append("setor = %s, setor_origem = %s")
            params.extend([str(setor_val)[:100], nova_orig_setor[:50]])
        if deve_atualizar_regime:
            updates.append("regime_tributario = %s, regime_origem = %s")
            params.extend([str(regime_val)[:50], nova_orig_regime[:50]])
        if deve_atualizar_fat:
            updates.append("faturamento_mensal = %s, faturamento_anual = %s, faturamento_origem = %s")
            params.extend([fat_mensal, fat_anual, nova_orig_fat[:50]])

        if updates:
            params.append(empresa_id)
            cur.execute(
                f"UPDATE empresa SET {', '.join(updates)} WHERE id_empresa = %s;",
                tuple(params),
            )

    return log
