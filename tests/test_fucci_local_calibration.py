"""Scientific invariants for local reporter measurements and selective calls."""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from fucci_analysis.local_calibration import (
    FEATURES, VARIANTS, local_masks, aggregate_features, threshold_fit,
    channel_call, apply_thresholds, select_thresholds,
)


class LocalCalibrationTests(unittest.TestCase):
    def test_references_and_dilation_exclude_neighboring_labels(self):
        geometry = np.zeros((50, 50), dtype=int)
        geometry[20:28, 20:28] = 1
        geometry[20:28, 28:35] = 2
        foreground, rings = local_masks(geometry, geometry, 1)
        for pixels in rings.values():
            self.assertTrue(np.all(geometry[pixels] == 0))
        self.assertFalse(np.any(foreground["dilate1"] & (geometry == 2)))
        self.assertLess(foreground["erode2"].sum(), foreground["erode1"].sum())
        self.assertLess(foreground["erode1"].sum(), foreground["original"].sum())

    def test_signed_volume_weighted_scores_and_z_subset(self):
        rows = []
        for z, area, value in [(0, 100, .004), (1, 300, .002), (2, 100, .004)]:
            row = {"geometry_id": 1, "channel": "green", "z": z}
            for fg in ["original", "erode1", "erode2", "dilate1"]:
                row.update({fg+"_n": area, fg+"_mean": value, fg+"_median": value, fg+"_q75": value})
            for bg in ["main", "near", "far"]:
                row.update({bg+"_n": 100, bg+"_mean": .003, bg+"_median": .003, bg+"_trimmed": .003, bg+"_mad": .001})
            rows.append(row)
        scores = aggregate_features(pd.DataFrame(rows)).set_index("variant")
        self.assertAlmostEqual(scores.loc["primary", "mean_excess"], -.0002)
        self.assertAlmostEqual(scores.loc["primary", "mean_contrast"], -.2)
        self.assertAlmostEqual(scores.loc["even_z", "mean_excess"], .001)
        self.assertAlmostEqual(scores.loc["odd_z", "mean_excess"], -.001)

    def test_threshold_uncertainty_and_variant_disagreement_are_unresolved(self):
        model = {"feature": "mean_excess", "bootstrap_threshold_low": 1., "bootstrap_threshold_high": 2.}
        self.assertEqual(channel_call([.5, 1.5, 3.], model).tolist(), ["not_detected", "ambiguous", "positive"])
        rows = []
        for obj in [1, 2, 3]:
            for variant in VARIANTS:
                for c in ["green", "red"]:
                    score = 3. if c == "green" else .5
                    if obj == 2 and variant == "far_reference" and c == "green": score = .5
                    if obj == 3 and c == "red": score = 1.5
                    rows.append({"geometry_id": obj, "channel": c, "variant": variant, "mean_excess": score,
                                 "reference_coverage": 1., "valid_voxels": 1000, "valid_planes": 10, "max_plane_area": 100})
        calls, _, _ = apply_thresholds(pd.DataFrame(rows), {"green": model, "red": model})
        self.assertEqual(calls.reporter_state.tolist(), ["green_only", "unresolved", "unresolved"])
        self.assertIn("sensitive_to_measurement_choice", calls.iloc[1].unresolved_reasons)
        self.assertIn("threshold_uncertainty", calls.iloc[2].unresolved_reasons)

    def test_threshold_fit_and_check_split_protection(self):
        result = threshold_fit([-.2, .1, 2, 3], [0, 0, 1, 1])
        self.assertEqual(result["balanced_agreement"], 1.)
        self.assertTrue(.1 <= result["threshold"] < 2)
        with self.assertRaisesRegex(ValueError, "Only calibration"):
            select_thresholds(pd.DataFrame(), pd.DataFrame({"split": ["check"]}))


if __name__ == "__main__":
    unittest.main()
