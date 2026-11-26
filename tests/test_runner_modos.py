# -*- coding: utf-8 -*-
"""Testes para os modos de execução de etapas do PipelineRunner e View."""
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.engine.runner import PipelineRunner
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

    @patch("app.engine.runner.deletar_pasta")
    @patch("app.engine.runner.resolver_destino")
    @patch("app.engine.runner.copiar_lote_trabalho")
    @patch("app.engine.runner.AudioInspector")
    @patch("app.engine.runner.coletar_wavs")
    @patch("app.engine.runner.get_database_url")
    def test_modo_apenas_transcricao(
        self, mock_env, mock_coletar, mock_inspector_cls, mock_copiar, mock_resolver, mock_deletar
    ):
        p1 = Path("1001-2026-09-28-10-00-00.wav")
        mock_coletar.return_value = [p1]
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
            modo_etapa="transcricao",
        )

        runner.ingestor = MagicMock()
        mock_item = MagicMock()
        mock_item.sucesso = True
        mock_item.ja_existente = False
        mock_item.texto_transcricao = "transcricao ok"
        mock_item.agente_nome = "Ana"
        mock_item.numero = "33101010"
        mock_item.estado_ddd = "41"
        mock_item.identificacao_cliente = None
        runner.ingestor.transcrever_e_inserir.return_value = mock_item
        runner.ingestor.verificar_transcricoes_existentes.return_value = set()

        runner.run()

        # Transcrição foi chamada
        runner.ingestor.transcrever_e_inserir.assert_called_once()
        # RPA, Revisão e Análise NÃO devem ser chamados no modo transcricao
        runner.ingestor.revisar_transcricao.assert_not_called()
        runner.ingestor.analisar_chamada.assert_not_called()

        self.assertEqual(len(self.finished_calls), 1)
        exit_code, summary, _, was_cancelled = self.finished_calls[0]
        self.assertEqual(exit_code, 0)
        self.assertFalse(was_cancelled)
        self.assertIn("Transcrição concluída", summary)

    @patch("app.engine.runner.deletar_pasta")
    @patch("app.engine.runner.resolver_destino")
    @patch("app.engine.runner.copiar_lote_trabalho")
    @patch("app.engine.runner.AudioInspector")
    @patch("app.engine.runner.coletar_wavs")
    @patch("app.engine.runner.get_database_url")
    def test_modo_analise_com_revisao_existente_pula_etapas_anteriores(
        self, mock_env, mock_coletar, mock_inspector_cls, mock_copiar, mock_resolver, mock_deletar
    ):
        p1 = Path("1001-2026-09-28-10-00-00.wav")
        mock_coletar.return_value = [p1]
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
            modo_etapa="analise",
        )

        runner.ingestor = MagicMock()
        # Simula que o áudio já possui revisão (mesmo que texto bruto)
        runner.ingestor.verificar_revisoes_existentes.return_value = {p1.name}

        runner.run()

        # Como já possui revisão, transcrição e revisão devem ter sido puladas
        runner.ingestor.transcrever_e_inserir.assert_not_called()
        runner.ingestor.revisar_transcricao.assert_not_called()

        # Análise comercial DEVE ser chamada com permitir_texto_bruto=True
        runner.ingestor.analisar_chamada.assert_called_once_with(
            p1.name,
            rotulo_audio="Audio 01",
            cancel=self.cancel_event,
            permitir_texto_bruto=True,
        )

        self.assertEqual(len(self.finished_calls), 1)
        exit_code, summary, _, was_cancelled = self.finished_calls[0]
        self.assertEqual(exit_code, 0)
        self.assertFalse(was_cancelled)
        self.assertIn("Análise comercial finalizada", summary)

    @patch("app.engine.runner.deletar_pasta")
    @patch("app.engine.runner.resolver_destino")
    @patch("app.engine.runner.copiar_lote_trabalho")
    @patch("app.engine.runner.AudioInspector")
    @patch("app.engine.runner.coletar_wavs")
    @patch("app.engine.runner.get_database_url")
    def test_modo_revisao_pula_sem_transcricao_e_revisa_aptos(
        self, mock_env, mock_coletar, mock_inspector_cls, mock_copiar, mock_resolver, mock_deletar
    ):
        p1 = Path("audio1.wav")
        p2 = Path("audio2.wav")
        mock_coletar.return_value = [p1, p2]

        runner = PipelineRunner(
            entrada=Path("entrada_fake"),
            cancel_event=self.cancel_event,
            dev_mode_event=self.dev_mode_event,
            on_progress=self.on_progress,
            on_log=self.on_log,
            on_finished=self.on_finished,
            modo_etapa="revisao",
        )

        runner.ingestor = MagicMock()
        # p1 já tem transcrição, p2 não tem transcrição no banco (ex.: descartado)
        runner.ingestor.verificar_transcricoes_existentes.return_value = {p1.name}
        runner.ingestor.carregar_transcricoes_lote.return_value = {
            p1.name: {
                "texto_diarizado": "texto transcrito",
                "agente_nome": "Agente",
                "numero": "123",
                "estado_ddd": "41",
                "identificacao_cliente": None,
            }
        }

        # p1 não possui revisão válida (vazia ou texto bruto)
        runner.ingestor.verificar_revisoes_existentes.return_value = set()
        runner.ingestor.obter_cache_rpa.return_value = {}
        runner.ingestor.revisar_transcricao.return_value = {"id_empresa": 1, "empresa": "Emp"}

        with patch("app.services.rpa_google.obter_caminho_chrome_instalado", return_value=None):
            with patch("app.services.rpa_google.coletar_textos_google_lote", return_value={}):
                runner.run()

        # Atomicidade: transcrição NÃO deve ser executada no modo revisão
        runner.ingestor.transcrever_e_inserir.assert_not_called()
        runner.ingestor.carregar_transcricoes_lote.assert_called_once()
        runner.ingestor.revisar_transcricao.assert_called_once()
        runner.ingestor.analisar_chamada.assert_called_once_with(
            p1.name,
            rotulo_audio="Audio 01",
            cancel=self.cancel_event,
            permitir_texto_bruto=True,
        )

        # Log deve registrar que 1 áudio sem transcrição foi ignorado
        textos_log = [c[0] for c in self.log_calls]
        self.assertTrue(any("1 áudio(s) sem transcrição no banco ignorados" in t for t in textos_log))

    @patch("app.engine.runner.deletar_pasta")
    @patch("app.engine.runner.resolver_destino")
    @patch("app.engine.runner.copiar_lote_trabalho")
    @patch("app.engine.runner.AudioInspector")
    @patch("app.engine.runner.coletar_wavs")
    @patch("app.engine.runner.get_database_url")
    def test_modo_apenas_revisao(
        self, mock_env, mock_coletar, mock_inspector_cls, mock_copiar, mock_resolver, mock_deletar
    ):
        p1 = Path("audio1.wav")
        mock_coletar.return_value = [p1]

        runner = PipelineRunner(
            entrada=Path("entrada_fake"),
            cancel_event=self.cancel_event,
            dev_mode_event=self.dev_mode_event,
            on_progress=self.on_progress,
            on_log=self.on_log,
            on_finished=self.on_finished,
            modo_etapa="apenas_revisao",
        )

        runner.ingestor = MagicMock()
        runner.ingestor.verificar_transcricoes_existentes.return_value = {p1.name}
        runner.ingestor.carregar_transcricoes_lote.return_value = {
            p1.name: {
                "texto_diarizado": "texto",
                "agente_nome": "Agente",
                "numero": "123",
                "estado_ddd": "41",
                "identificacao_cliente": None,
            }
        }
        # Sem revisão válida no banco (apenas_validas=True retorna vazio)
        runner.ingestor.verificar_revisoes_existentes.return_value = set()
        runner.ingestor.obter_cache_rpa.return_value = {}
        runner.ingestor.revisar_transcricao.return_value = {"id_empresa": 1, "empresa": "Emp"}

        with patch("app.services.rpa_google.obter_caminho_chrome_instalado", return_value=None):
            with patch("app.services.rpa_google.coletar_textos_google_lote", return_value={}):
                runner.run()

        # Transcrição NÃO deve ser executada
        runner.ingestor.transcrever_e_inserir.assert_not_called()
        # Revisão executada
        runner.ingestor.revisar_transcricao.assert_called_once()
        # Análise comercial DEVE ter sido pulada no modo apenas_revisao
        runner.ingestor.analisar_chamada.assert_not_called()

        self.assertEqual(len(self.finished_calls), 1)
        exit_code, summary, _, was_cancelled = self.finished_calls[0]
        self.assertEqual(exit_code, 0)
        self.assertFalse(was_cancelled)
        self.assertIn("Revisão finalizada", summary)

    @patch("app.engine.runner.deletar_pasta")
    @patch("app.engine.runner.resolver_destino")
    @patch("app.engine.runner.copiar_lote_trabalho")
    @patch("app.engine.runner.AudioInspector")
    @patch("app.engine.runner.coletar_wavs")
    @patch("app.engine.runner.get_database_url")
    def test_modo_revisao_reanalisa_texto_bruto_e_pula_validas(
        self, mock_env, mock_coletar, mock_inspector_cls, mock_copiar, mock_resolver, mock_deletar
    ):
        p_bruto = Path("call_bruto.wav")
        p_valida = Path("call_valida.wav")
        mock_coletar.return_value = [p_bruto, p_valida]

        runner = PipelineRunner(
            entrada=Path("entrada_fake"),
            cancel_event=self.cancel_event,
            dev_mode_event=self.dev_mode_event,
            on_progress=self.on_progress,
            on_log=self.on_log,
            on_finished=self.on_finished,
            modo_etapa="apenas_revisao",
        )

        runner.ingestor = MagicMock()
        # Ambos têm transcrição
        runner.ingestor.verificar_transcricoes_existentes.return_value = {p_bruto.name, p_valida.name}
        runner.ingestor.carregar_transcricoes_lote.return_value = {
            p_bruto.name: {
                "texto_diarizado": "texto bruto existente",
                "agente_nome": "Carlos",
                "numero": "1199999999",
                "estado_ddd": "11",
                "identificacao_cliente": None,
            },
            p_valida.name: {
                "texto_diarizado": "texto valido",
                "agente_nome": "Carlos",
                "numero": "1199999999",
                "estado_ddd": "11",
                "identificacao_cliente": None,
            },
        }

        # apenas_validas=True retorna apenas p_valida (p_bruto é texto bruto/degradação graciosa)
        runner.ingestor.verificar_revisoes_existentes.return_value = {p_valida.name}
        runner.ingestor.obter_cache_rpa.return_value = {}
        runner.ingestor.revisar_transcricao.return_value = {"id_empresa": 10, "empresa": "Empresa Reanalisada"}

        with patch("app.services.rpa_google.obter_caminho_chrome_instalado", return_value=None):
            with patch("app.services.rpa_google.coletar_textos_google_lote", return_value={}):
                runner.run()

        # Transcrição NÃO deve ser executada
        runner.ingestor.transcrever_e_inserir.assert_not_called()
        runner.ingestor.revisar_transcricao.assert_called_once()
        args, kwargs = runner.ingestor.revisar_transcricao.call_args
        self.assertEqual(args[0], p_bruto.name)

        # Log informando que 1 áudio válido foi pulado
        textos_log = [c[0] for c in self.log_calls]
        self.assertTrue(any("1 de 2 chamada(s) já possuem revisão válida" in t for t in textos_log))

    @patch("app.engine.runner.deletar_pasta")
    @patch("app.engine.runner.resolver_destino")
    @patch("app.engine.runner.copiar_lote_trabalho")
    @patch("app.engine.runner.AudioInspector")
    @patch("app.engine.runner.coletar_wavs")
    @patch("app.engine.runner.get_database_url")
    def test_modo_analise_comercial_pula_analises_ja_existentes_em_lote(
        self, mock_env, mock_coletar, mock_inspector_cls, mock_copiar, mock_resolver, mock_deletar
    ):
        p_existente = Path("audio_existente.wav")
        p_pendente = Path("audio_pendente.wav")
        mock_coletar.return_value = [p_existente, p_pendente]

        runner = PipelineRunner(
            entrada=Path("entrada_fake"),
            cancel_event=self.cancel_event,
            dev_mode_event=self.dev_mode_event,
            on_progress=self.on_progress,
            on_log=self.on_log,
            on_finished=self.on_finished,
            modo_etapa="analise",
        )

        runner.ingestor = MagicMock()
        # Ambos possuem revisão válida no banco
        runner.ingestor.verificar_revisoes_existentes.return_value = {p_existente.name, p_pendente.name}
        runner.ingestor.verificar_transcricoes_existentes.return_value = {p_existente.name, p_pendente.name}
        # Apenas p_existente já tem análise gravada em avaliacao_ia
        runner.ingestor.verificar_analises_existentes.return_value = {p_existente.name}

        runner.run()

        # analisar_chamada deve ter sido chamado APENAS para p_pendente, pulando p_existente instantaneamente
        runner.ingestor.analisar_chamada.assert_called_once_with(
            p_pendente.name,
            rotulo_audio="Audio 02",
            cancel=self.cancel_event,
            permitir_texto_bruto=True,
        )

        # Log informativo de lote emitido
        textos_log = [c[0] for c in self.log_calls]
        self.assertTrue(any("1 de 2 chamada(s) já avaliadas no banco (puladas)" in t for t in textos_log))

    def test_modos_execucao_labels_sem_emojis_e_ordem_exata(self):
        """Valida que os rótulos do menu não possuem emojis e seguem exatamente a ordem solicitada."""
        rotulos = [r for r, _ in _MODOS_EXECUCAO]
        modos = [m for _, m in _MODOS_EXECUCAO]

        ordem_esperada_modos = [
            "completo",
            "completo_sem_rpa",
            "revisao",
            "revisao_sem_rpa",
            "transcricao",
            "apenas_revisao",
            "analise",
        ]
        self.assertEqual(modos, ordem_esperada_modos)

        # Não deve conter 'diarização' no nome da opção de revisão
        for r, m in _MODOS_EXECUCAO:
            if m in ("revisao", "revisao_sem_rpa"):
                self.assertIn("A partir da Revisão", r)
                self.assertNotIn("diarização", r.lower())

        # Não deve conter emojis nos textos do menu
        emojis = ["🚀", "🔄", "📊", "🎙", "📝", "⚡", "✨", "🔍"]
        for r in rotulos:
            for emoji in emojis:
                self.assertNotIn(emoji, r)

    @patch("app.engine.runner.deletar_pasta")
    @patch("app.engine.runner.resolver_destino")
    @patch("app.engine.runner.copiar_lote_trabalho")
    @patch("app.engine.runner.AudioInspector")
    @patch("app.engine.runner.coletar_wavs")
    @patch("app.engine.runner.get_database_url")
    def test_modo_completo_sem_rpa_pula_rpa_e_executa_pipeline(
        self, mock_env, mock_coletar, mock_inspector_cls, mock_copiar, mock_resolver, mock_deletar
    ):
        from app.services.revisao import MARCADOR_RPA_IGNORADO

        p1 = Path("1001-2026-09-28-10-00-00.wav")
        mock_coletar.return_value = [p1]
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
            modo_etapa="completo_sem_rpa",
        )

        runner.ingestor = MagicMock()
        mock_item = MagicMock()
        mock_item.sucesso = True
        mock_item.ja_existente = False
        mock_item.texto_transcricao = "transcricao ok"
        mock_item.agente_nome = "Ana"
        mock_item.numero = "33101010"
        mock_item.estado_ddd = "41"
        mock_item.identificacao_cliente = None
        runner.ingestor.transcrever_e_inserir.return_value = mock_item
        runner.ingestor.verificar_transcricoes_existentes.return_value = set()
        runner.ingestor.verificar_revisoes_existentes.return_value = set()
        runner.ingestor.verificar_analises_existentes.return_value = set()
        runner.ingestor.revisar_transcricao.return_value = {"id_empresa": 1, "empresa": "Não encontrado"}

        with patch("app.services.rpa_google.coletar_textos_google_lote") as mock_rpa:
            runner.run()

        # Transcrição, revisão e análise executam; RPA e cache RPA NÃO são chamados
        runner.ingestor.transcrever_e_inserir.assert_called_once()
        mock_rpa.assert_not_called()
        runner.ingestor.obter_cache_rpa.assert_not_called()
        runner.ingestor.revisar_transcricao.assert_called_once()
        _, kwargs_rev = runner.ingestor.revisar_transcricao.call_args
        self.assertEqual(kwargs_rev.get("texto_google"), MARCADOR_RPA_IGNORADO)
        self.assertEqual(kwargs_rev.get("telefone"), "33101010")
        runner.ingestor.analisar_chamada.assert_called_once()

        textos_log = [c[0] for c in self.log_calls]
        self.assertTrue(any("etapa de coleta RPA no Google pulada" in t for t in textos_log))

    @patch("app.engine.runner.deletar_pasta")
    @patch("app.engine.runner.resolver_destino")
    @patch("app.engine.runner.copiar_lote_trabalho")
    @patch("app.engine.runner.AudioInspector")
    @patch("app.engine.runner.coletar_wavs")
    @patch("app.engine.runner.get_database_url")
    def test_modo_revisao_sem_rpa_pula_transcricao_e_rpa(
        self, mock_env, mock_coletar, mock_inspector_cls, mock_copiar, mock_resolver, mock_deletar
    ):
        from app.services.revisao import MARCADOR_RPA_IGNORADO

        p1 = Path("audio1.wav")
        mock_coletar.return_value = [p1]

        runner = PipelineRunner(
            entrada=Path("entrada_fake"),
            cancel_event=self.cancel_event,
            dev_mode_event=self.dev_mode_event,
            on_progress=self.on_progress,
            on_log=self.on_log,
            on_finished=self.on_finished,
            modo_etapa="revisao_sem_rpa",
        )

        runner.ingestor = MagicMock()
        runner.ingestor.verificar_transcricoes_existentes.return_value = {p1.name}
        runner.ingestor.carregar_transcricoes_lote.return_value = {
            p1.name: {
                "texto_diarizado": "texto transcrito",
                "agente_nome": "Agente",
                "numero": "123",
                "estado_ddd": "41",
                "identificacao_cliente": None,
            }
        }
        runner.ingestor.verificar_revisoes_existentes.return_value = set()
        runner.ingestor.verificar_analises_existentes.return_value = set()
        runner.ingestor.revisar_transcricao.return_value = {"id_empresa": 1, "empresa": "Não encontrado"}

        with patch("app.services.rpa_google.coletar_textos_google_lote") as mock_rpa:
            runner.run()

        runner.ingestor.transcrever_e_inserir.assert_not_called()
        mock_rpa.assert_not_called()
        runner.ingestor.obter_cache_rpa.assert_not_called()
        runner.ingestor.revisar_transcricao.assert_called_once()
        _, kwargs_rev = runner.ingestor.revisar_transcricao.call_args
        self.assertEqual(kwargs_rev.get("texto_google"), MARCADOR_RPA_IGNORADO)
        runner.ingestor.analisar_chamada.assert_called_once()

        self.assertEqual(len(self.finished_calls), 1)
        exit_code, summary, _, was_cancelled = self.finished_calls[0]
        self.assertEqual(exit_code, 0)
        self.assertFalse(was_cancelled)
        self.assertIn("Revisão e análise finalizadas", summary)

    @patch("app.engine.runner.deletar_pasta")
    @patch("app.engine.runner.resolver_destino")
    @patch("app.engine.runner.copiar_lote_trabalho")
    @patch("app.engine.runner.AudioInspector")
    @patch("app.engine.runner.coletar_wavs")
    @patch("app.engine.runner.get_database_url")
    def test_transcricao_sub_progress_marcos(
        self, mock_env, mock_coletar, mock_inspector_cls, mock_copiar, mock_resolver, mock_deletar
    ):
        """Valida que _on_sub_progress emite mensagens apenas nos marcos de 25%, 50% e 75%."""
        p1 = Path("1001-2026-09-28-10-00-00.wav")
        mock_coletar.return_value = [p1]
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
            modo_etapa="transcricao",
        )
        runner.ingestor = MagicMock()
        mock_item = MagicMock()
        mock_item.sucesso = True
        mock_item.ja_existente = False
        mock_item.texto_transcricao = "transcricao ok"
        mock_item.agente_nome = "Ana"
        mock_item.numero = "33101010"
        mock_item.estado_ddd = "41"
        mock_item.identificacao_cliente = None

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

        runner.ingestor.transcrever_e_inserir.side_effect = fake_transcrever
        runner.ingestor.verificar_transcricoes_existentes.return_value = set()

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

    @patch("app.engine.runner.deletar_pasta")
    @patch("app.engine.runner.resolver_destino")
    @patch("app.engine.runner.copiar_lote_trabalho")
    @patch("app.engine.runner.AudioInspector")
    @patch("app.engine.runner.coletar_wavs")
    @patch("app.engine.runner.get_database_url")
    def test_modo_analise_nao_espera_cooldown_quando_chamada_pulada(
        self, mock_env, mock_coletar, mock_inspector_cls, mock_copiar, mock_resolver, mock_deletar
    ):
        p1 = Path("audio1.wav")
        p2 = Path("audio2.wav")
        mock_coletar.return_value = [p1, p2]

        cancel_mock = MagicMock()
        cancel_mock.is_set.return_value = False
        cancel_mock.wait.return_value = False

        runner = PipelineRunner(
            entrada=Path("entrada_fake"),
            cancel_event=cancel_mock,
            dev_mode_event=self.dev_mode_event,
            on_progress=self.on_progress,
            on_log=self.on_log,
            on_finished=self.on_finished,
            modo_etapa="analise",
        )
        runner.ingestor = MagicMock()
        runner.ingestor.verificar_transcricoes_existentes.return_value = {p1.name, p2.name}
        runner.ingestor.verificar_revisoes_existentes.return_value = {p1.name, p2.name}
        runner.ingestor.verificar_analises_existentes.return_value = set()
        # p1 retorna None (pulado), p2 retorna id_avaliacao (processado)
        runner.ingestor.analisar_chamada.side_effect = [None, 42]

        runner.run()

        cancel_mock.wait.assert_called_once_with(1.2)


if __name__ == "__main__":
    unittest.main()
