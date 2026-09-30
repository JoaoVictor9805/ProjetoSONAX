# -*- coding: utf-8 -*-
"""Testes unitários para o serviço de análise de atendimento via IA."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.analise_final_AI import AnaliseLigacao, Criterio, analisar_ligacao, calcular_nota_final


class TestAnaliseFinalAI(unittest.TestCase):

    def test_calcular_nota_final_media_correta(self):
        dados = {
            "criterios": [
                {"criterio": "chamar pelo nome", "nota_criterio": 10},
                {"criterio": "agir com empatia", "nota_criterio": 8},
                {"criterio": "ouvir com atencao", "nota_criterio": 9},
                {"criterio": "eficiencia operacional", "nota_criterio": 7},
                {"criterio": "surpreender", "nota_criterio": 8},
            ]
        }
        res = calcular_nota_final(dados)
        self.assertEqual(res["nota_final"], 8)  # (10 + 8 + 9 + 7 + 8) / 5 = 42 / 5 = 8.4 -> round = 8

    def test_calcular_nota_final_sem_notas(self):
        dados = {
            "criterios": [
                {"criterio": "chamar pelo nome", "nota_criterio": None},
            ]
        }
        res = calcular_nota_final(dados)
        self.assertIsNone(res["nota_final"])

    @patch("app.services.analise_final_AI.chain")
    def test_analisar_ligacao_ura(self, mock_chain):
        mock_chain.invoke.return_value = {
            "nota_final": 5,
            "feedback_geral": "[A chamada retrata a fala de uma Unidade de resposta audível (URA)]",
            "titulo": "Ligação URA",
            "resumo_chamada": "Texto",
            "pontos_fortes": "Texto",
            "fragilidades": "Texto",
            "oportunidades": "Texto",
            "criterios": [
                {"criterio": "chamar pelo nome", "nota_criterio": 5, "justificativa_criterio": "ok"},
            ],
        }

        res = analisar_ligacao("URA: Digite 1")
        self.assertIsNone(res["nota_final"])
        self.assertIsNone(res["resumo_chamada"])
        self.assertIsNone(res["pontos_fortes"])
        self.assertEqual(
            res["criterios"][0]["justificativa_criterio"],
            "[Não houve contexto suficiente para a avaliação desse critério]",
        )


if __name__ == "__main__":
    unittest.main()
