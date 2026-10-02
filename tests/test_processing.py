from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from LensDesktop import processing


class BackgroundProcessingTests(unittest.TestCase):
    def test_bundled_default_exists_and_loads_as_rgb(self):
        background = processing.SkyBackground()
        background.load(processing.default_background_path())
        self.assertEqual(background.path.name, "euclid_abell_2764_example.jpeg")
        self.assertEqual(background.image.dtype, np.uint8)
        self.assertEqual(background.image.shape[2], 3)
        self.assertTrue(background.image.flags.c_contiguous)

    def test_unicode_path_and_failed_load_preserve_previous_image(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ("sky-" + chr(0x03B1) + ".png")
            image = np.full((4, 8, 3), (10, 70, 190), np.uint8)
            ok, encoded = cv2.imencode(".png", image)
            self.assertTrue(ok)
            path.write_bytes(encoded.tobytes())
            background = processing.SkyBackground()
            background.load(path)
            np.testing.assert_array_equal(background.image[0, 0], (190, 70, 10))
            previous = background.image
            invalid = Path(directory) / "invalid.jpg"
            invalid.write_bytes(b"not an image")
            for bad_path in (invalid, Path(directory) / "missing.png"):
                with self.assertRaises(processing.ImageError):
                    background.load(bad_path)
                self.assertIs(background.image, previous)
                self.assertEqual(background.path, path)

    def test_fit_and_fill_preserve_aspect_ratio(self):
        wide = np.full((4, 8, 3), 180, np.uint8)
        fitted = processing.fit_background(wide, 8, 8, "fit")
        np.testing.assert_array_equal(fitted[:2], 0)
        np.testing.assert_array_equal(fitted[2:6], 180)
        np.testing.assert_array_equal(fitted[6:], 0)
        filled = processing.fit_background(wide, 8, 8, "fill")
        np.testing.assert_array_equal(filled, 180)

    def test_cache_is_reused_and_clear_invalidates_it(self):
        background = processing.SkyBackground()
        background.load(processing.default_background_path())
        first = background.fitted(40, 40, "fill")
        self.assertIs(background.fitted(40, 40, "fill"), first)
        self.assertIsNot(background.fitted(50, 50, "fill"), first)
        background.clear()
        self.assertIsNone(background.image)
        self.assertIsNone(background.path)
        np.testing.assert_array_equal(background.fitted(40, 40, "fill"), 0)

    def test_transparent_and_black_layers_are_not_confused(self):
        sky = np.full((20, 20, 3), (30, 90, 180), np.uint8)
        black = np.zeros_like(sky)
        for opacity in (0, 1):
            alpha = np.full((20, 20), opacity, np.float32)
            result = processing.place_layer(black, alpha, sky)
            np.testing.assert_array_equal(result, sky if opacity == 0 else black)

    def test_size_and_offset_are_post_transform_and_leave_sky_unchanged(self):
        sky = np.full((20, 20, 3), (30, 90, 180), np.uint8)
        foreground = np.full_like(sky, (200, 50, 10))
        alpha = np.ones((20, 20), np.float32)
        before = sky.copy()
        result = processing.place_layer(foreground, alpha, sky, scale=0.5, x=0.25)
        np.testing.assert_array_equal(result[8:12, 12:16], foreground[8:12, 12:16])
        np.testing.assert_array_equal(result[:, :8], sky[:, :8])
        np.testing.assert_array_equal(sky, before)
        self.assertEqual(processing.unplace_point(15, 10, 20, 20, 0.5, 0.25, 0), (10, 10))
        self.assertIsNone(processing.unplace_point(2, 10, 20, 20, 0.5, 0.25, 0))

    def test_fully_offscreen_layer_shows_only_sky(self):
        sky = np.full((20, 20, 3), (30, 90, 180), np.uint8)
        foreground = np.full_like(sky, (200, 50, 10))
        result = processing.place_layer(
            foreground, np.ones((20, 20), np.float32), sky, scale=0.25, x=1
        )
        np.testing.assert_array_equal(result, sky)

    def test_premultiplied_soft_edges_blend_without_black_halos(self):
        sky = np.full((20, 20, 3), 100, np.uint8)
        alpha = np.full((20, 20), 0.5, np.float32)
        foreground = np.full_like(sky, 100)
        result = processing.place_layer(foreground, alpha, sky)
        np.testing.assert_array_equal(result, 150)

    def test_invalid_fitting_or_placement_is_not_silently_accepted(self):
        background = processing.SkyBackground()
        with self.assertRaises(processing.ImageError):
            background.fitted(10, 10, "stretch")
        with self.assertRaises(processing.ImageError):
            background.fitted(0, 10, "fit")
        with self.assertRaises(ValueError):
            processing.placement_matrix(10, 10, 0, 0, 0)


if __name__ == "__main__":
    unittest.main()
