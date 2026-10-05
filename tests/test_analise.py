# -*- coding: utf-8 -*-
"""Testes unitários para o módulo de análise comercial via IA (SPIN, BANT, SDR)."""
import unittest

from app.services.analise_final_AI import (
    calcular_e_sanitizar_analise,
    normalizar_acao_crm,
    normalizar_setor,
    normalizar_resultado_status_comercial,
    _limpar_resposta_json,
    SETORES_VALIDOS,
    ACOES_CRM_VALIDAS,
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

    def test_normalizacao_setor(self):
        # 1. Industrial e variações fabris/manufatura
        self.assertEqual(normalizar_setor("industrial"), "industrial")
        self.assertEqual(normalizar_setor("Indústria Metalúrgica"), "industrial")
        self.assertEqual(normalizar_setor("Fábrica de calçados"), "industrial")
        self.assertEqual(normalizar_setor("Usinagem de peças"), "industrial")
        self.assertEqual(normalizar_setor("Química pesada"), "industrial")
        self.assertEqual(normalizar_setor("Indústria"), "industrial")

        # 2. Outro confirmado (serviços, comércio, logística, agro, etc.)
        self.assertEqual(normalizar_setor("outro confirmado"), "outro confirmado")
        self.assertEqual(normalizar_setor("Transporte e Logística"), "outro confirmado")
        self.assertEqual(normalizar_setor("Comércio Varejista"), "outro confirmado")
        self.assertEqual(normalizar_setor("Serviços Financeiros"), "outro confirmado")
        self.assertEqual(normalizar_setor("Agronegócio"), "outro confirmado")

        # 3. Não informado
        self.assertEqual(normalizar_setor("não informado"), "não informado")
        self.assertEqual(normalizar_setor("Não se aplica"), "não informado")
        self.assertEqual(normalizar_setor(""), "não informado")
        self.assertEqual(normalizar_setor(None), "não informado")
        self.assertEqual(normalizar_setor("industrial", eh_nao_avaliavel=True), "não informado")

    def test_normalizacao_acao_crm(self):
        # 1. Reunião confirmada
        self.assertEqual(normalizar_acao_crm("reunião confirmada"), "reunião confirmada")
        self.assertEqual(normalizar_acao_crm("Reunião Confirmada"), "reunião confirmada")
        self.assertEqual(normalizar_acao_crm("Reunião confirmada (apresentação técnica)"), "reunião confirmada")
        self.assertEqual(normalizar_acao_crm("reuniao confirmada"), "reunião confirmada")
        self.assertEqual(normalizar_acao_crm("agendou reunião"), "reunião confirmada")

        # 2. Reunião proposta sem aceite
        self.assertEqual(normalizar_acao_crm("reunião proposta sem aceite"), "reunião proposta sem aceite")
        self.assertEqual(normalizar_acao_crm("Reunião proposta sem aceite"), "reunião proposta sem aceite")
        self.assertEqual(normalizar_acao_crm("Proposta de reunião sem aceite"), "reunião proposta sem aceite")

        # 3. Retorno com data combinado (nova ligação para conversar sobre marcar a reunião)
        self.assertEqual(normalizar_acao_crm("retorno com data combinado"), "retorno com data combinado")
        self.assertEqual(normalizar_acao_crm("Retorno com data combinada"), "retorno com data combinado")
        self.assertEqual(normalizar_acao_crm("Retorno agendado"), "retorno com data combinado")
        self.assertEqual(normalizar_acao_crm("Ligar dia 15 para marcar reunião"), "retorno com data combinado")

        # 4. Envio de material solicitado
        self.assertEqual(normalizar_acao_crm("envio de material solicitado"), "envio de material solicitado")
        self.assertEqual(normalizar_acao_crm("Envio de material"), "envio de material solicitado")
        self.assertEqual(normalizar_acao_crm("Solicitou envio de apresentação"), "envio de material solicitado")

        # 5. Sem próximo passo definido
        self.assertEqual(normalizar_acao_crm("sem próximo passo definido"), "sem próximo passo definido")
        self.assertEqual(normalizar_acao_crm("Sem próximo passo"), "sem próximo passo definido")
        self.assertEqual(normalizar_acao_crm("Recontatar"), "sem próximo passo definido")
        self.assertEqual(normalizar_acao_crm("Follow-up"), "sem próximo passo definido")
        self.assertEqual(normalizar_acao_crm(None), "sem próximo passo definido")

        # 6. Sem interesse explícito
        self.assertEqual(normalizar_acao_crm("sem interesse explícito"), "sem interesse explícito")
        self.assertEqual(normalizar_acao_crm("Sem interesse"), "sem interesse explícito")
        self.assertEqual(normalizar_acao_crm("Recusa explícita"), "sem interesse explícito")
        self.assertEqual(normalizar_acao_crm("Pediu para não ligar mais"), "sem interesse explícito")

        # 7. Não se aplica
        self.assertEqual(normalizar_acao_crm("Não se aplica"), "Não se aplica")
        self.assertEqual(normalizar_acao_crm("qualquer_coisa", eh_nao_avaliavel=True), "Não se aplica")

    def test_normalizacao_resultado_status_comercial(self):
        # 1. Perfil confirmado e contorno de Reunião Agendada/Confirmada
        self.assertEqual(normalizar_resultado_status_comercial("Perfil confirmado"), "Perfil confirmado")
        self.assertEqual(normalizar_resultado_status_comercial("Reunião Agendada"), "Perfil confirmado")
        self.assertEqual(normalizar_resultado_status_comercial("reuniao agendada"), "Perfil confirmado")
        self.assertEqual(normalizar_resultado_status_comercial("Reunião confirmada"), "Perfil confirmado")
        self.assertEqual(normalizar_resultado_status_comercial("qualificado"), "Perfil confirmado")

        # 2. Perfil pendente
        self.assertEqual(normalizar_resultado_status_comercial("Perfil pendente"), "Perfil pendente")
        self.assertEqual(normalizar_resultado_status_comercial("pendente"), "Perfil pendente")
        self.assertEqual(normalizar_resultado_status_comercial("em análise"), "Perfil pendente")

        # 3. Fora do perfil
        self.assertEqual(normalizar_resultado_status_comercial("Fora do perfil desta campanha"), "Fora do perfil desta campanha")
        self.assertEqual(normalizar_resultado_status_comercial("fora do perfil"), "Fora do perfil desta campanha")
        self.assertEqual(normalizar_resultado_status_comercial("desqualificado"), "Fora do perfil desta campanha")

        # 4. Dados insuficientes e chamadas não avaliáveis
        self.assertEqual(normalizar_resultado_status_comercial("Dados insuficientes"), "Dados insuficientes")
        self.assertEqual(normalizar_resultado_status_comercial(None), "Dados insuficientes")
        self.assertEqual(normalizar_resultado_status_comercial("Perfil confirmado", eh_nao_avaliavel=True), "Dados insuficientes")

    def test_sanitizacao_converte_reuniao_agendada_para_perfil_confirmado(self):
        dados = {
            "avaliacao_ia": {
                "resultado": "Reunião Agendada",
                "ligacao_relevante": "s",
                "reuniao_confirmada": "n",
                "data_confirmada": "s",
                "resultado_frase": "Reunião marcada com diretor.",
            },
            "analise_perfil": {
                "setor": "Indústria",
                "setor_origem": "confirmado pelo interlocutor",
                "regime_tributario": "Lucro Real",
                "regime_origem": "confirmado pelo interlocutor",
                "faturamento_mensal": 1500000.0,
                "faturamento_origem": "confirmado pelo interlocutor",
            },
            "avaliacao_sdr": {
                "feedback_geral": "Boa condução.",
                "codigo_oportunidade": "OP_DIR_03",
            },
            "avaliacao_criterio": [
                {"codigo_criterio": "CRIT_ABERTURA", "criterio": "Abertura", "nota_criterio": 10, "justificativa_criterio": "Ok."},
                {"codigo_criterio": "CRIT_SPIN", "criterio": "SPIN", "nota_criterio": 20, "justificativa_criterio": "Ok."},
                {"codigo_criterio": "CRIT_PERFIL", "criterio": "Perfil", "nota_criterio": 20, "justificativa_criterio": "Ok."},
                {"codigo_criterio": "CRIT_BANT", "criterio": "BANT", "nota_criterio": 10, "justificativa_criterio": "Ok."},
                {"codigo_criterio": "CRIT_ESCUTA", "criterio": "Escuta", "nota_criterio": 10, "justificativa_criterio": "Ok."},
                {"codigo_criterio": "CRIT_PROX_PASSO", "criterio": "Próximo Passo", "nota_criterio": 10, "justificativa_criterio": "Ok."},
            ],
            "crm": {"resumo": "Reunião agendada."}
        }
        res = calcular_e_sanitizar_analise(dados)
        self.assertEqual(res["avaliacao_ia"]["resultado"], "Perfil confirmado")
        self.assertEqual(res["avaliacao_ia"]["reuniao_confirmada"], "s")
        self.assertEqual(res["analise_perfil"]["setor"], "industrial")

    def test_calculo_faturamento_mensal_12_meses(self):
        dados = {
            "avaliacao_ia": {"resultado": "Perfil pendente"},
            "analise_perfil": {
                "faturamento_declarado_texto": "24 milhões de faturamento ano passado",
                "faturamento_anual": 24000000.0,
                "periodo_meses": 12,
                "faturamento_origem": "confirmado pelo interlocutor",
                "regime_tributario": "Lucro Real",
                "regime_origem": "confirmado pelo interlocutor",
            },
            "avaliacao_sdr": {"nota_final": 80, "feedback_geral": "Ok"},
            "avaliacao_criterio": [],
            "crm": {"resumo": "Ok"}
        }
        res = calcular_e_sanitizar_analise(dados)
        perfil = res["analise_perfil"]
        self.assertEqual(perfil["faturamento_mensal"], 2000000.0)
        self.assertEqual(perfil["faturamento_origem"], "calculado")
        self.assertEqual(perfil["faturamento_regra"], "calculado_12_meses")
        self.assertIn("calculada deterministicamente", perfil["detalhes_faturamento"])
        # Como Lucro Real foi confirmado e 2M >= 1M calculado, qualifica como Perfil confirmado!
        self.assertEqual(res["avaliacao_ia"]["resultado"], "Perfil confirmado")

    def test_faturamento_periodo_ambiguo_marca_nao_confirmado(self):
        dados = {
            "avaliacao_ia": {"resultado": "Perfil confirmado"},
            "analise_perfil": {
                "faturamento_declarado_texto": "Faturamos 10 milhões em 6 meses",
                "faturamento_anual": 10000000.0,
                "periodo_meses": 6,  # Não são 12 meses
                "faturamento_origem": "confirmado pelo interlocutor",
                "regime_tributario": "Lucro Real",
                "regime_origem": "confirmado pelo interlocutor",
            },
            "avaliacao_sdr": {"nota_final": 80, "feedback_geral": "Ok"},
            "avaliacao_criterio": [],
            "crm": {"resumo": "Ok"}
        }
        res = calcular_e_sanitizar_analise(dados)
        perfil = res["analise_perfil"]
        self.assertIsNone(perfil["faturamento_mensal"])
        self.assertEqual(perfil["faturamento_regra"], "nao_confirmado")
        self.assertEqual(perfil["faturamento_origem"], "não informado")
        # Sem faturamento mensal confirmado de 12 meses, não pode ser Perfil confirmado
        self.assertEqual(res["avaliacao_ia"]["resultado"], "Perfil pendente")

    def test_bloqueio_perfil_confirmado_se_apenas_afirmado_sdr(self):
        dados = {
            "avaliacao_ia": {"resultado": "Perfil confirmado"},
            "analise_perfil": {
                "regime_tributario": "Lucro Real",
                "regime_origem": "afirmado apenas pelo SDR",  # SDR falou sozinho!
                "faturamento_mensal": 2000000.0,
                "faturamento_origem": "confirmado pelo interlocutor",
            },
            "avaliacao_sdr": {"nota_final": 80, "feedback_geral": "Ok"},
            "avaliacao_criterio": [],
            "crm": {"resumo": "Ok"}
        }
        res = calcular_e_sanitizar_analise(dados)
        self.assertEqual(res["avaliacao_ia"]["resultado"], "Perfil pendente")

    def test_bloqueio_perfil_confirmado_se_faturamento_inferido(self):
        dados = {
            "avaliacao_ia": {"resultado": "Perfil confirmado"},
            "analise_perfil": {
                "regime_tributario": "Lucro Real",
                "regime_origem": "confirmado pelo interlocutor",
                "faturamento_mensal": 3000000.0,
                "faturamento_origem": "inferência plausível",  # Mera inferência!
            },
            "avaliacao_sdr": {"nota_final": 80, "feedback_geral": "Ok"},
            "avaliacao_criterio": [],
            "crm": {"resumo": "Ok"}
        }
        res = calcular_e_sanitizar_analise(dados)
        self.assertEqual(res["avaliacao_ia"]["resultado"], "Perfil pendente")

    def test_fora_do_perfil_se_simples_nacional_confirmado(self):
        dados = {
            "avaliacao_ia": {"resultado": "Perfil pendente"},
            "analise_perfil": {
                "regime_tributario": "Simples Nacional",
                "regime_origem": "confirmado pelo interlocutor",
                "faturamento_mensal": 200000.0,
                "faturamento_origem": "confirmado pelo interlocutor",
            },
            "avaliacao_sdr": {"nota_final": 80, "feedback_geral": "Ok"},
            "avaliacao_criterio": [],
            "crm": {"resumo": "Ok"}
        }
        res = calcular_e_sanitizar_analise(dados)
        self.assertEqual(res["avaliacao_ia"]["resultado"], "Fora do perfil desta campanha")

    def test_fora_do_perfil_se_faturamento_confirmado_abaixo_minimo(self):
        dados = {
            "avaliacao_ia": {"resultado": "Perfil pendente"},
            "analise_perfil": {
                "regime_tributario": "Lucro Real",
                "regime_origem": "confirmado pelo interlocutor",
                "faturamento_mensal": 450000.0,  # Abaixo de 1M
                "faturamento_origem": "confirmado pelo interlocutor",
            },
            "avaliacao_sdr": {"nota_final": 80, "feedback_geral": "Ok"},
            "avaliacao_criterio": [],
            "crm": {"resumo": "Ok"}
        }
        res = calcular_e_sanitizar_analise(dados)
        self.assertEqual(res["avaliacao_ia"]["resultado"], "Fora do perfil desta campanha")


if __name__ == "__main__":
    unittest.main()
