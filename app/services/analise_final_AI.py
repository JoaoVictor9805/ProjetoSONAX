import os

from dotenv import load_dotenv
from typing import Literal

from pydantic import BaseModel, Field

from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate

from app.config.prompts import prompt_analise


load_dotenv()


# ==========================================================
# SCHEMA
# ==========================================================

NomeCriterio = Literal[
    "chamar pelo nome",
    "agir com empatia",
    "ouvir com atencao",
    "eficiencia operacional",
    "surpreender",
]


class Criterio(BaseModel):

    criterio: NomeCriterio

    nota_criterio: int | None = Field(
        default=None,
        ge=0,
        le=10,
        description=(
            "Nota inteira entre 0 e 10. A nota começa em 10 e vai diminuindo progressivamente por deslize. "
            "Atribua null quando não for possível avaliar o critério a partir do contexto da chamada."
        ),
    )

    justificativa_criterio: str | None = Field(
        default=None,
        description=(
            "Justificativa curta e objetiva baseada exclusivamente na transcrição. "
            "Quando nota_criterio = null, a justificativa deve ser obrigatoriamente e exatamente: "
            "'[Não houve contexto suficiente para a avaliação desse critério]'."
        ),
    )


class AnaliseLigacao(BaseModel):

    nota_final: int | None = Field(
        default=None,
        ge=0,
        le=10,
        description=(
            "Nota geral da ligação recalculada pela aplicação. Use null se a chamada for URA ou inválida."
        ),
    )

    feedback_geral: str | None = Field(
        default=None,
        description=(
            "Feedback sobre o atendimento. Em caso de URA ou chamada não avaliável, escreva exatamente: "
            "'[A chamada retrata a fala de uma Unidade de resposta audível (URA)]' ou "
            "'[A chamada é inválida para a avalião]' conforme a situação."
        ),
    )

    titulo: str | None = Field(
        default=None,
        max_length=255,
        description=(
            "Título curto e informativo (4 a 7 palavras) sobre o tema principal da chamada, "
            "adequado para busca e identificação rápida em relatórios do Power BI. "
            "Ex: 'Dúvida Tributária - Contato Financeiro', 'Solicitação de 2ª Via de Boleto'."
        ),
    )

    resumo_chamada: str | None = Field(
        default=None,
        description=(
            "Resumo principal executivo da chamada (limite de até 340 caracteres) sobre o motivo do contato, "
            "a postura do atendente e o desfecho da ligação (ou null se for URA/inválida)."
        ),
    )

    pontos_fortes: str | None = Field(
        default=None,
        description=(
            "Pontos fortes e boas práticas demonstradas na ligação (limite de até 210 caracteres) "
            "(ou null se não houver destaques ou se for URA/inválida)."
        ),
    )

    fragilidades: str | None = Field(
        default=None,
        description=(
            "Pontos fracos, desvios pontuais ou deslizes observados na ligação (limite de até 210 caracteres) "
            "(ou null se não houver ou se for URA/inválida)."
        ),
    )

    oportunidades: str | None = Field(
        default=None,
        description=(
            "Oportunidades práticas e pontuais de melhoria para o atendente (limite de até 280 caracteres) "
            "(ou null se não houver ou se for URA/inválida)."
        ),
    )

    criterios: list[Criterio] = Field(
        min_length=5,
        max_length=5,
        description=(
            "Exatamente cinco critérios, utilizando uma única vez "
            "cada um dos critérios definidos."
        ),
    )



# ==========================================================
# MODELO
# ==========================================================
"""
client = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash-lite",
    google_api_key=os.getenv("GEMINI_API_KEY"),

    # Mantém o comportamento mais determinístico.
    temperature=0,

    max_output_tokens=4096,
    max_retries=3,
)
"""

client = ChatOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    model="openai/gpt-4o-mini",
    temperature=0.0,  # Zero para garantir a precisão estrutural das chaves
    max_tokens=1500,  # Margem segura para devolução completa do JSON
    max_retries=3,
)

# ==========================================================
# STRUCTURED OUTPUT
# ==========================================================

structured_client = client.with_structured_output(
    AnaliseLigacao,
    method="json_schema",
)


# ==========================================================
# PROMPT
# ==========================================================

prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            prompt_analise,
        ),
        (
            "user",
            """
TRANSCRIÇÃO DA LIGAÇÃO A SER AVALIADA:

{ligacao}
""",
        ),
    ]
)


# ==========================================================
# CHAIN
# ==========================================================

chain = prompt | structured_client


# ==========================================================
# CÁLCULO DA NOTA FINAL
# ==========================================================

def calcular_nota_final(resultado: dict) -> dict:

    notas = [
        criterio["nota_criterio"]
        for criterio in resultado.get("criterios", [])
        if criterio.get("nota_criterio") is not None
    ]

    if not notas:
        resultado["nota_final"] = None
        return resultado

    media = sum(notas) / len(notas)

    resultado["nota_final"] = round(media)

    return resultado


# ==========================================================
# FUNÇÃO PRINCIPAL
# ==========================================================

def analisar_ligacao(ligacao: str) -> dict:

    resposta = chain.invoke(
        {
            "ligacao": ligacao
        }
    )

    # Converte para dict caso seja um modelo Pydantic, ou preserva se já for dict
    if isinstance(resposta, BaseModel):
        resultado = resposta.model_dump()
    elif isinstance(resposta, dict):
        resultado = resposta
    else:
        resultado = dict(resposta)

    feedback = (resultado.get("feedback_geral") or "").strip()

    # Tratamento de URA ou chamadas inválidas
    if "[A chamada retrata a fala de uma Unidade de resposta audível (URA)]" in feedback:
        resultado["feedback_geral"] = "[A chamada retrata a fala de uma Unidade de resposta audível (URA)]"
        resultado["nota_final"] = None
        resultado["resumo_chamada"] = None
        resultado["pontos_fortes"] = None
        resultado["fragilidades"] = None
        resultado["oportunidades"] = None
        for crit in resultado.get("criterios", []):
            crit["nota_criterio"] = None
            crit["justificativa_criterio"] = "[Não houve contexto suficiente para a avaliação desse critério]"

    elif "[A chamada é inválida para a avali" in feedback or "inválida para a avali" in feedback.lower():
        resultado["feedback_geral"] = "[A chamada é inválida para a avalião]"
        resultado["nota_final"] = None
        resultado["resumo_chamada"] = None
        resultado["pontos_fortes"] = None
        resultado["fragilidades"] = None
        resultado["oportunidades"] = None
        for crit in resultado.get("criterios", []):
            crit["nota_criterio"] = None
            crit["justificativa_criterio"] = "[Não houve contexto suficiente para a avaliação desse critério]"

    # Regra: quando nota_criterio = null, justificativa obrigatória padronizada
    for criterio in resultado.get("criterios", []):
        if criterio.get("nota_criterio") is None:
            criterio["justificativa_criterio"] = "[Não houve contexto suficiente para a avaliação desse critério]"

    # Limites estritos de caracteres (salvaguarda de comprimento)
    if resultado.get("resumo_chamada") and len(resultado["resumo_chamada"]) > 340:
        resultado["resumo_chamada"] = resultado["resumo_chamada"][:337] + "..."
    if resultado.get("pontos_fortes") and len(resultado["pontos_fortes"]) > 210:
        resultado["pontos_fortes"] = resultado["pontos_fortes"][:207] + "..."
    if resultado.get("fragilidades") and len(resultado["fragilidades"]) > 210:
        resultado["fragilidades"] = resultado["fragilidades"][:207] + "..."
    if resultado.get("oportunidades") and len(resultado["oportunidades"]) > 280:
        resultado["oportunidades"] = resultado["oportunidades"][:277] + "..."

    # Calcula deterministicamente a nota final
    resultado = calcular_nota_final(resultado)

    return resultado


# ==========================================================
# TESTE
# ==========================================================

if __name__ == "__main__":

    LIGACAO_TESTE = """
URA: Olá, bem-vindo à empresa. Digite uma das opções para atendimento.

Agente (Falavinha): Boa tarde, Maria, tudo bem com você?

Cliente (Empresa): Tudo bem.

Agente (Falavinha): Que ótimo. Estou entrando em contato porque
identificamos algumas oportunidades tributárias para a empresa de vocês.

Cliente (Empresa): Entendi. Essa questão seria mais com o nosso financeiro.

Agente (Falavinha): Perfeito. Você consegue me informar quem é a pessoa
responsável por essa área?

Cliente (Empresa): Pode falar com a Jaqueline.

Agente (Falavinha): Perfeito. Você teria um telefone ou WhatsApp dela?

Cliente (Empresa): Tenho sim.
"""

    resultado = analisar_ligacao(LIGACAO_TESTE)

    print(resultado)