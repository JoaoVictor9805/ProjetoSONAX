# -*- coding: utf-8 -*-
"""
============================================================================
Fallback Local de Persistência no Banco de Dados (CSV + JSON).

Responsabilidades:
    1. Quando o PostgreSQL estiver indisponível (modo offline desde o início ou
       falha de conexão/timeout durante o processamento), salvar na raiz do
       projeto todos os dados processados:
       - transcrição (`transcricao`, `protocolo`, `ramal`, `data_chamada`)
       - dados do robô Google RPA (`rpa_telefone`, `rpa_texto_google`, `rpa_atualizado_em`)
       - revisão e metadados da empresa (`revisao`, `empresa_*`)
       - análise comercial completa e data original da avaliação (`data_avaliacao`, `analise_json`)
    2. Consolidar por `log` (chave primária de `registro_chamadas` e `avaliacao_ia`)
       em dois arquivos sincronizados na raiz:
       - `fallback_bd_pendentes.csv` (planilha UTF-8 com BOM, compatível com Excel)
       - `fallback_bd_pendentes.json` (estrutura tipada exata para reingestão direta)
    3. Fornecer leitura/idempotência e cache RPA locais durante execuções offline.
    4. Permitir o reprocessamento posterior (`reprocessar_fallback_bd`) quando o
       banco voltar a ficar disponível, inserindo tudo (inclusive `cache_rpa_google`
       e preservando a `data_avaliacao` original).
============================================================================
"""
from __future__ import annotations

import copy
import csv
import json
import re
import sys
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()

ARQUIVO_FALLBACK_CSV = "fallback_bd_pendentes.csv"
ARQUIVO_FALLBACK_JSON = "fallback_bd_pendentes.json"

COLUNAS_FALLBACK_CSV: tuple[str, ...] = (
    "log",
    "protocolo",
    "ramal",
    "data_chamada",
    "transcricao",
    "rpa_telefone",
    "rpa_texto_google",
    "rpa_atualizado_em",
    "revisao",
    "id_empresa",
    "empresa_nome",
    "empresa_telefone",
    "empresa_fonte_dados",
    "data_avaliacao",
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


def _normalizar_digitos_tel(tel: str | None) -> str:
    if not tel:
        return ""
    return re.sub(r"[^\d]", "", str(tel))


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
            data_av = reg.get("data_avaliacao") or ""
            if not data_av and isinstance(analise_obj, dict):
                data_av = str((analise_obj.get("avaliacao_ia") or {}).get("data_avaliacao") or "")
            writer.writerow(
                {
                    "log": reg.get("log") or "",
                    "protocolo": "" if reg.get("protocolo") is None else reg.get("protocolo"),
                    "ramal": reg.get("ramal") or "",
                    "data_chamada": reg.get("data_chamada") or "",
                    "transcricao": reg.get("transcricao") or "",
                    "rpa_telefone": reg.get("rpa_telefone") or "",
                    "rpa_texto_google": reg.get("rpa_texto_google") or "",
                    "rpa_atualizado_em": reg.get("rpa_atualizado_em") or "",
                    "revisao": reg.get("revisao") or "",
                    "id_empresa": "" if reg.get("id_empresa") is None else reg.get("id_empresa"),
                    "empresa_nome": reg.get("empresa_nome") or "",
                    "empresa_telefone": reg.get("empresa_telefone") or "",
                    "empresa_fonte_dados": reg.get("empresa_fonte_dados") or "",
                    "data_avaliacao": data_av,
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
    ramal: str | None = None,
    data_chamada: str | None = None,
    transcricao: str | None = None,
    rpa_telefone: str | None = None,
    rpa_texto_google: str | None = None,
    rpa_atualizado_em: str | None = None,
    revisao: str | None = None,
    id_empresa: int | None = None,
    empresa_nome: str | None = None,
    empresa_telefone: str | None = None,
    empresa_fonte_dados: str | None = None,
    data_avaliacao: str | None = None,
    analise_json: dict[str, Any] | str | None = None,
    erro: Exception | str | None = None,
    pasta_raiz: Path | None = None,
) -> tuple[Path, Path]:
    """Salva ou atualiza o registro pendente na planilha CSV e no JSON na raiz do projeto.

    Preserva campos já salvos anteriormente para o mesmo `log` quando etapas
    posteriores são gravadas (ex.: transcrição -> RPA -> revisão -> análise).
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

        if ramal is not None and str(ramal).strip():
            atual["ramal"] = str(ramal).strip()

        if data_chamada is not None and str(data_chamada).strip():
            atual["data_chamada"] = str(data_chamada).strip()

        if transcricao is not None and str(transcricao).strip():
            atual["transcricao"] = str(transcricao)

        if rpa_telefone is not None and str(rpa_telefone).strip():
            atual["rpa_telefone"] = str(rpa_telefone).strip()

        if rpa_texto_google is not None and str(rpa_texto_google).strip():
            txt_rpa = str(rpa_texto_google).strip()
            if txt_rpa != "Não encontrado" or not atual.get("rpa_texto_google"):
                atual["rpa_texto_google"] = txt_rpa
                atual["rpa_atualizado_em"] = (
                    str(rpa_atualizado_em).strip()
                    if rpa_atualizado_em and str(rpa_atualizado_em).strip()
                    else agora_iso
                )
        elif rpa_atualizado_em and str(rpa_atualizado_em).strip():
            atual["rpa_atualizado_em"] = str(rpa_atualizado_em).strip()

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
            av_ia = analise_normalizada.setdefault("avaliacao_ia", {})
            data_av_resolvida = (
                (str(data_avaliacao).strip()[:10] if data_avaliacao and str(data_avaliacao).strip() else None)
                or (str(av_ia.get("data_avaliacao")).strip()[:10] if av_ia.get("data_avaliacao") else None)
                or str(date.today())
            )
            av_ia["data_avaliacao"] = data_av_resolvida
            atual["data_avaliacao"] = data_av_resolvida
            atual["analise_json"] = analise_normalizada
        elif data_avaliacao is not None and str(data_avaliacao).strip():
            atual["data_avaliacao"] = str(data_avaliacao).strip()[:10]

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
                        "ramal": (row.get("ramal") or "").strip() or None,
                        "data_chamada": (row.get("data_chamada") or "").strip() or None,
                        "transcricao": row.get("transcricao") or None,
                        "rpa_telefone": (row.get("rpa_telefone") or "").strip() or None,
                        "rpa_texto_google": row.get("rpa_texto_google") or None,
                        "rpa_atualizado_em": (row.get("rpa_atualizado_em") or "").strip() or None,
                        "revisao": row.get("revisao") or None,
                        "id_empresa": int(id_emp_raw) if id_emp_raw.isdigit() else None,
                        "empresa_nome": row.get("empresa_nome") or None,
                        "empresa_telefone": row.get("empresa_telefone") or None,
                        "empresa_fonte_dados": row.get("empresa_fonte_dados") or None,
                        "data_avaliacao": (row.get("data_avaliacao") or "").strip() or None,
                        "analise_json": _normalizar_analise_para_json(analise_raw),
                        "etapa_falha": row.get("etapa_falha") or "",
                        "erro": row.get("erro") or "",
                        "atualizado_em": row.get("atualizado_em") or "",
                    }
                )
        return registros


def obter_registro_fallback_bd(
    log: str,
    pasta_raiz: Path | None = None,
) -> dict[str, Any] | None:
    """Retorna o registro salvo no fallback local para o `log` informado, se existir."""
    log_limpo = str(log or "").strip()
    if not log_limpo:
        return None
    for item in carregar_fallback_bd(pasta_raiz):
        if item.get("log") == log_limpo:
            return item
    return None


def buscar_logs_transcricao_fallback(
    logs: list[str],
    pasta_raiz: Path | None = None,
) -> set[str]:
    """Retorna o conjunto de `logs` que já possuem transcrição salva no fallback local."""
    if not logs:
        return set()
    alvo = set(logs)
    encontrados: set[str] = set()
    for item in carregar_fallback_bd(pasta_raiz):
        log_nome = item.get("log")
        if log_nome in alvo and item.get("transcricao") and str(item["transcricao"]).strip():
            encontrados.add(log_nome)
    return encontrados


def carregar_transcricoes_fallback_lote(
    logs: list[str],
    pasta_raiz: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Carrega metadados e transcrições em lote a partir do fallback local."""
    if not logs:
        return {}
    alvo = set(logs)
    resultado: dict[str, dict[str, Any]] = {}
    for item in carregar_fallback_bd(pasta_raiz):
        log_nome = item.get("log")
        transc = item.get("transcricao")
        if log_nome in alvo and transc and str(transc).strip():
            tel = item.get("rpa_telefone") or item.get("empresa_telefone")
            resultado[log_nome] = {
                "texto_diarizado": str(transc),
                "agente_nome": None,
                "numero": tel,
                "estado_ddd": None,
                "identificacao_cliente": None,
            }
    return resultado


def buscar_logs_analise_fallback(
    logs: list[str],
    pasta_raiz: Path | None = None,
) -> set[str]:
    """Retorna o conjunto de `logs` que já possuem análise comercial salva no fallback local."""
    if not logs:
        return set()
    alvo = set(logs)
    encontrados: set[str] = set()
    for item in carregar_fallback_bd(pasta_raiz):
        log_nome = item.get("log")
        analise = item.get("analise_json")
        if log_nome in alvo and isinstance(analise, dict) and analise:
            encontrados.add(log_nome)
    return encontrados


def buscar_logs_revisao_fallback(
    logs: list[str],
    *,
    apenas_validas: bool = True,
    pasta_raiz: Path | None = None,
) -> set[str]:
    """Retorna o conjunto de `logs` que já possuem revisão salva no fallback local."""
    if not logs:
        return set()
    from app.database.chamadas_dao import eh_revisao_texto_bruto

    alvo = set(logs)
    encontrados: set[str] = set()
    for item in carregar_fallback_bd(pasta_raiz):
        log_nome = item.get("log")
        rev = item.get("revisao")
        if log_nome not in alvo or not rev or not str(rev).strip():
            continue
        if apenas_validas:
            if not eh_revisao_texto_bruto(rev, item.get("transcricao")):
                encontrados.add(log_nome)
        else:
            encontrados.add(log_nome)
    return encontrados


def buscar_cache_rpa_fallback(
    telefones: list[str],
    pasta_raiz: Path | None = None,
) -> dict[str, str]:
    """Recupera textos do Google RPA já salvos no fallback local para os telefones pedidos."""
    if not telefones:
        return {}

    telefones_limpos = [str(t).strip() for t in telefones if t and str(t).strip()]
    if not telefones_limpos:
        return {}

    mapa_digitos_para_tel: dict[str, list[str]] = {}
    for tel in telefones_limpos:
        dig = _normalizar_digitos_tel(tel)
        if dig:
            mapa_digitos_para_tel.setdefault(dig, []).append(tel)

    cache: dict[str, str] = {}
    for item in carregar_fallback_bd(pasta_raiz):
        txt = str(item.get("rpa_texto_google") or "").strip()
        tel_salvo = str(item.get("rpa_telefone") or "").strip()
        if not txt or txt == "Não encontrado" or not tel_salvo:
            continue
        if tel_salvo in telefones_limpos and tel_salvo not in cache:
            cache[tel_salvo] = txt
        dig_salvo = _normalizar_digitos_tel(tel_salvo)
        if dig_salvo and dig_salvo in mapa_digitos_para_tel:
            for tel_pedido in mapa_digitos_para_tel[dig_salvo]:
                cache.setdefault(tel_pedido, txt)
    return cache


def salvar_cache_rpa_fallback(
    telefone: str,
    texto_google: str,
    *,
    logs: list[str] | None = None,
    erro: Exception | str | None = None,
    pasta_raiz: Path | None = None,
) -> tuple[Path, Path] | None:
    """Persiste o texto coletado pelo RPA Google nos registros correspondentes do fallback local."""
    tel_limpo = str(telefone or "").strip()
    txt_limpo = str(texto_google or "").strip()
    if not tel_limpo or not txt_limpo or txt_limpo == "Não encontrado":
        return None

    caminho_csv, caminho_json = obter_caminhos_fallback(pasta_raiz)
    agora_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    erro_str = str(erro).strip()[:400] if erro else ""
    dig_alvo = _normalizar_digitos_tel(tel_limpo)

    with _LOCK:
        registros = _carregar_registros_json(caminho_json)
        alvos: list[str] = []

        if logs:
            for lg in logs:
                lg_limpo = str(lg or "").strip()
                if lg_limpo:
                    alvos.append(lg_limpo)
        else:
            for lg_nome, reg in registros.items():
                tel_reg = str(reg.get("rpa_telefone") or reg.get("empresa_telefone") or "").strip()
                if tel_reg == tel_limpo or (dig_alvo and _normalizar_digitos_tel(tel_reg).endswith(dig_alvo[-10:])):
                    alvos.append(lg_nome)

        if not alvos:
            return None

        for lg_nome in alvos:
            atual = registros.get(lg_nome, {"log": lg_nome})
            atual["rpa_telefone"] = tel_limpo
            atual["rpa_texto_google"] = txt_limpo
            atual["rpa_atualizado_em"] = agora_iso
            if not atual.get("etapa_falha"):
                atual["etapa_falha"] = "rpa_google"
            if erro_str and not atual.get("erro"):
                atual["erro"] = erro_str
            atual["atualizado_em"] = agora_iso
            registros[lg_nome] = atual

        _persistir_arquivos_fallback(registros, caminho_csv, caminho_json)

    return caminho_csv, caminho_json


def reprocessar_fallback_bd(
    pasta_raiz: Path | None = None,
    *,
    verbose: bool = False,
) -> dict[str, int]:
    """Reinsere no PostgreSQL os registros salvos no fallback local e remove os bem-sucedidos.

    Persiste em ordem transacional para cada ligação:
      1. Cache RPA Google (`cache_rpa_google`), se coletado.
      2. Transcrição (`registro_chamadas`).
      3. Empresa + Revisão (`empresa` e `registro_chamadas.revisao`/`id_empresa`),
         enriquecendo o telefone via `chamadas.identificacao_cliente` quando disponível no banco.
      4. Análise comercial completa nas 7+ tabelas (`inserir_analise`), preservando
         a `data_avaliacao` original de quando foi executada offline e `dt_inicio`.
    """
    from app.database.chamadas_dao import (
        inserir_analise,
        inserir_empresa,
        inserir_registro_chamada,
        inserir_revisao,
        salvar_cache_rpa_google,
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
            protocolo_val = item.get("protocolo")
            protocolo_int = int(protocolo_val) if protocolo_val is not None and str(protocolo_val).isdigit() else None

            with conectar() as cur:
                # 1. Cache RPA Google
                rpa_tel = str(item.get("rpa_telefone") or "").strip()
                rpa_txt = str(item.get("rpa_texto_google") or "").strip()
                if rpa_tel and rpa_txt and rpa_txt != "Não encontrado":
                    salvar_cache_rpa_google(cur, rpa_tel, rpa_txt)

                # 2. Transcrição (registro_chamadas)
                if item.get("transcricao") and protocolo_int is not None:
                    inserir_registro_chamada(
                        cur,
                        log_arquivo=log_nome,
                        protocolo=protocolo_int,
                        transcricao=item["transcricao"],
                    )

                # 3. Empresa + Revisão
                id_empresa = item.get("id_empresa")
                if item.get("revisao"):
                    if id_empresa is None and item.get("empresa_nome"):
                        tel_empresa = item.get("empresa_telefone")
                        # Tenta enriquecer com identificacao_cliente oficial da tabela chamadas, se existir
                        if protocolo_int is not None:
                            try:
                                cur.execute(
                                    "SELECT identificacao_cliente FROM chamadas WHERE protocolo = %s LIMIT 1;",
                                    (protocolo_int,),
                                )
                                row_cli = cur.fetchone()
                                if (
                                    row_cli
                                    and isinstance(row_cli, (tuple, list))
                                    and isinstance(row_cli[0], (str, int, float))
                                ):
                                    val_cli = (
                                        str(int(row_cli[0])).strip()
                                        if isinstance(row_cli[0], (int, float))
                                        else str(row_cli[0]).strip()
                                    )
                                    if val_cli:
                                        tel_empresa = val_cli
                            except Exception:
                                pass

                        id_empresa = inserir_empresa(
                            cur,
                            item["empresa_nome"],
                            item.get("empresa_fonte_dados"),
                            telefone=tel_empresa,
                        )
                    inserir_revisao(cur, log_nome, item["revisao"], id_empresa=id_empresa)

                # 4. Análise Comercial (7+ tabelas, preservando data_avaliacao e dt_inicio)
                analise_orig = item.get("analise_json")
                if isinstance(analise_orig, dict) and analise_orig:
                    analise = copy.deepcopy(analise_orig)
                    av_ia = analise.setdefault("avaliacao_ia", {})
                    if id_empresa is not None and not av_ia.get("empresa_contatada"):
                        av_ia["empresa_contatada"] = id_empresa

                    if item.get("data_avaliacao") and not av_ia.get("data_avaliacao"):
                        av_ia["data_avaliacao"] = str(item["data_avaliacao"])[:10]

                    if not av_ia.get("dt_inicio"):
                        dt_inicio_db = None
                        if protocolo_int is not None:
                            try:
                                cur.execute(
                                    "SELECT dt_inicio FROM chamadas WHERE protocolo = %s LIMIT 1;",
                                    (protocolo_int,),
                                )
                                row_dt = cur.fetchone()
                                if row_dt and isinstance(row_dt, (tuple, list)) and isinstance(row_dt[0], (datetime, date, str)):
                                    dt_inicio_db = row_dt[0]
                            except Exception:
                                pass
                        dt_final = dt_inicio_db or item.get("data_chamada")
                        if dt_final:
                            av_ia["dt_inicio"] = dt_final

                    inserir_analise(cur, log_nome, analise)

            sucesso += 1
            if verbose:
                data_av_log = item.get("data_avaliacao") or (
                    (item.get("analise_json") or {}).get("avaliacao_ia", {}).get("data_avaliacao")
                    if isinstance(item.get("analise_json"), dict)
                    else None
                )
                print(
                    f"  [OK] {log_nome} inserido no banco"
                    + (f" (avaliação de {data_av_log})" if data_av_log else "")
                )
        except Exception as exc:
            falha += 1
            item["erro"] = str(exc)[:400]
            item["atualizado_em"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            pendentes[log_nome] = item
            if verbose:
                print(f"  [ERRO] {log_nome}: {exc}")

    with _LOCK:
        _persistir_arquivos_fallback(pendentes, caminho_csv, caminho_json)

    return {"processados": len(itens), "sucesso": sucesso, "falha": falha}


if __name__ == "__main__":
    resumo = reprocessar_fallback_bd(verbose=True)
    print(f"Reprocessamento do fallback de banco concluído: {resumo}")
