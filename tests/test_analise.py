# -*- coding: utf-8 -*-
"""Testes unitários para o módulo de análise comercial via IA (SPIN, BANT, SDR)."""
from datetime import date
import unittest

from app.services.analise_final_AI import (
    calcular_e_sanitizar_analise,
    derivar_data_confirmada,
    derivar_conversa_decisor,
    derivar_spin_investigado,
    normalizar_acao_crm,
    normalizar_setor,
    normalizar_resultado_status_comercial,
    normalizar_prazo_data_timestamp,
    _limpar_resposta_json,
    AnaliseCompletaModel,
    AnaliseSpinModel,
    AvaliacaoSDRModel,
    CrmModel,
    SETORES_VALIDOS,
    ACOES_CRM_VALIDAS,
    MODELO_ANALISE,
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

    def test_ligacao_nao_relevante_forca_notas_null_para_power_bi(self):
        # Toda ligação não relevante (ligacao_relevante = 'n') deve ter notas estritamente NULL
        dados = {
            "avaliacao_ia": {
                "resultado": "Dados insuficientes",
                "ligacao_relevante": "n",
                "reuniao_confirmada": "n",
                "data_confirmada": "n",
                "resultado_frase": "Sem diálogo substantivo.",
            },
            "avaliacao_sdr": {
                "nota_final": 0,
                "feedback_geral": "Chamada curta sem atendimento.",
                "codigo_oportunidade": "OP_DIR_03",
            },
            "avaliacao_criterio": [
                {"codigo_criterio": "CRIT_ABERTURA", "criterio": "Abertura", "nota_criterio": 0, "justificativa_criterio": "Sem diálogo."},
                {"codigo_criterio": "CRIT_SPIN", "criterio": "SPIN", "nota_criterio": 0, "justificativa_criterio": "Sem diálogo."},
                {"codigo_criterio": "CRIT_PERFIL", "criterio": "Perfil", "nota_criterio": 0, "justificativa_criterio": "Sem diálogo."},
                {"codigo_criterio": "CRIT_BANT", "criterio": "BANT", "nota_criterio": 0, "justificativa_criterio": "Sem diálogo."},
                {"codigo_criterio": "CRIT_ESCUTA", "criterio": "Escuta", "nota_criterio": 0, "justificativa_criterio": "Sem diálogo."},
                {"codigo_criterio": "CRIT_PROX_PASSO", "criterio": "Próximo Passo", "nota_criterio": 0, "justificativa_criterio": "Sem diálogo."},
            ],
            "crm": {"resumo": "Não se aplica"}
        }

        res = calcular_e_sanitizar_analise(dados)

        self.assertIsNone(res["avaliacao_sdr"]["nota_final"])
        self.assertIsNone(res["avaliacao_sdr"]["codigo_oportunidade"])
        self.assertTrue(res["avaliacao_sdr"]["feedback_geral"].startswith("Não avaliável:"))
        for crit in res["avaliacao_criterio"]:
            self.assertIsNone(crit["nota_criterio"])
            self.assertTrue(crit["justificativa_criterio"].startswith("Não avaliável:"))
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
        self.assertEqual(perfil["faturamento_origem"], "confirmado pelo interlocutor")
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

    def test_recepcao_nao_avaliavel_com_retorno_agendado_preserva_crm_e_perfil_pendente(self):
        # Regra 6 do PDF: chamada com secretária/recepcionista
        # SDR não é avaliado (notas NULL), mas o próximo passo do CRM deve ser preservado e resultado = Perfil pendente
        dados = {
            "avaliacao_ia": {
                "resultado": "Dados insuficientes",
                "ligacao_relevante": "n",
                "reuniao_confirmada": "n",
                "data_confirmada": "s",
                "resultado_frase": "Recepcionista pediu para retornar amanhã às 14h com o decisor.",
            },
            "avaliacao_sdr": {
                "feedback_geral": "Não avaliável: Atendido por recepcionista, decisor ausente.",
                "nota_final": None,
                "codigo_oportunidade": None,
            },
            "avaliacao_criterio": [],
            "crm": {
                "acao": "retorno com data combinado",
                "prazo": "amanhã às 14:00",
                "responsavel": "SDR",
                "resumo": "Recepcionista informou que o diretor só atende amanhã às 14h.",
            },
        }

        res = calcular_e_sanitizar_analise(dados)

        # SDR continua não avaliável (proteção Power BI)
        self.assertIsNone(res["avaliacao_sdr"]["nota_final"])
        self.assertIsNone(res["avaliacao_sdr"]["codigo_oportunidade"])
        for crit in res["avaliacao_criterio"]:
            self.assertIsNone(crit["nota_criterio"])

        # CRM e status comercial devem preservar o avanço
        self.assertEqual(res["crm"]["acao"], "retorno com data combinado")
        self.assertEqual(res["crm"]["prazo"], "amanhã às 14:00")
        self.assertEqual(res["avaliacao_ia"]["resultado"], "Perfil pendente")
        self.assertEqual(res["avaliacao_ia"]["ligacao_relevante"], "s")

    def test_recepcao_nao_avaliavel_com_envio_material_preserva_crm_e_perfil_pendente(self):
        dados = {
            "avaliacao_ia": {
                "resultado": "Dados insuficientes",
                "ligacao_relevante": "n",
                "resultado_frase": "Secretária solicitou apresentação comercial por e-mail.",
            },
            "avaliacao_sdr": {
                "feedback_geral": "Não avaliável: Conversa apenas com secretária.",
                "nota_final": None,
            },
            "avaliacao_criterio": [],
            "crm": {
                "acao": "envio de material solicitado",
                "prazo": "Não se aplica",
                "resumo": "Encaminhar portfólio para diretoria.",
            },
        }

        res = calcular_e_sanitizar_analise(dados)

        self.assertIsNone(res["avaliacao_sdr"]["nota_final"])
        self.assertEqual(res["crm"]["acao"], "envio de material solicitado")
        self.assertEqual(res["avaliacao_ia"]["resultado"], "Perfil pendente")
        self.assertEqual(res["avaliacao_ia"]["ligacao_relevante"], "s")

    def test_recepcao_sem_proximo_passo_marca_nao_relevante(self):
        dados = {
            "avaliacao_ia": {
                "resultado": "Dados insuficientes",
                "ligacao_relevante": "n",
                "resultado_frase": "Secretária informou que o responsável não estava e não aceitou recado.",
            },
            "avaliacao_sdr": {
                "feedback_geral": "Não avaliável: Atendimento encerrou na recepção sem retorno.",
                "nota_final": None,
            },
            "avaliacao_criterio": [],
            "crm": {
                "acao": "Não se aplica",
                "prazo": "Não se aplica",
                "resumo": "Não se aplica",
            },
        }

        res = calcular_e_sanitizar_analise(dados)

        self.assertIsNone(res["avaliacao_sdr"]["nota_final"])
        self.assertEqual(res["crm"]["acao"], "Não se aplica")
        self.assertEqual(res["avaliacao_ia"]["resultado"], "Dados insuficientes")
        self.assertEqual(res["avaliacao_ia"]["ligacao_relevante"], "n")

    def test_feedback_com_palavras_contendo_ura_nao_dispara_falso_positivo(self):
        # A palavra "abertura" ou "postura" não deve disparar detecção de URA se a ligação for avaliável
        dados = {
            "avaliacao_ia": {
                "resultado": "Perfil confirmado",
                "ligacao_relevante": "s",
                "resultado_frase": "Boa postura do atendente.",
            },
            "avaliacao_sdr": {
                "nota_final": 75,
                "feedback_geral": "Excelente postura profissional e abertura clara na abordagem.",
                "codigo_oportunidade": "OP_ABERT_01",
            },
            "avaliacao_criterio": [
                {"codigo_criterio": "CRIT_ABERTURA", "criterio": "Abertura", "nota_criterio": 10, "justificativa_criterio": "Boa postura."},
                {"codigo_criterio": "CRIT_SPIN", "criterio": "SPIN", "nota_criterio": 20, "justificativa_criterio": "Estrutura adequada."},
                {"codigo_criterio": "CRIT_PERFIL", "criterio": "Perfil", "nota_criterio": 20, "justificativa_criterio": "Ok."},
                {"codigo_criterio": "CRIT_BANT", "criterio": "BANT", "nota_criterio": 10, "justificativa_criterio": "Ok."},
                {"codigo_criterio": "CRIT_ESCUTA", "criterio": "Escuta", "nota_criterio": 8, "justificativa_criterio": "Ok."},
                {"codigo_criterio": "CRIT_PROX_PASSO", "criterio": "Próximo Passo", "nota_criterio": 7, "justificativa_criterio": "Ok."},
            ],
            "crm": {"resumo": "Ok"}
        }

        res = calcular_e_sanitizar_analise(dados)
        self.assertEqual(res["avaliacao_sdr"]["nota_final"], 75)
        self.assertEqual(res["avaliacao_ia"]["ligacao_relevante"], "s")

        # Boundary test: palavra "ura" isolada (ex: "caiu na URA") DEVE disparar URA quando notas zeradas/ausentes
        dados_ura = {
            "avaliacao_ia": {
                "resultado": "Dados insuficientes",
                "ligacao_relevante": "s",
                "resultado_frase": "Caiu na URA eletrônica.",
            },
            "avaliacao_sdr": {
                "nota_final": 0,
                "feedback_geral": "Chamada caiu na URA eletrônica sem atendimento humano.",
            },
            "avaliacao_criterio": [],
            "crm": {"acao": "Não se aplica"},
        }
        res_ura = calcular_e_sanitizar_analise(dados_ura)
        self.assertIsNone(res_ura["avaliacao_sdr"]["nota_final"])
        self.assertEqual(res_ura["avaliacao_ia"]["ligacao_relevante"], "n")
        self.assertEqual(res_ura["avaliacao_ia"]["resultado"], "Dados insuficientes")

    def test_sobrescrita_incondicional_metadados_sistema(self):
        dados = {
            "avaliacao_ia": {
                "protocolo": 123456789,      # Do exemplo de prompt
                "empresa_contatada": 1054,    # Do exemplo de prompt
                "data_avaliacao": "2020-01-01",
                "modelo_ia": "modelo_fantasia",
                "resultado": "Perfil pendente",
            },
            "avaliacao_sdr": {"nota_final": 50, "feedback_geral": "Ok"},
            "avaliacao_criterio": [],
            "crm": {"resumo": "Ok"},
        }

        res = calcular_e_sanitizar_analise(dados, protocolo=98765, empresa_contatada=55)

        self.assertEqual(res["avaliacao_ia"]["protocolo"], 98765)
        self.assertEqual(res["avaliacao_ia"]["empresa_contatada"], 55)
        self.assertEqual(res["avaliacao_ia"]["data_avaliacao"], str(date.today()))
        self.assertEqual(res["avaliacao_ia"]["modelo_ia"], MODELO_ANALISE)

        # Se empresa_contatada não for informada pelo chamador, NUNCA mantém o 1054 alucinado
        dados2 = {
            "avaliacao_ia": {
                "empresa_contatada": 1054,
                "resultado": "Perfil pendente",
            },
            "avaliacao_sdr": {"nota_final": 50, "feedback_geral": "Ok"},
            "avaliacao_criterio": [],
            "crm": {"resumo": "Ok"},
        }
        res2 = calcular_e_sanitizar_analise(dados2, empresa_contatada=None)
        self.assertIsNone(res2["avaliacao_ia"]["empresa_contatada"])

    def test_teto_por_criterio_respeita_max_pontos(self):
        # Cada critério oficial possui um teto específico que não pode ser ultrapassado:
        # ABERTURA: 10, SPIN: 30, PERFIL: 25, BANT: 15, ESCUTA: 10, PROX_PASSO: 10
        # Exemplo específico: nota 20 em abertura vira 10
        dados = {
            "avaliacao_ia": {
                "resultado": "Perfil confirmado",
                "ligacao_relevante": "s",
                "reuniao_confirmada": "s",
                "data_confirmada": "s",
                "resultado_frase": "Reunião confirmada.",
            },
            "avaliacao_sdr": {
                "feedback_geral": "Atendimento com pontuações infladas pelo modelo.",
                "codigo_oportunidade": "OP_SPIN_01",
            },
            "avaliacao_criterio": [
                {"codigo_criterio": "CRIT_ABERTURA", "criterio": "Abertura", "nota_criterio": 20, "justificativa_criterio": "Ok"}, # Nota 20 vira 10
                {"codigo_criterio": "CRIT_SPIN", "criterio": "SPIN", "nota_criterio": 50, "justificativa_criterio": "Ok"},         # Nota 50 vira 30
                {"codigo_criterio": "CRIT_PERFIL", "criterio": "Perfil", "nota_criterio": 30, "justificativa_criterio": "Ok"},     # Nota 30 vira 25
                {"codigo_criterio": "CRIT_BANT", "criterio": "BANT", "nota_criterio": 25, "justificativa_criterio": "Ok"},         # Nota 25 vira 15
                {"codigo_criterio": "CRIT_ESCUTA", "criterio": "Escuta", "nota_criterio": 20, "justificativa_criterio": "Ok"},     # Nota 20 vira 10
                {"codigo_criterio": "CRIT_PROX_PASSO", "criterio": "Próximo Passo", "nota_criterio": 15, "justificativa_criterio": "Ok"}, # Nota 15 vira 10
            ],
            "crm": {"resumo": "Ok"}
        }

        res = calcular_e_sanitizar_analise(dados)

        criterios_dict = {c["codigo_criterio"]: c["nota_criterio"] for c in res["avaliacao_criterio"]}
        self.assertEqual(criterios_dict["CRIT_ABERTURA"], 10)   # Nota 20 limitada a max 10
        self.assertEqual(criterios_dict["CRIT_SPIN"], 30)       # Limitado a max 30
        self.assertEqual(criterios_dict["CRIT_PERFIL"], 25)     # Limitado a max 25
        self.assertEqual(criterios_dict["CRIT_BANT"], 15)       # Limitado a max 15
        self.assertEqual(criterios_dict["CRIT_ESCUTA"], 10)     # Limitado a max 10
        self.assertEqual(criterios_dict["CRIT_PROX_PASSO"], 10) # Limitado a max 10

        # Soma total não pode passar de 100
        self.assertEqual(res["avaliacao_sdr"]["nota_final"], 100)

    def test_deduplicacao_de_criterios_duplicados(self):
        # Se a IA devolver códigos repetidos, deve manter apenas o primeiro e preencher os ausentes
        dados = {
            "avaliacao_ia": {
                "resultado": "Perfil confirmado",
                "ligacao_relevante": "s",
                "reuniao_confirmada": "s",
                "data_confirmada": "s",
                "resultado_frase": "Reunião confirmada.",
            },
            "avaliacao_sdr": {
                "feedback_geral": "Resposta com critérios duplicados.",
                "codigo_oportunidade": "OP_ABERT_01",
            },
            "avaliacao_criterio": [
                {"codigo_criterio": "CRIT_ABERTURA", "criterio": "Abertura 1", "nota_criterio": 8, "justificativa_criterio": "Primeira"},
                {"codigo_criterio": "CRIT_ABERTURA", "criterio": "Abertura 2", "nota_criterio": 10, "justificativa_criterio": "Duplicada"},
                {"codigo_criterio": "CRIT_PERFIL", "criterio": "Perfil", "nota_criterio": 20, "justificativa_criterio": "Ok"},
            ],
            "crm": {"resumo": "Ok"}
        }

        res = calcular_e_sanitizar_analise(dados)

        # Deve conter exatamente os 6 critérios oficiais únicos
        self.assertEqual(len(res["avaliacao_criterio"]), 6)
        codigos = [c["codigo_criterio"] for c in res["avaliacao_criterio"]]
        self.assertEqual(len(set(codigos)), 6)
        self.assertEqual(codigos, [
            "CRIT_ABERTURA", "CRIT_SPIN", "CRIT_PERFIL", "CRIT_BANT", "CRIT_ESCUTA", "CRIT_PROX_PASSO"
        ])

        criterios_dict = {c["codigo_criterio"]: c["nota_criterio"] for c in res["avaliacao_criterio"]}
        self.assertEqual(criterios_dict["CRIT_ABERTURA"], 8)  # Manteve o primeiro, descartou a duplicata
        self.assertEqual(criterios_dict["CRIT_PERFIL"], 20)
        self.assertIsNone(criterios_dict["CRIT_SPIN"])        # Criado como None pois estava ausente

        # Como soma dos tetos avaliados (10 + 25 = 35) < 50 (piso mínimo), nota_final global fica None
        self.assertIsNone(res["avaliacao_sdr"]["nota_final"])

    def test_bant_normalizado(self):
        dados = {
            "avaliacao_ia": {
                "resultado": "Perfil confirmado",
                "ligacao_relevante": "s",
            },
            "avaliacao_sdr": {"nota_final": 80, "feedback_geral": "Boa condução."},
            "avaliacao_criterio": [],
            "analise_bant": {
                "budget_classificacao": "Confirmado",      # Variação com maiúscula -> confirmado
                "budget_evidencia": "  ",                  # String vazia/espaços -> Não se aplica
                "authority_classificacao": "indicio",      # Sem acento -> indício
                "authority_evidencia": None,               # None -> Não se aplica
                "need_classificacao": "não",               # Sinônimo negativo -> negado
                "need_evidencia": "Prospect afirmou não ter dores fiscais.",
                "timeline_classificacao": "n/a",           # Sem valor -> não informado
                "timeline_evidencia": "não houve",         # Informal -> Não se aplica
            },
            "crm": {"resumo": "Ok"},
        }

        res = calcular_e_sanitizar_analise(dados)
        bant = res["analise_bant"]

        self.assertEqual(bant["budget_classificacao"], "confirmado")
        self.assertEqual(bant["budget_evidencia"], "Não se aplica")
        self.assertEqual(bant["authority_classificacao"], "indício")
        self.assertEqual(bant["authority_evidencia"], "Não se aplica")
        self.assertEqual(bant["need_classificacao"], "negado")
        self.assertEqual(bant["need_evidencia"], "Prospect afirmou não ter dores fiscais.")
        self.assertEqual(bant["timeline_classificacao"], "não informado")
        self.assertEqual(bant["timeline_evidencia"], "Não se aplica")

    def test_faturamento_anual_afirmado_sdr_nao_confirma_perfil(self):
        """Faturamento afirmado apenas pelo SDR calcula mensal mas NÃO qualifica Perfil confirmado."""
        dados = {
            "avaliacao_ia": {"resultado": "Perfil confirmado", "ligacao_relevante": "s"},
            "analise_perfil": {
                "faturamento_declarado_texto": "Vocês faturam 24 milhões ano passado, certo?",
                "faturamento_anual": 24000000.0,
                "periodo_meses": 12,
                "faturamento_origem": "afirmado apenas pelo SDR",
                "regime_tributario": "Lucro Real",
                "regime_origem": "confirmado pelo interlocutor",
            },
            "avaliacao_sdr": {"nota_final": 80, "feedback_geral": "Ok"},
            "avaliacao_criterio": [],
            "crm": {"resumo": "Ok"},
        }
        res = calcular_e_sanitizar_analise(dados)
        perfil = res["analise_perfil"]
        self.assertEqual(perfil["faturamento_mensal"], 2000000.0)
        self.assertEqual(perfil["faturamento_origem"], "afirmado apenas pelo SDR")
        self.assertEqual(perfil["faturamento_regra"], "calculado_12_meses")
        # Não pode virar Perfil confirmado pois o faturamento não foi confirmado pelo lead!
        self.assertEqual(res["avaliacao_ia"]["resultado"], "Perfil pendente")

    def test_normalizacao_proporcional_nota_final(self):
        """Testa que 4 critérios avaliados somando 62/75 normalizam para nota_final = 83."""
        dados = {
            "avaliacao_ia": {"resultado": "Perfil pendente", "ligacao_relevante": "s"},
            "avaliacao_sdr": {"nota_final": None, "feedback_geral": "Boa condução parcial."},
            "avaliacao_criterio": [
                {"codigo_criterio": "CRIT_ABERTURA", "nota_criterio": 9},    # teto 10
                {"codigo_criterio": "CRIT_SPIN", "nota_criterio": 25},        # teto 30
                {"codigo_criterio": "CRIT_PERFIL", "nota_criterio": 20},      # teto 25
                {"codigo_criterio": "CRIT_PROX_PASSO", "nota_criterio": 8},   # teto 10
                # CRIT_BANT (15) e CRIT_ESCUTA (10) ausentes -> soma_tetos = 75, soma_obtida = 62
            ],
            "crm": {"resumo": "Ok"},
        }
        res = calcular_e_sanitizar_analise(dados)
        # 62 / 75 * 100 = 82.666... -> round -> 83
        self.assertEqual(res["avaliacao_sdr"]["nota_final"], 83)

        # Critérios ausentes devem permanecer com nota None
        crit_map = {c["codigo_criterio"]: c["nota_criterio"] for c in res["avaliacao_criterio"]}
        self.assertEqual(crit_map["CRIT_ABERTURA"], 9)
        self.assertEqual(crit_map["CRIT_SPIN"], 25)
        self.assertEqual(crit_map["CRIT_PERFIL"], 20)
        self.assertEqual(crit_map["CRIT_PROX_PASSO"], 8)
        self.assertIsNone(crit_map["CRIT_BANT"])
        self.assertIsNone(crit_map["CRIT_ESCUTA"])

    def test_normalizacao_proporcional_abaixo_piso_fica_null(self):
        """Chamada avaliável com soma de tetos < 50 pontos não gera nota_final global (fica None)."""
        dados = {
            "avaliacao_ia": {"resultado": "Perfil pendente", "ligacao_relevante": "s"},
            "avaliacao_sdr": {"nota_final": None, "feedback_geral": "Chamada breve com decisor."},
            "avaliacao_criterio": [
                {"codigo_criterio": "CRIT_ABERTURA", "nota_criterio": 9},  # teto 10
                {"codigo_criterio": "CRIT_ESCUTA", "nota_criterio": 8},    # teto 10 -> soma_tetos = 20 (< 50)
            ],
            "crm": {"resumo": "Ok"},
        }
        res = calcular_e_sanitizar_analise(dados)
        # Como soma_tetos = 20 < 50, nota_final é None para não gerar um falso 85/100
        self.assertIsNone(res["avaliacao_sdr"]["nota_final"])

        # Mas as notas individuais nos critérios existem para fins de coaching
        crit_map = {c["codigo_criterio"]: c["nota_criterio"] for c in res["avaliacao_criterio"]}
        self.assertEqual(crit_map["CRIT_ABERTURA"], 9)
        self.assertEqual(crit_map["CRIT_ESCUTA"], 8)

    def test_codigo_oportunidade_op_esc_04_e_invalido_vira_none(self):
        """OP_ESC_04 ou código inexistente vira None (sem código inventado)."""
        dados1 = {
            "avaliacao_ia": {"resultado": "Perfil pendente", "ligacao_relevante": "s"},
            "avaliacao_sdr": {"nota_final": 70, "codigo_oportunidade": "OP_ESC_04", "feedback_geral": "Ok"},
            "avaliacao_criterio": [],
            "crm": {"resumo": "Ok"},
        }
        res1 = calcular_e_sanitizar_analise(dados1)
        self.assertIsNone(res1["avaliacao_sdr"]["codigo_oportunidade"])

        dados2 = {
            "avaliacao_ia": {"resultado": "Perfil pendente", "ligacao_relevante": "s"},
            "avaliacao_sdr": {"nota_final": 70, "codigo_oportunidade": "OP_CODIGO_INEXISTENTE", "feedback_geral": "Ok"},
            "avaliacao_criterio": [],
            "crm": {"resumo": "Ok"},
        }
        res2 = calcular_e_sanitizar_analise(dados2)
        self.assertIsNone(res2["avaliacao_sdr"]["codigo_oportunidade"])

    def test_derivar_data_confirmada_helper_casos_exaustivos(self):
        """Valida os 10 casos do helper derivar_data_confirmada."""
        self.assertEqual(derivar_data_confirmada("reunião confirmada", "amanhã às 14h"), "s")
        self.assertEqual(derivar_data_confirmada("reunião confirmada", "a definir"), "n")
        self.assertEqual(derivar_data_confirmada("reunião confirmada", "sem data"), "n")
        self.assertEqual(derivar_data_confirmada("reunião confirmada", "não definido"), "n")
        self.assertEqual(derivar_data_confirmada("reunião confirmada", "indefinido"), "n")
        self.assertEqual(derivar_data_confirmada("reunião confirmada", None), "n")
        self.assertEqual(derivar_data_confirmada("retorno com data combinado", "sexta-feira às 10h"), "s")
        self.assertEqual(derivar_data_confirmada("retorno com data combinado", ""), "n")
        self.assertEqual(derivar_data_confirmada("retorno com data combinado", "não informado"), "n")
        self.assertEqual(derivar_data_confirmada("envio de material solicitado", "até amanhã"), "n")
        self.assertEqual(derivar_data_confirmada("sem próximo passo definido", "dia 15"), "n")

    def test_alucinacao_data_confirmada_s_sem_prazo_forca_n(self):
        """Se o LLM disser data_confirmada='s' mas o prazo for vazio/a definir, sanitizador força 'n'."""
        dados = {
            "avaliacao_ia": {
                "resultado": "Perfil pendente",
                "ligacao_relevante": "s",
                "data_confirmada": "s",  # Alucinação da IA!
            },
            "avaliacao_sdr": {"nota_final": 80, "feedback_geral": "Ok"},
            "avaliacao_criterio": [],
            "crm": {
                "acao": "reunião confirmada",
                "prazo": "a definir",  # Prazo vazio/indefinido
                "resumo": "Ok",
            },
        }
        res = calcular_e_sanitizar_analise(dados)
        self.assertEqual(res["avaliacao_ia"]["data_confirmada"], "n")

    def test_envio_material_com_prazo_em_recepcao_gera_data_confirmada_n(self):
        """Envio de material na recepção com prazo não é compromisso de agenda -> data_confirmada='n'."""
        dados = {
            "avaliacao_ia": {"resultado": "Dados insuficientes", "ligacao_relevante": "n"},
            "avaliacao_sdr": {"nota_final": None, "feedback_geral": "Não avaliável: Recepção"},
            "avaliacao_criterio": [],
            "crm": {
                "acao": "envio de material solicitado",
                "prazo": "até sexta",
                "resumo": "Enviar apresentação.",
            },
        }
        res = calcular_e_sanitizar_analise(dados)
        self.assertEqual(res["avaliacao_ia"]["ligacao_relevante"], "s")
        self.assertEqual(res["avaliacao_ia"]["resultado"], "Perfil pendente")
        self.assertEqual(res["avaliacao_ia"]["data_confirmada"], "n")
        self.assertEqual(res["avaliacao_ia"]["reuniao_confirmada"], "n")

    def test_pydantic_analise_completa_valida_unicidade_6_criterios(self):
        """Garante que AnaliseCompletaModel rejeita repetição de códigos de critérios."""
        from pydantic import ValidationError

        payload_duplicado = {
            "avaliacao_ia": {
                "resultado": "Perfil pendente",
                "ligacao_relevante": "s",
                "reuniao_confirmada": "n",
                "data_confirmada": "n",
                "resultado_frase": "Teste",
            },
            "analise_perfil": {},
            "analise_spin": {},
            "analise_bant": {},
            "avaliacao_sdr": {"feedback_geral": "Teste"},
            "avaliacao_criterio": [
                {"codigo_criterio": "CRIT_ABERTURA", "criterio": "Abertura", "justificativa_criterio": "ok"},
                {"codigo_criterio": "CRIT_SPIN", "criterio": "SPIN 1", "justificativa_criterio": "ok"},
                {"codigo_criterio": "CRIT_SPIN", "criterio": "SPIN 2 duplicado!", "justificativa_criterio": "ok"},  # Duplicado!
                {"codigo_criterio": "CRIT_BANT", "criterio": "BANT", "justificativa_criterio": "ok"},
                {"codigo_criterio": "CRIT_ESCUTA", "criterio": "Escuta", "justificativa_criterio": "ok"},
                {"codigo_criterio": "CRIT_PROX_PASSO", "criterio": "Próximo Passo", "justificativa_criterio": "ok"},
                # Faltou CRIT_PERFIL!
            ],
            "interlocutor": {},
            "crm": {},
        }

        with self.assertRaises(ValidationError) as ctx:
            AnaliseCompletaModel.model_validate(payload_duplicado)
        self.assertIn("CRIT_PERFIL", str(ctx.exception))

    def test_pydantic_analise_completa_aceita_6_criterios_unicos(self):
        """Garante que AnaliseCompletaModel aceita os 6 critérios oficiais únicos."""
        payload_valido = {
            "avaliacao_ia": {
                "resultado": "Perfil pendente",
                "ligacao_relevante": "s",
                "reuniao_confirmada": "n",
                "data_confirmada": "n",
                "resultado_frase": "Teste",
            },
            "analise_perfil": {},
            "analise_spin": {},
            "analise_bant": {},
            "avaliacao_sdr": {"feedback_geral": "Teste"},
            "avaliacao_criterio": [
                {"codigo_criterio": "CRIT_ABERTURA", "criterio": "Abertura", "justificativa_criterio": "ok"},
                {"codigo_criterio": "CRIT_SPIN", "criterio": "SPIN", "justificativa_criterio": "ok"},
                {"codigo_criterio": "CRIT_PERFIL", "criterio": "Perfil", "justificativa_criterio": "ok"},
                {"codigo_criterio": "CRIT_BANT", "criterio": "BANT", "justificativa_criterio": "ok"},
                {"codigo_criterio": "CRIT_ESCUTA", "criterio": "Escuta", "justificativa_criterio": "ok"},
                {"codigo_criterio": "CRIT_PROX_PASSO", "criterio": "Próximo Passo", "justificativa_criterio": "ok"},
            ],
            "interlocutor": {},
            "crm": {},
        }
        modelo = AnaliseCompletaModel.model_validate(payload_valido)
        self.assertEqual(len(modelo.avaliacao_criterio), 6)

    def test_derivar_conversa_decisor_decisores_e_influenciadores(self):
        """Valida que Diretor, Sócio, Controller, Gerente Fiscal e Contador viram conversa_decisor='s'."""
        self.assertEqual(derivar_conversa_decisor("Diretor Financeiro"), "s")
        self.assertEqual(derivar_conversa_decisor("Sócio Proprietário"), "s")
        self.assertEqual(derivar_conversa_decisor("CEO"), "s")
        self.assertEqual(derivar_conversa_decisor("Controller"), "s")
        self.assertEqual(derivar_conversa_decisor("Gerente Fiscal e Tributário"), "s")
        self.assertEqual(derivar_conversa_decisor("Contador"), "s")
        self.assertEqual(derivar_conversa_decisor("Coordenadora Financeira"), "s")

    def test_derivar_conversa_decisor_gatekeepers_e_vazios(self):
        """Valida que Secretária, Recepção, Atendente e cargos vazios viram conversa_decisor='n'."""
        self.assertEqual(derivar_conversa_decisor("Secretária"), "n")
        self.assertEqual(derivar_conversa_decisor("Recepcionista"), "n")
        self.assertEqual(derivar_conversa_decisor("Telefonista"), "n")
        self.assertEqual(derivar_conversa_decisor("Atendente da Portaria"), "n")
        self.assertEqual(derivar_conversa_decisor("Não se aplica"), "n")
        self.assertEqual(derivar_conversa_decisor(None), "n")

    def test_chamada_transferida_recepcao_para_diretor_marca_conversa_decisor_s(self):
        """Chamada que capturou cargo mais alto (Diretor Financeiro) marca conversa_decisor='s'."""
        dados = {
            "avaliacao_ia": {
                "interlocutor": "Carlos Eduardo",
                "cargo": "Diretor Financeiro",
                "resultado": "Perfil confirmado",
                "ligacao_relevante": "s",
                "reuniao_confirmada": "s",
                "data_confirmada": "s",
                "conversa_decisor": "s",
            },
            "avaliacao_sdr": {"nota_final": 85, "feedback_geral": "Ótima condução com decisor."},
            "avaliacao_criterio": [],
            "analise_bant": {"authority_classificacao": "confirmado"},
            "crm": {"acao": "reunião confirmada", "prazo": "Amanhã às 14h", "resumo": "Ok"},
        }
        res = calcular_e_sanitizar_analise(dados)
        self.assertEqual(res["avaliacao_ia"]["conversa_decisor"], "s")

    def test_chamada_retida_recepcao_com_retorno_marca_conversa_decisor_n(self):
        """Chamada que parou na secretária com agendamento de retorno marca conversa_decisor='n'."""
        dados = {
            "avaliacao_ia": {
                "interlocutor": "Mariana",
                "cargo": "Secretária da Diretoria",
                "resultado": "Dados insuficientes",
                "ligacao_relevante": "n",
            },
            "avaliacao_sdr": {"nota_final": None, "feedback_geral": "Não avaliável: Parou na recepção."},
            "avaliacao_criterio": [],
            "crm": {
                "acao": "retorno com data combinado",
                "prazo": "Sexta às 10h",
                "resumo": "Retornar com decisor.",
            },
        }
        res = calcular_e_sanitizar_analise(dados)
        self.assertEqual(res["avaliacao_ia"]["ligacao_relevante"], "s")
        self.assertEqual(res["avaliacao_ia"]["conversa_decisor"], "n")

    def test_derivar_spin_investigado_cenarios(self):
        """Valida a derivação determinística das flags de investigação SPIN."""
        # Conteúdo substantivo com confirmação
        self.assertEqual(derivar_spin_investigado("Empresa na indústria metalúrgica", "s", False), "s")
        # Conteúdo substantivo sem flag explícita (fallback seguro/legado)
        self.assertEqual(derivar_spin_investigado("Relatou problemas fiscais", None, False), "s")
        # Flag negativa explícita da IA preservada
        self.assertEqual(derivar_spin_investigado("SDR não abordou este ponto", "n", False), "n")
        self.assertEqual(derivar_spin_investigado("SDR não abordou", "nao", False), "n")
        # Textos vazios / Não se aplica forçam 'n' mesmo se IA sugerir 's'
        self.assertEqual(derivar_spin_investigado("Não se aplica", "s", False), "n")
        self.assertEqual(derivar_spin_investigado("não informado", "s", False), "n")
        self.assertEqual(derivar_spin_investigado("nenhum", "s", False), "n")
        self.assertEqual(derivar_spin_investigado("", "s", False), "n")
        self.assertEqual(derivar_spin_investigado(None, "s", False), "n")
        # Chamada não avaliável (queda/URA) SEMPRE força 'n'
        self.assertEqual(
            derivar_spin_investigado("Perguntou sobre ICMS", "s", eh_nao_avaliavel=True),
            "n",
        )

    def test_sanitizacao_spin_flags_chamada_avaliavel(self):
        """Garante que calcular_e_sanitizar_analise preenche as 4 flags SPIN corretamente."""
        dados = {
            "avaliacao_ia": {
                "resultado": "Perfil confirmado",
                "ligacao_relevante": "s",
                "reuniao_confirmada": "s",
                "data_confirmada": "s",
            },
            "avaliacao_sdr": {"nota_final": 80, "feedback_geral": "Boa condução."},
            "avaliacao_criterio": [],
            "analise_spin": {
                "situacao": "Empresa no Simples Nacional com 50 funcionários.",
                "situacao_investigada": "s",
                "problema": "Contabilidade atual demora para emitir guias.",
                "problema_investigado": "s",
                "implicacao": "Não se aplica",
                "implicacao_investigada": "s",  # IA alucinou 's', mas texto é Não se aplica -> deve virar 'n'
                "necessidade_solucao": "Nenhum",
                "necessidade_investigada": "n",
            },
            "crm": {"acao": "reunião confirmada", "prazo": "Amanhã 15h"},
        }
        res = calcular_e_sanitizar_analise(dados)
        spin = res["analise_spin"]
        self.assertEqual(spin["situacao_investigada"], "s")
        self.assertEqual(spin["problema_investigado"], "s")
        self.assertEqual(spin["implicacao_investigada"], "n")  # Coagido para 'n'
        self.assertEqual(spin["necessidade_investigada"], "n")

    def test_sanitizacao_spin_flags_chamada_nao_avaliavel(self):
        """Garante que chamadas não avaliáveis forçam todas as 4 flags SPIN para 'n'."""
        dados = {
            "avaliacao_ia": {
                "resultado": "Dados insuficientes",
                "ligacao_relevante": "n",
            },
            "avaliacao_sdr": {"nota_final": None, "feedback_geral": "Não avaliável: URA."},
            "avaliacao_criterio": [],
            "analise_spin": {
                "situacao": "Algum texto",
                "situacao_investigada": "s",
                "problema": "Algum problema",
                "problema_investigado": "s",
                "implicacao": "Alguma implicação",
                "implicacao_investigada": "s",
                "necessidade_solucao": "Alguma solução",
                "necessidade_investigada": "s",
            },
            "crm": {"acao": "Não se aplica"},
        }
        res = calcular_e_sanitizar_analise(dados)
        spin = res["analise_spin"]
        self.assertEqual(spin["situacao_investigada"], "n")
        self.assertEqual(spin["problema_investigado"], "n")
        self.assertEqual(spin["implicacao_investigada"], "n")
        self.assertEqual(spin["necessidade_investigada"], "n")

    def test_pydantic_analise_spin_model_default_flags(self):
        """Garante que AnaliseSpinModel inicializa as 4 flags como 'n' por padrão."""
        modelo = AnaliseSpinModel()
        self.assertEqual(modelo.situacao_investigada, "n")
        self.assertEqual(modelo.problema_investigado, "n")
        self.assertEqual(modelo.implicacao_investigada, "n")
        self.assertEqual(modelo.necessidade_investigada, "n")

    def test_multiplas_oportunidades_treinamento_sanitizacao(self):
        """Valida que múltiplas oportunidades válidas são preservadas e códigos inválidos descartados."""
        dados = {
            "avaliacao_ia": {
                "resultado": "Perfil confirmado",
                "ligacao_relevante": "s",
                "reuniao_confirmada": "s",
                "data_confirmada": "s",
            },
            "avaliacao_sdr": {
                "nota_final": 85,
                "feedback_geral": "Boa condução com pontos a aprimorar.",
                "codigos_oportunidade": ["OP_SPIN_03", "OP_ESC_04", "OP_PERF_01", "OP_INVALIDO_99", "OP_SPIN_03"],
            },
            "avaliacao_criterio": [],
            "crm": {"acao": "reunião confirmada", "prazo": "10/10 às 15h"},
        }
        res = calcular_e_sanitizar_analise(dados)
        av_sdr = res["avaliacao_sdr"]
        # OP_ESC_04 e OP_INVALIDO descartados, duplicata deduplicada
        self.assertEqual(av_sdr["codigos_oportunidade"], ["OP_SPIN_03", "OP_PERF_01"])
        self.assertEqual(av_sdr["codigo_oportunidade"], "OP_SPIN_03")

    def test_blindagem_notas_null_quando_nao_avaliavel_no_meio_do_feedback(self):
        """Garante que 'não avaliável' no meio do feedback força NULL em todas as notas, mesmo com notas nos critérios."""
        dados = {
            "avaliacao_ia": {
                "resultado": "Dados insuficientes",
                "ligacao_relevante": "s",  # IA errou aqui, mas feedback diz não avaliável
            },
            "avaliacao_sdr": {
                "nota_final": 60,
                "feedback_geral": "O contato ocorreu com a portaria, sendo não avaliável tecnicamente para SDR.",
                "codigos_oportunidade": ["OP_SPIN_03"],
            },
            "avaliacao_criterio": [
                {"codigo_criterio": "CRIT_ABERTURA", "nota_criterio": 10, "justificativa_criterio": "Abriu bem"},
                {"codigo_criterio": "CRIT_SPIN", "nota_criterio": 15, "justificativa_criterio": "Tentou"},
            ],
            "crm": {"acao": "Não se aplica"},
        }
        res = calcular_e_sanitizar_analise(dados)
        av_sdr = res["avaliacao_sdr"]
        self.assertIsNone(av_sdr["nota_final"])
        self.assertEqual(av_sdr["codigos_oportunidade"], [])
        self.assertIsNone(av_sdr["codigo_oportunidade"])
        for crit in res["avaliacao_criterio"]:
            self.assertIsNone(crit["nota_criterio"])

    def test_pydantic_avaliacao_sdr_model_harmoniza_legado_e_lista(self):
        """Valida que AvaliacaoSDRModel aceita tanto string única (legado) quanto lista de códigos."""
        m1 = AvaliacaoSDRModel(feedback_geral="ok", codigo_oportunidade="OP_SPIN_03")
        self.assertEqual(m1.codigos_oportunidade, ["OP_SPIN_03"])
        self.assertEqual(m1.codigo_oportunidade, "OP_SPIN_03")

        m2 = AvaliacaoSDRModel(feedback_geral="ok", codigos_oportunidade=["OP_SPIN_03", "OP_PERF_01"])
        self.assertEqual(m2.codigos_oportunidade, ["OP_SPIN_03", "OP_PERF_01"])
        self.assertEqual(m2.codigo_oportunidade, "OP_SPIN_03")

    def test_normalizar_prazo_data_timestamp_com_data_referencia(self):
        """Valida que normalizar_prazo_data_timestamp formata e valida datas corretamente quando há referência."""
        # 1. ISO completo com segundos
        self.assertEqual(
            normalizar_prazo_data_timestamp("2026-10-10 14:00:00", tem_data_referencia=True),
            "2026-10-10 14:00:00"
        )
        # 2. ISO sem segundos (adiciona :00)
        self.assertEqual(
            normalizar_prazo_data_timestamp("2026-10-10 14:00", tem_data_referencia=True),
            "2026-10-10 14:00:00"
        )
        # 3. ISO com separador 'T'
        self.assertEqual(
            normalizar_prazo_data_timestamp("2026-10-10T14:00:00", tem_data_referencia=True),
            "2026-10-10 14:00:00"
        )
        # 4. Apenas data (complementa com 00:00:00)
        self.assertEqual(
            normalizar_prazo_data_timestamp("2026-10-10", tem_data_referencia=True),
            "2026-10-10 00:00:00"
        )
        # 5. Strings de ausência ou não se aplica
        self.assertIsNone(normalizar_prazo_data_timestamp("Não se aplica", tem_data_referencia=True))
        self.assertIsNone(normalizar_prazo_data_timestamp("a definir", tem_data_referencia=True))
        self.assertIsNone(normalizar_prazo_data_timestamp("null", tem_data_referencia=True))
        self.assertIsNone(normalizar_prazo_data_timestamp(None, tem_data_referencia=True))
        # 6. Data impossível no calendário (rejeição segura)
        self.assertIsNone(normalizar_prazo_data_timestamp("2026-02-31 10:00:00", tem_data_referencia=True))

    def test_normalizar_prazo_data_timestamp_sem_data_referencia_forca_none(self):
        """Regra estrita: se não houver data_referencia (tem_data_referencia=False), força incondicionalmente None."""
        self.assertIsNone(
            normalizar_prazo_data_timestamp("2026-10-10 14:00:00", tem_data_referencia=False)
        )
        self.assertIsNone(
            normalizar_prazo_data_timestamp("2026-10-10", tem_data_referencia=False)
        )

    def test_calcular_e_sanitizar_analise_com_dt_inicio_preserva_prazo_data(self):
        """Quando data_referencia é informada, prazo textual e prazo_data TIMESTAMP são preservados."""
        dados = {
            "avaliacao_ia": {
                "resultado": "Perfil confirmado",
                "ligacao_relevante": "s",
            },
            "avaliacao_sdr": {"nota_final": 85, "feedback_geral": "Ótima abordagem."},
            "avaliacao_criterio": [],
            "crm": {
                "acao": "reunião confirmada",
                "prazo": "Amanhã às 14h",
                "prazo_data": "2026-10-10 14:00:00",
                "resumo": "Reunião técnica agendada.",
            },
        }
        res = calcular_e_sanitizar_analise(
            dados,
            data_referencia="2026-10-09 10:15:00 (Sexta-feira)",
        )
        self.assertEqual(res["crm"]["prazo"], "Amanhã às 14h")
        self.assertEqual(res["crm"]["prazo_data"], "2026-10-10 14:00:00")
        self.assertEqual(res["avaliacao_ia"]["data_confirmada"], "s")

    def test_calcular_e_sanitizar_analise_sem_dt_inicio_forca_prazo_data_none(self):
        """Quando NÃO há data_referencia (None ou 'Não informado'), prazo_data é forçado para None."""
        dados = {
            "avaliacao_ia": {
                "resultado": "Perfil confirmado",
                "ligacao_relevante": "s",
            },
            "avaliacao_sdr": {"nota_final": 85, "feedback_geral": "Ótima abordagem."},
            "avaliacao_criterio": [],
            "crm": {
                "acao": "reunião confirmada",
                "prazo": "Amanhã às 14h",
                "prazo_data": "2026-10-10 14:00:00",  # Alucinação/tentativa de preencher sem referência
                "resumo": "Reunião técnica agendada.",
            },
        }
        # Caso 1: data_referencia=None
        res1 = calcular_e_sanitizar_analise(dados, data_referencia=None)
        self.assertEqual(res1["crm"]["prazo"], "Amanhã às 14h")
        self.assertIsNone(res1["crm"]["prazo_data"])

        # Caso 2: data_referencia="Não informado"
        res2 = calcular_e_sanitizar_analise(dados, data_referencia="Não informado")
        self.assertEqual(res2["crm"]["prazo"], "Amanhã às 14h")
        self.assertIsNone(res2["crm"]["prazo_data"])

    def test_pydantic_crm_model_valida_prazo_data_opcional(self):
        """Garante que o Pydantic CrmModel aceita prazo e prazo_data opcionalmente."""
        m = CrmModel(
            acao="reunião confirmada",
            prazo="Amanhã às 14h",
            prazo_data="2026-10-10 14:00:00",
        )
        self.assertEqual(m.prazo, "Amanhã às 14h")
        self.assertEqual(m.prazo_data, "2026-10-10 14:00:00")

        m_vazio = CrmModel(acao="Não se aplica")
        self.assertIsNone(m_vazio.prazo)
        self.assertIsNone(m_vazio.prazo_data)


if __name__ == "__main__":
    unittest.main()
