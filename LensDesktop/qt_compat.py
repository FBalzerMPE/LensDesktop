CANDIDATES = ("PySide6", "PyQt6", "PyQt5", "PySide2")


def _load_qt():
    for name in CANDIDATES:
        try:
            if name == "PySide6":
                from PySide6 import QtWidgets, QtCore, QtGui, QtPrintSupport
            elif name == "PyQt6":
                from PyQt6 import QtWidgets, QtCore, QtGui, QtPrintSupport
            elif name == "PyQt5":
                from PyQt5 import QtWidgets, QtCore, QtGui, QtPrintSupport
            else:
                from PySide2 import QtWidgets, QtCore, QtGui, QtPrintSupport
            return name, QtWidgets, QtCore, QtGui, QtPrintSupport
        except ModuleNotFoundError:
            continue
    raise ImportError("No Qt binding found. Install PyQt5/PyQt6/PySide6/PySide2.")


QT_PKG, QtWidgets, QtCore, QtGui, QtPrintSupport = _load_qt()
