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
    model="qwen/qwen3-30b-a3b-instruct-2507",
    temperature=0.0,  # Zero para evitar criação de diálogos falsos
    max_tokens=2000,  # Margem segura para devolver a transcrição inteira
    max_retries=3,
)


prompt = ChatPromptTemplate.from_messages([
    ("system", prompt_revisao),
    ("user", "INFORMAÇÕES DA LIGAÇÃO:\n- Atendente/Agente da Falavinha Next: {nome_atendente}\n\nTRANSCRIÇÃO DA CHAMADA (TEXTO CONTÍNUO):\n\n{transcricao}")
])

chain = prompt | client | StrOutputParser()

def revisar_texto(transcricao: str, nome_atendente: str | None = None) -> str:
    atendente_str = nome_atendente.strip() if nome_atendente and nome_atendente.strip() else "Não informado"
    resultado = chain.invoke({
        "transcricao": transcricao,
        "nome_atendente": atendente_str,
    })

    if not resultado:
        return ""

    linhas_limpas = []
    for linha in resultado.splitlines():
        linha_strip = linha.strip()
        # Remove eventuais marcadores ou tags de parada especiais do modelo (ex: <CPA_DONE>)
        if linha_strip.startswith("<") and linha_strip.endswith(">"):
            continue
        linhas_limpas.append(linha)

    texto_final = "\n".join(linhas_limpas).strip()
    # Remove rótulos órfãos que possam ter ficado no final sem conteúdo
    import re
    texto_final = re.sub(
        r"\n\s*(?:URA|Agente\s*\([^)]*\)|Cliente\s*(?:\([^)]*\))?):\s*$",
        "",
        texto_final,
        flags=re.IGNORECASE,
    ).strip()

    return texto_final

if __name__ == "__main__":
    TEXTO_TESTE = (
        "Auto Peças Brasil, bom dia. "
        "Olá, bom dia! Aqui é o Lucas da Falavinha Next, tudo bem? Gostaria de falar com o responsável pelo setor financeiro ou contábil, por gentileza. "
        "Um instante, vou transferir... Alô, quem fala? "
        "Olá, aqui é o Lucas da Falavinha Next, tudo bem? Falo com o responsável financeiro da Auto Peças Brasil? "
        "Sim, é o Eduardo, sou sócio e cuido do financeiro. "
        "Perfeito, Eduardo. Nós identificamos oportunidades relevantes de recuperação de créditos tributários para empresas do segmento de autopeças e eu gostaria de agendar uma reunião rápida de 10 a 12 minutos com nosso especialista tributário para apresentar essas oportunidades. Como está sua agenda nesta quarta-feira às 15 horas? "
        "Quarta às 15h fica bom para mim, pode agendar sim. "
        "Excelente Eduardo, vou enviar o convite para o seu e-mail. Tenha um ótimo dia!"
    )
    resultado = revisar_texto(TEXTO_TESTE, nome_atendente="Lucas")
    print(resultado)
