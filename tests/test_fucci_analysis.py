"""Scientific invariants: source gates, additive support, and reporter-state scores."""
import unittest
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.fucci_analysis.data import aggregate_mask_labels, gates, training_weights
from scripts.fucci_analysis.model import AnchoredMixture, IndependentChannels, model_from_dict


class FucciAnalysisTests(unittest.TestCase):
    def test_gate_boundaries_preserve_upstream_default(self):
        # R uses strict >/<; equality must retain its initialized low/low state.
        result = gates(np.array([.001, .006, .001, .006, .005, .006]),
                       np.array([.008, .008, .012, .012, .008, .009]), .005, .009)
        np.testing.assert_array_equal(result, [0, 1, 2, 3, 0, 0])

    def test_fragment_reassembly_preserves_signal_and_volume(self):
        rows = []
        for i, (volume, green, red, x) in enumerate([(100, .01, .02, 10), (1, .5, .3, 30)]):
            row = dict(mask_label_id="d/1/mask_7", object_id=f"d/1/{i}", field_id="d/1", folder="f",
                       Date="d", FoF="1", ImageSet="image", FileName_mask="mask", CellposeLabel="7",
                       green_gate=.005, red_gate=.009, volume=volume, green=green, red=red,
                       green_sum=volume*green, red_sum=volume*red, tiny_object=volume <= 8,
                       saturated_voxel=False, green_median=green, red_median=red, green_core=green, red_core=red)
            for axis in "xyz":
                row[axis] = x; row[f"{axis}_min"] = x-1; row[f"{axis}_max"] = x+1
            rows.append(row)
        labels = aggregate_mask_labels(pd.DataFrame(rows))
        self.assertEqual(len(labels), 1)
        self.assertEqual(labels.volume.iloc[0], 101)
        self.assertAlmostEqual(labels.green.iloc[0], 1.5/101)
        self.assertAlmostEqual(labels.red.iloc[0], 2.3/101)
        self.assertAlmostEqual(labels.x.iloc[0], 1030/101)
        self.assertEqual(labels.largest_green_median.iloc[0], .01)
        self.assertEqual(labels.n_components.iloc[0], 2)

    def test_split_fragments_do_not_increase_training_weight(self):
        df = pd.DataFrame({"field_id": ["a"]*4+["b"], "mask_label_id": ["a1"]*3+["a2", "b1"]})
        weights = pd.Series(training_weights(df, object_level=True))
        self.assertAlmostEqual(weights.iloc[:3].sum(), weights.iloc[3])
        self.assertAlmostEqual(weights.iloc[:4].sum(), weights.iloc[4])

    def test_models_keep_state_identity_and_unequal_frequencies(self):
        rng = np.random.default_rng(4)
        centers = np.array([[-.5,-.4],[.6,-.4],[-.5,.5],[.6,.5]])
        x = np.concatenate([rng.normal(center, .035, size=(n,2)) for center,n in zip(centers,[30,90,180,300])])
        for model in [AnchoredMixture(max_iter=150), IndependentChannels(max_iter=150)]:
            model.fit(x, seed=12)
            p = model.predict_proba(x)
            self.assertTrue(np.isfinite(p).all())
            np.testing.assert_allclose(p.sum(axis=1),1,atol=1e-12)
            np.testing.assert_array_equal(model.predict_proba(centers).argmax(axis=1),np.arange(4))
            self.assertTrue(np.isfinite(model.score_samples(x)).all())
            restored = model_from_dict(model.as_dict())
            np.testing.assert_allclose(restored.predict_proba(x), p, atol=1e-12)
        self.assertGreater(AnchoredMixture().fit(x).weights[3], .45)

    def test_lzw_decode_preserves_16_bit_intensity_scale(self):
        from PIL import Image
        from scripts.fucci_analysis.review import normalized_plane
        source = np.array([[0, 255], [32768, 65535]], dtype=np.uint16)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image.tif"
            Image.fromarray(source).save(path, compression="tiff_lzw")
            np.testing.assert_allclose(normalized_plane(path), source.astype(float)/65535, rtol=1e-7)


if __name__ == "__main__":
    unittest.main()
