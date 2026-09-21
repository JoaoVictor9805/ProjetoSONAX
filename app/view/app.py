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
import re
import threading
import tkinter as tk
from pathlib import Path

import customtkinter as ctk

from app.database.config import get_database_url
from app.services.assemblyai_transcribe import TranscricaoCancelada
from app.view.dialogs import pick_archive, pick_folder
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
    inferência do Whisper em `app/view/worker.py`.
    """
    api = ctypes.pythonapi.PyThreadState_SetAsyncExc
    # Compatibilidade com plataformas 32-bit e 64-bit (Windows/Linux)
    for id_type in (ctypes.c_ulonglong, ctypes.c_ulong):
        api.argtypes = [id_type, ctypes.py_object]
        api.restype = ctypes.c_int
        try:
            res = api(id_type(thread_id), ctypes.py_object(exc))
            if res == 1:
                return True
            if res > 1:
                api(id_type(thread_id), None)
                return False
        except Exception:
            continue
    return False


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
        self._entrada: Path | None = None
        self._cancel: threading.Event | None = None  # setado por "Cancelar"
        self._modo_dev = False  # log de desenvolvimento (mostra nome real dos arquivos)
        self._modo_dev_event = threading.Event()  # sinalizado ao worker em tempo real
        self._linhas_log: list[tuple[str, str, str | None, bool]] = []
        self._rotulos: dict[str, str] = {}  # "Audio NN" -> nome do arquivo

        # ----- UI -----
        self._build_header()
        self._build_selector()
        self._build_dropdown_menu()
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
            "1.  Clique em Procurar e selecione a pasta descompactada com os arquivos de áudio \n" 
            "    .wav **ou** um arquivo .zip/.rar com a pasta.\n"
            "2.  Você pode enviar a pasta geral ou especificar conforme seu escopo.\n"
            "3.  Quando o botão Enviar ficar disponível, clique nele para iniciar.\n"
            "4.  Acompanhe o progresso pelo log e pela barra abaixo.\n"
            "\n"
            "obs. Não altere o nome dos arquivos ou pastas antes de enviar"
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
            placeholder_text="Nenhuma pasta, .zip ou .rar selecionado...",
            state="readonly",
        )
        self._entry_path.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self._btn_procurar = ctk.CTkButton(
            row,
            text="Procurar ▾",
            width=120,
            command=self._on_procurar,
        )
        self._btn_procurar.pack(side="left", padx=(0, 8))

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

    def _build_dropdown_menu(self) -> None:
        """Cria o menu dropdown de seleção com tema escuro elegante."""
        self._menu_procurar = tk.Menu(
            self,
            tearoff=0,
            bg="#2b2b2b",
            fg="#ffffff",
            activebackground="#1f538d",
            activeforeground="#ffffff",
            activeborderwidth=0,
            bd=1,
            relief="solid",
            font=("Segoe UI", 10),
        )
        self._menu_procurar.add_command(
            label="📁  Selecionar Pasta...",
            command=self._on_selecionar_pasta,
        )
        self._menu_procurar.add_command(
            label="📦  Selecionar Arquivo .ZIP / .RAR ...",
            command=self._on_selecionar_arquivo,
        )

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
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=20, pady=(4, 16))

        self._status = ctk.CTkLabel(
            footer,
            text="",
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self._status.pack(side="left", fill="x", expand=True)

        self._log_dev_button = ctk.CTkLabel(
            footer,
            text="Log User",
            text_color="#3498db",
            font=ctk.CTkFont(size=11, underline=True),
            cursor="hand2",
        )
        self._log_dev_button.pack(side="right")
        self._log_dev_button.bind("<Button-1>", self._on_log_dev_button)

    # ----------------------------------------------------------------
    # Handlers dos botões
    # ----------------------------------------------------------------

    def _on_procurar(self) -> None:
        """Abre o menu dropdown logo abaixo do botão Procurar."""
        x = self._btn_procurar.winfo_rootx()
        y = self._btn_procurar.winfo_rooty() + self._btn_procurar.winfo_height()
        try:
            self._menu_procurar.tk_popup(x, y)
        finally:
            self._menu_procurar.grab_release()

    def _on_selecionar_pasta(self) -> None:
        """Abre o seletor nativo de pasta e valida o caminho retornado."""
        escolha = pick_folder(self, initial=self._entrada)
        if not escolha:
            return  # usuário cancelou
        path = Path(escolha)
        if not path.is_dir():
            self._set_status(f"Pasta inválida: {path}", cor=_COR_ERRO)
            return
        self._entrada = path
        self._set_entry_path(path)
        self._habilitar_enviar_se_ok()

    def _on_selecionar_arquivo(self) -> None:
        """Abre o seletor nativo de arquivo .zip/.rar e valida o caminho retornado."""
        escolha = pick_archive(self, initial=self._entrada)
        if not escolha:
            return  # usuário cancelou
        path = Path(escolha)
        if not path.is_file() or path.suffix.lower() not in [".zip", ".rar"]:
            self._set_status(
                f"Selecione um arquivo .zip ou .rar (recebido: {path.suffix})",
                cor=_COR_ERRO,
            )
            return
        if path.stat().st_size == 0:
            self._set_status(f"Arquivo vazio: {path}", cor=_COR_ERRO)
            return
        self._entrada = path
        self._set_entry_path(path)
        self._habilitar_enviar_se_ok()

    def _set_entry_path(self, path: Path) -> None:
        """Atualiza o campo de texto readonly que mostra o caminho escolhido."""
        self._entry_path.configure(state="normal")
        self._entry_path.delete(0, "end")
        self._entry_path.insert(0, str(path))
        self._entry_path.configure(state="readonly")

    def _habilitar_enviar_se_ok(self) -> None:
        """Confere o .env e habilita o botão Enviar, ou mostra erro."""
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
        if self._entrada is None or self._worker is not None:
            return

        # Limpa estado visual para a nova rodada.
        self._linhas_log = []
        self._rotulos = {}
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
            args=(self._entrada, self._queue, self._cancel, self._modo_dev_event),
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

    def _on_log_dev_button(self, _event=None) -> None:  # noqa: ARG002 — evento do bind
        """Alterna o log de desenvolvimento.

        Off: exibe os rótulos genéricos ("Audio 01", "Audio 02", ...) e
             esconde as linhas técnicas (`dev_only`).
        On : re-renderiza o log substituindo esses rótulos pelo nome
             real do arquivo (disponível nos `ProgressEvent.path`) e
             revelando as linhas técnicas já capturadas.
        """
        self._modo_dev = not self._modo_dev
        if self._modo_dev:
            self._modo_dev_event.set()
        else:
            self._modo_dev_event.clear()
        self._render_log()
        self._log_dev_button.configure(
            text="Log Dev" if self._modo_dev else "Log User",
            text_color="#e67e22" if self._modo_dev else "#3498db",
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
                self._append_log(
                    event.line, event.stream, dev_only=event.dev_only,
                )
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

    def _append_log(
        self,
        line: str,
        stream: str,
        path: str | None = None,
        dev_only: bool = False,
    ) -> None:
        """Guarda a linha no buffer e re-renderiza o texto na tela.

        `dev_only=True` guarda a linha normalmente, mas ela só será
        exibida quando o Log Dev estiver ligado.
        """
        self._linhas_log.append((line, stream, path, dev_only))
        self._render_log()

    def _render_log(self) -> None:
        """Re-renderiza todo o log aplicando o formato do modo atual."""
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        for line, stream, path, dev_only in self._linhas_log:
            if dev_only and not self._modo_dev:
                continue
            self._log.insert("end-1c", f"{self._formatar_linha(line, path)}\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _formatar_linha(self, line: str, path: str | None) -> str:
        """No modo dev, troca os rótulos genéricos 'Audio NN' pelo nome do arquivo.

        `path` tem prioridade (linhas de progresso, que já sabem o arquivo).
        Para o resto (ex.: linhas de `print()`), usa o mapeamento aprendido
        dos eventos de progresso (`self._rotulos`).
        """

        if not self._modo_dev:
            return line

        def _substituir(m: re.Match[str]) -> str:
            if path is not None:
                return path
            return self._rotulos.get(m.group(0), m.group(0))

        return re.sub(r"Audio \d+", _substituir, line)

    def _apply_progress(self, event: ProgressEvent) -> None:
        if event.path and event.message:
            m = re.search(r"Audio \d+", event.message)
            if m:
                self._rotulos[m.group(0)] = event.path

        if event.total <= 0:
            # Modo indeterminado (legado; hoje o worker sempre passa
            # `total>0`).
            if self._progress.cget("mode") != "indeterminate":
                self._progress.configure(mode="indeterminate")
            self._progress.start()
            self._progress_label.configure(text="Processando ...")
            if getattr(event, "message", None) and not getattr(event, "silent", False):
                self._append_log(event.message, "out", getattr(event, "path", None))
            return

        # Modo determinável: convertemos `done/total` da fase atual em
        # um percentual **cumulativo** do pipeline inteiro, para que a
        # barra nunca volte ao mudar de fase.
        #
        # Pesos por fase (somam 100%):
        #     scanning      0%   → 2%
        #     classifying   2%   → 5%
        #     copying       5%   → 10%
        #     transcribing  10%  → 80%   (granular intra e inter arquivos)
        #     inserting     80%  → 83%
        #     reviewing     83%  → 91%
        #     analyzing     91%  → 98%
        #     cleanup       98%  → 100%
        
        step_pct = event.done / event.total
        fase = (event.phase or "").lower()
        if fase == "scanning":
            cumulativo = 0.0 + step_pct * 0.02
            contexto = "varrendo  •  "
        elif fase == "classifying":
            cumulativo = 0.02 + step_pct * 0.03
            contexto = "classificando  •  "
        elif fase == "copying":
            cumulativo = 0.05 + step_pct * 0.05
            contexto = "copiando  •  "
        elif fase == "transcribing":
            cumulativo = 0.10 + step_pct * 0.70
            done_int = min(int(event.total), int(event.done) + 1 if event.done < event.total else int(event.total))
            total_int = int(event.total)
            contexto = f"{done_int}/{total_int} arquivos  •  "
        elif fase == "inserting":
            cumulativo = 0.80 + step_pct * 0.03
            contexto = "gravando no banco  •  "
        elif fase == "reviewing":
            cumulativo = 0.83 + step_pct * 0.08
            done_int = min(
                int(event.total),
                int(event.done) + 1 if event.done < event.total else int(event.total)
            )
            total_int = int(event.total)
            contexto = f"revisando {done_int}/{total_int}  •  "
        elif fase == "analyzing":
            cumulativo = 0.91 + step_pct * 0.07
            done_int = min(
                int(event.total),
                int(event.done) + 1 if event.done < event.total else int(event.total)
            )
            total_int = int(event.total)
            contexto = f"analisando {done_int}/{total_int}  •  "
        elif fase == "cleanup":
            cumulativo = 0.98 + step_pct * 0.02
            contexto = "limpando temporários  •  "
        else:
            cumulativo = step_pct
            contexto = ""

        cumulativo = min(1.0, max(0.0, cumulativo))
        self._progress.stop()
        self._progress.configure(mode="determinate")
        self._progress.set(cumulativo)
        self._progress_label.configure(
            text=f"{contexto}{cumulativo * 100:.0f}%"
        )

        if getattr(event, "message", None) and not getattr(event, "silent", False):
            self._append_log(
                event.message, "out", getattr(event, "path", None
            ))

    def _apply_done(self, event: DoneEvent) -> None:
        self._progress.stop()
        foi_cancelado = (
            (event.summary and event.summary.lower().startswith("cancelado"))
            or (self._cancel is not None and self._cancel.is_set())
        )

        if foi_cancelado:
            self._progress.configure(mode="determinate")
            self._progress_label.configure(text="Cancelado")
            self._set_status(event.summary or "Operação cancelada.", cor=_COR_NEUTRO)
        elif event.exit_code == 0:
            self._progress.configure(mode="determinate")
            self._progress.set(1.0)
            self._progress_label.configure(text="100%")
            self._set_status(event.summary or "Concluído.", cor=_COR_OK)
        else:
            self._progress.configure(mode="determinate")
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
        if self._entrada is not None:
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
