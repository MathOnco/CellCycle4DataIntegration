"""The additional gates may only modify a fresh original neither decision."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from force_fucci_fof5_reporter_states import point_states
from fucci_analysis.neither_refinement import classify
from refine_fucci_fof5_neither import apply_model


class NeitherRefinementTests(unittest.TestCase):
    def setUp(self):
        self.t = {"green": {"high": .006, "low": .003}, "red": {"high": .004, "low": .002}}

    def test_opposite_lower_cutoff_cannot_take_a_single_positive(self):
        final, original, promoted = classify([.007, .004, .007, .004, .001], [.003, .005, .005, .003, .001], self.t)
        self.assertEqual(original.tolist(), ["green_only", "red_only", "both", "neither", "neither"])
        self.assertEqual(final.tolist(), ["green_only", "red_only", "both", "both", "neither"])
        self.assertEqual(promoted.tolist(), [False, False, False, True, False])

    def test_original_function_is_called_again_when_measurements_change(self):
        with patch("fucci_analysis.neither_refinement.point_states", wraps=point_states) as original_function:
            a, original_a, _ = classify([.004], [.005], self.t)
            b, original_b, _ = classify([.007], [.005], self.t)
            self.assertEqual(original_function.call_count, 2)
        self.assertEqual((a[0], original_a[0]), ("red_only", "red_only"))
        self.assertEqual((b[0], original_b[0]), ("both", "both"))

    def test_only_neither_to_both_allowed_across_scores_and_lower_thresholds(self):
        g, r = np.meshgrid(np.linspace(-.002, .012, 51), np.linspace(-.002, .010, 51))
        for lg in [0, .002, .006]:
            for lr in [0, .001, .004]:
                model = {"green": {"high": .006, "low": lg}, "red": {"high": .004, "low": lr}}
                final, original, promoted = classify(g, r, model)
                self.assertTrue((final[original != "neither"] == original[original != "neither"]).all())
                changed = final != original
                np.testing.assert_array_equal(changed, promoted)
                self.assertTrue((original[changed] == "neither").all())
                self.assertTrue((final[changed] == "both").all())

    def test_export_ignores_saved_assignments_when_predicting(self):
        source = pd.DataFrame({"forced_green_score": [.004, .004],
                               "forced_red_score": [.005, .003],
                               "reporter_state": ["red_only", "neither"]})
        a = apply_model(source, self.t)
        source["reporter_state"] = ["green_only", "both"]
        b = apply_model(source, self.t)
        self.assertEqual(a.reporter_state.tolist(), ["red_only", "both"])
        self.assertEqual(a.reporter_state.tolist(), b.reporter_state.tolist())
        self.assertTrue(a.original_reproduces_stored_assignment.all())
        self.assertFalse(b.original_reproduces_stored_assignment.any())

    def test_equality_and_invalid_measurements(self):
        final, original, _ = classify([.003, .004, .006, .007], [.003, .002, .004, .004], self.t)
        self.assertEqual(original.tolist(), ["neither", "neither", "neither", "green_only"])
        self.assertEqual(final.tolist(), ["neither", "neither", "both", "green_only"])
        with self.assertRaisesRegex(ValueError, "missing is not neither"):
            classify([np.nan], [.001], self.t)
        with self.assertRaises(ValueError): classify([.001, .002], [.001], self.t)
        with self.assertRaises(ValueError):
            classify([.001], [.001], {"green": {"low": .007, "high": .006}, "red": self.t["red"]})


if __name__ == "__main__":
    unittest.main()
