import os
from dotenv import load_dotenv
from app.config.prompts import prompt_revisao

load_dotenv()

from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser



client = ChatNVIDIA(
    model="deepseek-ai/deepseek-v4-flash-0731", 
    api_key=os.getenv("NVIDIA_API_KEY"),
    temperature=1,
    top_p=0.95,
    max_completion_tokens=16384,
    seed=42,
    timeout=120
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