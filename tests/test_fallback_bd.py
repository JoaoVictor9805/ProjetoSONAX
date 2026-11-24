# -*- coding: utf-8 -*-
"""Testes unitários para o fallback local de persistência no banco (CSV + JSON)."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.fallback_bd import (
    COLUNAS_FALLBACK_CSV,
    carregar_fallback_bd,
    reprocessar_fallback_bd,
    salvar_fallback_bd,
)


class TestFallbackBD(unittest.TestCase):

    def test_salvar_fallback_consolida_etapas_em_csv_e_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)

            # 1. Falha ao salvar transcrição
            csv_path, json_path = salvar_fallback_bd(
                log="1001-2026-11-24-10-00-00.wav",
                protocolo=123456,
                transcricao="Bom dia, aqui é o Lucas da Falavinha Next.",
                etapa_falha="transcricao",
                erro="OperationalError: timeout",
                pasta_raiz=raiz,
            )

            self.assertTrue(csv_path.is_file())
            self.assertTrue(json_path.is_file())

            # 2. Falha posterior na revisão do mesmo log (deve preservar transcrição)
            salvar_fallback_bd(
                log="1001-2026-11-24-10-00-00.wav",
                revisao="Agente (Lucas): Bom dia, aqui é o Lucas da Falavinha Next.",
                empresa_nome="Auto Peças Brasil",
                empresa_telefone="4133101010",
                empresa_fonte_dados="Interlocutor / Agente",
                etapa_falha="revisao",
                erro="Connection refused",
                pasta_raiz=raiz,
            )

            # 3. Falha posterior na análise do mesmo log (deve preservar transcrição e revisão)
            analise_payload = {
                "avaliacao_ia": {"resultado": "Perfil pendente", "ligacao_relevante": "s"},
                "avaliacao_sdr": {"nota_final": 75, "feedback_geral": "Bom contato"},
                "avaliacao_criterio": [],
                "analise_spin": {"situacao": "Atendimento inicial"},
                "analise_bant": {"need_classificacao": "media"},
                "interlocutor": {"interesse_expresso": "Sim"},
                "crm": {"acao": "retorno com data combinado"},
                "analise_perfil": {"setor": "outro confirmado"},
            }
            salvar_fallback_bd(
                log="1001-2026-11-24-10-00-00.wav",
                analise_json=analise_payload,
                etapa_falha="analise",
                erro="Deadlock detected",
                pasta_raiz=raiz,
            )

            # Valida JSON consolidado
            with open(json_path, "r", encoding="utf-8") as f:
                dados_json = json.load(f)
            self.assertEqual(len(dados_json), 1)
            reg = dados_json[0]
            self.assertEqual(reg["log"], "1001-2026-11-24-10-00-00.wav")
            self.assertEqual(reg["protocolo"], 123456)
            self.assertIn("Falavinha Next", reg["transcricao"])
            self.assertIn("Agente (Lucas):", reg["revisao"])
            self.assertEqual(reg["empresa_nome"], "Auto Peças Brasil")
            self.assertEqual(reg["analise_json"]["avaliacao_sdr"]["nota_final"], 75)
            self.assertEqual(reg["etapa_falha"], "analise")

            # Valida planilha CSV (UTF-8 BOM, delimitador ';', cabeçalho exato)
            with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f, delimiter=";")
                self.assertEqual(tuple(reader.fieldnames), COLUNAS_FALLBACK_CSV)
                linhas = list(reader)
            self.assertEqual(len(linhas), 1)
            self.assertEqual(linhas[0]["log"], "1001-2026-11-24-10-00-00.wav")
            self.assertEqual(linhas[0]["protocolo"], "123456")
            self.assertEqual(
                json.loads(linhas[0]["analise_json"])["crm"]["acao"],
                "retorno com data combinado",
            )

    @patch("app.database.chamadas_dao.inserir_analise")
    @patch("app.database.chamadas_dao.inserir_revisao")
    @patch("app.database.chamadas_dao.inserir_empresa")
    @patch("app.database.chamadas_dao.inserir_registro_chamada")
    @patch("app.database.db.conectar")
    def test_reprocessar_fallback_bd_insere_e_limpa_concluidos(
        self,
        mock_conectar,
        mock_inserir_reg,
        mock_inserir_emp,
        mock_inserir_rev,
        mock_inserir_ana,
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            salvar_fallback_bd(
                log="ok.wav",
                protocolo=111,
                transcricao="Oi",
                revisao="Agente: Oi",
                empresa_nome="Empresa Ok",
                empresa_telefone="4199999999",
                empresa_fonte_dados="Agente",
                analise_json={"avaliacao_ia": {"resultado": "Perfil pendente"}},
                etapa_falha="analise",
                pasta_raiz=raiz,
            )
            salvar_fallback_bd(
                log="falha.wav",
                protocolo=222,
                transcricao="Alô",
                etapa_falha="transcricao",
                pasta_raiz=raiz,
            )

            mock_cur = MagicMock()
            mock_conectar.return_value.__enter__.return_value = mock_cur
            mock_inserir_emp.return_value = 77

            def inserir_reg_side_effect(cur, *, log_arquivo, protocolo, transcricao):
                if log_arquivo == "falha.wav":
                    raise RuntimeError("Falha simulada no banco")
                return log_arquivo

            mock_inserir_reg.side_effect = inserir_reg_side_effect

            resumo = reprocessar_fallback_bd(pasta_raiz=raiz)
            self.assertEqual(resumo, {"processados": 2, "sucesso": 1, "falha": 1})

            mock_inserir_emp.assert_called_once_with(
                mock_cur, "Empresa Ok", "Agente", telefone="4199999999"
            )
            mock_inserir_rev.assert_called_once_with(
                mock_cur, "ok.wav", "Agente: Oi", id_empresa=77
            )
            mock_inserir_ana.assert_called_once()
            self.assertEqual(
                mock_inserir_ana.call_args[0][2]["avaliacao_ia"]["empresa_contatada"], 77
            )

            restantes = carregar_fallback_bd(pasta_raiz=raiz)
            self.assertEqual(len(restantes), 1)
            self.assertEqual(restantes[0]["log"], "falha.wav")


if __name__ == "__main__":
    unittest.main()
