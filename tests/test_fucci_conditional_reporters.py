"""Check the agreed hierarchy and image-reference fitting guardrails."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from fucci_analysis.conditional_reporters import classify, fit_lower


class ConditionalReporterTests(unittest.TestCase):
    def setUp(self):
        self.t = {"green": {"low": .003, "high": .006}, "red": {"low": .002, "high": .004}}

    def test_dim_joint_detection_and_weak_single_signal(self):
        g = [.004, .004, .007, .007, .001, -.001]
        r = [.003, .001, .001, .003, .005, -.001]
        self.assertEqual(classify(g, r, self.t).tolist(), ["both", "neither", "green_only", "both", "red_only", "neither"])

    def test_equality_and_missing_values(self):
        self.assertEqual(classify([.003, .006, .007, .003], [.003, .002, .002, .005], self.t).tolist(),
                         ["neither", "neither", "green_only", "red_only"])
        with self.assertRaisesRegex(ValueError, "missing is not neither"):
            classify([np.nan], [.004], self.t)
        with self.assertRaises(ValueError):
            classify([.001, .002], [.001], self.t)

    def test_more_signal_cannot_turn_both_into_a_single(self):
        g, r = np.meshgrid(np.linspace(.0031, .02, 20), np.linspace(.0021, .02, 20))
        self.assertTrue((classify(g, r, self.t) == "both").all())

    def test_fit_requires_joint_positive_and_negative_image_references(self):
        high = {"green": .006, "red": .004}
        with self.assertRaisesRegex(ValueError, "two usable reviewed both"):
            fit_lower([.001, .002, .005], [.001, .001, .003], ["neither", "neither", "both"], high)
        g = np.array([.0035, .0045, .001, .002, .009, .001])
        r = np.array([.0025, .0035, .001, .001, .001, .009])
        y = np.array(["both", "both", "neither", "neither", "green_only", "red_only"])
        fitted, score = fit_lower(g, r, y, high)
        self.assertEqual(score["balanced_both_agreement"], 1)
        self.assertLess(fitted["green"]["low"], high["green"])
        self.assertLess(fitted["red"]["low"], high["red"])
        np.testing.assert_array_equal(classify(g, r, fitted), y)


if __name__ == "__main__":
    unittest.main()
