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
