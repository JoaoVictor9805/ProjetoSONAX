import os
from dotenv import load_dotenv
from app.config.prompts import prompt_analise

load_dotenv()

from langchain_google_genai import ChatGoogleGenerativeAI
# from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser


client = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash-lite",
    google_api_key=os.getenv("GEMINI_API_KEY"),
    max_output_tokens=4096,
    max_retries = 3
)

"""
client = ChatGroq (
    model="openai/gpt-oss-120b",
    temperature=0.5,
    max_tokens=4096,
    max_retries=3
)
"""

prompt = ChatPromptTemplate.from_messages([
  ("system", prompt_analise),
  ("user", "TRANSCRIÇÃO DA LIGAÇÂO A SER AVALIADA: \n \n{ligacao}")
])

chain = prompt | client | JsonOutputParser()

def analisar_ligacao(ligacao: str) -> dict:
    return chain.invoke({"ligacao": ligacao})


if __name__ == "__main__":

    LIGACAO_TESTE = "AAAAAAAAAAAAAAAAAAAAAAA"

    resultado = analisar_ligacao(LIGACAO_TESTE)
    print(repr(resultado))