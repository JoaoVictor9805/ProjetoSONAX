# -*- coding: utf-8 -*-
"""Testes unitários para a camada DAO de chamadas e empresas."""
import unittest
from unittest.mock import MagicMock

from app.database.chamadas_dao import (
    buscar_chamada_valida,
    inserir_empresa,
    inserir_revisao,
)


class TestChamadasDao(unittest.TestCase):

    def test_buscar_chamada_valida_retorna_dados_completos(self):
        cur = MagicMock()
        cur.fetchone.return_value = (123456, "1001", "Lucas", "33101010", "41")

        resultado = buscar_chamada_valida(cur, protocolo=123456, ramal="1001")

        self.assertIsNotNone(resultado)
        self.assertEqual(resultado["protocolo"], 123456)
        self.assertEqual(resultado["ramal"], "1001")
        self.assertEqual(resultado["agente_nome"], "Lucas")
        self.assertEqual(resultado["numero"], "33101010")
        self.assertEqual(resultado["estado_ddd"], "41")

    def test_inserir_empresa_nova(self):
        cur = MagicMock()
        # Primeiro SELECT (busca de existente) retorna None
        # Segundo INSERT retorna o novo ID (10)
        cur.fetchone.side_effect = [None, (10,)]

        id_empresa = inserir_empresa(cur, "Transportes Modelo", "Fonte Google")
        self.assertEqual(id_empresa, 10)
        self.assertEqual(cur.execute.call_count, 2)

    def test_inserir_empresa_existente_deduplicacao(self):
        cur = MagicMock()
        # Primeiro SELECT encontra a empresa existente com id 5 e fonte_dados preenchida
        cur.fetchone.return_value = (5, "Fonte Antiga")

        id_empresa = inserir_empresa(cur, "Transportes Modelo", "Fonte Nova")
        self.assertEqual(id_empresa, 5)
        # Deve apenas fazer o SELECT e não tentar fazer INSERT
        self.assertEqual(cur.execute.call_count, 1)

    def test_inserir_revisao_com_id_empresa(self):
        cur = MagicMock()
        cur.fetchone.return_value = ("Texto Revisado",)

        resultado = inserir_revisao(cur, "audio.wav", "Texto Revisado", id_empresa=5)
        self.assertEqual(resultado, "Texto Revisado")
        self.assertTrue(cur.execute.called)
        query_executada = cur.execute.call_args[0][0]
        self.assertIn("id_empresa", query_executada)


if __name__ == "__main__":
    unittest.main()
