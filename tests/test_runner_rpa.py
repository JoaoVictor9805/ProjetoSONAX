# -*- coding: utf-8 -*-
"""Garante que no Modo Teste o RPA Google, banco de dados e análise comercial não são acionados."""
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine.runner import PipelineRunner
from app.services.audio_inspector import AudioMetadata


class TestRunnerModoTesteSemRpaBanco(unittest.TestCase):

    def setUp(self):
        self.cancel_event = threading.Event()
        self.dev_mode_event = threading.Event()
        self.progress_calls = []
        self.log_calls = []
        self.finished_calls = []

        self.on_progress = lambda d, t, p, m, path: self.progress_calls.append((d, t, p, m, path))
        self.on_log = lambda text, stream, dev_only, path: self.log_calls.append((text, stream, dev_only, path))
        self.on_finished = lambda code, msg, err, cancelled: self.finished_calls.append((code, msg, err, cancelled))

    @patch("app.engine.runner.salvar_transcricoes_planilha")
    @patch("app.engine.runner.coletar_audios")
    @patch("app.engine.runner.copiar_lote_trabalho")
    @patch("app.engine.runner.AudioInspector")
    @patch("app.engine.runner.deletar_pasta")
    @patch("app.services.rpa_google.coletar_textos_google_lote")
    def test_nao_aciona_rpa_nem_banco_nem_analise(
        self,
        mock_coletar_rpa,
        mock_deletar,
        mock_inspector_cls,
        mock_copiar,
        mock_coletar_audios,
        mock_salvar_planilha,
    ):
        p1 = Path("reuniao_comercial_sem_id.wav")
        p2 = Path("chamada_aleatoria.m4a")
        mock_coletar_audios.return_value = [p1, p2]
        mock_copiar.return_value = [p1, p2]
        mock_salvar_planilha.return_value = Path("transcricoes_modo_teste.xlsx")

        mock_inspector = MagicMock()
        mock_inspecao = MagicMock()
        mock_inspecao.longos = [AudioMetadata(path=p1, duracao=120.0)]
        mock_inspecao.curtos = [AudioMetadata(path=p2, duracao=20.0)]
        mock_inspecao.invalidos = []
        mock_inspector.classificar_lote.return_value = mock_inspecao
        mock_inspector_cls.return_value = mock_inspector

        runner = PipelineRunner(
            entrada=Path("entrada_fake"),
            cancel_event=self.cancel_event,
            dev_mode_event=self.dev_mode_event,
            on_progress=self.on_progress,
            on_log=self.on_log,
            on_finished=self.on_finished,
        )

        runner.ingestor = MagicMock()
        runner.ingestor.transcrever_sem_banco.side_effect = [
            MagicMock(sucesso=True, texto_transcricao="texto 1", duracao_segundos=120.0, qualidade_resumo="Bom"),
            MagicMock(sucesso=True, texto_transcricao="texto 2", duracao_segundos=20.0, qualidade_resumo="Bom"),
        ]
        runner.ingestor.revisar_sem_banco.return_value = {
            "revisao": "Agente: Olá\nCliente: Oi",
            "empresa": "Não encontrado",
            "fonte_dados": "Interlocutor / Agente",
            "fallback_bruto": False,
        }

        runner.run()

        mock_coletar_rpa.assert_not_called()
        runner.ingestor.transcrever_e_inserir.assert_not_called()
        runner.ingestor.revisar_transcricao.assert_not_called()
        runner.ingestor.analisar_chamada.assert_not_called()
        self.assertEqual(runner.ingestor.transcrever_sem_banco.call_count, 2)
        self.assertEqual(runner.ingestor.revisar_sem_banco.call_count, 2)
        mock_salvar_planilha.assert_called_once()


if __name__ == "__main__":
    unittest.main()
