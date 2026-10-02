CANDIDATES = ("PySide6", "PyQt6", "PyQt5", "PySide2")


def _load_qt():
    for name in CANDIDATES:
        try:
            if name == "PySide6":
                from PySide6 import QtWidgets, QtCore, QtGui
            elif name == "PyQt6":
                from PyQt6 import QtWidgets, QtCore, QtGui
            elif name == "PyQt5":
                from PyQt5 import QtWidgets, QtCore, QtGui
            else:
                from PySide2 import QtWidgets, QtCore, QtGui
            return name, QtWidgets, QtCore, QtGui
        except ModuleNotFoundError:
            continue
    raise ImportError("No Qt binding found. Install PyQt5/PyQt6/PySide6/PySide2.")


QT_PKG, QtWidgets, QtCore, QtGui = _load_qt()
