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
    @patch("app.services.ingestao.buscar_transcricao")
    @patch("app.services.ingestao.buscar_chamada_valida")
    @patch("app.services.ingestao.registro_ja_existe")
    @patch("app.services.ingestao.parse_nome_arquivo")
    def test_transcrever_ja_existente(
        self, mock_parse_nome, mock_ja_existe, mock_buscar_chamada, mock_buscar_transcricao, mock_conectar
    ):
        mock_conectar.return_value.__enter__.return_value = MagicMock()
        mock_ja_existe.return_value = True
        mock_parse_nome.return_value = {"call_id": "21153502152", "ramal": "1001"}
        mock_buscar_chamada.return_value = {
            "protocolo": 21153502152,
            "ramal": "1001",
            "agente_nome": "Carlos Silva",
            "numero": "33462828",
            "estado_ddd": "41",
        }
        mock_buscar_transcricao.return_value = "Texto Transcrito Anteriormente"

        res = self.ingestor.transcrever_e_inserir(
            caminho=Path("1001-2026-09-28-10-00-00.wav"),
            rotulo_audio="Audio 01",
        )

        self.assertFalse(res.sucesso)
        self.assertTrue(res.ja_existente)
        self.assertEqual(res.agente_nome, "Carlos Silva")
        self.assertEqual(res.numero, "33462828")
        self.assertEqual(res.estado_ddd, "41")
        self.assertEqual(res.texto_transcricao, "Texto Transcrito Anteriormente")
        self.assertEqual(len(self.fake_ia.chamadas_transcrever), 0)

    @patch("app.services.ingestao.conectar")
    @patch("app.services.ingestao.registro_ja_existe")
    @patch("app.services.ingestao.analisar_transcricao")
    @patch("app.services.ingestao.avaliar_qualidade_transcricao")
    @patch("app.services.ingestao.parse_nome_arquivo")
    @patch("app.services.ingestao.buscar_chamada_valida")
    @patch("app.services.ingestao.inserir_registro_chamada")
    def test_transcrever_e_inserir_sucesso(
        self,
        mock_inserir,
        mock_buscar_chamada,
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
        mock_parse_nome.return_value = {"call_id": "21153502152", "ramal": "1001"}
        mock_buscar_chamada.return_value = {
            "protocolo": 21153502152,
            "ramal": "1001",
            "agente_nome": "Carlos Silva",
        }
        mock_inserir.return_value = "1001-2026-09-28-10-00-00.wav"

        res = self.ingestor.transcrever_e_inserir(
            caminho=Path("1001-2026-09-28-10-00-00.wav"),
            rotulo_audio="Audio 01",
        )

        self.assertTrue(res.sucesso)
        self.assertEqual(res.id_registro, "1001-2026-09-28-10-00-00.wav")
        self.assertEqual(res.agente_nome, "Carlos Silva")
        self.assertEqual(res.texto_transcricao, self.fake_ia.transcricao_padrao["texto"])
        self.assertEqual(len(self.fake_ia.chamadas_transcrever), 1)
        mock_inserir.assert_called_once_with(
            mock_conectar.return_value.__enter__.return_value,
            log_arquivo="1001-2026-09-28-10-00-00.wav",
            protocolo=21153502152,
            transcricao=self.fake_ia.transcricao_padrao["texto"],
        )

    @patch("app.services.ingestao.conectar")
    @patch("app.services.ingestao.registro_ja_existe")
    @patch("app.services.ingestao.analisar_transcricao")
    @patch("app.services.ingestao.avaliar_qualidade_transcricao")
    @patch("app.services.ingestao.parse_nome_arquivo")
    @patch("app.services.ingestao.buscar_chamada_valida")
    @patch("app.services.ingestao.inserir_registro_chamada")
    def test_transcrever_com_retry_sucesso_na_segunda_tentativa(
        self,
        mock_inserir,
        mock_buscar_chamada,
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
        mock_parse_nome.return_value = {"call_id": "21153502152", "ramal": "1001"}
        mock_buscar_chamada.return_value = {
            "protocolo": 21153502152,
            "ramal": "1001",
            "agente_nome": "Carlos Silva",
        }
        mock_inserir.return_value = "1001-2026-09-28-10-00-00.wav"

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
    @patch("app.services.ingestao.parse_nome_arquivo")
    @patch("app.services.ingestao.buscar_chamada_valida")
    def test_transcrever_falha_apos_tres_tentativas(
        self, mock_buscar_chamada, mock_parse_nome, mock_ja_existe, mock_conectar
    ):
        mock_conectar.return_value.__enter__.return_value = MagicMock()
        mock_ja_existe.return_value = False
        mock_parse_nome.return_value = {"call_id": "21153502152", "ramal": "1001"}
        mock_buscar_chamada.return_value = {
            "protocolo": 21153502152,
            "ramal": "1001",
            "agente_nome": "Carlos Silva",
        }

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
    @patch("app.services.ingestao.registro_ja_existe")
    @patch("app.services.ingestao.parse_nome_arquivo")
    @patch("app.services.ingestao.buscar_chamada_valida")
    def test_transcrever_nao_encontrado_na_tabela_chamadas(
        self, mock_buscar_chamada, mock_parse_nome, mock_ja_existe, mock_conectar
    ):
        mock_conectar.return_value.__enter__.return_value = MagicMock()
        mock_ja_existe.return_value = False
        mock_parse_nome.return_value = {"call_id": "99999999999", "ramal": "9999"}
        mock_buscar_chamada.return_value = None  # Não bate com chamadas

        res = self.ingestor.transcrever_e_inserir(
            caminho=Path("9999-2026-09-28-10-00-00.wav"),
            rotulo_audio="Audio Invalido",
        )

        self.assertFalse(res.sucesso)
        self.assertIn("não encontrada na tabela chamadas", res.motivo_descarte)
        # Garante que NÃO gastou chamada de transcrição da IA!
        self.assertEqual(len(self.fake_ia.chamadas_transcrever), 0)

    @patch("app.services.ingestao.parse_nome_arquivo")
    def test_transcrever_protocolo_invalido(self, mock_parse_nome):
        mock_parse_nome.return_value = {"call_id": "", "ramal": "1001"}

        res = self.ingestor.transcrever_e_inserir(
            caminho=Path("sem-callid.wav"),
            rotulo_audio="Audio Sem Call ID",
        )

        self.assertFalse(res.sucesso)
        self.assertIn("Protocolo (call_id) não encontrado", res.motivo_descarte)
        self.assertEqual(len(self.fake_ia.chamadas_transcrever), 0)

    @patch("app.services.ingestao.conectar")
    @patch("app.services.ingestao.verificar_coluna_revisao")
    @patch("app.services.ingestao.inserir_empresa")
    @patch("app.services.ingestao.inserir_revisao")
    def test_revisar_transcricao_sucesso(
        self, mock_inserir_rev, mock_inserir_emp, mock_verificar_rev, mock_conectar
    ):
        mock_conectar.return_value.__enter__.return_value = MagicMock()
        mock_verificar_rev.return_value = False
        mock_inserir_emp.return_value = 42
        mock_inserir_rev.return_value = "[Atendente]: Olá\n[Cliente]: Oi"

        res = self.ingestor.revisar_transcricao(
            log_arquivo="audio1.wav",
            texto_diarizado="Olá Oi",
            agente_nome="Carlos",
            rotulo_audio="Audio 01",
        )

        self.assertIsInstance(res, dict)
        self.assertEqual(res["empresa"], "Empresa Teste")
        self.assertEqual(res["id_empresa"], 42)
        self.assertIn("Agente", res["revisao"])
        self.assertEqual(len(self.fake_ia.chamadas_revisar), 1)
        mock_inserir_emp.assert_called_once()
        mock_inserir_rev.assert_called_once()

    @patch("app.services.ingestao.time.sleep")
    @patch("app.services.ingestao.conectar")
    @patch("app.services.ingestao.verificar_coluna_revisao")
    @patch("app.services.ingestao.inserir_empresa")
    @patch("app.services.ingestao.inserir_revisao")
    def test_revisar_transcricao_degradacao_graciosa(
        self, mock_inserir_rev, mock_inserir_emp, mock_verificar_rev, mock_conectar, mock_sleep
    ):
        mock_conectar.return_value.__enter__.return_value = MagicMock()
        mock_verificar_rev.return_value = False
        mock_inserir_emp.return_value = 99
        mock_inserir_rev.return_value = "URA / Transcrição Bruta (Revisão indisponível):\nOlá mundo"

        # Simula erro da IA em todas as tentativas
        self.fake_ia.revisar = MagicMock(side_effect=ValueError("Modelo de IA devolveu revisão vazia (resultado_raw='')."))

        res = self.ingestor.revisar_transcricao(
            log_arquivo="audio_falha.wav",
            texto_diarizado="Olá mundo",
            agente_nome="Lucas",
            rotulo_audio="Audio Falha",
        )

        self.assertIsInstance(res, dict)
        self.assertEqual(res["empresa"], "Não encontrado")
        self.assertIn("Transcrição Bruta", res["revisao"])
        self.assertEqual(res["fonte_dados"], "Não identificado")
        mock_inserir_rev.assert_called_once()
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("app.services.ingestao.time.sleep")
    @patch("app.services.ingestao.conectar")
    @patch("app.services.ingestao.verificar_coluna_revisao")
    @patch("app.services.ingestao.buscar_revisao")
    @patch("app.services.ingestao.buscar_transcricao")
    @patch("app.services.ingestao.inserir_empresa")
    @patch("app.services.ingestao.inserir_revisao")
    def test_revisar_transcricao_reprocessa_e_substitui_texto_bruto(
        self, mock_inserir_rev, mock_inserir_emp, mock_buscar_transc, mock_buscar_rev,
        mock_verificar_rev, mock_conectar, mock_sleep
    ):
        mock_conectar.return_value.__enter__.return_value = MagicMock()
        mock_verificar_rev.return_value = False
        mock_buscar_rev.return_value = "URA / Transcrição Bruta (Revisão indisponível):\nOlá mundo"
        mock_buscar_transc.return_value = "Olá mundo"
        mock_inserir_emp.return_value = 101
        mock_inserir_rev.return_value = "Agente: Olá\nCliente: Bom dia"

        self.fake_ia.revisar = MagicMock(return_value={
            "empresa": "Padaria Nova",
            "revisao": "Agente: Olá\nCliente: Bom dia",
            "fonte_dados": "Interlocutor",
        })

        res = self.ingestor.revisar_transcricao(
            log_arquivo="audio_reprocessar.wav",
            texto_diarizado=None,
            agente_nome="Lucas",
            rotulo_audio="Audio Reprocessar",
        )

        self.assertIsInstance(res, dict)
        self.assertEqual(res["empresa"], "Padaria Nova")
        self.assertEqual(res["revisao"], "Agente: Olá\nCliente: Bom dia")
        self.assertEqual(res["id_empresa"], 101)
        mock_inserir_emp.assert_called_once()
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

    @patch("app.services.ingestao.conectar")
    @patch("app.services.ingestao.verificar_coluna_revisao")
    def test_verificar_revisao_existente(self, mock_verificar, mock_conectar):
        mock_conectar.return_value.__enter__.return_value = MagicMock()
        mock_verificar.return_value = True
        self.assertTrue(self.ingestor.verificar_revisao_existente("audio1.wav"))

        mock_verificar.return_value = False
        self.assertFalse(self.ingestor.verificar_revisao_existente("audio2.wav"))

    @patch("app.services.ingestao.conectar")
    @patch("app.services.ingestao.buscar_logs_com_revisao")
    def test_verificar_revisoes_existentes(self, mock_buscar, mock_conectar):
        mock_conectar.return_value.__enter__.return_value = MagicMock()
        mock_buscar.return_value = {"audio1.wav"}
        res = self.ingestor.verificar_revisoes_existentes(["audio1.wav", "audio2.wav"])
        self.assertEqual(res, {"audio1.wav"})

    @patch("app.services.ingestao.conectar")
    @patch("app.services.ingestao.buscar_cache_rpa_google")
    def test_obter_cache_rpa(self, mock_buscar_cache, mock_conectar):
        mock_conectar.return_value.__enter__.return_value = MagicMock()
        mock_buscar_cache.return_value = {"(41) 3310-1010": "Texto Google"}
        res = self.ingestor.obter_cache_rpa(["(41) 3310-1010"])
        self.assertEqual(res, {"(41) 3310-1010": "Texto Google"})

    @patch("app.services.ingestao.conectar")
    @patch("app.services.ingestao.salvar_cache_rpa_google")
    def test_salvar_cache_rpa(self, mock_salvar_cache, mock_conectar):
        mock_cur = MagicMock()
        mock_conectar.return_value.__enter__.return_value = mock_cur
        self.ingestor.salvar_cache_rpa("(41) 3310-1010", "Texto Google")
        mock_salvar_cache.assert_called_once_with(mock_cur, "(41) 3310-1010", "Texto Google")

    def test_salvar_cache_rpa_ignora_vazio_ou_nao_encontrado(self):
        with patch("app.services.ingestao.conectar") as mock_conectar:
            self.ingestor.salvar_cache_rpa("", "Texto")
            self.ingestor.salvar_cache_rpa("(41) 3310-1010", "")
            self.ingestor.salvar_cache_rpa("(41) 3310-1010", "Não encontrado")
            mock_conectar.assert_not_called()


if __name__ == "__main__":
    unittest.main()


