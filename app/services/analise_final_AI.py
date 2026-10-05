# -*- coding: utf-8 -*-
"""
============================================================================
Serviço de Análise de Qualidade Comercial B2B via IA (Falavinha Next).

Responsabilidades:
    1. Avaliação estruturada da ligação conforme metodologia SPIN Selling e BANT.
    2. Avaliação de qualidade do SDR com 6 critérios pré-definidos (dim_criterio_avaliacao).
    3. Seleção de exatamente 1 código de oportunidade (dim_oportunidade_treinamento).
    4. Diagnóstico do interlocutor (dores, dúvidas, objeções) e próximo passo para CRM.
    5. Análise de Perfil da Empresa (setor, regime, faturamento) com distinção
       rigorosa de confiabilidade da fonte (confirmado, afirmado pelo SDR, inferência, não informado).
    6. Cálculo determinístico da média mensal de faturamento a partir de anual de 12 meses.
    7. Validação determinística estrita da qualificação técnica da empresa (resultado).
    8. Tratamento de ligações não avaliáveis (URA, queda, recusa imediata) com NULL numérico
       para integridade em agregações no Power BI.
    9. Estruturação tipada com Pydantic e chamada com Structured Output.
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
from langchain_google_genai import ChatGoogleGenerativeAI
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
# MODELOS PYDANTIC (ESTRUTURA RELACIONAL 8 TABELAS)
# ==========================================================

RESULTADOS_STATUS_COMERCIAL_VALIDOS = (
    "Perfil confirmado",
    "Perfil pendente",
    "Fora do perfil desta campanha",
    "Dados insuficientes",
)

SETORES_VALIDOS = (
    "industrial",
    "outro confirmado",
    "não informado",
)

ORIGENS_DADOS_PERFIL_VALIDAS = (
    "confirmado pelo interlocutor",
    "afirmado apenas pelo SDR",
    "inferência plausível",
    "não informado",
)

ORIGENS_FATURAMENTO_VALIDAS = (
    "confirmado pelo interlocutor",
    "afirmado apenas pelo SDR",
    "inferência plausível",
    "não informado",
    "calculado",
)

REGRAS_FATURAMENTO_VALIDAS = (
    "declarado_mensal",
    "calculado_12_meses",
    "nao_confirmado",
    "nao_informado",
)


class AvaliacaoIAModel(BaseModel):
    protocolo: int | None = Field(default=None, description="Número de protocolo da chamada")
    data_avaliacao: str = Field(description="Data da avaliação no formato YYYY-MM-DD")
    modelo_ia: str = Field(default="gemini-3.1-flash-lite", description="Identificador do modelo de IA utilizado")
    interlocutor: str | None = Field(default=None, description="Nome do interlocutor contatado na empresa")
    cargo: str | None = Field(default=None, description="Cargo ou área do interlocutor")
    empresa_contatada: int | None = Field(default=None, description="ID numérico da empresa contatada")
    resultado: Literal[
        "Perfil confirmado",
        "Perfil pendente",
        "Fora do perfil desta campanha",
        "Dados insuficientes",
    ] = Field(
        description="Qualificação técnica da empresa: 'Perfil confirmado', 'Perfil pendente', 'Fora do perfil desta campanha' ou 'Dados insuficientes'"
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


class AnalisePerfilModel(BaseModel):
    setor: Literal[
        "industrial",
        "outro confirmado",
        "não informado",
    ] | None = Field(
        default="não informado",
        description="Setor da empresa contatada: 'industrial', 'outro confirmado' ou 'não informado'",
    )
    setor_origem: Literal[
        "confirmado pelo interlocutor",
        "afirmado apenas pelo SDR",
        "inferência plausível",
        "não informado",
    ] = Field(
        default="não informado",
        description="Origem/confiabilidade da informação de setor",
    )
    regime_tributario: str | None = Field(default=None, description="Regime tributário identificado ou 'Não informado'")
    regime_origem: Literal[
        "confirmado pelo interlocutor",
        "afirmado apenas pelo SDR",
        "inferência plausível",
        "não informado",
    ] = Field(
        default="não informado",
        description="Origem/confiabilidade da informação de regime tributário",
    )
    faturamento_declarado_texto: str | None = Field(
        default=None, description="Citação ou menção bruta de faturamento na chamada"
    )
    faturamento_anual: float | None = Field(
        default=None, description="Valor anual numérico em reais se informado, ou null"
    )
    faturamento_mensal: float | None = Field(
        default=None, description="Valor mensal numérico em reais se citado diretamente ou calculado, ou null"
    )
    periodo_meses: int | None = Field(
        default=None, description="Número de meses a que se refere o faturamento anual (ex: 12), ou null"
    )
    faturamento_origem: Literal[
        "confirmado pelo interlocutor",
        "afirmado apenas pelo SDR",
        "inferência plausível",
        "não informado",
        "calculado",
    ] = Field(
        default="não informado",
        description="Origem da informação de faturamento",
    )
    faturamento_regra: Literal[
        "declarado_mensal",
        "calculado_12_meses",
        "nao_confirmado",
        "nao_informado",
    ] = Field(
        default="nao_informado",
        description="Regra de determinação do faturamento",
    )
    detalhes_faturamento: str | None = Field(
        default=None, description="Justificativa de cálculo ou ambiguidade"
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


ACOES_CRM_VALIDAS = (
    "reunião confirmada",
    "reunião proposta sem aceite",
    "retorno com data combinado",
    "envio de material solicitado",
    "sem próximo passo definido",
    "sem interesse explícito",
    "Não se aplica",
)
ACAO_CRM_VALIDAS = ACOES_CRM_VALIDAS


class CrmModel(BaseModel):
    acao: Literal[
        "reunião confirmada",
        "reunião proposta sem aceite",
        "retorno com data combinado",
        "envio de material solicitado",
        "sem próximo passo definido",
        "sem interesse explícito",
        "Não se aplica",
    ] | None = Field(
        default=None,
        description=(
            "Classificação do avanço comercial: 'reunião confirmada', 'reunião proposta sem aceite', "
            "'retorno com data combinado', 'envio de material solicitado', "
            "'sem próximo passo definido', 'sem interesse explícito' ou 'Não se aplica'"
        ),
    )
    responsavel: str | None = Field(default=None, description="Responsável pelo próximo passo")
    prazo: str | None = Field(default=None, description="Data e horário agendados ou 'não informado'")
    dados_extras: str | None = Field(default=None, description="Dados pendentes de confirmação")
    resumo: str | None = Field(default=None, description="Resumo executivo de até 80 palavras para colar no CRM")


class AnaliseCompletaModel(BaseModel):
    avaliacao_ia: AvaliacaoIAModel
    analise_perfil: AnalisePerfilModel
    analise_spin: AnaliseSpinModel
    analise_bant: AnaliseBantModel
    avaliacao_sdr: AvaliacaoSDRModel
    avaliacao_criterio: list[AvaliacaoCriterioItemModel] = Field(min_length=6, max_length=6)
    interlocutor: InterlocutorModel
    crm: CrmModel


# ==========================================================
# CLIENTE E CHAIN LANGCHAIN
# ==========================================================

MODELO_ANALISE = os.getenv("GEMINI_ANALISE_MODEL", "gemini-3.1-flash-lite")
GEMINI_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI API_KEY")

client = ChatGoogleGenerativeAI(
    model=MODELO_ANALISE,
    google_api_key=GEMINI_KEY,
    temperature=0.0,
    max_output_tokens=4096,
    max_retries=3,
)

structured_client = client.with_structured_output(
    AnaliseCompletaModel,
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


def _converter_para_float(valor: Any) -> float | None:
    """Converte números de formatos variados (string, int, float, moeda) com segurança."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    val_str = str(valor).strip()
    if not val_str or val_str.lower() in ("none", "null", "não se aplica", "nao se aplica", ""):
        return None
    val_str = re.sub(r"[^\d,\.]", "", val_str)
    if not val_str:
        return None
    if "," in val_str and "." in val_str:
        if val_str.rfind(",") > val_str.rfind("."):
            val_str = val_str.replace(".", "").replace(",", ".")
        else:
            val_str = val_str.replace(",", "")
    elif "," in val_str:
        val_str = val_str.replace(",", ".")
    try:
        return float(val_str)
    except Exception:
        return None


def _converter_para_int(valor: Any) -> int | None:
    """Converte inteiros de formatos variados com segurança."""
    if valor is None:
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float):
        return int(valor)
    digits = re.sub(r"\D", "", str(valor))
    if not digits:
        return None
    try:
        return int(digits)
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


def normalizar_origem_dado(origem: Any, eh_nao_avaliavel: bool = False) -> str:
    """Normaliza a origem do dado de perfil para uma das 4 categorias padrão."""
    if eh_nao_avaliavel or origem is None:
        return "não informado"
    val = str(origem).strip().lower()
    if any(k in val for k in ("confirmado pelo interlocutor", "confirmado pelo lead", "confirmado pelo cliente", "confirmado")):
        return "confirmado pelo interlocutor"
    if any(k in val for k in ("afirmado apenas pelo sdr", "afirmado pelo sdr", "sdr")):
        return "afirmado apenas pelo SDR"
    if any(k in val for k in ("inferência", "inferencia", "suposição", "suposicao", "indício", "indicio")):
        return "inferência plausível"
    return "não informado"


def normalizar_origem_faturamento(origem: Any, eh_nao_avaliavel: bool = False) -> str:
    """Normaliza a origem de faturamento incluindo 'calculado'."""
    if eh_nao_avaliavel or origem is None:
        return "não informado"
    val = str(origem).strip().lower()
    if "calculad" in val:
        return "calculado"
    if any(k in val for k in ("confirmado pelo interlocutor", "confirmado pelo lead", "confirmado pelo cliente", "confirmado")):
        return "confirmado pelo interlocutor"
    if any(k in val for k in ("afirmado apenas pelo sdr", "afirmado pelo sdr", "sdr")):
        return "afirmado apenas pelo SDR"
    if any(k in val for k in ("inferência", "inferencia", "suposição", "suposicao")):
        return "inferência plausível"
    return "não informado"


def normalizar_resultado_status_comercial(resultado: Any, eh_nao_avaliavel: bool = False) -> str:
    """Normaliza o status de qualificação da empresa para as 4 categorias oficiais."""
    if eh_nao_avaliavel:
        return "Dados insuficientes"
    if resultado is None:
        return "Dados insuficientes"
    val = str(resultado).strip()
    if not val:
        return "Dados insuficientes"
    val_norm = val.lower().rstrip(".").strip()

    if val_norm in ("dados insuficientes", "insuficiente", "não avaliável", "nao avaliavel", "não se aplica", "nao se aplica"):
        return "Dados insuficientes"
    if val_norm in ("perfil confirmado", "confirmado", "qualificado", "reunião agendada", "reuniao agendada", "reunião confirmada", "reuniao confirmada"):
        return "Perfil confirmado"
    if any(k in val_norm for k in ("fora do perfil", "desqualificado", "fora de perfil")):
        return "Fora do perfil desta campanha"
    if val_norm in ("perfil pendente", "pendente", "em análise", "em analise", "análise"):
        return "Perfil pendente"

    if val in RESULTADOS_STATUS_COMERCIAL_VALIDOS:
        return val

    return "Perfil pendente"


def normalizar_setor(setor: Any, eh_nao_avaliavel: bool = False) -> str:
    """
    Normaliza o setor da empresa contatada estritamente para um dos 3 valores permitidos:
    - 'industrial'
    - 'outro confirmado'
    - 'não informado'
    """
    if eh_nao_avaliavel or setor is None:
        return "não informado"
    val = str(setor).strip()
    if not val:
        return "não informado"

    val_norm = val.lower().rstrip(".").strip()

    termos_ausencia = {
        "não informado", "nao informado",
        "não se aplica", "nao se aplica",
        "não identificado", "nao identificado",
        "desconhecido", "indefinido",
        "nenhum", "nenhuma",
        "n/a", "null", "none",
        "sem informação", "sem informacao",
        "sem dados", "sem dado",
    }
    if val_norm in termos_ausencia or val_norm.startswith("não informado") or val_norm.startswith("nao informado"):
        return "não informado"

    termos_industriais = (
        "industr", "indústr",
        "metalúrg", "metalurg",
        "fábric", "fabric",
        "usinag",
        "manufatur",
        "químic", "quimic",
        "siderúrg", "siderurg",
        "caldeir",
        "autopeç", "autopec",
        "alimento", "alimentíc", "alimentic",
        "têxtil", "textil",
        "plástic", "plastic",
        "fundiç", "fundic",
        "embalag",
        "montadora",
        "automot",
        "farmacêut", "farmaceut",
    )
    if any(termo in val_norm for termo in termos_industriais):
        return "industrial"

    if val_norm == "industrial":
        return "industrial"

    if val_norm in ("outro confirmado", "outro"):
        return "outro confirmado"

    return "outro confirmado"


def normalizar_acao_crm(acao: Any, eh_nao_avaliavel: bool = False) -> str:
    """
    Normaliza deterministicamente a classificação do avanço comercial (CRM):
    - 'reunião confirmada'
    - 'reunião proposta sem aceite'
    - 'retorno com data combinado' (nova ligação agendada para conversar sobre marcar a reunião)
    - 'envio de material solicitado'
    - 'sem próximo passo definido'
    - 'sem interesse explícito'
    - 'Não se aplica' (chamadas sem diálogo substantivo / não avaliáveis)
    """
    if eh_nao_avaliavel:
        return "Não se aplica"
    if acao is None:
        return "sem próximo passo definido"
    val = str(acao).strip()
    if not val:
        return "sem próximo passo definido"
    val_norm = val.lower().rstrip(".").strip()

    if val_norm in ("não se aplica", "nao se aplica", "n/a", "none", "null"):
        return "Não se aplica"

    # 1. Reunião confirmada
    if any(k in val_norm for k in (
        "reunião confirmada", "reuniao confirmada",
        "reunião agendada", "reuniao agendada",
        "agendou reunião", "agendou reuniao",
        "confirmou reunião", "confirmou reuniao",
        "reuniao marcada", "reunião marcada",
    )):
        return "reunião confirmada"

    # 2. Reunião proposta sem aceite
    if any(k in val_norm for k in (
        "reunião proposta", "reuniao proposta",
        "proposta sem aceite",
        "proposta de reunião", "proposta de reuniao",
        "reunião oferecida", "reuniao oferecida",
        "aguardando aceite", "sem aceite",
    )):
        return "reunião proposta sem aceite"

    # 3. Retorno com data combinado (entendido como nova ligação para conversar sobre marcar a reunião)
    if any(k in val_norm for k in (
        "retorno com data", "retorno agendado", "retorno marcado",
        "retornar com data", "ligar com data", "retorno combinado",
        "nova ligação", "nova ligacao", "ligar dia", "retornar dia",
        "ligar na ", "retornar na ", "ligar amanhã", "ligar amanha",
    )):
        return "retorno com data combinado"
    if any(r in val_norm for r in ("retorno", "retornar", "ligar", "ligação", "ligacao")) and any(k in val_norm for k in ("data", "agendad", "combinad", "marcad", "hora", "horário", "horario", "dia")):
        return "retorno com data combinado"

    # 4. Envio de material solicitado
    if any(k in val_norm for k in (
        "envio de material", "enviar material", "material solicitado", "material",
        "apresentação", "apresentacao", "institucional",
        "enviar email", "enviar e-mail", "manda por email", "manda por e-mail",
        "mande por email", "mande por e-mail",
        "material por email", "material por e-mail",
    )):
        return "envio de material solicitado"

    # 5. Sem interesse explícito
    if any(k in val_norm for k in (
        "sem interesse", "desinteresse", "recusa",
        "não tem interesse", "nao tem interesse",
        "sem interesse explícito", "sem interesse explicito",
        "pediu para não ligar", "pediu para nao ligar",
        "descartad", "recusou contato",
    )):
        return "sem interesse explícito"

    # 6. Sem próximo passo definido
    if any(k in val_norm for k in (
        "sem próximo passo", "sem proximo passo",
        "indefinido", "em aberto",
        "recontatar", "follow-up", "follow up", "followup",
        "nova tentativa", "sem compromisso", "sem avanço", "sem avanco",
        "pendente", "a definir",
    )):
        return "sem próximo passo definido"

    # Checagem exata em ACOES_CRM_VALIDAS
    for acao_valida in ACOES_CRM_VALIDAS:
        if val_norm == acao_valida.lower():
            return acao_valida

    return "sem próximo passo definido"


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
        - Calcula faturamento_mensal = faturamento_anual / 12 quando período de 12 meses.
        - Aplica validação determinística estrita da qualificação comercial (status_comercial).
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
        av_ia["modelo_ia"] = MODELO_ANALISE

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

    # Detecção de chamadas não avaliáveis / não relevantes
    # Toda ligação não relevante (ligacao_relevante = 'n') tem notas estritamente NULL para o Power BI
    tem_pontos_positivos = any(n > 0 for n in notas_validas)
    eh_nao_avaliavel = (
        av_ia.get("ligacao_relevante") == "n"
        or feedback.lower().startswith("não avaliável")
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
        av_ia["resultado"] = "Dados insuficientes"
        resultado.setdefault("crm", {})["acao"] = "Não se aplica"

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
    crm["acao"] = normalizar_acao_crm(crm.get("acao"), eh_nao_avaliavel=eh_nao_avaliavel)
    for k in ("responsavel", "prazo", "dados_extras"):
        crm[k] = normalizar_texto_nao_se_aplica(crm.get(k))

    resumo_crm = (crm.get("resumo") or "").strip()
    if resumo_crm:
        palavras = resumo_crm.split()
        if len(palavras) > 80:
            crm["resumo"] = " ".join(palavras[:80]) + "..."
    else:
        crm["resumo"] = "Não se aplica"

    # 8. Análise de Perfil e Cálculo Determinístico de Faturamento
    perfil = resultado.setdefault("analise_perfil", {})
    if eh_nao_avaliavel:
        perfil["setor"] = "não informado"
        perfil["setor_origem"] = "não informado"
        perfil["regime_tributario"] = "Não se aplica"
        perfil["regime_origem"] = "não informado"
        perfil["faturamento_declarado_texto"] = "Não se aplica"
        perfil["faturamento_anual"] = None
        perfil["faturamento_mensal"] = None
        perfil["periodo_meses"] = None
        perfil["faturamento_origem"] = "não informado"
        perfil["faturamento_regra"] = "nao_informado"
        perfil["detalhes_faturamento"] = "Não se aplica"
    else:
        perfil["setor"] = normalizar_setor(perfil.get("setor"), eh_nao_avaliavel=False)
        perfil["setor_origem"] = normalizar_origem_dado(perfil.get("setor_origem"), eh_nao_avaliavel=False)
        perfil["regime_origem"] = normalizar_origem_dado(perfil.get("regime_origem"), eh_nao_avaliavel=False)
        perfil["regime_tributario"] = normalizar_texto_nao_se_aplica(perfil.get("regime_tributario"))
        perfil["faturamento_declarado_texto"] = normalizar_texto_nao_se_aplica(perfil.get("faturamento_declarado_texto"))
        perfil["detalhes_faturamento"] = normalizar_texto_nao_se_aplica(perfil.get("detalhes_faturamento"))

        fat_anual = _converter_para_float(perfil.get("faturamento_anual"))
        fat_mensal = _converter_para_float(perfil.get("faturamento_mensal"))
        periodo = _converter_para_int(perfil.get("periodo_meses"))

        perfil["faturamento_anual"] = fat_anual
        perfil["periodo_meses"] = periodo

        # Regra 4: Cálculo determinístico da média mensal a partir de anual de 12 meses
        if fat_anual is not None and fat_anual > 0 and periodo == 12:
            calc_mensal = round(fat_anual / 12.0, 2)
            perfil["faturamento_mensal"] = calc_mensal
            perfil["faturamento_regra"] = "calculado_12_meses"
            perfil["faturamento_origem"] = "calculado"
            if perfil["detalhes_faturamento"] in ("Não se aplica", "", None):
                perfil["detalhes_faturamento"] = (
                    f"Média mensal de R$ {calc_mensal:,.2f} calculada deterministicamente a partir de "
                    f"faturamento anual de 12 meses (R$ {fat_anual:,.2f})."
                )
        elif fat_mensal is not None and fat_mensal > 0 and (periodo is None or periodo == 1):
            perfil["faturamento_mensal"] = fat_mensal
            perfil["faturamento_regra"] = "declarado_mensal"
            perfil["faturamento_origem"] = normalizar_origem_faturamento(perfil.get("faturamento_origem"))
        elif periodo is not None and periodo != 12 and fat_anual is not None:
            # Período ambíguo ou diferente de 12 meses
            perfil["faturamento_mensal"] = None
            perfil["faturamento_regra"] = "nao_confirmado"
            perfil["faturamento_origem"] = "não informado"
        else:
            perfil["faturamento_mensal"] = fat_mensal
            perfil["faturamento_regra"] = "declarado_mensal" if fat_mensal else "nao_informado"
            perfil["faturamento_origem"] = normalizar_origem_faturamento(perfil.get("faturamento_origem")) if fat_mensal else "não informado"

    # 9. Coerção determinística estrita de status comercial (resultado)
    raw_res = str(av_ia.get("resultado") or "").strip().lower()
    if eh_nao_avaliavel:
        av_ia["resultado"] = "Dados insuficientes"
    else:
        # Se IA indicou reunião confirmada em qualquer campo, liga a flag reuniao_confirmada
        if crm.get("acao") == "reunião confirmada" or any(k in raw_res for k in ("reunião agendada", "reuniao agendada", "reunião confirmada", "reuniao confirmada")):
            av_ia["reuniao_confirmada"] = "s"

        regime_str = str(perfil.get("regime_tributario") or "").strip().lower()
        regime_conf = perfil.get("regime_origem") == "confirmado pelo interlocutor"
        eh_lucro_real = "lucro real" in regime_str

        fat_mensal_val = perfil.get("faturamento_mensal")
        fat_orig = perfil.get("faturamento_origem")
        fat_conf = fat_orig in ("confirmado pelo interlocutor", "calculado")
        fat_minimo_ok = fat_mensal_val is not None and fat_mensal_val >= 1000000.0

        # Regra de descarte explícito
        outro_regime_conf = regime_conf and not eh_lucro_real and any(r in regime_str for r in ("simples", "presumido", "mei"))
        fat_abaixo_conf = fat_conf and fat_mensal_val is not None and fat_mensal_val < 1000000.0

        if outro_regime_conf or fat_abaixo_conf:
            av_ia["resultado"] = "Fora do perfil desta campanha"
        elif eh_lucro_real and regime_conf and fat_minimo_ok and fat_conf:
            av_ia["resultado"] = "Perfil confirmado"
        else:
            # Qualquer ausência de confirmação não desqualifica, mantém pendente
            av_ia["resultado"] = "Perfil pendente"

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
    Submete a transcrição revisada ao Gemini e devolve o dicionário
    completo com as 8 chaves relacionais padronizadas.
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
