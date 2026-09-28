# -*- coding: utf-8 -*-
"""
============================================================================
`App` — Janela Principal do SONAX (CustomTkinter).

Camada de Apresentação Pura:
    - Renderiza a interface gráfica, layout e controles visuais.
    - Conecta-se à `PipelineEngine` via interface mínima:
      `start`, `cancel`, `subscribe`, `set_dev_mode`.
    - Não contém concorrência de baixo nível, ctypes ou matemática
      fracionária de fases do pipeline.
============================================================================
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path

import customtkinter as ctk

from app.database.config import get_database_url
from app.engine import (
    EngineEvent,
    ExecutionFinishedEvent,
    LogMessageEvent,
    PipelineEngine,
    ProgressUpdateEvent,
)
from app.view.dialogs import ModalFechamentoMensal, pick_archive, pick_folder

# Cor do texto de status por exit_code (consistente com semântica CLI).
_COR_OK = "#2ecc71"
_COR_ERRO = "#e74c3c"
_COR_NEUTRO = "#bdc3c7"


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

        # ----- Estado da Camada de Visualização -----
        self._entrada: Path | None = None
        self._modo_dev = False

        # ----- Módulo de Execução Profundo (Engine) -----
        self._engine = PipelineEngine(modo_dev=self._modo_dev)
        self._engine.subscribe(self._on_engine_event)

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

        # Botão "Cancelar" fica à direita do "Enviar"
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
        header_log = ctk.CTkFrame(self, fg_color="transparent")
        header_log.pack(fill="x", padx=20, pady=(10, 2))

        ctk.CTkLabel(
            header_log,
            text="Log de execução: ",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left")

        self._log_dev_button = ctk.CTkLabel(
            header_log,
            text="Log User",
            text_color="#3498db",
            font=ctk.CTkFont(size=12, underline=True),
            cursor="hand2",
        )
        self._log_dev_button.pack(side="left")
        self._log_dev_button.bind("<Button-1>", self._on_log_dev_button)

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

        self._btn_fechamento = ctk.CTkButton(
            footer,
            text="Fechamento Mensal",
            width=140,
            fg_color="#D17004",
            hover_color="#B5650D",
            command=self._on_fechamento_mensal,
        )
        self._btn_fechamento.pack(side="right")

    # ----------------------------------------------------------------
    # Handlers dos botões e ações de usuário
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
            return
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
            return
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
        """Dispara o pipeline na Engine e ajusta o estado dos controles."""
        if self._entrada is None or self._engine.is_running:
            return

        # Limpa controles visuais para a nova rodada
        self._limpar_log_visual()
        self._progress.stop()
        self._progress.configure(mode="determinate")
        self._progress.set(0)
        self._progress_label.configure(text="")
        self._set_status("Processando ...", cor=_COR_NEUTRO)

        self._btn_enviar.configure(state="disabled")
        self._btn_fechamento.configure(state="disabled")
        self._btn_cancelar.configure(
            state="normal",
            text="Cancelar",
            fg_color="#c0392b",       # vermelho enquanto ativo
            hover_color="#e74c3c",
        )

        self._engine.start(self._entrada)

    def _on_cancelar(self) -> None:
        """Solicita cancelamento imediato à Engine."""
        if not self._engine.is_running:
            return

        self._btn_cancelar.configure(
            state="disabled",
            text="Cancelando...",
            fg_color="#7f8c8d",
            hover_color="#95a5a6",
        )
        self._set_status(
            "Cancelamento solicitado — interrompendo processamento atual ...",
            cor=_COR_NEUTRO,
        )

        self._engine.cancel()

    def _on_log_dev_button(self, _event=None) -> None:  # noqa: ARG002
        """Alterna a exibição entre Log de Usuário e Log de Desenvolvedor."""
        self._modo_dev = not self._modo_dev
        self._engine.set_dev_mode(self._modo_dev)

        self._log_dev_button.configure(
            text="Log Dev" if self._modo_dev else "Log User",
            text_color="#e67e22" if self._modo_dev else "#3498db",
        )

        # Redesenha todo o log formatado diretamente pela Engine
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        for linha, _ in self._engine.get_formatted_logs():
            self._log.insert("end-1c", f"{linha}\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _on_fechamento_mensal(self) -> None:
        """Abre o modal para configuração e execução do Fechamento Mensal."""
        if self._engine.is_running:
            self._set_status("Aguarde a operação atual finalizar.", cor=_COR_ERRO)
            return

        ModalFechamentoMensal(self, on_confirm=self._iniciar_consolidacao_macro)

    def _iniciar_consolidacao_macro(self, ano: int, mes: int, forcar: bool) -> None:
        """Dispara a consolidação mensal via Engine."""
        self._limpar_log_visual()
        self._btn_enviar.configure(state="disabled")
        self._btn_fechamento.configure(state="disabled")
        self._btn_cancelar.configure(
            state="normal",
            text="Cancelar",
            fg_color=_COR_CANCELAR,
            hover_color=_COR_CANCELAR_HOVER,
        )

        self._set_status(f"Consolidando ciclo {mes:02d}/{ano} ...", cor="#e67e22")
        self._progress.configure(mode="indeterminate")
        self._progress.start()
        self._progress_label.configure(text="Iniciando consolidação...")

        self._engine.start_fechamento_mensal(ano=ano, mes=mes, forcar=forcar)

    # ----------------------------------------------------------------
    # Recepção e Despacho de Eventos da Engine
    # ----------------------------------------------------------------

    def _on_engine_event(self, event: EngineEvent) -> None:
        """Recebe eventos da Engine e os despacha thread-safe na mainloop do Tk."""
        self.after_idle(self._dispatch_event, event)

    def _dispatch_event(self, event: EngineEvent) -> None:
        """Distribui o evento para o handler visual específico."""
        if isinstance(event, ProgressUpdateEvent):
            self._handle_progress(event)
        elif isinstance(event, LogMessageEvent):
            self._handle_log_message(event)
        elif isinstance(event, ExecutionFinishedEvent):
            self._handle_finished(event)

    def _handle_progress(self, event: ProgressUpdateEvent) -> None:
        """Atualiza a barra e o rótulo de progresso com dados normalizados."""
        if event.is_indeterminate:
            if self._progress.cget("mode") != "indeterminate":
                self._progress.configure(mode="indeterminate")
                self._progress.start()
            self._progress_label.configure(text=event.label)
            return

        if self._progress.cget("mode") != "determinate":
            self._progress.stop()
            self._progress.configure(mode="determinate")

        self._progress.set(event.fraction)
        self._progress_label.configure(text=event.label)

    def _handle_log_message(self, event: LogMessageEvent) -> None:
        """Insere uma linha de log na caixa de texto visual."""
        if event.dev_only and not self._modo_dev:
            return

        self._log.configure(state="normal")
        self._log.insert("end-1c", f"{event.text}\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _handle_finished(self, event: ExecutionFinishedEvent) -> None:
        """Atualiza o estado dos controles ao finalizar a execução."""
        self._progress.stop()

        if event.was_cancelled:
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

        # Reseta botão Cancelar para o estado idle (cinza, disabled)
        self._btn_cancelar.configure(
            state="disabled",
            text="Cancelar",
            fg_color="#7f8c8d",
            hover_color="#95a5a6",
        )

        # Reabilita botão Fechamento e Enviar (se aplicável)
        self._btn_fechamento.configure(state="normal")
        if self._entrada is not None:
            try:
                get_database_url()
                self._btn_enviar.configure(state="normal")
            except KeyError:
                self._btn_enviar.configure(state="disabled")

    # ----------------------------------------------------------------
    # Utilitários de Interface
    # ----------------------------------------------------------------

    def _limpar_log_visual(self) -> None:
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

    def _set_status(self, texto: str, cor: str) -> None:
        self._status.configure(text=texto, text_color=cor)

    def destroy(self) -> None:
        """Garante encerramento seguro ao fechar a janela."""
        if self._engine.is_running:
            self._engine.cancel()
        super().destroy()
