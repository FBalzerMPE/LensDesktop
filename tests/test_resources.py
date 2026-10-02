import ast
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from LensDesktop import processing


class ResourceTests(unittest.TestCase):
    def test_spec_includes_default_image_and_attribution(self):
        root = Path(__file__).resolve().parent.parent
        source = ast.parse((root / "LensDesktop.spec").read_text(encoding="utf-8"))
        assignment = next(
            node for node in source.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "datas" for target in node.targets)
        )
        namespace = {"os": os, "SPECPATH": str(root)}
        exec(compile(ast.Module(body=[assignment], type_ignores=[]), "LensDesktop.spec", "exec"), namespace)
        paths = namespace["datas"]
        self.assertIn((str(root / "data" / "euclid_patch_example.jpg"), "data"), paths)
        self.assertIn((str(root / "data" / "euclid_abell_2764_example.jpeg"), "data"), paths)
        self.assertIn((str(root / "data" / "README.md"), "data"), paths)
        self.assertIn((str(root / "data" / "example_gs_pic.jpeg"), "data"), paths)
        self.assertIn((str(root / "data" / "defaults.ini"), "data"), paths)
        self.assertTrue(all(Path(path).is_file() for path, _ in paths))

    def test_default_path_resolves_in_a_relocated_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "_internal"
            data = root / "data"
            data.mkdir(parents=True)
            shutil.copy2(processing.default_background_path(), data / "euclid_abell_2764_example.jpeg")
            shutil.copy2(processing.example_source_path(), data / "example_gs_pic.jpeg")
            with patch.object(processing, "__file__", str(root / "LensDesktop" / "processing.py")):
                background = processing.SkyBackground()
                background.load(processing.default_background_path())
                self.assertEqual(background.path, data / "euclid_abell_2764_example.jpeg")
                self.assertIsNotNone(background.image)
                photo = processing.read_image_bgr(processing.example_source_path())
                self.assertEqual(photo.shape[2], 3)


if __name__ == "__main__":
    unittest.main()
