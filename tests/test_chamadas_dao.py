# -*- coding: utf-8 -*-
"""Testes unitários para a camada DAO de chamadas e empresas."""
import unittest
from unittest.mock import MagicMock

from app.database.chamadas_dao import (
    buscar_chamada_valida,
    inserir_analise,
    inserir_empresa,
    inserir_revisao,
    verificar_tabela_analise,
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
        # Primeiro SELECT encontra a empresa existente com id 5, telefone e fonte_dados preenchida
        cur.fetchone.return_value = (5, "(41) 3310-1010", "Fonte Antiga")

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


    def test_inserir_empresa_nao_encontrado_cria_novo_id_sempre(self):
        cur = MagicMock()
        cur.fetchone.return_value = (77,)

        id_empresa = inserir_empresa(cur, "Não encontrado", "Fonte Individual")
        self.assertEqual(id_empresa, 77)
        # Deve executar apenas o INSERT direto sem SELECT prévio de deduplicação
        self.assertEqual(cur.execute.call_count, 1)
        query = cur.execute.call_args[0][0]
        self.assertIn("INSERT INTO empresa", query)

    def test_inserir_empresa_ancora_telefone_reaproveita_id_e_enriquece_nome(self):
        cur = MagicMock()
        # SELECT por telefone encontra empresa existente (id=5, nome="Abima", fonte="Fonte")
        cur.fetchone.return_value = (5, "Abima", "Fonte")

        id_empresa = inserir_empresa(
            cur,
            nome="Abima calçados",
            fonte_dados="Fonte",
            telefone="(41) 3346-2828",
        )

        self.assertEqual(id_empresa, 5)
        # Deve fazer o SELECT por telefone e em seguida o UPDATE do nome
        self.assertEqual(cur.execute.call_count, 2)
        select_query = cur.execute.call_args_list[0][0][0]
        self.assertIn("WHERE telefone = %s", select_query)
        update_query = cur.execute.call_args_list[1][0][0]
        self.assertIn("UPDATE empresa SET nome = %s", update_query)
        self.assertEqual(cur.execute.call_args_list[1][0][1], ("Abima calçados", 5))

    def test_inserir_empresa_ancora_telefone_atualiza_nao_encontrado(self):
        cur = MagicMock()
        # Telefone já existia com nome "Não encontrado"
        cur.fetchone.return_value = (8, "Não encontrado", "Fonte")

        id_empresa = inserir_empresa(
            cur,
            nome="Abima",
            fonte_dados="Fonte Nova",
            telefone="(41) 3346-2828",
        )

        self.assertEqual(id_empresa, 8)
        # Deve atualizar o nome de "Não encontrado" para "Abima"
        update_query = cur.execute.call_args_list[1][0][0]
        self.assertIn("UPDATE empresa SET nome = %s", update_query)

    def test_verificar_tabela_analise(self):
        cur = MagicMock()
        cur.fetchone.return_value = (1,)
        self.assertTrue(verificar_tabela_analise(cur, "audio.wav"))
        cur.fetchone.return_value = None
        self.assertFalse(verificar_tabela_analise(cur, "audio2.wav"))

    def test_inserir_analise_persiste_nas_7_tabelas(self):
        cur = MagicMock()
        cur.fetchone.return_value = ("audio.wav",)

        dados_analise = {
            "avaliacao_ia": {
                "protocolo": 123456789,
                "data_avaliacao": "2026-09-30",
                "modelo_ia": "gpt-4o-mini",
                "interlocutor": "Carlos Silva",
                "cargo": "Diretor Financeiro",
                "empresa_contatada": 1054,
                "resultado": "Perfil confirmado",
                "ligacao_relevante": "s",
                "reuniao_confirmada": "s",
                "data_confirmada": "s",
                "resultado_frase": "O SDR validou o regime de Lucro Real e agendou reunião técnica.",
            },
            "analise_spin": {
                "situacao": "Empresa na indústria.",
                "problema": "Obrigações acessórias complexas.",
                "implicacao": "Risco de multas.",
                "necessidade_solucao": "Consultoria especializada.",
                "evidencias": "\"A nossa principal dor é o SPED\"",
                "lacunas": "Não aprofundou multas.",
            },
            "analise_bant": {
                "budget_classificacao": "não informado",
                "budget_evidencia": "Não abordado.",
                "authority_classificacao": "confirmado",
                "authority_evidencia": "Diretor aprova.",
                "need_classificacao": "confirmado",
                "need_evidencia": "Risco fiscal.",
                "timeline_classificacao": "indício",
                "timeline_evidencia": "Até o fim do trimestre.",
            },
            "avaliacao_sdr": {
                "nota_final": 85,
                "feedback_geral": "Boa condução consultiva.",
                "acertos": "1. Escuta ativa. 2. Investigação de perfil.",
                "melhorias": "1. Implicações. 2. Envolvimento de decisores.",
                "frase_alternativa": "Que impacto financeiro esses erros trouxeram?",
                "codigo_oportunidade": "OP_SPIN_03",
            },
            "avaliacao_criterio": [
                {
                    "criterio": "Abertura clara, motivo do contato e relevância para o interlocutor",
                    "nota_criterio": 10,
                    "justificativa_criterio": "Apresentou motivo claro.",
                    "codigo_criterio": "CRIT_ABERTURA",
                },
                {
                    "criterio": "Descoberta SPIN: Situação, Problema, Implicação, Necessidade de solução",
                    "nota_criterio": 22,
                    "justificativa_criterio": "Descoberta conduzida.",
                    "codigo_criterio": "CRIT_SPIN",
                },
            ],
            "interlocutor": {
                "interesse_expresso": "Interesse em avaliar créditos.",
                "duvidas": "Questionou sobre a contabilidade.",
                "objecoes": "não houve",
                "resposta_sdr": "Explicou modelo complementar.",
                "reacao_interlocutor": "Aceitou explicação.",
            },
            "crm": {
                "acao": "Reunião confirmada (apresentação técnica)",
                "responsavel": "SDR Carlos",
                "prazo": "06/10/2026 às 14:00",
                "dados_extras": "Confirmar se o contador participa.",
                "resumo": "Empresa industrial em Lucro Real. Reunião técnica agendada.",
            },
        }

        res = inserir_analise(cur, "audio.wav", dados_analise)
        self.assertEqual(res, "audio.wav")

        queries = [call[0][0] for call in cur.execute.call_args_list]
        self.assertTrue(any("INSERT INTO avaliacao_ia" in q for q in queries))
        self.assertTrue(any("INSERT INTO avaliacao_sdr" in q for q in queries))
        self.assertTrue(any("INSERT INTO avaliacao_criterio" in q for q in queries))
        self.assertTrue(any("INSERT INTO analise_spin" in q for q in queries))
        self.assertTrue(any("INSERT INTO analise_bant" in q for q in queries))
        self.assertTrue(any("INSERT INTO interlocutor" in q for q in queries))
        self.assertTrue(any("INSERT INTO crm" in q for q in queries))
        self.assertTrue(any("UPDATE empresa" in q for q in queries))


if __name__ == "__main__":
    unittest.main()
