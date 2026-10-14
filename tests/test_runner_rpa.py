# -*- coding: utf-8 -*-
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine.runner import PipelineRunner


class TestRunnerRpaSkip(unittest.TestCase):

    def setUp(self):
        self.cancel_event = threading.Event()
        self.dev_mode_event = threading.Event()
        self.progress_calls = []
        self.log_calls = []
        self.finished_calls = []

        def on_progress(done, total, phase, msg, path):
            self.progress_calls.append((done, total, phase, msg, path))

        def on_log(text, stream, dev_only, path):
            self.log_calls.append((text, stream, dev_only, path))

        def on_finished(exit_code, msg, err, cancelled):
            self.finished_calls.append((exit_code, msg, err, cancelled))

        self.on_progress = on_progress
        self.on_log = on_log
        self.on_finished = on_finished

    @patch("app.engine.runner.coletar_wavs")
    @patch("app.engine.runner.copiar_lote_trabalho")
    @patch("app.engine.runner.AudioInspector")
    @patch("app.engine.runner.deletar_pasta")
    @patch("app.services.rpa_google.coletar_textos_google_lote")
    def test_pula_rpa_quando_revisao_ja_esta_no_banco(
        self,
        mock_coletar_rpa,
        mock_deletar,
        mock_inspector_cls,
        mock_copiar,
        mock_coletar_wavs,
    ):
        p1 = Path("temp/call_123456_ramal_101.wav")
        mock_coletar_wavs.return_value = [p1]
        mock_copiar.return_value = [p1]

        mock_inspector = MagicMock()
        mock_inspecao = MagicMock()
        mock_inspecao.longos = [p1]
        mock_inspecao.curtos = []
        mock_inspecao.invalidos = []
        mock_inspector.classificar_lote.return_value = mock_inspecao
        mock_inspector.filtrar_qualidade_acustica.return_value = ([p1], [])
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
        mock_item_res = MagicMock()
        mock_item_res.sucesso = True
        mock_item_res.ja_existente = False
        mock_item_res.texto_transcricao = "transcricao ok"
        mock_item_res.agente_nome = "Carlos"
        mock_item_res.numero = "33101010"
        mock_item_res.estado_ddd = "41"
        mock_item_res.identificacao_cliente = None
        runner.ingestor.transcrever_e_inserir.return_value = mock_item_res

        # Simula que a ligação JÁ POSSUI revisão no banco
        runner.ingestor.verificar_revisoes_existentes.return_value = {p1.name}

        runner.run()

        # O robô RPA NÃO deve ter sido acionado!
        mock_coletar_rpa.assert_not_called()

        # Deve haver log informando que a revisão já está no banco e etapa RPA pulada
        textos_log = [c[0] for c in self.log_calls]
        self.assertTrue(
            any("Etapa de coleta RPA no Google pulada" in t for t in textos_log),
            f"Log esperado de pulo do RPA não encontrado em: {textos_log}",
        )

        # A revisão também deve ter sido pulada
        runner.ingestor.revisar_transcricao.assert_not_called()

        # A análise pode rodar normalmente
        runner.ingestor.analisar_chamada.assert_called_once()

    @patch("app.engine.runner.coletar_wavs")
    @patch("app.engine.runner.copiar_lote_trabalho")
    @patch("app.engine.runner.AudioInspector")
    @patch("app.engine.runner.deletar_pasta")
    @patch("app.services.rpa_google.coletar_textos_google_lote")
    def test_aciona_rpa_apenas_para_chamadas_sem_revisao(
        self,
        mock_coletar_rpa,
        mock_deletar,
        mock_inspector_cls,
        mock_copiar,
        mock_coletar_wavs,
    ):
        p1 = Path("temp/call_111111_ramal_101.wav")
        p2 = Path("temp/call_222222_ramal_102.wav")
        mock_coletar_wavs.return_value = [p1, p2]
        mock_copiar.return_value = [p1, p2]

        mock_inspector = MagicMock()
        mock_inspecao = MagicMock()
        mock_inspecao.longos = [p1, p2]
        mock_inspecao.curtos = []
        mock_inspecao.invalidos = []
        mock_inspector.classificar_lote.return_value = mock_inspecao
        mock_inspector.filtrar_qualidade_acustica.return_value = ([p1, p2], [])
        mock_inspector_cls.return_value = mock_inspector

        mock_coletar_rpa.return_value = {p2.name: "Texto Google"}

        runner = PipelineRunner(
            entrada=Path("entrada_fake"),
            cancel_event=self.cancel_event,
            dev_mode_event=self.dev_mode_event,
            on_progress=self.on_progress,
            on_log=self.on_log,
            on_finished=self.on_finished,
        )

        runner.ingestor = MagicMock()
        def mock_transcrever(caminho, **kwargs):
            res = MagicMock()
            res.sucesso = True
            res.ja_existente = False
            res.texto_transcricao = "texto"
            res.agente_nome = "Agente"
            res.numero = "33101010" if "111111" in caminho.name else "33202020"
            res.estado_ddd = "41"
            res.identificacao_cliente = None
            return res

        runner.ingestor.transcrever_e_inserir.side_effect = mock_transcrever

        # p1 já possui revisão, p2 NÃO possui
        runner.ingestor.verificar_revisoes_existentes.return_value = {p1.name}

        runner.run()

        # O robô RPA deve ter sido acionado SOMENTE com o telefone de p2
        mock_coletar_rpa.assert_called_once()
        args, kwargs = mock_coletar_rpa.call_args
        mapa_telefones_consultados = args[0]
        self.assertNotIn(p1.name, mapa_telefones_consultados)
        self.assertIn(p2.name, mapa_telefones_consultados)

        # p1 pula revisar_transcricao, p2 executa
        runner.ingestor.revisar_transcricao.assert_called_once()
        self.assertEqual(runner.ingestor.revisar_transcricao.call_args[0][0], p2.name)


if __name__ == "__main__":
    unittest.main()
