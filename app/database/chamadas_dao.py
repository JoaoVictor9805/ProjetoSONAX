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


_SCHEMA_AVALIACAO_GARANTIDO = False


def garantir_schema_avaliacao(cur: psycopg.Cursor) -> None:
    """Garante que as colunas das avaliações permitam NULL e que as tabelas de dimensões estejam populadas."""
    global _SCHEMA_AVALIACAO_GARANTIDO
    if _SCHEMA_AVALIACAO_GARANTIDO:
        return
    try:
        cur.execute(
            """
            ALTER TABLE avaliacao_sdr ALTER COLUMN nota_final DROP NOT NULL;
            ALTER TABLE avaliacao_sdr ALTER COLUMN codigo_oportunidade DROP NOT NULL;
            ALTER TABLE avaliacao_criterio ALTER COLUMN nota_criterio DROP NOT NULL;

            INSERT INTO dim_criterio_avaliacao (codigo, descricao) VALUES
            ('CRIT_ABERTURA', 'Abertura clara, motivo do contato e relevância para o interlocutor'),
            ('CRIT_SPIN', 'Descoberta SPIN: Situação, Problema, Implicação, Necessidade de solução'),
            ('CRIT_PERFIL', 'Investigação adequada do perfil: setor, regime tributário, faturamento'),
            ('CRIT_BANT', 'Investigação BANT: viabilidade comercial, autoridade, necessidade, prazo'),
            ('CRIT_ESCUTA', 'Escuta, aprofundamento e tratamento respeitoso de dúvidas ou objeções'),
            ('CRIT_PROX_PASSO', 'Proposta de próximo passo pertinente e tentativa de obter compromisso claro')
            ON CONFLICT (codigo) DO NOTHING;

            INSERT INTO dim_oportunidade_treinamento (codigo, fase_venda, descricao) VALUES
            ('OP_ABERT_01', '1. Abertura e Relevância', 'Apresentar-se e situar a empresa com objetividade'),
            ('OP_ABERT_02', '1. Abertura e Relevância', 'Utilizar a oportunidade de crédito mapeada como gancho'),
            ('OP_ABERT_03', '1. Abertura e Relevância', 'Expor o benefício da oportunidade sem sobrecarga técnica'),
            ('OP_ABERT_04', '1. Abertura e Relevância', 'Confirmar o alinhamento com o interlocutor antes de aprofundar'),
            ('OP_ABERT_05', '1. Abertura e Relevância', 'Direcionar o contato para o responsável fiscal, tributário ou financeiro'),
            ('OP_ABERT_06', '1. Abertura e Relevância', 'Evitar promessas de valores ou garantia de créditos'),
            ('OP_SPIN_01', '2. Descoberta SPIN', 'Mapear o cenário inicial com perguntas rápidas e indispensáveis'),
            ('OP_SPIN_02', '2. Descoberta SPIN', 'Mapear atritos fiscais ou lacunas na rotina da empresa'),
            ('OP_SPIN_03', '2. Descoberta SPIN', 'Destacar implicações simples e tangíveis (como a prescrição de créditos)'),
            ('OP_SPIN_04', '2. Descoberta SPIN', 'Conectar a solução à dor e checar a viabilidade de avanço'),
            ('OP_SPIN_05', '2. Descoberta SPIN', 'Diferenciar dor reconhecida pelo lead de argumentos do SDR'),
            ('OP_PERF_01', '3. Investigação de Perfil Técnico', 'Investigar o regime tributário da empresa'),
            ('OP_PERF_02', '3. Investigação de Perfil Técnico', 'Confirmar o faturamento mínimo'),
            ('OP_PERF_03', '3. Investigação de Perfil Técnico', 'Mapear o segmento de atuação'),
            ('OP_PERF_04', '3. Investigação de Perfil Técnico', 'Garantir a confirmação ativa dos dados'),
            ('OP_BANT_01', '4. Investigação BANT', 'Budget (Viabilidade Comercial): Avaliar viabilidade de contratação'),
            ('OP_BANT_02', '4. Investigação BANT', 'Authority (Autoridade): Avaliar papel do interlocutor'),
            ('OP_BANT_03', '4. Investigação BANT', 'Need (Necessidade): Estimular o lead a verbalizar dor real'),
            ('OP_BANT_04', '4. Investigação BANT', 'Timeline (Prazo): Mapear prioridade ou evento motivador'),
            ('OP_ESC_01', '5. Escuta e Objeções', 'Posicionar o trabalho como complementar à contabilidade atual'),
            ('OP_ESC_02', '5. Escuta e Objeções', 'Retomar e espelhar termos utilizados pelo lead'),
            ('OP_ESC_03', '5. Escuta e Objeções', 'Tratar com empatia o receio de riscos ou fiscalização'),
            ('OP_ESC_04', '5. Escuta e Objeções', 'Evitar interrupções e sobreposição de falas no fluxo da conversa'),
            ('OP_ESC_05', '5. Escuta e Objeções', 'Investigar o motivo do desinteresse para direcionar a melhor saída'),
            ('OP_PROX_01', '6. Próximo Passo e Compromisso', 'Propor opções objetivas de data e horário (técnica de dupla escolha)'),
            ('OP_PROX_02', '6. Próximo Passo e Compromisso', 'Alinhar formalmente a modalidade escolhida (online ou presencial)'),
            ('OP_PROX_03', '6. Próximo Passo e Compromisso', 'Contornar o pedido passivo de envio de material'),
            ('OP_PROX_04', '6. Próximo Passo e Compromisso', 'Definir responsável e data concreta para retornos agendados'),
            ('OP_DIR_01', '7. Direcionamento Final e Resolução', 'Direcionamento assertivo com base no perfil'),
            ('OP_DIR_02', '7. Direcionamento Final e Resolução', 'Condução para uma conversa substantiva'),
            ('OP_DIR_03', '7. Direcionamento Final e Resolução', 'Consolidação de um status claro')
            ON CONFLICT (codigo) DO NOTHING;
            """
        )
        _SCHEMA_AVALIACAO_GARANTIDO = True
    except Exception:
        pass


def inserir_analise(
    cur: psycopg.Cursor,
    log: str,
    analise: dict[str, Any],
) -> str | None:
    """
    Persiste a análise comercial completa nas 7 tabelas normalizadas
    dentro da transação ativa do cursor.
    """
    garantir_schema_avaliacao(cur)
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
            (perfil.get("setor") or None)[:100] if perfil.get("setor") and perfil.get("setor") != "Não se aplica" else None,
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
            "calculado": 3,
            "afirmado apenas pelo SDR": 2,
            "inferência plausível": 1,
            "não informado": 0,
        }

        # Busca dados e origens atuais da empresa
        cur.execute(
            """
            SELECT setor_origem, regime_origem, faturamento_origem
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

        nova_orig_setor = str(perfil.get("setor_origem") or "não informado")
        nova_orig_regime = str(perfil.get("regime_origem") or "não informado")
        nova_orig_fat = str(perfil.get("faturamento_origem") or "não informado")

        setor_val = perfil.get("setor") if perfil.get("setor") and perfil.get("setor") != "Não se aplica" else None
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

        updates = []
        params = []
        if resultado_comercial:
            updates.append("status_comercial = %s")
            params.append(str(resultado_comercial)[:100])
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
