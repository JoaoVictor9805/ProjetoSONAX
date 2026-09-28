# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine.events import (
    ExecutionFinishedEvent,
    LogMessageEvent,
    ProgressUpdateEvent,
)
from app.view.app import App


class TestAppGui(unittest.TestCase):

    def setUp(self):
        # Instancia sem inicializar a janela nativa do Tkinter
        self.app = App.__new__(App)
        self.app._modo_dev = False
        self.app._progress = MagicMock()
        self.app._progress_label = MagicMock()
        self.app._log = MagicMock()
        self.app._status = MagicMock()
        self.app._btn_cancelar = MagicMock()
        self.app._btn_enviar = MagicMock()
        self.app._btn_fechamento = MagicMock()
        self.app._entrada = None

    def test_handle_progress_determinate(self):
        self.app._progress.cget.return_value = "determinate"
        ev_prog = ProgressUpdateEvent(fraction=0.45, label="45% copiando", phase="copying")
        self.app._handle_progress(ev_prog)
        self.app._progress.set.assert_called_with(0.45)
        self.app._progress_label.configure.assert_called_with(text="45% copiando")

    def test_handle_progress_indeterminate(self):
        self.app._progress.cget.return_value = "determinate"
        ev_prog = ProgressUpdateEvent(fraction=0.0, label="Consolidando...", phase="closing", is_indeterminate=True)
        self.app._handle_progress(ev_prog)
        self.app._progress.configure.assert_called_with(mode="indeterminate")
        self.app._progress.start.assert_called_once()
        self.app._progress_label.configure.assert_called_with(text="Consolidando...")

    def test_handle_log_message_user_mode(self):
        ev_log_user = LogMessageEvent(text="Arquivo copiado", stream="out", dev_only=False)
        self.app._handle_log_message(ev_log_user)
        self.app._log.insert.assert_called_with("end-1c", "Arquivo copiado\n")

        self.app._log.reset_mock()
        ev_log_dev = LogMessageEvent(text="Detalhe interno", stream="err", dev_only=True)
        self.app._handle_log_message(ev_log_dev)
        self.app._log.insert.assert_not_called()

    def test_handle_finished_success(self):
        ev_done = ExecutionFinishedEvent(exit_code=0, summary="Processado com sucesso", error=None)
        self.app._handle_finished(ev_done)
        self.app._progress.set.assert_called_with(1.0)
        self.app._status.configure.assert_called_with(text="Processado com sucesso", text_color="#2ecc71")
        self.app._btn_cancelar.configure.assert_called()


if __name__ == "__main__":
    unittest.main()
