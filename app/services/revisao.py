import os
from dotenv import load_dotenv
from app.config.prompts2 import prompt_revisao

load_dotenv()

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

client = ChatGoogleGenerativeAI(
    model="gemini-3.1-flash-lite",
    google_api_key=os.getenv("GEMINI_API_KEY"),
    max_output_tokens=4096,
)

prompt = ChatPromptTemplate.from_messages([
    ("system", prompt_revisao),
    ("user", "TRANSCRIÇÃO A SER REVISADA:\n\n{transcricao}")
])

chain = prompt | client | StrOutputParser()

def revisar_texto(transcricao: str) -> str:
    return chain.invoke({"transcricao": transcricao})

if __name__ == "__main__":

    TEXTO_TESTE = "Olá, tudo bem?"
    resultado = revisar_texto(TEXTO_TESTE)
    print(resultado)