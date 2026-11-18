# -*- coding: utf-8 -*-
"""Testes unitários para o serviço de planilha e funções de apoio do Modo Teste."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.ia import FakeProvedorIA
from app.services.ingestao import ChamadaIngestor
from app.services.io import coletar_audios
from app.services.planilha import (
    NOME_ABA_PADRAO,
    obter_caminho_planilha_raiz,
    salvar_transcricoes_planilha,
)


class TestPlanilhaModoTeste(unittest.TestCase):

    def test_obter_caminho_planilha_raiz(self):
        caminho = obter_caminho_planilha_raiz()
        self.assertEqual(caminho.name, "transcricoes_modo_teste.xlsx")
        self.assertEqual(caminho.parent, Path(__file__).resolve().parent.parent)

    def test_criar_e_anexar_planilha(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "transcricoes_modo_teste.xlsx"

            reg1 = [{
                "arquivo": "ligacao_qualquer_titulo.mp3",
                "data_processamento": "2026-11-18 13:00:00",
                "duracao_segundos": 42.5,
                "empresa_identificada": "Auto Peças Teste",
                "transcricao_diarizada": "Agente (Falavinha): Bom dia!\nCliente (Auto Peças Teste): Olá!",
                "transcricao_bruta": "Bom dia Olá",
                "qualidade_transcricao": "Excelente (95/100)",
                "status": "Sucesso",
                "caminho_origem": "C:/audios/ligacao_qualquer_titulo.mp3",
            }]
            salvo1 = salvar_transcricoes_planilha(reg1, caminho=destino)
            self.assertEqual(salvo1, destino)
            self.assertTrue(destino.is_file())

            reg2 = [{
                "arquivo": "outro_audio_sem_padrao.wav",
                "data_processamento": "2026-11-18 13:05:00",
                "duracao_segundos": 15.0,
                "empresa_identificada": "Não encontrado",
                "transcricao_diarizada": "Cliente: Alô?",
                "transcricao_bruta": "Alô",
                "qualidade_transcricao": "Médio (65/100)",
                "status": "Sucesso",
                "caminho_origem": "C:/audios/outro_audio_sem_padrao.wav",
            }]
            salvo2 = salvar_transcricoes_planilha(reg2, caminho=destino)
            self.assertEqual(salvo2, destino)

            wb = openpyxl.load_workbook(destino)
            self.assertIn(NOME_ABA_PADRAO, wb.sheetnames)
            ws = wb[NOME_ABA_PADRAO]
            self.assertEqual(ws.max_row, 3)  # cabeçalho + 2 registros
            self.assertEqual(ws.max_column, 3)
            self.assertEqual(ws.cell(row=1, column=1).value, "Duração (s)")
            self.assertEqual(ws.cell(row=1, column=2).value, "Transcrição")
            self.assertEqual(ws.cell(row=1, column=3).value, "Revisão")
            self.assertEqual(ws.cell(row=2, column=1).value, 42.5)
            self.assertEqual(ws.cell(row=2, column=2).value, "Bom dia Olá")
            self.assertEqual(
                ws.cell(row=2, column=3).value,
                "Agente (Falavinha): Bom dia!\nCliente (Auto Peças Teste): Olá!",
            )
            self.assertEqual(ws.cell(row=3, column=1).value, 15.0)
            self.assertEqual(ws.cell(row=3, column=2).value, "Alô")
            self.assertEqual(ws.cell(row=3, column=3).value, "Cliente: Alô?")
            self.assertTrue(ws.cell(row=2, column=2).alignment.wrap_text)
            self.assertGreaterEqual(ws.row_dimensions[2].height, 22.0)

    def test_ajustar_layout_expande_colunas_e_preserva_valores(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "longo.xlsx"
            texto_longo = "\n".join(f"Linha {i}: " + ("palavra " * 25) for i in range(1, 36))
            salvar_transcricoes_planilha([{
                "duracao_segundos": 300.0,
                "transcricao_bruta": "palavra " * 400,
                "transcricao_diarizada": texto_longo,
            }], caminho=destino)

            wb = openpyxl.load_workbook(destino)
            ws = wb.active
            self.assertEqual(ws.cell(row=2, column=3).value, texto_longo)
            self.assertGreater(ws.column_dimensions["C"].width, 160.0)
            self.assertLessEqual(ws.row_dimensions[2].height, 409.5)
            self.assertEqual(ws.cell(row=2, column=3).font.size, 8)

    def test_fallback_permission_error_salva_com_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "transcricoes_modo_teste.xlsx"
            reg = [{
                "arquivo": "teste.wav",
                "transcricao_bruta": "olá",
                "transcricao_diarizada": "Cliente: olá",
                "status": "Sucesso",
            }]

            chamadas = {"n": 0}
            orig_save = openpyxl.Workbook.save

            def save_com_erro_na_primeira(self_wb, filename):
                chamadas["n"] += 1
                if chamadas["n"] == 1:
                    raise PermissionError("Arquivo aberto no Excel")
                return orig_save(self_wb, filename)

            with patch.object(openpyxl.Workbook, "save", new=save_com_erro_na_primeira):
                salvo = salvar_transcricoes_planilha(reg, caminho=destino)

            self.assertNotEqual(salvo, destino)
            self.assertTrue(salvo.is_file())
            self.assertTrue(salvo.name.startswith("transcricoes_modo_teste_"))
            self.assertEqual(salvo.suffix, ".xlsx")

    def test_coletar_audios_aceita_arquivo_unico_e_qualquer_titulo(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            f_wav = pasta / "minha ligacao de teste.wav"
            f_mp3 = pasta / "conversa cliente #2.mp3"
            f_txt = pasta / "notas.txt"
            f_wav.write_bytes(b"fake")
            f_mp3.write_bytes(b"fake")
            f_txt.write_text("ignorar")

            self.assertEqual(coletar_audios(f_mp3), [f_mp3])
            self.assertEqual(coletar_audios(f_txt), [])

            encontrados = coletar_audios(pasta)
            self.assertEqual({p.name for p in encontrados}, {"minha ligacao de teste.wav", "conversa cliente #2.mp3"})

    def test_ingestao_sem_banco_qualquer_titulo(self):
        fake_ia = FakeProvedorIA()
        ingestor = ChamadaIngestor(provedor_ia=fake_ia)

        res = ingestor.transcrever_sem_banco(
            caminho=Path("qualquer_nome_de_audio_sem_protocolo.mp3"),
            rotulo_audio="Audio 01",
            duracao_segundos=30.0,
        )
        self.assertTrue(res.sucesso)
        self.assertEqual(res.texto_transcricao, fake_ia.transcricao_padrao["texto"])

        rev = ingestor.revisar_sem_banco(
            log_arquivo="qualquer_nome_de_audio_sem_protocolo.mp3",
            texto_diarizado=res.texto_transcricao,
            rotulo_audio="Audio 01",
        )
        self.assertIsNotNone(rev)
        self.assertEqual(rev["revisao"], fake_ia.revisao_padrao)
        self.assertEqual(rev["empresa"], fake_ia.empresa_padrao)


if __name__ == "__main__":
    unittest.main()
