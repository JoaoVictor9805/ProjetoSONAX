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
        fonte = montar_fonte_dados("Texto Google da busca", "Padaria do João")
        self.assertIn("[GOOGLE]\nTexto Google da busca", fonte)
        self.assertIn("[DIARIZAÇÃO]\nPadaria do João", fonte)

    def test_montar_fonte_dados_vazia(self):
        fonte = montar_fonte_dados(None, None)
        self.assertIn("[GOOGLE]\nNão encontrado", fonte)
        self.assertIn("[DIARIZAÇÃO]\nNão identificado no diálogo", fonte)


    def test_parsear_resposta_com_think_tags(self):
        resposta_raw = """<think>
O usuário quer identificar a empresa.
Analisei a transcrição e identifiquei Metalúrgica Vale.
</think>
```json
[
  {
    "Empresa": "Metalúrgica Vale"
  },
  {
    "Revisao": "Agente (Falavinha): Bom dia.\\nCliente (Metalúrgica Vale): Olá!"
  }
]
```"""
        empresa, revisao = parsear_resposta_revisao(resposta_raw)
        self.assertEqual(empresa, "Metalúrgica Vale")
        self.assertIn("Cliente (Metalúrgica Vale): Olá!", revisao)


if __name__ == "__main__":
    unittest.main()
