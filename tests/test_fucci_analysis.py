"""Scientific invariants: source gates, additive support, and reporter-state scores."""
import unittest
import tempfile
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.fucci_analysis.data import aggregate_mask_labels, gates, training_weights
from scripts.fucci_analysis.data import validate_resume_inputs, validate_saved_labels, STATES
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

    def test_resume_rejects_changed_inputs_without_rewriting_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            archive = out / "input.zip"
            archive.write_bytes(b"original")
            config = {"archive": str(archive), "confidence_threshold": .8, "review_objects_per_field": 6}
            path = out / "prediction_provenance.json"
            path.write_text(json.dumps({"archive_sha256": hashlib.sha256(b"original").hexdigest(), "config": config}))
            original = path.read_bytes()
            validate_resume_inputs(config, out, "review")
            validate_resume_inputs({**config, "review_objects_per_field": 8}, out, "review")
            with self.assertRaisesRegex(ValueError, "configuration changed"):
                validate_resume_inputs({**config, "confidence_threshold": .6}, out, "report")
            archive.write_bytes(b"replacement")
            # A later audit must not make old predictions compatible with a new archive.
            (out / "input_manifest.json").write_text(json.dumps({
                "archive_sha256": hashlib.sha256(b"replacement").hexdigest(), "config": config}))
            with self.assertRaisesRegex(ValueError, "archive changed"):
                validate_resume_inputs(config, out, "review")
            self.assertEqual(path.read_bytes(), original)

    def test_saved_predictions_must_cover_unchanged_measurements(self):
        current = pd.DataFrame({"mask_label_id": ["a", "b"], "volume": [100, 200],
                                "green": [.01, .02], "red": [.008, .015],
                                "green_gate": [.005, .005], "red_gate": [.009, .009], "n_components": [1, 2]})
        saved = current.copy()
        for state in STATES:
            saved[f"p_{state}"] = .25
            saved[f"oof_p_{state}"] = .25
        validate_saved_labels(current, saved.iloc[::-1])
        with self.assertRaisesRegex(ValueError, "cover"):
            validate_saved_labels(current, saved.iloc[:1])
        altered = saved.copy()
        altered.loc[0, "green"] *= 2
        with self.assertRaises(AssertionError):
            validate_saved_labels(current, altered)

    def test_review_rerun_preserves_human_annotations_and_previous_candidates(self):
        from scripts.fucci_analysis.review import save_review_annotations
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "annotations.csv"
            pd.DataFrame([
                {"mask_label_id": "a", "review_status": "reviewed", "reviewer_notes": "boundary unclear", "crop_z": 3},
                {"mask_label_id": "b", "review_status": "reviewed", "reviewer_notes": "keep this note", "crop_z": 5},
            ]).to_csv(path, index=False)
            save_review_annotations([
                {"mask_label_id": "a", "review_status": "unreviewed", "reviewer_notes": "", "crop_z": 4},
                {"mask_label_id": "c", "review_status": "unreviewed", "reviewer_notes": "", "crop_z": 6},
            ], path)
            after = pd.read_csv(path).set_index("mask_label_id")
            self.assertEqual(after.loc["a", "review_status"], "reviewed")
            self.assertEqual(after.loc["a", "reviewer_notes"], "boundary unclear")
            self.assertEqual(after.loc["a", "crop_z"], 4)
            self.assertEqual(after.loc["b", "reviewer_notes"], "keep this note")
            self.assertFalse(after.loc["b", "in_current_review_set"])
            self.assertEqual(after.loc["c", "review_status"], "unreviewed")


if __name__ == "__main__":
    unittest.main()
