import os

from dotenv import load_dotenv
from typing import Literal

from pydantic import BaseModel, Field

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
            "Nota inteira entre 0 e 10. "
            "Use null quando não houver evidência suficiente "
            "para avaliar o critério."
        ),
    )

    justificativa_criterio: str | None = Field(
        default=None,
        description=(
            "Justificativa curta e objetiva baseada exclusivamente "
            "na transcrição. Use null quando o critério não puder "
            "ser avaliado."
        ),
    )


class AnaliseLigacao(BaseModel):

    nota_final: int | None = Field(
        default=None,
        ge=0,
        le=10,
        description=(
            "Nota geral da ligação. "
            "Esse valor será recalculado pela aplicação."
        ),
    )

    feedback_geral: str | None = Field(
        default=None,
        description=(
            "Feedback curto e objetivo sobre os principais pontos "
            "observados no comportamento do agente."
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

client = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash-lite",
    google_api_key=os.getenv("GEMINI_API_KEY"),

    # Mantém o comportamento mais determinístico.
    temperature=0,

    max_output_tokens=4096,
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
        for criterio in resultado["criterios"]
        if criterio["nota_criterio"] is not None
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