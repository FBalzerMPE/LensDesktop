from pathlib import Path
import tempfile
import unittest
from configparser import ConfigParser

from LensDesktop.defaults import DefaultsError, defaults_path, load_gui_defaults


class GuiDefaultsTests(unittest.TestCase):
    def test_bundled_ini_preserves_current_gui_defaults(self):
        defaults = load_gui_defaults()
        config = ConfigParser()
        config.read(defaults_path(), encoding="utf-8")
        self.assertEqual(defaults_path().name, "defaults.ini")
        self.assertEqual(defaults.input.key.color, (0, 255, 128))
        self.assertEqual(defaults.input.zoom, 100)
        self.assertEqual(defaults.configuration.preset, "cross")
        self.assertEqual(
            defaults.placement.scale,
            config.getint("Source placement", "scale"),
        )
        self.assertEqual(defaults.lens.einstein_radius, 65)
        self.assertFalse(defaults.lens.heart)
        self.assertEqual(defaults.background.fitting, "fill")
        self.assertTrue(defaults.background.image.endswith("euclid_abell_2764_example.jpeg"))

    def test_missing_or_invalid_ini_fails_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.ini"
            with self.assertRaisesRegex(DefaultsError, "Cannot load GUI defaults"):
                load_gui_defaults(path)

            source = defaults_path().read_text(encoding="utf-8")
            path.write_text(source.replace("camera_index = 0", "camera_index = 100"), encoding="utf-8")
            with self.assertRaisesRegex(DefaultsError, "camera_index must be between 0 and 99"):
                load_gui_defaults(path)

            path.write_text(source.replace("expanded = true", "expand = true", 1), encoding="utf-8")
            with self.assertRaisesRegex(DefaultsError, "missing options: expanded"):
                load_gui_defaults(path)


if __name__ == "__main__":
    unittest.main()
