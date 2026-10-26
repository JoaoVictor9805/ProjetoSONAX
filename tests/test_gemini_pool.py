# -*- coding: utf-8 -*-
"""Testes unitários para o pool e gerenciador de chaves Gemini com rotação e cooldown de 24h."""
import os
import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.services.gemini_pool import (
    DURACAO_BLOQUEIO_SEGUNDOS,
    OPENROUTER_STATUS_KEY,
    eh_erro_cota_gemini,
    eh_erro_credito_openrouter,
    executar_analise_com_pool,
    executar_revisao_com_pool,
    listar_chaves_gemini_configuradas,
    marcar_cota_esgotada,
    marcar_openrouter_esgotado,
    mascarar_chave,
    obter_chaves_gemini_disponiveis,
    openrouter_em_cooldown,
)


class TestGeminiPool(unittest.TestCase):

    def setUp(self):
        # Limpa variáveis de teste
        self.patcher = patch.dict(os.environ, {
            "GEMINI_API_KEY": "key-primary-123456",
            "GEMINI_API_KEY_FALLBACK": "key-fallback-1-789012",
            "GEMINI_API_KEY_FALLBACK_2": "key-fallback-2-345678",
        })
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_mascarar_chave(self):
        self.assertEqual(mascarar_chave(""), "")
        self.assertEqual(mascarar_chave("curta"), "cur...rta")
        masc = mascarar_chave("AIzaSyMockDummyKey1234567890abcdefghijk")
        self.assertTrue(masc.startswith("AIzaSyMo..."))
        self.assertTrue(masc.endswith("ghijk"))

    def test_listar_chaves_gemini_configuradas(self):
        chaves = listar_chaves_gemini_configuradas()
        self.assertEqual(len(chaves), 3)
        self.assertEqual(chaves[0], ("GEMINI_API_KEY", "key-primary-123456"))
        self.assertEqual(chaves[1], ("GEMINI_API_KEY_FALLBACK", "key-fallback-1-789012"))
        self.assertEqual(chaves[2], ("GEMINI_API_KEY_FALLBACK_2", "key-fallback-2-345678"))

    def test_listar_chaves_ignora_sk_dummy_e_duplicadas(self):
        with patch.dict(os.environ, {
            "GEMINI_API_KEY": "sk-dummy-key",
            "GEMINI_API_KEY_FALLBACK": "key-valida-unica",
            "GEMINI_API_KEY_FALLBACK_2": "key-valida-unica",  # duplicada
        }):
            chaves = listar_chaves_gemini_configuradas()
            self.assertEqual(chaves, [("GEMINI_API_KEY_FALLBACK", "key-valida-unica")])

    def test_eh_erro_cota_gemini(self):
        exc_429 = RuntimeError("429 RESOURCE_EXHAUSTED. Quota exceeded on Free Tier: 500 requests per day")
        self.assertTrue(eh_erro_cota_gemini(exc_429))

        exc_rate = Exception("You exceeded your current quota, please check your plan and billing details")
        self.assertTrue(eh_erro_cota_gemini(exc_rate))

        class GoogleRateLimitError(Exception):
            pass

        self.assertTrue(eh_erro_cota_gemini(GoogleRateLimitError("Rate limit exceeded")))

        # Erros não relacionados à cota
        exc_outro = ValueError("JSON inválido retornado pelo modelo")
        self.assertFalse(eh_erro_cota_gemini(exc_outro))

        exc_net = ConnectionError("Connection refused by peer")
        self.assertFalse(eh_erro_cota_gemini(exc_net))

    @patch("app.services.gemini_pool._salvar_status_disco")
    @patch("app.services.gemini_pool._carregar_status_disco")
    def test_marcar_cota_esgotada_e_obter_disponiveis(self, mock_carregar, mock_salvar):
        status_simulado = {}
        mock_carregar.side_effect = lambda: status_simulado.copy()

        def salvar_impl(d):
            status_simulado.clear()
            status_simulado.update(d)
        mock_salvar.side_effect = salvar_impl

        # Todas as 3 estão disponíveis inicialmente
        disp = obter_chaves_gemini_disponiveis()
        self.assertEqual(len(disp), 3)

        # Marca a primária como esgotada
        marcar_cota_esgotada("GEMINI_API_KEY", "key-primary-123456", "429 RESOURCE_EXHAUSTED")

        # Agora apenas 2 devem estar disponíveis
        disp_apos = obter_chaves_gemini_disponiveis()
        self.assertEqual(len(disp_apos), 2)
        self.assertEqual(disp_apos[0][0], "GEMINI_API_KEY_FALLBACK")
        self.assertEqual(disp_apos[1][0], "GEMINI_API_KEY_FALLBACK_2")

    @patch("app.services.gemini_pool._salvar_status_disco")
    @patch("app.services.gemini_pool._carregar_status_disco")
    def test_reseta_chave_apos_24_horas(self, mock_carregar, mock_salvar):
        # Simula chave bloqueada há 25 horas atrás
        tempo_bloqueio = time.time() - (25 * 3600)
        status_simulado = {
            "key-primary-123456": {
                "var_name": "GEMINI_API_KEY",
                "bloqueado_em": tempo_bloqueio,
            }
        }
        mock_carregar.side_effect = lambda: status_simulado.copy()

        def salvar_impl(d):
            status_simulado.clear()
            status_simulado.update(d)
        mock_salvar.side_effect = salvar_impl

        disp = obter_chaves_gemini_disponiveis()
        # A chave deve ter sido desbloqueada e reativada!
        nomes_disp = [item[0] for item in disp]
        self.assertIn("GEMINI_API_KEY", nomes_disp)
        self.assertNotIn("key-primary-123456", status_simulado)

    @patch("app.services.gemini_pool.obter_cliente_gemini")
    @patch("app.services.gemini_pool.marcar_cota_esgotada")
    def test_executar_revisao_rotaciona_quando_cota_atingida(self, mock_marcar, mock_obter_cliente):
        mock_prompt = MagicMock()
        mock_prompt.format_messages.return_value = ["msg"]

        # Cliente da chave 1 falha com 429
        cl1 = MagicMock()
        cl1.invoke.side_effect = RuntimeError("429 RESOURCE_EXHAUSTED: Quota exceeded")

        # Cliente da chave 2 sucede
        cl2 = MagicMock()
        mock_resposta = MagicMock()
        mock_resposta.content = '{"empresa": "Empresa Teste", "revisao": "Agente: Bom dia"}'
        cl2.invoke.return_value = mock_resposta

        mock_obter_cliente.side_effect = [cl1, cl2]

        def parsear_mock(texto):
            return "Empresa Teste", "Agente: Bom dia"

        with patch("app.services.gemini_pool.obter_chaves_gemini_disponiveis") as mock_chaves:
            mock_chaves.return_value = [
                ("GEMINI_API_KEY", "key-primary-123456"),
                ("GEMINI_API_KEY_FALLBACK", "key-fallback-1-789012"),
            ]

            resultado = executar_revisao_com_pool(
                mock_prompt,
                {"ligacao": "texto"},
                "gemini-3.1-flash-lite",
                parsear_mock,
            )

            self.assertIn("Empresa Teste", resultado)
            # A chave 1 deve ter sido marcada como esgotada
            mock_marcar.assert_called_once_with(
                "GEMINI_API_KEY",
                "key-primary-123456",
                cl1.invoke.side_effect,
            )
            self.assertEqual(cl2.invoke.call_count, 1)

    @patch("app.services.gemini_pool.obter_cliente_gemini")
    @patch("app.services.gemini_pool.marcar_cota_esgotada")
    def test_executar_analise_rotaciona_quando_cota_atingida(self, mock_marcar, mock_obter_cliente):
        mock_prompt = MagicMock()

        # Cliente da chave 1 falha com 429
        cl1 = MagicMock()
        chain1 = MagicMock()
        chain1.invoke.side_effect = RuntimeError("RESOURCE_EXHAUSTED: 429 quota per day limit exceeded")
        cl1.with_structured_output.return_value = chain1

        # Cliente da chave 2 sucede
        cl2 = MagicMock()
        chain2 = MagicMock()
        chain2.invoke.return_value = {"avaliacao_ia": {"resultado": "Perfil confirmado"}}
        cl2.with_structured_output.return_value = chain2

        mock_obter_cliente.side_effect = [cl1, cl2]
        mock_prompt.__or__.side_effect = lambda x: x

        with patch("app.services.gemini_pool.obter_chaves_gemini_disponiveis") as mock_chaves:
            mock_chaves.return_value = [
                ("GEMINI_API_KEY", "key-primary-123456"),
                ("GEMINI_API_KEY_FALLBACK", "key-fallback-1-789012"),
            ]

            resultado = executar_analise_com_pool(
                mock_prompt,
                {"ligacao": "texto"},
                "gemini-3.1-flash-lite",
                MagicMock,
            )

            self.assertEqual(resultado["avaliacao_ia"]["resultado"], "Perfil confirmado")
            mock_marcar.assert_called_once()
            self.assertEqual(chain2.invoke.call_count, 1)

    def test_eh_erro_credito_openrouter(self):
        exc_402 = RuntimeError("Error code: 402 - {'error': {'message': 'This request requires more credits, or fewer max_tokens. You requested up to 16384 tokens, but can only afford 3275.'}}")
        self.assertTrue(eh_erro_credito_openrouter(exc_402))

        class HttpErr(Exception):
            status_code = 402
        self.assertTrue(eh_erro_credito_openrouter(HttpErr("Payment required")))

        exc_outro = ValueError("Invalid prompt format")
        self.assertFalse(eh_erro_credito_openrouter(exc_outro))

    @patch("app.services.gemini_pool._salvar_status_disco")
    @patch("app.services.gemini_pool._carregar_status_disco")
    def test_marcar_openrouter_esgotado_e_cooldown(self, mock_carregar, mock_salvar):
        status_simulado = {}
        mock_carregar.side_effect = lambda: status_simulado.copy()

        def salvar_impl(d):
            status_simulado.clear()
            status_simulado.update(d)
        mock_salvar.side_effect = salvar_impl

        # Inicialmente não está em cooldown
        self.assertFalse(openrouter_em_cooldown())

        # Marca como esgotado
        marcar_openrouter_esgotado("Error code: 402")

        # Agora deve estar em cooldown
        self.assertTrue(openrouter_em_cooldown())
        self.assertIn(OPENROUTER_STATUS_KEY, status_simulado)
        self.assertEqual(status_simulado[OPENROUTER_STATUS_KEY]["provedor"], "OpenRouter")

    @patch("app.services.gemini_pool._salvar_status_disco")
    @patch("app.services.gemini_pool._carregar_status_disco")
    def test_openrouter_cooldown_expira_apos_24h(self, mock_carregar, mock_salvar):
        tempo_bloqueio = time.time() - (25 * 3600)
        status_simulado = {
            OPENROUTER_STATUS_KEY: {
                "provedor": "OpenRouter",
                "bloqueado_em": tempo_bloqueio,
            }
        }
        mock_carregar.side_effect = lambda: status_simulado.copy()

        def salvar_impl(d):
            status_simulado.clear()
            status_simulado.update(d)
        mock_salvar.side_effect = salvar_impl

        # Como já passaram 25h, cooldown deve retornar False e limpar o registro
        self.assertFalse(openrouter_em_cooldown())
        self.assertNotIn(OPENROUTER_STATUS_KEY, status_simulado)


if __name__ == "__main__":
    unittest.main()
