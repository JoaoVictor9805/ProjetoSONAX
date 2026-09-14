import os
from dotenv import load_dotenv

load_dotenv()

from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser



client = ChatNVIDIA(
  model="deepseek-ai/deepseek-v4-flash-0731",
  api_key=os.getenv("NVIDIA_API_KEY"),
  temperature=1,
  top_p=0.95,
  max_completion_tokens=16384,
  seed=42,
)

SYSTEM_PROMPT = """Você avalia ligações de call center.
Responda SOMENTE com um JSON válido, sem crases, sem texto antes ou depois, no formato:
{{"nota": <número de 0 a 10>, "resumo": "<string curta>"}}"""

prompt = ChatPromptTemplate.from_messages([
  ("system", SYSTEM_PROMPT),
  ("user", "TRANSCRIÇÃO DA LIGAÇÂO A SER AVALIADA: \n \n{ligacao}")
])

chain = prompt | client | JsonOutputParser()

def analisar_ligacao(ligacao: str) -> dict:
    return chain.invoke({"ligacao": ligacao})


if __name__ == "__main__":

    LIGACAO_TESTE = "Olá tudo bem? Como você está? Consegue me passar as informações nome e cpf por gentileza"

    resultado = analisar_ligacao(LIGACAO_TESTE)
    print(repr(resultado))