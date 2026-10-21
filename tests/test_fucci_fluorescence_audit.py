"""Check image-derived slice means and exclusion of other labels from local references."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import tifffile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_fucci_fluorescence import measure_images
from fucci_analysis.data import sha256


class FluorescenceAuditTests(unittest.TestCase):
    def test_slice_differs_from_volume_and_bright_neighbor_is_excluded_from_annulus(self):
        mask = np.zeros((3, 40, 40), dtype=np.uint16)
        mask[:, 12:18, 12:18] = 1
        mask[:, 12:18, 20:26] = 2
        backgrounds = {"green": .002, "red": .008}
        cell_values = {"green": [.010, .004, .016], "red": [.014, .008, .014]}
        means = {c: float(np.mean(values)) for c, values in cell_values.items()}
        frame = pd.DataFrame({"geometry_id": [1], "green": [means["green"]],
                              "red": [means["red"]], "baseline_phase": ["G2M"]})
        source = pd.DataFrame({"ObjectNumber": [1, 2],
                               "Intensity_MeanIntensity_green": [means["green"], .9],
                               "Intensity_MeanIntensity_red": [means["red"], .9]})
        display = {c: {"low": 0, "high": 1} for c in backgrounds}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = {"image_files": []}
            for c, number in [("green", "00"), ("red", "02")]:
                for z in range(3):
                    raw = np.full(mask.shape[1:], backgrounds[c], dtype=np.float32)
                    raw[mask[z] == 1] = cell_values[c][z]
                    raw[mask[z] == 2] = .9
                    path = root / f"example_z{z:02}_ch{number}.tif"
                    tifffile.imwrite(path, raw)
                    manifest["image_files"].append({"channel": c, "z": z, "sha256": sha256(path)})
            result, _, _ = measure_images(frame, mask, mask, root, display, 1, source, manifest)
        row = result.iloc[0]
        self.assertEqual(row.slice_area_pixels, 36)
        self.assertEqual(row.slice_threshold_phase, "G1")
        self.assertTrue(row.slice_vs_3d_threshold_changed)
        self.assertGreater(row.annulus_voxels_3d, 0)
        for c in backgrounds:
            self.assertAlmostEqual(row[c+"_annulus_mean_3d"], backgrounds[c], places=7)
            self.assertAlmostEqual(row[c+"_slice_annulus_mean"], backgrounds[c], places=7)
            self.assertAlmostEqual(row[c+"_slice_mean"], cell_values[c][1], places=7)


if __name__ == "__main__":
    unittest.main()
