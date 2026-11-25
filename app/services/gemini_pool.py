# -*- coding: utf-8 -*-
"""
============================================================================
Pool e Gerenciador de Chaves e Modelos do Google Gemini com Rotação e Cooldown Diário.

Responsabilidades:
    1. Descobrir chaves Gemini no .env (GEMINI_API_KEY, GEMINI_API_KEY_FALLBACK, etc.).
    2. Gerenciar lista ordenada de modelos Gemini compatíveis do Free Tier
       (gemini-3.1-flash-lite -> gemini-3.5-flash-lite -> gemini-3.6-flash -> gemini-3.8-flash -> gemini-4-hydrogen).
    3. Identificar se uma chave/modelo atingiu o limite de cota (429 / RESOURCE_EXHAUSTED).
    4. Registrar o bloqueio por chave composta (api_key, modelo) em .gemini_quota_status.json.
    5. Reativar automaticamente no próximo reset diário das cotas (00:00 America/Los_Angeles).
    6. Executar chamadas de revisão e análise comercial esgotando todas as chaves por modelo
       antes de avançar para o próximo modelo da fila.
============================================================================
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

# Duração padrão do cooldown legado/OpenRouter (24 horas)
DURACAO_BLOQUEIO_SEGUNDOS = 24 * 3600

# Lista padrão ordenada de modelos Gemini compatíveis com Free Tier e Structured Outputs
MODELOS_GEMINI_PADRAO: tuple[str, ...] = (
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.8-flash",
    "gemini-4-hydrogen",
)

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


def listar_modelos_gemini(modelo_primario: str | None = None) -> list[str]:
    """Retorna a lista ordenada e sem duplicatas de modelos Gemini do Free Tier.

    Combina na ordem:
    1. `modelo_primario` (se informado), garantindo o modelo atual sempre em 1º;
    2. Variável de ambiente `GEMINI_MODELS_FALLBACK` (lista separada por vírgula);
    3. `MODELOS_GEMINI_PADRAO`.
    """
    candidatos: list[str] = []
    if modelo_primario and modelo_primario.strip():
        candidatos.append(modelo_primario.strip())

    env_fallback = (os.getenv("GEMINI_MODELS_FALLBACK") or "").strip()
    if env_fallback:
        for item in env_fallback.split(","):
            limpo = item.strip()
            if limpo:
                candidatos.append(limpo)

    candidatos.extend(MODELOS_GEMINI_PADRAO)

    modelos: list[str] = []
    for mod in candidatos:
        if mod not in modelos:
            modelos.append(mod)
    return modelos


def _resolver_modelos_execucao(
    modelo_preferido: str,
    modelos_fallback: Sequence[str] | None = None,
) -> list[str]:
    """Monta a fila de modelos para execução mantendo `modelo_preferido` primeiro."""
    if modelos_fallback is None:
        return listar_modelos_gemini(modelo_preferido)

    modelos: list[str] = []
    for candidato in [modelo_preferido, *modelos_fallback]:
        mod = str(candidato or "").strip()
        if mod and mod not in modelos:
            modelos.append(mod)
    return modelos


def _chave_status_gemini(api_key: str, modelo: str | None = None) -> str:
    """Retorna a chave composta `api_key::modelo` ou a chave legada `api_key`."""
    modelo_limpo = (modelo or "").strip()
    return f"{api_key}::{modelo_limpo}" if modelo_limpo else api_key


def calcular_proximo_reset_gemini(momento: datetime | None = None) -> datetime:
    """Calcula o momento do próximo reset diário das cotas do Google Gemini.

    As cotas diárias gratuitas (RPD) do Google Gemini são redefinidas à meia-noite
    no fuso horário do Pacífico (00:00 America/Los_Angeles).
    """
    if momento is None:
        momento = datetime.now()

    momento_local = momento.astimezone() if momento.tzinfo is None else momento

    try:
        from zoneinfo import ZoneInfo

        tz_pt = ZoneInfo("America/Los_Angeles")
        dt_pt = momento_local.astimezone(tz_pt)
        amanha_pt = dt_pt.date() + timedelta(days=1)
        reset_pt = datetime(amanha_pt.year, amanha_pt.month, amanha_pt.day, 0, 0, 0, tzinfo=tz_pt)
        reset_local = reset_pt.astimezone(momento_local.tzinfo)
        return reset_local.replace(tzinfo=None)
    except Exception:
        base_reset = momento.replace(hour=4, minute=0, second=0, microsecond=0)
        if momento < base_reset:
            return base_reset
        return base_reset + timedelta(days=1)


def marcar_cota_esgotada(
    var_name: str,
    api_key: str,
    erro: Exception | str = "",
    modelo: str | None = None,
) -> None:
    """Registra o esgotamento da cota para `(api_key, modelo)` até o próximo reset (00:00 PT)."""
    agora = datetime.now()
    ts_agora = agora.timestamp()
    expira = calcular_proximo_reset_gemini(agora)
    ts_expira = expira.timestamp()
    mascarada = mascarar_chave(api_key)
    modelo_limpo = (modelo or "").strip() or None
    chave_registro = _chave_status_gemini(api_key, modelo_limpo)

    registro: dict[str, Any] = {
        "var_name": var_name,
        "chave_mascarada": mascarada,
        "bloqueado_em": ts_agora,
        "bloqueado_em_iso": agora.strftime("%Y-%m-%d %H:%M:%S"),
        "expira_em": ts_expira,
        "expira_em_iso": expira.strftime("%Y-%m-%d %H:%M:%S"),
        "motivo": str(erro)[:200] if erro else "RESOURCE_EXHAUSTED (Limite atingido)",
    }
    if modelo_limpo:
        registro["modelo"] = modelo_limpo

    with _LOCK:
        status = _carregar_status_disco()
        status[chave_registro] = registro
        _salvar_status_disco(status)

    alvo = f"{var_name} ({mascarada}) [modelo: {modelo_limpo}]" if modelo_limpo else f"{var_name} ({mascarada})"
    print(
        f"  [AVISO] Limite de cota atingido na chave Gemini {alvo}. "
        f"Momento registrado: {agora.strftime('%Y-%m-%d %H:%M:%S')}. "
        f"Bloqueado até o próximo reset diário ({expira.strftime('%d/%m/%Y às %H:%M:%S')})."
    )


def _verificar_registro_bloqueado(
    status: dict[str, dict[str, Any]],
    chave_registro: str,
    var_name: str,
    api_key: str,
    agora_ts: float,
    modelo: str | None = None,
) -> tuple[bool, bool]:
    """Avalia se `chave_registro` está em cooldown ativo.

    Retorna `(esta_bloqueada, status_foi_modificado)`.
    """
    reg = status.get(chave_registro)
    if not reg:
        return False, False

    bloqueado_em_ts = reg.get("bloqueado_em", 0)
    bloqueado_em_dt = datetime.fromtimestamp(bloqueado_em_ts)
    proximo_reset_dt = calcular_proximo_reset_gemini(bloqueado_em_dt)
    proximo_reset_ts = proximo_reset_dt.timestamp()
    mascarada = mascarar_chave(api_key)
    alvo = f"{var_name} ({mascarada}) [{modelo}]" if modelo else f"{var_name} ({mascarada})"

    if agora_ts >= proximo_reset_ts:
        del status[chave_registro]
        print(
            f"  [INFO] Reset diário de cota atingido para a chave Gemini {alvo}. "
            "Chave reativada e pronta para novas requisições!"
        )
        return False, True

    restante_segundos = max(0, int(proximo_reset_ts - agora_ts))
    horas = int(restante_segundos // 3600)
    minutos = int((restante_segundos % 3600) // 60)
    from app.logs import log_dev
    log_dev(
        f"Chave Gemini {alvo} em cooldown de cota diária. "
        f"Libera no próximo reset ({proximo_reset_dt.strftime('%d/%m às %H:%M')}, em {horas}h {minutos}m)."
    )
    return True, False


def obter_chaves_gemini_disponiveis(modelo: str | None = None) -> list[tuple[str, str]]:
    """Retorna as chaves configuradas disponíveis para `modelo` (ou legado se `modelo=None`).

    Verifica a entrada composta `api_key::modelo` (quando `modelo` é informado) além de
    eventual bloqueio legado sem modelo (`api_key`), reativando no reset de 00:00 PT.
    """
    configuradas = listar_chaves_gemini_configuradas()
    if not configuradas:
        return []

    agora_ts = datetime.now().timestamp()
    disponiveis: list[tuple[str, str]] = []
    modificado = False
    modelo_limpo = (modelo or "").strip() or None

    with _LOCK:
        status = _carregar_status_disco()

        for var_name, api_key in configuradas:
            bloqueado_legado, mod_leg = _verificar_registro_bloqueado(
                status, api_key, var_name, api_key, agora_ts, modelo=None
            )
            modificado = modificado or mod_leg
            if bloqueado_legado:
                continue

            if modelo_limpo:
                chave_composta = _chave_status_gemini(api_key, modelo_limpo)
                bloqueado_mod, mod_comp = _verificar_registro_bloqueado(
                    status, chave_composta, var_name, api_key, agora_ts, modelo=modelo_limpo
                )
                modificado = modificado or mod_comp
                if bloqueado_mod:
                    continue

            disponiveis.append((var_name, api_key))

        if modificado:
            _salvar_status_disco(status)

    return disponiveis


def obter_modelo_gemini_ativo(
    modelo_preferido: str,
    modelos_fallback: Sequence[str] | None = None,
) -> str:
    """Retorna o primeiro modelo Gemini com ao menos uma chave livre no momento."""
    modelos = _resolver_modelos_execucao(modelo_preferido, modelos_fallback)
    for mod in modelos:
        if obter_chaves_gemini_disponiveis(modelo=mod):
            return mod
    return modelos[0] if modelos else modelo_preferido


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


def resetar_cooldown_chaves(resetar_gemini: bool = True, resetar_openrouter: bool = False) -> None:
    """Reseta o status de cooldown das chaves gravado em disco.

    Args:
        resetar_gemini: Se True, remove o cooldown de todas as chaves Gemini.
        resetar_openrouter: Se True, remove o cooldown do OpenRouter.
    """
    with _LOCK:
        status = _carregar_status_disco()
        if resetar_gemini and resetar_openrouter:
            status = {}
        elif resetar_gemini:
            status = {k: v for k, v in status.items() if k == OPENROUTER_STATUS_KEY}
        elif resetar_openrouter:
            status.pop(OPENROUTER_STATUS_KEY, None)
        _salvar_status_disco(status)


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


def _executar_com_pool(
    etapa: str,
    modelo: str,
    modelos_fallback: Sequence[str] | None,
    chamada_fn: Callable[[ChatGoogleGenerativeAI], Any],
) -> Any:
    """Executa `chamada_fn` iterando primeiro todas as chaves disponíveis do modelo atual
    e só avançando para o próximo modelo quando todas as chaves do modelo atual falharem.
    """
    modelos = _resolver_modelos_execucao(modelo, modelos_fallback)
    ultimo_erro: Exception | None = None
    alguma_chave_disponivel = False

    for mod_idx, mod_atual in enumerate(modelos):
        chaves = obter_chaves_gemini_disponiveis(modelo=mod_atual)
        if not chaves:
            if mod_idx + 1 < len(modelos):
                prox_mod = modelos[mod_idx + 1]
                print(
                    f"  [AVISO] Nenhuma chave Gemini disponível para o modelo {mod_atual}. "
                    f"Alternando para o próximo modelo: {prox_mod}..."
                )
            continue

        alguma_chave_disponivel = True
        for idx, (var_name, api_key) in enumerate(chaves, 1):
            try:
                cl = obter_cliente_gemini(mod_atual, api_key)
                return chamada_fn(cl)
            except Exception as exc:
                ultimo_erro = exc
                if eh_erro_cota_gemini(exc):
                    marcar_cota_esgotada(var_name, api_key, exc, modelo=mod_atual)
                    if idx < len(chaves):
                        prox_nome = chaves[idx][0]
                        print(f"  [INFO] Alternando para a próxima chave Gemini ({mod_atual}): {prox_nome}...")
                else:
                    print(f"  [AVISO] Falha na {etapa} via Gemini ({var_name} | {mod_atual}): {exc}")
                    if idx < len(chaves):
                        prox_nome = chaves[idx][0]
                        print(f"  [INFO] Tentando próxima chave Gemini ({mod_atual}): {prox_nome}...")

        if mod_idx + 1 < len(modelos):
            prox_mod = modelos[mod_idx + 1]
            print(
                f"  [AVISO] Todas as chaves Gemini esgotaram ou falharam para {mod_atual}. "
                f"Alternando para o próximo modelo: {prox_mod}..."
            )

    if ultimo_erro:
        raise ultimo_erro
    if not alguma_chave_disponivel:
        raise RuntimeError(
            "Todas as chaves Gemini configuradas no .env estão temporariamente bloqueadas "
            "por terem atingido o limite diário de requisições em todos os modelos configurados."
        )
    raise RuntimeError(f"Falha ao executar {etapa} em todos os modelos e chaves Gemini disponíveis.")


def executar_revisao_com_pool(
    prompt: Any,
    inputs: dict[str, Any],
    modelo: str,
    parsear_fn: Callable[[str], tuple[str, str]],
    modelos_fallback: Sequence[str] | None = None,
) -> str:
    """Executa a revisão no Gemini esgotando todas as chaves de cada modelo antes de rotacionar o modelo."""
    def _chamar_revisao(cl: ChatGoogleGenerativeAI) -> str:
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
            _, rev_temp = parsear_fn(conteudo)
            if rev_temp and rev_temp.strip():
                return conteudo

        raise ValueError("Modelo Gemini devolveu resposta de revisão vazia.")

    return _executar_com_pool("revisão", modelo, modelos_fallback, _chamar_revisao)


def executar_analise_com_pool(
    prompt: Any,
    inputs: dict[str, Any],
    modelo: str,
    schema: type,
    modelos_fallback: Sequence[str] | None = None,
) -> Any:
    """Executa a análise comercial no Gemini com Structured Output rotacionando chaves e modelos."""
    def _chamar_analise(cl: ChatGoogleGenerativeAI) -> Any:
        ch = prompt | cl.with_structured_output(schema)
        resposta = ch.invoke(inputs)
        if resposta:
            return resposta
        raise ValueError("Modelo Gemini devolveu resposta estruturada vazia.")

    return _executar_com_pool("análise comercial", modelo, modelos_fallback, _chamar_analise)
