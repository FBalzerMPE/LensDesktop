from .qt_compat import QtCore, QtWidgets


class SettingsPanel(QtWidgets.QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        content = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        source_group = QtWidgets.QGroupBox("Source")
        source_layout = QtWidgets.QVBoxLayout(source_group)
        self.source_selector = QtWidgets.QComboBox()
        self.source_selector.addItem("Desktop", "desktop")
        self.source_selector.addItem("Webcam", "webcam")
        self.source_selector.addItem("Static image", "static")
        self.source_selector.setAccessibleName("Input source")
        source_layout.addWidget(self.source_selector)
        self.camera_selector = QtWidgets.QComboBox()
        self.camera_selector.addItem("Select a camera...", None)
        self.camera_selector.setAccessibleName("Camera")
        source_layout.addWidget(self.camera_selector)
        discovery_row = QtWidgets.QHBoxLayout()
        self.refresh_cameras = QtWidgets.QPushButton("Refresh")
        self.refresh_cameras.setToolTip("Probe camera indices 0 to 4.")
        self.cancel_refresh = QtWidgets.QPushButton("Cancel")
        self.cancel_refresh.setEnabled(False)
        discovery_row.addWidget(self.refresh_cameras)
        discovery_row.addWidget(self.cancel_refresh)
        source_layout.addLayout(discovery_row)
        index_row = QtWidgets.QHBoxLayout()
        index_label = QtWidgets.QLabel("Camera index")
        self.camera_index = QtWidgets.QSpinBox()
        self.camera_index.setRange(0, 99)
        index_label.setBuddy(self.camera_index)
        self.camera_index.setAccessibleName("Manual camera index")
        index_row.addWidget(index_label)
        index_row.addWidget(self.camera_index)
        source_layout.addLayout(index_row)
        self.open_camera = QtWidgets.QPushButton("Use index / retry")
        source_layout.addWidget(self.open_camera)
        static_buttons = QtWidgets.QHBoxLayout()
        self.load_input_image = QtWidgets.QPushButton("Load image...")
        self.load_input_example = QtWidgets.QPushButton("Hand example")
        static_buttons.addWidget(self.load_input_image)
        static_buttons.addWidget(self.load_input_example)
        source_layout.addLayout(static_buttons)
        capture_buttons = QtWidgets.QHBoxLayout()
        self.freeze_input = QtWidgets.QPushButton("Freeze input")
        self.save_input = QtWidgets.QPushButton("Save input...")
        self.freeze_input.setToolTip("Freeze the native live frame; rendering settings remain adjustable.")
        self.save_input.setToolTip("Save native input before crop, mirroring, lensing, sky, or overlays.")
        capture_buttons.addWidget(self.freeze_input)
        capture_buttons.addWidget(self.save_input)
        source_layout.addLayout(capture_buttons)
        self.input_fitting = QtWidgets.QComboBox()
        self.input_fitting.addItem("Static fit (whole image)", "fit")
        self.input_fitting.addItem("Static fill (center crop)", "fill")
        self.input_fitting.setAccessibleName("Static input framing")
        self.input_fitting.setEnabled(False)
        source_layout.addWidget(self.input_fitting)
        self.source_status = QtWidgets.QLabel("Desktop capture")
        self.source_status.setWordWrap(True)
        self.source_status.setTextFormat(QtCore.Qt.PlainText)
        self.source_status.setMinimumWidth(0)
        self.source_status.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred
        )
        source_layout.addWidget(self.source_status)
        layout.addWidget(source_group)

        background_group = QtWidgets.QGroupBox("Sky background")
        background_layout = QtWidgets.QVBoxLayout(background_group)
        background_buttons = QtWidgets.QHBoxLayout()
        self.load_background = QtWidgets.QPushButton("Load...")
        self.clear_background = QtWidgets.QPushButton("Clear")
        self.default_background = QtWidgets.QPushButton("Default")
        for button in (self.load_background, self.clear_background, self.default_background):
            background_buttons.addWidget(button)
        background_layout.addLayout(background_buttons)
        self.background_mode = QtWidgets.QComboBox()
        self.background_mode.addItem("Fill (center crop)", "fill")
        self.background_mode.addItem("Fit (black margins)", "fit")
        self.background_mode.setAccessibleName("Sky image fitting")
        background_layout.addWidget(self.background_mode)
        self.background_status = QtWidgets.QLabel()
        self.background_status.setWordWrap(True)
        self.background_status.setTextFormat(QtCore.Qt.PlainText)
        self.background_status.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred
        )
        background_layout.addWidget(self.background_status)
        placement = QtWidgets.QFormLayout()
        for name, title, minimum, maximum, value in (
            ("source_scale", "Source size", 10, 200, 100),
            ("source_offset_x", "Horizontal offset", -100, 100, 0),
            ("source_offset_y", "Vertical offset", -100, 100, 0),
        ):
            control = QtWidgets.QSpinBox()
            control.setRange(minimum, maximum)
            control.setValue(value)
            control.setSingleStep(5)
            control.setSuffix(" %")
            control.setAccessibleName(title)
            control.setToolTip("Applied after lensing, relative to each image panel.")
            setattr(self, name, control)
            placement.addRow(title, control)
        background_layout.addLayout(placement)
        self.reset_placement = QtWidgets.QPushButton("Reset source placement")
        background_layout.addWidget(self.reset_placement)
        layout.addWidget(background_group)

        view_group = QtWidgets.QGroupBox("View")
        view_layout = QtWidgets.QVBoxLayout(view_group)
        view_layout.setSpacing(8)
        self.critical_checkbox = QtWidgets.QCheckBox("Critical Curve")
        self.dual_checkbox = QtWidgets.QCheckBox("Dual view")
        self.inverse_checkbox = QtWidgets.QCheckBox("De-lensing")
        self.lenslight_checkbox = QtWidgets.QCheckBox("Lens Light")
        for checkbox in (
            self.critical_checkbox,
            self.dual_checkbox,
            self.inverse_checkbox,
            self.lenslight_checkbox,
        ):
            view_layout.addWidget(checkbox)
        layout.addWidget(view_group)

        lens_group = QtWidgets.QGroupBox("Lens")
        lens_layout = QtWidgets.QVBoxLayout(lens_group)
        lens_layout.setSpacing(12)
        for slider_name, label_name, title, value in (
            ("sliderb", "labelb", "Einstein Radius", 65),
            ("sliderq", "labelq", "Axis Ratio", 65),
            ("sliders", "labels", "Core Radius", 41),
            ("slidert", "labelt", "Position Angle", 95),
            ("slider_mask", "label_mask", "Mask Radius", 40),
        ):
            row = QtWidgets.QWidget()
            row_layout = QtWidgets.QVBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)
            label = QtWidgets.QLabel(title)
            slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            slider.setRange(40, 99)
            slider.setValue(value)
            slider.setAccessibleName(title)
            label.setBuddy(slider)
            row_layout.addWidget(label)
            row_layout.addWidget(slider)
            lens_layout.addWidget(row)
            setattr(self, slider_name, slider)
            setattr(self, label_name, label)
            if slider_name == "slider_mask":
                self.mask_controls = row
        self.set_inverse_mode(False)
        layout.addWidget(lens_group)

        hint = QtWidgets.QLabel("Ctrl+V: hide/show controls")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()
        self.setWidget(content)
        scrollbar_width = self.style().pixelMetric(
            QtWidgets.QStyle.PM_ScrollBarExtent
        )
        self.setFixedWidth(max(240, content.sizeHint().width() + scrollbar_width))

    def set_inverse_mode(self, enabled):
        self.mask_controls.setVisible(enabled)
