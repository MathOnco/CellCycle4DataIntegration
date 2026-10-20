"""Spatial joins must use explicit mappings when CellID and ObjectNumber differ."""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from plot_fucci_spatial_verification import build_policies, CODE


class SpatialMappingTests(unittest.TestCase):
    def test_global_cell_ids_map_to_local_components_and_excluded_satellites_stay_uncolored(self):
        source = pd.DataFrame({
            "ObjectNumber": [1, 2, 3], "CellposeLabel": [10, 10, 20],
            "object_id": ["241016/5/801", "241016/5/802", "241016/5/803"],
            "baseline_phase": ["G1", "S", "G2M"],
            "Intensity_MeanIntensity_green": [.01, .002, .02],
            "Intensity_MeanIntensity_red": [.008, .02, .02],
        })
        frame = pd.DataFrame({
            "mask_label_id": ["241016/5/mask_10", "241016/5/mask_20"],
            "CellposeLabel": [10, 20], "largest_object_id": ["241016/5/801", "241016/5/803"],
            "baseline_phase": ["G1", "G2M"], "provisional_phase": ["uncertain", "G2M"],
            "green": [.01, .02], "red": [.008, .02],
        })
        mask = np.array([[[0, 10, 10, 20]]])
        components = np.array([[[0, 1, 2, 3]]])
        predictions = {"aggregated": frame, "dominant": frame, "singletons": frame.iloc[[1]]}
        policies, _ = build_policies(source, mask, components, predictions)
        np.testing.assert_array_equal(policies["dominant"]["frame"].geometry_id, [1, 3])
        np.testing.assert_array_equal(
            policies["dominant"]["lookups"]["baseline_phase"][components],
            [[[0, CODE["G1"], 0, CODE["G2M"]]]])
        np.testing.assert_array_equal(
            policies["singletons"]["lookups"]["baseline_phase"][components],
            [[[0, 0, 0, CODE["G2M"]]]])
        np.testing.assert_array_equal(
            policies["source_rows"]["lookups"]["baseline_phase"][components],
            [[[0, CODE["G1"], CODE["S"], CODE["G2M"]]]])


if __name__ == "__main__":
    unittest.main()
