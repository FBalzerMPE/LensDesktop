from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np

from LensDesktop import app as desktop
from LensDesktop.processing import example_source_path, read_image_bgr
from test_sources import FakeCapture


class StaticInputIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = desktop.QtWidgets.QApplication.instance()
        if cls.application is None:
            cls.application = desktop.QtWidgets.QApplication([])

    def setUp(self):
        self.desktop_frame = np.arange(8 * 8 * 4, dtype=np.uint8).reshape(8, 8, 4)
        self.capture_impl = desktop.LensDesktop.capture_screen_rect
        self.capture_patch = patch.object(
            desktop.LensDesktop, "capture_screen_rect", lambda window: self.desktop_frame.copy()
        )
        self.capture_patch.start()
        self.exclusion_patch = patch.object(desktop, "exclude_from_capture", return_value=True)
        self.exclusion_patch.start()
        self.captures = []
        self.window = desktop.LensDesktop(camera_factory=self.create_capture)
        self.window.timer.stop()
        self.window.resize(650, 420)
        self.window.show()
        self.application.processEvents()

    def create_capture(self, index):
        capture = FakeCapture(opened=index == 0)
        self.captures.append(capture)
        return capture

    def wait_until(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            self.application.processEvents()
            time.sleep(0.005)
        self.application.processEvents()
        self.assertTrue(predicate(), "Static input transition did not settle in time")

    def tearDown(self):
        self.window.close()
        self.wait_until(lambda: not self.window.camera_worker.isRunning())
        self.application.processEvents()
        self.assertTrue(all(capture.released for capture in self.captures))
        self.capture_patch.stop()
        self.exclusion_patch.stop()

    def test_hand_example_loads_as_static_input_without_opening_camera(self):
        self.window.settings_panel.load_input_example.click()
        self.assertTrue(self.window.static_active)
        self.assertFalse(self.window.cam)
        self.assertEqual(self.window.static_source.path, example_source_path())
        self.assertEqual(self.window.settings_panel.source_selector.currentData(), "static")
        self.assertEqual(self.window.settings_panel.input_fitting.currentData(), "fit")
        self.assertFalse(self.window.settings_panel.freeze_input.isEnabled())
        self.assertFalse(self.captures)

    def test_static_source_is_immutable_across_all_modes_and_settings(self):
        self.window._load_input_example()
        expected = self.window.static_source.snapshot()
        with patch.object(self.window, "capture_screen_rect", side_effect=AssertionError("Live capture in static mode")):
            for dual in (False, True):
                self.window.dual_checkbox.setChecked(dual)
                for inverse in (False, True):
                    self.window.inverse_checkbox.setChecked(inverse)
                    self.window.critical_checkbox.setChecked(True)
                    self.window.settings_panel.source_scale.setValue(60)
                    self.assertTrue(self.window.update_view())
                    self.assertEqual(self.window.label.pixmap().width(), self.window.base_w * (2 if dual else 1))
                    np.testing.assert_array_equal(self.window.static_source.snapshot(), expected)

    def test_desktop_freeze_holds_pixels_and_can_resume(self):
        expected = self.window._acquire_source_frame().copy()
        self.window.settings_panel.freeze_input.click()
        self.assertTrue(self.window.static_active)
        self.desktop_frame[:] = 0
        np.testing.assert_array_equal(self.window._acquire_source_frame(), expected)
        self.window.settings_panel.source_selector.setCurrentIndex(0)
        self.assertFalse(self.window.static_active)
        np.testing.assert_array_equal(self.window._acquire_source_frame(), 0)
        self.window.settings_panel.source_selector.setCurrentIndex(2)
        self.assertTrue(self.window.static_active)
        np.testing.assert_array_equal(self.window._acquire_source_frame(), expected)

    def test_camera_freeze_releases_device_and_preserves_native_unmirrored_data(self):
        self.window.settings_panel.open_camera.click()
        self.wait_until(lambda: self.window.cam)
        expected = self.window._acquire_source_frame().copy()
        self.window.settings_panel.freeze_input.click()
        self.wait_until(lambda: self.captures[0].released)
        self.assertTrue(self.window.static_active)
        self.assertFalse(self.window.cam)
        self.assertTrue(self.window.static_source.mirror)
        self.assertEqual(self.window.settings_panel.input_fitting.currentData(), "fill")
        np.testing.assert_array_equal(self.window._acquire_source_frame(), expected)
        self.window.camera_recording()
        self.wait_until(lambda: self.window.cam)
        self.assertFalse(self.window.static_active)

    def test_failed_camera_request_keeps_static_input(self):
        self.window._load_input_example()
        expected = self.window.static_source.snapshot()
        self.window.settings_panel.camera_index.setValue(9)
        self.window.settings_panel.open_camera.click()
        self.wait_until(lambda: self.window._pending_camera is None)
        self.assertTrue(self.window.static_active)
        self.assertEqual(self.window.settings_panel.source_selector.currentData(), "static")
        np.testing.assert_array_equal(self.window._acquire_source_frame(), expected)

    def test_cancelled_static_selection_keeps_live_source(self):
        with patch.object(
            desktop.QtWidgets.QFileDialog, "getOpenFileName", return_value=("", "")
        ):
            self.window.settings_panel.source_selector.setCurrentIndex(2)
        self.assertFalse(self.window.static_active)
        self.assertEqual(self.window.settings_panel.source_selector.currentData(), "desktop")
        self.assertIsNone(self.window.static_source.frame)

    def test_static_activation_cancels_pending_camera_and_ignores_stale_signals(self):
        started = threading.Event()
        unblock = threading.Event()

        def slow_create_capture(index):
            started.set()
            unblock.wait(2)
            return self.create_capture(index)

        with patch.object(self.window.camera_worker, "_capture_factory", slow_create_capture):
            self.window.settings_panel.open_camera.click()
            token = self.window._pending_camera
            try:
                self.assertTrue(started.wait(1))
                self.window._load_input_example()
                self.assertIsNone(self.window._pending_camera)
                self.window._camera_opened(token, 0)
                self.window._camera_open_failed(token, "Stale failure")
                self.window._camera_disconnected(token, "Stale disconnect")
                self.assertTrue(self.window.static_active)
                self.assertIn("Static input:", self.window.settings_panel.source_status.text())
            finally:
                unblock.set()
            self.wait_until(lambda: self.captures and self.captures[0].released)
        self.assertTrue(self.window.static_active)
        self.assertFalse(self.window.cam)

    def test_failed_load_preserves_static_input_and_reports_error(self):
        self.window._load_input_example()
        expected = self.window.static_source.snapshot()
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(self.window._load_input_image(Path(directory) / "missing.png"))
        self.assertTrue(self.window.static_active)
        self.assertIn("Cannot load", self.window.settings_panel.source_status.text())
        np.testing.assert_array_equal(self.window._acquire_source_frame(), expected)

    def test_save_input_preserves_original_photo_pixels_not_composed_scene(self):
        self.window._load_input_example()
        expected = self.window.static_source.snapshot()
        self.window.settings_panel.source_scale.setValue(30)
        self.window.settings_panel.source_offset_x.setValue(100)
        self.window.dual_checkbox.setChecked(True)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calibration.png"
            with patch.object(
                desktop.QtWidgets.QFileDialog, "getSaveFileName", return_value=(str(path), "")
            ):
                self.window.settings_panel.save_input.click()
            saved = read_image_bgr(path)
            np.testing.assert_array_equal(saved, expected)
            self.assertNotEqual(saved.shape[1], self.window.label.pixmap().width())

    def test_save_snapshots_input_before_file_dialog_and_appends_png(self):
        self.window._freeze_input()
        expected = self.window.static_source.snapshot()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calibration"

            def choose_file(*args):
                self.window.static_source.set_frame(np.zeros((4, 4, 3), np.uint8))
                return str(path), ""

            with patch.object(desktop.QtWidgets.QFileDialog, "getSaveFileName", side_effect=choose_file):
                self.window.save_input_image()
            np.testing.assert_array_equal(read_image_bgr(path.with_suffix(".png")), expected)

    def test_cancelled_save_does_not_write_or_change_input(self):
        self.window._freeze_input()
        expected = self.window.static_source.snapshot()
        status = self.window.settings_panel.source_status.text()
        with patch.object(
            desktop.QtWidgets.QFileDialog, "getSaveFileName", return_value=("", "")
        ), patch.object(desktop, "write_image_bgr") as write:
            self.window.save_input_image()
            write.assert_not_called()
        self.assertTrue(self.window.static_active)
        self.assertEqual(self.window.settings_panel.source_status.text(), status)
        np.testing.assert_array_equal(self.window.static_source.snapshot(), expected)

    def test_save_failures_and_missing_freeze_frames_are_explicit(self):
        self.window._load_input_example()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing" / "input.png"
            with patch.object(
                desktop.QtWidgets.QFileDialog, "getSaveFileName", return_value=(str(path), "")
            ):
                self.window.save_input_image()
            self.assertIn("Cannot save", self.window.settings_panel.source_status.text())
            self.assertFalse(path.exists())
        self.window._use_desktop()
        with patch.object(self.window, "_acquire_source_frame", return_value=None):
            self.window._freeze_input()
        self.assertFalse(self.window.static_active)
        self.assertIn("Cannot freeze", self.window.settings_panel.source_status.text())

    def test_desktop_capture_retains_native_pixels_before_render_resizing(self):
        frame = np.arange(6 * 8 * 4, dtype=np.uint8).reshape(6, 8, 4)
        with patch.object(self.window.sct, "grab", return_value=frame):
            captured = self.capture_impl(self.window)
        np.testing.assert_array_equal(captured, frame)
        self.assertEqual(captured.shape, (6, 8, 4))


if __name__ == "__main__":
    unittest.main()
