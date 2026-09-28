# -*- coding: utf-8 -*-
import io
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.audio_inspector import AudioInspector, AudioMetadata


def criar_wav_sintetico(duracao_segundos: float = 70.0, byte_rate: int = 16000) -> bytes:
    """Gera bytes de um contêiner RIFF/WAVE válido com a duração especificada."""
    data_size = int(duracao_segundos * byte_rate)
    buffer = io.BytesIO()

    # RIFF header
    buffer.write(b"RIFF")
    buffer.write(struct.pack("<I", 36 + data_size))
    buffer.write(b"WAVE")

    # fmt chunk
    buffer.write(b"fmt ")
    buffer.write(struct.pack("<I", 16))  # chunk_size
    # AudioFormat=1 (PCM), NumChannels=1, SampleRate=8000, ByteRate, BlockAlign=2, BitsPerSample=16
    buffer.write(struct.pack("<HHIIHH", 1, 1, 8000, byte_rate, 2, 16))

    # data chunk
    buffer.write(b"data")
    buffer.write(struct.pack("<I", data_size))
    # Para o teste, não precisamos gravar todos os bytes de som se o leitor só lê cabeçalho
    # Mas como o loop lê chunks, escrevemos um pedaço ou saltamos
    buffer.write(b"\x00" * min(data_size, 64))

    return buffer.getvalue()


class TestAudioInspector(unittest.TestCase):

    def setUp(self):
        self.inspector = AudioInspector()

    def test_inspecionar_arquivo_invalido(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"Texto normal nao e WAV")
            caminho = Path(f.name)

        try:
            res = self.inspector.inspecionar(caminho)
            self.assertIsNone(res)
        finally:
            caminho.unlink(missing_ok=True)

    def test_inspecionar_wav_valido(self):
        raw_bytes = criar_wav_sintetico(duracao_segundos=75.0, byte_rate=16000)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(raw_bytes)
            caminho = Path(f.name)

        try:
            res = self.inspector.inspecionar(caminho)
            self.assertIsNotNone(res)
            self.assertAlmostEqual(res.duracao, 75.0, places=1)
            self.assertEqual(res.byte_rate, 16000)
        finally:
            caminho.unlink(missing_ok=True)

    def test_classificar_lote(self):
        meta_longo = AudioMetadata(path=Path("longo.wav"), duracao=90.0)
        meta_curto = AudioMetadata(path=Path("curto.wav"), duracao=30.0)

        with patch.object(self.inspector, "inspecionar") as mock_insp:
            mock_insp.side_effect = lambda p: meta_longo if p.name == "longo.wav" else (meta_curto if p.name == "curto.wav" else None)

            caminhos = [Path("longo.wav"), Path("curto.wav"), Path("invalido.wav")]
            res = self.inspector.classificar_lote(caminhos)

            self.assertEqual(len(res.longos), 1)
            self.assertEqual(res.longos[0].path.name, "longo.wav")
            self.assertEqual(len(res.curtos), 1)
            self.assertEqual(res.curtos[0].path.name, "curto.wav")
            self.assertEqual(len(res.invalidos), 1)
            self.assertEqual(res.invalidos[0].name, "invalido.wav")

    @patch("app.services.audio_inspector.analisar_audio")
    @patch("app.services.audio_inspector.classificar_qualidade_audio")
    def test_filtrar_qualidade_acustica(self, mock_classificar, mock_analisar):
        mock_analisar.return_value = {"snr": 20}
        mock_classificar.side_effect = ["Bom", "Péssimo"]

        audios = [
            AudioMetadata(path=Path("audio1.wav"), duracao=120.0),
            AudioMetadata(path=Path("audio2.wav"), duracao=150.0),
        ]

        aprovados, rejeitados = self.inspector.filtrar_qualidade_acustica(audios)

        self.assertEqual(len(aprovados), 1)
        self.assertEqual(aprovados[0].path.name, "audio1.wav")
        self.assertEqual(len(rejeitados), 1)
        self.assertEqual(rejeitados[0].name, "audio2.wav")


if __name__ == "__main__":
    unittest.main()
