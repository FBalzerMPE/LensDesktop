from dataclasses import dataclass, field
from itertools import count
from queue import Empty, Queue
from threading import Event, Lock
from pathlib import Path

import cv2
import numpy as np

from .qt_compat import QT_PKG, QtCore
from .processing import fit_background, read_image_bgr


Signal = QtCore.pyqtSignal if QT_PKG.startswith("PyQt") else QtCore.Signal


class SourceError(RuntimeError):
    pass


def normalize_bgr(frame: np.ndarray) -> np.ndarray:
    if (
        not isinstance(frame, np.ndarray)
        or frame.dtype != np.uint8
        or frame.ndim != 3
        or frame.shape[0] == 0
        or frame.shape[1] == 0
        or frame.shape[2] not in (3, 4)
    ):
        raise SourceError("The source did not provide a valid BGR/BGRA image.")
    if frame.shape[2] == 4:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    return np.ascontiguousarray(frame)


def read_camera_frame(capture) -> np.ndarray:
    ok, frame = capture.read()
    if not ok or frame is None:
        raise SourceError("No webcam frame received. Check the connection and camera permissions.")
    return normalize_bgr(frame)


def frame_for_canvas(
    frame: np.ndarray, width: int, height: int, *, camera: bool
) -> np.ndarray:
    if camera:
        side = min(frame.shape[:2])
        top = (frame.shape[0] - side) // 2
        left = (frame.shape[1] - side) // 2
        frame = frame[top:top + side, left:left + side]
    frame = cv2.resize(frame, (width * 2, height * 2))
    return cv2.flip(frame, 1) if camera else frame


class StaticSource:
    def __init__(self):
        self.frame: np.ndarray | None = None
        self.path: Path | None = None
        self.mirror = False
        self._cache_key: tuple[int, int, str] | None = None
        self._cache: np.ndarray | None = None

    def set_frame(self, frame: np.ndarray, *, mirror: bool = False, path: Path | None = None):
        owned = normalize_bgr(frame).copy()
        owned.setflags(write=False)
        self.frame = owned
        self.path = path
        self.mirror = mirror
        self._cache_key = None
        self._cache = None

    def load(self, path: str | Path):
        path = Path(path)
        self.set_frame(read_image_bgr(path), path=path)

    def snapshot(self) -> np.ndarray:
        if self.frame is None:
            raise SourceError("No static input image is available. Load an image or freeze live input.")
        return self.frame.copy()

    def render_frame(self, width: int, height: int, mode: str) -> np.ndarray:
        if self.frame is None:
            raise SourceError("No static input image is available. Load an image or freeze live input.")
        key = (width, height, mode)
        if key != self._cache_key:
            if self.mirror and mode == "fill":
                image = frame_for_canvas(self.frame, width, height, camera=True)
            else:
                image = fit_background(self.frame, width * 2, height * 2, mode)
                if self.mirror:
                    image = cv2.flip(image, 1)
            image.setflags(write=False)
            self._cache = image
            self._cache_key = key
        assert self._cache is not None
        return self._cache.copy()


@dataclass
class _Request:
    token: int
    index: int = 0
    cancelled: Event = field(default_factory=Event)


class CameraWorker(QtCore.QThread):
    opened = Signal(int, int)
    failed = Signal(int, str)
    disconnected = Signal(int, str)
    discovered = Signal(int, object, bool, str)

    def __init__(self, parent=None, capture_factory=None):
        super().__init__(parent)
        self._capture_factory = capture_factory or cv2.VideoCapture
        self._commands: Queue[tuple[str, _Request | None]] = Queue()
        self._tokens = count(1)
        self._stop = Event()
        self._lock = Lock()
        self._frame: np.ndarray | None = None
        self._frame_token: int | None = None
        self._capture = None
        self._index: int | None = None
        self._switch_request: _Request | None = None
        self._discovery_request: _Request | None = None
        self._started = False

    def _start_if_needed(self):
        if self._stop.is_set():
            raise RuntimeError("The camera worker has already been shut down.")
        if not self._started:
            self._started = True
            self.start()

    def select(self, index: int) -> int:
        if not 0 <= index <= 99:
            raise ValueError("Camera index must be between 0 and 99.")
        if self._switch_request is not None:
            self._switch_request.cancelled.set()
        self.cancel_discovery()
        request = _Request(next(self._tokens), index)
        self._switch_request = request
        self._commands.put(("select", request))
        self._start_if_needed()
        return request.token

    def discover(self) -> int:
        self.cancel_discovery()
        request = _Request(next(self._tokens))
        self._discovery_request = request
        self._commands.put(("discover", request))
        self._start_if_needed()
        return request.token

    def cancel_discovery(self):
        if self._discovery_request is not None:
            self._discovery_request.cancelled.set()

    def use_desktop(self):
        if self._switch_request is not None:
            self._switch_request.cancelled.set()
        self.cancel_discovery()
        if self._started:
            self._commands.put(("desktop", None))

    def snapshot(self, token: int | None) -> np.ndarray | None:
        with self._lock:
            if self._frame_token != token or self._frame is None:
                return None
            return self._frame.copy()

    def shutdown(self):
        if self._switch_request is not None:
            self._switch_request.cancelled.set()
        self.cancel_discovery()
        self._stop.set()

    def _publish(self, token: int, frame: np.ndarray):
        with self._lock:
            self._frame_token = token
            self._frame = frame.copy()

    def _release_active(self):
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        self._index = None
        with self._lock:
            self._frame = None
            self._frame_token = None

    def _open_camera(self, index: int, cancelled: Event):
        capture = self._capture_factory(index)
        try:
            if cancelled.is_set() or self._stop.is_set():
                raise SourceError("Camera opening cancelled.")
            if not capture.isOpened():
                raise SourceError(
                    f"Cannot open camera {index}. Check the index, permissions, "
                    "and whether another application is using it."
                )
            return capture, read_camera_frame(capture)
        except (SourceError, cv2.error):
            capture.release()
            raise

    def _switch(self, request: _Request):
        if request.cancelled.is_set():
            return
        if self._capture is not None and self._index == request.index:
            with self._lock:
                self._frame_token = request.token
            self.opened.emit(request.token, request.index)
            return
        try:
            capture, frame = self._open_camera(request.index, request.cancelled)
        except (SourceError, cv2.error) as error:
            if not request.cancelled.is_set() and not self._stop.is_set():
                self.failed.emit(request.token, str(error))
            return
        if request.cancelled.is_set() or self._stop.is_set():
            capture.release()
            return
        self._release_active()
        self._capture = capture
        self._index = request.index
        self._publish(request.token, frame)
        self.opened.emit(request.token, request.index)

    def _discover(self, request: _Request):
        indices = []
        errors = []
        for index in range(5):
            if request.cancelled.is_set() or self._stop.is_set():
                break
            if self._capture is not None and index == self._index:
                indices.append(index)
                continue
            capture = None
            try:
                capture = self._capture_factory(index)
                if request.cancelled.is_set() or self._stop.is_set():
                    break
                if capture.isOpened():
                    read_camera_frame(capture)
                    indices.append(index)
            except (SourceError, cv2.error) as error:
                errors.append(f"Camera {index}: {error}")
            finally:
                if capture is not None:
                    capture.release()
        self.discovered.emit(
            request.token, indices, request.cancelled.is_set(), "\n".join(errors)
        )

    def run(self):
        try:
            while not self._stop.is_set():
                try:
                    kind, request = self._commands.get(timeout=0.03)
                except Empty:
                    if self._stop.is_set():
                        break
                    if self._capture is None:
                        continue
                    token = self._frame_token
                    assert token is not None
                    try:
                        frame = read_camera_frame(self._capture)
                        self._publish(token, frame)
                    except (SourceError, cv2.error) as error:
                        index = self._index
                        self._release_active()
                        self.disconnected.emit(token, f"Camera {index}: {error}")
                    continue
                if kind == "select":
                    assert request is not None
                    self._switch(request)
                elif kind == "discover":
                    assert request is not None
                    self._discover(request)
                elif kind == "desktop":
                    self._release_active()
        finally:
            self._release_active()
