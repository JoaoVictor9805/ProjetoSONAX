import sys
import threading
import unittest
from pathlib import Path

# Permite executar este arquivo de teste diretamente (ex: botão Run/Play da IDE)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.ia import FakeProvedorIA, ProvedorIA, ProvedorIAReal
from app.services.transcricao import TranscricaoCancelada


class TestCosturaIA(unittest.TestCase):

    def test_protocol_conformance(self):
        # Valida em runtime se ambas as classes cumprem a assinatura do Protocol
        self.assertTrue(isinstance(FakeProvedorIA(), ProvedorIA))
        self.assertTrue(isinstance(ProvedorIAReal(), ProvedorIA))

    def test_fake_ia_execucao_padrao(self):
        fake = FakeProvedorIA()

        # Transcrição
        res_trans = fake.transcrever(Path("audio.wav"))
        self.assertIn("texto", res_trans)
        self.assertIn("metricas", res_trans)
        self.assertEqual(len(fake.chamadas_transcrever), 1)

        # Revisão
        res_rev = fake.revisar("transcricao teste", nome_atendente="Lucas")
        self.assertIsInstance(res_rev, str)
        self.assertIn("Agente", res_rev)
        self.assertEqual(len(fake.chamadas_revisar), 1)

        # Análise
        res_ana = fake.analisar(res_rev)
        self.assertIn("nota_final", res_ana)
        self.assertIn("criterios", res_ana)
        self.assertEqual(len(fake.chamadas_analisar), 1)

    def test_fake_ia_cancelamento(self):
        fake = FakeProvedorIA()
        cancel = threading.Event()
        cancel.set()

        with self.assertRaises(TranscricaoCancelada):
            fake.transcrever(Path("audio.wav"), cancel=cancel)

    def test_fake_ia_falhas_e_recuperacao(self):
        fake = FakeProvedorIA(falhas_antes_de_acerto=2)

        # 1ª tentativa -> falha
        with self.assertRaises(ConnectionError):
            fake.transcrever(Path("audio.wav"))

        # 2ª tentativa -> falha
        with self.assertRaises(ConnectionError):
            fake.transcrever(Path("audio.wav"))

        # 3ª tentativa -> sucesso
        res = fake.transcrever(Path("audio.wav"))
        self.assertIn("texto", res)
        self.assertEqual(len(fake.chamadas_transcrever), 3)


if __name__ == "__main__":
    unittest.main()
