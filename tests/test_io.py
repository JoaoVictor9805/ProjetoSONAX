# -*- coding: utf-8 -*-
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.audio_inspector import AudioMetadata
from app.services.io import copiar_lote_trabalho, deletar_pasta, resolver_destino


class TestIO(unittest.TestCase):

    def test_resolver_destino(self):
        p1 = Path("/tmp/00011687")
        d1 = resolver_destino(p1)
        self.assertEqual(d1.name, "audios_maiores_1min")
        self.assertEqual(d1.parent, p1.parent)

        p2 = Path("/tmp/geral")
        d2 = resolver_destino(p2)
        self.assertEqual(d2.name, "audios_maiores_1min")
        self.assertEqual(d2.parent, p2)

    def test_copiar_lote_trabalho_e_deletar(self):
        with tempfile.TemporaryDirectory() as temp_origem:
            origem = Path(temp_origem)
            f1 = origem / "audio1.wav"
            f2 = origem / "audio2.wav"
            f1.write_text("conteudo 1")
            f2.write_text("conteudo 2")

            with tempfile.TemporaryDirectory() as temp_destino:
                destino = Path(temp_destino) / "trabalho"

                audios = [
                    AudioMetadata(path=f1, duracao=120.0),
                    AudioMetadata(path=f2, duracao=90.0),
                ]

                copiados = copiar_lote_trabalho(audios, destino)
                self.assertEqual(len(copiados), 2)
                self.assertTrue((destino / "audio1.wav").exists())
                self.assertTrue((destino / "audio2.wav").exists())

                # Teste deletar
                sucesso = deletar_pasta(destino)
                self.assertTrue(sucesso)
                self.assertFalse(destino.exists())


if __name__ == "__main__":
    unittest.main()
