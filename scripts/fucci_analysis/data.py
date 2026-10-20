"""Read immutable exports, reproduce gates, and audit their segmentation units."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd

PHASES = np.array(["G1S", "G1", "S", "G2M"])
STATES = ["low_low", "high_low", "low_high", "high_high"]
ALIASES = {
    "AreaShape_Volume": "volume",
    "AreaShape_Center_X": "x", "AreaShape_Center_Y": "y", "AreaShape_Center_Z": "z",
    "Intensity_MeanIntensity_green": "green", "Intensity_MeanIntensity_red": "red",
    "Intensity_IntegratedIntensity_green": "green_sum", "Intensity_IntegratedIntensity_red": "red_sum",
    "Intensity_MedianIntensity_green": "green_median", "Intensity_MedianIntensity_red": "red_median",
    "Intensity_MaxIntensity_green": "green_max", "Intensity_MaxIntensity_red": "red_max",
    "SignalCore_MeanIntensity_green": "green_core", "SignalCore_MeanIntensity_red": "red_core",
    "SignalCore_Volume": "core_volume",
    "SignalCore_PercentObjectVolume": "core_fraction",
    **{f"AreaShape_BoundingBox{side}_{axis}": f"{axis.lower()}_{short}"
       for side, short in [("Minimum", "min"), ("Maximum", "max")] for axis in "XYZ"},
}
IDENTIFIERS = ["Date", "FoF", "CellID", "ObjectNumber", "CellposeLabel", "ImageSet", "FileName_mask"]


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, allow_nan=False, default=str) + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def gates(green, red, green_gate, red_gate) -> np.ndarray:
    """Exactly reproduce R's strict comparisons, including its default state."""
    return np.select([(green > green_gate) & (red < red_gate),
                      (green < green_gate) & (red > red_gate),
                      (green > green_gate) & (red > red_gate)], [1, 2, 3], default=0)


def gate_coordinates(frame: pd.DataFrame, columns=("green", "red")) -> np.ndarray:
    return np.log10(frame[list(columns)].to_numpy(float) /
                   frame[["green_gate", "red_gate"]].to_numpy(float))


def validate_resume_inputs(config: dict, out: Path, stage: str) -> None:
    """Reject stale model reuse before rewriting any provenance or measurements."""
    if stage in ["all", "audit"]:
        return
    source = out / "prediction_provenance.json"
    if stage == "fit" or not source.exists():
        source = out / "input_manifest.json"
    if not source.exists():
        raise ValueError("Run --stage audit (then fit) or --stage all before resuming")
    previous = json.loads(source.read_text())
    if sha256(Path(config["archive"]).expanduser()) != previous["archive_sha256"]:
        raise ValueError("Input archive changed; run --stage all to regenerate dependent artifacts")
    if stage in ["review", "report"]:
        ignored = {"archive", "review_objects_per_field"}
        expected = {k: v for k, v in previous["config"].items() if k not in ignored}
        current = {k: v for k, v in config.items() if k not in ignored}
        if current != expected:
            raise ValueError("Analysis configuration changed; rerun --stage fit or --stage all before review/report")


def validate_saved_labels(current: pd.DataFrame, saved: pd.DataFrame) -> None:
    """Confirm that reused calls describe exactly the current measurement units."""
    if not saved.mask_label_id.is_unique or set(current.mask_label_id) != set(saved.mask_label_id):
        raise ValueError("Saved predictions do not cover the current mask labels exactly")
    a = current.set_index("mask_label_id")
    b = saved.set_index("mask_label_id").loc[a.index]
    for column in ["volume", "green", "red", "green_gate", "red_gate", "n_components"]:
        np.testing.assert_allclose(a[column], b[column], rtol=1e-12, atol=1e-15,
                                   err_msg=f"Saved prediction measurements differ: {column}")
    probabilities = saved[[f"p_{s}" for s in STATES]].to_numpy()
    held_out = saved[[f"oof_p_{s}" for s in STATES]].to_numpy()
    for scores in [probabilities, held_out]:
        if not np.isfinite(scores).all() or (scores < 0).any() or (scores > 1).any():
            raise ValueError("Invalid saved reporter probabilities")
        np.testing.assert_allclose(scores.sum(axis=1), 1, atol=1e-10)


def check_result_artifacts(objects: pd.DataFrame, labels: pd.DataFrame, out: Path) -> dict:
    """Check persisted exports against source rows rather than trusting row counts alone."""
    columns = ["object_id", "mask_label_id", "cellCycle", "volume", "green", "red"]
    scores = [f"p_{state}" for state in STATES]
    predicted = pd.read_csv(out / "object_predictions.csv.gz", usecols=columns + scores)
    mapping = pd.read_csv(out / "object_mapping.csv.gz")
    for frame in [predicted, mapping]:
        if len(frame) != len(objects) or not frame.object_id.is_unique:
            raise ValueError("Object export lost or duplicated source rows")
        expected = objects.set_index("object_id").loc[frame.object_id]
        for column in ["object_id", "mask_label_id", "cellCycle"]:
            values = expected.index if column == "object_id" else expected[column]
            np.testing.assert_array_equal(frame[column], values)
    np.testing.assert_allclose(predicted[["volume", "green", "red"]],
                               objects.set_index("object_id").loc[predicted.object_id, ["volume", "green", "red"]],
                               rtol=1e-12, atol=1e-15)
    parents = labels.set_index("mask_label_id").loc[predicted.mask_label_id]
    np.testing.assert_allclose(predicted[scores], parents[scores], rtol=1e-12, atol=1e-15)
    np.testing.assert_array_equal(mapping.groupby("mask_label_id").size().sort_index(),
                                  labels.set_index("mask_label_id").n_components.sort_index())
    np.testing.assert_allclose(mapping.groupby("mask_label_id").volume.sum().sort_index(),
                               labels.set_index("mask_label_id").volume.sort_index())
    for filename, group_column in [("held_out_fields.csv", "field_id"), ("held_out_acquisitions.csv", "Date")]:
        holdouts = pd.read_csv(out / filename, dtype={"held_out": str})
        if holdouts.duplicated(["held_out", "model"]).any():
            raise ValueError("Duplicate evaluation folds")
        expected_groups = set(labels[group_column])
        for model in ["joint", "independent"]:
            subset = holdouts[holdouts.model == model]
            if set(subset.held_out) != expected_groups:
                raise ValueError("Incomplete grouped evaluation")
            counts = labels.groupby(group_column).size().reindex(subset.held_out)
            np.testing.assert_array_equal(subset.test_labels, counts)
            np.testing.assert_array_equal(subset.train_labels + subset.test_labels, len(labels))
    plotted = pd.read_csv(out / "scatter_field_index.csv")
    if plotted.field_id.duplicated().any() or set(plotted.field_id) != set(labels.field_id):
        raise ValueError("Scatter atlas does not cover every field exactly once")
    np.testing.assert_array_equal(plotted.plotted_mask_labels,
                                  labels.groupby("field_id").size().reindex(plotted.field_id))
    disposition = pd.read_csv(out / "disposition_by_fof.csv")
    count_columns = [c for c in disposition if c.endswith("_count")]
    np.testing.assert_array_equal(disposition[count_columns].sum(axis=1), disposition.denominator_mask_labels)
    if int(disposition.denominator_mask_labels.sum()) != len(labels):
        raise ValueError("Disposition denominators do not preserve every mask label")
    result = {"all_checks_passed": True, "source_objects_checked": len(objects),
              "mask_labels_checked": len(labels), "plotted_fields_checked": len(plotted),
              "source_identity_and_phase_preserved": True, "source_intensities_preserved": True,
              "object_to_mask_label_mapping_verified": True, "parent_probabilities_verified": True,
              "all_grouped_holdouts_present": True, "mutually_exclusive_disposition_totals_verified": True,
              "interpretation": "Computational consistency checks, not independent biological validation"}
    write_json(out / "artifact_checks.json", result)
    return result


def load_inputs(config: dict, out: Path) -> tuple[pd.DataFrame, dict]:
    archive_path = Path(config["archive"]).expanduser().resolve()
    frames, tables = [], []
    with ZipFile(archive_path) as archive:
        for folder in config["folders"]:
            name = f"{folder}/object_features_new.csv"
            label_name = f"{folder}/object_features_new_withCellCycle.csv"
            with archive.open(name) as f:
                schema = pd.read_csv(f, nrows=0).columns.tolist()
            with archive.open(name) as f:
                df = pd.read_csv(f, usecols=IDENTIFIERS + list(ALIASES),
                                 dtype={c: str for c in IDENTIFIERS})
            with archive.open(label_name) as f:
                supplied = pd.read_csv(f, usecols=["Date", "FoF", "CellID", "cellCycle",
                    "Intensity_MeanIntensity_green", "Intensity_MeanIntensity_red"],
                    dtype={c: str for c in ["Date", "FoF", "CellID"]})
            keys = ["Date", "FoF", "CellID"]
            if df.duplicated(keys).any() or supplied.duplicated(keys).any():
                raise ValueError(f"Duplicate object identity in {folder}")
            supplied = supplied.rename(columns={"Intensity_MeanIntensity_green": "check_green",
                                                "Intensity_MeanIntensity_red": "check_red"})
            df = df.merge(supplied, on=keys, how="outer", validate="one_to_one", indicator=True)
            if not df._merge.eq("both").all():
                raise ValueError(f"Raw and supplied-label identities differ in {folder}")
            df = df.drop(columns="_merge").rename(columns=ALIASES)
            np.testing.assert_allclose(df[["green", "red"]], df[["check_green", "check_red"]],
                                       rtol=1e-12, atol=1e-15)
            df = df.drop(columns=["check_green", "check_red"])
            df["folder"] = folder
            df["green_gate"], df["red_gate"], df["excluded_red_upper"] = config["thresholds"][folder]
            df["baseline_state"] = gates(df.green, df.red, df.green_gate, df.red_gate)
            if not np.array_equal(PHASES[df.baseline_state], df.cellCycle):
                raise ValueError(f"Baseline fails to reproduce supplied labels in {folder}")
            df["github_exclusion_rule"] = ((df.baseline_state == 3) &
                (df.red > df.red_gate) & (df.red <= df.excluded_red_upper))
            digest = hashlib.sha256()
            with archive.open(name) as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    digest.update(chunk)
            tables.append({"member": name, "rows": len(df), "columns": len(schema),
                           "column_names": schema, "sha256": digest.hexdigest(),
                           "labeled_member": label_name, "label_mismatches": 0,
                           "github_rule_flagged": int(df.github_exclusion_rule.sum())})
            frames.append(df)
    objects = pd.concat(frames, ignore_index=True)
    objects["field_id"] = objects.Date + "/" + objects.FoF
    objects["object_id"] = objects.field_id + "/" + objects.CellID
    objects["mask_label_id"] = objects.field_id + "/mask_" + objects.CellposeLabel
    objects["tiny_object"] = objects.volume <= config["tiny_volume_diagnostic"]
    objects["valid_signal"] = np.isfinite(objects[["green", "red"]]).all(axis=1) & (objects[["green", "red"]] > 0).all(axis=1)
    objects["saturated_voxel"] = (objects[["green_max", "red_max"]] >= 1).any(axis=1)
    objects["components_in_mask_label"] = objects.groupby("mask_label_id").object_id.transform("size")
    objects["repeated_mask_label"] = objects.components_in_mask_label > 1
    assert objects.object_id.is_unique and len(objects) == config["expected_rows"]
    assert objects.field_id.nunique() == config["expected_fields"]
    if not objects.valid_signal.all() or (objects.volume <= 0).any():
        raise ValueError("Invalid measurements require explicit handling; rows were not dropped")
    # Check that sums and means describe the same voxel support before aggregation.
    for channel in ["green", "red"]:
        np.testing.assert_allclose(objects[f"{channel}_sum"], objects[channel] * objects.volume,
                                   rtol=2e-6, atol=1e-5)
    versions = {p: importlib.metadata.version(p) for p in
                ["numpy", "pandas", "scipy", "matplotlib", "tifffile", "scikit-image", "Pillow"]}
    manifest = {"archive": str(archive_path), "archive_sha256": sha256(archive_path),
                "tables": tables, "objects": len(objects), "fields": objects.field_id.nunique(),
                "acquisitions": sorted(objects.Date.unique()), "config": config,
                "package_versions": versions, "no_rows_removed": True}
    write_json(out / "input_manifest.json", manifest)
    objects.groupby(["folder", "Date", "FoF", "cellCycle"]).size().rename("objects").to_csv(out / "baseline_counts.csv")
    return objects, manifest


def aggregate_mask_labels(objects: pd.DataFrame) -> pd.DataFrame:
    """Reconstruct exact mean/sum/volume measurements over the exported label support.

    A source mask label is not asserted to be a validated biological nucleus.
    Medians and percentile cores are retained only for the largest component.
    """
    by = objects.groupby("mask_label_id", sort=False)
    labels = by[["volume", "green_sum", "red_sum"]].sum()
    labels["green"] = labels.green_sum / labels.volume
    labels["red"] = labels.red_sum / labels.volume
    for name in ["folder", "Date", "FoF", "field_id", "ImageSet", "FileName_mask", "CellposeLabel", "green_gate", "red_gate"]:
        labels[name] = by[name].first()
    labels["n_components"] = by.size()
    labels["n_tiny_components"] = by.tiny_object.sum()
    labels["all_components_tiny"] = labels.n_components == labels.n_tiny_components
    labels["saturated_voxel"] = by.saturated_voxel.any()
    labels["largest_component_fraction"] = by.volume.max() / labels.volume
    for axis in "xyz":
        weighted = (objects[axis] * objects.volume).groupby(objects.mask_label_id).sum()
        labels[axis] = weighted / labels.volume
        labels[f"{axis}_min"] = by[f"{axis}_min"].min()
        labels[f"{axis}_max"] = by[f"{axis}_max"].max()
    largest = objects.loc[by.volume.idxmax()].set_index("mask_label_id")
    for name in ["object_id", "green", "red", "green_median", "red_median", "green_core", "red_core", "x", "y", "z"]:
        labels[f"largest_{name}"] = largest[name]
    labels["baseline_state"] = gates(labels.green, labels.red, labels.green_gate, labels.red_gate)
    labels["baseline_phase"] = PHASES[labels.baseline_state]
    labels = labels.reset_index()
    np.testing.assert_allclose(labels[["volume", "green_sum", "red_sum"]].sum(),
                               objects[["volume", "green_sum", "red_sum"]].sum(), rtol=1e-12)
    return labels


def training_weights(frame: pd.DataFrame, object_level=False) -> np.ndarray:
    """Equal total field weight; siblings share their original mask label's weight."""
    if object_level:
        counts = frame.groupby("mask_label_id").mask_label_id.transform("size")
        n_labels = frame.groupby("field_id").mask_label_id.transform("nunique")
        weights = 1 / (counts * n_labels)
    else:
        weights = 1 / frame.groupby("field_id").field_id.transform("size")
    return np.asarray(weights / weights.mean(), float)


def audit_units(objects: pd.DataFrame, labels: pd.DataFrame, out: Path) -> None:
    rows = []
    for field_id, subset in objects.groupby("field_id"):
        parent = labels[labels.field_id == field_id]
        rows.append({"field_id": field_id, "folder": subset.folder.iloc[0],
                     "objects": len(subset), "mask_labels": len(parent),
                     "tiny_objects": int(subset.tiny_object.sum()),
                     "tiny_object_percent": 100 * subset.tiny_object.mean(),
                     "multi_component_labels": int((parent.n_components > 1).sum()),
                     "all_tiny_labels": int(parent.all_components_tiny.sum()),
                     "median_object_volume": subset.volume.median(),
                     "median_mask_label_volume": parent.volume.median(),
                     "median_largest_component_fraction": parent.largest_component_fraction.median()})
    pd.DataFrame(rows).to_csv(out / "segmentation_audit_by_fof.csv", index=False)
    labels.to_csv(out / "mask_label_measurements.csv.gz", index=False,
                  compression={"method": "gzip", "mtime": 0})
    objects[["object_id", "mask_label_id", "Date", "FoF", "CellID", "ObjectNumber",
             "CellposeLabel", "volume", "tiny_object", "components_in_mask_label", "cellCycle",
             "github_exclusion_rule"]].to_csv(out / "object_mapping.csv.gz", index=False,
                                             compression={"method": "gzip", "mtime": 0})


def image_inventory(objects: pd.DataFrame, labels: pd.DataFrame, repo: Path, out: Path,
                    downloads: Path | None = None) -> pd.DataFrame:
    """Validate locally available original masks using per-label voxel counts."""
    import tifffile
    from skimage import measure
    downloads = downloads or Path.home() / "Downloads"
    inventory = []
    for field_id, subset in objects.groupby("field_id"):
        stem = subset.ImageSet.iloc[0]
        image_dir = repo / "data4paper/A01_rawData" / stem
        mask_candidates = [downloads / subset.FileName_mask.iloc[0],
                           repo / "data4paper/A04_CellposeOutput" / stem / subset.FileName_mask.iloc[0]]
        mask_path = next((p for p in mask_candidates if p.is_file()), None)
        row = {"field_id": field_id, "image_dir": str(image_dir) if image_dir.is_dir() else "",
               "raw_images_available": image_dir.is_dir(), "mask_path": str(mask_path or ""),
               "mask_volumes_match": False, "mask_components_match": False,
               "image_measurements_checked": False, "image_measurements_match": False,
               "image_measurements_compared": 0, "calibration_ready": False}
        if image_dir.is_dir():
            row["metadata_files"] = len(list(image_dir.rglob("*.xml")))
            row["green_planes"] = len(list(image_dir.glob("*_ch00.tif")))
            row["red_planes"] = len(list(image_dir.glob("*_ch02.tif")))
        if mask_path:
            mask = tifffile.imread(mask_path)
            counts = np.bincount(mask.ravel())
            parent = labels[labels.field_id == field_id]
            expected_ids = parent.CellposeLabel.astype(int).to_numpy()
            row["mask_volumes_match"] = bool(np.array_equal(np.flatnonzero(counts)[1:] if counts[0] else np.flatnonzero(counts),
                                                           np.sort(expected_ids)) and
                np.array_equal(counts[expected_ids], parent.volume.to_numpy()))
            components = measure.label(mask, background=0, connectivity=3)
            volumes = np.bincount(components.ravel())
            numbers = subset.ObjectNumber.astype(int).to_numpy()
            row["mask_components_match"] = bool(components.max() == len(subset) and
                numbers.max() < len(volumes) and np.array_equal(volumes[numbers], subset.volume.to_numpy()))
            row["mask_sha256"] = sha256(mask_path)
            del mask, components
        inventory.append(row)
    result = pd.DataFrame(inventory)
    result.to_csv(out / "image_inventory.csv", index=False)
    return result
