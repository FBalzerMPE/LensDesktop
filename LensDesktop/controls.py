from .qt_compat import QtCore, QtGui, QtWidgets
from .processing import ChromaKeySettings


class CollapsibleSection(QtWidgets.QWidget):
    def __init__(self, title, *, expanded=False, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.header = QtWidgets.QToolButton()
        self.header.setObjectName("sectionHeader")
        self.header.setText(title)
        self.header.setAccessibleName(title)
        self.header.setCheckable(True)
        self.header.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.header.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.body = QtWidgets.QFrame()
        self.body.setObjectName("sectionBody")
        self.body_layout = QtWidgets.QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(12, 10, 12, 10)
        self.body_layout.setSpacing(8)
        layout.addWidget(self.header)
        layout.addWidget(self.body)
        self.header.toggled.connect(self.set_expanded)
        self.set_expanded(expanded)

    def set_expanded(self, expanded):
        with QtCore.QSignalBlocker(self.header):
            self.header.setChecked(expanded)
        self.header.setArrowType(QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow)
        self.body.setVisible(expanded)


class SettingsPanel(QtWidgets.QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setObjectName("settingsPanel")

        content = QtWidgets.QWidget()
        content.setObjectName("settingsContent")
        layout = QtWidgets.QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.source_section = CollapsibleSection("Source", expanded=True)
        source_layout = self.source_section.body_layout
        self.source_selector = QtWidgets.QComboBox()
        self.source_selector.addItem("Desktop", "desktop")
        self.source_selector.addItem("Webcam", "webcam")
        self.source_selector.addItem("Static image", "static")
        self.source_selector.setAccessibleName("Input source")
        source_layout.addWidget(self.source_selector)
        self.camera_selector = QtWidgets.QComboBox()
        self.camera_selector.addItem("Select a camera...", None)
        self.camera_selector.setAccessibleName("Camera")
        self.camera_section = CollapsibleSection("Camera setup")
        camera_layout = self.camera_section.body_layout
        camera_layout.addWidget(self.camera_selector)
        discovery_row = QtWidgets.QHBoxLayout()
        self.refresh_cameras = QtWidgets.QPushButton("Refresh")
        self.refresh_cameras.setToolTip("Probe camera indices 0 to 4.")
        self.cancel_refresh = QtWidgets.QPushButton("Cancel")
        self.cancel_refresh.setEnabled(False)
        discovery_row.addWidget(self.refresh_cameras)
        discovery_row.addWidget(self.cancel_refresh)
        camera_layout.addLayout(discovery_row)
        index_row = QtWidgets.QHBoxLayout()
        index_label = QtWidgets.QLabel("Camera index")
        self.camera_index = QtWidgets.QSpinBox()
        self.camera_index.setRange(0, 99)
        index_label.setBuddy(self.camera_index)
        self.camera_index.setAccessibleName("Manual camera index")
        index_row.addWidget(index_label)
        index_row.addWidget(self.camera_index)
        camera_layout.addLayout(index_row)
        self.open_camera = QtWidgets.QPushButton("Use index / retry")
        camera_layout.addWidget(self.open_camera)
        source_layout.addWidget(self.camera_section)
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
        layout.addWidget(self.source_section)

        self.input_section = CollapsibleSection("Input / greenscreen")
        input_layout = self.input_section.body_layout
        self.key_enabled = QtWidgets.QCheckBox("Remove greenscreen")
        input_layout.addWidget(self.key_enabled)
        defaults = ChromaKeySettings()
        self.key_color_rgb = defaults.color
        self.key_color = QtWidgets.QPushButton()
        self.update_key_color_label()
        input_layout.addWidget(self.key_color)
        key_form = QtWidgets.QFormLayout()
        for name, title, maximum, value, suffix, tooltip in (
            ("key_tolerance", "Hue tolerance", 180, defaults.tolerance, " deg",
             "Hue distance from the key color that becomes fully transparent."),
            ("key_softness", "Edge softness", 90, defaults.softness, " deg",
             "Additional hue range blended from transparent to opaque."),
            ("key_saturation", "Minimum saturation", 100, defaults.saturation * 100, " %",
             "Protect low-saturation skin, gray and black from removal."),
            ("key_spill", "Spill suppression", 100, defaults.spill * 100, " %",
             "Reduce excess key-color channel near the selected hue."),
        ):
            control = QtWidgets.QSpinBox()
            control.setRange(0, maximum)
            control.setValue(int(value))
            control.setSuffix(suffix)
            control.setAccessibleName(title)
            control.setToolTip(tooltip)
            setattr(self, name, control)
            key_form.addRow(title, control)
        input_layout.addLayout(key_form)
        self.key_enabled.toggled.connect(self.set_key_controls_enabled)
        self.set_key_controls_enabled(False)
        framing_form = QtWidgets.QFormLayout()
        self.input_frame_mode = QtWidgets.QComboBox()
        for text, data in (
            ("Source default", "default"), ("Fit (whole image)", "fit"), ("Fill (center crop)", "fill")
        ):
            self.input_frame_mode.addItem(text, data)
        self.input_mirror = QtWidgets.QComboBox()
        for text, data in (("Source default", "default"), ("Unmirrored", "off"), ("Mirrored", "on")):
            self.input_mirror.addItem(text, data)
        self.input_preview = QtWidgets.QComboBox()
        for text, data in (("Composed scene", "scene"), ("Original source", "source"), ("Alpha mask", "mask")):
            self.input_preview.addItem(text, data)
        self.input_preview.setToolTip("Mask: white is retained, black is removed. Previews bypass lensing and placement.")
        for title, control in (
            ("Input framing", self.input_frame_mode),
            ("Mirror", self.input_mirror),
            ("Preview", self.input_preview),
        ):
            control.setAccessibleName(title)
            framing_form.addRow(title, control)
        self.input_zoom = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.input_zoom.setRange(100, 400)
        self.input_zoom.setValue(100)
        self.input_zoom.setSingleStep(5)
        self.input_zoom.setPageStep(25)
        self.input_zoom.setTracking(False)
        self.input_zoom.setAccessibleName("Input zoom")
        self.input_zoom.setToolTip(
            "Center crop before lensing: 100% keeps the whole input; 200% keeps half of each axis. Applied on release."
        )
        zoom_row, self.input_zoom_value = self._percentage_row(self.input_zoom)
        framing_form.addRow("Input zoom", zoom_row)
        input_layout.addLayout(framing_form)
        self.reset_input = QtWidgets.QPushButton("Reset input settings")
        input_layout.addWidget(self.reset_input)
        layout.addWidget(self.input_section)

        self.configuration_section = CollapsibleSection("Source relative to lens")
        configuration_layout = self.configuration_section.body_layout
        self.configuration_enabled = QtWidgets.QCheckBox("Place input before lensing")
        configuration_layout.addWidget(self.configuration_enabled)
        size_form = QtWidgets.QFormLayout()
        self.configuration_size = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.configuration_size.setRange(1, 100)
        self.configuration_size.setValue(10)
        self.configuration_size.setTracking(False)
        self.configuration_size.setAccessibleName("Pre-lens input size")
        self.configuration_size.setToolTip(
            "Longest visible source extent as a percentage of the Einstein radius. "
            "Transparent margins are trimmed and the subject is centered before placement."
        )
        size_row, self.configuration_size_value = self._percentage_row(self.configuration_size)
        size_form.addRow("Input size", size_row)
        configuration_layout.addLayout(size_form)
        presets = QtWidgets.QHBoxLayout()
        self.configuration_group = QtWidgets.QButtonGroup(self)
        self.configuration_buttons = {}
        for index, (name, title) in enumerate((("cross", "Cross"), ("cusp", "Cusp"), ("fold", "Fold"))):
            button = QtWidgets.QRadioButton(title)
            self.configuration_group.addButton(button, index)
            self.configuration_buttons[name] = button
            presets.addWidget(button)
        self.configuration_buttons["cross"].setChecked(True)
        configuration_layout.addLayout(presets)
        self.configuration_status = QtWidgets.QLabel(
            "Off: original input framing. Source placement below changes only the rendered result."
        )
        self.configuration_status.setWordWrap(True)
        self.configuration_status.setTextFormat(QtCore.Qt.PlainText)
        self.configuration_status.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred,
        )
        configuration_layout.addWidget(self.configuration_status)
        self.reset_configuration = QtWidgets.QPushButton("Reset pre-lens setup")
        configuration_layout.addWidget(self.reset_configuration)
        self.set_configuration_controls_enabled(False)
        layout.addWidget(self.configuration_section)

        self.background_section = CollapsibleSection("Sky background")
        background_layout = self.background_section.body_layout
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
        layout.addWidget(self.background_section)
        self.placement_section = CollapsibleSection("Source placement", expanded=True)
        placement_layout = self.placement_section.body_layout
        placement = QtWidgets.QFormLayout()
        self.source_scale = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.source_scale.setRange(10, 200)
        self.source_scale.setValue(25)
        self.source_scale.setSingleStep(5)
        self.source_scale.setPageStep(25)
        self.source_scale.setAccessibleName("Source size")
        self.source_scale.setToolTip("Size of the rendered source after lensing, relative to each image panel.")
        scale_row, self.source_scale_value = self._percentage_row(self.source_scale)
        placement.addRow("Source size", scale_row)
        for name, title, minimum, maximum, value in (
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
        placement_layout.addLayout(placement)
        self.reset_placement = QtWidgets.QPushButton("Reset source placement")
        placement_layout.addWidget(self.reset_placement)
        layout.addWidget(self.placement_section)

        self.view_section = CollapsibleSection("View", expanded=True)
        view_layout = QtWidgets.QGridLayout()
        view_layout.setSpacing(8)
        self.critical_checkbox = QtWidgets.QCheckBox("Critical Curve")
        self.dual_checkbox = QtWidgets.QCheckBox("Dual view")
        self.inverse_checkbox = QtWidgets.QCheckBox("De-lensing")
        self.lenslight_checkbox = QtWidgets.QCheckBox("Lens Light")
        for index, checkbox in enumerate((
            self.critical_checkbox,
            self.dual_checkbox,
            self.inverse_checkbox,
            self.lenslight_checkbox,
        )):
            view_layout.addWidget(checkbox, index // 2, index % 2)
        self.view_section.body_layout.addLayout(view_layout)
        layout.addWidget(self.view_section)

        self.lens_section = CollapsibleSection("Lens")
        lens_layout = self.lens_section.body_layout
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
        layout.addWidget(self.lens_section)

        hint = QtWidgets.QLabel("Ctrl+V: hide/show controls")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()
        self.sections = (
            self.source_section, self.input_section, self.background_section,
            self.configuration_section, self.placement_section, self.view_section, self.lens_section,
        )
        self.setWidget(content)
        self._apply_style()
        self.ensurePolished()
        scrollbar_width = self.style().pixelMetric(
            QtWidgets.QStyle.PM_ScrollBarExtent
        )
        body_width = max(section.body.sizeHint().width() for section in self.sections)
        self.setFixedWidth(max(320, body_width + 24 + scrollbar_width))

    @staticmethod
    def _percentage_row(slider):
        row = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        readout = QtWidgets.QLabel(f"{slider.value()}%")
        readout.setObjectName("percentageReadout")
        readout.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        readout.setMinimumWidth(44)
        slider.valueChanged.connect(lambda value: readout.setText(f"{value}%"))
        slider.sliderMoved.connect(lambda value: readout.setText(f"{value}%"))
        layout.addWidget(slider, 1)
        layout.addWidget(readout)
        return row, readout

    def update_percentage_labels(self):
        self.source_scale_value.setText(f"{self.source_scale.value()}%")
        self.input_zoom_value.setText(f"{self.input_zoom.value()}%")
        self.configuration_size_value.setText(f"{self.configuration_size.value()}%")

    def selected_configuration(self):
        return next(name for name, button in self.configuration_buttons.items() if button.isChecked())

    def set_configuration_controls_enabled(self, enabled):
        self.configuration_size.setEnabled(enabled)
        for button in self.configuration_buttons.values():
            button.setEnabled(enabled)

    def _apply_style(self):
        palette = self.palette()
        window = palette.color(QtGui.QPalette.Window).name()
        base = palette.color(QtGui.QPalette.Base).name()
        text = palette.color(QtGui.QPalette.Text).name()
        border = palette.color(QtGui.QPalette.Mid).name()
        disabled = palette.color(QtGui.QPalette.Disabled, QtGui.QPalette.Text).name()
        accent = "#237679" if palette.color(QtGui.QPalette.Window).lightness() > 128 else "#64c2c4"
        self.setStyleSheet(f"""
            QScrollArea#settingsPanel, QWidget#settingsContent {{ background: {window}; }}
            QFrame#sectionBody {{ background: {base}; border: 1px solid {border}; border-radius: 8px; }}
            QToolButton#sectionHeader {{
                color: {text}; background: transparent; border: 1px solid transparent; border-radius: 6px;
                padding: 8px; text-align: left; font-weight: 600;
            }}
            QToolButton#sectionHeader:hover, QToolButton#sectionHeader:checked {{
                background: rgba(49, 143, 145, 25);
            }}
            QToolButton#sectionHeader:focus {{ border-color: {accent}; }}
            QPushButton, QComboBox, QSpinBox {{
                color: {text}; border: 1px solid {border}; border-radius: 5px; padding: 4px 6px;
            }}
            QComboBox, QSpinBox {{ background: {base}; }}
            QPushButton:hover {{ border-color: {accent}; }}
            QPushButton:disabled, QComboBox:disabled, QSpinBox:disabled {{ color: {disabled}; }}
            QPushButton:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {accent}; }}
            QLabel#percentageReadout {{ color: {accent}; }}
            QSlider {{ border: 1px solid transparent; }}
            QSlider::groove:horizontal {{ height: 5px; background: {border}; border-radius: 2px; }}
            QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 2px; }}
            QSlider::handle:horizontal {{
                width: 14px; margin: -5px 0; background: {accent}; border-radius: 7px;
            }}
            QSlider:focus {{ border-color: {accent}; background: rgba(49, 143, 145, 15); }}
            QScrollBar:vertical {{ width: 10px; background: {window}; }}
            QScrollBar::handle:vertical {{ background: {border}; min-height: 24px; border-radius: 5px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        """)

    def chroma_settings(self):
        return ChromaKeySettings(
            enabled=self.key_enabled.isChecked(), color=self.key_color_rgb,
            tolerance=self.key_tolerance.value(), softness=self.key_softness.value(),
            saturation=self.key_saturation.value() / 100, spill=self.key_spill.value() / 100,
        )

    def update_key_color_label(self):
        self.key_color.setText("Key color: #{:02x}{:02x}{:02x}...".format(*self.key_color_rgb))

    def set_key_controls_enabled(self, enabled):
        for control in (
            self.key_color, self.key_tolerance, self.key_softness,
            self.key_saturation, self.key_spill,
        ):
            control.setEnabled(enabled)

    def set_inverse_mode(self, enabled):
        self.mask_controls.setVisible(enabled)
