# -*- coding: utf-8 -*-
"""
============================================================================
Módulo Profundo de Ingestão e Enriquecimento de Chamadas do SONAX.

Responsabilidades:
    1. Idempotência e consulta de duplicidade no banco de dados (ou fallback local).
    2. Transcrição de áudio com retries (Faster-Whisper local).
    3. Avaliação de qualidade do texto transcrito.
    4. Parsing de metadados do nome do arquivo (ramal, data, hora, protocolo, telefone).
    5. Associação do atendente e persistência em `registro_chamadas` (ou fallback local).
    6. Cache RPA Google persistente (banco ou fallback local).
    7. Diarização e revisão com IA (DeepSeek V4 Flash / cascata Gemini).
    8. Análise de qualidade comercial com IA (SPIN/BANT/SDR).
============================================================================
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from app.database.chamadas_dao import (
    buscar_cache_rpa_google,
    buscar_chamada_valida,
    buscar_identificacao_cliente,
    buscar_logs_com_analise,
    buscar_logs_com_revisao,
    buscar_logs_com_transcricao,
    buscar_revisao,
    buscar_transcricao,
    carregar_dados_transcricoes_existentes,
    eh_revisao_texto_bruto,
    inserir_analise,
    inserir_empresa,
    inserir_registro_chamada,
    inserir_revisao,
    registro_ja_existe,
    salvar_cache_rpa_google,
    verificar_coluna_revisao,
    verificar_tabela_analise,
)
from app.database.db import conectar, testar_conexao_bd
from app.logs import log_dev_exc
from app.services.fallback_bd import (
    buscar_cache_rpa_fallback,
    buscar_logs_analise_fallback,
    buscar_logs_revisao_fallback,
    buscar_logs_transcricao_fallback,
    carregar_transcricoes_fallback_lote,
    obter_registro_fallback_bd,
    salvar_cache_rpa_fallback,
    salvar_fallback_bd,
)
from app.services.ia import ProvedorIA, ProvedorIAReal
from app.services.parses import parse_data, parse_hora, parse_nome_arquivo
from app.services.qualidade_transcricao import (
    analisar_transcricao,
    avaliar_qualidade_transcricao,
)
from app.services.transcricao import TranscricaoCancelada

SubProgressCallback = Callable[[float, str], None]


def _extrair_data_chamada_info(info: dict[str, Any] | None) -> datetime | None:
    """Extrai `datetime` da chamada a partir dos blocos `data` (DDMMAAAA) e `hora` (HHMMSS)."""
    if not info or not isinstance(info, dict):
        return None
    data_str = str(info.get("data") or "").strip()
    hora_str = str(info.get("hora") or "").strip()
    if not data_str:
        return None
    try:
        dt_d = parse_data(data_str)
        if not dt_d:
            return None
        dt_h = parse_hora(hora_str) if hora_str else None
        if dt_h:
            return datetime.combine(dt_d, dt_h)
        return datetime.combine(dt_d, datetime.min.time())
    except Exception:
        return None


def _parsear_data_chamada_str(valor: str | datetime | date | None) -> datetime | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor
    if isinstance(valor, date):
        return datetime.combine(valor, datetime.min.time())
    texto = str(valor).strip()
    if not texto:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto[:19], fmt)
        except ValueError:
            pass
    return None


@dataclass
class TranscricaoItemResult:
    """Resultado do processo de transcrição e persistência inicial."""
    caminho: Path
    sucesso: bool
    ja_existente: bool = False
    salvo_fallback: bool = False
    id_registro: int | str | None = None
    texto_transcricao: str = ""
    agente_nome: str | None = None
    numero: str | None = None
    estado_ddd: str | None = None
    identificacao_cliente: Any | None = None
    data_chamada: str | None = None
    motivo_descarte: str | None = None


class ChamadaIngestor:
    """Módulo profundo que conduz a esteira de enriquecimento e persistência."""

    def __init__(self, provedor_ia: ProvedorIA | None = None, modo_offline: bool = False):
        self.ia = provedor_ia or ProvedorIAReal()
        self.modo_offline = modo_offline

    def verificar_disponibilidade_bd(self, connect_timeout: int = 3) -> tuple[bool, str | None]:
        """Testa se o banco PostgreSQL está acessível e configurado."""
        return testar_conexao_bd(connect_timeout=connect_timeout)

    # ------------------------------------------------------------------------
    # Fase 1: Transcrição e Inserção Inicial
    # ------------------------------------------------------------------------

    def transcrever_e_inserir(
        self,
        caminho: Path,
        rotulo_audio: str,
        cancel: threading.Event | None = None,
        on_sub_progress: SubProgressCallback | None = None,
    ) -> TranscricaoItemResult:
        """Transcreve um arquivo, valida qualidade, resolve atendente e insere no banco (ou fallback local)."""
        # 1. Parsing de metadados do nome do arquivo (protocolo, ramal, telefone, data/hora) em memória
        try:
            info = parse_nome_arquivo(caminho)
        except Exception:
            print(f"  [ERRO] Falha ao interpretar o nome do arquivo '{rotulo_audio}'")
            log_dev_exc()
            return TranscricaoItemResult(
                caminho=caminho, sucesso=False, motivo_descarte="Nome do arquivo em formato inválido."
            )

        call_id_str = info.get("call_id")
        if not call_id_str or not call_id_str.isdigit():
            print(f"  [AVISO] Protocolo (call_id) não encontrado em {rotulo_audio} — pulando")
            return TranscricaoItemResult(
                caminho=caminho,
                sucesso=False,
                motivo_descarte="Protocolo (call_id) não encontrado ou inválido no nome do arquivo.",
            )
        protocolo = int(call_id_str)

        ramal_str = info.get("ramal")
        if not ramal_str:
            print(f"  [AVISO] Ramal não encontrado em {rotulo_audio} — pulando")
            return TranscricaoItemResult(
                caminho=caminho, sucesso=False, motivo_descarte="Ramal não encontrado no nome do arquivo."
            )

        dt_chamada_arq = _extrair_data_chamada_info(info)
        data_chamada_str = dt_chamada_arq.strftime("%Y-%m-%d %H:%M:%S") if dt_chamada_arq else None

        # 2. Checagem prévia no banco (ou fallback local em modo offline)
        nome_atendente: str | None = None
        numero: str | None = info.get("telefone") or None
        estado_ddd: str | None = None
        identificacao_cliente: Any | None = None
        usando_fallback_offline = self.modo_offline
        erro_bd_inicial: Exception | str | None = None

        if not usando_fallback_offline:
            try:
                with conectar() as cur:
                    if registro_ja_existe(cur, caminho.name):
                        chamada = buscar_chamada_valida(cur, protocolo=protocolo, ramal=ramal_str)
                        texto_existente = buscar_transcricao(cur, caminho.name) or ""
                        num_existente = chamada.get("numero") if chamada else None
                        if not num_existente or not str(num_existente).strip():
                            id_cli_ex = chamada.get("identificacao_cliente") if chamada else None
                            if id_cli_ex:
                                num_existente = str(int(id_cli_ex) if isinstance(id_cli_ex, (int, float)) else id_cli_ex).strip()
                            else:
                                num_existente = info.get("telefone")

                        return TranscricaoItemResult(
                            caminho=caminho,
                            sucesso=False,
                            ja_existente=True,
                            texto_transcricao=texto_existente,
                            agente_nome=chamada.get("agente_nome") if chamada else None,
                            numero=num_existente,
                            estado_ddd=chamada.get("estado_ddd") if chamada else None,
                            identificacao_cliente=chamada.get("identificacao_cliente") if chamada else None,
                            data_chamada=data_chamada_str,
                            motivo_descarte="Transcrição já registrada no banco.",
                        )

                    chamada = buscar_chamada_valida(cur, protocolo=protocolo, ramal=ramal_str)
                    if not chamada:
                        print(
                            f"  [AVISO] Chamada não encontrada na tabela chamadas (protocolo={protocolo}, ramal={ramal_str}) — pulando"
                        )
                        return TranscricaoItemResult(
                            caminho=caminho,
                            sucesso=False,
                            motivo_descarte=f"Chamada com protocolo {protocolo} e ramal {ramal_str} não encontrada na tabela chamadas.",
                        )
                    nome_atendente = chamada.get("agente_nome")
                    numero = chamada.get("numero")
                    if not numero or not str(numero).strip():
                        id_cli = chamada.get("identificacao_cliente")
                        if id_cli:
                            numero = str(int(id_cli) if isinstance(id_cli, (int, float)) else id_cli).strip()
                        else:
                            numero = info.get("telefone")
                    estado_ddd = chamada.get("estado_ddd")
                    identificacao_cliente = chamada.get("identificacao_cliente")
            except Exception as exc:
                usando_fallback_offline = True
                erro_bd_inicial = exc
                print(
                    f"  [AVISO] Banco de dados indisponível ao verificar '{rotulo_audio}'. "
                    "Continuando em modo offline (fallback local JSON/CSV)."
                )
                log_dev_exc()

        if usando_fallback_offline:
            reg_local = obter_registro_fallback_bd(caminho.name)
            if reg_local and reg_local.get("transcricao") and str(reg_local["transcricao"]).strip():
                num_local = reg_local.get("empresa_telefone") or info.get("telefone") or None
                return TranscricaoItemResult(
                    caminho=caminho,
                    sucesso=False,
                    ja_existente=True,
                    salvo_fallback=True,
                    texto_transcricao=str(reg_local["transcricao"]),
                    agente_nome=None,
                    numero=num_local,
                    estado_ddd=None,
                    identificacao_cliente=None,
                    data_chamada=reg_local.get("data_chamada") or data_chamada_str,
                    motivo_descarte="Transcrição já registrada no fallback local.",
                )

        if cancel is not None and cancel.is_set():
            raise TranscricaoCancelada()

        # 4. Transcrição com retries
        res_transcricao = None
        for tentativa in range(1, 4):
            try:
                res_transcricao = self.ia.transcrever(
                    caminho,
                    cancel=cancel,
                    on_progress=on_sub_progress,
                )
                break
            except TranscricaoCancelada:
                raise
            except Exception:
                print(f"[AVISO] Falha na transcrição de '{rotulo_audio}' (tentativa {tentativa}/3)")
                log_dev_exc()
                if tentativa < 3:
                    print(f"  [INFO] Tentando novamente ({tentativa + 1}/3) ...")
        else:
            print(f"[ERRO] Não foi possível transcrever '{rotulo_audio}' após 3 tentativas. Arquivo ignorado.")
            return TranscricaoItemResult(
                caminho=caminho, sucesso=False, motivo_descarte="Falha na transcrição após 3 tentativas."
            )

        texto_transcricao = res_transcricao.get("texto", "") if res_transcricao else ""

        # 4.5 Avaliação de qualidade do texto transcrito
        try:
            dados_transcricao = analisar_transcricao(texto_transcricao)
            metricas_transcricao = res_transcricao.get("metricas", {}) if res_transcricao else {}
            avaliacao = avaliar_qualidade_transcricao({**dados_transcricao, **metricas_transcricao})
        except Exception:
            print(f"  [ERRO] Falha ao avaliar a transcrição de '{rotulo_audio}'")
            log_dev_exc()
            return TranscricaoItemResult(
                caminho=caminho, sucesso=False, motivo_descarte="Falha na avaliação da transcrição."
            )

        if avaliacao.get("classificacao") == "Péssimo":
            print(
                f"  [AVISO] Transcrição de {rotulo_audio} não é adequada "
                f"({avaliacao.get('pontuacao', 0)}/100 - {avaliacao.get('motivo', '')}) — pulando"
            )
            return TranscricaoItemResult(
                caminho=caminho, sucesso=False, motivo_descarte="Qualidade da transcrição insuficiente (Péssimo)."
            )

        # 5. Persistência (fallback local se offline, ou INSERT no banco com fallback em caso de erro)
        if usando_fallback_offline:
            try:
                caminho_csv, caminho_json = salvar_fallback_bd(
                    log=caminho.name,
                    protocolo=protocolo,
                    ramal=ramal_str,
                    data_chamada=data_chamada_str,
                    transcricao=texto_transcricao,
                    empresa_telefone=numero,
                    etapa_falha="offline_transcricao",
                    erro=erro_bd_inicial or "Banco de dados indisponível (modo offline)",
                )
                print(
                    f"  [INFO] Transcrição de '{rotulo_audio}' salva no fallback local "
                    f"({caminho_json.name} / {caminho_csv.name})."
                )
            except Exception:
                log_dev_exc()
                return TranscricaoItemResult(
                    caminho=caminho,
                    sucesso=False,
                    motivo_descarte="Falha ao salvar transcrição no fallback local.",
                )
            return TranscricaoItemResult(
                caminho=caminho,
                sucesso=False,
                salvo_fallback=True,
                texto_transcricao=texto_transcricao,
                agente_nome=nome_atendente,
                numero=numero,
                estado_ddd=estado_ddd,
                identificacao_cliente=identificacao_cliente,
                data_chamada=data_chamada_str,
            )

        id_reg = None
        ultimo_erro_bd: Exception | None = None
        for tentativa in range(1, 4):
            try:
                with conectar() as cur:
                    id_reg = inserir_registro_chamada(
                        cur,
                        log_arquivo=caminho.name,
                        protocolo=protocolo,
                        transcricao=texto_transcricao,
                    )
                break
            except Exception as exc:
                ultimo_erro_bd = exc
                print(f"  [ERRO] Falha ao salvar '{rotulo_audio}' no banco de dados (tentativa {tentativa}/3)")
                log_dev_exc()
                if tentativa < 3:
                    print(f"  [INFO] Tentando novamente ({tentativa + 1}/3) ...")
        else:
            print(f"  [ERRO] Não foi possível inserir '{rotulo_audio}' após 3 tentativas.")
            try:
                caminho_csv, _ = salvar_fallback_bd(
                    log=caminho.name,
                    protocolo=protocolo,
                    ramal=ramal_str,
                    data_chamada=data_chamada_str,
                    transcricao=texto_transcricao,
                    empresa_telefone=numero,
                    etapa_falha="transcricao",
                    erro=ultimo_erro_bd,
                )
                print(f"  [AVISO] Dados de transcrição de '{rotulo_audio}' salvos em fallback local ({caminho_csv.name}).")
            except Exception:
                log_dev_exc()
            return TranscricaoItemResult(
                caminho=caminho,
                sucesso=False,
                salvo_fallback=True,
                texto_transcricao=texto_transcricao,
                agente_nome=nome_atendente,
                numero=numero,
                estado_ddd=estado_ddd,
                identificacao_cliente=identificacao_cliente,
                data_chamada=data_chamada_str,
                motivo_descarte="Falha ao inserir no banco após 3 tentativas.",
            )

        if id_reg is None:
            print(f"  [AVISO] Transcrição de '{rotulo_audio}' já existe no banco — pulando")
            return TranscricaoItemResult(
                caminho=caminho, sucesso=False, ja_existente=True, motivo_descarte="Registro já existente."
            )

        return TranscricaoItemResult(
            caminho=caminho,
            sucesso=True,
            id_registro=id_reg,
            texto_transcricao=texto_transcricao,
            agente_nome=nome_atendente,
            numero=numero,
            estado_ddd=estado_ddd,
            identificacao_cliente=identificacao_cliente,
            data_chamada=data_chamada_str,
        )

    # ------------------------------------------------------------------------
    # Fase 2: Diarização e Revisão com IA (DeepSeek V4 Flash)
    # ------------------------------------------------------------------------

    def verificar_revisao_existente(self, log_arquivo: str) -> bool:
        """Verifica se a ligação já possui revisão preenchida e válida no banco (ou fallback local)."""
        if self.modo_offline:
            return bool(buscar_logs_revisao_fallback([log_arquivo], apenas_validas=True))
        try:
            with conectar() as cur:
                return bool(verificar_coluna_revisao(cur, log_arquivo, apenas_validas=True))
        except Exception:
            log_dev_exc()
            return bool(buscar_logs_revisao_fallback([log_arquivo], apenas_validas=True))

    def verificar_revisoes_existentes(self, logs: list[str], apenas_validas: bool = True) -> set[str]:
        """Retorna o conjunto de logs que já possuem revisão preenchida no banco (ou fallback local)."""
        if not logs:
            return set()
        if self.modo_offline:
            return buscar_logs_revisao_fallback(logs, apenas_validas=apenas_validas)
        try:
            with conectar() as cur:
                return buscar_logs_com_revisao(cur, logs, apenas_validas=apenas_validas)
        except Exception:
            log_dev_exc()
            return buscar_logs_revisao_fallback(logs, apenas_validas=apenas_validas)

    def verificar_transcricoes_existentes(self, logs: list[str]) -> set[str]:
        """Retorna o conjunto de logs que já possuem transcrição salva no banco (ou fallback local)."""
        if not logs:
            return set()
        if self.modo_offline:
            return buscar_logs_transcricao_fallback(logs)
        try:
            with conectar() as cur:
                return buscar_logs_com_transcricao(cur, logs)
        except Exception:
            log_dev_exc()
            return buscar_logs_transcricao_fallback(logs)

    def carregar_transcricoes_lote(self, logs: list[str]) -> dict[str, dict[str, Any]]:
        """Carrega metadados e transcrições de ligações existentes no banco (ou fallback local) em lote."""
        if not logs:
            return {}
        if self.modo_offline:
            return carregar_transcricoes_fallback_lote(logs)
        try:
            with conectar() as cur:
                return carregar_dados_transcricoes_existentes(cur, logs)
        except Exception:
            log_dev_exc()
            return carregar_transcricoes_fallback_lote(logs)

    def verificar_analises_existentes(self, logs: list[str]) -> set[str]:
        """Retorna o conjunto de logs que já possuem avaliação comercial no banco (ou fallback local)."""
        if not logs:
            return set()
        if self.modo_offline:
            return buscar_logs_analise_fallback(logs)
        try:
            with conectar() as cur:
                return buscar_logs_com_analise(cur, logs)
        except Exception:
            log_dev_exc()
            return buscar_logs_analise_fallback(logs)

    def carregar_transcricoes_lote(self, logs: list[str]) -> dict[str, dict[str, Any]]:
        """Carrega metadados e transcrições de ligações existentes no banco em lote."""
        if not logs:
            return {}
        try:
            with conectar() as cur:
                return carregar_dados_transcricoes_existentes(cur, logs)
        except Exception:
            log_dev_exc()
            return {}

    def verificar_analises_existentes(self, logs: list[str]) -> set[str]:
        """Retorna o conjunto de logs que já possuem avaliação comercial no banco de dados."""
        if not logs:
            return set()
        try:
            with conectar() as cur:
                return buscar_logs_com_analise(cur, logs)
        except Exception:
            log_dev_exc()
            return set()

    def obter_cache_rpa(self, telefones: list[str], max_dias: int | None = None) -> dict[str, str]:
        """Recupera textos do Google em cache no banco (ou fallback local se offline)."""
        if not telefones:
            return {}
        if self.modo_offline:
            return buscar_cache_rpa_fallback(telefones)
        try:
            with conectar() as cur:
                return buscar_cache_rpa_google(cur, telefones, max_dias=max_dias)
        except Exception:
            log_dev_exc()
            return buscar_cache_rpa_fallback(telefones)

    def salvar_cache_rpa(
        self,
        telefone: str,
        texto_google: str,
        *,
        logs: list[str] | None = None,
    ) -> None:
        """Salva no banco (ou no fallback local se indisponível) o texto coletado pelo RPA Google."""
        if not telefone or not texto_google or texto_google == "Não encontrado":
            return
        if self.modo_offline:
            try:
                salvar_cache_rpa_fallback(
                    telefone,
                    texto_google,
                    logs=logs,
                    erro="Banco de dados indisponível (modo offline)",
                )
            except Exception:
                log_dev_exc()
            return
        try:
            with conectar() as cur:
                salvar_cache_rpa_google(cur, telefone, texto_google)
        except Exception as exc:
            log_dev_exc()
            try:
                salvar_cache_rpa_fallback(
                    telefone,
                    texto_google,
                    logs=logs,
                    erro=exc,
                )
            except Exception:
                log_dev_exc()

    def revisar_transcricao(
        self,
        log_arquivo: str,
        texto_diarizado: str | None = None,
        agente_nome: str | None = None,
        texto_google: str | None = None,
        telefone: str | None = None,
        identificacao_cliente: Any | None = None,
        rotulo_audio: str | None = None,
        cancel: threading.Event | None = None,
        rpa_telefone: str | None = None,
    ) -> dict[str, Any] | None:
        """Gera revisão e diarização com IA, triangula dados da empresa e atualiza o banco (ou fallback local)."""
        nome_exibicao = rotulo_audio or log_arquivo

        if cancel is not None and cancel.is_set():
            print(f"  [CANCELADO] Revisão de {nome_exibicao} não iniciada.")
            return None

        revisao_anterior_bruta = False
        usando_fallback_offline = self.modo_offline
        erro_bd_inicial: Exception | str | None = None

        if not usando_fallback_offline:
            try:
                with conectar() as cur:
                    if verificar_coluna_revisao(cur, log_arquivo, apenas_validas=True):
                        print(f"  [AVISO] Revisão de {nome_exibicao} já existe no banco (pulado)")
                        return None

                    rev_atual = buscar_revisao(cur, log_arquivo)
                    transc_atual = buscar_transcricao(cur, log_arquivo)
                    if rev_atual and eh_revisao_texto_bruto(rev_atual, transc_atual):
                        revisao_anterior_bruta = True

                    if not texto_diarizado or not texto_diarizado.strip():
                        texto_diarizado = transc_atual
            except Exception as exc:
                usando_fallback_offline = True
                erro_bd_inicial = exc
                print(
                    f"  [AVISO] Banco indisponível ao verificar revisão de '{nome_exibicao}'. "
                    "Continuando em modo offline (fallback local)."
                )
                log_dev_exc()

        if usando_fallback_offline:
            reg_local = obter_registro_fallback_bd(log_arquivo)
            if reg_local:
                rev_local = reg_local.get("revisao")
                transc_local = reg_local.get("transcricao")
                if rev_local and str(rev_local).strip():
                    if not eh_revisao_texto_bruto(rev_local, transc_local):
                        print(f"  [AVISO] Revisão de {nome_exibicao} já existe no fallback local (pulado)")
                        return None
                    revisao_anterior_bruta = True
                if not texto_diarizado or not texto_diarizado.strip():
                    texto_diarizado = transc_local
                if (not texto_google or texto_google == "Não encontrado") and reg_local.get("rpa_texto_google"):
                    texto_google = reg_local.get("rpa_texto_google")
                if not rpa_telefone and reg_local.get("rpa_telefone"):
                    rpa_telefone = reg_local.get("rpa_telefone")

        if cancel is not None and cancel.is_set():
            print(f"  [CANCELADO] Revisão de {nome_exibicao} abortada antes da chamada de IA.")
            return None

        if not texto_diarizado or not texto_diarizado.strip():
            return None

        from app.services.gemini_pool import obter_modelo_gemini_ativo, openrouter_em_cooldown
        from app.services.revisao import MODELO_REVISAO, MODELO_REVISAO_FALLBACK_2
        mod_rev_log = (
            obter_modelo_gemini_ativo(MODELO_REVISAO_FALLBACK_2)
            if openrouter_em_cooldown()
            else MODELO_REVISAO
        )
        if not rotulo_audio:
            print(f"  [INFO] Diarizando e revisando {nome_exibicao} ({mod_rev_log})...")

        resultado_ia = None
        for tentativa in range(1, 4):
            try:
                resultado_ia = self.ia.revisar(
                    texto_diarizado,
                    texto_copiado_google=texto_google,
                    nome_atendente=agente_nome,
                )
                if resultado_ia and isinstance(resultado_ia, dict) and resultado_ia.get("revisao"):
                    rev_candidata = str(resultado_ia.get("revisao", "")).strip()
                    if rev_candidata and not eh_revisao_texto_bruto(rev_candidata):
                        break
            except Exception:
                print(f"  [ERRO] Falha ao revisar transcrição de {nome_exibicao} (tentativa {tentativa}/3)")
                log_dev_exc()
                if tentativa < 3:
                    tempo_espera = 2 * tentativa
                    print(f"  [INFO] Tentando novamente ({tentativa + 1}/3) em {tempo_espera}s ...")
                    time.sleep(tempo_espera)
        else:
            print(
                f"  [AVISO] Não foi possível revisar {nome_exibicao} após 3 tentativas via IA. "
                "Aplicando degradação graciosa (mantendo transcrição bruta para não descartar a chamada)."
            )
            resultado_ia = {
                "empresa": "Não encontrado",
                "revisao": f"URA / Transcrição Bruta (Revisão indisponível):\n{texto_diarizado}",
                "fonte_dados": "Não identificado",
            }

        if isinstance(resultado_ia, dict):
            revisao_texto = resultado_ia.get("revisao", "")
            empresa_nome = resultado_ia.get("empresa", "Não encontrado")
            fonte_dados = resultado_ia.get("fonte_dados")
        else:
            revisao_texto = str(resultado_ia)
            empresa_nome = "Não encontrado"
            fonte_dados = None

        tel_empresa_fallback: str | None = (
            str(int(identificacao_cliente)).strip() if isinstance(identificacao_cliente, (int, float))
            else str(identificacao_cliente).strip() if identificacao_cliente is not None
            else telefone
        )

        # Metadados auxiliares extraídos do nome do arquivo para fallback
        protocolo_rev: int | None = None
        ramal_rev: str | None = None
        data_chamada_rev: str | None = None
        try:
            info_rev = parse_nome_arquivo(Path(log_arquivo))
            call_id_rev = info_rev.get("call_id")
            if call_id_rev and str(call_id_rev).isdigit():
                protocolo_rev = int(call_id_rev)
            ramal_rev = info_rev.get("ramal") or None
            dt_rev = _extrair_data_chamada_info(info_rev)
            if dt_rev:
                data_chamada_rev = dt_rev.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

        if usando_fallback_offline:
            try:
                caminho_csv, caminho_json = salvar_fallback_bd(
                    log=log_arquivo,
                    protocolo=protocolo_rev,
                    ramal=ramal_rev,
                    data_chamada=data_chamada_rev,
                    transcricao=texto_diarizado,
                    rpa_telefone=rpa_telefone,
                    rpa_texto_google=texto_google,
                    revisao=revisao_texto,
                    id_empresa=None,
                    empresa_nome=empresa_nome,
                    empresa_telefone=tel_empresa_fallback,
                    empresa_fonte_dados=fonte_dados,
                    etapa_falha="offline_revisao",
                    erro=erro_bd_inicial or "Banco de dados indisponível (modo offline)",
                )
                print(f"  [INFO] Revisão de {nome_exibicao} salva no fallback local ({caminho_json.name} / {caminho_csv.name}):")
                print(f"    • Empresa identificada: {empresa_nome}")
                from app.logs import log_dev
                if fonte_dados:
                    log_dev(f"[{nome_exibicao}] Fonte de dados da empresa: {fonte_dados}")
                log_dev(f"[{nome_exibicao}] Prévia da revisão ({len(revisao_texto)} caracteres):\n{revisao_texto[:250]}...")
            except Exception:
                log_dev_exc()
                return None

            return {
                "revisao": revisao_texto,
                "empresa": empresa_nome,
                "fonte_dados": fonte_dados,
                "id_empresa": None,
                "salvo_fallback": True,
            }

        id_empresa = None
        ultimo_erro_bd_rev: Exception | None = None
        for tentativa in range(1, 4):
            try:
                with conectar() as cur:
                    # Telefone em empresa precisa ser preenchido com identificacao_cliente da tabela chamadas
                    id_cli = identificacao_cliente
                    if not id_cli:
                        id_cli = buscar_identificacao_cliente(cur, log_arquivo=log_arquivo)

                    tel_empresa = (
                        str(int(id_cli)).strip() if isinstance(id_cli, (int, float))
                        else str(id_cli).strip() if id_cli is not None
                        else telefone
                    )
                    tel_empresa_fallback = tel_empresa

                    try:
                        with cur.connection.transaction():
                            id_empresa = inserir_empresa(cur, empresa_nome, fonte_dados, telefone=tel_empresa)
                    except Exception:
                        log_dev_exc()

                    inserir_revisao(cur, log_arquivo, revisao_texto, id_empresa=id_empresa)
                    msg_sucesso = (
                        f"  [INFO] Revisão de {nome_exibicao} substituída com sucesso no banco (revisão de IA concluída):"
                        if revisao_anterior_bruta
                        else f"  [INFO] Revisão de {nome_exibicao} gravada com sucesso no banco:"
                    )
                    print(msg_sucesso)
                    print(
                        f"    • Empresa vinculada: {empresa_nome} (ID: {id_empresa})"
                    )
                    from app.logs import log_dev
                    if fonte_dados:
                        log_dev(f"[{nome_exibicao}] Fonte de dados da empresa: {fonte_dados}")
                    log_dev(f"[{nome_exibicao}] Prévia da revisão ({len(revisao_texto)} caracteres):\n{revisao_texto[:250]}...")
                break
            except Exception as exc:
                ultimo_erro_bd_rev = exc
                print(f"  [ERRO] Falha ao salvar a revisão '{nome_exibicao}' no banco de dados (tentativa {tentativa}/3)")
                log_dev_exc()
                if tentativa < 3:
                    print(f"  [INFO] Tentando novamente ({tentativa + 1}/3) ...")
        else:
            print(f"  [ERRO] Não foi possível salvar a revisão '{nome_exibicao}' após 3 tentativas.")
            try:
                caminho_csv, _ = salvar_fallback_bd(
                    log=log_arquivo,
                    protocolo=protocolo_rev,
                    ramal=ramal_rev,
                    data_chamada=data_chamada_rev,
                    transcricao=texto_diarizado,
                    rpa_telefone=rpa_telefone,
                    rpa_texto_google=texto_google,
                    revisao=revisao_texto,
                    id_empresa=id_empresa,
                    empresa_nome=empresa_nome,
                    empresa_telefone=tel_empresa_fallback,
                    empresa_fonte_dados=fonte_dados,
                    etapa_falha="revisao",
                    erro=ultimo_erro_bd_rev,
                )
                print(f"  [AVISO] Dados de revisão de '{nome_exibicao}' salvos em fallback local ({caminho_csv.name}).")
            except Exception:
                log_dev_exc()
            return {
                "revisao": revisao_texto,
                "empresa": empresa_nome,
                "fonte_dados": fonte_dados,
                "id_empresa": id_empresa,
                "salvo_fallback": True,
            }

        return {
            "revisao": revisao_texto,
            "empresa": empresa_nome,
            "fonte_dados": fonte_dados,
            "id_empresa": id_empresa,
        }

    # ------------------------------------------------------------------------
    # Fase 3: Análise de Critérios com IA (DeepSeek V4 Flash)
    # ------------------------------------------------------------------------

    @staticmethod
    def _imprimir_resumo_analise(
        nome_exibicao: str,
        analise_ia: Any,
        *,
        destino_label: str = "no banco",
    ) -> None:
        if isinstance(analise_ia, dict):
            av_ia = analise_ia.get("avaliacao_ia", {})
            av_sdr = analise_ia.get("avaliacao_sdr", {})
            crit_lista = analise_ia.get("avaliacao_criterio", [])
            crm_dados = analise_ia.get("crm", {})
            spin = analise_ia.get("analise_spin", {})
            bant = analise_ia.get("analise_bant", {})

            nota_sdr = av_sdr.get("nota_final")
            if nota_sdr is not None:
                op_cod = av_sdr.get("codigo_oportunidade") or "Nenhum"
                print(f"  [INFO] Análise de {nome_exibicao} gravada com sucesso {destino_label}:")
                print(f"    • Nota SDR: {nota_sdr}/100 | Oportunidade: {op_cod}")
                crit_resumo = " | ".join(
                    f"{c.get('codigo_criterio', '').replace('CRIT_', '')}: {c.get('nota_criterio')}"
                    for c in crit_lista
                    if isinstance(c, dict) and c.get("codigo_criterio")
                )
                if crit_resumo:
                    print(f"    • Critérios: {crit_resumo}")

                criterios_sem_oportunidade = [
                    c.get("codigo_criterio", "").replace("CRIT_", "")
                    for c in crit_lista
                    if isinstance(c, dict) and c.get("codigo_criterio") and c.get("nota_criterio") is None
                ]
                if criterios_sem_oportunidade:
                    print(
                        f"    • [AVISO] Critérios em aberto por ausência de oportunidade no diálogo: "
                        f"{', '.join(criterios_sem_oportunidade)} (nota recalculada proporcionalmente)"
                    )

                print(
                    f"    • Lead: {av_ia.get('resultado', 'N/A')} | "
                    f"Reunião confirmada: {str(av_ia.get('reuniao_confirmada', 'n')).upper()} | "
                    f"Data confirmada: {str(av_ia.get('data_confirmada', 'n')).upper()}"
                )
                if crm_dados.get("acao"):
                    prazo_txt = f" ({crm_dados.get('prazo')})" if crm_dados.get("prazo") else ""
                    print(f"    • Próximo Passo CRM: {crm_dados.get('acao')}{prazo_txt}")
            else:
                motivo_sdr = str(av_sdr.get("feedback_geral") or "Chamada sem conteúdo avaliável para o SDR").strip()
                if motivo_sdr.lower().startswith("não avaliável:"):
                    motivo_sdr = motivo_sdr[len("não avaliável:"):].strip()
                elif motivo_sdr.lower().startswith("nao avaliavel:"):
                    motivo_sdr = motivo_sdr[len("nao avaliavel:"):].strip()

                print(f"  [AVISO] {nome_exibicao}: Chamada não avaliável para o SDR (ligação não relevante / sem avanço comercial)")
                print(f"    • Motivo: {motivo_sdr}")
                print(f"    • Status comercial: {av_ia.get('resultado', 'N/A')}")
                if crm_dados.get("acao"):
                    prazo_txt = f" ({crm_dados.get('prazo')})" if crm_dados.get("prazo") else ""
                    print(f"    • Próximo Passo CRM: {crm_dados.get('acao')}{prazo_txt}")

            from app.logs import log_dev
            log_dev(f"[{nome_exibicao}] Feedback SDR: {av_sdr.get('feedback_geral')}")
            if av_sdr.get("acertos"):
                log_dev(f"[{nome_exibicao}] Acertos SDR: {av_sdr.get('acertos')}")
            if av_sdr.get("melhorias"):
                log_dev(f"[{nome_exibicao}] Oportunidades Melhoria: {av_sdr.get('melhorias')}")
            if av_sdr.get("frase_alternativa"):
                log_dev(f"[{nome_exibicao}] Frase Sugerida: {av_sdr.get('frase_alternativa')}")
            if spin.get("problema"):
                log_dev(f"[{nome_exibicao}] SPIN - Problema: {spin.get('problema')}")
            if spin.get("implicacao"):
                log_dev(f"[{nome_exibicao}] SPIN - Implicação: {spin.get('implicacao')}")
            if bant:
                log_dev(
                    f"[{nome_exibicao}] BANT: B={bant.get('budget_classificacao')} | "
                    f"A={bant.get('authority_classificacao')} | N={bant.get('need_classificacao')} | "
                    f"T={bant.get('timeline_classificacao')}"
                )
            if crm_dados.get("resumo"):
                log_dev(f"[{nome_exibicao}] Resumo Executivo CRM: {crm_dados.get('resumo')}")
        else:
            print(f"  [INFO] Análise de {nome_exibicao} inserida com sucesso {destino_label}")

    def analisar_chamada(
        self,
        log_arquivo: str,
        rotulo_audio: str | None = None,
        cancel: threading.Event | None = None,
        permitir_texto_bruto: bool = True,
    ) -> str | None:
        """Gera análise de qualidade comercial via IA e persiste nas 7 tabelas do banco (ou fallback local)."""
        nome_exibicao = rotulo_audio or log_arquivo

        if cancel is not None and cancel.is_set():
            print(f"  [CANCELADO] Análise de {nome_exibicao} não iniciada.")
            return None

        protocolo = None
        ramal_ana: str | None = None
        id_empresa = None
        empresa_nome = None
        agente_nome = None
        transcricao_atual: str | None = None
        revisao: str | None = None
        dt_chamada_ref: datetime | date | None = None

        usando_fallback_offline = self.modo_offline
        erro_bd_inicial: Exception | str | None = None

        if not usando_fallback_offline:
            try:
                with conectar() as cur:
                    if not verificar_coluna_revisao(cur, log_arquivo, apenas_validas=not permitir_texto_bruto):
                        print(f"  [AVISO] {nome_exibicao} não possui revisão de transcrição para analisar (pulado)")
                        return None

                    revisao = buscar_revisao(cur, log_arquivo)
                    if revisao is None:
                        print(f"  [AVISO] {nome_exibicao} não possui revisão de transcrição para analisar (pulado)")
                        return None

                    if verificar_tabela_analise(cur, log_arquivo):
                        print(f"  [AVISO] Análise de {nome_exibicao} já existe no banco (pulado)")
                        return None

                    # Obter metadados da ligação
                    cur.execute(
                        "SELECT protocolo, id_empresa, transcricao FROM registro_chamadas WHERE log = %s LIMIT 1;",
                        (log_arquivo,),
                    )
                    row_reg = cur.fetchone()
                    if row_reg:
                        protocolo = row_reg[0]
                        id_empresa = row_reg[1]
                        if isinstance(row_reg, (tuple, list)) and len(row_reg) > 2 and isinstance(row_reg[2], str):
                            transcricao_atual = row_reg[2]

                    if id_empresa:
                        cur.execute(
                            "SELECT nome FROM empresa WHERE id_empresa = %s LIMIT 1;",
                            (id_empresa,),
                        )
                        row_emp = cur.fetchone()
                        if row_emp:
                            empresa_nome = row_emp[0]

                    if protocolo:
                        cur.execute(
                            "SELECT agente_nome, dt_inicio FROM chamadas WHERE protocolo = %s LIMIT 1;",
                            (protocolo,),
                        )
                        row_ch = cur.fetchone()
                        if row_ch:
                            agente_nome = row_ch[0]
                            dt_chamada_ref = row_ch[1]

            except Exception as exc:
                usando_fallback_offline = True
                erro_bd_inicial = exc
                print(
                    f"  [AVISO] Banco indisponível ao verificar dados da análise de '{nome_exibicao}'. "
                    "Continuando em modo offline (fallback local)."
                )
                log_dev_exc()

        if usando_fallback_offline:
            reg_local = obter_registro_fallback_bd(log_arquivo)
            if not reg_local:
                print(f"  [AVISO] {nome_exibicao} não possui dados salvos no fallback local para analisar (pulado)")
                return None

            revisao = reg_local.get("revisao")
            transcricao_atual = reg_local.get("transcricao")
            if not revisao or not str(revisao).strip():
                print(f"  [AVISO] {nome_exibicao} não possui revisão de transcrição no fallback local para analisar (pulado)")
                return None
            if not permitir_texto_bruto and eh_revisao_texto_bruto(revisao, transcricao_atual):
                print(f"  [AVISO] {nome_exibicao} possui apenas texto bruto no fallback local (pulado)")
                return None

            if isinstance(reg_local.get("analise_json"), dict) and reg_local.get("analise_json"):
                print(f"  [AVISO] Análise de {nome_exibicao} já existe no fallback local (pulado)")
                return None

            protocolo = reg_local.get("protocolo")
            ramal_ana = reg_local.get("ramal")
            id_empresa = reg_local.get("id_empresa")
            empresa_nome = reg_local.get("empresa_nome")
            dt_chamada_ref = _parsear_data_chamada_str(reg_local.get("data_chamada"))

            if not dt_chamada_ref or not protocolo or not ramal_ana:
                try:
                    info_ana = parse_nome_arquivo(Path(log_arquivo))
                    if not protocolo and info_ana.get("call_id") and str(info_ana["call_id"]).isdigit():
                        protocolo = int(info_ana["call_id"])
                    if not ramal_ana:
                        ramal_ana = info_ana.get("ramal") or None
                    if not dt_chamada_ref:
                        dt_chamada_ref = _extrair_data_chamada_info(info_ana)
                except Exception:
                    pass

        # Data de referência da ligação (do banco `chamadas.dt_inicio` ou da data/hora do .wav em modo offline)
        data_referencia_str = None
        data_chamada_str = None
        if dt_chamada_ref and isinstance(dt_chamada_ref, (datetime, date)):
            dias_semana = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
            dia_extenso = dias_semana[dt_chamada_ref.weekday()]
            data_chamada_str = dt_chamada_ref.strftime("%Y-%m-%d %H:%M:%S")
            data_referencia_str = f"{data_chamada_str} ({dia_extenso})"

        from app.services.analise_final_AI import MODELO_ANALISE, MODELO_ANALISE_FALLBACK_2
        from app.services.gemini_pool import obter_modelo_gemini_ativo, openrouter_em_cooldown
        mod_ana_log = (
            obter_modelo_gemini_ativo(MODELO_ANALISE_FALLBACK_2)
            if openrouter_em_cooldown()
            else MODELO_ANALISE
        )
        print(f"  [INFO] Analisando qualidade comercial de {nome_exibicao} ({mod_ana_log}) (SPIN/BANT/SDR)...")
        analise_ia = None
        for tentativa in range(1, 4):
            try:
                analise_ia = self.ia.analisar(
                    revisao,
                    protocolo=protocolo,
                    empresa_contatada=id_empresa,
                    empresa_nome=empresa_nome,
                    nome_sdr=agente_nome,
                    data_referencia=data_referencia_str,
                )
                break
            except Exception:
                print(f"  [ERRO] Falha ao realizar análise final da ligação {nome_exibicao} (tentativa {tentativa}/3)")
                log_dev_exc()
                if tentativa < 3:
                    tempo_espera = 2 * tentativa
                    print(f"  [INFO] Tentando novamente ({tentativa + 1}/3) em {tempo_espera}s ...")
                    time.sleep(tempo_espera)
        else:
            print(f"  [ERRO] Não foi possível realizar a análise final de {nome_exibicao} após 3 tentativas.")
            return None

        # Garante preservação explícita da data em que a avaliação foi executada
        data_av_str = str(date.today())
        if isinstance(analise_ia, dict):
            av_ia_dict = analise_ia.setdefault("avaliacao_ia", {})
            if av_ia_dict.get("data_avaliacao"):
                data_av_str = str(av_ia_dict["data_avaliacao"])[:10]
            else:
                av_ia_dict["data_avaliacao"] = data_av_str

        if usando_fallback_offline:
            try:
                caminho_csv, caminho_json = salvar_fallback_bd(
                    log=log_arquivo,
                    protocolo=protocolo if isinstance(protocolo, int) else None,
                    ramal=ramal_ana,
                    data_chamada=data_chamada_str,
                    transcricao=transcricao_atual,
                    revisao=revisao,
                    id_empresa=id_empresa if isinstance(id_empresa, int) else None,
                    empresa_nome=empresa_nome if isinstance(empresa_nome, str) else None,
                    data_avaliacao=data_av_str,
                    analise_json=analise_ia,
                    etapa_falha="offline_analise",
                    erro=erro_bd_inicial or "Banco de dados indisponível (modo offline)",
                )
                self._imprimir_resumo_analise(
                    nome_exibicao,
                    analise_ia,
                    destino_label=f"no fallback local ({caminho_json.name} / {caminho_csv.name})",
                )
            except Exception:
                log_dev_exc()
            return None

        id_avaliacao = None
        ultimo_erro_bd_ana: Exception | None = None
        for tentativa in range(1, 4):
            try:
                with conectar() as cur:
                    id_avaliacao = inserir_analise(
                        cur,
                        log_arquivo,
                        analise_ia,
                    )
                    self._imprimir_resumo_analise(nome_exibicao, analise_ia, destino_label="no banco")
                break
            except Exception as exc:
                ultimo_erro_bd_ana = exc
                print(f"  [ERRO] Falha ao salvar a análise '{nome_exibicao}' no banco de dados (tentativa {tentativa}/3)")
                log_dev_exc()
                if tentativa < 3:
                    print(f"  [INFO] Tentando novamente ({tentativa + 1}/3) ...")
        else:
            print(f"  [ERRO] Não foi possível salvar a análise '{nome_exibicao}' após 3 tentativas.")
            try:
                caminho_csv, _ = salvar_fallback_bd(
                    log=log_arquivo,
                    protocolo=protocolo if isinstance(protocolo, int) else None,
                    ramal=ramal_ana,
                    data_chamada=data_chamada_str,
                    transcricao=transcricao_atual,
                    revisao=revisao,
                    id_empresa=id_empresa if isinstance(id_empresa, int) else None,
                    empresa_nome=empresa_nome if isinstance(empresa_nome, str) else None,
                    data_avaliacao=data_av_str,
                    analise_json=analise_ia,
                    etapa_falha="analise",
                    erro=ultimo_erro_bd_ana,
                )
                print(f"  [AVISO] Dados da análise de '{nome_exibicao}' salvos em fallback local ({caminho_csv.name}).")
            except Exception:
                log_dev_exc()
            return None

        return id_avaliacao
