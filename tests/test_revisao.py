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

    def test_parsear_resposta_preserva_acentuacao_e_evita_mojibake(self):
        resposta_raw = (
            '{\n'
            '  "Empresa": "Biesse",\n'
            '  "Revisao": "URA: Obrigado por ligar para a Biesse, para falar com a administração. '
            'Digite 1 para a assistência técnica, digite 2 para comercial.\\n'
            'Cliente (Biesse): Oi. Alô.\\n'
            'Agente (Falavinha): Meu nome é Karolini. Como você já falou?"\n'
            '}'
        )
        empresa, revisao = parsear_resposta_revisao(resposta_raw)
        self.assertEqual(empresa, "Biesse")
        self.assertNotIn("Ã§", revisao)
        self.assertNotIn("Ãª", revisao)
        self.assertIn("administração", revisao)
        self.assertIn("assistência técnica", revisao)
        self.assertIn("você", revisao)

    def test_parsear_resposta_fallback_regex_preserva_utf8(self):
        # Resposta corrompida na sintaxe JSON forçando o fallback via regex
        resposta_invalida = (
            'Aqui está o resultado:\n'
            '{\n'
            '  "Empresa": "Biesse",\n'
            '  "Revisao": "URA: administração\\nAssistência técnica para você."\n'
            '}\n'
            'Texto extra no final que quebra JSON puro'
        )
        empresa, revisao = parsear_resposta_revisao(resposta_invalida)
        self.assertEqual(empresa, "Biesse")
        self.assertNotIn("Ã§", revisao)
        self.assertIn("administração", revisao)
        self.assertIn("Assistência técnica para você.", revisao)

    def test_parsear_resposta_empresa_null_normaliza_para_nao_encontrado(self):
        resposta_raw = '[{"Empresa": null}, {"Revisao": "Cliente: Alô\\nAgente (Falavinha): Olá"}]'
        empresa, revisao = parsear_resposta_revisao(resposta_raw)
        self.assertEqual(empresa, "Não encontrado")
        self.assertIn("Cliente: Alô", revisao)

    def test_prompt_revisao_instrui_ignorar_etapa_empresa_quando_rpa_pulado(self):
        from app.config.prompts import prompt_revisao
        from app.services.revisao import MARCADOR_RPA_IGNORADO

        self.assertIn(MARCADOR_RPA_IGNORADO, prompt_revisao)
        self.assertIn("IGNORE COMPLETAMENTE a ETAPA 1", prompt_revisao)
        self.assertIn("NÃO** tente extrair, deduzir ou adivinhar o nome da empresa", prompt_revisao)

    def test_revisar_texto_com_rpa_ignorado_forca_nao_encontrado_e_remove_rotulo_empresa(self):
        from unittest.mock import MagicMock, patch
        from app.services.revisao import MARCADOR_RPA_IGNORADO, revisar_texto

        fake_msg = MagicMock()
        fake_msg.content = '[{"Empresa": "Empresa Alucinada"}, {"Revisao": "Cliente (Empresa Alucinada): Alô\\nAgente (Falavinha): Bom dia"}]'

        mock_client = MagicMock()
        mock_client.invoke.return_value = fake_msg

        with patch("app.services.gemini_pool.openrouter_em_cooldown", return_value=False):
            with patch("app.services.revisao.client", mock_client):
                res = revisar_texto(
                    "Alô. Bom dia.",
                    texto_copiado_google=MARCADOR_RPA_IGNORADO,
                    nome_atendente="Lucas",
                )

        self.assertEqual(res["empresa"], "Não encontrado")
        self.assertEqual(res["revisao"], "Cliente: Alô\nAgente (Falavinha): Bom dia")


if __name__ == "__main__":
    unittest.main()
