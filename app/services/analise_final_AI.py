# -*- coding: utf-8 -*-
"""
============================================================================
Serviço de Análise de Qualidade Comercial B2B via IA (Falavinha Next).

Responsabilidades:
    1. Avaliação estruturada da ligação conforme metodologia SPIN Selling e BANT.
    2. Avaliação de qualidade do SDR com 6 critérios pré-definidos (dim_criterio_avaliacao).
    3. Seleção de exatamente 1 código de oportunidade (dim_oportunidade_treinamento).
    4. Diagnóstico do interlocutor (dores, dúvidas, objeções) e próximo passo para CRM.
    5. Tratamento de ligações não avaliáveis (URA, queda, recusa imediata) com NULL numérico
       para integridade em agregações no Power BI.
    6. Estruturação tipada com Pydantic e chamada com Structured Output (GPT-4o-mini via OpenRouter).
============================================================================
"""
from __future__ import annotations

import json
import os
import re
from datetime import date
from typing import Any, Literal

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.config.prompts import prompt_analise

load_dotenv()


# ==========================================================
# CATÁLOGO DE DIMENSÕES PRÉ-DEFINIDAS
# ==========================================================

CRITERIOS_OFICIAIS: dict[str, dict[str, Any]] = {
    "CRIT_ABERTURA": {
        "descricao": "Abertura clara, motivo do contato e relevância para o interlocutor",
        "max_pontos": 10,
    },
    "CRIT_SPIN": {
        "descricao": "Descoberta SPIN: Situação, Problema, Implicação, Necessidade de solução",
        "max_pontos": 30,
    },
    "CRIT_PERFIL": {
        "descricao": "Investigação adequada do perfil: setor, regime tributário, faturamento",
        "max_pontos": 25,
    },
    "CRIT_BANT": {
        "descricao": "Investigação BANT: viabilidade comercial, autoridade, necessidade, prazo",
        "max_pontos": 15,
    },
    "CRIT_ESCUTA": {
        "descricao": "Escuta, aprofundamento e tratamento respeitoso de dúvidas ou objeções",
        "max_pontos": 10,
    },
    "CRIT_PROX_PASSO": {
        "descricao": "Proposta de próximo passo pertinente e tentativa de obter compromisso claro",
        "max_pontos": 10,
    },
}

CODIGOS_OPORTUNIDADE_VALIDOS = {
    "OP_ABERT_01", "OP_ABERT_02", "OP_ABERT_03", "OP_ABERT_04", "OP_ABERT_05", "OP_ABERT_06",
    "OP_SPIN_01", "OP_SPIN_02", "OP_SPIN_03", "OP_SPIN_04", "OP_SPIN_05",
    "OP_PERF_01", "OP_PERF_02", "OP_PERF_03", "OP_PERF_04",
    "OP_BANT_01", "OP_BANT_02", "OP_BANT_03", "OP_BANT_04",
    "OP_ESC_01", "OP_ESC_02", "OP_ESC_03", "OP_ESC_04", "OP_ESC_05",
    "OP_PROX_01", "OP_PROX_02", "OP_PROX_03", "OP_PROX_04",
    "OP_DIR_01", "OP_DIR_02", "OP_DIR_03",
}


# ==========================================================
# MODELOS PYDANTIC (ESTRUTURA RELACIONAL 7 TABELAS)
# ==========================================================

class AvaliacaoIAModel(BaseModel):
    protocolo: int | None = Field(default=None, description="Número de protocolo da chamada")
    data_avaliacao: str = Field(description="Data da avaliação no formato YYYY-MM-DD")
    modelo_ia: str = Field(default="gpt-4o-mini", description="Identificador do modelo de IA utilizado")
    interlocutor: str | None = Field(default=None, description="Nome do interlocutor contatado na empresa")
    cargo: str | None = Field(default=None, description="Cargo ou área do interlocutor")
    empresa_contatada: int | None = Field(default=None, description="ID numérico da empresa contatada")
    resultado: str = Field(
        description="Status comercial da empresa: 'Perfil confirmado', 'Perfil pendente', 'Fora do perfil desta campanha' ou 'Dados insuficientes'"
    )
    ligacao_relevante: Literal["s", "n"] = Field(
        description="'s' se a chamada teve conversa substantiva relevante, 'n' caso contrário"
    )
    reuniao_confirmada: Literal["s", "n"] = Field(
        description="'s' se reunião foi confirmada com aceite claro e data/horário, 'n' caso contrário"
    )
    data_confirmada: Literal["s", "n"] = Field(
        description="'s' se houve confirmação explícita de data e horário para próximo passo, 'n' caso contrário"
    )
    resultado_frase: str = Field(
        description="Resultado em uma frase: o que aconteceu e qual compromisso foi obtido"
    )


class AnaliseSpinModel(BaseModel):
    situacao: str | None = Field(default=None, description="Contexto atual, estrutura fiscal/contábil e prioridades")
    problema: str | None = Field(default=None, description="Dificuldades ou atritos fiscais reconhecidos pelo interlocutor")
    implicacao: str | None = Field(default=None, description="Consequências operacionais, financeiras ou estratégicas")
    necessidade_solucao: str | None = Field(default=None, description="Benefícios e resultados esperados pelo interlocutor")
    evidencias: str | None = Field(default=None, description="Citações textuais curtas entre aspas")
    lacunas: str | None = Field(default=None, description="O que o SDR deixou de aprofundar na descoberta SPIN")


class AnaliseBantModel(BaseModel):
    budget_classificacao: str = Field(description="confirmado, indício, não informado ou negado")
    budget_evidencia: str | None = Field(default=None, description="Evidência curta sobre orçamento")
    authority_classificacao: str = Field(description="confirmado, indício, não informado ou negado")
    authority_evidencia: str | None = Field(default=None, description="Evidência curta sobre autoridade")
    need_classificacao: str = Field(description="confirmado, indício, não informado ou negado")
    need_evidencia: str | None = Field(default=None, description="Evidência curta sobre necessidade")
    timeline_classificacao: str = Field(description="confirmado, indício, não informado ou negado")
    timeline_evidencia: str | None = Field(default=None, description="Evidência curta sobre prazos")


class AvaliacaoSDRModel(BaseModel):
    nota_final: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Nota inteira de 0 a 100, ou null se a chamada não for avaliável",
    )
    feedback_geral: str = Field(
        description="Feedback estruturado da atuação do SDR. Se não avaliável: 'Não avaliável: [motivo]'"
    )
    acertos: str | None = Field(default=None, description="Até 2 acertos observáveis na atuação do SDR")
    melhorias: str | None = Field(default=None, description="Até 2 oportunidades pontuais de melhoria para o SDR")
    frase_alternativa: str | None = Field(default=None, description="Uma frase ou pergunta concreta sugerida")
    codigo_oportunidade: str | None = Field(
        default=None,
        description="Exatamente 1 código de dim_oportunidade_treinamento (ex: OP_SPIN_03), ou null se não avaliável",
    )


class AvaliacaoCriterioItemModel(BaseModel):
    criterio: str = Field(description="Descrição oficial do critério avaliado")
    nota_criterio: int | None = Field(
        default=None,
        ge=0,
        le=30,
        description="Nota numérica inteira atribuída ao critério, ou null se não avaliável",
    )
    justificativa_criterio: str = Field(
        description="Justificativa sucinta da pontuação ou 'Não avaliável: [motivo]'"
    )
    codigo_criterio: str = Field(
        description="Código pré-definido: CRIT_ABERTURA, CRIT_SPIN, CRIT_PERFIL, CRIT_BANT, CRIT_ESCUTA ou CRIT_PROX_PASSO"
    )


class InterlocutorModel(BaseModel):
    interesse_expresso: str | None = Field(default=None, description="Interesse verbalizado ou 'não houve'")
    duvidas: str | None = Field(default=None, description="Dúvidas levantadas ou 'não houve'")
    objecoes: str | None = Field(default=None, description="Objeções apresentadas ou 'não houve'")
    resposta_sdr: str | None = Field(default=None, description="Como o SDR respondeu")
    reacao_interlocutor: str | None = Field(default=None, description="Reação final do lead")


class CrmModel(BaseModel):
    acao: str | None = Field(default=None, description="Próximo passo comercial concreto")
    responsavel: str | None = Field(default=None, description="Responsável pelo próximo passo")
    prazo: str | None = Field(default=None, description="Data e horário agendados ou 'não informado'")
    dados_extras: str | None = Field(default=None, description="Dados pendentes de confirmação")
    resumo: str | None = Field(default=None, description="Resumo executivo de até 80 palavras para colar no CRM")


class AnaliseCompletaModel(BaseModel):
    avaliacao_ia: AvaliacaoIAModel
    analise_spin: AnaliseSpinModel
    analise_bant: AnaliseBantModel
    avaliacao_sdr: AvaliacaoSDRModel
    avaliacao_criterio: list[AvaliacaoCriterioItemModel] = Field(min_length=6, max_length=6)
    interlocutor: InterlocutorModel
    crm: CrmModel


# ==========================================================
# CLIENTE E CHAIN LANGCHAIN
# ==========================================================

client = ChatOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    model="openai/gpt-4o-mini",
    temperature=0.0,
    max_tokens=2500,
    max_retries=3,
)

structured_client = client.with_structured_output(
    AnaliseCompletaModel,
    method="json_schema",
)

prompt = ChatPromptTemplate.from_messages(
    [
        SystemMessage(content=prompt_analise),
        (
            "user",
            """
### METADADOS DA LIGAÇÃO:
- Protocolo: {protocolo}
- ID da Empresa: {empresa_contatada}
- Nome da Empresa: {empresa_nome}
- SDR Responsável: {nome_sdr}

### TRANSCRIÇÃO REVISADA DA LIGAÇÃO A SER AVALIADA:
{ligacao}
""",
        ),
    ]
)

chain = prompt | structured_client


# ==========================================================
# FUNÇÕES DE CÁLCULO E TRATAMENTO
# ==========================================================

def _limpar_resposta_json(texto: str) -> dict[str, Any] | None:
    """Extrai JSON válido de strings que possam conter blocos de markdown."""
    texto_limpo = texto.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", texto_limpo, re.DOTALL)
    if match:
        texto_limpo = match.group(1).strip()
    try:
        return json.loads(texto_limpo)
    except Exception:
        return None


def normalizar_texto_nao_se_aplica(valor: Any) -> str:
    """Normaliza campos de texto que representam ausência ou vazio para 'Não se aplica'."""
    if valor is None:
        return "Não se aplica"
    val_str = str(valor).strip()
    if not val_str:
        return "Não se aplica"

    val_norm = val_str.lower().rstrip(".").strip()
    termos_ausencia = {
        "não se aplica", "nao se aplica",
        "não houve", "nao houve",
        "não informado", "nao informado",
        "não identificado", "nao identificado",
        "nenhum", "nenhuma",
        "não há", "nao ha",
        "nada", "n/a", "sem retorno",
        "null", "none",
        "não ocorreu", "nao ocorreu",
        "sem informações", "sem informacoes",
        "não mencionou", "nao mencionou",
        "não relatado", "nao relatado",
        "sem dados", "sem dado",
    }
    if (
        val_norm in termos_ausencia
        or val_norm.startswith("não se aplica")
        or val_norm.startswith("nao se aplica")
        or val_norm.startswith("não houve")
        or val_norm.startswith("nao houve")
    ):
        return "Não se aplica"

    return val_str


def calcular_e_sanitizar_analise(
    resultado: dict[str, Any],
    *,
    protocolo: int | None = None,
    empresa_contatada: int | None = None,
) -> dict[str, Any]:
    """
    Aplica regras determinísticas de negócio:
        - Ajusta protocolo e ID de empresa contatada.
        - Identifica chamadas não avaliáveis (URA, queda, recusa) e força nota_final = null
          e nota_criterio = null para proteção do Power BI.
        - Calcula nota_final como a soma dos 6 critérios quando a ligação for avaliável.
        - Garante que os 6 critérios oficiais existam na lista avaliacao_criterio.
        - Valida que codigo_oportunidade seja um código dimensional válido.
        - Padroniza campos textuais sem ocorrência para 'Não se aplica'.
    """
    # 1. Metadados de avaliacao_ia
    av_ia = resultado.setdefault("avaliacao_ia", {})
    if protocolo is not None and not av_ia.get("protocolo"):
        av_ia["protocolo"] = protocolo
    if empresa_contatada is not None and not av_ia.get("empresa_contatada"):
        av_ia["empresa_contatada"] = empresa_contatada
    if not av_ia.get("data_avaliacao"):
        av_ia["data_avaliacao"] = str(date.today())
    if not av_ia.get("modelo_ia"):
        av_ia["modelo_ia"] = "gpt-4o-mini"

    # Normalização de interlocutor e cargo quando ausentes/vazios
    av_ia["interlocutor"] = normalizar_texto_nao_se_aplica(av_ia.get("interlocutor"))
    av_ia["cargo"] = normalizar_texto_nao_se_aplica(av_ia.get("cargo"))

    # 2. Avaliação SDR e Critérios
    av_sdr = resultado.setdefault("avaliacao_sdr", {})
    criterios = resultado.setdefault("avaliacao_criterio", [])
    feedback = (av_sdr.get("feedback_geral") or "").strip()

    # Notas numéricas presentes nos critérios
    notas_validas = [
        c["nota_criterio"] for c in criterios if c.get("nota_criterio") is not None
    ]

    # Detecção de URA ou chamadas não avaliáveis (apenas quando não há pontuação positiva válida)
    tem_pontos_positivos = any(n > 0 for n in notas_validas)
    eh_nao_avaliavel = (
        feedback.lower().startswith("não avaliável")
        or feedback.lower().startswith("nao avaliavel")
        or (not tem_pontos_positivos and (
            "não avaliável" in feedback.lower()
            or "nao avaliavel" in feedback.lower()
            or "ura" in feedback.lower()
            or "inválida para a avali" in feedback.lower()
        ))
        or (not notas_validas and av_sdr.get("nota_final") is None)
    )

    if eh_nao_avaliavel:
        av_sdr["nota_final"] = None
        av_sdr["codigo_oportunidade"] = None
        if not feedback.lower().startswith("não avaliável"):
            av_sdr["feedback_geral"] = f"Não avaliável: {feedback}" if feedback else "Não avaliável: Sem diálogo suficiente para avaliação."

        for crit in criterios:
            crit["nota_criterio"] = None
            just = (crit.get("justificativa_criterio") or "").strip()
            if not just.lower().startswith("não avaliável"):
                crit["justificativa_criterio"] = f"Não avaliável: {just}" if just else "Não avaliável: Sem contexto para este critério."

        av_ia["ligacao_relevante"] = "n"
        av_ia["reuniao_confirmada"] = "n"
        av_ia["data_confirmada"] = "n"

    else:
        # Ligações avaliáveis: soma determinística dos 6 critérios
        notas_validas = [
            c["nota_criterio"] for c in criterios if c.get("nota_criterio") is not None
        ]
        if notas_validas:
            soma = sum(notas_validas)
            av_sdr["nota_final"] = max(0, min(100, soma))
        else:
            av_sdr["nota_final"] = None

        # Validação do código de oportunidade contra a dimensão
        cod_op = av_sdr.get("codigo_oportunidade")
        if cod_op and cod_op not in CODIGOS_OPORTUNIDADE_VALIDOS:
            # Fallback seguro para código existente mais genérico de fechamento
            av_sdr["codigo_oportunidade"] = "OP_DIR_03"

    # Padronização de campos de avaliação SDR
    for k in ("acertos", "melhorias", "frase_alternativa"):
        av_sdr[k] = normalizar_texto_nao_se_aplica(av_sdr.get(k))

    # 3. Garantia dos 6 critérios pré-definidos
    codigos_presentes = {c.get("codigo_criterio") for c in criterios if c.get("codigo_criterio")}
    for cod_crit, meta in CRITERIOS_OFICIAIS.items():
        if cod_crit not in codigos_presentes:
            criterios.append({
                "criterio": meta["descricao"],
                "nota_criterio": None,
                "justificativa_criterio": "Não avaliável: Critério ausente na resposta da IA.",
                "codigo_criterio": cod_crit,
            })

    # 4. Padronização de campos em analise_spin
    spin = resultado.setdefault("analise_spin", {})
    for k in ("situacao", "problema", "implicacao", "necessidade_solucao", "evidencias", "lacunas"):
        spin[k] = normalizar_texto_nao_se_aplica(spin.get(k))

    # 5. Padronização de campos em analise_bant
    bant = resultado.setdefault("analise_bant", {})
    for k in ("budget_evidencia", "authority_evidencia", "need_evidencia", "timeline_evidencia"):
        bant[k] = normalizar_texto_nao_se_aplica(bant.get(k))

    # 6. Padronização de campos em interlocutor
    inter = resultado.setdefault("interlocutor", {})
    for k in ("interesse_expresso", "duvidas", "objecoes", "resposta_sdr", "reacao_interlocutor"):
        inter[k] = normalizar_texto_nao_se_aplica(inter.get(k))

    # 7. Padronização de campos em crm
    crm = resultado.setdefault("crm", {})
    crm["acao"] = crm.get("acao") or "Sem próximo passo definido"
    for k in ("responsavel", "prazo", "dados_extras"):
        crm[k] = normalizar_texto_nao_se_aplica(crm.get(k))

    resumo_crm = (crm.get("resumo") or "").strip()
    if resumo_crm:
        palavras = resumo_crm.split()
        if len(palavras) > 80:
            crm["resumo"] = " ".join(palavras[:80]) + "..."
    else:
        crm["resumo"] = "Não se aplica"

    return resultado


# ==========================================================
# FUNÇÃO PRINCIPAL
# ==========================================================

def analisar_ligacao(
    ligacao: str,
    *,
    protocolo: int | None = None,
    empresa_contatada: int | None = None,
    empresa_nome: str | None = None,
    nome_sdr: str | None = None,
) -> dict[str, Any]:
    """
    Submete a transcrição revisada ao GPT-4o-mini e devolve o dicionário
    completo com as 7 chaves relacionais padronizadas.
    """
    inputs = {
        "ligacao": ligacao,
        "protocolo": protocolo or "Não informado",
        "empresa_contatada": empresa_contatada or "Não informado",
        "empresa_nome": empresa_nome or "Não informado",
        "nome_sdr": nome_sdr or "Não informado",
    }

    resposta = chain.invoke(inputs)

    # Conversão Pydantic -> dict
    if isinstance(resposta, BaseModel):
        resultado = resposta.model_dump()
    elif isinstance(resposta, dict):
        resultado = resposta
    elif isinstance(resposta, str):
        parsed = _limpar_resposta_json(resposta)
        resultado = parsed if parsed else {}
    else:
        resultado = dict(resposta)

    resultado = calcular_e_sanitizar_analise(
        resultado,
        protocolo=protocolo,
        empresa_contatada=empresa_contatada,
    )

    return resultado