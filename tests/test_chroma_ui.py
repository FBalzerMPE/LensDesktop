from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np

from LensDesktop import app as desktop
from LensDesktop.processing import ChromaKeySettings, read_image_bgr
from test_sources import FakeCapture


class KeyedInverseTests(unittest.TestCase):
    def test_inverse_averages_color_and_alpha_with_identical_counts(self):
        alpha = np.array([[1, 1, 0], [1, 0, 0], [1, 0, 0]], np.float32)
        color = np.zeros((3, 3, 3), np.float32)
        color[..., 0] = 200 * alpha
        indices = np.zeros(9, int)
        image, coverage = desktop.inverse_remap_image(
            color, indices, indices, 0, 3, 3, input_alpha=alpha,
        )
        np.testing.assert_array_equal(image[0, 0], [100, 0, 0])
        self.assertEqual(coverage[0, 0], 0.5)
        np.testing.assert_array_equal(image[1:], 0)
        np.testing.assert_array_equal(coverage[1:], 0)

    def test_inverse_preserves_black_coverage_and_makes_excluded_pixels_transparent(self):
        xx, yy = np.meshgrid(np.arange(3), np.arange(3))
        image, alpha = desktop.inverse_remap_image(
            np.zeros((3, 3, 3), np.float32), xx.ravel(), yy.ravel(), 0, 3, 3,
            input_alpha=np.ones((3, 3), np.float32),
        )
        self.assertEqual(alpha[0, 0], 1)
        self.assertEqual(alpha[1, 1], 0)
        np.testing.assert_array_equal(image, 0)


class ChromaIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = desktop.QtWidgets.QApplication.instance() or desktop.QtWidgets.QApplication([])

    def setUp(self):
        self.capture_patch = patch.object(
            desktop.LensDesktop, "capture_screen_rect",
            lambda window: np.full((32, 32, 3), (0, 255, 0), np.uint8),
        )
        self.capture_patch.start()
        self.exclusion_patch = patch.object(desktop, "exclude_from_capture", return_value=True)
        self.exclusion_patch.start()
        self.window = desktop.LensDesktop()
        self.window.timer.stop()
        self.window.resize(700, 500)
        self.window.show()
        self.application.processEvents()
        self.panel = self.window.settings_panel
        self.panel.key_enabled.setChecked(False)
        self.panel.configuration_enabled.setChecked(False)
        self.window.dual_checkbox.setChecked(False)
        self.window.critical_checkbox.setChecked(False)
        self.window.lenslight_checkbox.setChecked(False)
        self.window._configuration_geometry_cache = None
        self.window._configured_source_cache = None
        self.window.static_source.set_frame(np.full((32, 32, 3), (0, 255, 0), np.uint8))
        self.window._activate_static_source()
        self.window.background.clear()
        self.window.background.image = np.full((5, 5, 3), (23, 47, 83), np.uint8)

    def tearDown(self):
        self.window.close()
        self.wait_until(lambda: not self.window.camera_worker.isRunning())
        self.capture_patch.stop()
        self.exclusion_patch.stop()

    def wait_until(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            self.application.processEvents()
            time.sleep(0.005)
        self.application.processEvents()
        self.assertTrue(predicate(), "Camera transition timed out")

    def displayed_rgb(self):
        image = self.window.label.pixmap().toImage().convertToFormat(desktop.QtGui.QImage.Format_RGB888)
        pointer = image.bits()
        pointer.setsize(image.byteCount())
        data = np.frombuffer(pointer, np.uint8).reshape(image.height(), image.bytesPerLine())
        return data[:, :image.width() * 3].reshape(image.height(), image.width(), 3).copy()

    def test_keying_is_opt_in_and_disabled_controls_explain_parameters(self):
        self.assertFalse(self.panel.key_enabled.isChecked())
        self.assertFalse(self.panel.key_tolerance.isEnabled())
        self.assertTrue(self.panel.key_tolerance.toolTip())
        self.window.update_view()
        self.assertFalse(np.all(self.displayed_rgb() == (23, 47, 83)))
        self.panel.key_enabled.setChecked(True)
        self.assertTrue(self.panel.key_tolerance.isEnabled())

    def test_fully_green_input_reveals_exact_unchanged_sky_in_all_modes(self):
        self.panel.key_enabled.setChecked(True)
        for dual in (False, True):
            self.window.dual_checkbox.setChecked(dual)
            for inverse in (False, True):
                self.window.inverse_checkbox.setChecked(inverse)
                self.assertTrue(self.window.update_view())
                np.testing.assert_array_equal(
                    self.displayed_rgb(), np.full(self.displayed_rgb().shape, (23, 47, 83), np.uint8)
                )
        self.window._clear_background()
        np.testing.assert_array_equal(self.displayed_rgb(), 0)

    def test_desktop_keying_uses_same_transparent_pipeline(self):
        self.window._use_desktop()
        self.panel.key_enabled.setChecked(True)
        np.testing.assert_array_equal(
            self.displayed_rgb(), np.full(self.displayed_rgb().shape, (23, 47, 83), np.uint8)
        )

    def test_webcam_keying_freeze_and_resume_preserve_composed_pixels_and_native_frame(self):
        native = np.full((24, 32, 3), (0, 255, 0), np.uint8)
        native[:, :12] = (0, 0, 200)
        captures = []

        def factory(index):
            capture = FakeCapture(frame=native.copy())
            captures.append(capture)
            return capture

        self.window.camera_worker._capture_factory = factory
        self.panel.key_enabled.setChecked(True)
        self.panel.open_camera.click()
        self.wait_until(lambda: self.window.cam)
        self.window.update_view()
        live = self.displayed_rgb()
        self.panel.freeze_input.click()
        self.wait_until(lambda: captures[0].released)
        np.testing.assert_array_equal(self.displayed_rgb(), live)
        np.testing.assert_array_equal(self.window.static_source.snapshot(), native)
        self.panel.freeze_input.click()
        self.wait_until(lambda: self.window.cam)
        np.testing.assert_array_equal(self.displayed_rgb(), live)
        self.window._use_desktop()
        self.wait_until(lambda: captures[-1].released)

    def test_source_and_mask_previews_do_not_change_lens_parameters_or_native_data(self):
        self.window._load_input_example()
        native = self.window.static_source.snapshot()
        radius = self.window.b_value
        self.panel.key_enabled.setChecked(True)
        self.panel.input_preview.setCurrentIndex(1)
        source = self.displayed_rgb()
        self.panel.input_preview.setCurrentIndex(2)
        mask = self.displayed_rgb()
        np.testing.assert_array_equal(mask[..., 0], mask[..., 1])
        np.testing.assert_array_equal(mask[..., 0], mask[..., 2])
        self.assertGreater(np.mean(mask == 0), 0.5)
        self.assertFalse(np.array_equal(source, mask))
        self.assertEqual(self.window.b_value, radius)
        np.testing.assert_array_equal(self.window.static_source.snapshot(), native)

    def test_static_processing_cache_is_reused_for_lens_changes_but_not_key_changes(self):
        self.panel.key_enabled.setChecked(True)
        cache = self.window._keyed_input_cache
        self.assertFalse(cache[2].flags.writeable)
        self.assertFalse(cache[3].flags.writeable)
        with patch("LensDesktop.processing.chroma_key", wraps=desktop.chroma_key) as key:
            self.window.sliderb.setValue(80)
            self.window.update_view()
            key.assert_not_called()
            self.assertIs(self.window._keyed_input_cache, cache)
            self.panel.key_tolerance.setValue(45)
            self.assertEqual(key.call_count, 1)

    def test_mirroring_moves_both_color_and_mask(self):
        frame = np.full((32, 32, 3), (0, 255, 0), np.uint8)
        frame[:, :8] = (0, 0, 200)
        self.window.static_source.set_frame(frame)
        self.panel.key_enabled.setChecked(True)
        original, alpha = self.window._keyed_input(self.window.static_source.frame)
        self.panel.input_mirror.setCurrentIndex(2)
        mirrored, mirrored_alpha = self.window._keyed_input(self.window.static_source.frame)
        np.testing.assert_array_equal(mirrored, original[:, ::-1])
        np.testing.assert_array_equal(mirrored_alpha, alpha[:, ::-1])

    def test_markers_curves_and_lens_light_remain_visible_over_removed_green(self):
        self.panel.key_enabled.setChecked(True)
        sky = (23, 47, 83)
        self.window.ellipses_source_plane = [(self.window.base_w / 2, self.window.base_h / 2)]
        self.window.dual_checkbox.setChecked(True)
        cached_alpha = self.window._keyed_input_cache[3].copy()
        self.window.update_view()
        np.testing.assert_array_equal(self.window._keyed_input_cache[3], cached_alpha)
        self.assertTrue(np.any(self.displayed_rgb()[:, :self.window.base_w] != sky))
        self.window.ellipses_source_plane = []
        self.window.dual_checkbox.setChecked(False)
        self.window.lenslight_checkbox.setChecked(True)
        self.window.update_view()
        self.assertTrue(np.any(self.displayed_rgb() != sky))
        self.window.lenslight_checkbox.setChecked(False)
        self.window.critical_checkbox.setChecked(True)
        self.window.update_view()
        self.assertTrue(np.any(self.displayed_rgb() != sky))

    def test_keyed_sequence_exports_composed_scene_and_restores_lens_radius(self):
        self.panel.key_enabled.setChecked(True)
        self.window.inverse_checkbox.setChecked(True)
        radius = self.window.b_value
        linspace = np.linspace
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sequence.png"
            with (
                patch.object(desktop.QtWidgets.QFileDialog, "getSaveFileName", return_value=(str(path), "")),
                patch.object(
                    desktop.np, "linspace",
                    side_effect=lambda start, stop, num: (
                        np.array([0, radius]) if start == 0 and stop == radius and num == 160
                        else linspace(start, stop, num)
                    ),
                ),
            ):
                self.window.recording()
            for index in range(2):
                saved = read_image_bgr(Path(directory) / f"sequence_{index:04d}.png")[..., ::-1]
                np.testing.assert_array_equal(saved, np.full(saved.shape, (23, 47, 83), np.uint8))
        self.assertEqual(self.window.b_value, radius)

    def test_reset_restores_defaults_without_discarding_source(self):
        self.panel.key_enabled.setChecked(True)
        frame = self.window.static_source.frame
        self.panel.key_tolerance.setValue(65)
        self.panel.key_color_rgb = (255, 0, 0)
        self.panel.input_mirror.setCurrentIndex(2)
        self.panel.input_preview.setCurrentIndex(2)
        self.panel.reset_input.click()
        self.assertEqual(
            self.panel.chroma_settings(),
            self.window.gui_defaults.input.key,
        )
        self.assertEqual(self.panel.input_preview.currentData(), "scene")
        self.assertEqual(self.panel.input_mirror.currentData(), "default")
        self.assertIs(self.window.static_source.frame, frame)
        self.assertEqual(
            self.panel.key_color.isEnabled(),
            self.window.gui_defaults.input.key.enabled,
        )

    def test_color_dialog_cancel_and_invalid_gray_keep_previous_color(self):
        self.panel.key_enabled.setChecked(True)
        previous = self.panel.key_color_rgb
        for color in (desktop.QtGui.QColor(), desktop.QtGui.QColor(100, 100, 100)):
            with patch.object(desktop.QtWidgets.QColorDialog, "getColor", return_value=color):
                self.panel.key_color.click()
            self.assertEqual(self.panel.key_color_rgb, previous)
        self.assertIn("saturated", self.panel.source_status.text())
        with patch.object(desktop.QtWidgets.QColorDialog, "getColor", return_value=desktop.QtGui.QColor("blue")):
            self.panel.key_color.click()
        self.assertEqual(self.panel.key_color_rgb, (0, 0, 255))

    def test_calibration_previews_do_not_create_misplaced_markers(self):
        self.panel.input_preview.setCurrentIndex(2)
        event = desktop.QtGui.QMouseEvent(
            desktop.QtCore.QEvent.MouseButtonPress, desktop.QtCore.QPointF(20, 20),
            desktop.QtCore.Qt.RightButton, desktop.QtCore.Qt.RightButton,
            desktop.QtCore.Qt.NoModifier,
        )
        self.application.sendEvent(self.window.label, event)
        self.assertFalse(self.window.ellipses_source_plane)
        self.assertFalse(self.window.ellipses_image_plane)
        self.assertIn("Composed scene", self.panel.source_status.text())

    def test_keyed_screenshot_and_raw_export_remain_distinct(self):
        native = self.window.static_source.snapshot()
        self.panel.key_enabled.setChecked(True)
        with tempfile.TemporaryDirectory() as directory:
            scene_path = Path(directory) / "scene.png"
            raw_path = Path(directory) / "raw.png"
            with patch.object(
                desktop.QtWidgets.QFileDialog, "getSaveFileName", return_value=(str(scene_path), "")
            ):
                self.window.save_screenshot()
            np.testing.assert_array_equal(read_image_bgr(scene_path)[..., ::-1], self.displayed_rgb())
            with patch.object(
                desktop.QtWidgets.QFileDialog, "getSaveFileName", return_value=(str(raw_path), "")
            ):
                self.window.save_input_image()
            np.testing.assert_array_equal(read_image_bgr(raw_path), native)


if __name__ == "__main__":
    unittest.main()
