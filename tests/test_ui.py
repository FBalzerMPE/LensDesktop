import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

from LensDesktop import app as desktop


class SettingsPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = desktop.QtWidgets.QApplication.instance()
        if cls.app is None:
            cls.app = desktop.QtWidgets.QApplication([])

    def setUp(self):
        self.capture_patch = patch.object(
            desktop.LensDesktop, "capture_screen_rect", self.capture_frame
        )
        self.capture_patch.start()
        self.exclusion_patch = patch.object(
            desktop, "exclude_from_capture", return_value=True
        )
        self.exclusion_patch.start()
        self.window = desktop.LensDesktop()
        self.window.timer.stop()
        self.window.settings_panel.lens_section.set_expanded(True)
        self.window.show()
        self.app.processEvents()
        self.window.resize(650, 400)
        self.app.processEvents()
        self.window.update_view()

    @staticmethod
    def capture_frame(window):
        frame = np.zeros((window.base_h * 2, window.base_w * 2, 4), np.uint8)
        frame[:, :, 0] = 30
        frame[:, :, 1] = 80
        frame[:, :, 2] = 140
        frame[:, :, 3] = 255
        return frame

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        self.capture_patch.stop()
        self.exclusion_patch.stop()

    def test_native_controls_and_existing_defaults(self):
        panel = self.window.settings_panel
        for checkbox in (
            panel.critical_checkbox,
            panel.dual_checkbox,
            panel.inverse_checkbox,
            panel.lenslight_checkbox,
        ):
            self.assertEqual(checkbox.styleSheet(), "")
            self.assertFalse(checkbox.font().bold())
            self.assertGreaterEqual(
                checkbox.width(), checkbox.minimumSizeHint().width()
            )
            self.assertTrue(checkbox.isVisible())
            self.assertFalse(checkbox.isChecked())
        for slider, value in (
            (panel.sliderb, 65),
            (panel.sliderq, 65),
            (panel.sliders, 41),
            (panel.slidert, 95),
            (panel.slider_mask, 40),
        ):
            self.assertEqual((slider.minimum(), slider.maximum()), (40, 99))
            self.assertEqual(slider.value(), value)
        self.assertFalse(panel.mask_controls.isVisible())

    def test_canvas_is_square_and_does_not_overlap_controls(self):
        self.assertEqual(self.window.base_w, self.window.base_h)
        self.assertEqual(self.window.label.width(), self.window.base_w)
        self.assertEqual(self.window.label.height(), self.window.base_h)
        label_origin = self.window.label.mapTo(
            self.window.centralWidget(), desktop.QtCore.QPoint(0, 0)
        )
        panel_origin = self.window.settings_panel.mapTo(
            self.window.centralWidget(), desktop.QtCore.QPoint(0, 0)
        )
        self.assertLessEqual(
            label_origin.x() + self.window.label.width(), panel_origin.x()
        )
        size = self.window.size()
        self.window.update_view()
        self.assertEqual(self.window.size(), size)
        self.assertEqual(self.window.label.pixmap().size(), self.window.label.size())

    def test_capture_origin_follows_canvas_not_window(self):
        region = self.window._content_capture_rect_px()
        origin = self.window.label.mapToGlobal(desktop.QtCore.QPoint(0, 0))
        self.assertEqual((region["left"], region["top"]), (origin.x(), origin.y()))
        self.assertEqual(region["width"], self.window.base_w)
        self.assertEqual(region["height"], self.window.base_h)

    def test_modes_and_sliders_preserve_rendering(self):
        for dual in (False, True):
            self.window.dual_checkbox.setChecked(dual)
            self.app.processEvents()
            for inverse in (False, True):
                self.window.inverse_checkbox.setChecked(inverse)
                self.window.critical_checkbox.setChecked(True)
                self.window.lenslight_checkbox.setChecked(True)
                self.window.update_view()
                expected_width = self.window.base_w * (2 if dual else 1)
                self.assertEqual(self.window.label.pixmap().width(), expected_width)
                self.assertEqual(
                    self.window.label.pixmap().height(), self.window.base_h
                )
                self.assertEqual(
                    self.window.settings_panel.mask_controls.isVisible(), inverse
                )
        self.window.sliderb.setValue(70)
        self.assertAlmostEqual(self.window.b_value, (70 - 40) / 59)
        self.window.sliderq.setValue(75)
        self.assertAlmostEqual(self.window.q_value, 0.75)
        self.window.sliders.setValue(45)
        self.assertAlmostEqual(self.window.s_value, 5 / 59)
        self.window.slidert.setValue(80)
        self.assertAlmostEqual(self.window.t_value, 40 / 59 * np.pi)
        self.window.slider_mask.setValue(50)
        self.assertAlmostEqual(
            self.window.mask_radius,
            10 / 59 * np.hypot(self.window.base_w, self.window.base_h) / 2,
        )

    def test_presentation_mode_preserves_settings(self):
        self.window.inverse_checkbox.setChecked(True)
        self.window.sliderb.setValue(70)
        self.window.HideGUI()
        self.app.processEvents()
        self.assertFalse(self.window.settings_panel.isVisible())
        self.assertTrue(
            self.window.windowFlags() & desktop.QtCore.Qt.FramelessWindowHint
        )
        self.window.HideGUI()
        self.app.processEvents()
        self.assertTrue(self.window.settings_panel.isVisible())
        self.assertTrue(self.window.settings_panel.mask_controls.isVisible())
        self.assertFalse(
            self.window.windowFlags() & desktop.QtCore.Qt.FramelessWindowHint
        )
        self.assertTrue(self.window.inverse_checkbox.isChecked())
        self.assertEqual(self.window.sliderb.value(), 70)

    def test_marker_coordinates_are_local_to_canvas(self):
        self.window.settings_panel.source_scale.setValue(100)
        self.window.dual_checkbox.setChecked(True)
        self.app.processEvents()
        point = desktop.QtCore.QPoint(self.window.base_w + 20, 30)
        event = desktop.QtGui.QMouseEvent(
            desktop.QtCore.QEvent.MouseButtonPress,
            desktop.QtCore.QPointF(point),
            desktop.QtCore.Qt.RightButton,
            desktop.QtCore.Qt.RightButton,
            desktop.QtCore.Qt.NoModifier,
        )
        self.app.sendEvent(self.window.label, event)
        self.assertEqual(self.window.ellipses_image_plane, [(20, 30)])
        self.assertEqual(self.window.ellipses_source_plane, [])
        self.app.sendEvent(self.window.label, event)
        self.assertEqual(self.window.ellipses_image_plane, [])
        self.window.inverse_checkbox.setChecked(True)
        self.app.sendEvent(self.window.label, event)
        self.assertEqual(self.window.ellipses_source_plane, [(20, 30)])

    def test_shortcuts_are_retained(self):
        shortcuts = {
            shortcut.key().toString()
            for shortcut in self.window.findChildren(desktop.QtWidgets.QShortcut)
        }
        self.assertEqual(
            shortcuts, {"Ctrl+S", "Ctrl+L", "Ctrl+R", "Ctrl+F", "Ctrl+V"}
        )
        for shortcut in self.window.findChildren(desktop.QtWidgets.QShortcut):
            if shortcut.key().toString() == "Ctrl+V":
                shortcut.activated.emit()
                self.app.processEvents()
                self.assertFalse(self.window.settings_panel.isVisible())
                shortcut.activated.emit()
                self.app.processEvents()
                self.assertTrue(self.window.settings_panel.isVisible())

    def test_panel_clicks_do_not_create_markers(self):
        event = desktop.QtGui.QMouseEvent(
            desktop.QtCore.QEvent.MouseButtonPress,
            desktop.QtCore.QPointF(10, 10),
            desktop.QtCore.Qt.RightButton,
            desktop.QtCore.Qt.RightButton,
            desktop.QtCore.Qt.NoModifier,
        )
        self.app.sendEvent(self.window.settings_panel.widget(), event)
        self.assertEqual(self.window.ellipses_image_plane, [])
        self.assertEqual(self.window.ellipses_source_plane, [])

    def test_canvas_drag_and_release(self):
        origin = self.window.pos()
        global_pos = self.window.label.mapToGlobal(desktop.QtCore.QPoint(20, 20))
        for event_type, offset, button, buttons in (
            (desktop.QtCore.QEvent.MouseButtonPress, 0,
             desktop.QtCore.Qt.LeftButton, desktop.QtCore.Qt.LeftButton),
            (desktop.QtCore.QEvent.MouseMove, 10,
             desktop.QtCore.Qt.NoButton, desktop.QtCore.Qt.LeftButton),
            (desktop.QtCore.QEvent.MouseButtonRelease, 10,
             desktop.QtCore.Qt.LeftButton, desktop.QtCore.Qt.NoButton),
        ):
            event = desktop.QtGui.QMouseEvent(
                event_type,
                desktop.QtCore.QPointF(20 + offset, 20 + offset),
                desktop.QtCore.QPointF(global_pos + desktop.QtCore.QPoint(offset, offset)),
                button, buttons, desktop.QtCore.Qt.NoModifier,
            )
            self.app.sendEvent(self.window.label, event)
        self.assertEqual(self.window.pos(), origin + desktop.QtCore.QPoint(10, 10))
        self.assertIsNone(self.window.old_pos)

    def test_screenshot_exports_only_canvas(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "scene.png")
            with patch.object(
                desktop.QtWidgets.QFileDialog, "getSaveFileName",
                return_value=(path, "PNG Files (*.png)"),
            ):
                self.window.save_screenshot()
            image = desktop.QtGui.QImage(path)
            self.assertFalse(image.isNull())
            self.assertEqual(image.size(), self.window.label.pixmap().size())
            self.assertLess(image.width(), self.window.width())

    def test_panel_scrolls_in_short_windows(self):
        self.window.resize(650, 180)
        self.app.processEvents()
        self.assertGreater(self.window.settings_panel.verticalScrollBar().maximum(), 0)
        self.assertEqual(
            self.window.settings_panel.horizontalScrollBar().maximum(), 0
        )
        self.assertGreaterEqual(self.window.base_w, 2)


if __name__ == "__main__":
    unittest.main()
