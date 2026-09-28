# -*- coding: utf-8 -*-
"""
============================================================================
Serviço de Consolidação e Fechamento de Ciclo Mensal (Nível Macro).
============================================================================

Consolida o desempenho de cada atendente em ciclos mensais fechados de 30 dias:
1. Agrega métricas numéricas via PostgreSQL (médias dos critérios PEAH e nota geral).
2. Coleta amostragem das 15 chamadas com menor nota e 15 com maior nota no ciclo.
3. Submete o dossiê consolidado ao modelo de IA via Structured Output.
4. Grava/atualiza os diagnósticos na tabela `perfil_agente` para consumo no Power BI.

Pode ser executado via CLI (terminal / agendador) ou disparado pela Engine/GUI do SONAX.
============================================================================
"""
from __future__ import annotations

import argparse
import calendar
from dataclasses import dataclass
from datetime import date, datetime
import os
import sys
import threading
from typing import Any, Callable, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from app.config.prompts import prompt_consolidacao_macro
from app.database.db import conectar
from app.database.chamadas_dao import garantir_schema_atualizado
from app.database.perfil_dao import (
    buscar_agentes_no_ciclo,
    gravar_perfil_agente,
    obter_amostras_extremos,
    obter_estatisticas_agente,
    perfil_ja_existe,
)
from app.logs import log_dev_exc

load_dotenv()


# ============================================================================
# DATACLASS DE RESULTADO
# ============================================================================

@dataclass(frozen=True)
class FechamentoCicloResult:
    """Resultado estruturado e tipado da consolidação macro mensal."""
    ano: int
    mes: int
    inicio: date
    fim: date
    mes_referencia: date
    total_agentes: int
    processados: int
    pulados: int
    falhas: int
    cancelado: bool = False

    @property
    def sucesso(self) -> bool:
        return self.falhas == 0 and not self.cancelado

    def __getitem__(self, item: str) -> Any:
        """Compatibilidade para acesso por chave estilo dicionário legado."""
        return getattr(self, item)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


# ============================================================================
# SCHEMA ESTRUTURADO PARA O MODELO DE IA
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
# FORMATAÇÃO DE AMOSTRAS PARA O PROMPT
# ============================================================================

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
# ORQUESTRADOR PRINCIPAL DO FECHAMENTO
# ============================================================================

def executar_fechamento_ciclo(
    ano: int,
    mes: int,
    forcar: bool = True,
    *,
    cancel: threading.Event | None = None,
    on_progress: Optional[Callable[..., None]] = None,
    on_log: Optional[Callable[[str], None]] = None,
    chain_ia: Any | None = None,
) -> FechamentoCicloResult:
    """Executa a consolidação Macro para todos os atendentes ativos no mês.

    Args:
        ano: Ano do ciclo (ex: 2026).
        mes: Mês do ciclo (1 a 12).
        forcar: Se True, atualiza agentes já consolidados (ON CONFLICT DO UPDATE).
                Se False, pula agentes que já possuem registro no ciclo.
        cancel: Flag threading.Event para cancelamento cooperativo imediato.
        on_progress: Callback f(frac, label) para notificar progresso numérico à Engine/UI.
        on_log: Callback f(msg) para mensagens de log de console.
        chain_ia: Objeto chain opcional para testes ou injeção de dependência.

    Returns:
        FechamentoCicloResult estruturado com métricas da operação.
    """
    def _log(msg: str) -> None:
        if on_log:
            on_log(msg)
        elif on_progress:
            try:
                on_progress(msg)
            except TypeError:
                print(msg)
        else:
            print(msg)

    def _notify_progress(frac: float, label: str) -> None:
        if on_progress:
            try:
                on_progress(frac, label)
            except TypeError:
                pass

    inicio, fim = calcular_intervalo_ciclo(ano, mes)
    mes_referencia = date(ano, mes, 1)

    _log("============================================================")
    _log(f"  FECHAMENTO MENSAL DE QUALIDADE - CICLO: {inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}")
    _log(f"  Mês de Referência Power BI: {mes_referencia.strftime('%Y-%m-%d')}")
    _log("============================================================")

    if cancel is not None and cancel.is_set():
        _log("\n[CANCELADO] Fechamento mensal cancelado antes de iniciar.")
        return FechamentoCicloResult(
            ano=ano, mes=mes, inicio=inicio, fim=fim, mes_referencia=mes_referencia,
            total_agentes=0, processados=0, pulados=0, falhas=0, cancelado=True,
        )

    try:
        with conectar() as cur:
            garantir_schema_atualizado(cur)
            agentes = buscar_agentes_no_ciclo(cur, inicio, fim)
    except Exception:
        _log("[FALHA TOTAL] Não foi possível conectar ao banco de dados para buscar os atendentes.")
        log_dev_exc()
        return FechamentoCicloResult(
            ano=ano, mes=mes, inicio=inicio, fim=fim, mes_referencia=mes_referencia,
            total_agentes=0, processados=0, pulados=0, falhas=1, cancelado=False,
        )

    if not agentes:
        _log(f"[AVISO] Nenhum atendente com chamadas avaliadas encontrado no período {inicio} a {fim}.")
        return FechamentoCicloResult(
            ano=ano, mes=mes, inicio=inicio, fim=fim, mes_referencia=mes_referencia,
            total_agentes=0, processados=0, pulados=0, falhas=0, cancelado=False,
        )

    _log(f"[INFO] {len(agentes)} atendente(s) identificado(s) com chamadas no ciclo.")

    if chain_ia is not None:
        chain = chain_ia
    else:
        try:
            chain = _obter_chain_macro()
        except Exception:
            _log("[FALHA TOTAL] Não foi possível inicializar o serviço de inteligência artificial.")
            log_dev_exc()
            return FechamentoCicloResult(
                ano=ano, mes=mes, inicio=inicio, fim=fim, mes_referencia=mes_referencia,
                total_agentes=len(agentes), processados=0, pulados=0, falhas=len(agentes), cancelado=False,
            )

    processados = 0
    pulados = 0
    falhas = 0

    for i, agente_nome in enumerate(agentes, start=1):
        if cancel is not None and cancel.is_set():
            _log(f"\n[CANCELADO] Fechamento mensal interrompido pelo usuário no atendente {agente_nome}.")
            return FechamentoCicloResult(
                ano=ano, mes=mes, inicio=inicio, fim=fim, mes_referencia=mes_referencia,
                total_agentes=len(agentes), processados=processados, pulados=pulados, falhas=falhas, cancelado=True,
            )

        frac = (i - 1) / len(agentes)
        _notify_progress(frac, f"Consolidando [{i}/{len(agentes)}]: {agente_nome} ...")
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

        # Regra: Quando um ciclo não puder ser avaliado, não atribua 0, atribua null em nota_media_mes
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

            # Invocação do modelo de IA com retries de resiliência (3 tentativas)
            perfil_resultado: PerfilAgenteOutput | None = None
            for tentativa in range(1, 4):
                if cancel is not None and cancel.is_set():
                    _log("\n[CANCELADO] Fechamento mensal interrompido pelo usuário durante inferência.")
                    return FechamentoCicloResult(
                        ano=ano, mes=mes, inicio=inicio, fim=fim, mes_referencia=mes_referencia,
                        total_agentes=len(agentes), processados=processados, pulados=pulados, falhas=falhas, cancelado=True,
                    )

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
                except Exception:
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
                    perfil_resultado.resumo_evolutivo,
                    perfil_resultado.principais_pontos_fortes,
                    perfil_resultado.principais_fragilidades,
                    perfil_resultado.plano_acao_oportunidades,
                )
            _log(f"  [INFO] Perfil macro de {agente_nome} salvo com sucesso no banco (ID {id_perfil}).")
            processados += 1
        except Exception:
            _log(f"  [ERRO] Falha ao salvar o perfil de {agente_nome} no banco de dados.")
            log_dev_exc()
            falhas += 1

    _notify_progress(1.0, f"Fechamento {mes:02d}/{ano} finalizado.")
    _log(
        f"\n[INFO] Fechamento Mensal concluído!\n"
        f"  Total de agentes: {len(agentes)} | Processados: {processados} | "
        f"Pulados: {pulados} | Falhas: {falhas}"
    )

    return FechamentoCicloResult(
        ano=ano,
        mes=mes,
        inicio=inicio,
        fim=fim,
        mes_referencia=mes_referencia,
        total_agentes=len(agentes),
        processados=processados,
        pulados=pulados,
        falhas=falhas,
        cancelado=False,
    )


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

    if resultado.falhas > 0 or resultado.cancelado:
        sys.exit(1)
    sys.exit(0)
