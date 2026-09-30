# -*- coding: utf-8 -*-
"""Testes unitários para o serviço de RPA Google (formatação, cache e cancelamento)."""
import threading
import unittest
from unittest.mock import MagicMock, patch

from app.services.rpa_google import (
    coletar_texto_google_telefone,
    coletar_textos_google_lote,
    formatar_telefone_busca,
)


class TestRpaGoogle(unittest.TestCase):

    def test_formatar_telefone_com_ddd_e_numero(self):
        # 8 dígitos com DDD
        self.assertEqual(formatar_telefone_busca("33101010", "41"), "41 3310-1010")
        # 9 dígitos com DDD
        self.assertEqual(formatar_telefone_busca("999991234", "41"), "41 99999-1234")
        # Número já completo
        self.assertEqual(formatar_telefone_busca("4133101010"), "41 3310-1010")
        # 0800
        self.assertEqual(formatar_telefone_busca("08005912117"), "0800 591 2117")
        # None ou vazio
        self.assertIsNone(formatar_telefone_busca(None))
        self.assertIsNone(formatar_telefone_busca(""))

    @patch("webbrowser.open")
    @patch("pyperclip.paste")
    @patch("pyperclip.copy")
    @patch("pywinauto.keyboard.send_keys")
    def test_coletar_texto_google_sucesso(self, mock_send_keys, mock_copy, mock_paste, mock_open):
        mock_paste.return_value = "Resultado da pesquisa no Google sobre Empresa Modelo"

        texto = coletar_texto_google_telefone("41 3310-1010", tempo_espera_pagina=0.01)

        mock_open.assert_called_once()
        self.assertIn("Empresa Modelo", texto)
        self.assertEqual(mock_send_keys.call_count, 3)

    def test_coletar_texto_google_cancelado(self):
        cancel = threading.Event()
        cancel.set()

        texto = coletar_texto_google_telefone("41 3310-1010", cancel=cancel, tempo_espera_pagina=1.0)
        self.assertEqual(texto, "Não encontrado")

    @patch("app.services.rpa_google.coletar_texto_google_telefone")
    def test_coletar_textos_google_lote_com_cache(self, mock_coletar_individual):
        mock_coletar_individual.return_value = "Texto Simulado Google"

        telefones_map = {
            "Audio_01.wav": "41 3310-1010",
            "Audio_02.wav": "41 3310-1010",  # Mesmo telefone: deve usar cache!
            "Audio_03.wav": "0800 591 2117",
            "Audio_04.wav": None,             # Sem telefone
        }

        resultados = coletar_textos_google_lote(telefones_map, tempo_espera_pagina=0.01)

        # Deve chamar apenas 2 vezes (41 3310-1010 e 0800 591 2117)
        self.assertEqual(mock_coletar_individual.call_count, 2)
        self.assertEqual(resultados["Audio_01.wav"], "Texto Simulado Google")
        self.assertEqual(resultados["Audio_02.wav"], "Texto Simulado Google")
        self.assertEqual(resultados["Audio_03.wav"], "Texto Simulado Google")
        self.assertEqual(resultados["Audio_04.wav"], "Não encontrado")


if __name__ == "__main__":
    unittest.main()
