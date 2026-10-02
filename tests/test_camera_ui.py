import threading
import time
import unittest
from unittest.mock import patch

import numpy as np

from LensDesktop import app as desktop
from test_sources import FakeCapture


class CameraIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = desktop.QtWidgets.QApplication.instance()
        if cls.application is None:
            cls.application = desktop.QtWidgets.QApplication([])

    def setUp(self):
        self.capture_patch = patch.object(
            desktop.LensDesktop, "capture_screen_rect",
            lambda window: np.full(
                (window.base_h * 2, window.base_w * 2, 4),
                (10, 70, 190, 255), np.uint8,
            ),
        )
        self.capture_patch.start()
        self.exclusion_patch = patch.object(desktop, "exclude_from_capture", return_value=True)
        self.exclusion_patch.start()
        self.captures = []
        self.factory = lambda index: FakeCapture(opened=index in (0, 1))
        self.window = desktop.LensDesktop(camera_factory=self.create_capture)
        self.window.timer.stop()
        self.window.resize(650, 350)
        self.window.show()
        self.application.processEvents()

    def create_capture(self, index):
        capture = self.factory(index)
        self.captures.append(capture)
        return capture

    def wait_until(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            self.application.processEvents()
            time.sleep(0.005)
        self.application.processEvents()
        self.assertTrue(predicate(), "Camera UI did not settle in time")

    def tearDown(self):
        self.window.close()
        self.wait_until(lambda: not self.window.camera_worker.isRunning())
        self.application.processEvents()
        self.assertTrue(all(cap.released for cap in self.captures))
        self.capture_patch.stop()
        self.exclusion_patch.stop()

    def open_camera(self, index=0):
        self.window.settings_panel.camera_index.setValue(index)
        self.window.settings_panel.open_camera.click()
        self.wait_until(lambda: self.window.cam and self.window._pending_camera is None)

    def test_default_does_not_open_or_probe_camera(self):
        self.assertFalse(self.window.cam)
        self.assertFalse(self.window.camera_worker.isRunning())
        self.assertFalse(self.captures)
        self.assertEqual(self.window.settings_panel.source_selector.currentData(), "desktop")

    def test_ctrl_f_without_selection_reveals_selector(self):
        self.window.HideGUI()
        self.window.camera_recording()
        self.assertFalse(self.window.gui_hidden)
        self.assertFalse(self.window.cam)
        self.assertIn("Select a camera", self.window.settings_panel.source_status.text())
        self.assertFalse(self.captures)

    def test_manual_camera_and_ctrl_f_toggle(self):
        self.open_camera()
        self.assertEqual(self.window.settings_panel.source_selector.currentData(), "webcam")
        self.window.camera_recording()
        self.assertFalse(self.window.cam)
        self.window.camera_recording()
        self.wait_until(lambda: self.window.cam)
        self.assertEqual(self.window.selected_camera_index, 0)

    def test_camera_colors_and_all_view_modes(self):
        self.window._clear_background()
        self.open_camera()
        for dual in (False, True):
            self.window.dual_checkbox.setChecked(dual)
            for inverse in (False, True):
                self.window.inverse_checkbox.setChecked(inverse)
                self.window.update_view()
                image = self.window.label.pixmap().toImage()
                self.assertEqual(image.width(), self.window.base_w * (2 if dual else 1))
                self.assertEqual(image.height(), self.window.base_h)
                pixel = image.pixelColor(self.window.base_w // 2 + 5, image.height() // 2)
                self.assertEqual((pixel.red(), pixel.green(), pixel.blue()), (190, 70, 10))

    def test_failed_camera_switch_keeps_previous_source(self):
        self.open_camera()
        token = self.window.camera_token
        self.window.settings_panel.camera_index.setValue(9)
        self.window.settings_panel.open_camera.click()
        self.wait_until(lambda: self.window._pending_camera is None)
        self.assertTrue(self.window.cam)
        self.assertEqual(self.window.camera_token, token)
        self.assertEqual(self.window.selected_camera_index, 0)
        self.assertIn("Previous source kept", self.window.settings_panel.source_status.text())
        self.assertFalse(self.captures[0].released)

    def test_failed_open_from_desktop_stays_desktop(self):
        self.window.settings_panel.camera_index.setValue(9)
        self.window.settings_panel.open_camera.click()
        self.wait_until(lambda: self.window._pending_camera is None)
        self.assertFalse(self.window.cam)
        self.assertEqual(self.window.settings_panel.source_selector.currentData(), "desktop")
        self.assertIn("Cannot open camera 9", self.window.settings_panel.source_status.text())

    def test_invalid_desktop_frame_is_reported_without_black_fallback(self):
        before = self.window.label.pixmap().toImage()
        with patch.object(self.window, "capture_screen_rect", return_value=None):
            self.window.update_view()
        self.assertEqual(self.window.label.pixmap().toImage(), before)
        self.assertIn("Cannot capture", self.window.settings_panel.source_status.text())

    def test_disconnect_is_explicit_and_does_not_switch_to_desktop(self):
        self.open_camera()
        self.captures[0].reads = [(False, None)]
        self.wait_until(lambda: self.window._camera_fault)
        self.assertTrue(self.window.cam)
        before = self.window.label.pixmap().toImage()
        self.window.update_view()
        self.assertEqual(self.window.label.pixmap().toImage(), before)
        self.assertIn("frozen", self.window.settings_panel.source_status.text())
        self.assertIn("frozen", self.window.statusBar().currentMessage())
        self.window.settings_panel.source_selector.setCurrentIndex(0)
        self.assertFalse(self.window.cam)
        self.assertFalse(self.window._camera_fault)

    def test_refresh_lists_indices_and_selection_opens_webcam(self):
        self.window.settings_panel.refresh_cameras.click()
        self.wait_until(lambda: self.window._discovery_token is None)
        selector = self.window.settings_panel.camera_selector
        self.assertEqual([selector.itemData(i) for i in range(selector.count())], [None, 0, 1])
        selector.setCurrentIndex(2)
        self.window.settings_panel.source_selector.setCurrentIndex(1)
        self.wait_until(lambda: self.window.cam)
        self.assertEqual(self.window.selected_camera_index, 1)

    def test_slow_open_leaves_ui_responsive_and_shutdown_cleans_up(self):
        started = threading.Event()
        unblock = threading.Event()

        def factory(index):
            started.set()
            unblock.wait(2)
            return FakeCapture()

        self.factory = factory
        self.window.settings_panel.open_camera.click()
        self.assertTrue(started.wait(1))
        heartbeat = []
        desktop.QtCore.QTimer.singleShot(0, lambda: heartbeat.append(True))
        self.application.processEvents()
        self.assertTrue(heartbeat)
        self.assertFalse(self.window.cam)
        self.window.close()
        self.assertTrue(self.window.isVisible())
        unblock.set()
        self.wait_until(lambda: not self.window.isVisible())
        self.assertTrue(all(cap.released for cap in self.captures))


if __name__ == "__main__":
    unittest.main()
