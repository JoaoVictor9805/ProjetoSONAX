# -*- coding: utf-8 -*-
"""
============================================================================
`App` — janela principal do SONAX (CustomTkinter).

Threading:
    - O usuário clica **Enviar** → uma `Thread` daemon roda
      `worker.run_pipeline` em background.
    - A main loop do Tk faz `after(50, self._poll)` a cada 50 ms para
      drenar a `EventQueue` e atualizar o `CTkTextbox` (log) e a
      `CTkProgressBar` sem travar a UI.
============================================================================
"""

from __future__ import annotations

import ctypes
import threading
from pathlib import Path

import customtkinter as ctk

from app.database.config import get_database_url
from app.services.transcrever import TranscricaoCancelada
from app.view.dialogs import pick_folder
from app.view.events import (
    DoneEvent,
    EventQueue,
    LogEvent,
    ProgressEvent,
)
from app.view.worker import run_pipeline


# Cor do texto de status por exit_code (consistente com semântica CLI).
_COR_OK = "#2ecc71"
_COR_ERRO = "#e74c3c"
_COR_NEUTRO = "#bdc3c7"


def _interromper_thread(thread_id: int, exc: type) -> bool:
    """Injeta uma exceção assíncrona na thread alvo via ctypes.

    `PyThreadState_SetAsyncExc` entrega a exceção no próximo boundary
    de bytecode da thread — na prática interrompe **imediatamente** a
    inferência do Whisper em `app/view/worker.py`, sem depender do
    hook de ~30s no `tqdm.update`. O `worker.py` já trata
    `TranscricaoCancelada` como cancelamento limpo.
    """
    api = ctypes.pythonapi.PyThreadState_SetAsyncExc
    api.argtypes = [ctypes.c_ulong, ctypes.py_object]
    api.restype = ctypes.c_int

    res = api(ctypes.c_ulong(thread_id), ctypes.py_object(exc))
    if res > 1:
        # Raro: mais de um estado de thread atendido. A API pede para
        # "destravar" com NULL para não corromper o processo.
        api(ctypes.c_ulong(thread_id), None)
        return False
    # res == 1 → exceção agendada; res == 0 → thread já encerrou.
    return res == 1


class App(ctk.CTk):
    """Janela principal do SONAX."""

    def __init__(self) -> None:
        super().__init__()

        # ----- Configuração da janela -----
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("SONAX — Transcrição de Chamadas")
        self.geometry("720x620")
        self.minsize(460, 360)

        # ----- Estado interno -----
        self._queue: EventQueue | None = None
        self._worker: threading.Thread | None = None
        self._after_id: str | None = None
        self._diretorio: Path | None = None
        self._cancel: threading.Event | None = None  # setado por "Cancelar"

        # ----- UI -----
        self._build_header()
        self._build_selector()
        self._build_progress()
        self._build_log()
        self._build_status()

    # ----------------------------------------------------------------
    # Construção da UI
    # ----------------------------------------------------------------

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 8))

        ctk.CTkLabel(
            header,
            text="SONAX - Transcrição de Chamadas",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(anchor="w")

        instrucoes = (
            "1.  Clique em Procurar e selecione a pasta descompactada com os arquivos de áudio .wav.\n"
            "2.  Você pode enviar a pasta geral ou especificar conforme seu escopo.\n"
            "3.  Quando o botão Enviar ficar disponível, clique nele para iniciar.\n"
            "4.  Acompanhe o progresso pelo log e pela barra abaixo.\n"
            "obs. Não altere o nome dos arquivos .wav. ou pastas antes de enviar"
        )
        
        ctk.CTkLabel(
            header,
            text=instrucoes,
            justify="left",
            anchor="w",
            text_color=_COR_NEUTRO,
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", pady=(6, 0), fill="x")

    def _build_selector(self) -> None:
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(12, 4))

        self._entry_path = ctk.CTkEntry(
            row,
            placeholder_text="Nenhuma pasta selecionada ...",
            state="readonly",
        )
        self._entry_path.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            row,
            text="Procurar...",
            width=120,
            command=self._on_procurar,
        ).pack(side="left", padx=(0, 8))

        self._btn_enviar = ctk.CTkButton(
            row,
            text="Enviar",
            width=100,
            state="disabled",
            command=self._on_enviar,
        )
        self._btn_enviar.pack(side="left")

        # Botão "Cancelar" fica à direita do "Enviar", mas só é
        # habilitado enquanto uma operação está rodando (idle = disabled).
        self._btn_cancelar = ctk.CTkButton(
            row,
            text="Cancelar",
            width=100,
            state="disabled",
            fg_color="#7f8c8d",       # cinza quando idle
            hover_color="#95a5a6",
            command=self._on_cancelar,
        )
        self._btn_cancelar.pack(side="left", padx=(8, 0))

    def _build_progress(self) -> None:
        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.pack(fill="x", padx=20, pady=(8, 4))

        # Label de progresso (ex: "3 / 5 arquivos  •  60%") acima da
        # barra — dá o contexto que o terminal mostrava em texto.
        self._progress_label = ctk.CTkLabel(
            wrap,
            text="",
            anchor="e",
            text_color=_COR_NEUTRO,
            font=ctk.CTkFont(size=12),
        )
        self._progress_label.pack(fill="x", pady=(0, 2))

        self._progress = ctk.CTkProgressBar(wrap, mode="determinate")
        self._progress.pack(fill="x")
        self._progress.set(0)

    def _build_log(self) -> None:
        ctk.CTkLabel(
            self,
            text="Log de execução",
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(fill="x", padx=20, pady=(10, 2))

        self._log = ctk.CTkTextbox(
            self,
            height=240,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="word",
        )
        self._log.pack(fill="both", expand=True, padx=20, pady=(0, 4))
        self._log.configure(state="disabled")

    def _build_status(self) -> None:
        self._status = ctk.CTkLabel(
            self,
            text="",
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self._status.pack(fill="x", padx=20, pady=(4, 16))

    # ----------------------------------------------------------------
    # Handlers dos botões
    # ----------------------------------------------------------------

    def _on_procurar(self) -> None:
        """Abre o diálogo nativo de seleção de pasta e valida o resultado."""
        escolha = pick_folder(self, initial=self._diretorio)
        if not escolha:
            return  # usuário cancelou

        path = Path(escolha)
        if not path.is_dir():
            self._set_status(f"Caminho inválido: {path}", cor=_COR_ERRO)
            return

        self._diretorio = path
        # CTkEntry não tem setter direto: trocamos o state, escrevemos, e voltamos.
        self._entry_path.configure(state="normal")
        self._entry_path.delete(0, "end")
        self._entry_path.insert(0, str(path))
        self._entry_path.configure(state="readonly")

        # Verifica .env antes de habilitar o botão: se faltar config, fica desabilitado.
        try:
            get_database_url()
        except KeyError as e:
            self._btn_enviar.configure(state="disabled")
            self._set_status(
                f"Configure o .env antes de processar (faltando: {e}).",
                cor=_COR_ERRO,
            )
            return

        self._btn_enviar.configure(state="normal")
        self._set_status("Pronto para enviar.", cor=_COR_NEUTRO)

    def _on_enviar(self) -> None:
        """Desabilita o botão e dispara a thread de trabalho."""
        if self._diretorio is None or self._worker is not None:
            return

        # Limpa estado visual para a nova rodada.
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        self._progress.configure(mode="determinate")
        self._progress.set(0)
        self._progress_label.configure(text="")
        self._set_status("Processando ...", cor=_COR_NEUTRO)

        # Cria o flag de cancelamento e a fila. O "Cancelar" marca o
        # flag (worker respeita entre arquivos) **e** injeta
        # `TranscricaoCancelada` na thread para interromper já o
        # arquivo em andamento — veja `_on_cancelar`. O flag cobre a
        # guarnição entre arquivos; a injeção cobre a preempção
        # intra-arquivo do Whisper. Ver [app/view/worker.py].
        self._cancel = threading.Event()
        self._queue = EventQueue()

        self._btn_enviar.configure(state="disabled")
        self._btn_cancelar.configure(
            state="normal",
            text="Cancelar",
            fg_color="#c0392b",       # vermelho enquanto ativo
            hover_color="#e74c3c",
        )

        self._worker = threading.Thread(
            target=run_pipeline,
            args=(self._diretorio, self._queue, self._cancel),
            daemon=True,
            name="sonax-pipeline",
        )
        self._worker.start()
        self._after_id = self.after(50, self._poll)

    def _on_cancelar(self) -> None:
        """Cancela **imediatamente**, interrompendo a transcrição atual.

        Além de marcar o flag de cancelamento (que o worker respeita
        entre arquivos), injeta `TranscricaoCancelada` direto na thread
        do worker via `PyThreadState_SetAsyncExc`. Isso derruba a
        inferência do Whisper em andamento sem esperar a próxima janela
        de ~30s do tqdm hook. O `salvar_no_banco` captura a exceção e
        encerra sem inserir o arquivo parcial.
        """
        if self._cancel is None or self._cancel.is_set():
            return
        self._cancel.set()

        if self._worker is not None and self._worker.ident is not None:
            _interromper_thread(self._worker.ident, TranscricaoCancelada)

        # Feedback visual imediato: o usuário sabe que o pedido foi
        # registrado mesmo antes do worker confirmar.
        self._btn_cancelar.configure(
            state="disabled",
            text="Cancelando...",
            fg_color="#7f8c8d",
            hover_color="#95a5a6",
        )
        self._set_status(
            "Cancelamento solicitado — interrompendo transcrição atual ...",
            cor=_COR_NEUTRO,
        )

    # ----------------------------------------------------------------
    # Polling: drena a fila e atualiza a UI
    # ----------------------------------------------------------------

    def _poll(self) -> None:
        """Lê eventos da `EventQueue` enquanto a thread trabalha."""
        if self._queue is None:
            return

        done_received = False
        while True:
            event = self._queue.get_event(timeout=0.02)
            if event is None:
                break
            if isinstance(event, LogEvent):
                self._append_log(event.line, event.stream)
            elif isinstance(event, ProgressEvent):
                self._apply_progress(event)
            elif isinstance(event, DoneEvent):
                self._apply_done(event)
                done_received = True
                break

        if not done_received:
            self._after_id = self.after(50, self._poll)
        else:
            # Libera referências; a thread daemon é coletada no fim do processo.
            self._worker = None
            self._after_id = None

    # ----------------------------------------------------------------
    # Atualizações de widgets
    # ----------------------------------------------------------------

    def _append_log(self, line: str, stream: str) -> None:
        prefixo = "" if stream == "out" else "[err] "
        self._log.configure(state="normal")
        self._log.insert("end-1c", f"{prefixo}{line}\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _apply_progress(self, event: ProgressEvent) -> None:
        if event.total <= 0:
            # Modo indeterminado (legado; hoje o worker sempre passa
            # `total>0`).
            if self._progress.cget("mode") != "indeterminate":
                self._progress.configure(mode="indeterminate")
            self._progress.start()
            self._progress_label.configure(text="Processando ...")
            return

        # Modo determinável: convertemos `done/total` da fase atual em
        # um percentual **cumulativo** do pipeline inteiro, para que a
        # barra nunca volte ao mudar de fase.
        #
        # Pesos por fase (somam 100%):
        #     copying     0%   → 10%   (operação única, sem granularidade)
        #     transcribing 10% → 95%   (granular por arquivo)
        #     inserting   95%  → 100%  (operação única, sem granularidade)
        step_pct = event.done / event.total
        fase = (event.phase or "").lower()
        if fase == "copying":
            cumulativo = 0.0 + step_pct * 0.10
            contexto = ""
        elif fase == "transcribing":
            cumulativo = 0.10 + step_pct * 0.85
            contexto = f"{event.done} / {event.total} arquivos  •  "
        elif fase == "inserting":
            cumulativo = 0.95 + step_pct * 0.05
            contexto = "gravando no banco  •  "
        else:
            cumulativo = step_pct
            contexto = ""

        self._progress.stop()
        self._progress.configure(mode="determinate")
        self._progress.set(cumulativo)
        self._progress_label.configure(
            text=f"{contexto}{cumulativo * 100:.0f}%"
        )

    def _apply_done(self, event: DoneEvent) -> None:
        self._progress.stop()
        self._progress.configure(mode="determinate")
        self._progress.set(1.0)
        self._progress_label.configure(text="100%")

        if event.exit_code == 0:
            self._set_status(event.summary or "Concluído.", cor=_COR_OK)
        else:
            self._set_status(
                event.error or f"Falha (exit_code={event.exit_code}).",
                cor=_COR_ERRO,
            )

        # Reseta o botão "Cancelar" para o estado idle (cinza, disabled).
        self._btn_cancelar.configure(
            state="disabled",
            text="Cancelar",
            fg_color="#7f8c8d",
            hover_color="#95a5a6",
        )
        self._cancel = None

        # Reabilita Enviar se o usuário pode tentar de novo.
        if self._diretorio is not None:
            try:
                get_database_url()
                self._btn_enviar.configure(state="normal")
            except KeyError:
                self._btn_enviar.configure(state="disabled")

    def _set_status(self, texto: str, cor: str) -> None:
        self._status.configure(text=texto, text_color=cor)

    # ----------------------------------------------------------------
    # Cleanup
    # ----------------------------------------------------------------

    def destroy(self) -> None:  # noqa: D401
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
        super().destroy()
