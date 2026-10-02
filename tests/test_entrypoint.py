import runpy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from LensDesktop import app as desktop
from LensDesktop import controls, qt_compat


class PackageEntrypointTests(unittest.TestCase):
    def test_modules_share_the_same_qt_binding(self):
        self.assertIs(desktop.QtWidgets, controls.QtWidgets)
        self.assertIs(desktop.QtWidgets, qt_compat.QtWidgets)
        self.assertIs(desktop.SettingsPanel, controls.SettingsPanel)

    def test_main_creates_shows_and_runs_application(self):
        with (
            patch.object(desktop.QtWidgets, "QApplication") as application,
            patch.object(desktop, "LensDesktop") as window,
        ):
            application.return_value.exec_.return_value = 7
            self.assertEqual(desktop.main(), 7)
            application.assert_called_once_with(sys.argv)
            window.assert_called_once_with()
            window.return_value.show.assert_called_once_with()
            application.return_value.exec_.assert_called_once_with()

    def test_package_launcher_propagates_exit_status(self):
        with patch.object(desktop, "main", return_value=7) as main:
            with self.assertRaises(SystemExit) as result:
                runpy.run_module("LensDesktop", run_name="__main__")
            self.assertEqual(result.exception.code, 7)
            main.assert_called_once_with()

    def test_pyinstaller_script_launcher_uses_package_imports(self):
        launcher = Path(desktop.__file__).with_name("__main__.py")
        with patch.object(desktop, "main", return_value=3) as main:
            with self.assertRaises(SystemExit) as result:
                runpy.run_path(str(launcher), run_name="__main__")
            self.assertEqual(result.exception.code, 3)
            main.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
