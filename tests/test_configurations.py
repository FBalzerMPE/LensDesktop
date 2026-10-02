import unittest

import cv2
import numpy as np
from scipy.optimize import root

from LensDesktop.app import SIE_defl, source_configuration_geometry
from LensDesktop.processing import ImageError, place_source


class ConfigurationGeometryTests(unittest.TestCase):
    def test_presets_are_inside_tangential_caustic_and_follow_rotation(self):
        geometry = source_configuration_geometry(0.65, 0.02, 0)
        np.testing.assert_array_equal(geometry.position("cross"), [0, 0])
        for name in ("cross", "cusp", "fold"):
            self.assertGreater(geometry.clearance(name), 0)
        cusp = geometry.position("cusp")
        fold = geometry.position("fold")
        self.assertGreater(cusp[0], fold[0])
        self.assertAlmostEqual(cusp[1], 0, delta=0.02)
        self.assertGreater(fold[0], 0)
        self.assertGreater(fold[1], 0)
        angle = 0.6
        rotated = source_configuration_geometry(0.65, 0.02, angle)
        rotation = np.array([[np.cos(angle), np.sin(angle)], [-np.sin(angle), np.cos(angle)]])
        for name in ("cusp", "fold"):
            np.testing.assert_allclose(rotated.position(name), rotation @ geometry.position(name), atol=0.015)

    def test_axis_ratio_and_core_affect_presets(self):
        first = source_configuration_geometry(0.65, 0.02, 0)
        second = source_configuration_geometry(0.8, 0.02, 0)
        self.assertLess(np.linalg.norm(second.position("cusp")), np.linalg.norm(first.position("cusp")))
        self.assertFalse(np.allclose(
            first.position("fold"), source_configuration_geometry(0.65, 0.1, 0).position("fold")
        ))

    def test_degenerate_lenses_and_nonstandard_model_fail_explicitly(self):
        for kwargs in ({"q": 0.99, "core": 0.02}, {"q": 0.65, "core": 1},
                       {"q": 0.65, "core": 0.02, "heart": True}):
            with self.assertRaises(ImageError):
                source_configuration_geometry(angle=0, **kwargs)

    def test_point_sources_produce_cross_cusp_trio_and_fold_pair(self):
        geometry = source_configuration_geometry(0.65, 0.02, 0)

        def images(position):
            def equation(point):
                x, y, _ = SIE_defl(point[0], point[1], 0, 0.02, False, 0.65, 1 / np.sqrt(0.65))
                return point - np.array([x, y]) - position

            solutions = []
            for radius in (0.3, 0.8, 1.5):
                for angle in np.linspace(0, 2 * np.pi, 24, endpoint=False):
                    solved = root(equation, radius * np.array([np.cos(angle), np.sin(angle)]))
                    if solved.success and np.linalg.norm(equation(solved.x)) < 1e-7:
                        if np.linalg.norm(solved.x) > 0.1 and all(
                            np.linalg.norm(solved.x - previous) > 1e-3 for previous in solutions
                        ):
                            solutions.append(solved.x)
            return np.array(solutions)

        cross, cusp, fold = [images(geometry.position(name)) for name in ("cross", "cusp", "fold")]
        for found in (cross, cusp, fold):
            self.assertEqual(len(found), 4)
        self.assertEqual(np.count_nonzero(cusp[:, 0] > 0), 3)
        cross_distances = sorted(np.linalg.norm(cross[i] - cross[j]) for i in range(4) for j in range(i))
        fold_distances = sorted(np.linalg.norm(fold[i] - fold[j]) for i in range(4) for j in range(i))
        self.assertLess(fold_distances[0], cross_distances[0])
        self.assertLess(fold_distances[0], fold_distances[1] * 0.8)


class PreLensPlacementTests(unittest.TestCase):
    def test_visible_subject_is_centered_at_requested_source_position(self):
        alpha = np.zeros((128, 128), np.float32)
        alpha[30:70, 10:50] = 1
        color = np.full((128, 128, 3), (200, 80, 20), np.float32) * alpha[..., None]
        original = color.copy()
        placed, coverage, diameter = place_source(color, alpha, 0.5, 40, (0.2, -0.1))
        yy, xx = np.indices(coverage.shape)
        self.assertAlmostEqual(float(np.sum(xx * coverage) / coverage.sum()), 1.2 * 63, delta=0.06)
        self.assertAlmostEqual(float(np.sum(yy * coverage) / coverage.sum()), 0.9 * 63, delta=0.06)
        self.assertAlmostEqual(diameter, 12.6)
        np.testing.assert_allclose(placed, coverage[..., None] * (200, 80, 20), atol=0.001)
        np.testing.assert_array_equal(color, original)

    def test_black_source_remains_opaque_and_empty_source_reports_error(self):
        color = np.zeros((64, 64, 3), np.float32)
        _, alpha, _ = place_source(color, np.ones((64, 64), np.float32), 0.5, 40, (0, 0))
        self.assertGreater(alpha.sum(), 0)
        with self.assertRaises(ImageError):
            place_source(color, np.zeros((64, 64), np.float32), 0.5, 40, (0, 0))
        with self.assertRaises(ImageError):
            place_source(color, np.ones((64, 64), np.float32), 0, 40, (0, 0))


if __name__ == "__main__":
    unittest.main()
