# -*- coding: utf-8 -*-
"""
============================================================================
Pool e Gerenciador de Chaves do Google Gemini com Rotação e Bloqueio de 24h.

Responsabilidades:
    1. Descobrir chaves Gemini no .env (GEMINI_API_KEY, GEMINI_API_KEY_FALLBACK, etc.).
    2. Identificar se uma chave atingiu o limite de cota (429 / RESOURCE_EXHAUSTED).
    3. Registrar o momento exato do bloqueio em arquivo persistente (.gemini_quota_status.json).
    4. Bloquear a chave por 24 horas e alternar automaticamente para a próxima chave válida.
    5. Reativar automaticamente a chave após o término das 24 horas.
    6. Executar chamadas de revisão e análise comercial com rotação resiliente.
============================================================================
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

# Duração padrão do cooldown de cota (24 horas)
DURACAO_BLOQUEIO_SEGUNDOS = 24 * 3600

_LOCK = threading.Lock()
_CLIENTS_CACHE: dict[tuple[str, str], ChatGoogleGenerativeAI] = {}


def obter_caminho_status() -> Path:
    """Retorna o caminho do arquivo de status de cotas das chaves Gemini."""
    if getattr(sys, "frozen", False):
        pasta = Path(sys.executable).resolve().parent
    else:
        pasta = Path(__file__).resolve().parents[2]
    return pasta / ".gemini_quota_status.json"


def mascarar_chave(chave: str) -> str:
    """Retorna uma versão mascarada da chave para logs seguros."""
    if not chave:
        return ""
    limpo = str(chave).strip()
    if len(limpo) <= 14:
        return limpo[:3] + "..." + limpo[-3:]
    return limpo[:8] + "..." + limpo[-5:]


def eh_erro_cota_gemini(exc: Exception) -> bool:
    """Verifica se a exceção indica limite de cota excedido (429 RESOURCE_EXHAUSTED)."""
    exc_type = type(exc).__name__
    if exc_type in ("GoogleRateLimitError", "ResourceExhausted"):
        return True

    msg = str(exc).lower()
    indicadores = (
        "resource_exhausted",
        "429",
        "quota exceeded",
        "quota_exceeded",
        "rate limit",
        "rate_limit",
        "ratelimit",
        "exceeded your current quota",
        "generaterequestsperday",
        "free_tier_requests",
    )
    return any(ind in msg for ind in indicadores)


def listar_chaves_gemini_configuradas() -> list[tuple[str, str]]:
    """Lista todas as chaves Gemini configuradas no ambiente em ordem de prioridade:
    1. GEMINI_API_KEY
    2. GEMINI_API_KEY_FALLBACK / GEMINI_API_KEY_FALLBACK_1
    3. GEMINI_API_KEY_FALLBACK_2, GEMINI_API_KEY_FALLBACK_3, etc.
    """
    chaves: list[tuple[str, str]] = []
    vistas: set[str] = set()

    # 1. Chave primária
    primaria = (os.getenv("GEMINI_API_KEY") or "").strip()
    if primaria and primaria != "sk-dummy-key" and not primaria.startswith("sk-dummy"):
        chaves.append(("GEMINI_API_KEY", primaria))
        vistas.add(primaria)

    # 2. Chave de fallback 1
    fb1 = (os.getenv("GEMINI_API_KEY_FALLBACK") or os.getenv("GEMINI_API_KEY_FALLBACK_1") or "").strip()
    if fb1 and fb1 != "sk-dummy-key" and not fb1.startswith("sk-dummy") and fb1 not in vistas:
        nome_var = "GEMINI_API_KEY_FALLBACK" if os.getenv("GEMINI_API_KEY_FALLBACK") else "GEMINI_API_KEY_FALLBACK_1"
        chaves.append((nome_var, fb1))
        vistas.add(fb1)

    # 3. Chaves subsequentes (FALLBACK_2 até FALLBACK_20)
    for idx in range(2, 21):
        nome_var = f"GEMINI_API_KEY_FALLBACK_{idx}"
        val = (os.getenv(nome_var) or "").strip()
        if val and val != "sk-dummy-key" and not val.startswith("sk-dummy") and val not in vistas:
            chaves.append((nome_var, val))
            vistas.add(val)

    return chaves


def _carregar_status_disco() -> dict[str, dict[str, Any]]:
    """Lê o arquivo de status JSON sob lock."""
    caminho = obter_caminho_status()
    if not caminho.is_file():
        return {}
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
            return dados if isinstance(dados, dict) else {}
    except Exception:
        return {}


def _salvar_status_disco(status: dict[str, dict[str, Any]]) -> None:
    """Grava o arquivo de status JSON sob lock."""
    caminho = obter_caminho_status()
    try:
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(status, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        print(f"  [AVISO] Falha ao persistir status de cotas do Gemini: {exc}")


def marcar_cota_esgotada(
    var_name: str,
    api_key: str,
    erro: Exception | str = "",
) -> None:
    """Registra o momento do esgotamento da cota e bloqueia a chave por 24 horas."""
    agora = datetime.now()
    ts_agora = agora.timestamp()
    expira = agora + timedelta(seconds=DURACAO_BLOQUEIO_SEGUNDOS)
    mascarada = mascarar_chave(api_key)

    with _LOCK:
        status = _carregar_status_disco()
        status[api_key] = {
            "var_name": var_name,
            "chave_mascarada": mascarada,
            "bloqueado_em": ts_agora,
            "bloqueado_em_iso": agora.strftime("%Y-%m-%d %H:%M:%S"),
            "expira_em_iso": expira.strftime("%Y-%m-%d %H:%M:%S"),
            "motivo": str(erro)[:200] if erro else "RESOURCE_EXHAUSTED (Limite atingido)",
        }
        _salvar_status_disco(status)

    print(
        f"  [AVISO] Limite de cota atingido na chave Gemini {var_name} ({mascarada}). "
        f"Momento registrado: {agora.strftime('%Y-%m-%d %H:%M:%S')}. "
        f"Esta chave ficará em cooldown por 24h (até {expira.strftime('%Y-%m-%d %H:%M:%S')})."
    )


def obter_chaves_gemini_disponiveis() -> list[tuple[str, str]]:
    """Retorna a lista de chaves configuradas que NÃO estão em período de bloqueio de 24h.
    Reativa automaticamente chaves cujo período de 24 horas já expirou.
    """
    configuradas = listar_chaves_gemini_configuradas()
    if not configuradas:
        return []

    agora_ts = time.time()
    disponiveis: list[tuple[str, str]] = []
    modificado = False

    with _LOCK:
        status = _carregar_status_disco()

        for var_name, api_key in configuradas:
            reg = status.get(api_key)
            if not reg:
                disponiveis.append((var_name, api_key))
                continue

            bloqueado_em = reg.get("bloqueado_em", 0)
            decorrido = agora_ts - bloqueado_em

            if decorrido >= DURACAO_BLOQUEIO_SEGUNDOS:
                # 24 horas expiradas! Reativa a chave
                del status[api_key]
                modificado = True
                mascarada = mascarar_chave(api_key)
                print(
                    f"  [INFO] Período de 24h de bloqueio expirado para a chave Gemini {var_name} ({mascarada}). "
                    "Chave reativada e pronta para novas requisições!"
                )
                disponiveis.append((var_name, api_key))
            else:
                restante_segundos = DURACAO_BLOQUEIO_SEGUNDOS - decorrido
                horas = int(restante_segundos // 3600)
                minutos = int((restante_segundos % 3600) // 60)
                from app.logs import log_dev
                log_dev(
                    f"Chave Gemini {var_name} ({mascarar_chave(api_key)}) em cooldown de cota. "
                    f"Libera em {horas}h {minutos}m."
                )

        if modificado:
            _salvar_status_disco(status)

    return disponiveis


OPENROUTER_STATUS_KEY = "__OPENROUTER_CREDITS__"


def eh_erro_credito_openrouter(exc: Exception) -> bool:
    """Verifica se a exceção indica falta de créditos / cota no OpenRouter (HTTP 402)."""
    status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status_code == 402:
        return True

    msg = str(exc).lower()
    indicadores = (
        "error code: 402",
        "code': 402",
        "code\": 402",
        "requires more credits",
        "openrouter_credits",
        "can only afford",
        "fewer max_tokens",
        "insufficient credits",
        "payment required",
        "add more credits",
    )
    return any(ind in msg for ind in indicadores)


def marcar_openrouter_esgotado(erro: Exception | str = "") -> None:
    """Registra o esgotamento de créditos no OpenRouter e ativa bloqueio por 24 horas."""
    agora = datetime.now()
    ts_agora = agora.timestamp()
    expira = agora + timedelta(seconds=DURACAO_BLOQUEIO_SEGUNDOS)

    with _LOCK:
        status = _carregar_status_disco()
        status[OPENROUTER_STATUS_KEY] = {
            "provedor": "OpenRouter",
            "bloqueado_em": ts_agora,
            "bloqueado_em_iso": agora.strftime("%Y-%m-%d %H:%M:%S"),
            "expira_em_iso": expira.strftime("%Y-%m-%d %H:%M:%S"),
            "motivo": "Créditos insuficientes no OpenRouter (HTTP 402)",
        }
        _salvar_status_disco(status)

    print(
        f"  [AVISO] Créditos esgotados no OpenRouter (DeepSeek). "
        f"Momento registrado: {agora.strftime('%Y-%m-%d %H:%M:%S')}. "
        f"Alternando automaticamente para o Gemini por 24h (até {expira.strftime('%Y-%m-%d %H:%M:%S')})."
    )


def openrouter_em_cooldown() -> bool:
    """Verifica se o OpenRouter está bloqueado por falta de créditos (cooldown 24h).
    Reativa automaticamente se o período de 24 horas expirou.
    """
    agora_ts = time.time()
    with _LOCK:
        status = _carregar_status_disco()
        reg = status.get(OPENROUTER_STATUS_KEY)
        if not reg:
            return False

        bloqueado_em = reg.get("bloqueado_em", 0)
        decorrido = agora_ts - bloqueado_em

        if decorrido >= DURACAO_BLOQUEIO_SEGUNDOS:
            del status[OPENROUTER_STATUS_KEY]
            _salvar_status_disco(status)
            print(
                "  [INFO] Período de 24h de bloqueio do OpenRouter expirado. "
                "Tentativas com DeepSeek reativadas!"
            )
            return False
        else:
            restante_segundos = DURACAO_BLOQUEIO_SEGUNDOS - decorrido
            horas = int(restante_segundos // 3600)
            minutos = int((restante_segundos % 3600) // 60)
            from app.logs import log_dev
            log_dev(
                f"OpenRouter (DeepSeek) em cooldown de créditos. "
                f"Usando Gemini por padrão (libera em {horas}h {minutos}m)."
            )
            return True


def obter_cliente_gemini(modelo: str, api_key: str) -> ChatGoogleGenerativeAI:
    """Cria ou recupera em cache o cliente ChatGoogleGenerativeAI para o modelo e chave especificados."""
    cache_key = (modelo, api_key)
    with _LOCK:
        if cache_key not in _CLIENTS_CACHE:
            _CLIENTS_CACHE[cache_key] = ChatGoogleGenerativeAI(
                model=modelo,
                google_api_key=api_key,
                temperature=0.0,
                max_output_tokens=8192,
            )
        return _CLIENTS_CACHE[cache_key]


def executar_revisao_com_pool(
    prompt: Any,
    inputs: dict[str, Any],
    modelo: str,
    parsear_fn: Callable[[str], tuple[str, str]],
) -> str:
    """Executa a revisão no Gemini iterando pelo pool de chaves disponíveis.
    Se a chave atual falhar com cota ou erro, registra o momento e passa para a próxima.
    """
    chaves = obter_chaves_gemini_disponiveis()
    if not chaves:
        raise RuntimeError(
            "Todas as chaves Gemini configuradas no .env estão temporariamente bloqueadas "
            "por terem atingido o limite diário de requisições (cooldown de 24 horas)."
        )

    ultimo_erro = None
    for idx, (var_name, api_key) in enumerate(chaves, 1):
        mascarada = mascarar_chave(api_key)
        try:
            cl = obter_cliente_gemini(modelo, api_key)
            mensagens = prompt.format_messages(**inputs)
            resposta = cl.invoke(mensagens)

            raw_c = resposta.content if hasattr(resposta, "content") else resposta
            if isinstance(raw_c, list):
                conteudo = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in raw_c).strip()
            else:
                conteudo = str(raw_c or "").strip()

            if not conteudo and hasattr(resposta, "additional_kwargs"):
                raciocinio = (
                    resposta.additional_kwargs.get("reasoning_content")
                    or resposta.additional_kwargs.get("reasoning")
                    or ""
                )
                if isinstance(raciocinio, str) and raciocinio.strip():
                    conteudo = raciocinio.strip()

            if conteudo:
                emp_temp, rev_temp = parsear_fn(conteudo)
                if rev_temp and rev_temp.strip():
                    return conteudo

            raise ValueError("Modelo Gemini devolveu resposta de revisão vazia.")

        except Exception as exc:
            ultimo_erro = exc
            if eh_erro_cota_gemini(exc):
                marcar_cota_esgotada(var_name, api_key, exc)
                if idx < len(chaves):
                    prox_nome = chaves[idx][0]
                    print(f"  [INFO] Alternando para a próxima chave Gemini: {prox_nome}...")
            else:
                print(f"  [AVISO] Falha na revisão via Gemini ({var_name}): {exc}")
                if idx < len(chaves):
                    prox_nome = chaves[idx][0]
                    print(f"  [INFO] Tentando próxima chave Gemini: {prox_nome}...")

    if ultimo_erro:
        raise ultimo_erro
    raise RuntimeError("Falha ao executar revisão em todas as chaves Gemini disponíveis.")


def executar_analise_com_pool(
    prompt: Any,
    inputs: dict[str, Any],
    modelo: str,
    schema: type,
) -> Any:
    """Executa a análise comercial no Gemini com Structured Output iterando pelo pool de chaves disponíveis.
    Se a chave atual falhar com cota ou erro, registra o momento e passa para a próxima.
    """
    chaves = obter_chaves_gemini_disponiveis()
    if not chaves:
        raise RuntimeError(
            "Todas as chaves Gemini configuradas no .env estão temporariamente bloqueadas "
            "por terem atingido o limite diário de requisições (cooldown de 24 horas)."
        )

    ultimo_erro = None
    for idx, (var_name, api_key) in enumerate(chaves, 1):
        mascarada = mascarar_chave(api_key)
        try:
            cl = obter_cliente_gemini(modelo, api_key)
            ch = prompt | cl.with_structured_output(schema)
            resposta = ch.invoke(inputs)
            if resposta:
                return resposta

            raise ValueError("Modelo Gemini devolveu resposta estruturada vazia.")

        except Exception as exc:
            ultimo_erro = exc
            if eh_erro_cota_gemini(exc):
                marcar_cota_esgotada(var_name, api_key, exc)
                if idx < len(chaves):
                    prox_nome = chaves[idx][0]
                    print(f"  [INFO] Alternando para a próxima chave Gemini: {prox_nome}...")
            else:
                print(f"  [AVISO] Falha na análise comercial via Gemini ({var_name}): {exc}")
                if idx < len(chaves):
                    prox_nome = chaves[idx][0]
                    print(f"  [INFO] Tentando próxima chave Gemini: {prox_nome}...")

    if ultimo_erro:
        raise ultimo_erro
    raise RuntimeError("Falha ao executar análise comercial em todas as chaves Gemini disponíveis.")
