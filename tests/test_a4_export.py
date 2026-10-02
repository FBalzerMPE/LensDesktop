from pathlib import Path
import os
import re
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from LensDesktop.a4_export import PAGE_SIZE_MM, PRINT_DPI, write_a4_pdf
from LensDesktop.processing import ChromaKeySettings, ImageError
from LensDesktop.qt_compat import QtGui, QtWidgets
from LensDesktop.scene import InputSettings, SceneSnapshot, sky_attribution


class A4PdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        if os.name == "nt" and not QtGui.QFontDatabase().families():
            for filename in ("segoeui.ttf", "segoeuib.ttf"):
                font = Path(os.environ["WINDIR"]) / "Fonts" / filename
                if QtGui.QFontDatabase.addApplicationFont(str(font)) < 0:
                    raise RuntimeError(f"Cannot load the Windows font for offscreen PDF tests: {font}")

    def snapshot(self):
        raw = np.full((48, 64, 3), (0, 255, 0), np.uint8)
        raw[12:36, 20:44] = (0, 0, 210)
        return SceneSnapshot(
            raw, np.full((64, 96, 3), (23, 47, 83), np.uint8),
            input=InputSettings(key=ChromaKeySettings(enabled=True), configuration="cross"),
        )

    def test_pdf_has_one_true_a4_page_and_print_resolution_images(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Erklärung.pdf"
            result = write_a4_pdf(self.snapshot(), path)
            data = path.read_bytes()
        self.assertTrue(data.startswith(b"%PDF-"))
        self.assertTrue(data.rstrip().endswith(b"%%EOF"))
        self.assertEqual(len(re.findall(rb"/Type\s*/Page\b", data)), 1)
        match = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]", data)
        self.assertIsNotNone(match)
        for points, millimeters in zip(match.groups(), PAGE_SIZE_MM):
            self.assertAlmostEqual(float(points) * 25.4 / 72, millimeters, delta=0.15)
        self.assertEqual(PRINT_DPI, 300)
        self.assertGreaterEqual(result.source.rgb.shape[0], 62 / 25.4 * PRINT_DPI)
        self.assertGreaterEqual(result.montage.shape[1], 186 / 25.4 * PRINT_DPI)
        self.assertGreaterEqual(data.count(b"/Subtype /Image"), 7)

    def test_write_error_is_explicit_and_failed_render_preserves_existing_pdf(self):
        snapshot = self.snapshot()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ImageError, "Cannot"):
                write_a4_pdf(snapshot, Path(directory) / "missing" / "page.pdf")
            path = Path(directory) / "page.pdf"
            path.write_bytes(b"existing file")
            with patch("LensDesktop.a4_export.render_snapshot", side_effect=ImageError("bad source")):
                with self.assertRaisesRegex(ImageError, "bad source"):
                    write_a4_pdf(snapshot, path)
            self.assertEqual(path.read_bytes(), b"existing file")
            with patch("LensDesktop.a4_export.paint_a4_page", side_effect=ImageError("bad caption")):
                with self.assertRaisesRegex(ImageError, "bad caption"):
                    write_a4_pdf(snapshot, path)
            self.assertEqual(path.read_bytes(), b"existing file")
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_default_and_custom_attribution_are_not_confused(self):
        data = Path(__file__).resolve().parent.parent / "data"
        known = sky_attribution(data / "euclid_abell_2764_example.jpeg")
        self.assertIn("Abell 2764", known.title)
        self.assertIn("Cuillandre", known.credit)
        self.assertEqual(known.license, "CC BY-SA 3.0 IGO")
        custom = sky_attribution(Path("somewhere") / "euclid_abell_2764_example.jpeg")
        self.assertIn("Eigener Hintergrund", custom.credit)
        self.assertFalse(custom.license)
        self.assertFalse(sky_attribution(None).source_url)


if __name__ == "__main__":
    unittest.main()
