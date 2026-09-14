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
    timeout=600
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

    TEXTO_TESTE = "Escritório Sul-América agradece sua ligação. Digite quatro para despassante. Cinco contabilidade. Seis. Departamento pessoal. Ou aguarde para ser atendido. Sul-América. Olá, boa tarde. Tudo bem? Tudo. Que bom. Eu falo com quem, príncipe, beleza? Andréia. Andréia, eu me chamo Mayra. Fala aqui das empresas Falavinia Next. Eu gostaria de conversar com vocês aí, de escritório, a respeito de uma proposta de parceria. Se ação seria contigo mesmo, ou tem outra pessoa aí com quem eu posso tratar? Não tenho sentido. Acredito que você ainda não ouviu falar referente a Falavinia, certo? Não. Nós somos uma empresa que estamos há quase 50 anos aí no mercado, uma empresa de assessoria tributária, mais em específico ali na parte de recuperação de créditos tributários. E hoje nós buscamos por parceiros estratégicos, como contadores, advogados, pessoas que têm um grande network em tanto com empresas quanto com empresários. E aí, o intuito da minha ligação seria a gente andar ali 10 minutos contigo, nessa semana ou na próxima, para a gente poder apresentar esse canal de parcerias para vocês. E vocês avaliarem se faz sentido, se a gente tem alguma sinergia ali, sabe? Você não pode passar por e-mail? Consigo sim. Qual que seria o e-mail para a gente, beleza? Tá bom. E-S-L-A-E-S-U-L-I-A-N Arrota bom. Ponto com ponto B? Isso. Perfeito. Então, responsável é E-S-L-A? Isso? Não. É o nome do território. Ah, tá. Muito obrigada, viu? Tá bom. Se lente e tache. Tchau, tchau."
    resultado = revisar_texto(TEXTO_TESTE)
    print(resultado)