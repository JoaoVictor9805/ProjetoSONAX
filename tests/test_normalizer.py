# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.engine.normalizer import ProgressNormalizer


class TestProgressNormalizer(unittest.TestCase):

    def setUp(self):
        self.normalizer = ProgressNormalizer()

    def test_normalizer_indeterminate(self):
        ev = self.normalizer.normalize(done=0, total=0, phase="transcribing")
        self.assertTrue(ev.is_indeterminate)
        self.assertEqual(ev.fraction, 0.0)
        self.assertEqual(ev.label, "Processando ...")

    def test_normalizer_eight_phases(self):
        # 1. scanning (0% -> 2%)
        ev_start = self.normalizer.normalize(done=0, total=1, phase="scanning")
        self.assertAlmostEqual(ev_start.fraction, 0.00, places=4)
        self.assertEqual(ev_start.label, "varrendo  •  0%")

        ev_end = self.normalizer.normalize(done=1, total=1, phase="scanning")
        self.assertAlmostEqual(ev_end.fraction, 0.02, places=4)
        self.assertEqual(ev_end.label, "varrendo  •  2%")

        # 2. classifying (2% -> 5%)
        ev = self.normalizer.normalize(done=0.5, total=1, phase="classifying")
        self.assertAlmostEqual(ev.fraction, 0.02 + 0.5 * 0.03, places=4)

        # 3. copying (5% -> 10%)
        ev = self.normalizer.normalize(done=5, total=10, phase="copying")
        self.assertAlmostEqual(ev.fraction, 0.05 + 0.5 * 0.05, places=4)
        self.assertEqual(ev.label, "copiando  •  8%")

        # 4. transcribing (10% -> 80%)
        ev = self.normalizer.normalize(done=0, total=10, phase="transcribing")
        self.assertAlmostEqual(ev.fraction, 0.10, places=4)
        self.assertIn("1/10 arquivos", ev.label)

        ev = self.normalizer.normalize(done=10, total=10, phase="transcribing")
        self.assertAlmostEqual(ev.fraction, 0.80, places=4)
        self.assertIn("10/10 arquivos", ev.label)

        # 5. inserting (80% -> 83%)
        ev = self.normalizer.normalize(done=1, total=1, phase="inserting")
        self.assertAlmostEqual(ev.fraction, 0.83, places=4)
        self.assertIn("gravando no banco", ev.label)

        # 6. reviewing (83% -> 91%)
        ev = self.normalizer.normalize(done=5, total=10, phase="reviewing")
        self.assertAlmostEqual(ev.fraction, 0.83 + 0.5 * 0.08, places=4)
        self.assertIn("revisando 6/10", ev.label)

        # 7. analyzing (91% -> 98%)
        ev = self.normalizer.normalize(done=5, total=10, phase="analyzing")
        self.assertAlmostEqual(ev.fraction, 0.91 + 0.5 * 0.07, places=4)
        self.assertIn("analisando 6/10", ev.label)

        # 8. cleanup (98% -> 100%)
        ev = self.normalizer.normalize(done=1, total=1, phase="cleanup")
        self.assertAlmostEqual(ev.fraction, 1.00, places=4)
        self.assertEqual(ev.label, "limpando temporários  •  100%")


if __name__ == "__main__":
    unittest.main()
