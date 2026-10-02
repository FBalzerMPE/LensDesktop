from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from LensDesktop.processing import ImageError, example_source_path, read_image_bgr, write_image_bgr
from LensDesktop.sources import SourceError, StaticSource, frame_for_canvas


class StaticSourceTests(unittest.TestCase):
    def test_sample_loads_at_native_resolution_without_mirroring(self):
        expected = cv2.imdecode(
            np.frombuffer(example_source_path().read_bytes(), np.uint8), cv2.IMREAD_COLOR
        )
        source = StaticSource()
        source.load(example_source_path())
        np.testing.assert_array_equal(source.snapshot(), expected)
        self.assertFalse(source.mirror)
        self.assertEqual(source.path, example_source_path())

    def test_freeze_owns_frame_and_snapshot_copies_cannot_change_it(self):
        frame = np.full((4, 6, 3), (10, 70, 190), np.uint8)
        source = StaticSource()
        source.set_frame(frame, mirror=True)
        frame[:] = 0
        snapshot = source.snapshot()
        np.testing.assert_array_equal(snapshot[0, 0], (10, 70, 190))
        snapshot[:] = 0
        np.testing.assert_array_equal(source.snapshot()[0, 0], (10, 70, 190))
        self.assertTrue(source.mirror)

    def test_portrait_fit_preserves_entire_image_and_native_data(self):
        frame = np.full((8, 4, 3), (10, 70, 190), np.uint8)
        source = StaticSource()
        source.set_frame(frame)
        rendered = source.render_frame(4, 4, "fit")
        self.assertEqual(rendered.shape, (8, 8, 3))
        np.testing.assert_array_equal(rendered[:, :2], 0)
        np.testing.assert_array_equal(rendered[:, 2:6], np.full((8, 4, 3), (10, 70, 190), np.uint8))
        np.testing.assert_array_equal(source.snapshot(), frame)

    def test_frozen_camera_fill_matches_live_framing(self):
        frame = np.arange(8 * 12 * 3, dtype=np.uint8).reshape(8, 12, 3)
        source = StaticSource()
        source.set_frame(frame, mirror=True)
        np.testing.assert_array_equal(
            source.render_frame(3, 3, "fill"), frame_for_canvas(frame, 3, 3, camera=True)
        )

    def test_cached_render_copies_are_safe_for_markers(self):
        source = StaticSource()
        source.set_frame(np.full((8, 4, 3), 180, np.uint8))
        first = source.render_frame(4, 4, "fit")
        cached = source._cache
        first[:] = 0
        second = source.render_frame(4, 4, "fit")
        self.assertIs(source._cache, cached)
        self.assertTrue(np.any(second))
        source.render_frame(5, 5, "fit")
        self.assertIsNot(source._cache, cached)

    def test_failed_load_and_invalid_freeze_preserve_previous_frame(self):
        source = StaticSource()
        original = np.full((8, 4, 3), 180, np.uint8)
        source.set_frame(original)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ImageError):
                source.load(Path(directory) / "missing.jpeg")
        with self.assertRaises(SourceError):
            source.set_frame(None)
        np.testing.assert_array_equal(source.snapshot(), original)

    def test_empty_source_reports_missing_frame(self):
        source = StaticSource()
        with self.assertRaises(SourceError):
            source.snapshot()
        with self.assertRaises(SourceError):
            source.render_frame(4, 4, "fit")

    def test_unicode_png_export_keeps_native_pixels_and_colors(self):
        frame = np.arange(8 * 12 * 3, dtype=np.uint8).reshape(8, 12, 3)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ("input-" + chr(0x03B1) + ".png")
            write_image_bgr(path, frame)
            np.testing.assert_array_equal(read_image_bgr(path), frame)

    def test_unsupported_and_unwritable_exports_are_explicit(self):
        frame = np.zeros((4, 4, 3), np.uint8)
        with tempfile.TemporaryDirectory() as directory:
            for path in (Path(directory) / "input.txt", Path(directory) / "missing" / "input.png"):
                with self.subTest(path=path):
                    with self.assertRaises(ImageError):
                        write_image_bgr(path, frame)


if __name__ == "__main__":
    unittest.main()
