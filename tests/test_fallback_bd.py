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
    buscar_cache_rpa_fallback,
    carregar_fallback_bd,
    reprocessar_fallback_bd,
    salvar_cache_rpa_fallback,
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

    @patch("app.database.chamadas_dao.salvar_cache_rpa_google")
    @patch("app.database.chamadas_dao.inserir_analise")
    @patch("app.database.chamadas_dao.inserir_revisao")
    @patch("app.database.chamadas_dao.inserir_empresa")
    @patch("app.database.chamadas_dao.inserir_registro_chamada")
    @patch("app.database.db.conectar")
    def test_reprocessar_fallback_preserva_rpa_data_avaliacao_e_dt_inicio(
        self,
        mock_conectar,
        mock_inserir_reg,
        mock_inserir_emp,
        mock_inserir_rev,
        mock_inserir_ana,
        mock_salvar_rpa,
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            salvar_fallback_bd(
                log="103-554130142200-26082026-113047-178775464634775-21153502152.wav",
                protocolo=21153502152,
                ramal="103",
                data_chamada="2026-08-26 11:30:47",
                transcricao="Bom dia, falo com o financeiro?",
                etapa_falha="offline_transcricao",
                pasta_raiz=raiz,
            )
            salvar_cache_rpa_fallback(
                "(41) 3014-2200",
                "Indústria Metalúrgica Modelo Ltda - Curitiba PR",
                logs=["103-554130142200-26082026-113047-178775464634775-21153502152.wav"],
                pasta_raiz=raiz,
            )
            # Valida leitura do cache RPA offline
            cache = buscar_cache_rpa_fallback(["(41) 3014-2200"], pasta_raiz=raiz)
            self.assertEqual(
                cache.get("(41) 3014-2200"),
                "Indústria Metalúrgica Modelo Ltda - Curitiba PR",
            )

            salvar_fallback_bd(
                log="103-554130142200-26082026-113047-178775464634775-21153502152.wav",
                revisao="Agente: Bom dia, falo com o financeiro?\nCliente: Sim.",
                empresa_nome="Indústria Metalúrgica Modelo Ltda",
                empresa_telefone="554130142200",
                empresa_fonte_dados="Interlocutor",
                data_avaliacao="2026-10-15",
                analise_json={
                    "avaliacao_ia": {"resultado": "Perfil pendente", "ligacao_relevante": "s"},
                    "avaliacao_sdr": {"nota_final": 82, "feedback_geral": "Bom contato"},
                },
                etapa_falha="offline_analise",
                pasta_raiz=raiz,
            )

            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = None
            mock_conectar.return_value.__enter__.return_value = mock_cur
            mock_inserir_emp.return_value = 55

            resumo = reprocessar_fallback_bd(pasta_raiz=raiz)
            self.assertEqual(resumo, {"processados": 1, "sucesso": 1, "falha": 0})

            mock_salvar_rpa.assert_called_once_with(
                mock_cur,
                "(41) 3014-2200",
                "Indústria Metalúrgica Modelo Ltda - Curitiba PR",
            )
            mock_inserir_reg.assert_called_once()
            mock_inserir_emp.assert_called_once_with(
                mock_cur,
                "Indústria Metalúrgica Modelo Ltda",
                "Interlocutor",
                telefone="554130142200",
            )
            mock_inserir_rev.assert_called_once_with(
                mock_cur,
                "103-554130142200-26082026-113047-178775464634775-21153502152.wav",
                "Agente: Bom dia, falo com o financeiro?\nCliente: Sim.",
                id_empresa=55,
            )
            mock_inserir_ana.assert_called_once()
            analise_enviada = mock_inserir_ana.call_args[0][2]
            self.assertEqual(analise_enviada["avaliacao_ia"]["empresa_contatada"], 55)
            self.assertEqual(analise_enviada["avaliacao_ia"]["data_avaliacao"], "2026-10-15")
            self.assertEqual(analise_enviada["avaliacao_ia"]["dt_inicio"], "2026-08-26 11:30:47")

            self.assertEqual(carregar_fallback_bd(pasta_raiz=raiz), [])

    @patch("app.engine.runner.deletar_pasta")
    @patch("app.engine.runner.resolver_destino")
    @patch("app.engine.runner.copiar_lote_trabalho")
    @patch("app.engine.runner.AudioInspector")
    @patch("app.engine.runner.coletar_wavs")
    @patch("app.engine.runner.get_database_url")
    def test_pipeline_completo_em_modo_offline_salva_todas_as_etapas(
        self,
        mock_db_url,
        mock_coletar,
        mock_inspector_cls,
        mock_copiar,
        mock_resolver,
        mock_deletar,
    ):
        import threading
        from app.engine.runner import PipelineRunner
        from app.services.ia import FakeProvedorIA

        # Simula ausência total de configuração de banco no .env
        mock_db_url.side_effect = KeyError("DB_USER")

        wav = Path("103-554130142200-26082026-113047-178775464634775-21153502152.wav")
        mock_coletar.return_value = [wav]
        mock_copiar.return_value = [wav]

        mock_inspector = MagicMock()
        mock_inspecao = MagicMock()
        mock_inspecao.longos = [wav]
        mock_inspecao.curtos = []
        mock_inspecao.invalidos = []
        mock_inspector.classificar_lote.return_value = mock_inspecao
        mock_inspector.filtrar_qualidade_acustica.return_value = ([wav], [])
        mock_inspector_cls.return_value = mock_inspector

        fake_ia = FakeProvedorIA()
        fake_ia.transcricao_padrao = {
            "texto": (
                "Olá bom dia tudo bem aqui é o João da Falavinha Next gostaria de falar "
                "com o responsável financeiro da empresa sobre planejamento tributário"
            ),
            "metricas": {},
        }
        finished_calls = []

        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)

            def fake_rpa_lote(telefones_por_chave, *, on_item_coletado=None, **kwargs):
                for arq, tel in telefones_por_chave.items():
                    if tel and on_item_coletado:
                        on_item_coletado(tel, "Metalúrgica Curitiba S.A. - Telefone (41) 3014-2200")
                return {arq: "Metalúrgica Curitiba S.A. - Telefone (41) 3014-2200" for arq in telefones_por_chave}

            with patch("app.services.fallback_bd.obter_pasta_raiz_fallback", return_value=raiz):
                with patch("app.services.rpa_google.obter_caminho_chrome_instalado", return_value=None):
                    with patch("app.services.rpa_google.coletar_textos_google_lote", side_effect=fake_rpa_lote) as mock_rpa:
                        runner = PipelineRunner(
                            entrada=Path("entrada_offline"),
                            cancel_event=threading.Event(),
                            dev_mode_event=threading.Event(),
                            on_progress=lambda *a: None,
                            on_log=lambda *a: None,
                            on_finished=lambda *a: finished_calls.append(a),
                            provedor_ia=fake_ia,
                            modo_etapa="completo",
                        )
                        runner.run()

                        self.assertEqual(len(finished_calls), 1)
                        self.assertEqual(finished_calls[0][0], 0)
                        mock_rpa.assert_called_once()

                itens = carregar_fallback_bd(pasta_raiz=raiz)
                self.assertEqual(len(itens), 1)
                reg = itens[0]
                self.assertEqual(reg["log"], wav.name)
                self.assertEqual(reg["protocolo"], 21153502152)
                self.assertEqual(reg["ramal"], "103")
                self.assertEqual(reg["data_chamada"], "2026-08-26 11:30:47")
                self.assertIn("Falavinha Next", reg["transcricao"])
                self.assertEqual(reg["rpa_telefone"], "(41) 3014-2200")
                self.assertIn("Metalúrgica Curitiba", reg["rpa_texto_google"])
                self.assertIn("Agente", reg["revisao"])
                self.assertEqual(reg["empresa_nome"], "Empresa Teste")
                self.assertTrue(bool(reg["data_avaliacao"]))
                self.assertIsInstance(reg["analise_json"], dict)
                self.assertEqual(
                    reg["analise_json"]["avaliacao_ia"]["data_avaliacao"],
                    reg["data_avaliacao"],
                )

                # Segunda rodada offline com o mesmo arquivo deve reaproveitar tudo (idempotência)
                fake_ia.chamadas_transcrever.clear()
                fake_ia.chamadas_revisar.clear()
                fake_ia.chamadas_analisar.clear()
                with patch("app.services.rpa_google.coletar_textos_google_lote") as mock_rpa_2:
                    runner2 = PipelineRunner(
                        entrada=Path("entrada_offline"),
                        cancel_event=threading.Event(),
                        dev_mode_event=threading.Event(),
                        on_progress=lambda *a: None,
                        on_log=lambda *a: None,
                        on_finished=lambda *a: finished_calls.append(a),
                        provedor_ia=fake_ia,
                        modo_etapa="completo",
                    )
                    runner2.run()

                    mock_rpa_2.assert_not_called()
                    self.assertEqual(len(fake_ia.chamadas_transcrever), 0)
                    self.assertEqual(len(fake_ia.chamadas_revisar), 0)
                    self.assertEqual(len(fake_ia.chamadas_analisar), 0)


if __name__ == "__main__":
    unittest.main()
