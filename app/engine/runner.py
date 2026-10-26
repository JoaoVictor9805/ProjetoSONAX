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
        modo_etapa: str = "completo",
    ) -> None:
        self.entrada = entrada
        self.cancel_event = cancel_event
        self.dev_mode_event = dev_mode_event
        self.on_progress = on_progress
        self.on_log = on_log
        self.on_finished = on_finished
        self.modo_etapa = modo_etapa

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
                rotulo_modo = {
                    "completo": "Fluxo Completo (Transcrição, Revisão e Análise)",
                    "revisao": "A partir da Revisão (Revisão e Análise)",
                    "transcricao": "Apenas Transcrição",
                    "apenas_revisao": "Apenas Revisão",
                    "analise": "Apenas Análise Comercial (SPIN/BANT/SDR)",
                }.get(self.modo_etapa, self.modo_etapa)
                self.on_log(f"[INFO] Modo de execução selecionado: {rotulo_modo}", "out", False, None)
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

                # Checagem prévia no banco de dados para evitar inspeção acústica e cópia desnecessárias
                nomes_wavs = [w.name for w in wavs]
                try:
                    res_transc = self.ingestor.verificar_transcricoes_existentes(nomes_wavs)
                    transcricoes_no_banco = set(res_transc) if isinstance(res_transc, (set, list)) else set()
                except Exception:
                    transcricoes_no_banco = set()

                revisoes_no_banco_brutas = set()
                if self.modo_etapa == "analise":
                    try:
                        res_rev = self.ingestor.verificar_revisoes_existentes(nomes_wavs, apenas_validas=False)
                        revisoes_no_banco_brutas = set(res_rev) if isinstance(res_rev, (set, list)) else set()
                    except Exception:
                        revisoes_no_banco_brutas = set()

                # Identifica quais áudios necessitam de processamento acústico (Whisper local)
                if self.modo_etapa in ("analise", "revisao", "apenas_revisao"):
                    # Nestes modos derivados, o Faster-Whisper NUNCA deve ser executado.
                    # Áudios sem registro prévio no banco (ex.: ligações descartadas por <10 palavras) são ignorados.
                    wavs_para_processamento_acustico = []

                    if self.modo_etapa == "analise":
                        aptos = [w for w in wavs if w.name in revisoes_no_banco_brutas or w.name in transcricoes_no_banco]
                        ignorados = [w for w in wavs if w not in aptos]
                        if ignorados:
                            self.on_log(
                                f"[INFO] Modo Análise Comercial: {len(ignorados)} áudio(s) sem dados no banco ignorados (não elegíveis para análise).",
                                "out", False, None,
                            )
                        copiados = aptos
                    else:  # "revisao" ou "apenas_revisao"
                        aptos = [w for w in wavs if w.name in transcricoes_no_banco]
                        ignorados = [w for w in wavs if w not in aptos]
                        nome_modo = "A partir da Revisão" if self.modo_etapa == "revisao" else "Apenas Revisão"
                        if ignorados:
                            self.on_log(
                                f"[INFO] Modo {nome_modo}: {len(ignorados)} áudio(s) sem transcrição no banco ignorados (não elegíveis para revisão).",
                                "out", False, None,
                            )
                        copiados = aptos
                else:
                    # Em "completo" ou "transcricao", apenas os que não têm transcrição no banco passam por Whisper
                    wavs_para_processamento_acustico = [w for w in wavs if w.name not in transcricoes_no_banco]

                if not wavs_para_processamento_acustico:
                    if self.modo_etapa == "analise":
                        self.on_log(
                            f"[INFO] Todas as {len(copiados)} chamadas elegíveis já possuem dados no banco. Inspeção acústica e cópia puladas!",
                            "out", False, None,
                        )
                    elif self.modo_etapa in ("revisao", "apenas_revisao"):
                        self.on_log(
                            f"[INFO] Todas as {len(copiados)} chamadas elegíveis já possuem transcrição no banco. Inspeção acústica e cópia puladas!",
                            "out", False, None,
                        )
                    else:
                        self.on_log(
                            f"[INFO] Todas as {len(wavs)} chamadas já possuem transcrição no banco. Inspeção acústica e cópia puladas.",
                            "out", False, None,
                        )
                    self.on_progress(1, 1, "classifying", "[INFO] Inspeção acústica pulada (áudios já no banco).", None)
                    self.on_progress(1, 1, "copying", "[INFO] Cópia de arquivos pulada (processamento direto via banco).", None)
                    if self.modo_etapa not in ("analise", "revisao", "apenas_revisao"):
                        copiados = list(wavs)
                else:
                    if len(wavs_para_processamento_acustico) < len(wavs):
                        self.on_log(
                            f"[INFO] {len(wavs_para_processamento_acustico)} de {len(wavs)} áudio(s) sem transcrição no banco. Inspecionando apenas faltantes...",
                            "out", False, None,
                        )

                    # 2) Classificação por duração (AudioInspector)
                    self.on_progress(0, 1, "classifying", "[INFO] Classificando arquivos por duração ...", None)
                    inspecao = self.inspector.classificar_lote(wavs_para_processamento_acustico, cancel=self.cancel_event)
                    self.on_log(
                        f"[INFO] Total faltantes: {len(wavs_para_processamento_acustico)}  •  >1min: {len(inspecao.longos)}  •  "
                        f"<=1min: {len(inspecao.curtos)}  •  inválidos: {len(inspecao.invalidos)}",
                        "out", False, None,
                    )
                    self.on_progress(1, 1, "classifying", f"[INFO] Classificação concluída: {len(inspecao.longos)} áudio(s) >1min elegível(is).", None)

                    if not inspecao.longos and len(wavs_para_processamento_acustico) == len(wavs):
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

                    aprovados = []
                    if inspecao.longos:
                        aprovados, rejeitados = self.inspector.filtrar_qualidade_acustica(
                            inspecao.longos, cancel=self.cancel_event, on_progress=on_quality_progress,
                        )
                        inspecao.invalidos.extend(rejeitados)
                        if rejeitados:
                            self.on_log(f"[AVISO] {len(rejeitados)} áudio(s) reprovados e excluídos do processamento.", "out", False, None)

                    # 3) Cópia para a pasta destino (io)
                    if aprovados:
                        self.destino = resolver_destino(diretorio)
                        self.on_log(f"[INFO] Pasta de destino: {self.destino}", "out", False, None)
                        self.on_progress(0, len(aprovados), "copying", f"[INFO] Copiando {len(aprovados)} arquivo(s) para a pasta de trabalho ...", None)

                        def on_copy_progress(idx: int, tot: int, p: Path) -> None:
                            rotulo = self._rotular(idx)
                            msg = f"[INFO] Copiado ({idx}/{tot}): {rotulo}"
                            self.on_progress(idx, tot, "copying", msg, p.name)

                        copiados_novos = copiar_lote_trabalho(
                            aprovados, self.destino, cancel=self.cancel_event, on_progress=on_copy_progress,
                        )
                        self.on_log(f"[INFO] {len(copiados_novos)} arquivo(s) copiado(s) para: {self.destino}", "out", False, None)
                        self.on_progress(len(copiados_novos), len(copiados_novos), "copying", None, None)
                    else:
                        copiados_novos = []

                    nomes_processados = {w.name for w in wavs_para_processamento_acustico}
                    mapa_copiados = {c.name: c for c in copiados_novos}
                    copiados = [
                        mapa_copiados.get(w.name, w)
                        for w in wavs
                        if w.name in mapa_copiados or w.name not in nomes_processados
                    ]

                if not copiados:
                    self._limpar_temporarios()
                    self.on_log("[AVISO] Nenhum áudio elegível para processamento.", "out", False, None)
                    self.on_finished(0, "[AVISO] Nenhum áudio elegível.", None, False)
                    return

                if self.cancel_event.is_set():
                    self._limpar_temporarios()
                    self.on_finished(0, "[CANCELADO] Cancelado antes de iniciar transcrição.", None, True)
                    return

                # 4) Transcrição + Insert no banco (ChamadaIngestor)
                total = len(copiados)
                inseridos = 0
                ja_existentes = 0
                mapa_diarizacao: dict[str, dict] = {}

                # Determina quais arquivos precisam passar pela checagem/execução de transcrição
                if self.modo_etapa == "analise":
                    # Na etapa de análise comercial, se o áudio já tem revisão (mesmo que texto bruto),
                    # a transcrição e revisão prévias não são necessárias.
                    arquivos_para_transcrever = [c for c in copiados if c.name not in revisoes_no_banco_brutas]
                    if not arquivos_para_transcrever:
                        self.on_log(
                            f"[INFO] Todas as {total} chamadas já possuem revisão no banco de dados. Etapas de transcrição e revisão puladas!",
                            "out", False, None,
                        )
                    else:
                        faltantes_transc = [c for c in arquivos_para_transcrever if c.name not in transcricoes_no_banco]
                        if faltantes_transc:
                            self.on_log(
                                f"[INFO] Modo Análise Comercial: {len(faltantes_transc)} chamada(s) sem transcrição no banco. Transcrevendo apenas faltantes...",
                                "out", False, None,
                            )
                        else:
                            self.on_log(
                                f"[INFO] Modo Análise Comercial: {len(arquivos_para_transcrever)} chamada(s) sem revisão, mas já com transcrição no banco.",
                                "out", False, None,
                            )
                elif self.modo_etapa in ("revisao", "apenas_revisao"):
                    # Identifica quais chamadas precisam de revisão com IA (vazias ou com texto bruto)
                    nomes_copiados = [c.name for c in copiados]
                    try:
                        res_validas = self.ingestor.verificar_revisoes_existentes(nomes_copiados, apenas_validas=True)
                        revisoes_validas = set(res_validas) if isinstance(res_validas, (set, list)) else set()
                    except Exception:
                        revisoes_validas = set()

                    precisam_revisao = [c for c in copiados if c.name not in revisoes_validas]
                    qtd_validas = len(copiados) - len(precisam_revisao)
                    if qtd_validas > 0:
                        self.on_log(
                            f"[INFO] {qtd_validas} de {total} chamada(s) já possuem revisão válida com IA no banco (puladas).",
                            "out", False, None,
                        )

                    if precisam_revisao:
                        self.on_log(
                            f"[INFO] {len(precisam_revisao)} chamada(s) pendente(s) de revisão (vazias ou com texto bruto). Carregando dados do banco...",
                            "out", False, None,
                        )
                        arquivos_para_transcrever = precisam_revisao
                    else:
                        self.on_log(
                            f"[INFO] Todas as {total} chamadas já possuem revisão válida com IA no banco de dados!",
                            "out", False, None,
                        )
                        arquivos_para_transcrever = []
                else:
                    faltantes_transc = [c for c in copiados if c.name not in transcricoes_no_banco]
                    if faltantes_transc:
                        self.on_log(
                            f"[INFO] Iniciando transcrição de {len(faltantes_transc)} arquivo(s) faltante(s) (total no lote: {total}) ...",
                            "out", False, None,
                        )
                    else:
                        self.on_log(
                            f"[INFO] Todas as {total} chamadas já possuem transcrição no banco.",
                            "out", False, None,
                        )
                    arquivos_para_transcrever = copiados

                total_transc = len(arquivos_para_transcrever)
                if total_transc > 0:
                    self.on_progress(0, total_transc, "transcribing", f"[INFO] Processando transcrições ({total_transc} arquivo(s)) ...", None)

                    for i, caminho in enumerate(arquivos_para_transcrever, 1):
                        if self.cancel_event.is_set():
                            break

                        rotulo = self._rotular(i)

                        def _on_sub_progress(sub_frac: float, msg: str = "") -> None:
                            pct = int(sub_frac * 100)
                            done_cum = (i - 1) + (sub_frac * 0.85)
                            self.on_progress(
                                done_cum,
                                total_transc,
                                "transcribing",
                                f"[INFO] [{i}/{total_transc}] {rotulo}: {pct}% {msg or 'Faster-Whisper processando...'}",
                                caminho.name,
                            )

                        if caminho.name not in transcricoes_no_banco:
                            self.on_progress(
                                i - 1,
                                total_transc,
                                "transcribing",
                                f"[INFO] [{i}/{total_transc}] Transcrevendo {rotulo} via Faster-Whisper local (small)...",
                                caminho.name,
                            )
                        else:
                            self.on_progress(
                                i - 1,
                                total_transc,
                                "transcribing",
                                f"[INFO] [{i}/{total_transc}] Carregando transcrição existente de {rotulo} ...",
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
                                total_transc,
                                "transcribing",
                                f"[AVISO] [{i}/{total_transc}] {rotulo} - Transcrição já registrada no banco (pulado)",
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
                                total_transc,
                                "transcribing",
                                f"[INFO] [{i}/{total_transc}] {rotulo} gravado com sucesso no banco!",
                                caminho.name,
                            )
                else:
                    self.on_progress(1, 1, "transcribing", None, None)

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

                # Se o usuário escolheu APENAS transcrição, finaliza aqui
                if self.modo_etapa == "transcricao":
                    self.on_log("[INFO] Modo 'Apenas Transcrição': etapas de RPA, Revisão e Análise Comercial puladas.", "out", False, None)
                    self.on_progress(0, 1, "cleanup", "[INFO] Limpando arquivos temporários ...", None)
                    self._limpar_temporarios()
                    self.on_progress(1, 1, "cleanup", "[INFO] Limpeza concluída.", None)
                    self.on_finished(
                        0,
                        f"[INFO] Transcrição concluída ({inseridos} inserido(s){detalhes_existentes}).",
                        None,
                        False,
                    )
                    return

                # 4.25) Coleta RPA Google (Triangulação de Dados)
                from app.services.rpa_google import (
                    coletar_textos_google_lote,
                    formatar_telefone_busca,
                    obter_caminho_chrome_instalado,
                )

                # Verifica se a revisão da ligação já está no banco antes de acionar o robô RPA
                if self.modo_etapa == "analise":
                    # Na análise comercial, ligações com revisão bruta ou válida não necessitam de RPA/Revisão
                    arquivos_precisam_revisao = [c for c in copiados if c.name not in revisoes_no_banco_brutas]
                    revisoes_existentes = set(revisoes_no_banco_brutas)
                    arquivos_pendentes = [c.name for c in arquivos_precisam_revisao if c.name in mapa_diarizacao]
                else:
                    try:
                        res_rev = self.ingestor.verificar_revisoes_existentes(
                            list(mapa_diarizacao.keys()), apenas_validas=True
                        )
                        revisoes_existentes = set(res_rev) if isinstance(res_rev, (set, list)) else set()
                    except Exception:
                        revisoes_existentes = set()
                    arquivos_pendentes = [arq for arq in mapa_diarizacao if arq not in revisoes_existentes]

                textos_google: dict[str, str] = {}
                telefones_para_busca: dict[str, str | None] = {}

                if not arquivos_pendentes and (mapa_diarizacao or self.modo_etapa == "analise"):
                    msg_pulo = (
                        "[INFO] Revisão da ligação já está no banco de dados. Etapa de coleta RPA no Google pulada."
                        if total == 1
                        else f"[INFO] Todas as {total} ligações já possuem revisão no banco de dados. Etapa de coleta RPA no Google pulada."
                    )
                    self.on_progress(1, 1, "searching", None, None)
                    self.on_log(msg_pulo, "out", False, None)
                    textos_google = {c.name: "Não encontrado" for c in copiados}
                else:
                    if revisoes_existentes:
                        msg_existentes = (
                            "[INFO] 1 ligação já possui revisão no banco de dados e não será consultada via RPA."
                            if len(revisoes_existentes) == 1
                            else f"[INFO] {len(revisoes_existentes)} ligações já possuem revisão no banco de dados e não serão consultadas via RPA."
                        )
                        self.on_log(msg_existentes, "out", False, None)

                    for arq_name in arquivos_pendentes:
                        dados_audio = mapa_diarizacao.get(arq_name, {})
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

                    cache_banco: dict[str, str] = {}
                    if telefones_validos and hasattr(self.ingestor, "obter_cache_rpa"):
                        try:
                            res_cache = self.ingestor.obter_cache_rpa(telefones_validos)
                            if isinstance(res_cache, dict):
                                cache_banco = res_cache
                        except Exception as exc:
                            self.on_log(f"  [AVISO] Falha ao consultar cache RPA no banco: {exc}", "out", True, None)

                    telefones_a_consultar = [t for t in telefones_validos if t not in cache_banco]

                    if cache_banco:
                        qtd_cache = len(cache_banco)
                        if qtd_cache == len(telefones_validos):
                            self.on_log(
                                f"[INFO] Cache RPA Google: Todos os {len(telefones_validos)} telefone(s) já possuem dados no banco de dados. Etapa do navegador pulada com sucesso!",
                                "out", False, None,
                            )
                        else:
                            self.on_log(
                                f"[INFO] Cache RPA Google: {qtd_cache} de {len(telefones_validos)} telefone(s) recuperados do banco de dados. Apenas {len(telefones_a_consultar)} precisará(ão) de consulta no navegador.",
                                "out", False, None,
                            )

                    if telefones_a_consultar:
                        chrome_exec = obter_caminho_chrome_instalado()
                        if chrome_exec:
                            self.on_log(f"[INFO] Google Chrome detectado: {chrome_exec}", "out", True, None)
                        else:
                            self.on_log("[INFO] Usando navegador padrão do sistema para pesquisa.", "out", True, None)

                        self.on_log(
                            f"[INFO] Iniciando coleta de dados no Google via RPA para {len(telefones_a_consultar)} telefone(s)...",
                            "out", False, None,
                        )
                        self.on_log(
                            "  [ATENÇÃO] O robô de consulta abrirá o navegador. Solte mouse e teclado.",
                            "out", False, None,
                        )

                        def _on_rpa_progress(idx: int, tot: int, tel: str) -> None:
                            msg = f"[INFO] [{idx}/{tot}] Consultando Google (RPA): {tel} ..."
                            self.on_progress(idx - 1, tot, "searching", msg, None)

                        def _on_rpa_salvar(tel: str, txt: str) -> None:
                            if hasattr(self.ingestor, "salvar_cache_rpa"):
                                try:
                                    self.ingestor.salvar_cache_rpa(tel, txt)
                                except Exception as exc:
                                    self.on_log(f"  [AVISO] Erro ao salvar cache RPA de '{tel}': {exc}", "out", True, None)

                        textos_google = coletar_textos_google_lote(
                            telefones_para_busca,
                            cancel=self.cancel_event,
                            tempo_espera_pagina=6.0,
                            on_progress=_on_rpa_progress,
                            on_item_coletado=_on_rpa_salvar,
                            cache_existente=cache_banco,
                        )
                        self.on_progress(len(telefones_a_consultar), len(telefones_a_consultar), "searching", None, None)
                        self.on_log(f"[INFO] Coleta RPA no Google concluída ({len(telefones_a_consultar)} telefone(s) consultado(s)).", "out", False, None)
                    elif telefones_validos:
                        msg_pulo_cache = f"[INFO] Dados do Google de todos os {len(telefones_validos)} telefone(s) recuperados do cache (navegador pulado)."
                        self.on_progress(len(telefones_validos), len(telefones_validos), "searching", msg_pulo_cache, None)
                        textos_google = {k: cache_banco.get(tel, "Não encontrado") for k, tel in telefones_para_busca.items()}
                    else:
                        self.on_log("[INFO] Nenhum telefone válido para consulta RPA no Google (etapa pulada).", "out", False, None)
                        textos_google = {k: "Não encontrado" for k in telefones_para_busca}

                    for arq in revisoes_existentes:
                        textos_google.setdefault(arq, "Não encontrado")

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
                from app.services.revisao import MODELO_REVISAO
                from app.services.gemini_pool import openrouter_em_cooldown

                mod_rev_log = "gemini-3.1-flash-lite" if openrouter_em_cooldown() else MODELO_REVISAO
                if not arquivos_pendentes:
                    self.on_log(
                        f"[INFO] Todas as {total_copiados} chamada(s) já possuem revisão válida no banco. Etapa de revisão com IA pulada.",
                        "out", False, None,
                    )
                    self.on_progress(total_copiados, total_copiados, "reviewing", None, None)
                else:
                    self.on_log(
                        f"[INFO] Iniciando diarização e revisão com IA ({mod_rev_log}) de {len(arquivos_pendentes)} chamada(s) pendente(s) (total no lote: {total_copiados}) ...",
                        "out", False, None,
                    )
                    for idx, caminho in enumerate(copiados, 1):
                        if self.cancel_event.is_set():
                            break

                        rotulo_audio = self._rotular(idx)

                        if caminho.name in revisoes_existentes:
                            self.on_progress(
                                idx,
                                total_copiados,
                                "reviewing",
                                f"[AVISO] [{idx}/{total_copiados}] {rotulo_audio} - Revisão já registrada no banco (pulado)",
                                caminho.name,
                            )
                            continue

                        mod_rev_cur = "gemini-3.1-flash-lite" if openrouter_em_cooldown() else MODELO_REVISAO
                        msg = f"[INFO] [{idx}/{total_copiados}] Diarizando e revisando ({mod_rev_cur}): {rotulo_audio} ..."
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
                        None, None,
                    )
                    self.on_log(
                        f"[INFO] Diarização e revisão finalizada com sucesso para {total_copiados} chamada(s).",
                        "out", False, None,
                    )

                # 4.75) Análise com IA (ChamadaIngestor)
                if self.modo_etapa == "apenas_revisao":
                    self.on_log(
                        "[INFO] Modo 'Apenas Revisão': etapa de Análise Comercial pulada.",
                        "out", False, None,
                    )
                else:
                    from app.services.analise_final_AI import MODELO_ANALISE
                    from app.services.gemini_pool import openrouter_em_cooldown

                    mod_ana_log = "gemini-3.1-flash-lite" if openrouter_em_cooldown() else MODELO_ANALISE
                    self.on_log(
                        f"[INFO] Iniciando avaliação de critérios comerciais ({mod_ana_log}) de {total_copiados} chamada(s) ...",
                        "out", False, None,
                    )
                    for idx, caminho in enumerate(copiados, 1):
                        if self.cancel_event.is_set():
                            break

                        rotulo_audio = self._rotular(idx)
                        self.on_progress(idx - 1, total_copiados, "analyzing", None, caminho.name)

                        self.ingestor.analisar_chamada(
                            caminho.name,
                            rotulo_audio=rotulo_audio,
                            cancel=self.cancel_event,
                            permitir_texto_bruto=True,
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
                        None, None,
                    )
                    self.on_log(
                        f"[INFO] Avaliação comercial concluída com sucesso para {total_copiados} chamada(s).",
                        "out", False, None,
                    )

                # 5) Limpeza
                self.on_progress(0, 1, "cleanup", "[INFO] Limpando arquivos temporários ...", None)
                self._limpar_temporarios()
                self.on_progress(1, 1, "cleanup", "[INFO] Limpeza concluída.", None)

                if self.modo_etapa == "analise":
                    resumo_final = f"[INFO] Análise comercial finalizada para {total_copiados} chamada(s)."
                elif self.modo_etapa == "apenas_revisao":
                    resumo_final = f"[INFO] Revisão finalizada para {total_copiados} chamada(s)."
                elif self.modo_etapa == "revisao":
                    resumo_final = f"[INFO] Revisão e análise finalizadas para {total_copiados} chamada(s)."
                else:
                    resumo_final = f"[INFO] {inseridos} registro(s) inserido(s) com transcrição {detalhes_existentes}."

                self.on_finished(
                    0,
                    resumo_final,
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
