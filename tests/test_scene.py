from dataclasses import replace
import unittest

import cv2
import numpy as np

from LensDesktop.lensing import draw_lens_light
from LensDesktop.processing import ChromaKeySettings, ImageError, fit_background, place_layer
from LensDesktop.scene import DisplaySettings, InputSettings, LensSettings, SceneSnapshot, render_snapshot


class SceneTests(unittest.TestCase):
    def snapshot(self, **changes):
        raw = np.full((48, 64, 3), (0, 255, 0), np.uint8)
        raw[12:36, 20:44] = (0, 0, 210)
        sky = np.full((60, 90, 3), (23, 47, 83), np.uint8)
        arguments = dict(
            raw_bgr=raw, sky_rgb=sky, lens=LensSettings(),
            input=InputSettings(key=ChromaKeySettings(enabled=True), configuration="cross"),
            display=DisplaySettings(),
        )
        arguments.update(changes)
        return SceneSnapshot(**arguments)

    def test_snapshot_detaches_arrays_and_settings(self):
        raw = np.zeros((16, 16, 3), np.uint8)
        sky = raw.copy()
        snapshot = self.snapshot(raw_bgr=raw, sky_rgb=sky)
        raw[:] = 255
        sky[:] = 100
        np.testing.assert_array_equal(snapshot.raw_bgr, 0)
        np.testing.assert_array_equal(snapshot.sky_rgb, 0)
        self.assertFalse(snapshot.raw_bgr.flags.writeable)
        self.assertFalse(snapshot.sky_rgb.flags.writeable)

    def test_five_panels_are_rerendered_and_native_raw_is_unchanged(self):
        snapshot = self.snapshot()
        result = render_snapshot(snapshot, side=128, montage_size=(240, 100))
        np.testing.assert_array_equal(result.raw_rgb, cv2.cvtColor(snapshot.raw_bgr, cv2.COLOR_BGR2RGB))
        for layer in (result.cleaned, result.source, result.lensed):
            self.assertEqual(layer.rgb.shape, (128, 128, 3))
            self.assertEqual(layer.alpha.shape, (128, 128))
            self.assertFalse(layer.rgb.flags.writeable)
            self.assertFalse(layer.alpha.flags.writeable)
            self.assertTrue(np.all(layer.rgb <= layer.alpha[..., None] * 255 + 0.001))
        self.assertEqual(result.montage.shape, (100, 240, 3))
        self.assertEqual(result.montage.dtype, np.uint8)
        self.assertTrue(result.critical_curves)
        self.assertTrue(result.caustic_curves)
        self.assertGreater(result.cleaned.alpha.sum(), result.source.alpha.sum())

    def test_montage_uses_current_sky_placement_and_keeps_black_opaque(self):
        snapshot = self.snapshot(
            raw_bgr=np.zeros((32, 32, 3), np.uint8),
            input=InputSettings(configuration="cross"),
            display=DisplaySettings(scale=0.5, offset_x=0.25),
        )
        result = render_snapshot(snapshot, side=128, montage_size=(128, 128))
        with_light = render_snapshot(
            replace(snapshot, display=replace(snapshot.display, lens_light=True)),
            side=128,
            montage_size=(128, 128),
        )
        expected = place_layer(
            with_light.lensed.rgb, with_light.lensed.alpha,
            fit_background(snapshot.sky_rgb, 128, 128, "fill"),
            scale=0.5, x=0.25,
        )
        np.testing.assert_array_equal(result.montage, expected)
        self.assertGreater(np.count_nonzero(result.source.alpha), 0)
        np.testing.assert_array_equal(result.source.rgb, 0)

    def test_lens_light_is_softened_whiter_and_fades_outward(self):
        image = np.zeros((1, 3, 3), np.float32)
        kappa = np.array([[1e6, 1, 0.01]], np.float32)
        tinted = draw_lens_light(0.5, kappa, image, 3, 1)
        center, middle, outside = tinted[0]
        self.assertLess(center[0], 255)
        self.assertLess(center[0] - center[2], 20)
        self.assertGreater(center[0], middle[0])
        self.assertGreater(middle[0], outside[0])
        self.assertLess(outside[0] / 255, np.log10(1 + kappa[0, 2]))

    def test_current_input_and_lens_settings_affect_result_not_original(self):
        snapshot = self.snapshot()
        result = render_snapshot(snapshot, side=128, montage_size=(128, 128))
        changed = replace(
            snapshot,
            input=replace(snapshot.input, zoom=200, mirror=True, configuration="cusp", size_percent=4),
            lens=replace(snapshot.lens, angle=0.9, radius=0.65),
        )
        other = render_snapshot(changed, side=128, montage_size=(128, 128))
        np.testing.assert_array_equal(result.raw_rgb, other.raw_rgb)
        self.assertFalse(np.array_equal(result.source.alpha, other.source.alpha))
        self.assertFalse(np.array_equal(result.lensed.rgb, other.lensed.rgb))

    def test_overlays_follow_display_settings_without_mutating_snapshot(self):
        snapshot = self.snapshot()
        plain = render_snapshot(snapshot, side=128, montage_size=(128, 128))
        overlaid = render_snapshot(
            replace(snapshot, display=DisplaySettings(
                lens_light=True, curves=True, source_markers=((0.5, 0.5),), marker_radius=0.03,
            )),
            side=128, montage_size=(128, 128),
        )
        self.assertFalse(np.array_equal(plain.lensed.rgb, overlaid.lensed.rgb))
        self.assertFalse(np.array_equal(plain.montage, overlaid.montage))
        self.assertFalse(snapshot.raw_bgr.flags.writeable)

    def test_montage_lens_light_is_independent_of_diagnostic_toggle(self):
        snapshot = self.snapshot()
        without_toggle = render_snapshot(snapshot, side=128, montage_size=(128, 128))
        with_toggle = render_snapshot(
            replace(snapshot, display=replace(snapshot.display, lens_light=True)),
            side=128,
            montage_size=(128, 128),
        )
        np.testing.assert_array_equal(without_toggle.montage, with_toggle.montage)
        self.assertFalse(np.array_equal(without_toggle.lensed.rgb, with_toggle.lensed.rgb))

    def test_empty_subject_and_invalid_configurations_fail(self):
        with self.assertRaisesRegex(ImageError, "No visible"):
            render_snapshot(self.snapshot(raw_bgr=np.full((32, 32, 3), (0, 255, 0), np.uint8)), side=128)
        with self.assertRaisesRegex(ImageError, "nearly circular"):
            render_snapshot(self.snapshot(lens=LensSettings(axis_ratio=0.99)), side=128)
        with self.assertRaisesRegex(ImageError, "positive"):
            render_snapshot(self.snapshot(lens=LensSettings(radius=0)), side=128)

    def test_no_sky_zero_mass_and_no_configuration_are_supported(self):
        snapshot = self.snapshot(sky_rgb=None, lens=LensSettings(radius=0), input=InputSettings())
        result = render_snapshot(snapshot, side=128, montage_size=(128, 128))
        self.assertFalse(result.critical_curves)
        self.assertFalse(result.caustic_curves)
        self.assertEqual(result.montage.shape, (128, 128, 3))

    def test_invalid_data_settings_and_resolution_fail_explicitly(self):
        with self.assertRaises(ImageError):
            self.snapshot(raw_bgr=np.zeros((10, 10), np.uint8))
        with self.assertRaises(ImageError):
            LensSettings(axis_ratio=1)
        with self.assertRaises(ImageError):
            InputSettings(zoom=99)
        with self.assertRaises(ImageError):
            DisplaySettings(scale=0)
        with self.assertRaises(ImageError):
            render_snapshot(self.snapshot(), side=31)
        with self.assertRaises(ImageError):
            render_snapshot(self.snapshot(), side=129)


if __name__ == "__main__":
    unittest.main()
