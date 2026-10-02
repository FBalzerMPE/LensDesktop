import threading
import time
import unittest

import numpy as np

from LensDesktop import sources
from LensDesktop.qt_compat import QtWidgets


class FakeCapture:
    def __init__(self, frame=None, opened=True, reads=None):
        self.frame = np.full((6, 8, 3), (10, 70, 190), np.uint8) if frame is None else frame
        self.opened = opened
        self.reads = reads
        self.released = False
        self.thread_ids = []

    def isOpened(self):
        self.thread_ids.append(threading.get_ident())
        return self.opened

    def read(self):
        self.thread_ids.append(threading.get_ident())
        if self.reads is not None:
            return self.reads.pop(0) if self.reads else (False, None)
        return True, self.frame

    def release(self):
        self.thread_ids.append(threading.get_ident())
        self.released = True


class FrameTests(unittest.TestCase):
    def test_bgra_normalization_preserves_bgr_colors(self):
        frame = np.full((3, 4, 4), (10, 70, 190, 255), np.uint8)
        output = sources.normalize_bgr(frame)
        self.assertEqual(output.shape, (3, 4, 3))
        self.assertTrue(output.flags.c_contiguous)
        np.testing.assert_array_equal(output[0, 0], (10, 70, 190))

    def test_invalid_frames_are_explicit_errors(self):
        for frame in (None, np.zeros((0, 4, 3), np.uint8),
                      np.zeros((4, 4), np.uint8), np.zeros((4, 4, 3), np.float32)):
            with self.subTest(frame=type(frame)):
                with self.assertRaises(sources.SourceError):
                    sources.normalize_bgr(frame)
        with self.assertRaises(sources.SourceError):
            sources.read_camera_frame(FakeCapture(reads=[(False, None)]))

    def test_portrait_landscape_and_square_framing(self):
        for height, width in ((8, 4), (4, 8), (5, 5)):
            frame = np.full((height, width, 3), (10, 70, 190), np.uint8)
            output = sources.frame_for_canvas(frame, 10, 10, camera=True)
            self.assertEqual(output.shape, (20, 20, 3))
            self.assertTrue(output.flags.c_contiguous)
            np.testing.assert_array_equal(output[0, 0], (10, 70, 190))

    def test_webcam_is_mirrored_without_mirroring_desktop(self):
        frame = np.zeros((4, 4, 3), np.uint8)
        frame[:, :2] = (10, 70, 190)
        camera = sources.frame_for_canvas(frame, 4, 4, camera=True)
        desktop = sources.frame_for_canvas(frame, 4, 4, camera=False)
        np.testing.assert_array_equal(camera[0, -1], (10, 70, 190))
        np.testing.assert_array_equal(desktop[0, 0], (10, 70, 190))


class CameraWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QtWidgets.QApplication.instance()
        if cls.application is None:
            cls.application = QtWidgets.QApplication([])

    def setUp(self):
        self.captures = []
        self.factory = lambda index: FakeCapture()
        self.worker = sources.CameraWorker(capture_factory=self.create_capture)
        self.opened = []
        self.failed = []
        self.disconnected = []
        self.discovered = []
        self.worker.opened.connect(lambda *args: self.opened.append(args))
        self.worker.failed.connect(lambda *args: self.failed.append(args))
        self.worker.disconnected.connect(lambda *args: self.disconnected.append(args))
        self.worker.discovered.connect(lambda *args: self.discovered.append(args))

    def create_capture(self, index):
        capture = self.factory(index)
        self.captures.append((index, capture))
        return capture

    def wait_until(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            self.application.processEvents()
            time.sleep(0.005)
        self.application.processEvents()
        self.assertTrue(predicate(), "Camera worker did not complete in time")

    def tearDown(self):
        self.worker.shutdown()
        self.assertTrue(self.worker.wait(3000))
        self.application.processEvents()
        self.assertTrue(all(cap.released for _, cap in self.captures))

    def test_successful_switch_releases_previous_capture(self):
        token = self.worker.select(0)
        self.wait_until(lambda: len(self.opened) == 1)
        self.assertEqual(self.opened[0], (token, 0))
        first = self.captures[0][1]
        self.worker.select(1)
        self.wait_until(lambda: len(self.opened) == 2)
        self.assertTrue(first.released)
        self.assertIsNotNone(self.worker.snapshot(self.opened[-1][0]))
        ids = {identifier for _, cap in self.captures for identifier in cap.thread_ids}
        self.assertEqual(len(ids), 1)
        self.assertNotIn(threading.get_ident(), ids)

    def test_failed_open_keeps_previous_camera(self):
        token = self.worker.select(0)
        self.wait_until(lambda: len(self.opened) == 1)
        self.factory = lambda index: FakeCapture(opened=False)
        self.worker.select(1)
        self.wait_until(lambda: bool(self.failed))
        self.assertFalse(self.captures[0][1].released)
        self.assertTrue(self.captures[-1][1].released)
        self.assertIsNotNone(self.worker.snapshot(token))

    def test_failed_initial_read_releases_candidate(self):
        self.factory = lambda index: FakeCapture(reads=[(False, None)])
        self.worker.select(0)
        self.wait_until(lambda: bool(self.failed))
        self.assertFalse(self.opened)
        self.assertTrue(self.captures[0][1].released)

    def test_disconnect_clears_frame_and_releases_camera(self):
        frame = np.zeros((4, 4, 3), np.uint8)
        self.factory = lambda index: FakeCapture(reads=[(True, frame), (False, None)])
        token = self.worker.select(0)
        self.wait_until(lambda: bool(self.disconnected))
        self.assertIsNone(self.worker.snapshot(token))
        self.assertTrue(self.captures[0][1].released)

    def test_snapshot_is_independent_of_camera_buffers(self):
        token = self.worker.select(0)
        self.wait_until(lambda: bool(self.opened))
        frame = self.worker.snapshot(token)
        frame[:] = 0
        np.testing.assert_array_equal(self.worker.snapshot(token)[0, 0], (10, 70, 190))

    def test_selecting_active_camera_reuses_capture_and_updates_token(self):
        self.worker.select(0)
        self.wait_until(lambda: bool(self.opened))
        token = self.worker.select(0)
        self.wait_until(lambda: len(self.opened) == 2)
        self.assertEqual(len(self.captures), 1)
        self.assertIsNotNone(self.worker.snapshot(token))

    def test_discovery_does_not_reopen_active_camera(self):
        token = self.worker.select(0)
        self.wait_until(lambda: bool(self.opened))
        self.worker.discover()
        self.wait_until(lambda: bool(self.discovered))
        self.assertEqual([index for index, _ in self.captures].count(0), 1)
        self.assertFalse(self.captures[0][1].released)
        self.assertIsNotNone(self.worker.snapshot(token))

    def test_new_selection_cancels_stale_open(self):
        started = threading.Event()
        unblock = threading.Event()

        def factory(index):
            if index == 0:
                started.set()
                unblock.wait(2)
            return FakeCapture()

        self.factory = factory
        self.worker.select(0)
        self.assertTrue(started.wait(1))
        token = self.worker.select(1)
        unblock.set()
        self.wait_until(lambda: bool(self.opened))
        self.assertEqual(self.opened, [(token, 1)])
        self.assertTrue(self.captures[0][1].released)

    def test_discovery_is_bounded_and_releases_probes(self):
        self.factory = lambda index: FakeCapture(opened=index == 2)
        token = self.worker.discover()
        self.wait_until(lambda: bool(self.discovered))
        self.assertEqual([index for index, _ in self.captures], list(range(5)))
        self.assertEqual(self.discovered[0][:3], (token, [2], False))
        self.assertTrue(all(cap.released for _, cap in self.captures))

    def test_discovery_cancellation_is_observed_between_driver_calls(self):
        started = threading.Event()
        unblock = threading.Event()

        def factory(index):
            started.set()
            unblock.wait(2)
            return FakeCapture()

        self.factory = factory
        self.worker.discover()
        self.assertTrue(started.wait(1))
        self.worker.cancel_discovery()
        unblock.set()
        self.wait_until(lambda: bool(self.discovered))
        self.assertTrue(self.discovered[0][2])
        self.assertEqual(len(self.captures), 1)

    def test_desktop_request_cancels_inflight_open(self):
        started = threading.Event()
        unblock = threading.Event()

        def factory(index):
            started.set()
            unblock.wait(2)
            return FakeCapture()

        self.factory = factory
        self.worker.select(0)
        self.assertTrue(started.wait(1))
        self.worker.use_desktop()
        unblock.set()
        self.wait_until(lambda: self.captures and self.captures[0][1].released)
        self.assertFalse(self.opened)


if __name__ == "__main__":
    unittest.main()
