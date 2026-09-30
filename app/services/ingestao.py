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
    buscar_chamada_valida,
    buscar_revisao,
    buscar_transcricao,
    inserir_analise,
    inserir_empresa,
    inserir_registro_chamada,
    inserir_revisao,
    registro_ja_existe,
    verificar_coluna_revisao,
    verificar_tabela_analise,
)
from app.services.ia import ProvedorIA, ProvedorIAReal
from app.services.parses import parse_nome_arquivo
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
    id_registro: int | str | None = None
    texto_transcricao: str = ""
    agente_nome: str | None = None
    numero: str | None = None
    estado_ddd: str | None = None
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
        # 1. Parsing de metadados do nome do arquivo (protocolo e ramal) em memória
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

        # 2. Checagem prévia no banco: duplicata e existência na tabela chamadas (protocolo + ramal)
        nome_atendente = None
        try:
            with conectar() as cur:
                if registro_ja_existe(cur, caminho.name):
                    chamada = buscar_chamada_valida(cur, protocolo=protocolo, ramal=ramal_str)
                    texto_existente = buscar_transcricao(cur, caminho.name) or ""
                    return TranscricaoItemResult(
                        caminho=caminho,
                        sucesso=False,
                        ja_existente=True,
                        texto_transcricao=texto_existente,
                        agente_nome=chamada.get("agente_nome") if chamada else None,
                        numero=chamada.get("numero") if chamada else None,
                        estado_ddd=chamada.get("estado_ddd") if chamada else None,
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
                estado_ddd = chamada.get("estado_ddd")
        except Exception:
            print(f"  [ERRO] Falha ao verificar '{rotulo_audio}' no banco de dados")
            log_dev_exc()
            return TranscricaoItemResult(
                caminho=caminho, sucesso=False, motivo_descarte="Erro ao consultar banco de dados."
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

        # 4. Avaliação de qualidade do texto transcrito
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

        # 5. INSERT no banco
        id_reg = None
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
        )

    # ------------------------------------------------------------------------
    # Fase 2: Diarização e Revisão com IA (Qwen)
    # ------------------------------------------------------------------------

    def revisar_transcricao(
        self,
        log_arquivo: str,
        texto_diarizado: str | None = None,
        agente_nome: str | None = None,
        texto_google: str | None = None,
        telefone: str | None = None,
        rotulo_audio: str | None = None,
        cancel: threading.Event | None = None,
    ) -> dict[str, Any] | None:
        """Gera revisão e diarização com IA, triangula dados da empresa e atualiza o banco."""
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

        resultado_ia = None
        for tentativa in range(1, 4):
            try:
                resultado_ia = self.ia.revisar(
                    texto_diarizado,
                    texto_copiado_google=texto_google,
                    nome_atendente=agente_nome,
                )
                break
            except Exception:
                print(f"  [ERRO] Falha ao revisar transcrição de {nome_exibicao} (tentativa {tentativa}/3)")
                log_dev_exc()
                if tentativa < 3:
                    print(f"  [INFO] Tentando novamente ({tentativa + 1}/3) ...")
        else:
            print(f"  [ERRO] Não foi possível revisar {nome_exibicao} após 3 tentativas — próximo arquivo.")
            return None

        if isinstance(resultado_ia, dict):
            revisao_texto = resultado_ia.get("revisao", "")
            empresa_nome = resultado_ia.get("empresa", "Não encontrado")
            fonte_dados = resultado_ia.get("fonte_dados")
        else:
            revisao_texto = str(resultado_ia)
            empresa_nome = "Não encontrado"
            fonte_dados = None

        resultado = None
        id_empresa = None
        for tentativa in range(1, 4):
            try:
                with conectar() as cur:
                    try:
                        id_empresa = inserir_empresa(cur, empresa_nome, fonte_dados, telefone=telefone)
                    except Exception:
                        log_dev_exc()

                    resultado = inserir_revisao(cur, log_arquivo, revisao_texto, id_empresa=id_empresa)
                    print(
                        f"  [INFO] Revisão de {nome_exibicao} inserida com sucesso no banco "
                        f"(Empresa: {empresa_nome} | ID: {id_empresa})"
                    )
                break
            except Exception:
                print(f"  [ERRO] Falha ao salvar a revisão '{nome_exibicao}' no banco de dados (tentativa {tentativa}/3)")
                log_dev_exc()
                if tentativa < 3:
                    print(f"  [INFO] Tentando novamente ({tentativa + 1}/3) ...")
        else:
            print(f"  [ERRO] Não foi possível salvar a revisão '{nome_exibicao}' após 3 tentativas.")
            return None

        return {
            "revisao": revisao_texto,
            "empresa": empresa_nome,
            "fonte_dados": fonte_dados,
            "id_empresa": id_empresa,
        }

    # ------------------------------------------------------------------------
    # Fase 3: Análise de Critérios com IA (GPT-4o-mini)
    # ------------------------------------------------------------------------

    def analisar_chamada(
        self,
        log_arquivo: str,
        rotulo_audio: str | None = None,
        cancel: threading.Event | None = None,
    ) -> str | None:
        """Gera análise de qualidade comercial via IA e persiste nas 7 tabelas do banco."""
        nome_exibicao = rotulo_audio or log_arquivo

        if cancel is not None and cancel.is_set():
            print(f"  [CANCELADO] Análise de {nome_exibicao} não iniciada.")
            return None

        protocolo = None
        id_empresa = None
        empresa_nome = None
        agente_nome = None

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

                # Obter metadados da ligação
                cur.execute(
                    "SELECT protocolo, id_empresa FROM registro_chamadas WHERE log = %s LIMIT 1;",
                    (log_arquivo,),
                )
                row_reg = cur.fetchone()
                if row_reg:
                    protocolo = row_reg[0]
                    id_empresa = row_reg[1]

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
                        "SELECT agente_nome FROM chamadas WHERE protocolo = %s LIMIT 1;",
                        (protocolo,),
                    )
                    row_ch = cur.fetchone()
                    if row_ch:
                        agente_nome = row_ch[0]

        except Exception:
            print(f"  [ERRO] Falha ao verificar dados da análise de '{nome_exibicao}' no banco")
            log_dev_exc()
            return None

        analise_ia = None
        for tentativa in range(1, 4):
            try:
                analise_ia = self.ia.analisar(
                    revisao,
                    protocolo=protocolo,
                    empresa_contatada=id_empresa,
                    empresa_nome=empresa_nome,
                    nome_sdr=agente_nome,
                )
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
                        analise_ia,
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
