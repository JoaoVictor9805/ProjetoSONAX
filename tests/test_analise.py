# -*- coding: utf-8 -*-
"""Testes unitários para o módulo de análise comercial via IA (SPIN, BANT, SDR)."""
import unittest

from app.services.analise_final_AI import (
    calcular_e_sanitizar_analise,
    normalizar_acao_crm,
    _limpar_resposta_json,
)


class TestAnaliseFinalAI(unittest.TestCase):

    def test_limpar_resposta_json_markdown(self):
        json_str = """
```json
{
  "teste": 123
}
```
"""
        res = _limpar_resposta_json(json_str)
        self.assertIsNotNone(res)
        self.assertEqual(res.get("teste"), 123)

    def test_chamada_avaliavel_soma_criterios_e_valida_dimensoes(self):
        dados = {
            "avaliacao_ia": {
                "resultado": "Perfil confirmado",
                "ligacao_relevante": "s",
                "reuniao_confirmada": "s",
                "data_confirmada": "s",
                "resultado_frase": "Reunião técnica agendada com decisor.",
            },
            "avaliacao_sdr": {
                "feedback_geral": "Ótima abordagem consultiva.",
                "codigo_oportunidade": "OP_SPIN_03",
            },
            "avaliacao_criterio": [
                {"codigo_criterio": "CRIT_ABERTURA", "criterio": "Abertura", "nota_criterio": 10, "justificativa_criterio": "Clara."},
                {"codigo_criterio": "CRIT_SPIN", "criterio": "SPIN", "nota_criterio": 22, "justificativa_criterio": "Bom."},
                {"codigo_criterio": "CRIT_PERFIL", "criterio": "Perfil", "nota_criterio": 25, "justificativa_criterio": "Validou tudo."},
                {"codigo_criterio": "CRIT_BANT", "criterio": "BANT", "nota_criterio": 12, "justificativa_criterio": "Faltou orçamento."},
                {"codigo_criterio": "CRIT_ESCUTA", "criterio": "Escuta", "nota_criterio": 8, "justificativa_criterio": "Atento."},
                {"codigo_criterio": "CRIT_PROX_PASSO", "criterio": "Próximo Passo", "nota_criterio": 8, "justificativa_criterio": "Agendou."},
            ],
            "crm": {
                "resumo": "Resumo executivo curto para teste."
            }
        }

        res = calcular_e_sanitizar_analise(dados, protocolo=999, empresa_contatada=42)

        # Nota final deve ser a soma exata dos 6 critérios: 10 + 22 + 25 + 12 + 8 + 8 = 85
        self.assertEqual(res["avaliacao_sdr"]["nota_final"], 85)
        self.assertEqual(res["avaliacao_sdr"]["codigo_oportunidade"], "OP_SPIN_03")
        self.assertEqual(res["avaliacao_ia"]["protocolo"], 999)
        self.assertEqual(res["avaliacao_ia"]["empresa_contatada"], 42)
        self.assertEqual(len(res["avaliacao_criterio"]), 6)

    def test_chamada_ura_nao_avaliavel_forca_null_para_power_bi(self):
        dados = {
            "avaliacao_ia": {
                "resultado": "Dados insuficientes",
                "ligacao_relevante": "s",
                "reuniao_confirmada": "s",
                "data_confirmada": "s",
                "resultado_frase": "URA eletrônica detectada.",
            },
            "avaliacao_sdr": {
                "nota_final": 0,  # Não deve manter zero nem string
                "feedback_geral": "A chamada retrata a fala de uma Unidade de resposta audível (URA)",
                "codigo_oportunidade": "OP_SPIN_03",
            },
            "avaliacao_criterio": [
                {"codigo_criterio": "CRIT_ABERTURA", "criterio": "Abertura", "nota_criterio": 0, "justificativa_criterio": "Sem contexto."},
                {"codigo_criterio": "CRIT_SPIN", "criterio": "SPIN", "nota_criterio": 0, "justificativa_criterio": "Sem contexto."},
                {"codigo_criterio": "CRIT_PERFIL", "criterio": "Perfil", "nota_criterio": 0, "justificativa_criterio": "Sem contexto."},
                {"codigo_criterio": "CRIT_BANT", "criterio": "BANT", "nota_criterio": 0, "justificativa_criterio": "Sem contexto."},
                {"codigo_criterio": "CRIT_ESCUTA", "criterio": "Escuta", "nota_criterio": 0, "justificativa_criterio": "Sem contexto."},
                {"codigo_criterio": "CRIT_PROX_PASSO", "criterio": "Próximo Passo", "nota_criterio": 0, "justificativa_criterio": "Sem contexto."},
            ],
            "crm": {
                "resumo": "URA detectada."
            }
        }

        res = calcular_e_sanitizar_analise(dados)

        # Regra de Ouro do Power BI: notas numéricas como NULL
        self.assertIsNone(res["avaliacao_sdr"]["nota_final"])
        self.assertIsNone(res["avaliacao_sdr"]["codigo_oportunidade"])
        self.assertTrue(res["avaliacao_sdr"]["feedback_geral"].startswith("Não avaliável:"))

        for crit in res["avaliacao_criterio"]:
            self.assertIsNone(crit["nota_criterio"])
            self.assertTrue(crit["justificativa_criterio"].startswith("Não avaliável:"))

        # Flags devem ser 'n' e ação do CRM 'Não se aplica'
        self.assertEqual(res["avaliacao_ia"]["ligacao_relevante"], "n")
        self.assertEqual(res["avaliacao_ia"]["reuniao_confirmada"], "n")
        self.assertEqual(res["avaliacao_ia"]["data_confirmada"], "n")
        self.assertEqual(res["crm"]["acao"], "Não se aplica")

    def test_resumo_crm_limitado_a_80_palavras(self):
        texto_longo = " ".join(["palavra"] * 120)
        dados = {
            "avaliacao_ia": {"resultado": "Perfil pendente"},
            "avaliacao_sdr": {"nota_final": None, "feedback_geral": "Não avaliável: Queda"},
            "avaliacao_criterio": [],
            "crm": {"resumo": texto_longo}
        }

        res = calcular_e_sanitizar_analise(dados)
        palavras_resumo = res["crm"]["resumo"].replace("...", "").split()
        self.assertLessEqual(len(palavras_resumo), 80)

    def test_padronizacao_campos_texto_nao_se_aplica(self):
        dados = {
            "avaliacao_ia": {
                "resultado": "Perfil pendente",
                "interlocutor": "Não houve...",
                "cargo": None,
                "resultado_frase": "Conversa curta sem avanço.",
            },
            "avaliacao_sdr": {
                "nota_final": 50,
                "feedback_geral": "Atendimento básico.",
                "acertos": "não informado",
                "melhorias": None,
                "frase_alternativa": "   ",
                "codigo_oportunidade": "OP_DIR_03",
            },
            "avaliacao_criterio": [
                {"codigo_criterio": "CRIT_ABERTURA", "criterio": "Abertura", "nota_criterio": 10, "justificativa_criterio": "Ok."},
            ],
            "analise_spin": {
                "situacao": "Nenhum",
                "problema": "não houve",
            },
            "analise_bant": {
                "budget_evidencia": "n/a",
            },
            "interlocutor": {
                "duvidas": "null",
                "objecoes": "não se aplica...",
            },
            "crm": {
                "responsavel": "não houve",
                "prazo": None,
            }
        }

        res = calcular_e_sanitizar_analise(dados)

        self.assertEqual(res["avaliacao_ia"]["interlocutor"], "Não se aplica")
        self.assertEqual(res["avaliacao_ia"]["cargo"], "Não se aplica")
        self.assertEqual(res["avaliacao_sdr"]["acertos"], "Não se aplica")
        self.assertEqual(res["avaliacao_sdr"]["melhorias"], "Não se aplica")
        self.assertEqual(res["avaliacao_sdr"]["frase_alternativa"], "Não se aplica")
        self.assertEqual(res["analise_spin"]["situacao"], "Não se aplica")
        self.assertEqual(res["analise_spin"]["problema"], "Não se aplica")
        self.assertEqual(res["analise_bant"]["budget_evidencia"], "Não se aplica")
        self.assertEqual(res["interlocutor"]["duvidas"], "Não se aplica")
        self.assertEqual(res["interlocutor"]["objecoes"], "Não se aplica")
        self.assertEqual(res["crm"]["responsavel"], "Não se aplica")
        self.assertEqual(res["crm"]["prazo"], "Não se aplica")

    def test_normalizacao_acao_crm(self):
        # 1. Reunião confirmada e variações
        self.assertEqual(normalizar_acao_crm("Reunião confirmada"), "Reunião confirmada")
        self.assertEqual(normalizar_acao_crm("Reunião confirmada (apresentação técnica)"), "Reunião confirmada")
        self.assertEqual(normalizar_acao_crm("reuniao confirmada"), "Reunião confirmada")

        # 2. Retorno com data combinada e variações
        self.assertEqual(normalizar_acao_crm("Retorno com data combinada"), "Retorno com data combinada")
        self.assertEqual(normalizar_acao_crm("Retorno com data combinado"), "Retorno com data combinada")
        self.assertEqual(normalizar_acao_crm("Retorno agendado"), "Retorno com data combinada")

        # 3. Recontatar (Follow-up) agregando termos legados e alucinações
        self.assertEqual(normalizar_acao_crm("Recontatar (Follow-up)"), "Recontatar (Follow-up)")
        self.assertEqual(normalizar_acao_crm("Nova Tentativa"), "Recontatar (Follow-up)")
        self.assertEqual(normalizar_acao_crm("Reunião proposta sem aceite"), "Recontatar (Follow-up)")
        self.assertEqual(normalizar_acao_crm("Sem próximo passo definido"), "Recontatar (Follow-up)")
        self.assertEqual(normalizar_acao_crm("Envio de material solicitado"), "Recontatar (Follow-up)")
        self.assertEqual(normalizar_acao_crm(None), "Recontatar (Follow-up)")

        # 4. Sem interesse
        self.assertEqual(normalizar_acao_crm("Sem interesse"), "Sem interesse")
        self.assertEqual(normalizar_acao_crm("Sem interesse explícito"), "Sem interesse")
        self.assertEqual(normalizar_acao_crm("Recusa explícita"), "Sem interesse")

        # 5. Não se aplica
        self.assertEqual(normalizar_acao_crm("Não se aplica"), "Não se aplica")
        self.assertEqual(normalizar_acao_crm("qualquer_coisa", eh_nao_avaliavel=True), "Não se aplica")


if __name__ == "__main__":
    unittest.main()
