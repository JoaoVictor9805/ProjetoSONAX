# -*- coding: utf-8 -*-
"""Testes unitários para o parser de resposta e triangulação de revisão com IA."""
import unittest

from app.services.revisao import montar_fonte_dados, parsear_resposta_revisao


class TestRevisao(unittest.TestCase):

    def test_parsear_resposta_json_lista(self):
        resposta_raw = """
[
  {
    "Empresa": "Transportes Modelo"
  },
  {
    "Revisao": "Cliente (Transportes Modelo): Bom dia.\\nAgente (Falavinha): Olá, bom dia!"
  }
]
"""
        empresa, revisao = parsear_resposta_revisao(resposta_raw)
        self.assertEqual(empresa, "Transportes Modelo")
        self.assertIn("Cliente (Transportes Modelo): Bom dia.", revisao)

    def test_parsear_resposta_com_markdown_fences(self):
        resposta_raw = """```json
[
  {
    "Empresa": "Indústria ABC"
  },
  {
    "Revisao": "Agente (Falavinha): Olá!\\nCliente (Indústria ABC): Alô."
  }
]
```"""
        empresa, revisao = parsear_resposta_revisao(resposta_raw)
        self.assertEqual(empresa, "Indústria ABC")
        self.assertIn("Agente (Falavinha): Olá!", revisao)

    def test_parsear_resposta_fallback(self):
        resposta_raw = "Cliente: Bom dia, não veio em JSON."
        empresa, revisao = parsear_resposta_revisao(resposta_raw)
        self.assertEqual(empresa, "Não encontrado")
        self.assertIn("Cliente: Bom dia", revisao)

    def test_montar_fonte_dados_combinada(self):
        revisao = "Agente (Carlos): Bom dia!\nCliente (Padaria do João): Olá, tudo bem?"
        fonte = montar_fonte_dados(revisao, "Padaria do João")
        self.assertEqual(fonte, "Interlocutor / Agente")

    def test_montar_fonte_dados_apenas_cliente(self):
        revisao = "Cliente (Padaria do João): Padaria do João, bom dia."
        fonte = montar_fonte_dados(revisao, "Padaria do João")
        self.assertEqual(fonte, "Interlocutor")

    def test_montar_fonte_dados_apenas_agente(self):
        revisao = "Agente (Carlos): Alô, alguém na linha?"
        fonte = montar_fonte_dados(revisao, None)
        self.assertEqual(fonte, "Agente")

    def test_montar_fonte_dados_vazia(self):
        fonte = montar_fonte_dados(None, None)
        self.assertEqual(fonte, "Não identificado")

    def test_montar_fonte_dados_parametros_explicitos(self):
        fonte = montar_fonte_dados(tem_interlocutor=True, tem_agente=False)
        self.assertEqual(fonte, "Interlocutor")


if __name__ == "__main__":
    unittest.main()
