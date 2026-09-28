# -*- coding: utf-8 -*-
import sys
import threading
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.fechamento_ciclo import (
    FechamentoCicloResult,
    PerfilAgenteOutput,
    calcular_intervalo_ciclo,
    executar_fechamento_ciclo,
    mes_anterior_padrao,
)


class TestFechamentoCiclo(unittest.TestCase):

    def test_calcular_intervalo_ciclo(self):
        # Agosto de 2026 tem 31 dias
        inicio, fim = calcular_intervalo_ciclo(2026, 8)
        self.assertEqual(inicio, date(2026, 8, 1))
        self.assertEqual(fim, date(2026, 8, 31))

        # Fevereiro de 2024 (ano bissexto) tem 29 dias
        inicio_bis, fim_bis = calcular_intervalo_ciclo(2024, 2)
        self.assertEqual(fim_bis, date(2024, 2, 29))

        # Fevereiro de 2026 (ano normal) tem 28 dias
        inicio_norm, fim_norm = calcular_intervalo_ciclo(2026, 2)
        self.assertEqual(fim_norm, date(2026, 2, 28))

    def test_mes_anterior_padrao(self):
        ano, mes = mes_anterior_padrao()
        self.assertIsInstance(ano, int)
        self.assertIsInstance(mes, int)
        self.assertTrue(1 <= mes <= 12)

    @patch("app.services.fechamento_ciclo.conectar")
    @patch("app.services.fechamento_ciclo.garantir_schema_atualizado")
    @patch("app.services.fechamento_ciclo.buscar_agentes_no_ciclo")
    def test_executar_fechamento_sem_agentes(self, mock_buscar_agentes, mock_schema, mock_conectar):
        mock_conectar.return_value.__enter__.return_value = MagicMock()
        mock_buscar_agentes.return_value = []

        res = executar_fechamento_ciclo(2026, 8, forcar=True)

        self.assertIsInstance(res, FechamentoCicloResult)
        self.assertEqual(res.total_agentes, 0)
        self.assertEqual(res.processados, 0)
        self.assertEqual(res.falhas, 0)
        self.assertFalse(res.cancelado)
        self.assertTrue(res.sucesso)

    @patch("app.services.fechamento_ciclo.conectar")
    @patch("app.services.fechamento_ciclo.garantir_schema_atualizado")
    @patch("app.services.fechamento_ciclo.buscar_agentes_no_ciclo")
    def test_executar_fechamento_cancelamento_imediato(
        self, mock_buscar_agentes, mock_schema, mock_conectar
    ):
        mock_conectar.return_value.__enter__.return_value = MagicMock()
        mock_buscar_agentes.return_value = ["Carlos", "Ana", "Marcos"]

        cancel = threading.Event()
        cancel.set()  # Cancela antes de começar

        res = executar_fechamento_ciclo(2026, 8, forcar=True, cancel=cancel)

        self.assertIsInstance(res, FechamentoCicloResult)
        self.assertTrue(res.cancelado)
        self.assertFalse(res.sucesso)
        self.assertEqual(res.processados, 0)

    @patch("app.services.fechamento_ciclo.conectar")
    @patch("app.services.fechamento_ciclo.garantir_schema_atualizado")
    @patch("app.services.fechamento_ciclo.buscar_agentes_no_ciclo")
    @patch("app.services.fechamento_ciclo.obter_estatisticas_agente")
    @patch("app.services.fechamento_ciclo.obter_amostras_extremos")
    @patch("app.services.fechamento_ciclo.gravar_perfil_agente")
    def test_executar_fechamento_sucesso_com_chain_injetada(
        self,
        mock_gravar,
        mock_amostras,
        mock_stats,
        mock_buscar_agentes,
        mock_schema,
        mock_conectar,
    ):
        mock_conectar.return_value.__enter__.return_value = MagicMock()
        mock_buscar_agentes.return_value = ["Carlos Silva"]
        mock_stats.return_value = {
            "total_chamadas": 20,
            "nota_media": 8.5,
            "chamadas_validas": 18,
            "medias_criterios": {"empatia": 9.0},
        }
        mock_amostras.return_value = ([], [])
        mock_gravar.return_value = 1

        mock_chain = MagicMock()
        mock_chain.invoke.return_value = PerfilAgenteOutput(
            resumo_evolutivo="Agente consistente e comunicativo.",
            principais_pontos_fortes="Clareza na fala",
            principais_fragilidades="Demora na resposta",
            plano_acao_oportunidades="Treinar agilidade no sistema",
        )

        res = executar_fechamento_ciclo(
            ano=2026,
            mes=8,
            forcar=True,
            chain_ia=mock_chain,
        )

        self.assertTrue(res.sucesso)
        self.assertEqual(res.processados, 1)
        self.assertEqual(res.total_agentes, 1)
        self.assertEqual(res.falhas, 0)
        self.assertFalse(res.cancelado)
        mock_gravar.assert_called_once()


if __name__ == "__main__":
    unittest.main()
