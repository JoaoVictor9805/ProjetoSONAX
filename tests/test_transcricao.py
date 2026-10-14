# -*- coding: utf-8 -*-
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.transcricao import (
    TranscricaoCancelada,
    TranscricaoErro,
    obter_modelo_whisper,
    transcrever_audio,
    transcrever_audio_faster_whisper,
)


class TestTranscricaoFasterWhisper(unittest.TestCase):

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        self.temp_file.write(
            b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x40\x1f\x00\x00\x80\x3e\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
        )
        self.temp_file.close()
        self.audio_path = Path(self.temp_file.name)

    def tearDown(self):
        self.audio_path.unlink(missing_ok=True)

    def test_arquivo_inexistente_lanca_filenotfound(self):
        with self.assertRaises(FileNotFoundError):
            transcrever_audio_faster_whisper(Path("caminho_inexistente_12345.wav"))

    def test_cancelamento_antes_do_inicio(self):
        cancel = threading.Event()
        cancel.set()

        with self.assertRaises(TranscricaoCancelada):
            transcrever_audio_faster_whisper(self.audio_path, cancel=cancel)

    def test_transcricao_sucesso_com_metricas_completas(self):
        mock_seg1 = MagicMock(
            text="Olá, bom dia!",
            avg_logprob=-0.2,
            compression_ratio=1.1,
            no_speech_prob=0.01,
            end=2.0,
        )
        mock_seg2 = MagicMock(
            text="Gostaria de falar com o responsável comercial.",
            avg_logprob=-0.1,
            compression_ratio=1.0,
            no_speech_prob=0.02,
            end=5.0,
        )
        mock_info = MagicMock(duration=5.0)

        mock_modelo = MagicMock()
        mock_modelo.transcribe.return_value = ([mock_seg1, mock_seg2], mock_info)

        progresso_itens = []

        def _on_progress(frac: float, msg: str):
            progresso_itens.append((frac, msg))

        res = transcrever_audio_faster_whisper(
            self.audio_path,
            modelo=mock_modelo,
            on_progress=_on_progress,
        )

        self.assertEqual(res["texto"], "Olá, bom dia! Gostaria de falar com o responsável comercial.")
        self.assertEqual(res["duracao_segundos"], 5.0)
        self.assertAlmostEqual(res["metricas"]["logprob_media"], -0.15, places=3)
        self.assertAlmostEqual(res["metricas"]["taxa_compressao_media"], 1.05, places=3)
        self.assertAlmostEqual(res["metricas"]["probabilidade_media_sem_fala"], 0.015, places=3)
        self.assertGreater(res["confidence"], 0.8)
        self.assertTrue(len(progresso_itens) > 0)
        self.assertEqual(progresso_itens[-1][0], 1.0)

    def test_cancelamento_durante_iteracao_segmentos(self):
        cancel = threading.Event()

        def gerador_segmentos():
            seg1 = MagicMock(
                text="Primeiro trecho",
                avg_logprob=-0.1,
                compression_ratio=1.0,
                no_speech_prob=0.0,
                end=1.5,
            )
            yield seg1
            cancel.set()
            seg2 = MagicMock(
                text="Segundo trecho",
                avg_logprob=-0.1,
                compression_ratio=1.0,
                no_speech_prob=0.0,
                end=3.0,
            )
            yield seg2

        mock_modelo = MagicMock()
        mock_modelo.transcribe.return_value = (gerador_segmentos(), MagicMock(duration=3.0))

        with self.assertRaises(TranscricaoCancelada):
            transcrever_audio_faster_whisper(
                self.audio_path,
                cancel=cancel,
                modelo=mock_modelo,
            )

    def test_erro_na_inferencia_lanca_transcricao_erro(self):
        mock_modelo = MagicMock()
        mock_modelo.transcribe.side_effect = RuntimeError("Falha interna de GPU/CUDA")

        with self.assertRaises(TranscricaoErro):
            transcrever_audio_faster_whisper(self.audio_path, modelo=mock_modelo)

    def test_roteamento_padrao_transcrever_audio(self):
        with patch("app.services.transcricao.transcrever_audio_faster_whisper") as mock_fw:
            mock_fw.return_value = {"texto": "teste"}
            res = transcrever_audio(self.audio_path)
            self.assertEqual(res["texto"], "teste")
            mock_fw.assert_called_once()


if __name__ == "__main__":
    unittest.main()
