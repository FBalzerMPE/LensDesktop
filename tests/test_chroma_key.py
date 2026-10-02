import unittest

import cv2
import numpy as np

from LensDesktop.processing import (
    ChromaKeySettings, ImageError, chroma_key, example_source_path,
    fit_layer, read_image_bgr, remap_layer,
)


class ChromaKeyTests(unittest.TestCase):
    def test_disabled_key_preserves_colors_and_opaque_black(self):
        frame = np.array([[[0, 255, 0], [0, 0, 0], [100, 120, 180]]], np.uint8)
        color, alpha = chroma_key(frame, ChromaKeySettings())
        np.testing.assert_array_equal(color, frame[..., ::-1])
        np.testing.assert_array_equal(alpha, 1)

    def test_green_is_removed_but_skin_black_and_gray_are_retained(self):
        frame = np.array([[[0, 255, 0], [0, 0, 0], [120, 120, 120], [100, 120, 180]]], np.uint8)
        color, alpha = chroma_key(frame, ChromaKeySettings(enabled=True))
        np.testing.assert_array_equal(alpha, [[0, 1, 1, 1]])
        np.testing.assert_array_equal(color[0, 0], 0)
        np.testing.assert_array_equal(color[0, 3], [180, 120, 100])

    def test_hue_wrap_and_softness_produce_bounded_premultiplied_edges(self):
        hsv = np.array([[[179, 255, 255], [0, 255, 255], [12, 255, 255], [25, 255, 255]]], np.uint8)
        frame = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        color, alpha = chroma_key(
            frame, ChromaKeySettings(enabled=True, color=(255, 0, 0), tolerance=10, softness=30, spill=0)
        )
        np.testing.assert_array_equal(alpha[0, :2], 0)
        self.assertGreater(alpha[0, 2], 0)
        self.assertLess(alpha[0, 2], 1)
        self.assertEqual(alpha[0, 3], 1)
        self.assertTrue(np.all(color <= alpha[..., None] * 255))

    def test_spill_suppression_reduces_green_without_changing_alpha_or_source(self):
        frame = cv2.cvtColor(np.array([[[48, 200, 200]]], np.uint8), cv2.COLOR_HSV2BGR)
        original = frame.copy()
        settings = dict(enabled=True, tolerance=30, softness=30)
        untreated, alpha = chroma_key(frame, ChromaKeySettings(**settings, spill=0))
        treated, treated_alpha = chroma_key(frame, ChromaKeySettings(**settings, spill=1))
        np.testing.assert_array_equal(treated_alpha, alpha)
        self.assertLess(treated[0, 0, 1], untreated[0, 0, 1])
        np.testing.assert_array_equal(frame, original)

    def test_fit_fill_and_mirror_transform_color_and_alpha_together(self):
        alpha = np.array([[1, 0], [1, 0], [1, 0], [1, 0]], np.float32)
        color = np.full((4, 2, 3), 200, np.float32) * alpha[..., None]
        fitted, fitted_alpha = fit_layer(color, alpha, 8, 8, "fit", mirror=True)
        np.testing.assert_array_equal(fitted_alpha[:, :2], 0)
        np.testing.assert_array_equal(fitted_alpha[:, -2:], 0)
        np.testing.assert_allclose(fitted, fitted_alpha[..., None] * np.full((8, 8, 3), 200))
        filled, filled_alpha = fit_layer(color, alpha, 8, 8, "fill")
        self.assertEqual(filled.shape, (8, 8, 3))
        self.assertEqual(filled_alpha.shape, (8, 8))

    def test_fractional_remapping_has_no_green_or_dark_halo(self):
        color = np.array([[[255, 0, 0], [0, 0, 0]]], np.float32)
        alpha = np.array([[1, 0]], np.float32)
        mapped, coverage = remap_layer(
            color, alpha, np.array([[0.5, -10]], np.float32), np.zeros((1, 2), np.float32)
        )
        np.testing.assert_allclose(coverage, [[0.5, 0]])
        np.testing.assert_allclose(mapped, [[[127.5, 0, 0], [0, 0, 0]]])

    def test_hand_example_removes_cloth_and_preserves_skin_with_defaults(self):
        frame = read_image_bgr(example_source_path())
        original = frame.copy()
        color, alpha = chroma_key(frame, ChromaKeySettings(enabled=True))
        cloth = alpha[40:300, 700:1100]
        skin = alpha[740:840, 430:500]
        shadowed_arm = alpha[850:950, 50:150]
        self.assertGreater(np.mean(cloth < 0.01), 0.99)
        self.assertGreater(np.mean(skin > 0.99), 0.99)
        self.assertGreater(np.mean(shadowed_arm > 0.99), 0.99)
        self.assertTrue(np.all(color <= alpha[..., None] * 255 + 0.001))
        np.testing.assert_array_equal(frame, original)

    def test_invalid_settings_fail_explicitly(self):
        for kwargs in ({"tolerance": -1}, {"softness": float("nan")}, {"spill": 2},
                       {"saturation": -0.1}, {"color": (256, 0, 0)}):
            with self.assertRaises(ImageError):
                ChromaKeySettings(**kwargs)
        with self.assertRaises(ImageError):
            chroma_key(np.zeros((1, 1, 3), np.uint8),
                       ChromaKeySettings(enabled=True, color=(0, 0, 0)))


if __name__ == "__main__":
    unittest.main()
