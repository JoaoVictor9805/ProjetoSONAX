# -*- coding: utf-8 -*-
"""
============================================================================
Serviço de Consolidação e Fechamento de Ciclo Mensal (Nível Macro).
============================================================================

Consolida o desempenho de cada atendente em ciclos mensais fechados de 30 dias:
1. Agrega métricas numéricas via PostgreSQL (médias dos critérios PEAH e nota geral).
2. Coleta amostragem das 15 chamadas com menor nota e 15 com maior nota no ciclo.
3. Submete o dossiê consolidado ao Gemini Flash-Lite via Structured Output.
4. Grava/atualiza os diagnósticos na tabela `perfil_agente` para consumo no Power BI.

Pode ser executado via CLI (terminal / agendador) ou disparado pela GUI do SONAX.
"""

from __future__ import annotations

import argparse
import calendar
from datetime import date, datetime
import os
import sys
from typing import Callable, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
import psycopg

from app.config.prompts import prompt_consolidacao_macro
from app.database.db import conectar
from app.services.chamadas_dao import garantir_schema_atualizado
from app.logs import log_dev_exc

load_dotenv()


# ============================================================================
# SCHEMA ESTRUTURADO PARA O GEMINI FLASH-LITE
# ============================================================================

class PerfilAgenteOutput(BaseModel):
    resumo_evolutivo: str = Field(
        description=(
            "Síntese executiva (máximo 3 a 4 linhas) do perfil e consistência do agente neste ciclo. "
            "Se o ciclo não puder ser avaliado ou não houver chamadas válidas, retorne exatamente: "
            "'[Não houve chamadas válidas durante esse ciclo]'."
        )
    )
    principais_pontos_fortes: str | None = Field(
        default=None,
        description="Os 2 a 3 pontos fortes e boas práticas mais consistentes demonstrados pelo agente no mês (ou null se o ciclo não puder ser avaliado)."
    )
    principais_fragilidades: str | None = Field(
        default=None,
        description="Os 2 a 3 pontos críticos mais recorrentes que mais prejudicaram o desempenho do agente no mês (ou null se o ciclo não puder ser avaliado)."
    )
    plano_acao_oportunidades: str | None = Field(
        default=None,
        description="Recomendações práticas, direcionadas e focadas na correção das fragilidades observadas (ou null se o ciclo não puder ser avaliado)."
    )


# ============================================================================
# INICIALIZAÇÃO DO MODELO
# ============================================================================

def _obter_chain_macro():
    """
    client = ChatGoogleGenerativeAI(
        model="gemini-3.5-flash-lite",
        google_api_key=os.getenv("GEMINI_API_KEY"),
        temperature=0,
        max_output_tokens=4096,
        max_retries=3,
    )
    """
    client = ChatOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
        model="openai/gpt-4o-mini",
        temperature=0.0,
        max_tokens=1500,
        max_retries=3,
    )
    structured_client = client.with_structured_output(
        PerfilAgenteOutput,
        method="json_schema",
    )
    prompt = ChatPromptTemplate.from_template(prompt_consolidacao_macro)
    return prompt | structured_client


# ============================================================================
# FUNÇÕES DE DATA E CICLO
# ============================================================================

def calcular_intervalo_ciclo(ano: int, mes: int) -> tuple[date, date]:
    """Retorna o primeiro e o último dia do mês especificado."""
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, 1), date(ano, mes, ultimo_dia)


def mes_anterior_padrao() -> tuple[int, int]:
    """Retorna (ano, mes) correspondente ao mês anterior completo."""
    hoje = date.today()
    if hoje.month == 1:
        return hoje.year - 1, 12
    return hoje.year, hoje.month - 1


# ============================================================================
# CONSULTAS SQL DE AGREGAÇÃO
# ============================================================================

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
) -> dict:
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
) -> tuple[list[dict], list[dict]]:
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


def formatar_bloco_amostras(amostras: list[dict]) -> str:
    """Formata a lista de chamadas extremas em texto legível para o prompt."""
    if not amostras:
        return "Nenhuma chamada com diagnósticos registrados nesta categoria."
    linhas = []
    for i, a in enumerate(amostras, start=1):
        titulo_str = f" - \"{a['titulo']}\"" if a.get("titulo") and a["titulo"] != "Sem título" else ""
        linhas.append(
            f"Ligação #{i}{titulo_str} [Nota: {a['nota']}]:\n"
            f"  - Resumo: {a['resumo']}\n"
            f"  - Pontos Fortes: {a.get('pontos_fortes', 'Nenhum informado')}\n"
            f"  - Fragilidades: {a['fragilidades']}\n"
            f"  - Oportunidades: {a['oportunidades']}"
        )
    return "\n\n".join(linhas)



# ============================================================================
# PERSISTÊNCIA EM PERFIL_AGENTE
# ============================================================================

def gravar_perfil_agente(
    cur: psycopg.Cursor,
    agente_nome: str,
    mes_referencia: date,
    total_chamadas_mes: int,
    nota_media_mes: float | None,
    perfil: PerfilAgenteOutput,
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
            perfil.resumo_evolutivo,
            perfil.principais_pontos_fortes,
            perfil.principais_fragilidades,
            perfil.plano_acao_oportunidades,
        ),
    )
    res = cur.fetchone()
    return res[0] if res else None


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


# ============================================================================
# ORQUESTRADOR PRINCIPAL DO FECHAMENTO
# ============================================================================

def executar_fechamento_ciclo(
    ano: int,
    mes: int,
    forcar: bool = True,
    on_progress: Optional[Callable[[str], None]] = None,
) -> dict:
    """Executa a consolidação Macro para todos os atendentes ativos no mês.

    Args:
        ano: Ano do ciclo (ex: 2026).
        mes: Mês do ciclo (1 a 12).
        forcar: Se True, atualiza agentes já consolidados (ON CONFLICT DO UPDATE).
                Se False, pula agentes que já possuem registro no ciclo.
        on_progress: Callback para notificar mensagens de log à UI ou CLI.

    Returns:
        dict com estatísticas do processamento (total_agentes, processados, pulados, falhas).
    """
    def _log(msg: str) -> None:
        if on_progress:
            on_progress(msg)
        else:
            print(msg)

    inicio, fim = calcular_intervalo_ciclo(ano, mes)
    mes_referencia = date(ano, mes, 1)

    _log(f"============================================================")
    _log(f"  FECHAMENTO MENSAL DE QUALIDADE - CICLO: {inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}")
    _log(f"  Mês de Referência Power BI: {mes_referencia.strftime('%Y-%m-%d')}")
    _log(f"============================================================")

    try:
        with conectar() as cur:
            garantir_schema_atualizado(cur)
            agentes = buscar_agentes_no_ciclo(cur, inicio, fim)
    except Exception as exc:
        _log("[FALHA TOTAL] Não foi possível conectar ao banco de dados para buscar os atendentes.")
        log_dev_exc()
        return {
            "mes_referencia": mes_referencia,
            "ciclo": (inicio, fim),
            "total_agentes": 0,
            "processados": 0,
            "pulados": 0,
            "falhas": 1,
        }

    if not agentes:
        _log(f"[AVISO] Nenhum atendente com chamadas avaliadas encontrado no período {inicio} a {fim}.")
        return {
            "mes_referencia": mes_referencia,
            "ciclo": (inicio, fim),
            "total_agentes": 0,
            "processados": 0,
            "pulados": 0,
            "falhas": 0,
        }

    _log(f"[INFO] {len(agentes)} atendente(s) identificado(s) com chamadas no ciclo.")

    try:
        chain = _obter_chain_macro()
    except Exception as exc:
        _log("[FALHA TOTAL] Não foi possível inicializar o serviço de inteligência artificial.")
        log_dev_exc()
        return {
            "mes_referencia": mes_referencia,
            "ciclo": (inicio, fim),
            "total_agentes": len(agentes),
            "processados": 0,
            "pulados": 0,
            "falhas": len(agentes),
        }

    processados = 0
    pulados = 0
    falhas = 0

    for i, agente_nome in enumerate(agentes, start=1):
        _log(f"\n[INFO] [{i}/{len(agentes)}] Consolidando perfil de: {agente_nome} ...")

        with conectar() as cur:
            if not forcar and perfil_ja_existe(cur, agente_nome, mes_referencia):
                _log(f"  [PULADO] Agente {agente_nome} já consolidado neste mês (--forcar=False).")
                pulados += 1
                continue

            stats = obter_estatisticas_agente(cur, agente_nome, inicio, fim)
            menores, maiores = obter_amostras_extremos(cur, agente_nome, inicio, fim, limite=15)

        total_chamadas = stats["total_chamadas"]
        nota_media = stats["nota_media"]
        chamadas_validas = stats.get("chamadas_validas", 0)

        # Regra: Quando um ciclo não puder ser avaliado, não atribua 0, atribua null em nota_media_mes (perfil_agente).
        # Quando um ciclo = null, o resumo mensal deve ser [Não houve chamadas válidas durante esse ciclo] (perfil_agente).
        # Os demais atributos: fragilidades, pontos fortes e oportunidades de melhoria devem receber null (perfil_agente).
        if total_chamadas == 0 or chamadas_validas == 0 or nota_media is None:
            _log(f"  [INFO] Ciclo sem chamadas válidas para {agente_nome}. Gravando perfil nulo padronizado.")
            perfil_resultado = PerfilAgenteOutput(
                resumo_evolutivo="[Não houve chamadas válidas durante esse ciclo]",
                principais_pontos_fortes=None,
                principais_fragilidades=None,
                plano_acao_oportunidades=None,
            )
            nota_media_gravar = None
        else:
            nota_media_gravar = nota_media
            medias_criterios_str = "\n".join(
                f"- {crit}: {nota:.2f}" for crit, nota in stats["medias_criterios"].items()
            ) or "- Nenhum critério pontuado."

            _log(f"  Métricas: {total_chamadas} chamadas ({chamadas_validas} válidas) | Média geral: {nota_media:.2f}")
            _log(f"  Amostras coletadas: {len(menores)} menores notas | {len(maiores)} maiores notas")

            # Invocação do Gemini Flash-Lite com retentativas
            perfil_resultado: PerfilAgenteOutput | None = None
            for tentativa in range(1, 4):
                try:
                    payload = {
                        "agente_nome": agente_nome,
                        "ciclo_inicio": inicio.strftime("%d/%m/%Y"),
                        "ciclo_fim": fim.strftime("%d/%m/%Y"),
                        "total_chamadas": total_chamadas,
                        "nota_media": f"{nota_media:.2f}",
                        "medias_criterios": medias_criterios_str,
                        "amostras_menores_notas": formatar_bloco_amostras(menores),
                        "amostras_maiores_notas": formatar_bloco_amostras(maiores),
                    }
                    resposta = chain.invoke(payload)
                    if isinstance(resposta, PerfilAgenteOutput):
                        perfil_resultado = resposta
                    elif isinstance(resposta, dict):
                        perfil_resultado = PerfilAgenteOutput(**resposta)
                    else:
                        perfil_resultado = PerfilAgenteOutput(**dict(resposta))
                    break
                except Exception as e:
                    _log(f"  [AVISO] Tentativa {tentativa}/3 falhou para {agente_nome}.")
                    log_dev_exc()

            if perfil_resultado is None:
                _log(f"  [ERRO] Não foi possível gerar o perfil macro de {agente_nome} após 3 tentativas.")
                falhas += 1
                continue

        # Gravação no PostgreSQL
        try:
            with conectar() as cur:
                id_perfil = gravar_perfil_agente(
                    cur,
                    agente_nome,
                    mes_referencia,
                    total_chamadas,
                    nota_media_gravar,
                    perfil_resultado,
                )
            _log(f"  [INFO] Perfil macro de {agente_nome} salvo com sucesso no banco (ID {id_perfil}).")
            processados += 1
        except Exception as e:
            _log(f"  [ERRO] Falha ao salvar o perfil de {agente_nome} no banco de dados.")
            log_dev_exc()
            falhas += 1

    _log(
        f"\n[INFO] Fechamento Mensal concluído!\n"
        f"  Total de agentes: {len(agentes)} | Processados: {processados} | "
        f"Pulados: {pulados} | Falhas: {falhas}"
    )

    return {
        "ciclo": (inicio, fim),
        "total_agentes": len(agentes),
        "processados": processados,
        "pulados": pulados,
        "falhas": falhas,
    }


# ============================================================================
# CLI DE EXECUÇÃO INDEPENDENTE
# ============================================================================

if __name__ == "__main__":
    ano_padrao, mes_padrao = mes_anterior_padrao()

    parser = argparse.ArgumentParser(
        description="Fechamento e Consolidação Macro de Ciclo Mensal (SONAX)"
    )
    parser.add_argument(
        "--ano",
        type=int,
        default=ano_padrao,
        help=f"Ano do ciclo de consolidação (padrão: {ano_padrao})",
    )
    parser.add_argument(
        "--mes",
        type=int,
        default=mes_padrao,
        help=f"Mês do ciclo de consolidação (1 a 12, padrão: {mes_padrao})",
    )
    parser.add_argument(
        "--nao-forcar",
        dest="forcar",
        action="store_false",
        help="Pula agentes que já possuem avaliação registrada no ciclo",
    )
    parser.set_defaults(forcar=True)

    args = parser.parse_args()

    if not (1 <= args.mes <= 12):
        print(f"[ERRO] Mês inválido: {args.mes}. Deve ser entre 1 e 12.")
        sys.exit(1)

    print("=" * 70)
    print(f"SONAX - Fechamento Mensal de Qualidade ({args.mes:02d}/{args.ano})")
    print("=" * 70)

    resultado = executar_fechamento_ciclo(
        ano=args.ano,
        mes=args.mes,
        forcar=args.forcar,
    )

    if resultado["falhas"] > 0:
        sys.exit(1)
    sys.exit(0)
