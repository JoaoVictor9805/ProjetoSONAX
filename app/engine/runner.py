# -*- coding: utf-8 -*-
"""
============================================================================
Runner do Pipeline SONAX — Branch modoTeste.

Orquestra os módulos especializados sem depender de banco de dados, RPA Google
ou avaliação comercial:
    - `io`: varredura de arquivos de áudio de qualquer título/formato e limpeza.
    - `AudioInspector`: leitura de duração de arquivos de áudio.
    - `ChamadaIngestor`: transcrição local (Faster-Whisper) e diarização/revisão (IA).
    - `planilha`: exportação dos resultados para planilha Excel na raiz do projeto.
============================================================================
"""
from __future__ import annotations

import tempfile
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Literal

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
    coletar_audios,
    copiar_lote_trabalho,
    deletar_pasta,
)
from app.services.planilha import salvar_transcricoes_planilha
from app.services.transcricao import TranscricaoCancelada

ProgressCallback = Callable[[float, float, str, str | None, str | None], None]
LogCallback = Callable[[str, Literal["out", "err"], bool, str | None], None]
FinishedCallback = Callable[[int, str, str | None, bool], None]


class PipelineRunner:
    """Executa a sequência de transcrição, diarização e exportação em planilha (modoTeste)."""

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

    def _exportar_parcial_se_houver(self, registros: list[dict[str, Any]]) -> Path | None:
        """Salva registros já processados na planilha antes de encerrar por cancelamento."""
        if not registros:
            return None
        try:
            caminho_planilha = salvar_transcricoes_planilha(registros)
            self.on_log(
                f"[INFO] Resultados parciais salvos na planilha: {caminho_planilha}",
                "out", False, None,
            )
            return caminho_planilha
        except Exception as exc:
            self.on_log(f"[AVISO] Não foi possível salvar planilha parcial: {exc}", "err", True, None)
            return None

    def run(self) -> None:
        """Executa o fluxo de teste: varredura, transcrição, diarização e planilha na raiz."""
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

            def _log_from_stdio(line: str, stream: Literal["out", "err"], dev_only: bool) -> None:
                self.on_log(line, stream, dev_only, None)

            with redirect_engine_stdio(_log_from_stdio):
                rotulo_modo = {
                    "completo": "Modo Teste — Transcrição e Diarização (Planilha)",
                    "transcricao": "Modo Teste — Apenas Transcrição (Planilha)",
                }.get(self.modo_etapa, f"Modo Teste ({self.modo_etapa})")
                self.on_log(f"[INFO] Modo de execução selecionado: {rotulo_modo}", "out", False, None)
                self.on_log(f"[INFO] Entrada selecionada: {diretorio}", "out", False, None)

                # 1) Varredura (aceita arquivo único ou pasta, qualquer título e formatos suportados)
                self.on_progress(0, 1, "scanning", "[INFO] Varrendo arquivos de áudio ...", None)
                audios = coletar_audios(diretorio)
                self.on_progress(
                    1, 1, "scanning",
                    f"[INFO] Varredura concluída: {len(audios)} arquivo(s) de áudio encontrado(s).",
                    None,
                )

                if not audios:
                    self._limpar_temporarios()
                    self.on_log("[INFO] Nenhum arquivo de áudio compatível encontrado.", "out", False, None)
                    self.on_finished(0, "[INFO] Nenhum áudio encontrado.", None, False)
                    return

                if self.cancel_event.is_set():
                    self._limpar_temporarios()
                    self.on_finished(0, "[CANCELADO] Cancelado antes de iniciar inspeção.", None, True)
                    return

                mapa_origem = {a.name: str(a) for a in audios}

                # 2) Inspeção de duração (aceita qualquer duração válida no modoTeste)
                self.on_progress(0, 1, "classifying", "[INFO] Inspecionando arquivos de áudio ...", None)
                inspecao = self.inspector.classificar_lote(audios, cancel=self.cancel_event)
                audios_validos = list(inspecao.longos) + list(inspecao.curtos)

                self.on_log(
                    f"[INFO] Total encontrado: {len(audios)}  •  válidos: {len(audios_validos)}  •  inválidos: {len(inspecao.invalidos)}",
                    "out", False, None,
                )
                self.on_progress(
                    1, 1, "classifying",
                    f"[INFO] Inspeção concluída: {len(audios_validos)} áudio(s) elegível(is).",
                    None,
                )

                if not audios_validos:
                    self._limpar_temporarios()
                    self.on_log("[AVISO] Nenhum arquivo de áudio válido encontrado para transcrição.", "out", False, None)
                    self.on_finished(0, "[AVISO] Nenhum áudio válido encontrado.", None, False)
                    return

                if self.cancel_event.is_set():
                    self._limpar_temporarios()
                    self.on_finished(0, "[CANCELADO] Cancelado antes de iniciar cópia.", None, True)
                    return

                # 3) Cópia segura para pasta temporária de trabalho
                self.destino = Path(tempfile.mkdtemp(prefix="sonax_teste_"))
                self.on_log(f"[INFO] Pasta temporária de trabalho: {self.destino}", "out", True, None)
                self.on_progress(
                    0, len(audios_validos), "copying",
                    f"[INFO] Preparando {len(audios_validos)} arquivo(s) para processamento ...",
                    None,
                )

                def on_copy_progress(idx: int, tot: int, p: Path) -> None:
                    self.on_progress(idx, tot, "copying", None, p.name)

                copiados = copiar_lote_trabalho(
                    audios_validos, self.destino, cancel=self.cancel_event, on_progress=on_copy_progress,
                )
                self.on_progress(len(copiados), len(copiados) or 1, "copying", None, None)

                if not copiados:
                    self._limpar_temporarios()
                    self.on_log("[AVISO] Nenhum áudio elegível após cópia.", "out", False, None)
                    self.on_finished(0, "[AVISO] Nenhum áudio elegível.", None, False)
                    return

                if self.cancel_event.is_set():
                    self._limpar_temporarios()
                    self.on_finished(0, "[CANCELADO] Cancelado antes de iniciar transcrição.", None, True)
                    return

                mapa_duracoes = {m.path.name: m.duracao for m in audios_validos}

                # 4) Transcrição via Faster-Whisper (sem banco e sem exigir formato no título)
                total = len(copiados)
                transcritos = 0
                registros_por_nome: dict[str, dict[str, Any]] = {}

                self.on_progress(0, total, "transcribing", f"[INFO] Iniciando transcrição de {total} arquivo(s) ...", None)

                for i, caminho in enumerate(copiados, 1):
                    if self.cancel_event.is_set():
                        break

                    rotulo = self._rotular(i)
                    marcos_atingidos: set[int] = set()

                    def _on_sub_progress(sub_frac: float, msg: str = "") -> None:
                        pct = int(sub_frac * 100)
                        done_cum = (i - 1) + (sub_frac * 0.85)
                        msg_log = None
                        for marco in (25, 50, 75):
                            if pct >= marco and marco not in marcos_atingidos:
                                marcos_atingidos.add(marco)
                                msg_log = f"[INFO] [{i}/{total}] {rotulo}: {marco}% concluído..."
                        self.on_progress(done_cum, total, "transcribing", msg_log, caminho.name)

                    self.on_progress(
                        i - 1, total, "transcribing",
                        f"[INFO] [{i}/{total}] Transcrevendo {rotulo} via Faster-Whisper local (small)...",
                        caminho.name,
                    )

                    duracao_est = mapa_duracoes.get(caminho.name, 0.0)
                    res = self.ingestor.transcrever_sem_banco(
                        caminho,
                        rotulo_audio=rotulo,
                        cancel=self.cancel_event,
                        on_sub_progress=_on_sub_progress,
                        duracao_segundos=duracao_est,
                    )

                    agora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    if res.sucesso:
                        transcritos += 1
                        registros_por_nome[caminho.name] = {
                            "arquivo": caminho.name,
                            "data_processamento": agora_str,
                            "duracao_segundos": res.duracao_segundos or duracao_est,
                            "empresa_identificada": "Não encontrado",
                            "transcricao_diarizada": "",
                            "transcricao_bruta": res.texto_transcricao,
                            "qualidade_transcricao": res.qualidade_resumo or "",
                            "status": "Apenas Transcrição" if self.modo_etapa == "transcricao" else "Transcrito",
                            "caminho_origem": mapa_origem.get(caminho.name, str(caminho)),
                        }
                        self.on_progress(
                            i, total, "transcribing",
                            f"[INFO] [{i}/{total}] {rotulo} transcrito com sucesso.",
                            caminho.name,
                        )
                    else:
                        registros_por_nome[caminho.name] = {
                            "arquivo": caminho.name,
                            "data_processamento": agora_str,
                            "duracao_segundos": duracao_est,
                            "empresa_identificada": "Não encontrado",
                            "transcricao_diarizada": "",
                            "transcricao_bruta": "",
                            "qualidade_transcricao": "",
                            "status": f"Erro: {res.motivo_descarte or 'Falha na transcrição'}",
                            "caminho_origem": mapa_origem.get(caminho.name, str(caminho)),
                        }

                if self.cancel_event.is_set():
                    self._exportar_parcial_se_houver(list(registros_por_nome.values()))
                    self._limpar_temporarios()
                    self.on_finished(
                        0,
                        f"[CANCELADO] Cancelado após transcrever {transcritos} arquivo(s).",
                        None,
                        True,
                    )
                    return

                self.on_log(
                    f"[INFO] Transcrição finalizada: {transcritos}/{total} arquivo(s) transcrito(s).",
                    "out", False, None,
                )

                # 5) Diarização e revisão com IA (sem RPA Google e sem avaliação comercial)
                if self.modo_etapa == "transcricao":
                    self.on_log(
                        "[INFO] Modo 'Apenas Transcrição': etapa de Diarização/Revisão pulada.",
                        "out", False, None,
                    )
                else:
                    from app.services.revisao import MODELO_REVISAO
                    from app.services.gemini_pool import openrouter_em_cooldown

                    mod_rev_log = "gemini-3.1-flash-lite" if openrouter_em_cooldown() else MODELO_REVISAO
                    self.on_log(
                        f"[INFO] Iniciando diarização e revisão com IA ({mod_rev_log}) de {total} chamada(s) ...",
                        "out", False, None,
                    )

                    for idx, caminho in enumerate(copiados, 1):
                        if self.cancel_event.is_set():
                            break

                        reg = registros_por_nome.get(caminho.name)
                        if not reg or not reg.get("transcricao_bruta"):
                            continue

                        rotulo_audio = self._rotular(idx)
                        mod_rev_cur = "gemini-3.1-flash-lite" if openrouter_em_cooldown() else MODELO_REVISAO
                        msg = f"[INFO] [{idx}/{total}] Diarizando e revisando ({mod_rev_cur}): {rotulo_audio} ..."
                        self.on_progress(idx - 1, total, "reviewing", msg, caminho.name)

                        res_rev = self.ingestor.revisar_sem_banco(
                            caminho.name,
                            texto_diarizado=reg["transcricao_bruta"],
                            rotulo_audio=rotulo_audio,
                            cancel=self.cancel_event,
                        )
                        if isinstance(res_rev, dict):
                            reg["transcricao_diarizada"] = res_rev.get("revisao", "")
                            reg["empresa_identificada"] = res_rev.get("empresa") or "Não encontrado"
                            reg["status"] = (
                                "Sucesso (Transcrição bruta - IA indisponível)"
                                if res_rev.get("fallback_bruto")
                                else "Sucesso"
                            )

                    if self.cancel_event.is_set():
                        self._exportar_parcial_se_houver(list(registros_por_nome.values()))
                        self._limpar_temporarios()
                        self.on_finished(
                            0,
                            f"[CANCELADO] Cancelado durante a diarização ({transcritos} arquivo(s) transcrito(s)).",
                            None,
                            True,
                        )
                        return

                    self.on_progress(total, total, "reviewing", None, None)
                    self.on_log(
                        f"[INFO] Diarização e revisão finalizadas para {transcritos} chamada(s).",
                        "out", False, None,
                    )

                # 6) Exportação para planilha na raiz do projeto
                registros_finais = [
                    registros_por_nome[c.name]
                    for c in copiados
                    if c.name in registros_por_nome
                ]
                self.on_progress(0, 1, "exporting", "[INFO] Salvando resultados na planilha ...", None)
                caminho_planilha = salvar_transcricoes_planilha(registros_finais)
                self.on_progress(
                    1, 1, "exporting",
                    f"[INFO] Planilha salva na raiz do projeto: {caminho_planilha}",
                    None,
                )

                # 7) Limpeza
                self.on_progress(0, 1, "cleanup", "[INFO] Limpando arquivos temporários ...", None)
                self._limpar_temporarios()
                self.on_progress(1, 1, "cleanup", "[INFO] Limpeza concluída.", None)

                resumo_final = (
                    f"[INFO] Concluído! {transcritos} áudio(s) processado(s). "
                    f"Planilha salva em: {caminho_planilha.name}"
                )
                self.on_finished(0, resumo_final, None, False)

        except FileNotFoundError as e:
            self._limpar_temporarios()
            self.on_log("[FALHA TOTAL] Arquivo ou diretório inválido ou inacessível.", "err", False, None)
            self.on_log(f"{type(e).__name__}: {e}", "err", True, None)
            self.on_log(traceback.format_exc(), "err", True, None)
            self.on_finished(1, "", "Arquivo ou diretório inválido ou inacessível.", False)
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
