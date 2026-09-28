# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.ia import FakeProvedorIA
from app.services.ingestao import ChamadaIngestor
from app.services.transcricao import TranscricaoCancelada


class TestChamadaIngestor(unittest.TestCase):

    def setUp(self):
        self.fake_ia = FakeProvedorIA()
        self.ingestor = ChamadaIngestor(provedor_ia=self.fake_ia)

    @patch("app.services.ingestao.conectar")
    @patch("app.services.ingestao.registro_ja_existe")
    def test_transcrever_ja_existente(self, mock_ja_existe, mock_conectar):
        mock_conectar.return_value.__enter__.return_value = MagicMock()
        mock_ja_existe.return_value = True

        res = self.ingestor.transcrever_e_inserir(
            caminho=Path("0001-2026-09-28-10-00-00.wav"),
            rotulo_audio="Audio 01",
        )

        self.assertFalse(res.sucesso)
        self.assertTrue(res.ja_existente)
        self.assertEqual(len(self.fake_ia.chamadas_transcrever), 0)

    @patch("app.services.ingestao.conectar")
    @patch("app.services.ingestao.registro_ja_existe")
    @patch("app.services.ingestao.analisar_transcricao")
    @patch("app.services.ingestao.avaliar_qualidade_transcricao")
    @patch("app.services.ingestao.parse_nome_arquivo")
    @patch("app.services.ingestao.buscar_nome_atendente")
    @patch("app.services.ingestao.inserir_registro_chamada")
    def test_transcrever_e_inserir_sucesso(
        self,
        mock_inserir,
        mock_buscar_atendente,
        mock_parse_nome,
        mock_avaliar,
        mock_analisar,
        mock_ja_existe,
        mock_conectar,
    ):
        mock_conectar.return_value.__enter__.return_value = MagicMock()
        mock_ja_existe.return_value = False
        mock_analisar.return_value = {}
        mock_avaliar.return_value = {"classificacao": "Bom"}
        mock_parse_nome.return_value = {"ramal": "1001", "data": "28092026", "hora": "100000"}
        mock_buscar_atendente.return_value = "Carlos Silva"
        mock_inserir.return_value = 42

        res = self.ingestor.transcrever_e_inserir(
            caminho=Path("1001-2026-09-28-10-00-00.wav"),
            rotulo_audio="Audio 01",
        )

        self.assertTrue(res.sucesso)
        self.assertEqual(res.id_registro, 42)
        self.assertEqual(res.agente_nome, "Carlos Silva")
        self.assertEqual(res.texto_transcricao, self.fake_ia.transcricao_padrao["texto"])
        self.assertEqual(len(self.fake_ia.chamadas_transcrever), 1)

    @patch("app.services.ingestao.conectar")
    @patch("app.services.ingestao.registro_ja_existe")
    @patch("app.services.ingestao.analisar_transcricao")
    @patch("app.services.ingestao.avaliar_qualidade_transcricao")
    @patch("app.services.ingestao.parse_nome_arquivo")
    @patch("app.services.ingestao.buscar_nome_atendente")
    @patch("app.services.ingestao.inserir_registro_chamada")
    def test_transcrever_com_retry_sucesso_na_segunda_tentativa(
        self,
        mock_inserir,
        mock_buscar_atendente,
        mock_parse_nome,
        mock_avaliar,
        mock_analisar,
        mock_ja_existe,
        mock_conectar,
    ):
        mock_conectar.return_value.__enter__.return_value = MagicMock()
        mock_ja_existe.return_value = False
        mock_analisar.return_value = {}
        mock_avaliar.return_value = {"classificacao": "Bom"}
        mock_parse_nome.return_value = {"ramal": "1001", "data": "28092026", "hora": "100000"}
        mock_buscar_atendente.return_value = "Carlos Silva"
        mock_inserir.return_value = 99

        # Configura falha na primeira tentativa e sucesso na segunda
        fake_ia = FakeProvedorIA(falhas_antes_de_acerto=1)
        ingestor = ChamadaIngestor(provedor_ia=fake_ia)

        res = ingestor.transcrever_e_inserir(
            caminho=Path("1001-2026-09-28-10-00-00.wav"),
            rotulo_audio="Audio 01",
        )

        self.assertTrue(res.sucesso)
        self.assertEqual(len(fake_ia.chamadas_transcrever), 2)

    @patch("app.services.ingestao.conectar")
    @patch("app.services.ingestao.registro_ja_existe")
    def test_transcrever_falha_apos_tres_tentativas(self, mock_ja_existe, mock_conectar):
        mock_conectar.return_value.__enter__.return_value = MagicMock()
        mock_ja_existe.return_value = False

        # Configura 3 falhas seguidas
        fake_ia = FakeProvedorIA(falhas_antes_de_acerto=3)
        ingestor = ChamadaIngestor(provedor_ia=fake_ia)

        res = ingestor.transcrever_e_inserir(
            caminho=Path("1001-2026-09-28-10-00-00.wav"),
            rotulo_audio="Audio 01",
        )

        self.assertFalse(res.sucesso)
        self.assertEqual(len(fake_ia.chamadas_transcrever), 3)

    @patch("app.services.ingestao.conectar")
    @patch("app.services.ingestao.verificar_coluna_revisao")
    @patch("app.services.ingestao.inserir_revisao")
    def test_revisar_transcricao_sucesso(
        self, mock_inserir_rev, mock_verificar_rev, mock_conectar
    ):
        mock_conectar.return_value.__enter__.return_value = MagicMock()
        mock_verificar_rev.return_value = False
        mock_inserir_rev.return_value = "[Atendente]: Olá\n[Cliente]: Oi"

        res = self.ingestor.revisar_transcricao(
            log_arquivo="audio1.wav",
            texto_diarizado="Olá Oi",
            agente_nome="Carlos",
            rotulo_audio="Audio 01",
        )

        self.assertEqual(res, "[Atendente]: Olá\n[Cliente]: Oi")
        self.assertEqual(len(self.fake_ia.chamadas_revisar), 1)
        mock_inserir_rev.assert_called_once()

    @patch("app.services.ingestao.conectar")
    @patch("app.services.ingestao.verificar_coluna_revisao")
    @patch("app.services.ingestao.buscar_revisao")
    @patch("app.services.ingestao.verificar_tabela_analise")
    @patch("app.services.ingestao.inserir_analise")
    def test_analisar_chamada_sucesso(
        self,
        mock_inserir_analise,
        mock_verificar_analise,
        mock_buscar_rev,
        mock_verificar_rev,
        mock_conectar,
    ):
        mock_conectar.return_value.__enter__.return_value = MagicMock()
        mock_verificar_rev.return_value = True
        mock_buscar_rev.return_value = "[Atendente]: Bom dia"
        mock_verificar_analise.return_value = False
        mock_inserir_analise.return_value = 101

        res = self.ingestor.analisar_chamada(log_arquivo="audio1.wav", rotulo_audio="Audio 01")
        self.assertEqual(res, 101)
        self.assertEqual(len(self.fake_ia.chamadas_analisar), 1)
        mock_inserir_analise.assert_called_once()


if __name__ == "__main__":
    unittest.main()

