from pathlib import Path
import tempfile
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from LensDesktop import app as desktop
from LensDesktop.processing import ImageError
from LensDesktop.scene import render_snapshot
import test_chroma_ui as fixtures


class A4IntegrationTests(unittest.TestCase):
    setUp = fixtures.ChromaIntegrationTests.setUp
    tearDown = fixtures.ChromaIntegrationTests.tearDown
    wait_until = fixtures.ChromaIntegrationTests.wait_until
    displayed_rgb = fixtures.ChromaIntegrationTests.displayed_rgb

    @classmethod
    def setUpClass(cls):
        cls.application = desktop.QtWidgets.QApplication.instance() or desktop.QtWidgets.QApplication([])

    def set_subject(self):
        native = np.full((48, 64, 3), (0, 255, 0), np.uint8)
        native[12:36, 20:44] = (0, 0, 210)
        self.window.static_source.set_frame(native)
        self.panel.key_enabled.setChecked(True)
        self.panel.configuration_enabled.setChecked(True)
        return native

    def test_live_and_inverse_export_are_guarded_without_changing_modes(self):
        self.assertTrue(self.panel.export_a4.isEnabled())
        self.assertTrue(self.panel.print_a4.isEnabled())
        self.window._use_desktop()
        self.assertFalse(self.panel.export_a4.isEnabled())
        self.assertFalse(self.panel.print_a4.isEnabled())
        with (
            patch.object(desktop.QtWidgets.QFileDialog, "getSaveFileName") as dialog,
            patch.object(desktop.QtPrintSupport, "QPrintDialog") as print_dialog,
        ):
            self.assertFalse(self.window.export_a4_pdf())
            self.assertFalse(self.window.print_a4())
            dialog.assert_not_called()
            print_dialog.assert_not_called()
        self.assertIn("Freeze", self.panel.export_status.text())
        self.window._activate_static_source()
        self.window.inverse_checkbox.setChecked(True)
        self.assertFalse(self.panel.export_a4.isEnabled())
        self.assertFalse(self.panel.print_a4.isEnabled())
        self.assertFalse(self.window.export_a4_pdf())
        self.assertFalse(self.window.print_a4())
        self.assertTrue(self.window.inverse_checkbox.isChecked())
        self.assertIn("forward", self.panel.export_status.text())

    def test_snapshot_captures_current_gui_and_detaches_input_and_sky(self):
        native = self.set_subject()
        self.panel.configuration_buttons["fold"].click()
        self.panel.configuration_size.setValue(3)
        self.panel.input_zoom.setValue(150)
        self.panel.input_mirror.setCurrentIndex(self.panel.input_mirror.findData("on"))
        self.panel.source_scale.setValue(80)
        self.panel.source_offset_x.setValue(25)
        self.window.lenslight_checkbox.setChecked(True)
        self.window.critical_checkbox.setChecked(True)
        self.window.ellipses_source_plane = [[self.window.base_w / 2, self.window.base_h / 2]]
        snapshot = self.window.capture_print_snapshot()
        self.assertEqual(snapshot.input.configuration, "fold")
        self.assertEqual(snapshot.input.size_percent, 3)
        self.assertEqual(snapshot.input.zoom, 150)
        self.assertTrue(snapshot.input.mirror)
        self.assertEqual(snapshot.display.scale, 0.8)
        self.assertEqual(snapshot.display.offset_x, 0.25)
        self.assertEqual(snapshot.display.source_markers, ((0.5, 0.5),))
        self.assertTrue(snapshot.display.lens_light)
        self.assertTrue(snapshot.display.curves)
        self.assertEqual(snapshot.lens.radius, self.window.b_value)
        np.testing.assert_array_equal(snapshot.raw_bgr, native)
        self.window.background.image[:] = 0
        self.window.static_source.set_frame(np.zeros_like(native))
        np.testing.assert_array_equal(snapshot.raw_bgr, native)
        self.assertTrue(np.any(snapshot.sky_rgb))

    def test_reset_buttons_use_the_loaded_gui_defaults(self):
        panel = self.panel
        original = self.window.gui_defaults
        key = replace(original.input.key, enabled=True, tolerance=47)
        self.window.gui_defaults = replace(
            original,
            input=replace(
                original.input,
                key=key,
                framing="fit",
                mirror="on",
                preview="source",
                zoom=135,
                frozen_input_fitting="fill",
            ),
            configuration=replace(
                original.configuration, size=32, preset="fold"
            ),
            placement=replace(
                original.placement, scale=80, offset_x=15, offset_y=-20
            ),
        )
        with patch.object(self.window, "update_view"):
            panel.key_enabled.setChecked(False)
            panel.key_tolerance.setValue(10)
            panel.input_zoom.setValue(100)
            self.window._reset_input_settings()
            self.assertTrue(panel.key_enabled.isChecked())
            self.assertEqual(panel.key_tolerance.value(), 47)
            self.assertEqual(panel.input_frame_mode.currentData(), "fit")
            self.assertEqual(panel.input_mirror.currentData(), "on")
            self.assertEqual(panel.input_preview.currentData(), "source")
            self.assertEqual(panel.input_zoom.value(), 135)

            panel.configuration_size.setValue(10)
            self.window._reset_configuration()
            self.assertEqual(panel.configuration_size.value(), 32)
            self.assertTrue(panel.configuration_buttons["fold"].isChecked())

            panel.source_scale.setValue(25)
            self.window._reset_source_placement()
            self.assertEqual(
                self.window._source_placement(), (0.8, 0.15, -0.2)
            )

    def test_capture_is_independent_of_preview_and_dual_mode(self):
        self.set_subject()
        before = self.window.capture_print_snapshot()
        self.panel.input_preview.setCurrentIndex(2)
        self.window.dual_checkbox.setChecked(True)
        after = self.window.capture_print_snapshot()
        self.assertEqual(before.lens, after.lens)
        self.assertEqual(before.input, after.input)
        self.assertEqual(before.display, replace(after.display, marker_radius=before.display.marker_radius))
        np.testing.assert_array_equal(before.raw_bgr, after.raw_bgr)
        np.testing.assert_array_equal(
            render_snapshot(before, side=128, montage_size=(128, 128)).montage,
            render_snapshot(after, side=128, montage_size=(128, 128)).montage,
        )

    def test_freezing_webcam_preserves_native_pixels_and_default_mirror_for_print(self):
        native = np.full((24, 32, 3), (20, 70, 180), np.uint8)
        captures = []

        def factory(index):
            capture = fixtures.FakeCapture(frame=native.copy())
            captures.append(capture)
            return capture

        self.window.camera_worker._capture_factory = factory
        self.panel.open_camera.click()
        self.wait_until(lambda: self.window.cam)
        self.assertFalse(self.panel.export_a4.isEnabled())
        self.panel.freeze_input.click()
        self.wait_until(lambda: captures[0].released)
        self.assertTrue(self.panel.export_a4.isEnabled())
        snapshot = self.window.capture_print_snapshot()
        self.assertTrue(snapshot.input.mirror)
        np.testing.assert_array_equal(snapshot.raw_bgr, native)

    def test_square_print_montage_matches_gui_keyed_scene_and_overlays(self):
        self.set_subject()
        self.window.lenslight_checkbox.setChecked(True)
        self.window.critical_checkbox.setChecked(True)
        self.panel.source_scale.setValue(100)
        self.window.update_view()
        side = self.window.base_w
        if side % 2:
            self.window.resize(self.window.width() + 1, self.window.height())
            self.application.processEvents()
            self.window.update_view()
            side = self.window.base_w
        self.assertEqual(side % 2, 0)
        scene = render_snapshot(self.window.capture_print_snapshot(), side=side, montage_size=(side, side))
        np.testing.assert_array_equal(scene.montage, self.displayed_rgb())

    def test_cancel_does_not_render_or_write(self):
        with (
            patch.object(desktop.QtWidgets.QFileDialog, "getSaveFileName", return_value=("", "")),
            patch.object(desktop, "write_a4_pdf") as writer,
        ):
            self.assertFalse(self.window.export_a4_pdf())
            writer.assert_not_called()

    def test_print_dialog_cancel_does_not_start_printing(self):
        self.set_subject()
        with (
            patch.object(desktop.QtPrintSupport, "QPrintDialog") as dialog,
            patch.object(desktop, "print_a4_snapshot") as printer,
        ):
            dialog.return_value.exec.return_value = desktop.QtWidgets.QDialog.Rejected
            self.assertFalse(self.window.print_a4())
            printer.assert_not_called()

    def test_print_dialog_uses_the_captured_snapshot(self):
        self.set_subject()
        radius = self.window.b_value
        with (
            patch.object(desktop.QtPrintSupport, "QPrinter") as printer_class,
            patch.object(desktop.QtPrintSupport, "QPrintDialog") as dialog,
            patch.object(desktop, "print_a4_snapshot", return_value=SimpleNamespace(warnings=())) as printer,
        ):
            printer_class.HighResolution = object()
            printer_class.return_value.setPageLayout.return_value = True
            dialog.return_value.exec.return_value = desktop.QtWidgets.QDialog.Accepted
            self.assertTrue(self.window.print_a4())
        snapshot, selected_printer = printer.call_args.args
        self.assertEqual(snapshot.lens.radius, radius)
        self.assertIs(selected_printer, printer_class.return_value)
        self.assertIs(dialog.call_args.args[0], selected_printer)
        self.assertIn("sent to the printer", self.panel.export_status.text())
        self.assertTrue(self.panel.print_a4.isEnabled())

    def test_export_uses_pre_dialog_snapshot_and_restores_timer_controls_on_failure(self):
        self.set_subject()
        radius = self.window.b_value
        self.window.timer.start()

        def choose(*args):
            self.window.sliderb.setValue(75)
            return "example.pdf", ""

        with (
            patch.object(desktop.QtWidgets.QFileDialog, "getSaveFileName", side_effect=choose),
            patch.object(desktop, "write_a4_pdf", side_effect=ImageError("Cannot save test PDF")) as writer,
        ):
            self.assertFalse(self.window.export_a4_pdf())
        self.assertEqual(writer.call_args.args[0].lens.radius, radius)
        self.assertIn("Cannot save", self.panel.export_status.text())
        self.assertTrue(self.window.timer.isActive())
        self.assertTrue(self.panel.isEnabled())
        self.assertTrue(self.panel.export_a4.isEnabled())
        self.assertIsNone(desktop.QtWidgets.QApplication.overrideCursor())
        self.window.timer.stop()

    def test_success_extension_and_custom_background_attribution(self):
        self.set_subject()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "page"
            with (
                patch.object(desktop.QtWidgets.QFileDialog, "getSaveFileName", return_value=(str(path), "")),
                patch.object(desktop, "write_a4_pdf", return_value=SimpleNamespace(warnings=())) as writer,
            ):
                self.assertTrue(self.window.export_a4_pdf())
            self.assertEqual(writer.call_args.args[1], path.with_suffix(".pdf"))
            self.assertIn("saved", self.panel.export_status.text())
            self.assertFalse(self.window.timer.isActive())

    def test_appended_extension_never_silently_overwrites_and_bad_suffix_reports_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "page"
            path.with_suffix(".pdf").write_bytes(b"existing")
            with (
                patch.object(desktop.QtWidgets.QFileDialog, "getSaveFileName", return_value=(str(path), "")),
                patch.object(desktop.QtWidgets.QMessageBox, "question", return_value=desktop.QtWidgets.QMessageBox.No),
                patch.object(desktop, "write_a4_pdf") as writer,
            ):
                self.assertFalse(self.window.export_a4_pdf())
                writer.assert_not_called()
            self.assertEqual(path.with_suffix(".pdf").read_bytes(), b"existing")
            with patch.object(desktop.QtWidgets.QFileDialog, "getSaveFileName", return_value=("page.jpg", "")):
                self.assertFalse(self.window.export_a4_pdf())
            self.assertIn(".pdf", self.panel.export_status.text())


if __name__ == "__main__":
    unittest.main()
