import os
from dotenv import load_dotenv

load_dotenv()

from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# Obtém a chave da API a partir do .env (suporta GEMINI_API_KEY e GOOGLE_API_KEY)

# Configura o modelo do Gemini
client = ChatNVIDIA(
    model="deepseek-ai/deepseek-v4-flash-0731", 
    api_key=os.getenv("NVIDIA_API_KEY"),
    temperature=1,
    top_p=0.95,
    max_completion_tokens=16384,
    seed=42,
    timeout=120
)

SYSTEM_PROMPT = """

Você é um sistema especializado em corrigir transcrições automáticas de áudio em português brasileiro.
Corrija SOMENTE erros provavelmente causados pelo ASR; preserve ao máximo o texto original.
Não reescreva, resuma, formalize, interprete, reorganize ou substitua palavras por sinônimos.
Corrija apenas erros evidentes de reconhecimento, incluindo palavras, nomes, termos técnicos, números e repetições artificiais.
Use o contexto de toda a transcrição para identificar erros, mas nunca invente informações.
Se um termo aparecer corretamente em outro trecho, use-o como referência para corrigir ocorrências inconsistentes do mesmo termo.
Não corrija erros gramaticais ou formas informais quando puderem representar a fala original.
Não altere números por estimativa; se um identificador não puder ser determinado com segurança, use um marcador apropriado.
A gravação automática inicial pode não ter relação com o restante da ligação; não use o contexto posterior para corrigi-la.
Faça o mínimo de alterações possível; na dúvida, mantenha o original. Retorne SOMENTE a transcrição corrigida.
Qualquer coisa parecida com "Salavinha", "saladinha", "Fala Vinha" provavelmente representa o nome da empresa? Falavinha Next.
"""

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("user", "TRANSCRIÇÃO A SER REVISADA:\n\n{transcricao}")
])

chain = prompt | client | StrOutputParser()

def revisar_texto(transcricao: str) -> str:
    return chain.invoke({"transcricao": transcricao})

if __name__ == "__main__":

    """
    TEXTO_TESTE = "Olá tudo tudo tudo tudo tudo tudo tudo tudo tudo bem? Aqui é o João da Salavinha Next"
    resultado = revisar_texto(TEXTO_TESTE)
    print(resultado)
    """