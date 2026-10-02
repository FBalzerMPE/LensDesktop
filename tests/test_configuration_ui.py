from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from LensDesktop import app as desktop
from LensDesktop.processing import read_image_bgr
import test_chroma_ui as fixtures


class ConfigurationIntegrationTests(unittest.TestCase):
    setUp = fixtures.ChromaIntegrationTests.setUp
    tearDown = fixtures.ChromaIntegrationTests.tearDown
    wait_until = fixtures.ChromaIntegrationTests.wait_until
    displayed_rgb = fixtures.ChromaIntegrationTests.displayed_rgb

    @classmethod
    def setUpClass(cls):
        cls.application = desktop.QtWidgets.QApplication.instance() or desktop.QtWidgets.QApplication([])

    def enable_subject(self, keyed=True):
        native = np.full((48, 64, 3), (0, 255, 0), np.uint8)
        native[12:36, 24:40] = (0, 0, 220)
        self.window.static_source.set_frame(native)
        self.panel.key_enabled.setChecked(keyed)
        self.panel.configuration_enabled.setChecked(True)
        self.assertTrue(self.window.update_view())
        return native

    def test_opt_in_exclusive_radios_size_and_separate_reset(self):
        defaults = self.window.gui_defaults.configuration
        self.panel.configuration_enabled.setChecked(False)
        self.panel.configuration_size.setValue(10)
        self.panel.configuration_buttons["cross"].setChecked(True)
        self.assertFalse(self.panel.configuration_enabled.isChecked())
        self.assertFalse(self.panel.configuration_size.isEnabled())
        self.assertEqual(self.panel.configuration_size.value(), 10)
        self.assertEqual(self.panel.selected_configuration(), "cross")
        self.enable_subject()
        self.panel.configuration_buttons["fold"].click()
        self.assertEqual(self.panel.selected_configuration(), "fold")
        self.assertEqual(sum(button.isChecked() for button in self.panel.configuration_buttons.values()), 1)
        self.panel.configuration_size.setValue(30)
        self.assertEqual(self.panel.configuration_size_value.text(), "30%")
        post_placement = self.window._source_placement()
        self.panel.reset_configuration.click()
        self.assertEqual(self.panel.configuration_enabled.isChecked(), defaults.enabled)
        self.assertEqual(self.panel.selected_configuration(), defaults.preset)
        self.assertEqual(self.panel.configuration_size.value(), defaults.size)
        self.assertEqual(self.window._source_placement(), post_placement)

    def test_placement_changes_source_plane_not_sky_or_post_lens_settings(self):
        native = self.enable_subject()
        self.panel.source_scale.setValue(100)
        self.window.dual_checkbox.setChecked(True)
        self.panel.configuration_size.setValue(10)
        post_placement = self.window._source_placement()
        sky = self.window.background.image.copy()
        rgb, alpha = self.window._keyed_input(self.window.static_source.snapshot())
        first_rgb, first_alpha = self.window._configured_source(rgb, alpha)
        self.panel.configuration_buttons["cusp"].click()
        cusp_rgb, cusp_alpha = self.window._configured_source(rgb, alpha)
        self.assertFalse(np.array_equal(first_alpha, cusp_alpha))
        self.assertFalse(np.array_equal(first_rgb, cusp_rgb))
        self.panel.configuration_size.setValue(20)
        _, larger_alpha = self.window._configured_source(rgb, alpha)
        self.assertGreater(larger_alpha.sum(), cusp_alpha.sum() * 3)
        np.testing.assert_array_equal(self.window.background.image, sky)
        np.testing.assert_array_equal(self.window.static_source.snapshot(), native)
        self.assertEqual(self.window._source_placement(), post_placement)
        frame = self.displayed_rgb()
        np.testing.assert_array_equal(frame[0, 0], (23, 47, 83))
        np.testing.assert_array_equal(frame[0, -1], (23, 47, 83))

    def test_opaque_input_also_uses_transparent_pre_lens_placement(self):
        self.enable_subject(keyed=False)
        rgb, alpha = self.window._keyed_input(self.window.static_source.snapshot())
        self.assertEqual(alpha[alpha.shape[0] // 2, alpha.shape[1] // 2], 1)
        _, placed_alpha = self.window._configured_source(rgb, alpha)
        self.assertGreater(placed_alpha.sum(), 0)
        self.assertEqual(placed_alpha[0, 0], 0)
        self.assertTrue(self.window.update_view())

    def test_geometry_cache_follows_shape_not_radius_angle_or_canvas(self):
        with patch.object(desktop, "source_configuration_geometry", wraps=desktop.source_configuration_geometry) as geometry:
            self.enable_subject()
            self.assertEqual(geometry.call_count, 1)
            self.panel.configuration_buttons["cusp"].click()
            prepared = self.window._keyed_input(self.window.static_source.snapshot())
            original = self.window._configured_source(*prepared)
            self.window.slidert.setValue(70)
            rotated = self.window._configured_source(*prepared)
            self.assertFalse(np.array_equal(original[1], rotated[1]))
            self.window.sliderb.setValue(75)
            self.window.resize(900, 650)
            self.application.processEvents()
            self.window.update_view()
            self.assertEqual(geometry.call_count, 1)
            self.window.sliderq.setValue(70)
            self.window.update_view()
            self.assertEqual(geometry.call_count, 2)
            self.window.sliders.setValue(43)
            self.window.update_view()
            self.assertEqual(geometry.call_count, 3)

    def test_static_placement_cache_reused_but_invalidated_for_size(self):
        self.enable_subject()
        with patch.object(desktop, "place_source", wraps=desktop.place_source) as placement:
            self.window.update_view()
            self.assertEqual(placement.call_count, 0)
            self.panel.configuration_size.setValue(8)
            self.assertEqual(placement.call_count, 1)
            self.window.update_view()
            self.assertEqual(placement.call_count, 1)

    def test_degenerate_shape_is_reported_cached_and_stale_snapshot_blocked(self):
        self.enable_subject()
        with patch.object(desktop, "source_configuration_geometry", wraps=desktop.source_configuration_geometry) as geometry:
            self.window.sliders.setValue(99)
            self.assertFalse(self.window.update_view())
            self.assertFalse(self.window.update_view())
            self.assertEqual(geometry.call_count, 1)
        self.assertIn("Last image kept", self.panel.configuration_status.text())
        with patch.object(desktop.QtWidgets.QFileDialog, "getSaveFileName") as dialog:
            self.window.save_screenshot()
            self.window.recording()
            dialog.assert_not_called()
        self.window.sliders.setValue(41)
        self.assertTrue(self.window.update_view())
        self.assertNotIn("Last image kept", self.panel.configuration_status.text())

    def test_empty_source_nearly_circular_zero_mass_and_heart_fail_explicitly(self):
        self.panel.key_enabled.setChecked(True)
        self.panel.configuration_enabled.setChecked(True)
        self.assertFalse(self.window.update_view())
        self.assertIn("No visible source", self.panel.configuration_status.text())
        self.enable_subject()
        self.window.sliderq.setValue(99)
        self.assertFalse(self.window.update_view())
        self.assertIn("nearly circular", self.panel.configuration_status.text())
        self.window.sliderq.setValue(65)
        self.window.b_value = 0
        self.assertFalse(self.window.update_view())
        self.assertIn("positive Einstein radius", self.panel.configuration_status.text())
        self.window.b_value = 0.5
        self.window.heart = True
        self.assertFalse(self.window.update_view())
        self.assertIn("heart", self.panel.configuration_status.text())

    def test_inverse_disables_presets_without_discarding_selection(self):
        self.enable_subject()
        self.panel.configuration_buttons["fold"].click()
        self.window.inverse_checkbox.setChecked(True)
        self.assertTrue(self.window.update_view())
        self.assertFalse(self.panel.configuration_size.isEnabled())
        self.assertIn("only to forward", self.panel.configuration_status.text())
        with patch.object(self.window, "_configured_source") as placement:
            self.window.update_view()
            placement.assert_not_called()
        self.window.inverse_checkbox.setChecked(False)
        self.window.update_view()
        self.assertTrue(self.panel.configuration_size.isEnabled())
        self.assertEqual(self.panel.selected_configuration(), "fold")

    def test_calibration_preview_and_raw_export_remain_unplaced(self):
        native = self.enable_subject()
        self.panel.input_preview.setCurrentIndex(1)
        expected = self.displayed_rgb()
        self.panel.configuration_buttons["fold"].click()
        np.testing.assert_array_equal(self.displayed_rgb(), expected)
        self.assertIn("Calibration previews stay unplaced", self.panel.configuration_status.text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.png"
            with patch.object(desktop.QtWidgets.QFileDialog, "getSaveFileName", return_value=(str(path), "")):
                self.window.save_input_image()
            np.testing.assert_array_equal(read_image_bgr(path), native)
        self.panel.input_preview.setCurrentIndex(0)
        self.assertIn("Fold:", self.panel.configuration_status.text())

    def test_finite_source_and_resolution_warnings_are_explicit(self):
        self.enable_subject()
        self.panel.configuration_buttons["cusp"].click()
        self.panel.configuration_size.setValue(100)
        self.assertIn("cross the caustic", self.panel.configuration_status.text())
        self.window.b_value = 0.001
        self.window.update_view()
        self.assertIn("below two input samples", self.panel.configuration_status.text())

    def test_screenshot_and_positive_mass_sequence_restore_configuration(self):
        native = self.enable_subject()
        self.panel.configuration_buttons["fold"].click()
        radius = self.window.b_value
        linspace = np.linspace
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scene.png"
            with patch.object(desktop.QtWidgets.QFileDialog, "getSaveFileName", return_value=(str(path), "")):
                self.window.save_screenshot()
                self.assertEqual(desktop.QtGui.QImage(str(path)), self.window.label.pixmap().toImage())
                with patch.object(
                    desktop.np, "linspace",
                    side_effect=lambda start, stop, num: (
                        np.array([0, radius / 2, radius]) if start == 0 and stop == radius and num == 160
                        else linspace(start, stop, num)
                    ),
                ):
                    self.window.recording()
            self.assertTrue((Path(directory) / "scene_0000.png").exists())
            self.assertTrue((Path(directory) / "scene_0001.png").exists())
            self.assertFalse((Path(directory) / "scene_0002.png").exists())
            self.assertEqual(
                desktop.QtGui.QImage(str(Path(directory) / "scene_0001.png")),
                self.window.label.pixmap().toImage(),
            )
        self.assertEqual(self.window.b_value, radius)
        self.assertEqual(self.panel.selected_configuration(), "fold")
        self.assertIn("omits zero mass", self.panel.background_status.text())
        np.testing.assert_array_equal(self.window.static_source.snapshot(), native)


if __name__ == "__main__":
    unittest.main()
