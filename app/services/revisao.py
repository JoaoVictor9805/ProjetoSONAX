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
    5. Integração com modelo LLM via LangChain (DeepSeek V4 Flash via OpenRouter).
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
from app.services.sanitizador import sanitizar_texto_estrangeiro

load_dotenv()

MODELO_REVISAO = os.getenv(
    "REVISAO_MODEL",
    "deepseek/deepseek-v4-flash-0731",
)
MODELO_REVISAO_FALLBACK_1 = os.getenv(
    "REVISAO_MODEL_FALLBACK_1",
    "deepseek/deepseek-v4.1-flash",
)
MODELO_REVISAO_FALLBACK_2 = os.getenv(
    "REVISAO_MODEL_FALLBACK_2",
    "gemini-3.1-flash-lite",
)

client = ChatOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY") or "sk-dummy-key",
    model=MODELO_REVISAO,
    temperature=0.0,  # Zero para evitar criação de diálogos falsos
    max_tokens=8192,
    extra_body={"reasoning": {"effort": "low"}},
    max_retries=2,
)

client_fallback_1 = ChatOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY") or "sk-dummy-key",
    model=MODELO_REVISAO_FALLBACK_1,
    temperature=0.0,
    max_tokens=8192,
    extra_body={"reasoning": {"effort": "low"}},
    max_retries=2,
)

client_fallback_2 = ChatGoogleGenerativeAI(
    model=MODELO_REVISAO_FALLBACK_2,
    google_api_key=os.getenv("GEMINI_API_KEY") or "sk-dummy-key",
    temperature=0.0,
    max_output_tokens=8192,
)


import json
import re

prompt = ChatPromptTemplate.from_template(prompt_revisao)

chain = prompt | client | StrOutputParser()


def montar_fonte_dados(
    revisao_texto: str | None = None, 
    nome_diarizado: str | None = None,
    *,
    tem_interlocutor: bool | None = None,
    tem_agente: bool | None = None,
) -> str:
    """Monta a fonte de dados consolidada para a tabela empresa.

    Identifica as fontes primárias na ligação que forneceram/confirmaram 
    informações sobre a empresa:
    - 'Interlocutor / Agente' (diálogo com participação de ambos)
    - 'Interlocutor' (informação obtida pelo cliente/contato)
    - 'Agente' (menção isolada do SDR/agente)
    - 'Não identificado' (sem diálogo conclusivo ou chamada não atendida)
    """
    texto = (revisao_texto or "").strip()

    interlocutor = tem_interlocutor
    agente = tem_agente

    if interlocutor is None:
        interlocutor = bool(
            re.search(r"^\s*Cliente\b", texto, re.MULTILINE | re.IGNORECASE)
            or re.search(r"\bCliente\s*\(", texto, re.IGNORECASE)
        )

    if agente is None:
        agente = bool(
            re.search(r"^\s*Agente\b", texto, re.MULTILINE | re.IGNORECASE)
            or re.search(r"\bAgente\s*\(", texto, re.IGNORECASE)
        )

    fontes = []
    if interlocutor:
        fontes.append("Interlocutor")
    if agente:
        fontes.append("Agente")

    if fontes:
        return " / ".join(fontes)

    # Se não houver marcadores claros mas o nome diarizado estiver preenchido e válido
    if (
        nome_diarizado
        and nome_diarizado.strip()
        and nome_diarizado.strip().lower() not in ("não identificado", "não encontrado", "nao encontrado")
    ):
        return "Interlocutor"

    return "Não identificado"


def corrigir_mojibake(texto: str) -> str:
    """Detecta e recupera textos UTF-8 corrompidos por interpretação em Latin-1/CP1252 (Mojibake)."""
    if not texto or ("Ã" not in texto and "Â" not in texto):
        return texto
    try:
        return texto.encode("latin1").decode("utf-8")
    except Exception:
        def _desfazer(m):
            try:
                return m.group(0).encode("latin1").decode("utf-8")
            except Exception:
                return m.group(0)
        return re.sub(r"[\xc2-\xf4][\x80-\xbf]+", _desfazer, texto)


def parsear_resposta_revisao(resultado_raw: str) -> tuple[str, str]:
    """Faz o parse seguro do JSON retornado pelo modelo de revisão.

    Retorna (empresa, revisao).
    """
    if not resultado_raw or not resultado_raw.strip():
        return "Não encontrado", ""

    texto = resultado_raw.strip()

    # Remove eventuais blocos de raciocínio (<think>...</think>)
    texto = re.sub(r"<think>[\s\S]*?</think>", "", texto).strip()

    # Extrai o conteúdo de blocos markdown se existirem
    match_bloco = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", texto, re.IGNORECASE)
    if match_bloco:
        texto_json = match_bloco.group(1).strip()
    else:
        texto_json = texto

    empresa = "Não encontrado"
    revisao = ""

    try:
        dados = json.loads(texto_json, strict=False)
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
            raw_rev = match_rev.group(1)
            raw_rev = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), raw_rev)
            mapa_escapes = {'n': '\n', 'r': '\r', 't': '\t', '"': '"', '\\': '\\', '/': '/'}
            revisao = re.sub(r'\\([nrt"\\/])', lambda m: mapa_escapes.get(m.group(1), m.group(0)), raw_rev).strip()
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

    empresa = sanitizar_texto_estrangeiro(empresa)
    revisao_final = sanitizar_texto_estrangeiro(revisao_final)

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

    inputs = {
        "texto_copiado_google": google_str,
        "transcricao_bruta": transcricao,
        "nome_agente": atendente_str,
    }

    resultado_raw = ""
    ultimo_erro = None

    from app.services.gemini_pool import (
        eh_erro_credito_openrouter,
        marcar_openrouter_esgotado,
        openrouter_em_cooldown,
    )

    # Sequência de fallbacks: DeepSeek 0731 -> DeepSeek V4.1 -> Gemini direto com Pool de Chaves
    # Se o OpenRouter estiver em cooldown por falta de créditos (24h), pula direto para o Gemini
    if not openrouter_em_cooldown():
        modelos_openrouter = [
            (MODELO_REVISAO, client),
            (MODELO_REVISAO_FALLBACK_1, client_fallback_1),
        ]
        for nome_mod, cl in modelos_openrouter:
            try:
                mensagens = prompt.format_messages(**inputs)
                resposta = cl.invoke(mensagens)
                raw_c = resposta.content if hasattr(resposta, "content") else resposta
                if isinstance(raw_c, list):
                    conteudo = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in raw_c).strip()
                else:
                    conteudo = str(raw_c or "").strip()

                # Se content vier vazio, resgata do canal de raciocínio se o provedor colocou o texto lá
                if not conteudo and hasattr(resposta, "additional_kwargs"):
                    raciocinio = (
                        resposta.additional_kwargs.get("reasoning_content")
                        or resposta.additional_kwargs.get("reasoning")
                        or ""
                    )
                    if isinstance(raciocinio, str) and raciocinio.strip():
                        conteudo = raciocinio.strip()

                if conteudo:
                    emp_temp, rev_temp = parsear_resposta_revisao(conteudo)
                    if rev_temp and rev_temp.strip():
                        resultado_raw = conteudo
                        break
            except Exception as exc:
                ultimo_erro = exc
                from app.logs import log_dev_exc
                log_dev_exc()
                if eh_erro_credito_openrouter(exc):
                    marcar_openrouter_esgotado(exc)
                    # Não tenta o próximo modelo do OpenRouter já que a conta inteira está sem créditos
                    break
                else:
                    print(f"  [AVISO] Falha na revisão via {nome_mod}. Tentando próximo modelo...")

    # Fallback 2: Gemini com pool dinâmico e rotação resiliente de chaves (cooldown 24h)
    if not resultado_raw:
        try:
            from app.services.gemini_pool import executar_revisao_com_pool
            resultado_raw = executar_revisao_com_pool(
                prompt=prompt,
                inputs=inputs,
                modelo=MODELO_REVISAO_FALLBACK_2,
                parsear_fn=parsear_resposta_revisao,
            )
        except Exception as exc:
            from app.logs import log_dev_exc
            log_dev_exc()
            print(f"  [AVISO] Falha na revisão via Gemini (todas as chaves): {exc}")
            ultimo_erro = exc

    if not resultado_raw:
        if ultimo_erro:
            raise ultimo_erro
        raise ValueError("Modelo de IA devolveu revisão vazia (resultado_raw='').")

    empresa, revisao = parsear_resposta_revisao(resultado_raw)
    if not revisao or not revisao.strip():
        raise ValueError(
            f"Modelo de IA devolveu revisão vazia (resultado_raw={repr(resultado_raw[:200])})."
        )

    # Tenta extrair menção ao nome da empresa rotulada nos turnos do Cliente
    nome_diarizado = None
    match_cliente = re.search(r"Cliente\s*\(([^)]+)\)", revisao, re.IGNORECASE)
    if match_cliente:
        rotulo_extraido = match_cliente.group(1).strip()
        if rotulo_extraido.lower() != "cliente":
            nome_diarizado = rotulo_extraido

    fonte_dados = montar_fonte_dados(revisao, nome_diarizado or empresa)

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

