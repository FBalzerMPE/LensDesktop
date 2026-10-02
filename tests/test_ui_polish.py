from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from LensDesktop import app as desktop
from LensDesktop.processing import ImageError, fit_layer, read_image_bgr


class InputZoomTests(unittest.TestCase):
    def test_200_percent_crops_central_half_of_each_axis(self):
        color = np.arange(8 * 12 * 3, dtype=np.float32).reshape(8, 12, 3)
        alpha = np.arange(8 * 12, dtype=np.float32).reshape(8, 12) / 100
        image, coverage = fit_layer(color, alpha, 6, 4, "stretch", zoom=200)
        np.testing.assert_array_equal(image, color[2:6, 3:9])
        np.testing.assert_array_equal(coverage, alpha[2:6, 3:9])

    def test_zoom_preserves_premultiplied_edges_and_does_not_modify_input(self):
        alpha = np.zeros((8, 12), np.float32)
        alpha[:, 5:] = 1
        color = np.full((8, 12, 3), (200, 80, 20), np.float32) * alpha[..., None]
        original = color.copy()
        image, coverage = fit_layer(color, alpha, 24, 16, "fill", zoom=200, mirror=True)
        np.testing.assert_allclose(image, coverage[..., None] * (200, 80, 20), atol=0.001)
        np.testing.assert_array_equal(color, original)

    def test_invalid_zoom_is_explicit_and_small_images_stay_valid(self):
        color = np.ones((1, 1, 3), np.float32)
        alpha = np.ones((1, 1), np.float32)
        for zoom in (0, 99, 401, float("nan")):
            with self.assertRaises(ImageError):
                fit_layer(color, alpha, 4, 4, "fit", zoom=zoom)
        image, coverage = fit_layer(color, alpha, 4, 4, "fill", zoom=400)
        np.testing.assert_array_equal(image, 1)
        np.testing.assert_array_equal(coverage, 1)


class PolishedUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = desktop.QtWidgets.QApplication.instance() or desktop.QtWidgets.QApplication([])

    def setUp(self):
        self.native = np.full((8, 12, 3), (0, 255, 0), np.uint8)
        self.native[2:6, 3:9] = (0, 0, 200)
        self.capture_patch = patch.object(
            desktop.LensDesktop, "capture_screen_rect", lambda window: self.native.copy()
        )
        self.exclusion_patch = patch.object(desktop, "exclude_from_capture", return_value=True)
        self.capture_patch.start()
        self.exclusion_patch.start()
        self.window = desktop.LensDesktop()
        self.window.timer.stop()
        self.window.show()
        self.window.resize(750, 550)
        self.application.processEvents()
        self.panel = self.window.settings_panel
        self.panel.configuration_enabled.setChecked(False)
        self.window.dual_checkbox.setChecked(False)
        self.window.critical_checkbox.setChecked(False)
        self.window.lenslight_checkbox.setChecked(False)

    def tearDown(self):
        self.window.close()
        self.application.processEvents()
        self.capture_patch.stop()
        self.exclusion_patch.stop()

    def test_source_size_slider_uses_ini_default_and_reset(self):
        default_scale = self.window.gui_defaults.placement.scale
        self.assertIsInstance(self.panel.source_scale, desktop.QtWidgets.QSlider)
        self.assertEqual(self.panel.source_scale.value(), default_scale)
        self.assertEqual(self.panel.source_scale_value.text(), f"{default_scale}%")
        self.panel.source_scale.setValue(65)
        self.assertEqual(self.panel.source_scale_value.text(), "65%")
        self.panel.reset_placement.click()
        self.assertEqual(
            self.window._source_placement(),
            (
                default_scale / 100,
                self.window.gui_defaults.placement.offset_x / 100,
                self.window.gui_defaults.placement.offset_y / 100,
            ),
        )
        self.assertEqual(self.panel.source_scale_value.text(), f"{default_scale}%")

    def test_sections_are_reordered_and_expose_reset_icons(self):
        self.assertEqual(
            [section.header.text() for section in self.panel.sections],
            [
                "Source",
                "Input / greenscreen",
                "Sky background",
                "Source placement",
                "Source relative to lens",
                "Lens",
                "View",
                "Print / export",
            ],
        )
        self.assertTrue(all(section.reset_button is not None for section in self.panel.sections[:-1]))
        self.assertIsNone(self.panel.export_section.reset_button)

    def test_settings_sections_reset_to_loaded_defaults(self):
        defaults = self.window.gui_defaults
        panel = self.panel

        panel.background_mode.setCurrentIndex(panel.background_mode.findData("fit"))
        with patch.object(self.window, "_load_background") as load_background:
            panel.background_section.reset_button.click()
        self.assertEqual(panel.background_mode.currentData(), defaults.background.fitting)
        load_background.assert_called_once()
        self.assertTrue(str(load_background.call_args.args[0]).endswith(defaults.background.image))

        panel.camera_index.setValue(8)
        self.window.selected_camera_index = 8
        self.window.static_active = True
        with patch.object(self.window, "update_view"):
            panel.source_section.reset_button.click()
        self.assertEqual(panel.camera_index.value(), defaults.source.camera_index)
        self.assertIsNone(self.window.selected_camera_index)
        self.assertFalse(self.window.static_active)

        for checkbox, default in (
            (panel.critical_checkbox, defaults.view.critical_curve),
            (panel.dual_checkbox, defaults.view.dual_view),
            (panel.inverse_checkbox, defaults.view.de_lensing),
            (panel.lenslight_checkbox, defaults.view.lens_light),
        ):
            with desktop.QtCore.QSignalBlocker(checkbox):
                checkbox.setChecked(not default)
        self.window.heart = not defaults.lens.heart
        for slider in (
            panel.sliderb, panel.sliderq, panel.sliders, panel.slidert, panel.slider_mask,
        ):
            with desktop.QtCore.QSignalBlocker(slider):
                slider.setValue(99)
        with patch.object(self.window, "update_view"):
            panel.view_section.reset_button.click()
            panel.lens_section.reset_button.click()
        self.assertEqual(panel.critical_checkbox.isChecked(), defaults.view.critical_curve)
        self.assertEqual(panel.dual_checkbox.isChecked(), defaults.view.dual_view)
        self.assertEqual(panel.inverse_checkbox.isChecked(), defaults.view.de_lensing)
        self.assertEqual(panel.lenslight_checkbox.isChecked(), defaults.view.lens_light)
        self.assertEqual(
            [
                panel.sliderb.value(), panel.sliderq.value(), panel.sliders.value(),
                panel.slidert.value(), panel.slider_mask.value(),
            ],
            [
                defaults.lens.einstein_radius, defaults.lens.axis_ratio,
                defaults.lens.core_radius, defaults.lens.position_angle,
                defaults.lens.mask_radius,
            ],
        )
        self.assertEqual(self.window.heart, defaults.lens.heart)

    def test_expanders_preserve_enabled_state_and_values(self):
        section = self.panel.input_section
        self.assertFalse(section.header.isChecked())
        section.header.click()
        self.assertTrue(section.body.isVisible())
        self.panel.input_zoom.setValue(175)
        section.header.click()
        self.assertFalse(section.body.isVisible())
        self.assertTrue(self.panel.input_zoom.isEnabled())
        section.header.click()
        self.assertEqual(self.panel.input_zoom.value(), 175)
        self.assertEqual(section.header.arrowType(), desktop.QtCore.Qt.DownArrow)
        self.window.HideGUI()
        self.window.HideGUI()
        self.assertTrue(section.header.isChecked())

    def test_camera_shortcut_opens_required_expanders_without_opening_a_camera(self):
        self.panel.source_section.set_expanded(False)
        self.window.camera_recording()
        self.assertTrue(self.panel.source_section.header.isChecked())
        self.assertTrue(self.panel.camera_section.header.isChecked())
        self.assertTrue(self.panel.camera_selector.isVisible())
        self.assertFalse(self.window.camera_worker.isRunning())

    def test_all_sections_fit_panel_width_and_scroll_vertically(self):
        for section in self.panel.sections:
            section.set_expanded(True)
        self.panel.camera_section.set_expanded(True)
        self.window.resize(750, 300)
        self.application.processEvents()
        self.assertGreater(self.panel.verticalScrollBar().maximum(), 0)
        self.assertEqual(self.panel.horizontalScrollBar().maximum(), 0)
        for control in (self.panel.key_tolerance, self.panel.input_zoom, self.panel.source_scale):
            position = control.mapTo(self.panel.widget(), desktop.QtCore.QPoint(0, 0))
            self.assertLessEqual(position.x() + control.width(), self.panel.viewport().width())

    def test_window_client_and_frame_height_are_limited_to_available_screen(self):
        screen = self.window.screen()
        available = desktop.QtCore.QRect(0, 0, 1000, 430)
        with patch.object(
            desktop.QtGui.QScreen, "availableGeometry", return_value=available
        ):
            screen.availableGeometryChanged.emit(available)
            self.window.resize(750, 1500)
            self.application.processEvents()
            self.assertLessEqual(self.window.frameGeometry().height(), available.height())
            self.assertLessEqual(self.window.height(), self.window.maximumHeight())
            self.window.HideGUI()
            self.application.processEvents()
            self.assertLessEqual(self.window.frameGeometry().height(), available.height())
            self.window.HideGUI()
            self.application.processEvents()
            self.assertLessEqual(self.window.frameGeometry().height(), available.height())
        self.window._update_screen_height_limit()

    def test_zoom_changes_keyed_input_and_preview_but_not_native_pixels_or_lens_maps(self):
        self.window.static_source.set_frame(self.native)
        self.window._activate_static_source()
        self.panel.input_frame_mode.setCurrentIndex(2)
        self.panel.key_enabled.setChecked(True)
        maps = self.window.map_x.copy()
        self.panel.input_zoom.setValue(200)
        image, alpha = self.window._keyed_input(self.window.static_source.frame)
        np.testing.assert_array_equal(image, np.full(image.shape, (200, 0, 0), np.float32))
        np.testing.assert_array_equal(alpha, 1)
        np.testing.assert_array_equal(self.window.map_x, maps)
        np.testing.assert_array_equal(self.window.static_source.snapshot(), self.native)
        self.panel.input_preview.setCurrentIndex(2)
        pixel = self.window.label.pixmap().toImage().pixelColor(5, 5)
        self.assertEqual((pixel.red(), pixel.green(), pixel.blue()), (255, 255, 255))
        self.panel.reset_input.click()
        self.assertEqual(self.panel.input_zoom.value(), 100)
        self.assertEqual(self.panel.input_zoom_value.text(), "100%")

    def test_maximize_and_restore_recompute_height_for_current_frame_margins(self):
        with patch.object(
            self.window, "_update_screen_height_limit", wraps=self.window._update_screen_height_limit
        ) as limit:
            self.window.showMaximized()
            self.application.processEvents()
            self.assertTrue(limit.called)
            self.assertTrue(self.window.isMaximized())
            self.assertLessEqual(
                self.window.maximumHeight(), self.window.screen().availableGeometry().height()
            )
            limit.reset_mock()
            self.window.showNormal()
            self.application.processEvents()
            self.assertTrue(limit.called)
            margins = self.window.windowHandle().frameMargins()
            self.assertEqual(
                self.window.maximumHeight(),
                self.window.screen().availableGeometry().height() - margins.top() - margins.bottom(),
            )

    def test_zoom_is_applied_to_opaque_live_input_before_lensing(self):
        with patch.object(self.window, "update_single_view") as render:
            self.panel.input_frame_mode.setCurrentIndex(2)
            self.panel.input_zoom.setValue(200)
            self.assertTrue(self.window.update_view())
            prepared = render.call_args.args[0]
        np.testing.assert_array_equal(prepared, np.full(prepared.shape, (0, 0, 200), np.uint8))

    def test_zoom_crops_green_edges_in_every_view_with_keying_on_and_off(self):
        self.window.static_source.set_frame(self.native)
        self.window._activate_static_source()
        self.panel.input_frame_mode.setCurrentIndex(2)
        self.panel.input_zoom.setValue(200)
        for keyed in (False, True):
            self.panel.key_enabled.setChecked(keyed)
            for dual in (False, True):
                self.window.dual_checkbox.setChecked(dual)
                for inverse in (False, True):
                    self.window.inverse_checkbox.setChecked(inverse)
                    with patch.object(self.window, "_compose_layer", wraps=self.window._compose_layer) as compose:
                        self.assertTrue(self.window.update_view())
                    for call in compose.call_args_list:
                        color = call.args[0]
                        # The opaque inverse reference panel can retain one gray mask-center pixel.
                        self.assertLessEqual(np.count_nonzero(color[..., 1]), 1)
                    self.assertEqual(
                        self.window.label.pixmap().width(), self.window.base_w * (2 if dual else 1)
                    )

    def test_zoom_and_size_controls_do_not_change_raw_calibration_export(self):
        self.window.static_source.set_frame(self.native)
        self.window._activate_static_source()
        self.panel.input_zoom.setValue(300)
        self.panel.source_scale.setValue(75)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.png"
            with patch.object(desktop.QtWidgets.QFileDialog, "getSaveFileName", return_value=(str(path), "")):
                self.window.save_input_image()
            np.testing.assert_array_equal(read_image_bgr(path), self.native)


if __name__ == "__main__":
    unittest.main()
