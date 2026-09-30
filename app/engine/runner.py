# -*- coding: utf-8 -*-
"""
============================================================================
Runner do Pipeline SONAX.

Orquestra os módulos especializados:
    - `io`: varredura de diretórios, cópia de trabalho e limpeza.
    - `AudioInspector`: parsing de cabeçalhos WAV e qualidade acústica.
    - `ChamadaIngestor`: esteira de transcrição, validação, diarização e análise.

Emite eventos de progresso, logs e status final de forma limpa e desacoplada.
============================================================================
"""
from __future__ import annotations

import threading
import traceback
from pathlib import Path
from typing import Callable, Literal

from app.database.config import get_database_url
from app.engine.stream import redirect_engine_stdio
from app.services.arquivos import (
    DescompactacaoError,
    descompactar_arquivo,
    eh_arquivo_compactado,
)
from app.services.audio_inspector import AudioInspector
from app.services.ia import ProvedorIA
from app.services.ingestao import ChamadaIngestor
from app.services.io import (
    coletar_wavs,
    copiar_lote_trabalho,
    deletar_pasta,
    resolver_destino,
)
from app.services.transcricao import TranscricaoCancelada

ProgressCallback = Callable[[float, float, str, str | None, str | None], None]
LogCallback = Callable[[str, Literal["out", "err"], bool, str | None], None]
FinishedCallback = Callable[[int, str, str | None, bool], None]


class PipelineRunner:
    """Executa a sequência de etapas de processamento do pipeline."""

    def __init__(
        self,
        entrada: Path,
        cancel_event: threading.Event,
        dev_mode_event: threading.Event,
        on_progress: ProgressCallback,
        on_log: LogCallback,
        on_finished: FinishedCallback,
        provedor_ia: ProvedorIA | None = None,
    ) -> None:
        self.entrada = entrada
        self.cancel_event = cancel_event
        self.dev_mode_event = dev_mode_event
        self.on_progress = on_progress
        self.on_log = on_log
        self.on_finished = on_finished

        self.inspector = AudioInspector()
        self.ingestor = ChamadaIngestor(provedor_ia=provedor_ia)

        self.pasta_extracao: Path | None = None
        self.destino: Path | None = None

    def _rotular(self, i: int) -> str:
        return f"Audio {i:02d}"

    def _limpar_temporarios(self) -> None:
        if self.destino is not None and self.destino.exists():
            self.on_log(f"[INFO] Excluindo pasta temporária: {self.destino} ...", "out", False, None)
            deletar_pasta(self.destino)
        if self.pasta_extracao is not None and self.pasta_extracao.exists():
            self.on_log(f"[INFO] Excluindo pasta temporária extraída: {self.pasta_extracao} ...", "out", False, None)
            deletar_pasta(self.pasta_extracao)

    def run(self) -> None:
        """Executa a sequência completa de passos do pipeline."""
        try:
            # Descompactação se arquivo comprimido (.zip / .rar)
            if eh_arquivo_compactado(self.entrada):
                self.on_log(f"[INFO] Descompactando {self.entrada.name} ...", "out", False, None)
                try:
                    self.pasta_extracao, diretorio = descompactar_arquivo(self.entrada)
                except DescompactacaoError as e:
                    self._limpar_temporarios()
                    self.on_log("[FALHA TOTAL] Não foi possível descompactar o arquivo enviado.", "err", False, None)
                    self.on_log(f"{type(e).__name__}: {e}", "err", True, None)
                    self.on_log(traceback.format_exc(), "err", True, None)
                    self.on_finished(1, "", "Arquivo compactado inválido ou corrompido.", False)
                    return
                self.on_log(f"[INFO] Extraído em: {diretorio}", "out", False, None)
            else:
                diretorio = self.entrada

            # Pre-check do .env
            try:
                get_database_url()
            except KeyError as e:
                self._limpar_temporarios()
                self.on_log("[FALHA TOTAL] Configuração do sistema ausente ou incompleta (.env).", "err", False, None)
                self.on_log(f"{type(e).__name__}: {e}", "err", True, None)
                self.on_log(traceback.format_exc(), "err", True, None)
                self.on_finished(2, "", "Configuração do banco ausente (.env).", False)
                return

            def _log_from_stdio(line: str, stream: Literal["out", "err"], dev_only: bool) -> None:
                self.on_log(line, stream, dev_only, None)

            with redirect_engine_stdio(_log_from_stdio):
                self.on_log(f"[INFO] Diretório selecionado: {diretorio}", "out", False, None)

                # 1) Varredura
                self.on_progress(0, 1, "scanning", "[INFO] Varrendo arquivos .wav ...", None)
                wavs = coletar_wavs(diretorio)
                self.on_progress(1, 1, "scanning", f"[INFO] Varredura concluída: {len(wavs)} arquivo(s) .wav encontrado(s).", None)

                if not wavs:
                    self._limpar_temporarios()
                    self.on_log("[INFO] Nenhum .wav encontrado no diretório.", "out", False, None)
                    self.on_finished(0, "[INFO] Nenhum .wav encontrado.", None, False)
                    return

                if self.cancel_event.is_set():
                    self._limpar_temporarios()
                    self.on_finished(0, "[CANCELADO] Cancelado antes de iniciar classificação.", None, True)
                    return

                # 2) Classificação por duração (AudioInspector)
                self.on_progress(0, 1, "classifying", "[INFO] Classificando arquivos por duração ...", None)
                inspecao = self.inspector.classificar_lote(wavs, cancel=self.cancel_event)
                self.on_log(
                    f"[INFO] Total: {len(wavs)}  •  >1min: {len(inspecao.longos)}  •  "
                    f"<=1min: {len(inspecao.curtos)}  •  inválidos: {len(inspecao.invalidos)}",
                    "out", False, None,
                )
                self.on_progress(1, 1, "classifying", f"[INFO] Classificação concluída: {len(inspecao.longos)} áudio(s) >1min elegível(is).", None)

                if not inspecao.longos:
                    self._limpar_temporarios()
                    self.on_log("[AVISO] Nenhum áudio com mais de 1 minuto encontrado.", "out", False, None)
                    self.on_finished(0, "[AVISO] Nenhum áudio >1min encontrado.", None, False)
                    return

                if self.cancel_event.is_set():
                    self._limpar_temporarios()
                    self.on_finished(0, "[CANCELADO] Cancelado antes de iniciar cópia.", None, True)
                    return

                # 2.5) Filtragem de qualidade acústica
                def on_quality_progress(idx: int, tot: int, p: Path) -> None:
                    self.on_progress(1, 1, "classifying", None, p.name)

                aprovados, rejeitados = self.inspector.filtrar_qualidade_acustica(
                    inspecao.longos, cancel=self.cancel_event, on_progress=on_quality_progress,
                )
                inspecao.invalidos.extend(rejeitados)
                if rejeitados:
                    self.on_log(f"[AVISO] {len(rejeitados)} áudio(s) reprovados e excluídos do processamento.", "out", False, None)

                # 3) Cópia para a pasta destino (io)
                self.destino = resolver_destino(diretorio)
                self.on_log(f"[INFO] Pasta de destino: {self.destino}", "out", False, None)
                self.on_progress(0, len(aprovados), "copying", f"[INFO] Copiando {len(aprovados)} arquivo(s) para a pasta de trabalho ...", None)

                def on_copy_progress(idx: int, tot: int, p: Path) -> None:
                    rotulo = self._rotular(idx)
                    msg = f"[INFO] Copiado ({idx}/{tot}): {rotulo}"
                    self.on_progress(idx, tot, "copying", msg, p.name)

                copiados = copiar_lote_trabalho(
                    aprovados, self.destino, cancel=self.cancel_event, on_progress=on_copy_progress,
                )
                self.on_log(f"[INFO] {len(copiados)} arquivo(s) copiado(s) para: {self.destino}", "out", False, None)
                self.on_progress(len(copiados), len(copiados), "copying", f"[INFO] {len(copiados)} arquivo(s) copiado(s) com sucesso.", None)

                if self.cancel_event.is_set():
                    self._limpar_temporarios()
                    self.on_finished(0, "[CANCELADO] Cancelado antes de iniciar transcrição.", None, True)
                    return

                # 4) Transcrição + Insert no banco (ChamadaIngestor)
                total = len(copiados)
                self.on_progress(0, total, "transcribing", f"[INFO] Iniciando transcrição (NVIDIA Nemotron) de {total} arquivo(s) ...", None)

                inseridos = 0
                ja_existentes = 0
                mapa_diarizacao: dict[str, dict] = {}

                for i, caminho in enumerate(copiados, 1):
                    if self.cancel_event.is_set():
                        break

                    rotulo = self._rotular(i)

                    def _on_sub_progress(sub_frac: float, msg: str = "") -> None:
                        pct = int(sub_frac * 100)
                        done_cum = (i - 1) + (sub_frac * 0.85)
                        self.on_progress(
                            done_cum,
                            total,
                            "transcribing",
                            f"[INFO] [{i}/{total}] {rotulo}: {pct}% {msg or 'NVIDIA Nemotron processando...'}",
                            caminho.name,
                        )

                    self.on_progress(
                        i - 1,
                        total,
                        "transcribing",
                        f"[INFO] [{i}/{total}] Enviando {rotulo} para NVIDIA Nemotron (OpenRouter)...",
                        caminho.name,
                    )

                    res = self.ingestor.transcrever_e_inserir(
                        caminho,
                        rotulo_audio=rotulo,
                        cancel=self.cancel_event,
                        on_sub_progress=_on_sub_progress,
                    )

                    if res.ja_existente:
                        ja_existentes += 1
                        mapa_diarizacao[caminho.name] = {
                            "texto_diarizado": res.texto_transcricao,
                            "agente_nome": res.agente_nome,
                            "numero": res.numero,
                            "estado_ddd": res.estado_ddd,
                            "identificacao_cliente": res.identificacao_cliente,
                        }
                        self.on_progress(
                            i,
                            total,
                            "transcribing",
                            f"[AVISO] [{i}/{total}] {rotulo} - Transcrição já registrada no banco (pulado)",
                            caminho.name,
                        )
                    elif res.sucesso:
                        inseridos += 1
                        mapa_diarizacao[caminho.name] = {
                            "texto_diarizado": res.texto_transcricao,
                            "agente_nome": res.agente_nome,
                            "numero": res.numero,
                            "estado_ddd": res.estado_ddd,
                            "identificacao_cliente": res.identificacao_cliente,
                        }
                        self.on_progress(
                            i,
                            total,
                            "transcribing",
                            f"[INFO] [{i}/{total}] {rotulo} gravado com sucesso no banco!",
                            caminho.name,
                        )

                detalhes_existentes = f" | [INFO] {ja_existentes} já existente(s)" if ja_existentes > 0 else ""

                if self.cancel_event.is_set():
                    self._limpar_temporarios()
                    self.on_finished(
                        0,
                        f"[CANCELADO] Cancelado após {inseridos} registro(s) inserido(s) com transcrição {detalhes_existentes}.",
                        None,
                        True,
                    )
                    return

                self.on_progress(
                    total,
                    total,
                    "inserting",
                    f"[INFO] Transcrição finalizada: {inseridos} registro(s) processado(s) {detalhes_existentes}.",
                    None,
                )

                # 4.25) Coleta RPA Google (Triangulação de Dados)
                from app.services.rpa_google import (
                    coletar_textos_google_lote,
                    formatar_telefone_busca,
                    obter_caminho_chrome_instalado,
                )

                telefones_para_busca: dict[str, str | None] = {}
                for arq_name, dados_audio in mapa_diarizacao.items():
                    num = dados_audio.get("numero")
                    if not num or not str(num).strip():
                        id_cli = dados_audio.get("identificacao_cliente")
                        if id_cli:
                            num = str(int(id_cli) if isinstance(id_cli, (int, float)) else id_cli).strip()
                    if not num or not str(num).strip():
                        from app.services.parses import parse_nome_arquivo
                        info_arq = parse_nome_arquivo(Path(arq_name))
                        num = info_arq.get("telefone")

                    ddd = dados_audio.get("estado_ddd")
                    telefones_para_busca[arq_name] = formatar_telefone_busca(num, ddd)

                telefones_validos = [t for t in set(telefones_para_busca.values()) if t]
                textos_google: dict[str, str] = {}

                if telefones_validos:
                    chrome_exec = obter_caminho_chrome_instalado()
                    if chrome_exec:
                        self.on_log(f"[INFO] Google Chrome detectado: {chrome_exec}", "out", True, None)
                    else:
                        self.on_log("[INFO] Usando navegador padrão do sistema para pesquisa.", "out", True, None)

                    self.on_log(
                        f"[INFO] Iniciando coleta de dados no Google via RPA para {len(telefones_validos)} telefone(s)...",
                        "out", False, None,
                    )
                    self.on_log(
                        "  [ATENÇÃO] O robô de consulta abrirá o navegador. Solte mouse e teclado.",
                        "out", False, None,
                    )

                    def _on_rpa_progress(idx: int, tot: int, tel: str) -> None:
                        msg = f"[INFO] [{idx}/{tot}] Consultando Google (RPA): {tel} ..."
                        self.on_progress(idx - 1, tot, "searching", msg, None)

                    textos_google = coletar_textos_google_lote(
                        telefones_para_busca,
                        cancel=self.cancel_event,
                        tempo_espera_pagina=6.0,
                        on_progress=_on_rpa_progress,
                    )
                    self.on_progress(len(telefones_validos), len(telefones_validos), "searching", "[INFO] Coleta RPA no Google concluída.", None)
                    self.on_log(f"[INFO] Coleta RPA no Google concluída ({len(telefones_validos)} telefone(s) consultado(s)).", "out", False, None)
                else:
                    self.on_log("[INFO] Nenhum telefone válido para consulta RPA no Google (etapa pulada).", "out", False, None)
                    textos_google = {k: "Não encontrado" for k in telefones_para_busca}

                if self.cancel_event.is_set():
                    self._limpar_temporarios()
                    self.on_finished(
                        0,
                        f"[CANCELADO] Cancelado durante a coleta RPA ({inseridos} registro(s) inserido(s)).",
                        None,
                        True,
                    )
                    return

                # 4.5) Diarização e revisão com IA (ChamadaIngestor)
                total_copiados = len(copiados)
                self.on_log(
                    f"[INFO] Iniciando diarização e revisão com IA (Qwen 30B Instruct) de {total_copiados} chamada(s) ...",
                    "out", False, None,
                )
                for idx, caminho in enumerate(copiados, 1):
                    if self.cancel_event.is_set():
                        break

                    rotulo_audio = self._rotular(idx)
                    msg = f"[INFO] [{idx}/{total_copiados}] Diarizando e revisando (Qwen Instruct): {rotulo_audio} ..."
                    self.on_progress(idx - 1, total_copiados, "reviewing", msg, caminho.name)

                    dados_audio = mapa_diarizacao.get(caminho.name, {})
                    id_cliente = dados_audio.get("identificacao_cliente")
                    tel_para_empresa = (
                        str(int(id_cliente)).strip() if isinstance(id_cliente, (int, float))
                        else str(id_cliente).strip() if id_cliente is not None
                        else telefones_para_busca.get(caminho.name)
                    )
                    res_rev = self.ingestor.revisar_transcricao(
                        caminho.name,
                        texto_diarizado=dados_audio.get("texto_diarizado"),
                        agente_nome=dados_audio.get("agente_nome"),
                        texto_google=textos_google.get(caminho.name),
                        telefone=tel_para_empresa,
                        identificacao_cliente=id_cliente,
                        rotulo_audio=rotulo_audio,
                        cancel=self.cancel_event,
                    )
                    if isinstance(res_rev, dict):
                        dados_audio["id_empresa"] = res_rev.get("id_empresa")
                        dados_audio["empresa"] = res_rev.get("empresa")

                    if self.cancel_event.wait(1.2):
                        break

                if self.cancel_event.is_set():
                    self._limpar_temporarios()
                    self.on_finished(
                        0,
                        f"[CANCELADO] Cancelado durante a diarização e revisão ({inseridos} registro(s) inserido(s)).",
                        None,
                        True,
                    )
                    return

                self.on_progress(
                    total_copiados, total_copiados, "reviewing",
                    "[INFO] Diarização e revisão das transcrições finalizada.", None,
                )
                self.on_log(
                    f"[INFO] Diarização e revisão finalizada com sucesso para {total_copiados} chamada(s).",
                    "out", False, None,
                )

                # 4.75) Análise com IA (ChamadaIngestor)
                self.on_log(
                    f"[INFO] Iniciando avaliação de critérios comerciais (GPT-4o-mini) de {total_copiados} chamada(s) ...",
                    "out", False, None,
                )
                for idx, caminho in enumerate(copiados, 1):
                    if self.cancel_event.is_set():
                        break

                    rotulo_audio = self._rotular(idx)
                    msg = f"[INFO] [{idx}/{total_copiados}] Analisando qualidade comercial SPIN/BANT/SDR (GPT-4o-mini): {rotulo_audio} ..."
                    self.on_progress(idx - 1, total_copiados, "analyzing", msg, caminho.name)

                    self.ingestor.analisar_chamada(
                        caminho.name,
                        rotulo_audio=rotulo_audio,
                        cancel=self.cancel_event,
                    )
                    if self.cancel_event.wait(1.2):
                        break

                if self.cancel_event.is_set():
                    self._limpar_temporarios()
                    self.on_finished(
                        0,
                        f"[CANCELADO] Cancelado durante a análise ({inseridos} registro(s) inserido(s)).",
                        None,
                        True,
                    )
                    return

                self.on_progress(
                    total_copiados, total_copiados, "analyzing",
                    "[INFO] Análise das ligações finalizada.", None,
                )
                self.on_log(
                    f"[INFO] Avaliação comercial concluída com sucesso para {total_copiados} chamada(s).",
                    "out", False, None,
                )

                # 5) Limpeza
                self.on_progress(0, 1, "cleanup", "[INFO] Limpando arquivos temporários ...", None)
                self._limpar_temporarios()
                self.on_progress(1, 1, "cleanup", "[INFO] Limpeza concluída.", None)

                self.on_finished(
                    0,
                    f"[INFO] {inseridos} registro(s) inserido(s) com transcrição {detalhes_existentes}.",
                    None,
                    False,
                )

        except FileNotFoundError as e:
            self._limpar_temporarios()
            self.on_log("[FALHA TOTAL] Diretório de arquivos inválido ou inacessível.", "err", False, None)
            self.on_log(f"{type(e).__name__}: {e}", "err", True, None)
            self.on_log(traceback.format_exc(), "err", True, None)
            self.on_finished(1, "", "Diretório de arquivos inválido ou inacessível.", False)
        except TranscricaoCancelada:
            self._limpar_temporarios()
            self.on_log("[CANCELADO] Cancelado durante transcrição.", "out", False, None)
            self.on_finished(0, "[CANCELADO] Cancelado durante transcrição.", None, True)
        except Exception as e:
            self._limpar_temporarios()
            tb = traceback.format_exc()
            self.on_log("[FALHA TOTAL] Ocorreu um erro inesperado e o processamento foi interrompido.", "err", False, None)
            self.on_log(f"{type(e).__name__}: {e}", "err", True, None)
            self.on_log(tb, "err", True, None)
            self.on_finished(2, "", "Erro inesperado durante o processamento.", False)
