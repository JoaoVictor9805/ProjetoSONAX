import os
from dotenv import load_dotenv
from app.config.prompts import prompt_revisao

load_dotenv()

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

"""
client = ChatGoogleGenerativeAI (
    model="gemini-3.1-flash-lite",
    google_api_key=os.getenv("GEMINI_API_KEY"),
    max_output_tokens=4096,
    max_retries=3
)
"""

client = ChatOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    model="nex-agi/nex-n2.5-mini:free", # Modelo gratuito confiável via OpenRouter
    max_tokens=4096,
    max_retries=3
)


prompt = ChatPromptTemplate.from_messages([
    ("system", prompt_revisao),
    ("user", "INFORMAÇÕES DA LIGAÇÃO:\n- Atendente/Agente da Falavinha Next: {nome_atendente}\n\nTRANSCRIÇÃO DIARIZADA (POR LOCUTOR):\n\n{transcricao}")
])

chain = prompt | client | StrOutputParser()

def revisar_texto(transcricao: str, nome_atendente: str | None = None) -> str:
    atendente_str = nome_atendente.strip() if nome_atendente and nome_atendente.strip() else "Não informado"
    return chain.invoke({
        "transcricao": transcricao,
        "nome_atendente": atendente_str,
    })

if __name__ == "__main__":
    TEXTO_TESTE = "SPEAKER_00 (0.00s - 2.50s): Bom dia, Falavinha Next, João falando.\nSPEAKER_01 (2.60s - 5.00s): Olá João, gostaria de um suporte."
    resultado = revisar_texto(TEXTO_TESTE, nome_atendente="João")
    print(resultado)
