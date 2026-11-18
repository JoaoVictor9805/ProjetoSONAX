# -*- coding: utf-8 -*-
"""Testes para os modos de execução do PipelineRunner e View no Modo Teste."""
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.engine.runner import PipelineRunner
from app.services.audio_inspector import AudioMetadata
from app.view.app import _MODOS_EXECUCAO


class TestRunnerModos(unittest.TestCase):

    def setUp(self):
        self.cancel_event = threading.Event()
        self.dev_mode_event = threading.Event()
        self.log_calls: list[tuple] = []
        self.progress_calls: list[tuple] = []
        self.finished_calls: list[tuple] = []

    def on_progress(self, done, total, phase, message, path):
        self.progress_calls.append((done, total, phase, message, path))

    def on_log(self, line, stream, dev_only, path):
        self.log_calls.append((line, stream, dev_only, path))

    def on_finished(self, exit_code, summary, error, was_cancelled):
        self.finished_calls.append((exit_code, summary, error, was_cancelled))

    @patch("app.engine.runner.salvar_transcricoes_planilha")
    @patch("app.engine.runner.deletar_pasta")
    @patch("app.engine.runner.copiar_lote_trabalho")
    @patch("app.engine.runner.AudioInspector")
    @patch("app.engine.runner.coletar_audios")
    def test_modo_completo_transcreve_diariza_e_salva_planilha(
        self, mock_coletar, mock_inspector_cls, mock_copiar, mock_deletar, mock_salvar_planilha
    ):
        p1 = Path("qualquer titulo de ligacao.mp3")
        meta1 = AudioMetadata(path=p1, duracao=35.0)  # < 90s também é aceito no modoTeste!
        mock_coletar.return_value = [p1]
        mock_copiar.return_value = [p1]
        mock_salvar_planilha.return_value = Path("transcricoes_modo_teste.xlsx")

        mock_inspector = MagicMock()
        mock_inspecao = MagicMock()
        mock_inspecao.longos = []
        mock_inspecao.curtos = [meta1]
        mock_inspecao.invalidos = []
        mock_inspector.classificar_lote.return_value = mock_inspecao
        mock_inspector_cls.return_value = mock_inspector

        runner = PipelineRunner(
            entrada=p1,
            cancel_event=self.cancel_event,
            dev_mode_event=self.dev_mode_event,
            on_progress=self.on_progress,
            on_log=self.on_log,
            on_finished=self.on_finished,
            modo_etapa="completo",
        )

        runner.ingestor = MagicMock()
        mock_item = MagicMock()
        mock_item.sucesso = True
        mock_item.texto_transcricao = "transcricao ok"
        mock_item.duracao_segundos = 35.0
        mock_item.qualidade_resumo = "Bom (85/100)"
        runner.ingestor.transcrever_sem_banco.return_value = mock_item
        runner.ingestor.revisar_sem_banco.return_value = {
            "revisao": "Agente (Falavinha): Olá\nCliente: Oi",
            "empresa": "Empresa X",
            "fonte_dados": "Interlocutor / Agente",
            "fallback_bruto": False,
        }

        runner.run()

        runner.ingestor.transcrever_sem_banco.assert_called_once()
        runner.ingestor.revisar_sem_banco.assert_called_once()
        # Nunca chama métodos de banco ou análise comercial
        runner.ingestor.transcrever_e_inserir.assert_not_called()
        runner.ingestor.analisar_chamada.assert_not_called()

        mock_salvar_planilha.assert_called_once()
        registros_salvos = mock_salvar_planilha.call_args[0][0]
        self.assertEqual(len(registros_salvos), 1)
        self.assertEqual(registros_salvos[0]["arquivo"], "qualquer titulo de ligacao.mp3")
        self.assertEqual(registros_salvos[0]["transcricao_bruta"], "transcricao ok")
        self.assertEqual(registros_salvos[0]["transcricao_diarizada"], "Agente (Falavinha): Olá\nCliente: Oi")
        self.assertEqual(registros_salvos[0]["status"], "Sucesso")

        self.assertEqual(len(self.finished_calls), 1)
        exit_code, summary, _, was_cancelled = self.finished_calls[0]
        self.assertEqual(exit_code, 0)
        self.assertFalse(was_cancelled)
        self.assertIn("transcricoes_modo_teste.xlsx", summary)

    @patch("app.engine.runner.salvar_transcricoes_planilha")
    @patch("app.engine.runner.deletar_pasta")
    @patch("app.engine.runner.copiar_lote_trabalho")
    @patch("app.engine.runner.AudioInspector")
    @patch("app.engine.runner.coletar_audios")
    def test_modo_apenas_transcricao_pula_diarizacao_e_salva_planilha(
        self, mock_coletar, mock_inspector_cls, mock_copiar, mock_deletar, mock_salvar_planilha
    ):
        p1 = Path("audio_teste_livre.wav")
        meta1 = AudioMetadata(path=p1, duracao=45.0)
        mock_coletar.return_value = [p1]
        mock_copiar.return_value = [p1]
        mock_salvar_planilha.return_value = Path("transcricoes_modo_teste.xlsx")

        mock_inspector = MagicMock()
        mock_inspecao = MagicMock()
        mock_inspecao.longos = []
        mock_inspecao.curtos = [meta1]
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
            modo_etapa="transcricao",
        )

        runner.ingestor = MagicMock()
        mock_item = MagicMock()
        mock_item.sucesso = True
        mock_item.texto_transcricao = "transcricao ok"
        mock_item.duracao_segundos = 45.0
        mock_item.qualidade_resumo = "Excelente (95/100)"
        runner.ingestor.transcrever_sem_banco.return_value = mock_item

        runner.run()

        runner.ingestor.transcrever_sem_banco.assert_called_once()
        runner.ingestor.revisar_sem_banco.assert_not_called()
        runner.ingestor.analisar_chamada.assert_not_called()
        mock_salvar_planilha.assert_called_once()

        registros_salvos = mock_salvar_planilha.call_args[0][0]
        self.assertEqual(registros_salvos[0]["status"], "Apenas Transcrição")

        exit_code, _, _, was_cancelled = self.finished_calls[0]
        self.assertEqual(exit_code, 0)
        self.assertFalse(was_cancelled)

    def test_modos_execucao_ui(self):
        modos = [m for _, m in _MODOS_EXECUCAO]
        self.assertEqual(modos, ["completo", "transcricao"])

    @patch("app.engine.runner.salvar_transcricoes_planilha")
    @patch("app.engine.runner.deletar_pasta")
    @patch("app.engine.runner.copiar_lote_trabalho")
    @patch("app.engine.runner.AudioInspector")
    @patch("app.engine.runner.coletar_audios")
    def test_transcricao_sub_progress_marcos(
        self, mock_coletar, mock_inspector_cls, mock_copiar, mock_deletar, mock_salvar_planilha
    ):
        """Valida que _on_sub_progress emite mensagens apenas nos marcos de 25%, 50% e 75%."""
        p1 = Path("qualquer_audio.wav")
        meta1 = AudioMetadata(path=p1, duracao=100.0)
        mock_coletar.return_value = [p1]
        mock_copiar.return_value = [p1]
        mock_salvar_planilha.return_value = Path("transcricoes_modo_teste.xlsx")

        mock_inspector = MagicMock()
        mock_inspecao = MagicMock()
        mock_inspecao.longos = [meta1]
        mock_inspecao.curtos = []
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
            modo_etapa="transcricao",
        )
        runner.ingestor = MagicMock()
        mock_item = MagicMock()
        mock_item.sucesso = True
        mock_item.texto_transcricao = "transcricao ok"
        mock_item.duracao_segundos = 100.0
        mock_item.qualidade_resumo = "Bom (85/100)"

        def fake_transcrever(*args, **kwargs):
            cb = kwargs.get("on_sub_progress")
            if cb:
                cb(0.05, "prep")
                cb(0.15, "init")
                cb(0.26, "seg1")
                cb(0.35, "seg2")
                cb(0.52, "seg3")
                cb(0.70, "seg4")
                cb(0.78, "seg5")
                cb(0.95, "seg6")
            return mock_item

        runner.ingestor.transcrever_sem_banco.side_effect = fake_transcrever

        runner.run()

        chamadas_sub = [
            c for c in self.progress_calls
            if c[2] == "transcribing" and c[4] == p1.name
        ]
        self.assertEqual(len(chamadas_sub), 10)

        msgs_sub = [c[3] for c in chamadas_sub[1:-1]]
        self.assertEqual(len(msgs_sub), 8)

        msgs_com_conteudo = [m for m in msgs_sub if m is not None]
        self.assertEqual(len(msgs_com_conteudo), 3)
        self.assertTrue(any("25% concluído" in m for m in msgs_com_conteudo))
        self.assertTrue(any("50% concluído" in m for m in msgs_com_conteudo))
        self.assertTrue(any("75% concluído" in m for m in msgs_com_conteudo))

        msgs_silenciosas = [m for m in msgs_sub if m is None]
        self.assertEqual(len(msgs_silenciosas), 5)


if __name__ == "__main__":
    unittest.main()
