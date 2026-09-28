# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.engine.log_session import LogSessionManager


class TestLogSessionManager(unittest.TestCase):

    def setUp(self):
        self.mgr = LogSessionManager(modo_dev=False)

    def test_mascaramento_modo_usuario(self):
        self.mgr.adicionar_linha("Processando: Audio 01 ...", path="chamada_123.wav")
        self.mgr.adicionar_linha("Erro técnico interno", dev_only=True)

        linhas = self.mgr.obter_linhas_formatadas(modo_dev=False)
        # No modo usuário, deve ter apenas 1 linha e manter "Audio 01"
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0][0], "Processando: Audio 01 ...")

    def test_revelacao_modo_dev(self):
        self.mgr.adicionar_linha("Processando: Audio 01 ...", path="chamada_123.wav")
        self.mgr.adicionar_linha("Erro técnico interno", dev_only=True)

        linhas = self.mgr.obter_linhas_formatadas(modo_dev=True)
        # No modo dev, deve ter 2 linhas e substituir "Audio 01" por "chamada_123.wav"
        self.assertEqual(len(linhas), 2)
        self.assertEqual(linhas[0][0], "Processando: chamada_123.wav ...")
        self.assertEqual(linhas[1][0], "Erro técnico interno")

    def test_aprendizado_rotulo_indireto(self):
        # Primeiro ensina via path
        self.mgr.adicionar_linha("[INFO] Audio 02", path="audio_teste.wav")
        # Depois uma linha de print comum sem path
        self.mgr.adicionar_linha("Diarizando Audio 02 ...")

        linhas_dev = self.mgr.obter_linhas_formatadas(modo_dev=True)
        self.assertEqual(linhas_dev[0][0], "[INFO] audio_teste.wav")
        self.assertEqual(linhas_dev[1][0], "Diarizando audio_teste.wav ...")


if __name__ == "__main__":
    unittest.main()
