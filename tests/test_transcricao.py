# -*- coding: utf-8 -*-
"""Testes unitários para o serviço de transcrição via AssemblyAI."""

from __future__ import annotations

import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.transcricao import (
    ChaveAssemblyAINaoConfigurada,
    TranscricaoCancelada,
    TranscricaoErro,
    obter_api_key,
    transcrever_audio_assemblyai,
)


class TestTranscricaoAssemblyAI(unittest.TestCase):

    @patch("app.services.transcricao.os.getenv")
    def test_obter_api_key_sucesso(self, mock_getenv):
        mock_getenv.side_effect = lambda k, default=None: "chave-valida" if "ASSEMBLY" in k else None
        self.assertEqual(obter_api_key(), "chave-valida")

    @patch("app.services.transcricao.os.getenv")
    def test_obter_api_key_ausente(self, mock_getenv):
        mock_getenv.return_value = ""
        with self.assertRaises(ChaveAssemblyAINaoConfigurada):
            obter_api_key()

    def test_transcrever_arquivo_inexistente(self):
        with self.assertRaises(FileNotFoundError):
            transcrever_audio_assemblyai(Path("arquivo_que_nao_existe_12345.wav"))

    def test_transcrever_cancelado_pre_envio(self):
        cancel = threading.Event()
        cancel.set()
        caminho_dummy = Path(__file__)

        with self.assertRaises(TranscricaoCancelada):
            transcrever_audio_assemblyai(caminho_dummy, cancel=cancel)

    @patch("app.services.transcricao.obter_api_key", return_value="chave-mock")
    @patch("app.services.transcricao.aai")
    def test_transcrever_sucesso_somente_transcricao(self, mock_aai, mock_key):
        caminho_dummy = Path(__file__)

        mock_transcriber = MagicMock()
        mock_submit_init = MagicMock()
        mock_submit_init.id = "transcript-abc-123"
        mock_transcriber.submit.return_value = mock_submit_init
        mock_aai.Transcriber.return_value = mock_transcriber

        mock_status = MagicMock()
        mock_status.status = mock_aai.TranscriptStatus.completed
        mock_status.text = "Bom dia, aqui é da Falavinha Next."
        mock_status.audio_duration = 32.5
        mock_status.confidence = 0.96
        mock_aai.Transcript.get_by_id.return_value = mock_status

        progresso_mensagens = []

        def callback_progresso(frac, msg):
            progresso_mensagens.append((frac, msg))

        resultado = transcrever_audio_assemblyai(
            caminho_dummy,
            on_progress=callback_progresso,
            deletar_apos_transcricao=True,
        )

        self.assertIn("texto", resultado)
        self.assertEqual(resultado["texto"], "Bom dia, aqui é da Falavinha Next.")
        self.assertEqual(resultado["duracao_segundos"], 32.5)
        self.assertEqual(resultado["confidence"], 0.96)
        self.assertIn("logprob_media", resultado["metricas"])
        # Garante que SOMENTE transcreve (sem diarização de falantes na fase de transcrição)
        self.assertEqual(resultado["turnos"], [])
        self.assertEqual(resultado["speakers"], [])

        # Verifica chamada de exclusão do transcript na nuvem ao final
        mock_aai.Transcript.delete_by_id.assert_called_with("transcript-abc-123")
        self.assertTrue(len(progresso_mensagens) > 0)

    @patch("app.services.transcricao.obter_api_key", return_value="chave-mock")
    @patch("app.services.transcricao.aai")
    def test_transcrever_falha_assembly(self, mock_aai, mock_key):
        caminho_dummy = Path(__file__)

        mock_transcriber = MagicMock()
        mock_submit_init = MagicMock()
        mock_submit_init.id = "transcript-err-999"
        mock_transcriber.submit.return_value = mock_submit_init
        mock_aai.Transcriber.return_value = mock_transcriber

        mock_status = MagicMock()
        mock_status.status = mock_aai.TranscriptStatus.error
        mock_status.error = "Audio file corrupted"
        mock_aai.Transcript.get_by_id.return_value = mock_status

        with self.assertRaises(TranscricaoErro) as ctx:
            transcrever_audio_assemblyai(caminho_dummy)

        self.assertIn("Audio file corrupted", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
