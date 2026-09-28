# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine.engine import PipelineEngine
from app.engine.events import (
    ExecutionFinishedEvent,
    ExecutionState,
    LogMessageEvent,
    ProgressUpdateEvent,
)


class TestPipelineEngine(unittest.TestCase):

    def setUp(self):
        self.engine = PipelineEngine(modo_dev=False)

    def test_initial_state(self):
        self.assertFalse(self.engine.is_running)
        self.assertEqual(self.engine.state, ExecutionState.IDLE)
        self.assertFalse(self.engine.modo_dev)

    def test_dev_mode_toggle(self):
        self.engine.set_dev_mode(True)
        self.assertTrue(self.engine.modo_dev)
        self.engine.set_dev_mode(False)
        self.assertFalse(self.engine.modo_dev)

    def test_subscribe_and_events(self):
        received_events = []
        listener = lambda ev: received_events.append(ev)

        self.engine.subscribe(listener)

        # Simula entrega de progresso
        self.engine._handle_runner_progress(
            done=5, total=10, phase="copying", message="Copiando 5/10", path="audio.wav"
        )
        self.assertTrue(any(isinstance(e, ProgressUpdateEvent) for e in received_events))

        # Simula entrega de log
        self.engine._handle_runner_log("Linha de teste", "out", False, None)
        self.assertTrue(any(isinstance(e, LogMessageEvent) and e.text == "Linha de teste" for e in received_events))

        # Simula término
        self.engine._handle_runner_finished(0, "Sucesso", None, False)
        self.assertTrue(any(isinstance(e, ExecutionFinishedEvent) and e.exit_code == 0 for e in received_events))

        self.engine.unsubscribe(listener)

    @patch("app.engine.engine.PipelineRunner")
    def test_start_and_cancel_lifecycle(self, mock_runner_cls):
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner

        fake_path = Path("fake_path")
        self.engine.start(fake_path)

        self.assertTrue(self.engine.is_running)
        self.assertEqual(self.engine.state, ExecutionState.RUNNING)

        # Tentar iniciar novamente enquanto rodando deve falhar
        with self.assertRaises(RuntimeError):
            self.engine.start(fake_path)

        # Cancelar
        self.engine.cancel()
        self.assertEqual(self.engine.state, ExecutionState.CANCELLING)


if __name__ == "__main__":
    unittest.main()
