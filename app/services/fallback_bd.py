# -*- coding: utf-8 -*-
"""
============================================================================
Fallback Local de Persistência no Banco de Dados (CSV + JSON).

Responsabilidades:
    1. Quando o salvamento no PostgreSQL falhar após as tentativas (ex.: queda de rede,
       banco indisponível ou timeout), salvar na raiz do projeto todos os dados
       processados (transcrição, revisão, metadados da empresa e JSON da análise)
       no formato exato exigido para posterior INSERT.
    2. Consolidar por `log` (chave primária de `registro_chamadas` e `avaliacao_ia`)
       em dois arquivos sincronizados na raiz:
       - `fallback_bd_pendentes.csv` (planilha UTF-8 com BOM, compatível com Excel)
       - `fallback_bd_pendentes.json` (estrutura tipada exata para reingestão direta)
    3. Permitir o reprocessamento posterior (`reprocessar_fallback_bd`) quando o
       banco voltar a ficar disponível.
============================================================================
"""
from __future__ import annotations

import csv
import json
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()

ARQUIVO_FALLBACK_CSV = "fallback_bd_pendentes.csv"
ARQUIVO_FALLBACK_JSON = "fallback_bd_pendentes.json"

COLUNAS_FALLBACK_CSV: tuple[str, ...] = (
    "log",
    "protocolo",
    "transcricao",
    "revisao",
    "id_empresa",
    "empresa_nome",
    "empresa_telefone",
    "empresa_fonte_dados",
    "analise_json",
    "etapa_falha",
    "erro",
    "atualizado_em",
)


def obter_pasta_raiz_fallback() -> Path:
    """Retorna a pasta raiz do projeto (ou do executável quando empacotado)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def obter_caminhos_fallback(pasta_raiz: Path | None = None) -> tuple[Path, Path]:
    """Retorna `(caminho_csv, caminho_json)` na pasta raiz configurada."""
    raiz = pasta_raiz or obter_pasta_raiz_fallback()
    return raiz / ARQUIVO_FALLBACK_CSV, raiz / ARQUIVO_FALLBACK_JSON


def _carregar_registros_json(caminho_json: Path) -> dict[str, dict[str, Any]]:
    if not caminho_json.is_file():
        return {}
    try:
        with open(caminho_json, "r", encoding="utf-8") as f:
            dados = json.load(f)
        if isinstance(dados, dict):
            return {str(k): v for k, v in dados.items() if isinstance(v, dict)}
        if isinstance(dados, list):
            return {
                str(item["log"]): item
                for item in dados
                if isinstance(item, dict) and item.get("log")
            }
    except Exception:
        pass
    return {}


def _normalizar_analise_para_json(analise: dict[str, Any] | str | None) -> dict[str, Any] | None:
    if analise is None or analise == "":
        return None
    if isinstance(analise, dict):
        return json.loads(json.dumps(analise, ensure_ascii=False, default=str))
    if isinstance(analise, str):
        try:
            parsed = json.loads(analise)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
    return None


def _persistir_arquivos_fallback(
    registros: dict[str, dict[str, Any]],
    caminho_csv: Path,
    caminho_json: Path,
) -> None:
    """Grava `fallback_bd_pendentes.json` e `fallback_bd_pendentes.csv` de forma sincronizada."""
    caminho_json.parent.mkdir(parents=True, exist_ok=True)
    lista_ordenada = list(registros.values())

    with open(caminho_json, "w", encoding="utf-8") as f_json:
        json.dump(lista_ordenada, f_json, indent=2, ensure_ascii=False, default=str)

    with open(caminho_csv, "w", encoding="utf-8-sig", newline="") as f_csv:
        writer = csv.DictWriter(
            f_csv,
            fieldnames=list(COLUNAS_FALLBACK_CSV),
            delimiter=";",
            quotechar='"',
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\n",
        )
        writer.writeheader()
        for reg in lista_ordenada:
            analise_obj = reg.get("analise_json")
            analise_str = (
                json.dumps(analise_obj, ensure_ascii=False, default=str)
                if isinstance(analise_obj, dict)
                else (str(analise_obj) if analise_obj else "")
            )
            writer.writerow(
                {
                    "log": reg.get("log") or "",
                    "protocolo": "" if reg.get("protocolo") is None else reg.get("protocolo"),
                    "transcricao": reg.get("transcricao") or "",
                    "revisao": reg.get("revisao") or "",
                    "id_empresa": "" if reg.get("id_empresa") is None else reg.get("id_empresa"),
                    "empresa_nome": reg.get("empresa_nome") or "",
                    "empresa_telefone": reg.get("empresa_telefone") or "",
                    "empresa_fonte_dados": reg.get("empresa_fonte_dados") or "",
                    "analise_json": analise_str,
                    "etapa_falha": reg.get("etapa_falha") or "",
                    "erro": reg.get("erro") or "",
                    "atualizado_em": reg.get("atualizado_em") or "",
                }
            )


def salvar_fallback_bd(
    *,
    log: str,
    etapa_falha: str,
    protocolo: int | str | None = None,
    transcricao: str | None = None,
    revisao: str | None = None,
    id_empresa: int | None = None,
    empresa_nome: str | None = None,
    empresa_telefone: str | None = None,
    empresa_fonte_dados: str | None = None,
    analise_json: dict[str, Any] | str | None = None,
    erro: Exception | str | None = None,
    pasta_raiz: Path | None = None,
) -> tuple[Path, Path]:
    """Salva ou atualiza o registro pendente na planilha CSV e no JSON na raiz do projeto.

    Preserva campos já salvos anteriormente para o mesmo `log` quando uma etapa
    posterior falha (ex.: transcrição salva primeiro, depois revisão e análise).
    """
    log_limpo = str(log or "").strip()
    if not log_limpo:
        raise ValueError("Campo 'log' é obrigatório para salvar fallback de banco.")

    caminho_csv, caminho_json = obter_caminhos_fallback(pasta_raiz)
    analise_normalizada = _normalizar_analise_para_json(analise_json)
    agora_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    erro_str = str(erro).strip()[:400] if erro else ""

    with _LOCK:
        registros = _carregar_registros_json(caminho_json)
        atual = registros.get(log_limpo, {"log": log_limpo})

        if protocolo is not None and str(protocolo).strip():
            try:
                atual["protocolo"] = int(protocolo)
            except (ValueError, TypeError):
                atual["protocolo"] = str(protocolo).strip()

        if transcricao is not None and str(transcricao).strip():
            atual["transcricao"] = str(transcricao)

        if revisao is not None and str(revisao).strip():
            atual["revisao"] = str(revisao)

        if id_empresa is not None:
            atual["id_empresa"] = id_empresa

        if empresa_nome is not None and str(empresa_nome).strip():
            atual["empresa_nome"] = str(empresa_nome).strip()

        if empresa_telefone is not None and str(empresa_telefone).strip():
            atual["empresa_telefone"] = str(empresa_telefone).strip()

        if empresa_fonte_dados is not None and str(empresa_fonte_dados).strip():
            atual["empresa_fonte_dados"] = str(empresa_fonte_dados).strip()

        if analise_normalizada is not None:
            atual["analise_json"] = analise_normalizada

        atual["etapa_falha"] = etapa_falha
        if erro_str:
            atual["erro"] = erro_str
        atual["atualizado_em"] = agora_iso

        registros[log_limpo] = atual
        _persistir_arquivos_fallback(registros, caminho_csv, caminho_json)

    return caminho_csv, caminho_json


def carregar_fallback_bd(pasta_raiz: Path | None = None) -> list[dict[str, Any]]:
    """Carrega todos os registros pendentes salvos em fallback (JSON ou CSV)."""
    caminho_csv, caminho_json = obter_caminhos_fallback(pasta_raiz)
    with _LOCK:
        if caminho_json.is_file():
            return list(_carregar_registros_json(caminho_json).values())

        if not caminho_csv.is_file():
            return []

        registros: list[dict[str, Any]] = []
        with open(caminho_csv, "r", encoding="utf-8-sig", newline="") as f_csv:
            reader = csv.DictReader(f_csv, delimiter=";")
            for row in reader:
                log_nome = (row.get("log") or "").strip()
                if not log_nome:
                    continue
                analise_raw = row.get("analise_json") or ""
                prot_raw = (row.get("protocolo") or "").strip()
                id_emp_raw = (row.get("id_empresa") or "").strip()
                registros.append(
                    {
                        "log": log_nome,
                        "protocolo": int(prot_raw) if prot_raw.isdigit() else (prot_raw or None),
                        "transcricao": row.get("transcricao") or None,
                        "revisao": row.get("revisao") or None,
                        "id_empresa": int(id_emp_raw) if id_emp_raw.isdigit() else None,
                        "empresa_nome": row.get("empresa_nome") or None,
                        "empresa_telefone": row.get("empresa_telefone") or None,
                        "empresa_fonte_dados": row.get("empresa_fonte_dados") or None,
                        "analise_json": _normalizar_analise_para_json(analise_raw),
                        "etapa_falha": row.get("etapa_falha") or "",
                        "erro": row.get("erro") or "",
                        "atualizado_em": row.get("atualizado_em") or "",
                    }
                )
        return registros


def reprocessar_fallback_bd(pasta_raiz: Path | None = None) -> dict[str, int]:
    """Reinsere no PostgreSQL os registros salvos no fallback local e remove os bem-sucedidos."""
    from app.database.chamadas_dao import (
        inserir_analise,
        inserir_empresa,
        inserir_registro_chamada,
        inserir_revisao,
    )
    from app.database.db import conectar

    caminho_csv, caminho_json = obter_caminhos_fallback(pasta_raiz)
    itens = carregar_fallback_bd(pasta_raiz)
    if not itens:
        return {"processados": 0, "sucesso": 0, "falha": 0}

    pendentes: dict[str, dict[str, Any]] = {}
    sucesso = 0
    falha = 0

    for item in itens:
        log_nome = item["log"]
        try:
            with conectar() as cur:
                if item.get("transcricao") and item.get("protocolo"):
                    inserir_registro_chamada(
                        cur,
                        log_arquivo=log_nome,
                        protocolo=int(item["protocolo"]),
                        transcricao=item["transcricao"],
                    )

                id_empresa = item.get("id_empresa")
                if item.get("revisao"):
                    if id_empresa is None and item.get("empresa_nome"):
                        id_empresa = inserir_empresa(
                            cur,
                            item["empresa_nome"],
                            item.get("empresa_fonte_dados"),
                            telefone=item.get("empresa_telefone"),
                        )
                    inserir_revisao(cur, log_nome, item["revisao"], id_empresa=id_empresa)

                analise = item.get("analise_json")
                if isinstance(analise, dict) and analise:
                    if id_empresa is not None:
                        av_ia = analise.setdefault("avaliacao_ia", {})
                        if not av_ia.get("empresa_contatada"):
                            av_ia["empresa_contatada"] = id_empresa
                    inserir_analise(cur, log_nome, analise)

            sucesso += 1
        except Exception as exc:
            falha += 1
            item["erro"] = str(exc)[:400]
            item["atualizado_em"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            pendentes[log_nome] = item

    with _LOCK:
        _persistir_arquivos_fallback(pendentes, caminho_csv, caminho_json)

    return {"processados": len(itens), "sucesso": sucesso, "falha": falha}


if __name__ == "__main__":
    resumo = reprocessar_fallback_bd()
    print(f"Reprocessamento do fallback de banco concluído: {resumo}")
