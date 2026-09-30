# -*- coding: utf-8 -*-
"""
============================================================================
Serviço de Revisão Textual e Diarização com IA do SONAX.

Responsabilidades:
    1. Segmentação e identificação de locutores (diarização textual):
       - URA, Agente (Falavinha Next) e Cliente.
    2. Correção de pontuação, concordância e ruídos fonéticos do ASR contínuo.
    3. Preservação estrita do conteúdo e vocabulário original da chamada
       (sem alucinar diálogos nem remover termos de negócio).
    4. Limpeza de artefatos, tags especiais de parada e rótulos órfãos pós-processamento.
    5. Integração com modelo LLM via LangChain (Qwen 30B Instruct via OpenRouter).
============================================================================
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.config.prompts import prompt_revisao

load_dotenv()

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
    api_key=os.getenv("OPENROUTER_API_KEY") or "sk-dummy-key",
    model="qwen/qwen3-30b-a3b-instruct-2507",
    temperature=0.0,  # Zero para evitar criação de diálogos falsos
    max_tokens=2000,  # Margem segura para devolver a transcrição inteira
    max_retries=3,
)


import json
import re

prompt = ChatPromptTemplate.from_template(prompt_revisao)

chain = prompt | client | StrOutputParser()


def montar_fonte_dados(
    texto_google: str | None, 
    nome_diarizado: str | None = None
) -> str:
    """Monta a fonte de dados consolidada para a tabela empresa."""
    partes = []
    txt_g = (texto_google or "").strip()
    partes.append(f"[GOOGLE]\n{txt_g if txt_g else 'Não encontrado'}")

    txt_d = (nome_diarizado or "").strip()
    partes.append(f"[DIARIZAÇÃO]\n{txt_d if txt_d else 'Não identificado no diálogo'}")

    return "\n\n".join(partes)


def parsear_resposta_revisao(resultado_raw: str) -> tuple[str, str]:
    """Faz o parse seguro do JSON retornado pelo modelo de revisão.

    Retorna (empresa, revisao).
    """
    if not resultado_raw or not resultado_raw.strip():
        return "Não encontrado", ""

    texto = resultado_raw.strip()
    # Remove eventuais blocos de código markdown ```json ... ```
    if texto.startswith("```"):
        texto = re.sub(r"^```(?:json)?\s*", "", texto, flags=re.IGNORECASE)
        texto = re.sub(r"\s*```$", "", texto)

    empresa = "Não encontrado"
    revisao = ""

    try:
        dados = json.loads(texto)
        if isinstance(dados, list):
            for item in dados:
                if isinstance(item, dict):
                    if "Empresa" in item:
                        empresa = str(item["Empresa"]).strip() or "Não encontrado"
                    elif "empresa" in item:
                        empresa = str(item["empresa"]).strip() or "Não encontrado"
                    if "Revisao" in item:
                        revisao = str(item["Revisao"]).strip()
                    elif "revisao" in item:
                        revisao = str(item["revisao"]).strip()
        elif isinstance(dados, dict):
            empresa = str(dados.get("Empresa") or dados.get("empresa") or "Não encontrado").strip()
            revisao = str(dados.get("Revisao") or dados.get("revisao") or "").strip()
    except Exception:
        # Fallback via regex
        match_emp = re.search(r'"Empresa"\s*:\s*"([^"]+)"', texto, re.IGNORECASE)
        if match_emp:
            empresa = match_emp.group(1).strip()

        match_rev = re.search(r'"Revisao"\s*:\s*"([\s\S]+?)"\s*\}', texto, re.IGNORECASE)
        if match_rev:
            revisao = match_rev.group(1).encode().decode("unicode_escape", errors="ignore").strip()
        else:
            # Caso extremo: o modelo devolveu o texto diretamente sem JSON
            revisao = texto

    # Limpeza de marcadores especiais do modelo
    linhas_limpas = []
    for linha in revisao.splitlines():
        linha_strip = linha.strip()
        if linha_strip.startswith("<") and linha_strip.endswith(">"):
            continue
        linhas_limpas.append(linha)

    revisao_final = "\n".join(linhas_limpas).strip()
    revisao_final = re.sub(
        r"\n\s*(?:URA|Agente\s*\([^)]*\)|Cliente\s*(?:\([^)]*\))?):\s*$",
        "",
        revisao_final,
        flags=re.IGNORECASE,
    ).strip()

    return empresa, revisao_final


def revisar_texto(
    transcricao: str,
    *,
    texto_copiado_google: str | None = None,
    nome_atendente: str | None = None,
) -> dict[str, str]:
    """Executa a triangulação e revisão textual com IA.

    Retorna um dicionário:
        {
            "empresa": str,
            "revisao": str,
            "fonte_dados": str
        }
    """
    atendente_str = nome_atendente.strip() if nome_atendente and nome_atendente.strip() else "Não informado"
    google_str = texto_copiado_google.strip() if texto_copiado_google and texto_copiado_google.strip() else "Não encontrado"

    resultado_raw = chain.invoke({
        "texto_copiado_google": google_str,
        "transcricao_bruta": transcricao,
        "nome_agente": atendente_str,
    })

    empresa, revisao = parsear_resposta_revisao(resultado_raw)

    # Tenta extrair menção ao nome da empresa rotulada nos turnos do Cliente
    nome_diarizado = None
    match_cliente = re.search(r"Cliente\s*\(([^)]+)\)", revisao, re.IGNORECASE)
    if match_cliente:
        rotulo_extraido = match_cliente.group(1).strip()
        if rotulo_extraido.lower() != "cliente":
            nome_diarizado = rotulo_extraido

    fonte_dados = montar_fonte_dados(google_str, nome_diarizado or empresa)

    return {
        "empresa": empresa,
        "revisao": revisao,
        "fonte_dados": fonte_dados,
    }


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
    resultado = revisar_texto(TEXTO_TESTE, texto_copiado_google="Auto Peças Brasil Curitiba Telefone 41 3310-1010", nome_atendente="Lucas")
    print(resultado)

