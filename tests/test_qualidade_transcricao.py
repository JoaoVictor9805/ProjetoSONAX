# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.qualidade_transcricao import (
    analisar_transcricao,
    avaliar_qualidade_transcricao,
)


class TestQualidadeTranscricao(unittest.TestCase):

    def test_analisar_transcricao_basica(self):
        texto = "Olá, bom dia! Aqui é o atendente Carlos da empresa."
        metricas = analisar_transcricao(texto)

        self.assertEqual(metricas["quantidade_palavras"], 10)
        self.assertEqual(metricas["quantidade_repeticoes"], 0)
        self.assertEqual(metricas["taxa_repeticao"], 0.0)
        self.assertEqual(metricas["caracteres_invalidos"], 0)

    def test_analisar_transcricao_com_repeticoes(self):
        texto = "bom dia dia dia atendente atendente"
        metricas = analisar_transcricao(texto)

        self.assertEqual(metricas["quantidade_palavras"], 6)
        # repeticoes: "dia dia", "dia dia", "atendente atendente" = 3
        self.assertGreater(metricas["quantidade_repeticoes"], 0)
        self.assertGreater(metricas["taxa_repeticao"], 0.0)

    def test_avaliar_qualidade_transcricao_excelente(self):
        # Texto com mais de 40 palavras distintas e boa confiança
        palavras = [f"termo{i}" for i in range(50)]
        texto = " ".join(palavras)
        dados = {
            **analisar_transcricao(texto),
            "logprob_media": -0.2,
            "taxa_compressao_media": 1.1,
            "probabilidade_media_sem_fala": 0.02,
        }
        avaliacao = avaliar_qualidade_transcricao(dados)
        self.assertEqual(avaliacao["classificacao"], "Excelente")
        self.assertGreaterEqual(avaliacao["pontuacao"], 90)

    def test_avaliar_qualidade_transcricao_curta_pessima(self):
        # Texto com menos de 10 palavras
        texto = "Oi tudo bem"
        dados = {
            **analisar_transcricao(texto),
        }
        avaliacao = avaliar_qualidade_transcricao(dados)
        self.assertEqual(avaliacao["classificacao"], "Péssimo")
        self.assertLess(avaliacao["pontuacao"], 40)


if __name__ == "__main__":
    unittest.main()
