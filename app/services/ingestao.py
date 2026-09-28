# -*- coding: utf-8 -*-
"""
============================================================================
Módulo Profundo de Ingestão e Enriquecimento de Chamadas do SONAX.

Responsabilidades:
    1. Idempotência e consulta de duplicidade no banco de dados.
    2. Transcrição de áudio com retries (NVIDIA Nemotron via OpenRouter).
    3. Avaliação de qualidade do texto transcrito.
    4. Parsing de metadados do nome do arquivo (ramal, data, hora).
    5. Associação do atendente e persistência em `registro_chamadas`.
    6. Diarização e revisão com IA (Qwen Instruct).
    7. Análise de critérios PEAH com IA (GPT-4o-mini).
============================================================================
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from app.database.db import conectar
from app.logs import log_dev_exc
from app.database.chamadas_dao import (
    buscar_nome_atendente,
    buscar_revisao,
    buscar_transcricao,
    inserir_analise,
    inserir_registro_chamada,
    inserir_revisao,
    registro_ja_existe,
    verificar_coluna_revisao,
    verificar_tabela_analise,
)
from app.services.ia import ProvedorIA, ProvedorIAReal
from app.services.parses import parse_data, parse_hora, parse_nome_arquivo
from app.services.qualidade_transcricao import (
    analisar_transcricao,
    avaliar_qualidade_transcricao,
)
from app.services.transcricao import TranscricaoCancelada

SubProgressCallback = Callable[[float, str], None]


@dataclass
class TranscricaoItemResult:
    """Resultado do processo de transcrição e persistência inicial."""
    caminho: Path
    sucesso: bool
    ja_existente: bool = False
    id_registro: int | None = None
    texto_transcricao: str = ""
    agente_nome: str | None = None
    motivo_descarte: str | None = None


class ChamadaIngestor:
    """Módulo profundo que conduz a esteira de enriquecimento e persistência."""

    def __init__(self, provedor_ia: ProvedorIA | None = None):
        self.ia = provedor_ia or ProvedorIAReal()

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
        """Transcreve um arquivo, valida qualidade, resolve atendente e insere no banco."""
        # 1. Checagem prévia no banco
        try:
            with conectar() as cur:
                if registro_ja_existe(cur, caminho.name):
                    return TranscricaoItemResult(
                        caminho=caminho,
                        sucesso=False,
                        ja_existente=True,
                        motivo_descarte="Transcrição já registrada no banco.",
                    )
        except Exception:
            print(f"  [ERRO] Falha ao verificar se '{rotulo_audio}' já existe no banco")
            log_dev_exc()
            return TranscricaoItemResult(
                caminho=caminho, sucesso=False, motivo_descarte="Erro ao consultar banco de dados."
            )

        if cancel is not None and cancel.is_set():
            raise TranscricaoCancelada()

        # 2. Transcrição com retries
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

        # 3. Avaliação de qualidade do texto transcrito
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

        # 4. Parsing de metadados do nome do arquivo
        try:
            info = parse_nome_arquivo(caminho)
        except Exception:
            print(f"  [ERRO] Falha ao interpretar o nome do arquivo '{rotulo_audio}'")
            log_dev_exc()
            return TranscricaoItemResult(
                caminho=caminho, sucesso=False, motivo_descarte="Nome do arquivo em formato inválido."
            )

        if not info["ramal"].isdigit():
            print(f"  [AVISO] Ramal inválido em {rotulo_audio}: {info['ramal']!r} — pulando")
            return TranscricaoItemResult(
                caminho=caminho, sucesso=False, motivo_descarte="Ramal não numérico."
            )

        data = parse_data(info["data"])
        if data is None:
            print(f"  [AVISO] Data inválida em {rotulo_audio}: {info['data']!r} — pulando")
            return TranscricaoItemResult(
                caminho=caminho, sucesso=False, motivo_descarte="Data inválida no nome do arquivo."
            )

        hora = parse_hora(info["hora"])
        data_ligacao = datetime.combine(data, hora) if hora else datetime(data.year, data.month, data.day)
        ramal = int(info["ramal"])

        # 5. Resolução de atendente e INSERT no banco
        nome_atendente = None
        id_reg = None

        for tentativa in range(1, 4):
            try:
                with conectar() as cur:
                    nome_atendente = buscar_nome_atendente(cur, ramal, data_ligacao)
                    if nome_atendente is None:
                        print(f"  [AVISO] ramal {ramal} não encontrado em `origem` ({rotulo_audio}) — pulando")
                        break

                    id_reg = inserir_registro_chamada(
                        cur,
                        ramal=ramal,
                        agente_nome=nome_atendente,
                        data_ligacao=data_ligacao,
                        log_arquivo=caminho.name,
                        transcricao=texto_transcricao,
                    )
                break
            except Exception:
                print(f"  [ERRO] Falha ao salvar '{rotulo_audio}' no banco de dados (tentativa {tentativa}/3)")
                log_dev_exc()
                if tentativa < 3:
                    print(f"  [INFO] Tentando novamente ({tentativa + 1}/3) ...")
        else:
            print(f"  [ERRO] Não foi possível inserir '{rotulo_audio}' após 3 tentativas.")
            return TranscricaoItemResult(
                caminho=caminho, sucesso=False, motivo_descarte="Falha ao inserir no banco após 3 tentativas."
            )

        if nome_atendente is None:
            return TranscricaoItemResult(
                caminho=caminho, sucesso=False, motivo_descarte=f"Ramal {ramal} não encontrado na tabela de origem."
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
        )

    # ------------------------------------------------------------------------
    # Fase 2: Diarização e Revisão com IA (Qwen)
    # ------------------------------------------------------------------------

    def revisar_transcricao(
        self,
        log_arquivo: str,
        texto_diarizado: str | None = None,
        agente_nome: str | None = None,
        rotulo_audio: str | None = None,
        cancel: threading.Event | None = None,
    ) -> str | None:
        """Gera revisão e diarização com IA e atualiza o registro no banco."""
        nome_exibicao = rotulo_audio or log_arquivo

        if cancel is not None and cancel.is_set():
            print(f"  [CANCELADO] Revisão de {nome_exibicao} não iniciada.")
            return None

        try:
            with conectar() as cur:
                if verificar_coluna_revisao(cur, log_arquivo):
                    print(f"  [AVISO] Revisão de {nome_exibicao} já existe no banco (pulado)")
                    return None

                if not texto_diarizado or not texto_diarizado.strip():
                    texto_diarizado = buscar_transcricao(cur, log_arquivo)
        except Exception:
            print(f"  [ERRO] Falha ao verificar revisão de '{nome_exibicao}' no banco")
            log_dev_exc()
            return None

        if cancel is not None and cancel.is_set():
            print(f"  [CANCELADO] Revisão de {nome_exibicao} abortada antes da chamada de IA.")
            return None

        if not texto_diarizado or not texto_diarizado.strip():
            return None

        revisao = None
        for tentativa in range(1, 4):
            try:
                revisao = self.ia.revisar(texto_diarizado, nome_atendente=agente_nome)
                break
            except Exception:
                print(f"  [ERRO] Falha ao revisar transcrição de {nome_exibicao} (tentativa {tentativa}/3)")
                log_dev_exc()
                if tentativa < 3:
                    print(f"  [INFO] Tentando novamente ({tentativa + 1}/3) ...")
        else:
            print(f"  [ERRO] Não foi possível revisar {nome_exibicao} após 3 tentativas — próximo arquivo.")
            return None

        resultado = None
        for tentativa in range(1, 4):
            try:
                with conectar() as cur:
                    resultado = inserir_revisao(cur, log_arquivo, revisao)
                    print(f"  [INFO] Revisão de {nome_exibicao} inserida com sucesso no banco")
                break
            except Exception:
                print(f"  [ERRO] Falha ao salvar a revisão '{nome_exibicao}' no banco de dados (tentativa {tentativa}/3)")
                log_dev_exc()
                if tentativa < 3:
                    print(f"  [INFO] Tentando novamente ({tentativa + 1}/3) ...")
        else:
            print(f"  [ERRO] Não foi possível salvar a revisão '{nome_exibicao}' após 3 tentativas.")
            return None

        return resultado

    # ------------------------------------------------------------------------
    # Fase 3: Análise de Critérios com IA (GPT-4o-mini)
    # ------------------------------------------------------------------------

    def analisar_chamada(
        self,
        log_arquivo: str,
        rotulo_audio: str | None = None,
        cancel: threading.Event | None = None,
    ) -> int | None:
        """Gera análise de critérios de atendimento via IA e persiste no banco."""
        nome_exibicao = rotulo_audio or log_arquivo

        if cancel is not None and cancel.is_set():
            print(f"  [CANCELADO] Análise de {nome_exibicao} não iniciada.")
            return None

        try:
            with conectar() as cur:
                if not verificar_coluna_revisao(cur, log_arquivo):
                    return None

                revisao = buscar_revisao(cur, log_arquivo)
                if revisao is None:
                    print(f"  [AVISO] {nome_exibicao} não possui revisão de transcrição para analisar (pulado)")
                    return None

                if verificar_tabela_analise(cur, log_arquivo):
                    print(f"  [AVISO] Análise de {nome_exibicao} já existe no banco (pulado)")
                    return None
        except Exception:
            print(f"  [ERRO] Falha ao verificar dados da análise de '{nome_exibicao}' no banco")
            log_dev_exc()
            return None

        analise_ia = None
        for tentativa in range(1, 4):
            try:
                analise_ia = self.ia.analisar(revisao)
                break
            except Exception:
                print(f"  [ERRO] Falha ao realizar análise final da ligação {nome_exibicao} (tentativa {tentativa}/3)")
                log_dev_exc()
                if tentativa < 3:
                    print(f"  [INFO] Tentando novamente ({tentativa + 1}/3) ...")
        else:
            print(f"  [ERRO] Não foi possível realizar a análise final de {nome_exibicao} após 3 tentativas.")
            return None

        id_avaliacao = None
        for tentativa in range(1, 4):
            try:
                with conectar() as cur:
                    id_avaliacao = inserir_analise(
                        cur,
                        log_arquivo,
                        analise_ia["nota_final"],
                        analise_ia["feedback_geral"],
                        analise_ia["criterios"],
                        titulo=analise_ia.get("titulo"),
                        resumo_chamada=analise_ia.get("resumo_chamada"),
                        pontos_fortes=analise_ia.get("pontos_fortes"),
                        fragilidades=analise_ia.get("fragilidades"),
                        oportunidades=analise_ia.get("oportunidades"),
                    )
                    print(f"  [INFO] Análise de {nome_exibicao} inserida com sucesso no banco")
                break
            except Exception:
                print(f"  [ERRO] Falha ao salvar a análise '{nome_exibicao}' no banco de dados (tentativa {tentativa}/3)")
                log_dev_exc()
                if tentativa < 3:
                    print(f"  [INFO] Tentando novamente ({tentativa + 1}/3) ...")
        else:
            print(f"  [ERRO] Não foi possível salvar a análise '{nome_exibicao}' após 3 tentativas.")
            return None

        return id_avaliacao
