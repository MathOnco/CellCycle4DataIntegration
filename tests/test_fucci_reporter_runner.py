"""Portable input matching, measurement and multi-field execution invariants."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

import numpy as np
import pandas as pd
from scipy import ndimage
from skimage import measure
import tifffile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"scripts"))
from fucci_analysis.reporter_inputs import (feature_table, image_files, match_components,
    read_manifest, read_mask, select_field, inventory)
from fucci_analysis.reporter_runner import load_model, run_field


def fixture(root, date="231005", fof="1"):
    image_set = f"FoF{fof}_{date}_test"
    images = root/image_set; images.mkdir()
    mask = np.zeros((3, 64, 64), np.uint16)
    for label, y, x, size in [(10, 4, 4, 10), (20, 4, 36, 10), (30, 36, 4, 10), (40, 36, 36, 10), (50, 24, 24, 7)]:
        mask[:, y:y+size, x:x+size] = label
    mask[0, 60, 60] = 10  # a disconnected fragment, never a separate final cell
    tifffile.imwrite(root/f"{image_set}_masks.tif", mask, photometric="minisblack")
    raw = {}
    for c, ch, excess in [("green", "00", {10: 650, 20: 200, 30: 250, 40: 80, 50: 600}),
                           ("red", "02", {10: 100, 20: 600, 30: 230, 40: 60, 50: 500})]:
        channel = np.full(mask.shape, 1000, np.uint16)
        for label, value in excess.items(): channel[mask == label] += value
        for z, plane in enumerate(channel): tifffile.imwrite(images/f"img_z{z:02}_ch{ch}.tif", plane)
        raw[c] = channel.astype(np.float32)/65535
    components = measure.label(mask, background=0, connectivity=3)
    rows = []
    for obj, box in enumerate(ndimage.find_objects(components), start=1):
        foreground = components == obj
        row = {"Date": date, "FoF": fof, "ObjectNumber": obj, "CellposeLabel": int(mask[foreground][0]),
               "CellID": obj+100, "AreaShape_Volume": int(foreground.sum()), "ImageSet": image_set,
               "FileName_mask": f"{image_set}_masks.tif"}
        for axis, pos in zip("XYZ", [2, 1, 0]):
            row[f"AreaShape_BoundingBoxMinimum_{axis}"] = box[pos].start
            row[f"AreaShape_BoundingBoxMaximum_{axis}"] = box[pos].stop
        for c, image in raw.items():
            row[f"Intensity_MeanIntensity_{c}"] = np.mean(image[foreground], dtype=np.float64)
            row[f"Intensity_IntegratedIntensity_{c}"] = np.sum(image[foreground], dtype=np.float64)
        rows.append(row)
    return {"folder": "source", "date": date, "fof": fof, "features": str(root/"object_features_new.csv"),
            "features_member": "", "images": str(images), "mask": str(root/f"{image_set}_masks.tif"),
            "mask_member": "", "green_channel": "00", "red_channel": "02"}, pd.DataFrame(rows), mask


class PortableReporterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.a, a, self.mask = fixture(self.root)
        self.b, b, _ = fixture(self.root, "241016", "7")
        pd.concat([a, b], ignore_index=True).to_csv(self.a["features"], index=False)
        self.model, self.bootstrap, self.model_hash = load_model()

    def tearDown(self):
        feature_table.cache_clear()
        self.temp.cleanup()

    def test_matching_and_selection_are_specific_to_the_requested_field(self):
        frame, _ = select_field(self.b)
        components, units = match_components(frame, self.mask)
        self.assertTrue(frame.Date.eq("241016").all())
        self.assertTrue(frame.FoF.eq("7").all())
        self.assertEqual(len(frame), 6)
        self.assertEqual(len(units), 5)
        parent = units.set_index("CellposeLabel").loc[10]
        self.assertEqual(parent.n_components, 2)
        self.assertEqual(parent.volume, 300)
        self.assertEqual(parent.parent_volume, 301)
        self.assertFalse(parent.ObjectNumber == int(components[0, 60, 60]))
        broken = frame.copy(); broken.loc[0, "AreaShape_BoundingBoxMinimum_X"] += 1
        with self.assertRaisesRegex(ValueError, "bounding-box"):
            match_components(broken, self.mask)
        broken = frame.copy(); broken.loc[0, "CellposeLabel"] = 10+65536
        with self.assertRaisesRegex(ValueError, "integer range"):
            match_components(broken, self.mask)

    def test_missing_duplicate_planes_and_ambiguous_masks_are_rejected(self):
        images = Path(self.a["images"])
        (images/"duplicate_z00_ch00.tif").write_bytes((images/"img_z00_ch00.tif").read_bytes())
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            image_files(images, "00", 3)
        (images/"duplicate_z00_ch00.tif").unlink()
        (images/"img_z01_ch00.tif").unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            image_files(images, "00", 3)
        archive = self.root/"masks.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.write(self.a["mask"], "one_masks.tif"); z.write(self.b["mask"], "two_masks.tif")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            read_mask(archive)
        actual, provenance = read_mask(archive, "two_masks.tif")
        np.testing.assert_array_equal(actual, self.mask)
        self.assertEqual(provenance["member"], "two_masks.tif")

    def test_raw_to_states_and_resume_integrity(self):
        output = self.root/"result"
        with contextlib.redirect_stdout(io.StringIO()):
            summary = run_field(self.a, output, self.model, self.bootstrap, self.model_hash, plots=False)
            resumed = run_field(self.a, output, self.model, self.bootstrap, self.model_hash, resume=True, plots=False)
        self.assertEqual(summary, resumed)
        data = pd.read_csv(output/"cell_reporter_states.csv").set_index("CellposeLabel")
        self.assertEqual(data.reporter_state.to_dict(), {10: "green_only", 20: "red_only", 30: "both", 40: "neither", 50: "both"})
        self.assertEqual(data.original_reporter_state.loc[30], "neither")
        self.assertEqual(summary["promoted_n"], 1)
        self.assertEqual(summary["fallback_n"], 0)
        self.assertGreater(data.forced_green_score.loc[20], self.model["thresholds"]["green"]["low"])
        self.assertTrue(data.green_reference_coverage.eq(1).all())
        with (output/"cell_reporter_states.csv").open("a") as f: f.write("\n")
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, "Saved output changed"):
            run_field(self.a, output, self.model, self.bootstrap, self.model_hash, resume=True, plots=False)

    def test_manifest_paths_inventory_and_batch_failure_accounting(self):
        specs = [dict(self.a), dict(self.b)]
        for spec in specs:
            for col in ["features", "images", "mask"]:
                spec[col] = str(Path(spec[col]).relative_to(self.root))
        manifest = self.root/"fields.csv"
        pd.DataFrame(specs).to_csv(manifest, index=False)
        self.assertEqual(read_manifest(manifest)[0]["images"], self.a["images"])
        discovered = inventory(Path(self.a["features"]), self.root, self.root)
        self.assertEqual(len(discovered), 2)
        self.assertTrue(discovered.images_exist.all())
        self.assertTrue(discovered.mask_candidates_found.eq(1).all())
        command = [sys.executable, str(ROOT/"scripts/run_fucci_reporters.py"), "batch", "--manifest", str(manifest),
                   "--output", str(self.root/"batch"), "--no-plots"]
        checked = subprocess.run(command+["--check"], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stdout+checked.stderr)
        self.assertFalse((self.root/"batch").exists())
        result = subprocess.run(command, cwd=self.root, env={**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        combined = pd.read_csv(self.root/"batch/all_cell_reporter_states.csv.gz")
        self.assertEqual(len(combined), 10)
        self.assertEqual(combined.field_id.nunique(), 2)
        self.assertTrue(combined.unit_id.is_unique)
        (Path(self.b["images"])/"img_z02_ch02.tif").unlink()
        resumed = subprocess.run(command+["--resume"], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(resumed.returncode, 1)
        summary = json.loads((self.root/"batch/batch_summary.json").read_text())
        self.assertFalse(summary["all_requested_fields_complete"])
        self.assertEqual((summary["completed_fields"], summary["failed_fields"], summary["completed_labels"]), (1, 1, 5))
        states = pd.read_csv(self.root/"batch/field_status.csv")
        self.assertEqual(states.status.tolist(), ["complete", "error"])

    def test_swapped_channels_cannot_publish_mismatched_measurements(self):
        bad = {**self.a, "green_channel": "02", "red_channel": "00"}
        output = self.root/"bad_result"
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, "do not reproduce"):
            run_field(bad, output, self.model, self.bootstrap, self.model_hash, plots=False)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
