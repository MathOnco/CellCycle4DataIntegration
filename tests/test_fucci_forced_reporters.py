"""Forced reporter decisions must retain all four states without hiding missing data."""
import sys
import unittest
from pathlib import Path

import numpy as np
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from force_fucci_fof5_reporter_states import point_states, nearest_reference


class ForcedReporterTests(unittest.TestCase):
    def test_all_four_states_threshold_equality_and_missing_guard(self):
        models = {"green": {"threshold": .006}, "red": {"threshold": .004}}
        states, _, _ = point_states([.02, .001, .02, -.001, .006], [.001, .02, .02, -.001, .004], models)
        self.assertEqual(states.tolist(), ["green_only", "red_only", "both", "neither", "neither"])
        with self.assertRaisesRegex(ValueError, "missing is not neither"):
            point_states([np.nan], [.001], models)

    def test_fallback_expands_past_masked_neighbors_and_includes_distance_ties(self):
        geometry = np.zeros((60, 60), int)
        geometry[29:31, 29:31] = 1
        mask = np.zeros_like(geometry)
        mask[10:50, 10:50] = 2
        mask[geometry == 1] = 1
        selected, radius = nearest_reference(geometry, mask, 1)
        distance = ndimage.distance_transform_edt(geometry != 1)
        self.assertTrue((mask[selected] == 0).all())
        self.assertTrue((distance[selected] > 3).all())
        self.assertGreaterEqual(selected.sum(), 50)
        self.assertGreater(radius, 12)
        self.assertLess(((mask == 0) & (distance > 3) & (distance < radius)).sum(), 50)
        np.testing.assert_array_equal(selected, (mask == 0) & (distance > 3) & (distance <= radius))


if __name__ == "__main__":
    unittest.main()
