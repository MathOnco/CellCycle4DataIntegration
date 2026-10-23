"""Measure and classify arbitrary FoFs with the accepted, fixed reporter rules."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import ndimage

from .data import sha256, write_json
from .local_calibration import local_masks, pixel_stats, aggregate_features
from .neither_refinement import classify
from .reporter_inputs import preflight, match_components, read_plane
from force_fucci_fof5_reporter_states import nearest_reference

SCRIPTS = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = Path(__file__).parent/"models/fof5_neither_v1.json"
STATES = ["green_only", "red_only", "both", "neither"]


def load_model(path=DEFAULT_MODEL):
    path = Path(path).resolve()
    model = json.loads(path.read_text())
    if model.get("schema_version") != 1 or model.get("method") != "original_then_neither_to_both":
        raise ValueError("Unsupported reporter model schema or method")
    classify([], [], model["thresholds"])
    for relative, expected in model["locked_code_sha256"].items():
        if sha256(SCRIPTS/relative) != expected:
            raise ValueError(f"Accepted classification/measurement helper changed: {relative}")
    bootstrap_path = path.parent/model["bootstrap_file"]
    if sha256(bootstrap_path) != model["bootstrap_sha256"]:
        raise ValueError("Bootstrap threshold file changed")
    bootstrap = pd.read_csv(bootstrap_path)
    if len(bootstrap) != 500 or bootstrap.replicate.duplicated().any():
        raise ValueError("Expected 500 distinct frozen calibration bootstrap fits")
    return model, bootstrap, sha256(path)


def implementation_hashes():
    # All imported local modules are included: resuming cannot silently mix code versions.
    return {str(p.relative_to(SCRIPTS)): sha256(p) for p in sorted(SCRIPTS.rglob("*.py"))}


def measure(frame, mask, components, units, files, provenance):
    ids = set(units.geometry_id.astype(int))
    expected_hash = {(r["channel"], r["z"]): r["sha256"] for r in provenance["image_files"]}
    volumes = np.bincount(components.ravel())
    sums = {c: np.zeros(len(volumes), float) for c in files}
    rows, display, samples = [], {}, {c: [] for c in files}
    display_z = len(mask)//2
    for z in range(len(mask)):
        raw = {}
        for c, paths in files.items():
            if sha256(paths[z]) != expected_hash[(c, z)]: raise ValueError(f"Image changed during run: {paths[z]}")
            raw[c] = read_plane(paths[z], mask.shape[1:])
            sums[c] += np.bincount(components[z].ravel(), weights=raw[c].ravel(), minlength=len(volumes))
            samples[c].append(raw[c][::16, ::16].ravel())
            if z == display_z: display[c] = raw[c]
        geometry = components[z]
        boxes = ndimage.find_objects(geometry)
        for obj in sorted(ids.intersection(np.unique(geometry))):
            region = tuple(slice(max(0, b.start-21), min(size, b.stop+21))
                           for b, size in zip(boxes[obj-1], geometry.shape))
            foreground, rings = local_masks(geometry[region], mask[z][region], obj)
            for c in files:
                image = raw[c][region]
                row = {"geometry_id": obj, "z": z, "channel": c}
                for name, pixels in foreground.items():
                    row.update({f"{name}_{k}": v for k, v in pixel_stats(image[pixels]).items()})
                for name, pixels in rings.items():
                    row.update({f"{name}_{k}": v for k, v in pixel_stats(image[pixels], background=True).items()})
                rows.append(row)
        if (z+1) % 10 == 0 or z+1 == len(mask):
            print(f"  measured {z+1}/{len(mask)} planes", flush=True)
    checks = []
    component_ids = frame.ObjectNumber.to_numpy(int)
    for c in files:
        observed = sums[c][component_ids]/volumes[component_ids]
        source_mean = frame[f"Intensity_MeanIntensity_{c}"].to_numpy(float)
        source_sum = frame[f"Intensity_IntegratedIntensity_{c}"].to_numpy(float)
        means_ok = np.isclose(observed, source_mean, rtol=2e-5, atol=5e-7)
        sums_ok = np.isclose(sums[c][component_ids], source_sum, rtol=2e-5, atol=5e-7)
        if not (means_ok.all() and sums_ok.all()):
            raise ValueError(f"{c} images do not reproduce the table's component means/sums; check channels, scaling and alignment")
        checks.append(pd.DataFrame({"ObjectNumber": component_ids, "CellposeLabel": frame.CellposeLabel.to_numpy(),
            "channel": c, "table_mean": source_mean, "image_mean": observed,
            "absolute_mean_error": abs(observed-source_mean), "table_sum": source_sum,
            "image_sum": sums[c][component_ids], "mean_matches": means_ok, "sum_matches": sums_ok}))
    limits = {}
    for c in files:
        values = np.concatenate(samples[c])
        low, high = np.quantile(values, [.01, .998])
        if high <= low: low, high = float(values.min()), float(values.max())
        limits[c] = {"low": float(low), "high": float(max(high, low+1/65535))}
    return pd.DataFrame(rows), pd.concat(checks, ignore_index=True), display, limits


def primary_calls(units, features, mask, components, files, thresholds):
    data = units.copy()
    for c in files:
        f = features[features.variant.eq("primary") & features.channel.eq(c)].set_index("geometry_id")
        for column in ["mean_excess", "valid_voxels", "valid_planes", "max_plane_area", "reference_coverage"]:
            data[f"{c}_{column}"] = data.geometry_id.map(f[column])
        data[f"forced_{c}_score"] = data[f"{c}_mean_excess"]
    missing = ~np.isfinite(data[["forced_green_score", "forced_red_score"]]).all(axis=1)
    fallback_rows = []
    for index, row in data[missing].iterrows():
        obj = int(row.geometry_id)
        zs = np.flatnonzero(np.any(components == obj, axis=(1, 2)))
        current = []
        for z in zs:
            foreground = components[z] == obj
            reference, radius = nearest_reference(components[z], mask[z], obj)
            for c in files:
                image = read_plane(files[c][z], mask.shape[1:])
                foreground_mean = float(np.mean(image[foreground], dtype=np.float64))
                background = float(np.median(image[reference]))
                current.append({"geometry_id": obj, "CellposeLabel": int(row.CellposeLabel), "channel": c,
                    "z": int(z), "foreground_n": int(foreground.sum()), "reference_n": int(reference.sum()),
                    "reference_outer_radius_pixels": radius, "foreground_mean": foreground_mean,
                    "reference_median": background, "mean_excess": foreground_mean-background})
        fallback_rows.extend(current)
        for c in files:
            if not np.isfinite(row[f"forced_{c}_score"]):
                selected = [r for r in current if r["channel"] == c]
                data.loc[index, f"forced_{c}_score"] = np.average([r["mean_excess"] for r in selected], weights=[r["foreground_n"] for r in selected])
    data["forced_reference_fallback"] = missing
    final, original, promoted = classify(data.forced_green_score, data.forced_red_score, thresholds)
    data["original_reporter_state"], data["reporter_state"], data["refinement_promoted"] = original, final, promoted
    for c in files:
        data[f"{c}_call"] = np.where(data.reporter_state.isin([f"{c}_only", "both"]), "positive", "not_detected")
        data[f"{c}_high_margin"] = data[f"forced_{c}_score"]-thresholds[c]["high"]
        data[f"{c}_low_margin"] = data[f"forced_{c}_score"]-thresholds[c]["low"]
    return data, pd.DataFrame(fallback_rows, columns=["geometry_id", "CellposeLabel", "channel", "z", "foreground_n", "reference_n", "reference_outer_radius_pixels", "foreground_mean", "reference_median", "mean_excess"])


def sensitivity(data, features, thresholds, bootstrap, out):
    variant_rows, counts = [], []
    for variant, frame in features.groupby("variant", sort=False):
        scores = frame.pivot(index="geometry_id", columns="channel", values="mean_excess").reindex(data.geometry_id)
        if variant == "primary":
            scores.loc[:, "green"] = data.forced_green_score.to_numpy()
            scores.loc[:, "red"] = data.forced_red_score.to_numpy()
        available = np.isfinite(scores[["green", "red"]]).all(axis=1).to_numpy()
        final, original = np.full(len(data), "", object), np.full(len(data), "", object)
        final[available], original[available], _ = classify(scores.green.to_numpy()[available], scores.red.to_numpy()[available], thresholds)
        agree = available & (final == data.reporter_state.to_numpy())
        variant_rows.append(pd.DataFrame({"unit_id": data.unit_id, "geometry_id": data.geometry_id,
            "variant": variant, "green_score": scores.green.to_numpy(), "red_score": scores.red.to_numpy(),
            "available": available, "original_reporter_state": original, "reporter_state": final,
            "agrees_with_primary": agree}))
        counts.append({"variant": variant, "available_n": int(available.sum()), "missing_n": int((~available).sum()),
            "changed_n": int((available & ~agree).sum()),
            "original_stage_changes_vs_primary_n": int((available & (original != data.original_reporter_state.to_numpy())).sum()),
            **{f"{s}_n": int((final == s).sum()) for s in STATES}})
    variants = pd.concat(variant_rows, ignore_index=True)
    variants.to_csv(out/"variant_reporter_states.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    pd.DataFrame(counts).to_csv(out/"measurement_stability.csv", index=False)
    by = variants.groupby("unit_id")
    data["refinement_available_variants"] = data.unit_id.map(by.available.sum()).astype(int)
    data["refinement_agreeing_variants"] = data.unit_id.map(by.agrees_with_primary.sum()).astype(int)
    data["refinement_stable_all_11_measurements"] = data.refinement_available_variants.eq(11) & data.refinement_agreeing_variants.eq(11)
    for mode in ["bootstrap", "grid"]:
        models = []
        if mode == "bootstrap":
            models = [(row.replicate, row.green_low, row.red_low) for row in bootstrap.itertuples()]
        else:
            models = [(f"{g:.2f}/{r:.2f}", min(thresholds["green"]["low"]*g, thresholds["green"]["high"]),
                       min(thresholds["red"]["low"]*r, thresholds["red"]["high"]))
                      for g in np.linspace(.8, 1.2, 9) for r in np.linspace(.8, 1.2, 9)]
        agreements, totals = np.zeros(len(data), int), []
        for replicate, lg, lr in models:
            t = {"green": {**thresholds["green"], "low": lg}, "red": {**thresholds["red"], "low": lr}}
            final, _, promoted = classify(data.forced_green_score, data.forced_red_score, t)
            agreements += final == data.reporter_state.to_numpy()
            totals.append({"replicate": replicate, "green_low": lg, "red_low": lr, "promoted_n": int(promoted.sum()),
                           **{f"{s}_n": int((final == s).sum()) for s in STATES}})
        data[f"refinement_{mode}_agreement"] = agreements/len(models)
        pd.DataFrame(totals).to_csv(out/f"{mode}_counts.csv", index=False)
    return data


def run_field(spec, output, model, bootstrap, model_hash, resume=False, plots=True):
    output = Path(output).resolve()
    print(f"{spec.get('folder', 'dataset')}/{spec['date']}/{spec['fof']}", flush=True)
    frame, mask, files, provenance = preflight(spec)
    environment = {"python": platform.python_version(), **{p: importlib.metadata.version(p) for p in
        ["numpy", "pandas", "scipy", "matplotlib", "tifffile", "scikit-image", "Pillow"]}}
    signature = {"inputs": provenance, "model_sha256": model_hash, "code_sha256": implementation_hashes(),
                 "field_id": frame.field_id.iloc[0], "plots": plots, "environment": environment}
    fingerprint = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
    if output.exists():
        if not resume: raise ValueError(f"Output exists: {output}; use a new directory or --resume")
        previous = json.loads((output/"run.json").read_text())
        if previous.get("fingerprint") != fingerprint: raise ValueError("Inputs, code, model or plot settings changed; use a new output directory")
        for name, expected in previous["artifact_sha256"].items():
            if sha256(output/name) != expected: raise ValueError(f"Saved output changed: {name}")
        print("  verified existing result; resumed", flush=True)
        return previous["summary"]
    components, units = match_components(frame, mask)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".fucci-", dir=output.parent) as temp:
        work = Path(temp)/"result"; work.mkdir()
        measured, checks, display, limits = measure(frame, mask, components, units, files, provenance)
        features = aggregate_features(measured)
        measured.to_csv(work/"plane_measurements.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
        features.to_csv(work/"measurement_variants.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
        checks.to_csv(work/"component_image_measurement_checks.csv", index=False)
        data, fallback = primary_calls(units, features, mask, components, files, model["thresholds"])
        fallback.to_csv(work/"fallback_measurements.csv", index=False)
        data = sensitivity(data, features, model["thresholds"], bootstrap, work)
        data["model_id"] = model["model_id"]
        data.to_csv(work/"cell_reporter_states.csv", index=False)
        transition = pd.crosstab(data.original_reporter_state, data.reporter_state).reindex(index=STATES, columns=STATES, fill_value=0)
        transition.to_csv(work/"original_to_refined.csv")
        component_map = frame[["Date", "FoF", "ObjectNumber", "CellposeLabel", "AreaShape_Volume", "field_id"]].copy()
        component_map["selected_dominant_component"] = component_map.ObjectNumber.isin(units.ObjectNumber)
        component_map["unit_id"] = component_map.field_id+"/mask_"+component_map.CellposeLabel.astype(str)
        component_map.to_csv(work/"component_to_label.csv", index=False)
        if plots:
            from .reporter_plots import render
            render(data, components[len(mask)//2], display, limits, model["thresholds"], len(mask)//2, work)
        summary = {"field_id": data.field_id.iloc[0], "n": len(data), "source_components_n": len(frame),
            "counts": {s: int(data.reporter_state.eq(s).sum()) for s in STATES},
            "original_counts": {s: int(data.original_reporter_state.eq(s).sum()) for s in STATES},
            "promoted_n": int(data.refinement_promoted.sum()), "fallback_n": int(data.forced_reference_fallback.sum()),
            "measurement_complete_n": int(data.refinement_available_variants.eq(11).sum()),
            "measurement_stable_all_n": int(data.refinement_stable_all_11_measurements.sum()),
            "max_image_mean_error": float(checks.absolute_mean_error.max()),
            "interpretation": "Fixed thresholds calibrated on 241016/FoF5; transfer to other fields is unvalidated. Reporter states, not independently validated cell-cycle phases."}
        write_json(work/"model.json", model)
        bootstrap.to_csv(work/"calibration_bootstrap_thresholds.csv", index=False)
        write_json(work/"run.json", {**signature, "fingerprint": fingerprint, "summary": summary,
            "display_limits": limits,
            "artifact_sha256": {p.name: sha256(p) for p in sorted(work.iterdir())}})
        work.rename(output)
    print(f"  {len(data)} labels: {summary['counts']}", flush=True)
    return summary
