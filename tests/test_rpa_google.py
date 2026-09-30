# -*- coding: utf-8 -*-
"""Testes unitários para o serviço de RPA Google (formatação, cache e cancelamento)."""
import threading
import unittest
from unittest.mock import MagicMock, patch

from app.services.rpa_google import (
    abrir_navegador_busca,
    coletar_texto_google_telefone,
    coletar_textos_google_lote,
    formatar_telefone_busca,
    listar_caminhos_google_chrome,
    obter_caminho_chrome_instalado,
    testar_versoes_chrome,
)


class TestRpaGoogle(unittest.TestCase):

    def test_formatar_telefone_com_ddd_e_numero(self):
        # Número com DDI 55 e 8 dígitos (exemplo do Ramon / áudio WAV real)
        self.assertEqual(formatar_telefone_busca("554136682223"), "(41) 3668-2223")
        self.assertEqual(formatar_telefone_busca("554133462828"), "(41) 3346-2828")
        # Número com DDI 55 e celular (9 dígitos)
        self.assertEqual(formatar_telefone_busca("5541999992828"), "(41) 99999-2828")
        # 8 dígitos com DDD separado (com zero ou sem zero)
        self.assertEqual(formatar_telefone_busca("36682223", "041"), "(41) 3668-2223")
        self.assertEqual(formatar_telefone_busca("33101010", "41"), "(41) 3310-1010")
        # 9 dígitos com DDD separado (com zero ou sem zero)
        self.assertEqual(formatar_telefone_busca("988887777", "041"), "(41) 98888-7777")
        self.assertEqual(formatar_telefone_busca("999991234", "41"), "(41) 99999-1234")
        # Número já com DDD embutido e com prefixo de operadora
        self.assertEqual(formatar_telefone_busca("41988887777", "041"), "(41) 98888-7777")
        self.assertEqual(formatar_telefone_busca("04141988887777", "041"), "(41) 98888-7777")
        self.assertEqual(formatar_telefone_busca("04136682223"), "(41) 3668-2223")
        self.assertEqual(formatar_telefone_busca("4133101010"), "(41) 3310-1010")
        # 0800
        self.assertEqual(formatar_telefone_busca("08005912117"), "0800 591 2117")
        # None ou vazio
        self.assertIsNone(formatar_telefone_busca(None))
        self.assertIsNone(formatar_telefone_busca(""))

    @patch("app.services.rpa_google.abrir_navegador_busca")
    @patch("pyperclip.paste")
    @patch("pyperclip.copy")
    @patch("pywinauto.keyboard.send_keys")
    def test_coletar_texto_google_sucesso(self, mock_send_keys, mock_copy, mock_paste, mock_abrir):
        mock_paste.return_value = "Resultado da pesquisa no Google sobre Empresa Modelo"

        texto = coletar_texto_google_telefone("(41) 3310-1010", tempo_espera_pagina=0.01)

        mock_abrir.assert_called_once_with("https://www.google.com/search?q=%2841%29+3310-1010", caminho_navegador=None)
        self.assertIn("Empresa Modelo", texto)
        self.assertEqual(mock_send_keys.call_count, 3)

    def test_coletar_texto_google_cancelado(self):
        cancel = threading.Event()
        cancel.set()

        texto = coletar_texto_google_telefone("(41) 3310-1010", cancel=cancel, tempo_espera_pagina=1.0)
        self.assertEqual(texto, "Não encontrado")

    @patch("app.services.rpa_google.coletar_texto_google_telefone")
    def test_coletar_textos_google_lote_com_cache(self, mock_coletar_individual):
        mock_coletar_individual.return_value = "Texto Simulado Google"

        telefones_map = {
            "Audio_01.wav": "(41) 3310-1010",
            "Audio_02.wav": "(41) 3310-1010",  # Mesmo telefone: deve usar cache!
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

    def test_listar_caminhos_google_chrome_multiplas_versoes(self):
        caminhos = listar_caminhos_google_chrome()
        self.assertIsInstance(caminhos, list)
        self.assertGreater(len(caminhos), 3)
        # Deve cobrir Program Files e AppData
        textos_juntos = " ".join(caminhos)
        self.assertIn("chrome.exe", textos_juntos)

    @patch("os.path.isfile")
    def test_obter_caminho_chrome_instalado(self, mock_isfile):
        # Simula que o segundo caminho existe
        mock_isfile.side_effect = lambda p: "Program Files (x86)" in p

        caminho = obter_caminho_chrome_instalado()
        self.assertIsNotNone(caminho)
        self.assertIn("Program Files (x86)", caminho)

    @patch("subprocess.Popen")
    @patch("app.services.rpa_google.obter_caminho_chrome_instalado")
    @patch("os.path.isfile")
    def test_abrir_navegador_busca_com_chrome(self, mock_isfile, mock_obter_chrome, mock_popen):
        mock_isfile.return_value = True
        mock_obter_chrome.return_value = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

        res = abrir_navegador_busca("https://google.com")
        self.assertTrue(res)
        mock_popen.assert_called_once_with([r"C:\Program Files\Google\Chrome\Application\chrome.exe", "https://google.com"])

    @patch("webbrowser.open")
    @patch("app.services.rpa_google.obter_caminho_chrome_instalado")
    def test_abrir_navegador_busca_fallback_webbrowser(self, mock_obter_chrome, mock_wb_open):
        mock_obter_chrome.return_value = None

        res = abrir_navegador_busca("https://google.com")
        mock_wb_open.assert_called_once_with("https://google.com")

    def test_testar_versoes_chrome_retorna_lista_diagnostico(self):
        versoes = testar_versoes_chrome()
        self.assertIsInstance(versoes, list)
        self.assertGreater(len(versoes), 0)
        self.assertIn("caminho", versoes[0])
        self.assertIn("instalado", versoes[0])


if __name__ == "__main__":
    unittest.main()
