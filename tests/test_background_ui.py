from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from LensDesktop import app as desktop
from LensDesktop.processing import default_background_path


class BackgroundIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = desktop.QtWidgets.QApplication.instance()
        if cls.application is None:
            cls.application = desktop.QtWidgets.QApplication([])

    def setUp(self):
        self.capture_patch = patch.object(
            desktop.LensDesktop, "capture_screen_rect",
            lambda window: np.zeros((window.base_h * 2, window.base_w * 2, 4), np.uint8),
        )
        self.capture_patch.start()
        self.exclusion_patch = patch.object(desktop, "exclude_from_capture", return_value=True)
        self.exclusion_patch.start()
        self.window = desktop.LensDesktop()
        self.window.timer.stop()
        self.window.resize(650, 350)
        self.window.show()
        self.application.processEvents()
        self.window.update_view()

    def tearDown(self):
        self.window.close()
        self.application.processEvents()
        self.capture_patch.stop()
        self.exclusion_patch.stop()

    def displayed_rgb(self):
        image = self.window.label.pixmap().toImage().convertToFormat(
            desktop.QtGui.QImage.Format_RGB888
        )
        pointer = image.bits()
        pointer.setsize(image.byteCount())
        data = np.frombuffer(pointer, np.uint8).reshape(image.height(), image.bytesPerLine())
        return data[:, :image.width() * 3].reshape(image.height(), image.width(), 3).copy()

    def test_default_loads_once_and_reuses_fit_cache(self):
        self.assertEqual(self.window.background.path, default_background_path())
        image = self.window.background.image
        fitted = self.window.background.fitted(self.window.base_w, self.window.base_h, "fill")
        self.window.update_view()
        self.assertIs(self.window.background.image, image)
        self.assertIs(
            self.window.background.fitted(self.window.base_w, self.window.base_h, "fill"),
            fitted,
        )

    def test_all_modes_move_only_source_and_reveal_unchanged_sky(self):
        panel = self.window.settings_panel
        panel.source_scale.setValue(50)
        panel.source_offset_x.setValue(100)
        self.window.lenslight_checkbox.setChecked(True)
        self.window.critical_checkbox.setChecked(True)
        for dual in (False, True):
            self.window.dual_checkbox.setChecked(dual)
            for inverse in (False, True):
                self.window.inverse_checkbox.setChecked(inverse)
                self.window.sliderb.setValue(75)
                self.window.update_view()
                sky = self.window.background.fitted(self.window.base_w, self.window.base_h, "fill")
                expected = np.hstack((sky, sky)) if dual else sky
                np.testing.assert_array_equal(self.displayed_rgb(), expected)

    def test_black_source_stays_opaque_and_moving_it_does_not_change_maps(self):
        panel = self.window.settings_panel
        panel.source_scale.setValue(50)
        maps = self.window.map_x.copy()
        frame = self.displayed_rgb()
        side = self.window.base_w
        np.testing.assert_array_equal(frame[side // 2, side // 2], 0)
        sky = self.window.background.fitted(side, side, "fill")
        np.testing.assert_array_equal(frame[:side // 8], sky[:side // 8])
        panel.source_offset_x.setValue(25)
        np.testing.assert_array_equal(self.window.map_x, maps)
        self.assertEqual(self.window._source_placement(), (0.5, 0.25, 0.0))

    def test_clear_and_default_restore(self):
        self.window.settings_panel.clear_background.click()
        self.assertIsNone(self.window.background.image)
        self.window.settings_panel.default_background.click()
        self.assertEqual(self.window.background.path, default_background_path())

    def test_reset_placement_restores_defaults(self):
        panel = self.window.settings_panel
        panel.source_scale.setValue(50)
        panel.source_offset_x.setValue(-25)
        panel.source_offset_y.setValue(30)
        panel.reset_placement.click()
        self.assertEqual(self.window._source_placement(), (0.25, 0.0, 0.0))

    def test_bad_load_and_cancel_preserve_last_valid_background(self):
        previous = self.window.background.image
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(self.window._load_background(Path(directory) / "missing.png"))
        self.assertIs(self.window.background.image, previous)
        self.assertIn("Cannot load", self.window.settings_panel.background_status.text())
        with patch.object(
            desktop.QtWidgets.QFileDialog, "getOpenFileName", return_value=("", "")
        ):
            self.window.settings_panel.load_background.click()
        self.assertIs(self.window.background.image, previous)

    def test_marker_click_is_mapped_back_through_post_lens_placement(self):
        panel = self.window.settings_panel
        panel.source_scale.setValue(50)
        panel.source_offset_x.setValue(25)
        side = self.window.base_w
        for point in (desktop.QtCore.QPointF(1, 1),
                      desktop.QtCore.QPointF(side * 0.75, side * 0.5)):
            event = desktop.QtGui.QMouseEvent(
                desktop.QtCore.QEvent.MouseButtonPress, point,
                desktop.QtCore.Qt.RightButton, desktop.QtCore.Qt.RightButton,
                desktop.QtCore.Qt.NoModifier,
            )
            self.application.sendEvent(self.window.label, event)
        self.assertEqual(len(self.window.ellipses_image_plane), 1)
        x, y = self.window.ellipses_image_plane[0]
        self.assertAlmostEqual(x, side * 0.5, delta=1)
        self.assertAlmostEqual(y, side * 0.5, delta=1)

    def test_screenshot_includes_sky_and_placement_without_controls(self):
        self.window.settings_panel.source_scale.setValue(50)
        self.window.settings_panel.source_offset_x.setValue(100)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scene.png"
            with patch.object(
                desktop.QtWidgets.QFileDialog, "getSaveFileName",
                return_value=(str(path), ""),
            ):
                self.window.save_screenshot()
            image = desktop.QtGui.QImage(str(path))
            self.assertEqual(image, self.window.label.pixmap().toImage())

    def test_inverse_sequence_exports_composition_and_restores_settings(self):
        self.window.inverse_checkbox.setChecked(True)
        self.window.settings_panel.source_scale.setValue(50)
        self.window.settings_panel.source_offset_x.setValue(100)
        radius = self.window.b_value
        linspace = np.linspace
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scene.png"
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
            self.assertTrue((Path(directory) / "scene_0000.png").exists())
            self.assertTrue((Path(directory) / "scene_0001.png").exists())
            saved = desktop.QtGui.QImage(str(Path(directory) / "scene_0001.png"))
            self.assertEqual(saved, self.window.label.pixmap().toImage())
        self.assertEqual(self.window.b_value, radius)

    def test_zero_mass_has_finite_zero_deflection(self):
        xx, yy = np.meshgrid(np.linspace(-1, 1, 9), np.linspace(-1, 1, 9))
        with np.errstate(divide="raise", invalid="raise"):
            deflx, defly, _ = desktop.SIE_defl(xx, yy, 0, 0, False, 0.65, 0)
        np.testing.assert_array_equal(deflx, 0)
        np.testing.assert_array_equal(defly, 0)

    def test_forward_out_of_bounds_pixels_reveal_sky(self):
        self.window.map_x.fill(-20)
        self.window.map_y.fill(-20)
        frame = np.zeros((self.window.base_h * 2, self.window.base_w * 2, 3), np.uint8)
        rgb, alpha = self.window._forward_layer(frame)
        np.testing.assert_array_equal(alpha, 0)
        sky = self.window.background.fitted(self.window.base_w, self.window.base_h, "fill")
        np.testing.assert_array_equal(self.window._compose_layer(rgb, alpha), sky)

    def test_inverse_unsampled_pixels_have_zero_coverage(self):
        frame = np.full((4, 4, 3), (190, 70, 10), np.uint8)
        indices = np.zeros(16, np.int64)
        image, alpha = desktop.inverse_remap_image(
            frame, indices, indices, -1, 4, 4, return_alpha=True
        )
        self.assertEqual(alpha[0, 0], 1)
        self.assertEqual(np.count_nonzero(alpha), 1)
        np.testing.assert_array_equal(image[0, 0], (190, 70, 10))


if __name__ == "__main__":
    unittest.main()
