# -*- coding: utf-8 -*-
import unittest

from app.services.sanitizador import (
    corrigir_mojibake,
    sanitizar_texto_estrangeiro,
    sanitizar_estrutura_analise,
)


class TestSanitizador(unittest.TestCase):
    def test_preserva_portugues_e_acentos(self):
        texto = "Olá, tudo bem? Reunião técnica confirmada às 14h com o Dr. João da Silva (Açúcar & Café LTDA)."
        resultado = sanitizar_texto_estrangeiro(texto)
        self.assertEqual(resultado, texto)

    def test_remove_chines_e_normaliza_pontuacao(self):
        # Exemplo real do banco: modelo de收费
        texto = "O SDR apresentou a proposta e esclareceu o modelo de收费, mas o interlocutor recusou..."
        resultado = sanitizar_texto_estrangeiro(texto)
        self.assertNotIn("收费", resultado)
        self.assertEqual(resultado, "O SDR apresentou a proposta e esclareceu o modelo de, mas o interlocutor recusou...")

    def test_converte_pontuacao_oriental(self):
        texto = "A SDR propôs dia e horário concretos，confirmou o retorno para o dia 20。"
        resultado = sanitizar_texto_estrangeiro(texto)
        self.assertEqual(resultado, "A SDR propôs dia e horário concretos, confirmou o retorno para o dia 20.")

    def test_remove_arabe_e_cirilico(self):
        texto_arabe = "A conversaشروع uma abertura clara para qualificar a empresa."
        resultado_arabe = sanitizar_texto_estrangeiro(texto_arabe)
        self.assertNotIn("شروع", resultado_arabe)
        self.assertEqual(resultado_arabe, "A conversa uma abertura clara para qualificar a empresa.")

        texto_russo = "O SDR acolheu a recusa, пояс positioning que não iria."
        resultado_russo = sanitizar_texto_estrangeiro(texto_russo)
        self.assertNotIn("пояс", resultado_russo)
        self.assertEqual(resultado_russo, "O SDR acolheu a recusa, positioning que não iria.")

    def test_sanitiza_estrutura_recursiva(self):
        dados = {
            "avaliacao_ia": {
                "interlocutor": "Carlos 王 Silva",
                "resultado_frase": "O SDR falou com Wagner, e a万多，安排 de envio...",
            },
            "criterios": [
                {"justificativa": "Sem oportunidade: a interlocutora foi direta e得到的 aceite..."},
                {"justificativa": "A SDR propôs dia e horário concretos."},
            ],
            "nota": 85,
        }
        sanitizado = sanitizar_estrutura_analise(dados)
        self.assertEqual(sanitizado["avaliacao_ia"]["interlocutor"], "Carlos Silva")
        self.assertNotIn("万多", sanitizado["avaliacao_ia"]["resultado_frase"])
        self.assertNotIn("得到的", sanitizado["criterios"][0]["justificativa"])
        self.assertEqual(sanitizado["nota"], 85)

    def test_corrige_mojibake(self):
        mojibake = "ReuniÃ£o confirmada para avaliaÃ§Ã£o de crÃ©ditos"
        recuperado = sanitizar_texto_estrangeiro(mojibake)
        self.assertEqual(recuperado, "Reunião confirmada para avaliação de créditos")


if __name__ == "__main__":
    unittest.main()
