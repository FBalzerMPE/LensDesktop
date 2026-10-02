"""
This Python Tool is a Desktop Lens. When executed it will record the screen below it
and either lens it or de-lens it according to an softened SIE model.

The slider parameters are:

Mask Radius : Radius of a mask for the inverse mode (to cut away lens light that is close to the center).
Position Angle : Position angle that allows to change the orientation of the lens mass profile.
Core Radius : Softening scale / core radius of the power law mass profile.
Axis Ratio : Minor-to-Major axis ratio of the mass profile.
Einstein Radius : Einstein Radius of the mass profile.

You can use the following shortcuts:

Ctrl+S : To Save the currently shown screen (without the GUI printed on top of it).
Ctrl+F : To switch desktop/webcam input or reveal camera controls.
Ctrl+R : To Save a sequence of images in which the Einstein radius increases up
         to its current value (this allows to create nice gifs, e.g. using ffmpeg to postprocess the images).
Ctrl+V : To turn some of the GUI elements on/off.

Use Rightclick to add / remove an RBG circle. This can be used to show Parity of images, magnification and sheer, and conjugate points.
Notice that it matters on which side of the dual view you click when creating this RBG circle, since this will decide the where the circle is anchored to.

I only used this Code on my Macbook where it ran in almost real time. I have not yet confirmed if it is supported by other operating systems.
If it does not work, but you found a fix, please let me know so that we can include it in upcoming versions!

I used ChatGPT o4/o3 to deal with the GUI elements of this Code or to help me figure out how to add the Camera recording and minor things.
If you have any suggestions for how to improve anything or if you want new features to be added, just drop me a message!

The Code in its current form shows some unexpected behaviour for multiple screens when you are not in the main screen.
I plan on fixing this in future versions!

Copyright (c) 2025, Wolfgang Enzi
"""

__author__ = "WolfgangEnzi"

# Import packages
import sys
import gc
import numpy as np
import cv2
import mss
from mss.exception import ScreenShotError
from functools import partial
from pathlib import Path
from scipy.interpolate import RegularGridInterpolator as interp
from scipy.ndimage import zoom
from .qt_compat import QT_PKG, QtWidgets, QtCore, QtGui
from .controls import SettingsPanel
from .sources import CameraWorker, SourceError, StaticSource, normalize_bgr, frame_for_canvas
from .processing import (
    ImageError, SkyBackground, default_background_path, example_source_path,
    place_layer, unplace_point, write_image_bgr,
)

# Set window extent
# base_w = 600
# base_h = 600
ps = 20

import time

QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

print(f"[info] Using {QT_PKG}")

# from QtWidgets import QtWidgets.QApplication, QtWidgets.QLabel, QtWidgets.QMainWindow, QtWidgets.QSlider, QtWidgets.QSlider, QtWidgets.QFileDialog, QtWidgets.QShortcut
# from QtCore import Qt, QtCore.QTimer
# from QtGui import QtGui.QImage, QtGui.QPixmap, QtGui.QKeySequence


def reduce_points(points, threshold):
    points = [np.array(p) for p in points]
    unique = []

    for p in points:
        if not any(np.linalg.norm(p - u) <= threshold for u in unique):
            unique.append(p)

    return np.array([tuple(p) for p in unique])


def heart_shape(x, y):
    """
    Easteregg Heart-shaped multiplier, to show our love for lensing.

    Parameters
    ----------
    x, y : int
        The x and y position values at which to evaluate the height map that generates a heart shape

    Returns
    -------
    height : numpy.array
        The height of the filter that generates the heart shape of the easteregg
    """
    z = 0.5 * x**2 + (-1.2 * y + 0.35 - np.sqrt(abs(x * 0.75))) ** 2
    height = 1 / (1 + np.exp(5 * (z - 0.3)))
    return height


eps = 1e-5


def SIE_defl(xx, yy, t, s, heart, q, b):
    ct, st = np.cos(t), np.sin(t)
    xv, yv = ct * xx - st * yy, st * xx + ct * yy
    r = np.sqrt(q * q * (xv * xv + s * s) + yv * yv)
    if b == 0:
        return np.zeros_like(xx), np.zeros_like(yy), r
    fac = 1.0
    if heart:
        fac = heart_shape(xv, yv)
    A = b * q / np.sqrt(1 - q * q)
    deflx = A * np.arctan(np.sqrt(1 - q * q) * xv / (r + s)) * fac
    defly = A * np.arctanh(np.sqrt(1 - q * q) * yv / (r + q * q * s)) * fac
    deflxv = ct * deflx + st * defly
    deflyv = -st * deflx + ct * defly
    return deflxv, deflyv, r


def create_SIE_map(width, height, b=0.75, q=0.79, s=0.0001, t=0.0, heart=False):
    """
    Function that computes the source positions and deflection angles.
    When precomputed for fixed parameters, it is possible to map an image from the source plane
    to the image plane according to a softened Singular Isothermal Ellipsoid (SIE) profile in
    almost real time.
    Fore reference check https://arxiv.org/pdf/astro-ph/0102341.

    Parameters
    ----------
    width, height : int
        The window width and height determine all the x and y coordinates that are mapped to the source plane.

    Returns
    -------
    map_x, map_y : int
        The map of source positions after the displacement of the softened SIE is applied.
    deflxv, deflyv : int
        The deflection angle maps of the softened SIE.
    xx, yy : int
        The original positions of the grid on the image plane.
    """
    Lx = 2 * width / max(width, height)
    Ly = 2 * height / max(width, height)
    x = np.linspace(-1, 1, width) * Lx / 2
    y = np.linspace(-1, 1, height) * Ly / 2
    xx, yy = np.meshgrid(x, y)
    deflxv, deflyv, r = SIE_defl(xx, yy, t, s, heart, q, b)
    xv_new = xx - deflxv
    yv_new = yy - deflyv
    map_x = ((xv_new + Lx / 2) * (width - 1)).astype(np.float32)
    map_y = ((yv_new + Ly / 2) * (height - 1)).astype(np.float32)
    kappa = 0.5 * b / (1e-30 + r * r / q / q)
    # in the future one could also add the easteregg heartshape to this
    return (
        map_x,
        map_y,
        deflxv,
        deflyv,
        xx.astype(np.float32),
        yy.astype(np.float32),
        kappa,
    )


def inverse_remap_image(lensed_img, x_idx, y_idx, mask_radius, base_w, base_h, *, return_alpha=False):
    """
    Optimized inverse remapping using flat indexing and manual filling of the 2D histogram
    that becomes the reconstructed source. When precomputed for fixed parameters, it is possible
    to map an image back to the source plane according to a softened SIE profile in almost real time.
    Fore reference check https://arxiv.org/pdf/astro-ph/0102341.

    I thank Tian Li for coming up with the name of this mode of the tool, i.e. "Humantonian Monte Carlo".

    Parameters
    ----------
    lensed_img : numpy.array
        Input lensed image that is de-lensed to produce the source reconstruction.
    x_idx, y_idx : int
        The histogram indices obtained from the mapping to the source plane.
    mask_radius=-1 : int
        Radius of the mask that can be used to avoid contamination from lens light.

    Returns
    -------
    inv_img : numpy.array

    """

    h, w, c = lensed_img.shape
    assert c == 3
    inv_img = np.zeros((h * w, 3), dtype=np.float32)
    count = np.zeros((h * w,), dtype=np.float32)

    # Flatten image and indices
    xx, yy = np.meshgrid(np.arange(base_w), np.arange(base_h))
    r2 = (yy.flatten() - base_h // 2) ** 2 + (
        xx.flatten() - base_w // 2
    ) ** 2 > mask_radius**2
    flat_img = lensed_img.reshape(-1, 3).astype(np.float32)[r2]
    flat_indices = (y_idx * w + x_idx)[r2]

    # Accumulate values
    np.add.at(inv_img, flat_indices, flat_img)
    np.add.at(count, flat_indices, 1)

    # Avoid division by zero
    mask = count == 0
    coverage = (~mask).reshape(h, w).astype(np.float32) if return_alpha else None

    if flat_img.size == 0:
        mean_color = np.array([0, 0, 0])
    else:
        mean_color = flat_img.mean(axis=0)

    count[mask] = 1
    inv_img[mask] = mean_color

    inv_img = (inv_img / count[:, None]).reshape(h, w, 3).astype(np.uint8)
    if return_alpha:
        assert coverage is not None
        return inv_img, coverage
    return inv_img


def draw_lens_light(b, kappa, SIE_map_rgb, base_w, base_h):
    # A pseudo lens light distribution. I could have picked a Sersic profile, but this seemed simpler and more directly related to the mass distribution.
    if b > 0:
        img2 = np.zeros((base_h, base_w, 3))
        img2[:, :, 0] = 255
        img2[:, :, 1] = 200
        img2[:, :, 2] = 130
        lkappa = np.log10(1 + kappa)
        alpha = np.clip(lkappa, 0, 1)
        for i in range(3):
            SIE_map_rgb[:, :, i] = (
                SIE_map_rgb[:, :, i] * (1 - alpha) + img2[:, :, i] * alpha
            )
    return SIE_map_rgb


# -------------------------


def exclude_from_capture(widget) -> bool:
    plat = sys.platform
    if plat == "darwin":
        try:
            from ctypes import c_void_p
            import objc
            from Cocoa import NSWindowSharingNone

            nsview = objc.objc_object(c_void_p=int(widget.winId()))
            nswindow = nsview.window()
            if nswindow is None:
                return False
            nswindow.setSharingType_(NSWindowSharingNone)
            return True
        except Exception:
            return False
    if plat.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes

            hwnd = int(widget.winId())
            user32 = ctypes.windll.user32
            WDA_EXCLUDEFROMCAPTURE = 0x11  # Win11 22H2+
            res = user32.SetWindowDisplayAffinity(
                wintypes.HWND(hwnd), WDA_EXCLUDEFROMCAPTURE
            )
            return bool(res)
        except Exception:
            return False
    return False


class LensDesktop(QtWidgets.QMainWindow):
    """
    This class is a QtWidgets.QMainWindow of the application that does the lensing of the Desktop / Camera input.
    """

    def __init__(self, camera_factory=None):
        """
        Create a new Window in which the application lives.
        Define all relevant parameters used during the run time of the Script.
        Define the sliders and the initial state of the application.
        """
        super().__init__()

        self.setWindowTitle("Lens Desktop")

        self._ready = False
        self.gui_hidden = False
        self.heart = False
        self.frame = True
        self.old_pos = None
        self._closing = False

        # capture setup
        self.sct = mss.MSS()
        try:
            self.mon = self.sct.monitors[0]
            self.w_full = self.mon["width"]
            self.h_full = self.mon["height"]
            self.base_w = self.w_full // 4
            self.base_h = self.w_full // 4
        except Exception:
            QtWidgets.QMessageBox.critical(self, "Error", f"Invalid monitor index 0")
            sys.exit(1)

        self.cam = False
        self.selected_camera_index = None
        self.camera_token = None
        self._pending_camera = None
        self._discovery_token = None
        self._camera_fault = False
        self._last_source_error = None
        self._last_background_error = None
        self.background = SkyBackground()
        self.static_source = StaticSource()
        self.static_active = False

        self.setWindowFlags(QtCore.Qt.Window)
        central = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.canvas = QtWidgets.QWidget()
        self.canvas.setMinimumSize(120, 120)
        self.canvas.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        self.canvas.setAutoFillBackground(True)
        self.canvas.setBackgroundRole(QtGui.QPalette.Dark)
        self.canvas.installEventFilter(self)
        self.label = QtWidgets.QLabel(self.canvas)
        self.label.setGeometry(0, 0, self.base_w, self.base_h)
        self.label.installEventFilter(self)
        self.label.setToolTip("Drag to move the window. Right-click to toggle a marker.")
        self.settings_panel = SettingsPanel()
        layout.addWidget(self.canvas, 1)
        layout.addWidget(self.settings_panel)
        self.setCentralWidget(central)

        for name in (
            "critical_checkbox", "dual_checkbox", "inverse_checkbox",
            "lenslight_checkbox", "sliderb", "labelb", "sliderq", "labelq",
            "sliders", "labels", "slidert", "labelt", "slider_mask", "label_mask",
        ):
            setattr(self, name, getattr(self.settings_panel, name))

        self.dual_checkbox.stateChanged.connect(self.dual_view_toggled)
        self.inverse_checkbox.stateChanged.connect(self.update_view)
        self.lenslight_checkbox.stateChanged.connect(self.update_view)
        self.critical_checkbox.stateChanged.connect(self.update_view)

        self.camera_worker = CameraWorker(self, capture_factory=camera_factory)
        self.camera_worker.opened.connect(self._camera_opened)
        self.camera_worker.failed.connect(self._camera_open_failed)
        self.camera_worker.disconnected.connect(self._camera_disconnected)
        self.camera_worker.discovered.connect(self._cameras_discovered)
        self.camera_worker.finished.connect(self._camera_worker_finished)
        self.settings_panel.source_selector.currentIndexChanged.connect(self._source_changed)
        self.settings_panel.source_selector.activated.connect(self._source_activated)
        self.settings_panel.camera_selector.currentIndexChanged.connect(self._camera_selected)
        self.settings_panel.refresh_cameras.clicked.connect(self._refresh_cameras)
        self.settings_panel.cancel_refresh.clicked.connect(self.camera_worker.cancel_discovery)
        self.settings_panel.open_camera.clicked.connect(self._open_camera_index)
        self.settings_panel.load_input_image.clicked.connect(self._choose_input_image)
        self.settings_panel.load_input_example.clicked.connect(self._load_input_example)
        self.settings_panel.freeze_input.clicked.connect(self._freeze_input)
        self.settings_panel.save_input.clicked.connect(self.save_input_image)
        self.settings_panel.input_fitting.currentIndexChanged.connect(self.update_view)
        self.settings_panel.load_background.clicked.connect(self._choose_background)
        self.settings_panel.clear_background.clicked.connect(self._clear_background)
        self.settings_panel.default_background.clicked.connect(self._default_background)
        self.settings_panel.background_mode.currentIndexChanged.connect(self.update_view)
        for control in (
            self.settings_panel.source_scale,
            self.settings_panel.source_offset_x,
            self.settings_panel.source_offset_y,
        ):
            control.valueChanged.connect(self.update_view)
        self.settings_panel.reset_placement.clicked.connect(self._reset_source_placement)

        # Timer for view updates.
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_view)
        refresh_rate_hz = 30  # e.g., 30 frames per second
        interval_ms = int(1000 / refresh_rate_hz)

        self.sliderb.valueChanged.connect(self.update_b_value)
        self.b_value = (65 - 40) / (99 - 40)
        self.sliderq.valueChanged.connect(self.update_q_value)
        self.q_value = 0.65
        self.sliders.valueChanged.connect(self.update_s_value)
        self.s_value = (41 - 40) / (99 - 40.0)
        self.slidert.valueChanged.connect(self.update_t_value)
        self.t_value = (95 - 40) / (99 - 40) * np.pi
        self.slider_mask.valueChanged.connect(self.update_mask)
        self.mask_radius = (
            (40 - 40) / (99 - 40) * np.sqrt(self.base_h**2 + self.base_w**2) / 2
        )

        # Shortcuts for several features.

        # Create shortcut 1: Save Screenshot
        save_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+S"), self)
        save_shortcut.activated.connect(self.save_screenshot)

        # Create shortcut 2: Valentines day Easteregg
        save_shortcut2 = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+L"), self)
        save_shortcut2.activated.connect(self.easteregg)

        # Create shortcut 3: Saving a sequence of einstein radii increasing over time
        save_shortcut3 = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+R"), self)
        save_shortcut3.activated.connect(self.recording)

        # Create shortcut 4: Change to camera recording
        save_shortcut4 = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+F"), self)
        save_shortcut4.activated.connect(self.camera_recording)

        # Create shortcut 5: Hide/Show GUI
        save_shortcut5 = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+V"), self)
        save_shortcut5.activated.connect(self.HideGUI)

        # Once the above is initialized create and draw the map.
        self.update_lensed_map()
        self.inv_map = partial(
            inverse_remap_image,
            x_idx=self.x_idx,
            y_idx=self.y_idx,
            mask_radius=self.mask_radius,
            base_w=self.base_w,
            base_h=self.base_h,
        )

        self.ellipses_image_plane = []
        self.ellipses_source_plane = []

        # try OS-level exclusion
        self.excluded = exclude_from_capture(self)
        self._default_background()
        self._ready = True
        available = self.screen().availableGeometry()
        self.resize(
            min(self.base_w + self.settings_panel.width(), available.width()),
            min(max(self.base_h, 360), available.height()),
        )
        self.timer.start(interval_ms)

    def _content_capture_rect_px(self):

        tl = self.label.mapToGlobal(QtCore.QPoint(0, 0))
        region = {
            "left": int(round(tl.x())),
            "top": int(round(tl.y())),
            "width": int(round(self.base_w)),
            "height": int(round(self.base_h)),
        }
        return region

    def capture_screen_rect(self):
        rect = self._content_capture_rect_px()
        raw = self.sct.grab(rect)
        return np.array(raw, dtype=np.uint8)

    def HideGUI(self):

        self.gui_hidden = not self.gui_hidden
        self.settings_panel.setVisible(not self.gui_hidden)
        if not self.isMaximized():
            delta = -self.settings_panel.width() if self.gui_hidden else self.settings_panel.width()
            self.resize(self.width() + delta, self.height())

        flags = self.windowFlags()

        if self.frame == True:
            flags |= QtCore.Qt.FramelessWindowHint
            flags |= QtCore.Qt.Window
        else:
            flags &= ~QtCore.Qt.FramelessWindowHint
        self.frame = not self.frame

        self.setWindowFlags(flags)
        self.show()
        self.excluded = exclude_from_capture(self)
        self.centralWidget().layout().activate()
        self._update_canvas_geometry()

    def set_Geometry_sliders_and_labels(self):
        self.settings_panel.set_inverse_mode(self.inverse_checkbox.isChecked())

    def _update_canvas_geometry(self):
        panels = 2 if self.dual_checkbox.isChecked() else 1
        side = max(2, min(self.canvas.width() // panels, self.canvas.height()))
        self.label.setGeometry(
            (self.canvas.width() - panels * side) // 2,
            (self.canvas.height() - side) // 2,
            panels * side,
            side,
        )
        if (side, side) != (self.base_w, self.base_h):
            scale = side / self.base_w
            self.ellipses_image_plane = [
                (x * scale, y * scale) for x, y in self.ellipses_image_plane
            ]
            self.ellipses_source_plane = [
                (x * scale, y * scale) for x, y in self.ellipses_source_plane
            ]
            self.base_w = self.base_h = side
            self.update_mask(self.slider_mask.value())
        self.update_view()

    def eventFilter(self, watched, event):
        if self._ready:
            if watched is self.canvas and event.type() == QtCore.QEvent.Resize:
                self._update_canvas_geometry()
            elif watched is self.label:
                if event.type() == QtCore.QEvent.MouseButtonPress:
                    self._canvas_mouse_press(event)
                    return True
                if event.type() == QtCore.QEvent.MouseMove:
                    self._canvas_mouse_move(event)
                    return True
                if event.type() == QtCore.QEvent.MouseButtonRelease:
                    self.old_pos = None
                    return True
        return super().eventFilter(watched, event)

    def camera_recording(self):
        if self._closing:
            return
        if self.cam or self._pending_camera is not None:
            self._use_desktop()
        elif self.selected_camera_index is not None:
            self._request_camera(self.selected_camera_index)
        else:
            self._show_camera_selector()

    def _show_camera_selector(self):
        if self.gui_hidden:
            self.HideGUI()
        self.settings_panel.ensureWidgetVisible(self.settings_panel.camera_selector)
        self.settings_panel.camera_selector.setFocus()
        self._source_status("Select a camera after Refresh, or use a manual camera index.")

    def _source_status(self, message, *, error=False):
        self.settings_panel.source_status.setText(message)
        self.statusBar().showMessage(message)
        if error and message != self._last_source_error:
            print(f"[error] {message}", file=sys.stderr)
        self._last_source_error = message if error else None

    def _sync_source_selector(self):
        source = "static" if self.static_active else "webcam" if self.cam else "desktop"
        with QtCore.QSignalBlocker(self.settings_panel.source_selector):
            selector = self.settings_panel.source_selector
            selector.setCurrentIndex(selector.findData(source))
        self.settings_panel.input_fitting.setEnabled(self.static_active)
        self.settings_panel.freeze_input.setEnabled(not self.static_active and not self._camera_fault)
        self.settings_panel.save_input.setEnabled(not self._camera_fault)

    def _source_changed(self):
        source = self.settings_panel.source_selector.currentData()
        if source == "desktop":
            self._use_desktop()
        elif source == "static":
            self._sync_source_selector()
            if self.static_source.frame is None:
                self._choose_input_image()
            else:
                self._activate_static_source()
        elif self.selected_camera_index is not None:
            self._request_camera(self.selected_camera_index)
        else:
            self._sync_source_selector()
            self._show_camera_selector()

    def _source_activated(self, index):
        if index == 0 and self._pending_camera is not None:
            self._use_desktop()

    def _camera_selected(self):
        index = self.settings_panel.camera_selector.currentData()
        if index is not None:
            self.selected_camera_index = index
            self.settings_panel.camera_index.setValue(index)
            if self.cam:
                self._request_camera(index)

    def _open_camera_index(self):
        self._request_camera(self.settings_panel.camera_index.value())

    def _request_camera(self, index):
        self._pending_camera = self.camera_worker.select(index)
        self._sync_source_selector()
        self._source_status(f"Opening camera {index}... Previous source remains active.")

    def _use_desktop(self):
        self.camera_worker.use_desktop()
        self._pending_camera = None
        self.cam = False
        self.static_active = False
        self.camera_token = None
        self._camera_fault = False
        self._sync_source_selector()
        self._source_status("Desktop capture")
        self.update_view()

    def _camera_opened(self, token, index):
        if self._closing or token != self._pending_camera:
            return
        self._pending_camera = None
        self.camera_token = token
        self.cam = True
        self.static_active = False
        self._camera_fault = False
        self.selected_camera_index = index
        self.settings_panel.camera_index.setValue(index)
        self._sync_source_selector()
        with QtCore.QSignalBlocker(self.settings_panel.camera_selector):
            selector = self.settings_panel.camera_selector
            item = selector.findData(index)
            if item < 0:
                selector.addItem(f"Camera {index}", index)
                item = selector.findData(index)
            selector.setCurrentIndex(item)
        self._source_status(f"Camera {index} active (center-cropped and mirrored).")
        self.update_view()

    def _camera_open_failed(self, token, message):
        if self._closing or token != self._pending_camera:
            return
        self._pending_camera = None
        self._sync_source_selector()
        self._source_status(f"{message} Previous source kept. Use index / retry to try again.", error=True)

    def _camera_disconnected(self, token, message):
        if self._closing or token != self.camera_token:
            return
        self._camera_fault = True
        self._sync_source_selector()
        self._source_status(
            f"{message} Last image is frozen. Use index / retry or select Desktop.",
            error=True,
        )

    def _refresh_cameras(self):
        self._discovery_token = self.camera_worker.discover()
        self.settings_panel.refresh_cameras.setEnabled(False)
        self.settings_panel.cancel_refresh.setEnabled(True)
        self._source_status("Scanning camera indices 0-4... A camera driver may take time to respond.")

    def _cameras_discovered(self, token, indices, cancelled, errors):
        if self._closing or token != self._discovery_token:
            return
        self._discovery_token = None
        self.settings_panel.refresh_cameras.setEnabled(True)
        self.settings_panel.cancel_refresh.setEnabled(False)
        with QtCore.QSignalBlocker(self.settings_panel.camera_selector):
            selector = self.settings_panel.camera_selector
            selector.clear()
            selector.addItem("Select a camera...", None)
            for index in sorted(set(indices + (
                [self.selected_camera_index] if self.selected_camera_index is not None else []
            ))):
                label = f"Camera {index}" if index in indices else f"Camera {index} (manual / previous)"
                selector.addItem(label, index)
            selector.setCurrentIndex(max(0, selector.findData(self.selected_camera_index)))
        if self._pending_camera is not None or self._camera_fault or self.static_active:
            return
        if cancelled:
            message = "Camera scan cancelled. Partial results are listed."
        elif indices:
            message = "Scan complete. Select a camera, then choose Webcam."
        else:
            message = "No accessible cameras at indices 0-4. Check permissions or try a manual index."
        if errors:
            message += f"\n{errors}"
        self._source_status(message, error=bool(errors) or (not cancelled and not indices))

    def _acquire_source_frame(self):
        if self.static_active:
            if self.static_source.frame is None:
                raise SourceError("No static input image is available.")
            return self.static_source.frame
        if self.cam:
            return self.camera_worker.snapshot(self.camera_token)
        return normalize_bgr(self.capture_screen_rect())

    def _activate_static_source(self):
        self.camera_worker.use_desktop()
        self._pending_camera = None
        self.camera_token = None
        self.cam = False
        self.static_active = True
        self._camera_fault = False
        self._sync_source_selector()
        frame = self.static_source.frame
        assert frame is not None
        name = self.static_source.path.name if self.static_source.path is not None else "frozen live frame"
        self._source_status(f"Static input: {name} ({frame.shape[1]} x {frame.shape[0]}).")
        self.update_view()

    def _load_input_image(self, path):
        try:
            self.static_source.load(path)
        except (ImageError, SourceError) as error:
            self._source_status(str(error), error=True)
            self._sync_source_selector()
            return False
        with QtCore.QSignalBlocker(self.settings_panel.input_fitting):
            self.settings_panel.input_fitting.setCurrentIndex(0)
        self._activate_static_source()
        return True

    def _choose_input_image(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load static input image", str(example_source_path().parent),
            "Image Files (*.png *.jpg *.jpeg);;All Files (*)",
        )
        if path:
            self._load_input_image(path)
        else:
            self._sync_source_selector()

    def _load_input_example(self):
        self._load_input_image(example_source_path())

    def _freeze_input(self):
        if self._closing:
            return
        if self.static_active:
            self._source_status("Input is already static; select Desktop or Webcam to resume live input.")
            return
        try:
            if self._camera_fault:
                raise SourceError("Cannot freeze a disconnected camera. Retry or select Desktop.")
            frame = self._acquire_source_frame()
            if frame is None:
                raise SourceError("No live input frame is available yet. Try freezing again.")
            self.static_source.set_frame(frame, mirror=self.cam)
        except (SourceError, ScreenShotError, cv2.error) as error:
            self._source_status(f"Cannot freeze input: {error}", error=True)
            return
        with QtCore.QSignalBlocker(self.settings_panel.input_fitting):
            self.settings_panel.input_fitting.setCurrentIndex(1)
        self._activate_static_source()

    def save_input_image(self):
        try:
            if self._camera_fault:
                raise SourceError("Cannot save a disconnected camera's input. Retry or load a static image.")
            frame = self._acquire_source_frame()
            if frame is None:
                raise SourceError("No current input frame is available.")
            frame = frame.copy()
        except (SourceError, ScreenShotError, cv2.error) as error:
            self._source_status(f"Cannot save input: {error}", error=True)
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save native input for calibration", "input.png",
            "PNG Files (*.png);;JPEG Files (*.jpg *.jpeg)",
        )
        if not path:
            return
        output = Path(path)
        if not output.suffix:
            output = output.with_suffix(".png")
        try:
            write_image_bgr(output, frame)
        except ImageError as error:
            self._source_status(str(error), error=True)
            return
        self._source_status(f"Saved native input: {output}")

    def _camera_worker_finished(self):
        if self._closing:
            self.close()

    def _background_status(self, message, *, error=False):
        self.settings_panel.background_status.setText(message)
        if error:
            self.statusBar().showMessage(message)
            print(f"[error] {message}", file=sys.stderr)
            self._last_background_error = message
        elif self._last_background_error is not None:
            if self.statusBar().currentMessage() == self._last_background_error:
                self.statusBar().clearMessage()
            self._last_background_error = None

    def _load_background(self, path):
        try:
            self.background.load(path)
        except ImageError as error:
            self._background_status(str(error), error=True)
            return False
        assert self.background.path is not None
        self._background_status(f"Sky: {self.background.path.name}")
        self.update_view()
        return True

    def _choose_background(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load sky background", "",
            "Image Files (*.png *.jpg *.jpeg);;All Files (*)",
        )
        if path:
            self._load_background(path)

    def _default_background(self):
        self._load_background(default_background_path())

    def _clear_background(self):
        self.background.clear()
        self._background_status("No sky image: black backdrop.")
        self.update_view()

    def _source_placement(self):
        panel = self.settings_panel
        return (
            panel.source_scale.value() / 100,
            panel.source_offset_x.value() / 100,
            panel.source_offset_y.value() / 100,
        )

    def _reset_source_placement(self):
        panel = self.settings_panel
        with (
            QtCore.QSignalBlocker(panel.source_scale),
            QtCore.QSignalBlocker(panel.source_offset_x),
            QtCore.QSignalBlocker(panel.source_offset_y),
        ):
            panel.source_scale.setValue(100)
            panel.source_offset_x.setValue(0)
            panel.source_offset_y.setValue(0)
        self.update_view()

    def _compose_layer(self, rgb, alpha):
        background = self.background.fitted(
            self.base_w, self.base_h, self.settings_panel.background_mode.currentData()
        )
        scale, x, y = self._source_placement()
        return place_layer(rgb, alpha, background, scale=scale, x=x, y=y)

    def _forward_layer(self, img_bgr):
        Lx = 2 * self.base_w / max(self.base_w, self.base_h)
        Ly = 2 * self.base_h / max(self.base_w, self.base_h)
        map_x = self.map_x * 2 / Lx
        map_y = self.map_y * 2 / Ly
        color = cv2.remap(
            img_bgr, map_x, map_y, interpolation=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_CONSTANT,
        )
        if self.background.image is None:
            alpha = np.ones((self.base_h, self.base_w), np.float32)
        else:
            alpha = cv2.remap(
                np.ones(img_bgr.shape[:2], np.float32), map_x, map_y,
                interpolation=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT,
            )
            alpha = np.clip(alpha, 0, 1)
        rgb = cv2.cvtColor(color, cv2.COLOR_BGR2RGB)
        if self.lenslight_checkbox.isChecked():
            rgb = draw_lens_light(
                self.b_value, self.kappa, rgb, base_w=self.base_w, base_h=self.base_h
            )
            if self.b_value > 0:
                light_alpha = np.clip(np.log10(1 + self.kappa), 0, 1)
                alpha = alpha * (1 - light_alpha) + light_alpha
        return rgb, alpha

    def _inverse_layer(self, rgb):
        if self.background.image is None:
            return self.inv_map(rgb), np.ones((self.base_h, self.base_w), np.float32)
        image, alpha = self.inv_map(rgb, return_alpha=True)
        return image * alpha[..., None], alpha

    def update_lensed_map(self):

        self.map_x, self.map_y, self.deflxv, self.deflyv, _, _, self.kappa = (
            create_SIE_map(
                self.base_w,
                self.base_h,
                b=self.b_value / np.sqrt(self.q_value),
                q=self.q_value,
                s=self.s_value * self.b_value,
                t=self.t_value,
                heart=self.heart,
            )
        )

        Lx = 2 * self.base_w / max(self.base_w, self.base_h)
        Ly = 2 * self.base_h / max(self.base_w, self.base_h)

        # Flatten the mapping arrays.
        flat_map_x = self.map_x.flatten() / Lx
        flat_map_y = self.map_y.flatten() / Ly

        # Define bins corresponding to pixel boundaries.
        x_bins = np.arange(self.base_w + 1) - 0.5
        y_bins = np.arange(self.base_h + 1) - 0.5

        x_idx = np.digitize(flat_map_x, bins=x_bins) - 1
        y_idx = np.digitize(flat_map_y, bins=y_bins) - 1

        # Clip indices to stay in bounds
        self.x_idx = np.clip(x_idx, 0, len(x_bins) - 2)
        self.y_idx = np.clip(y_idx, 0, len(y_bins) - 2)

        # Save contours for critical curves
        dx = 2.0 / (self.base_w - 1)
        dy = 2.0 / (self.base_h - 1)
        d_deflx_dx, d_deflx_dy = (
            np.gradient(self.map_x, axis=1) / dx,
            np.gradient(self.map_x, axis=0) / dy,
        )
        d_defly_dx, d_defly_dy = (
            np.gradient(self.map_y, axis=1) / dx,
            np.gradient(self.map_y, axis=0) / dy,
        )
        det = d_deflx_dx * d_defly_dy - d_deflx_dy * d_defly_dx
        crit_mask = np.sign(det) < 0
        self.contours, _ = cv2.findContours(
            crit_mask.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE
        )

        # Save critical curves that go along
        caustic_contours = []
        for cnt in self.contours:

            if len(cnt) < 2:
                continue

            cnt_caustic = cnt.astype(np.float32, copy=False)
            for i in range(len(cnt_caustic)):
                x_idx = cnt_caustic[i, 0, 0]
                y_idx = cnt_caustic[i, 0, 1]
                norm_x_lensed = -Lx / 2 + Lx * x_idx / (self.base_w - 1)
                norm_y_lensed = -Ly / 2 + Ly * y_idx / (self.base_h - 1)
                ix = np.clip(int(round(y_idx)), 0, self.base_h - 1)
                jx = np.clip(int(round(x_idx)), 0, self.base_w - 1)
                source_norm_x = norm_x_lensed - self.deflxv[ix, jx]
                source_norm_y = norm_y_lensed - self.deflyv[ix, jx]
                cnt_caustic[i, 0, 0] = (source_norm_x + Lx / 2) / Lx * (self.base_w - 1)
                cnt_caustic[i, 0, 1] = (source_norm_y + Ly / 2) / Ly * (self.base_h - 1)
            caustic_contours.append(cnt_caustic.astype(np.int32, copy=False))

        self.caustic_curves = caustic_contours

    def dual_view_toggled(self):
        if not self.isMaximized():
            panels = 2 if self.dual_checkbox.isChecked() else 1
            width = self.width() + panels * self.base_w - self.canvas.width()
            self.resize(min(width, self.screen().availableGeometry().width()), self.height())
        self.centralWidget().layout().activate()
        self._update_canvas_geometry()

    # Functions that are called when the sliders are updated
    def update_mask(self, valuem):
        self.mask_radius = (
            (valuem - 40) / (99 - 40) * np.sqrt(self.base_h**2 + self.base_w**2) / 2
        )
        self.update_lensed_map()
        self.inv_map = partial(
            inverse_remap_image,
            x_idx=self.x_idx,
            y_idx=self.y_idx,
            mask_radius=self.mask_radius,
            base_w=self.base_w,
            base_h=self.base_h,
        )

    def update_b_value(self, valueb):
        self.b_value = (valueb - 40) / (99 - 40.0)
        self.update_lensed_map()
        self.inv_map = partial(
            inverse_remap_image,
            x_idx=self.x_idx,
            y_idx=self.y_idx,
            mask_radius=self.mask_radius,
            base_w=self.base_w,
            base_h=self.base_h,
        )

    def update_q_value(self, valueq):
        self.q_value = valueq / 100.0
        self.update_lensed_map()
        self.inv_map = partial(
            inverse_remap_image,
            x_idx=self.x_idx,
            y_idx=self.y_idx,
            mask_radius=self.mask_radius,
            base_w=self.base_w,
            base_h=self.base_h,
        )

    def update_s_value(self, values):
        self.s_value = (values - 40) / (99 - 40.0)
        self.update_lensed_map()
        self.inv_map = partial(
            inverse_remap_image,
            x_idx=self.x_idx,
            y_idx=self.y_idx,
            mask_radius=self.mask_radius,
            base_w=self.base_w,
            base_h=self.base_h,
        )

    def update_t_value(self, valuet):
        self.t_value = (valuet - 40) / (99 - 40.0) * np.pi
        self.update_lensed_map()
        self.inv_map = partial(
            inverse_remap_image,
            x_idx=self.x_idx,
            y_idx=self.y_idx,
            mask_radius=self.mask_radius,
            base_w=self.base_w,
            base_h=self.base_h,
        )

    def easteregg(self):
        self.heart = not self.heart
        self.update_lensed_map()
        self.inv_map = partial(
            inverse_remap_image,
            x_idx=self.x_idx,
            y_idx=self.y_idx,
            mask_radius=self.mask_radius,
            base_w=self.base_w,
            base_h=self.base_h,
        )

    # Functions for critical curves and caustics:

    def get_critical(self, SIE_map_rgb, alpha=None):
        cv2.drawContours(SIE_map_rgb, self.contours, -1, (255, 255, 255), 5)
        cv2.drawContours(SIE_map_rgb, self.contours, -1, (0, 0, 0), 2)
        if alpha is not None:
            cv2.drawContours(alpha, self.contours, -1, 1.0, 5)
        return self.contours

    def get_caustics(self, img_unlensed, contours, alpha=None):

        cv2.drawContours(img_unlensed, self.caustic_curves, -1, (255, 255, 255), 5)
        cv2.drawContours(img_unlensed, self.caustic_curves, -1, (0, 0, 0), 2)
        if alpha is not None:
            cv2.drawContours(alpha, self.caustic_curves, -1, 1.0, 5)

    def save_screenshot(self):
        original_pixmap = self.label.pixmap()
        if not original_pixmap:
            print("No pixmap to save.")
            return

        pixmap = original_pixmap.copy()  # Prevents RuntimeError

        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Screenshot",
            "screenshot.png",
            "PNG Files (*.png);;JPEG Files (*.jpg *.jpeg);;All Files (*)",
        )

        if file_path and not pixmap.save(file_path):
            self._background_status(f"Cannot save image to {file_path}. Check permissions and file format.", error=True)

        gc.collect()

    def recording(self):

        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Screenshot",
            "screenshot.png",
            "PNG Files (*.png);;JPEG Files (*.jpg *.jpeg);;All Files (*)",
        )

        if not file_path:
            return
        path = Path(file_path)
        b0 = self.b_value
        try:
            for i, radius in enumerate(np.linspace(0, b0, 160)):
                self.b_value = float(radius)
                self.update_mask(self.slider_mask.value())
                if not self.update_view():
                    self._background_status("Sequence export stopped: no current input image available.", error=True)
                    break
                pixmap = self.label.pixmap().copy()
                output = path.with_name(f"{path.stem}_{i:04d}{path.suffix}")
                if not pixmap.save(str(output)):
                    self._background_status(f"Cannot save sequence image to {output}.", error=True)
                    break
        finally:
            self.b_value = b0
            self.update_mask(self.slider_mask.value())
            self.update_view()

        gc.collect()

    def showEvent(self, event):
        super().showEvent(event)

    def update_view(self):

        if not self._ready:
            return False
        gc.collect()
        self.set_Geometry_sliders_and_labels()
        if self._camera_fault or self._closing:
            return False
        try:
            frame = self._acquire_source_frame()
            if frame is None:
                return False
            if self.static_active:
                frame = self.static_source.render_frame(
                    self.base_w, self.base_h, self.settings_panel.input_fitting.currentData()
                )
            else:
                frame = frame_for_canvas(frame, self.base_w, self.base_h, camera=self.cam)
        except (SourceError, ImageError, cv2.error, ScreenShotError) as error:
            self._source_status(f"Cannot capture the input image: {error}", error=True)
            return False

        # If inverse lensing is selected, do that; otherwise, use single or dual view.
        if self.inverse_checkbox.isChecked():
            if self.dual_checkbox.isChecked():
                self.update_inverse_dual_view(frame)
            else:
                self.update_inverse_single_view(frame)
        else:
            if self.dual_checkbox.isChecked():
                self.update_dual_view(frame)
            else:
                self.update_single_view(frame)
        return True

    # Forward Updates

    def show_ps(self, img_bgr):
        if len(self.ellipses_image_plane) > 0 or len(self.ellipses_source_plane) > 0:

            if len(self.ellipses_image_plane) > 0:
                x0 = self.ellipses_image_plane[0][0]
                y0 = self.ellipses_image_plane[0][1]

                x_source = int(
                    interp(
                        (np.arange(self.base_w), np.arange(self.base_h)),
                        self.map_x.T,
                        method="linear",
                        bounds_error=False,
                        fill_value=None,
                    )(np.array([[x0, y0]]))[0]
                )
                y_source = int(
                    interp(
                        (np.arange(self.base_w), np.arange(self.base_h)),
                        self.map_y.T,
                        method="linear",
                        bounds_error=False,
                        fill_value=None,
                    )(np.array([[x0, y0]]))[0]
                )

            if len(self.ellipses_source_plane) > 0:
                x_source = int(2 * (self.ellipses_source_plane[0][0]))
                y_source = int(2 * (self.ellipses_source_plane[0][1]))

            for c in range(3):
                cc = np.zeros((3,))
                cc[c] = 255
                color = (int(cc[0]), int(cc[1]), int(cc[2]))
                cv2.ellipse(
                    img_bgr,
                    (x_source, y_source),  # center
                    (ps, ps),  # axes
                    0,  # angle
                    0 + c * 120,  # startAngle
                    120 + c * 120,  # endAngle
                    color,  # color
                    -1,  # thickness
                )

    def update_single_view(self, img_bgr):

        self.show_ps(img_bgr)

        SIE_map_rgb, alpha = self._forward_layer(img_bgr)

        # Optionally overlay critical curve.
        if self.critical_checkbox.isChecked():
            self.get_critical(SIE_map_rgb, alpha)
        SIE_map_rgb = self._compose_layer(SIE_map_rgb, alpha)

        result_image = QtGui.QImage(
            SIE_map_rgb.data,
            self.base_w,
            self.base_h,
            self.base_w * 3,
            QtGui.QImage.Format_RGB888,
        )
        result_pixmap = QtGui.QPixmap.fromImage(result_image)

        self.label.setPixmap(result_pixmap)

    def update_dual_view(self, img_bgr):

        self.show_ps(img_bgr)

        img_unlensed = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

        if img_unlensed.shape[0] != self.base_h or img_unlensed.shape[1] != self.base_w:

            img_unlensed = cv2.resize(img_unlensed, (self.base_w, self.base_h))

        SIE_map_rgb, alpha = self._forward_layer(img_bgr)

        if self.critical_checkbox.isChecked():
            contours = self.get_critical(SIE_map_rgb, alpha)
            self.get_caustics(img_unlensed, contours)

        img_unlensed = self._compose_layer(img_unlensed, np.ones((self.base_h, self.base_w), np.float32))
        SIE_map_rgb = self._compose_layer(SIE_map_rgb, alpha)
        # Combine views.
        combined = np.hstack((img_unlensed, SIE_map_rgb))
        result_image = QtGui.QImage(
            combined.data,
            2 * self.base_w,
            self.base_h,
            2 * self.base_w * 3,
            QtGui.QImage.Format_RGB888,
        )
        result_pixmap = QtGui.QPixmap.fromImage(result_image)
        self.label.setPixmap(result_pixmap)

    # Inverse Updates
    def inverse_ps_show(self, img_bgr):
        if len(self.ellipses_image_plane) > 0 or len(self.ellipses_source_plane) > 0:

            if len(self.ellipses_source_plane) > 0:

                if (
                    self.base_h == self.base_w
                ):  # Right now only supported for the equal dimensions case

                    id = np.array(
                        np.where(
                            (
                                self.x_idx.reshape((self.base_w, self.base_h))
                                - self.ellipses_source_plane[0][0]
                            )
                            ** 2
                            + (
                                self.y_idx.reshape((self.base_w, self.base_h))
                                - self.ellipses_source_plane[0][1]
                            )
                            ** 2
                            < 1.0
                        )
                    )

                    id = reduce_points(id.T, ps * 2).T

                    if len(id) > 0:
                        for i in range(len(id[0])):
                            x0, y0 = id[1][i], id[0][i]

                            for c in range(3):
                                cc = np.zeros((3,))
                                cc[c] = 255
                                color = (int(cc[0]), int(cc[1]), int(cc[2]))
                                cv2.ellipse(
                                    img_bgr,
                                    (int(x0), int(y0)),  # center
                                    (ps // 2, ps // 2),  # axes
                                    0,  # angle
                                    0 + c * 120,  # startAngle
                                    120 + c * 120,  # endAngle
                                    color,  # color
                                    -1,  # thickness
                                )

            if len(self.ellipses_image_plane) > 0:
                x0 = self.ellipses_image_plane[0][0]
                y0 = self.ellipses_image_plane[0][1]

                for c in range(3):
                    cc = np.zeros((3,))
                    cc[c] = 255
                    color = (int(cc[0]), int(cc[1]), int(cc[2]))
                    cv2.ellipse(
                        img_bgr,
                        (int(x0), int(y0)),  # center
                        (ps // 2, ps // 2),  # axes
                        0,  # angle
                        0 + c * 120,  # startAngle
                        120 + c * 120,  # endAngle
                        color,  # color
                        -1,  # thickness
                    )

    def update_inverse_single_view(self, frame):
        """
        When inverse lensing is enabled, we capture the image, perform the forward mapping as before,
        and then use our inverse_remap_image() routine to “undo” the lensing.
        """

        img_bgr = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        if img_bgr.shape[0] != self.base_h or img_bgr.shape[1] != self.base_w:
            img_bgr = cv2.resize(img_bgr, (self.base_w, self.base_h))

        self.inverse_ps_show(img_bgr)

        # Now, perform the inverse remapping to (attempt to) recover the original.
        inv_img, alpha = self._inverse_layer(img_bgr)

        if self.critical_checkbox.isChecked():
            contours = self.get_critical(img_bgr)
            self.get_caustics(inv_img, contours, alpha)
        inv_img = self._compose_layer(inv_img, alpha)

        result_image = QtGui.QImage(
            inv_img.data,
            self.base_w,
            self.base_h,
            self.base_w * 3,
            QtGui.QImage.Format_RGB888,
        )
        result_pixmap = QtGui.QPixmap.fromImage(result_image)
        self.label.setPixmap(result_pixmap)

    def update_inverse_dual_view(self, frame):
        """
        When inverse lensing is enabled, we capture the image, perform the forward mapping as before,
        and then use our inverse_remap_image() routine to “undo” the lensing.
        """

        img_bgr = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        if img_bgr.shape[0] != self.base_h or img_bgr.shape[1] != self.base_w:
            img_bgr = cv2.resize(img_bgr, (self.base_w, self.base_h))

        self.inverse_ps_show(img_bgr)

        xx, yy = np.meshgrid(np.arange(self.base_w), np.arange(self.base_h))
        r2 = (yy - self.base_h // 2) ** 2 + (
            xx - self.base_w // 2
        ) ** 2 > self.mask_radius**2
        img_bgr[r2 == False] = img_bgr.mean()

        # Now, perform the inverse remapping to (attempt to) recover the original.
        inv_img, alpha = self._inverse_layer(img_bgr)

        if self.critical_checkbox.isChecked():
            contours = self.get_critical(img_bgr)
            self.get_caustics(inv_img, contours, alpha)

        img_bgr = self._compose_layer(img_bgr, np.ones((self.base_h, self.base_w), np.float32))
        inv_img = self._compose_layer(inv_img, alpha)
        # Combine views.
        combined = np.hstack((img_bgr, inv_img))
        result_image = QtGui.QImage(
            combined.data,
            2 * self.base_w,
            self.base_h,
            2 * self.base_w * 3,
            QtGui.QImage.Format_RGB888,
        )
        result_pixmap = QtGui.QPixmap.fromImage(result_image)
        self.label.setPixmap(result_pixmap)

    def _canvas_mouse_press(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.old_pos = event.globalPos()

        if event.button() == QtCore.Qt.RightButton:
            # I thank Christopher Pattison and Sergi Sirera Lahoz for this nice idea!

            if (
                len(self.ellipses_image_plane) > 0
                or len(self.ellipses_source_plane) > 0
            ):
                self.ellipses_image_plane = []
                self.ellipses_source_plane = []
                gc.collect()
            else:

                ex, ey = event.x(), event.y()
                right_panel = self.dual_checkbox.isChecked() and ex >= self.base_w
                scale, offset_x, offset_y = self._source_placement()
                point = unplace_point(
                    ex - (self.base_w if right_panel else 0), ey,
                    self.base_w, self.base_h, scale, offset_x, offset_y,
                )
                if point is None:
                    return
                ex, ey = point
                if right_panel:
                    ex += self.base_w

                if self.inverse_checkbox.isChecked():
                    if self.dual_checkbox.isChecked():
                        # check for left and right side add accordingly
                        if ex >= self.base_w:
                            self.ellipses_source_plane += [
                                (
                                    (ex - self.base_w),
                                    ey,
                                )
                            ]
                        else:
                            self.ellipses_image_plane += [
                                (
                                    ex,
                                    ey,
                                )
                            ]
                    else:
                        self.ellipses_source_plane += [
                            (
                                ex,
                                ey,
                            )
                        ]

                else:
                    if self.dual_checkbox.isChecked():
                        if ex >= self.base_w:
                            self.ellipses_image_plane += [
                                (
                                    (ex - self.base_w),
                                    ey,
                                )
                            ]
                        else:
                            self.ellipses_source_plane += [
                                (
                                    ex,
                                    ey,
                                )
                            ]
                    else:
                        self.ellipses_image_plane += [
                            (
                                ex,
                                ey,
                            )
                        ]

                self.update_lensed_map()

    def _canvas_mouse_move(self, event):

        if self.old_pos is not None:
            delta = event.globalPos() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPos()

    def closeEvent(self, event):
        self._closing = True
        self.timer.stop()
        self.camera_worker.shutdown()
        if self.camera_worker.isRunning():
            event.ignore()
            self.settings_panel.setEnabled(False)
            self._source_status("Closing... Waiting for the camera driver to release its devices.")
            return
        self._ready = False
        self.sct.close()
        event.accept()
        QtWidgets.QApplication.instance().quit()


def main():
    app = QtWidgets.QApplication(sys.argv)
    lens_desktop = LensDesktop()
    lens_desktop.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
