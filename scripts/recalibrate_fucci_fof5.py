#!/usr/bin/env python3
"""Reproducible FoF5 local-background reporter calibration; phase mapping is conditional."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import ndimage

from plot_fucci_spatial_verification import read_sources, build_policies, stretch, selected_boundaries
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from fucci_analysis.data import sha256, write_json
from fucci_analysis.review import normalized_plane, planes
from fucci_analysis.outputs import save, PHASE_COLORS
from fucci_analysis.local_calibration import (
    CHANNELS, FEATURES, VARIANTS, STATE_COLORS, measure_planes, aggregate_features,
    select_thresholds, apply_thresholds, reporter_state,
)

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "results/fucci_fof5_recalibration"
FIGS = REPO / "figs4paper/fucci_fof5_recalibration"
SEED = 20261021


def inputs(mask_archive):
    source, mask, components, predictions, image_dir, provenance = read_sources(REPO, mask_archive)
    policies, _ = build_policies(source, mask, components, predictions)
    units = policies["dominant"]["frame"].copy()
    manifest = json.loads((REPO/"results/fucci_spatial_verification/241016_5/image_mask_verification.json").read_text())
    if provenance["mask_member_sha256"] != manifest["mask_member_sha256"]:
        raise ValueError("Mask changed since verification")
    return units, mask, components, image_dir, provenance, manifest


def prepare(mask_archive):
    units, mask, components, image_dir, provenance, manifest = inputs(mask_archive)
    measured = measure_planes(mask, components, units, image_dir, manifest)
    measured.to_csv(OUT/"plane_measurements.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    features = aggregate_features(measured)
    features.to_csv(OUT/"measurement_variants.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    units.to_csv(OUT/"source_units.csv", index=False)
    write_json(OUT/"input_provenance.json", {"source": provenance, "display_limits": manifest["display_limits"],
        "image_files": manifest["image_files"], "checked_image_channels": list(CHANNELS),
        "minimum_reference_pixels_per_plane": 50, "negative_contrasts_clipped": False,
        "measurement_source_sha256": sha256(Path(__file__).parent/"fucci_analysis/local_calibration.py"),
        "script_sha256": sha256(Path(__file__))})
    if (OUT/"review_key.csv").exists():
        print("Existing review identities and annotations preserved", flush=True)
        return
    primary = features[features.variant.eq("primary")].pivot(index="geometry_id", columns="channel", values="mean_contrast")
    area = measured[measured.channel.eq("green")].groupby("geometry_id").original_n.max()
    eligible = units[units.volume.ge(1000) & ~units.CellposeLabel.isin([63, 410, 42, 220, 127, 16])].set_index("geometry_id")
    eligible = eligible.join(area.rename("max_area")).join(primary[["green", "red"]], rsuffix="_contrast")
    eligible = eligible[eligible.max_area.ge(100) & eligible.green_contrast.notna() & eligible.red_contrast.notna()]
    eligible["stratum"] = pd.qcut(eligible.green_contrast.rank(method="first"), 4, labels=False)*4 + pd.qcut(eligible.red_contrast.rank(method="first"), 4, labels=False)
    rng = np.random.default_rng(SEED)
    groups = {key: rng.permutation(g.index).tolist() for key, g in eligible.groupby("stratum")}
    sample = []
    while len(sample) < 48:
        for key in rng.permutation(list(groups)):
            if groups[key] and len(sample) < 48:
                sample.append(groups[key].pop())
    sample = rng.permutation(sample)
    key = eligible.loc[sample, ["CellposeLabel", "stratum"]].reset_index()
    key.insert(0, "review_id", [f"R{i+1:02}" for i in range(len(key))])
    key["split"] = ["calibration"]*32 + ["check"]*16
    key.to_csv(OUT/"review_key.csv", index=False)
    annotations = key[["review_id", "split"]].copy()
    for c in ["green", "red", "mask_review", "notes"]:
        annotations[c] = ""
    annotations["reviewer"] = "assistant_visual_review"
    annotations["experimental_ground_truth"] = False
    annotations.to_csv(OUT/"review_annotations.csv", index=False)
    write_json(OUT/"review_protocol.json", {
        "seed": SEED, "n": 48, "calibration_n": 32, "check_n": 16,
        "selection": "Round-robin sample from 4x4 quantile strata of preliminary local mean contrasts; random assignment to review splits",
        "minimum_volume": 1000, "minimum_max_plane_area": 100,
        "previously_discussed_labels_excluded": [63, 410, 42, 220, 127, 16],
        "review_labels_hidden": ["CellposeLabel", "old_phase", "new_prediction", "numeric_features"],
        "positive": "Coherent localized signal within the outline relative to neighboring regions across at least two displayed cross-sections",
        "not_detected": "No convincing localized signal across the displayed cross-sections, including fixed 4x display",
        "ambiguous": "Weak, inconsistent, overlapping, or spatially uncertain signal",
        "reviewer": "assistant; not an independent experimental or expert annotation",
        "prior_exposure": "Reviewer has seen this field and six excluded examples in prior analysis",
        "check_protocol": "Freeze feature and threshold choices before rendering/reviewing the check examples"})
    print("Prepared 578 units and 48 label-concealed review examples", flush=True)


def review_pages(mask_archive, split):
    if split == "check" and not (OUT/"frozen_calibration.json").exists():
        raise ValueError("Freeze calibration before opening check images")
    units, mask, components, image_dir, provenance, manifest = inputs(mask_archive)
    key = pd.read_csv(OUT/"review_key.csv")
    key = key[key.split.eq(split)]
    measured = pd.read_csv(OUT/"plane_measurements.csv.gz")
    measured = measured[measured.channel.eq("green")]
    files = {c: planes(image_dir, number) for c, number in {**CHANNELS, "bright": "01"}.items()}
    cache = {}
    metadata = []
    folder = FIGS/f"review_{split}"
    folder.mkdir(exist_ok=True)
    with PdfPages(FIGS/f"review_{split}.pdf") as pdf:
        for page, start in enumerate(range(0, len(key), 4), start=1):
            fig = plt.figure(figsize=(19, 12))
            outer = fig.add_gridspec(2, 2, left=.015, right=.99, bottom=.065, top=.92, wspace=.06, hspace=.12)
            for position, (_, item) in enumerate(key.iloc[start:start+4].iterrows()):
                obj = int(item.geometry_id)
                d = measured[measured.geometry_id.eq(obj)]
                peak = int(d.loc[d.original_n.idxmax(), "z"])
                substantial = d[d.original_n >= .35*d.original_n.max()].z.to_numpy(int)
                if len(substantial) < 3:
                    substantial = d.z.to_numpy(int)
                z_values = sorted(set(int(substantial[np.argmin(abs(substantial-target))]) for target in [peak-4, peak, peak+4]))
                if len(z_values) < 3:
                    z_values = sorted(set(z_values + list(substantial)))
                    z_values = [z_values[i] for i in [0, len(z_values)//2, len(z_values)-1]]
                xy = np.argwhere((components[z_values] == obj).any(axis=0))
                y0, x0 = np.maximum(xy.min(axis=0)-12, 0)
                y1, x1 = np.minimum(xy.max(axis=0)+13, components.shape[1:])
                region = (slice(y0, y1), slice(x0, x1))
                grid = outer[position//2, position%2].subgridspec(4, 6, height_ratios=[.18, 1, 1, 1], hspace=.05, wspace=.03)
                title = fig.add_subplot(grid[0, :]); title.axis("off")
                title.text(0, .5, f"{item.review_id} · planes {', '.join(map(str,z_values))}", fontsize=12, weight="bold")
                for row, z in enumerate(z_values, start=1):
                    for c in files:
                        if (c, z) not in cache:
                            path = files[c][z]
                            expected = next(v["sha256"] for v in manifest["image_files"] if v["channel"] == c and v["z"] == z)
                            if sha256(path) != expected: raise ValueError("Changed review image")
                            cache[(c, z)] = normalized_plane(path)
                    g, r, b = [stretch(cache[(c, z)][region], manifest["display_limits"][c]) for c in ["green", "red", "bright"]]
                    lookup = np.zeros(int(components.max())+1, dtype=np.uint8); lookup[obj] = 1
                    boundary = selected_boundaries(components[z][region], lookup)
                    images = [g, r, np.clip(4*g, 0, 1), np.clip(4*r, 0, 1), np.stack([r, g, np.zeros_like(g)], axis=-1), b]
                    titles = ["Green", "Red", "Green ×4", "Red ×4", "Merge", "Brightfield"]
                    for col, (plane, caption) in enumerate(zip(images, titles)):
                        ax = fig.add_subplot(grid[row, col])
                        rgb = np.repeat(plane[..., None], 3, axis=2) if plane.ndim == 2 else plane.copy()
                        rgb[boundary] = .25*rgb[boundary] + .75
                        ax.imshow(rgb, interpolation="nearest"); ax.axis("off")
                        if row == 1: ax.set_title(caption, fontsize=9, pad=3)
                metadata.append({"review_id": item.review_id, "split": split, "page": page,
                                 "z_indices": ";".join(map(str, z_values)), "x0": int(x0), "x1": int(x1), "y0": int(y0), "y1": int(y1)})
            fig.suptitle(f"FoF5 reporter image review · {split} set · page {page}\nOld labels, numeric scores and new predictions concealed", fontsize=15)
            fig.text(.5, .025, "Each channel: positive / not detected / ambiguous. Judge localized signal across slices; mark uncertain masks. Display ranges fixed across all examples.", ha="center", fontsize=10)
            pdf.savefig(fig)
            fig.savefig(folder/f"page_{page:02}.png", dpi=160, bbox_inches="tight", facecolor="white")
            plt.close(fig)
    pd.DataFrame(metadata).to_csv(OUT/f"review_{split}_display.csv", index=False)
    print(f"Review sheets: {folder}", flush=True)


def fit():
    if (OUT/"frozen_calibration.json").exists():
        raise ValueError("Calibration already frozen; preserve it for the separate check")
    annotations = pd.read_csv(OUT/"review_annotations.csv", keep_default_na=False)
    calibration = annotations[annotations.split.eq("calibration")]
    allowed = {"positive", "not_detected", "ambiguous"}
    if any(not set(calibration[c]).issubset(allowed) for c in CHANNELS):
        raise ValueError("Complete calibration image reviews first")
    if not set(calibration.mask_review).issubset({"usable", "questionable"}):
        raise ValueError("Complete mask reviews first")
    key = pd.read_csv(OUT/"review_key.csv")
    calibration = calibration.merge(key[["review_id", "geometry_id"]], on="review_id", validate="one_to_one")
    calibration.to_csv(OUT/"calibration_annotations_frozen.csv", index=False)
    features = pd.read_csv(OUT/"measurement_variants.csv.gz")
    models, comparisons = select_thresholds(features, calibration)
    comparisons.to_csv(OUT/"feature_comparison_calibration_only.csv", index=False)
    write_json(OUT/"frozen_calibration.json", {"models": models, "features_considered": FEATURES,
        "calibration_annotations_sha256": sha256(OUT/"calibration_annotations_frozen.csv"),
        "measurement_variants_sha256": sha256(OUT/"measurement_variants.csv.gz"),
        "selection": "Leave-one-cell-out balanced agreement with clear calibration image judgments; conservative specificity tie break",
        "uncertainty": "5th–95th percentiles of 500 stratified calibration-cell bootstrap thresholds",
        "stability": "All 11 prespecified measurement variants must agree for a resolved reporter-state call",
        "reviewed_mask_quality": "Flag reviewed questionable masks as unresolved in the delivered map; retain automatic calls before this flag and evaluate the check set before applying manual mask flags",
        "minimum_support": {"valid_voxels": 100, "valid_planes": 3, "largest_plane_pixels": 25, "reference_coverage": .8},
        "check_reviews_used": False, "old_phase_labels_used": False,
        "code_sha256": sha256(Path(__file__).parent/"fucci_analysis/local_calibration.py")})
    print(json.dumps(models, indent=2), flush=True)


def freeze_check():
    if not (OUT/"frozen_calibration.json").exists() or not (OUT/"review_check_display.csv").exists():
        raise ValueError("Freeze calibration and render check images first")
    annotations = pd.read_csv(OUT/"review_annotations.csv", keep_default_na=False)
    check = annotations[annotations.split.eq("check")]
    if len(check) != 16 or any(not set(check[c]).issubset({"positive", "not_detected", "ambiguous"}) for c in CHANNELS):
        raise ValueError("Complete all 16 check image judgments first")
    if not set(check.mask_review).issubset({"usable", "questionable"}) or check.notes.eq("").any():
        raise ValueError("Complete mask judgments and review notes first")
    key = pd.read_csv(OUT/"review_key.csv")
    check = check.merge(key[["review_id", "geometry_id"]], on="review_id", validate="one_to_one")
    path = OUT/"check_annotations_frozen.csv"
    if path.exists():
        pd.testing.assert_frame_equal(check, pd.read_csv(path, keep_default_na=False))
        print("Existing frozen check judgments verified; preserved", flush=True)
    else:
        check.to_csv(path, index=False)
        print("Check judgments frozen before scoring", flush=True)


def report(mask_archive):
    from fucci_analysis.local_calibration_outputs import evaluate_reviews, render_figures, write_report

    frozen = json.loads((OUT/"frozen_calibration.json").read_text())
    for filename, key in [("measurement_variants.csv.gz", "measurement_variants_sha256"),
                          ("calibration_annotations_frozen.csv", "calibration_annotations_sha256")]:
        if sha256(OUT/filename) != frozen[key]:
            raise ValueError(f"Frozen calibration input changed: {filename}")
    if sha256(Path(__file__).parent/"fucci_analysis/local_calibration.py") != frozen["code_sha256"]:
        raise ValueError("Calibration implementation changed after freezing")
    annotations = pd.read_csv(OUT/"review_annotations.csv", keep_default_na=False)
    key = pd.read_csv(OUT/"review_key.csv")
    annotations = annotations.merge(key[["review_id", "geometry_id"]], on="review_id", validate="one_to_one")
    for split in ["calibration", "check"]:
        reference = pd.read_csv(OUT/f"{split}_annotations_frozen.csv", keep_default_na=False)
        pd.testing.assert_frame_equal(annotations[annotations.split.eq(split)].reset_index(drop=True), reference)
    if len(annotations) != 48 or not annotations.geometry_id.is_unique:
        raise ValueError("Review identity or coverage changed")
    for c in CHANNELS:
        if not set(annotations[c]).issubset({"positive", "not_detected", "ambiguous"}):
            raise ValueError("Complete all image reviews before scoring")
    if not set(annotations.mask_review).issubset({"usable", "questionable"}):
        raise ValueError("Complete all mask reviews before scoring")

    units, mask, components, image_dir, provenance, manifest = inputs(mask_archive)
    pd.testing.assert_frame_equal(units.reset_index(drop=True), pd.read_csv(OUT/"source_units.csv"), check_dtype=False)
    features = pd.read_csv(OUT/"measurement_variants.csv.gz")
    primary, variants, scored = apply_thresholds(features, frozen["models"])
    if len(primary) != 578 or len(variants) != 578*len(VARIANTS):
        raise ValueError("Lost units or measurement variants")
    if set(primary.geometry_id) != set(units.geometry_id):
        raise ValueError("Input/output object mismatch")
    primary = primary.rename(columns={"green": "green_call", "red": "red_call", "reporter_state": "automatic_reporter_state"})
    results = units.merge(primary.drop(columns="variant"), on="geometry_id", validate="one_to_one")
    for c in CHANNELS:
        scores = scored[scored.channel.eq(c)]
        main = scores[scores.variant.eq("primary")].set_index("geometry_id")
        for name in ["score", "valid_voxels", "valid_planes", "max_plane_area", "reference_coverage", "reference_mean"]:
            results[f"{c}_{name}"] = results.geometry_id.map(main[name])
        calls = scores.pivot(index="geometry_id", columns="variant", values="channel_call")
        stable = calls.primary.where(calls.nunique(axis=1).eq(1), "unstable")
        results[f"{c}_stable_call"] = results.geometry_id.map(stable)
    reviewed = annotations.rename(columns={"green": "review_green", "red": "review_red", "notes": "review_notes"})
    results = results.merge(reviewed, on="geometry_id", how="left", validate="one_to_one")
    for c in ["review_id", "split", "review_green", "review_red", "mask_review", "review_notes", "reviewer"]:
        results[c] = results[c].fillna("unreviewed" if c != "review_notes" else "")
    results["experimental_ground_truth"] = False
    results["reporter_state"] = results.automatic_reporter_state
    questionable = results.mask_review.eq("questionable")
    results.loc[questionable, "reporter_state"] = "unresolved"
    results.loc[questionable, "unresolved_reasons"] = results.loc[questionable, "unresolved_reasons"].map(
        lambda value: ";".join(filter(None, [value, "reviewed_mask_questionable"])))
    missing_scores = ~np.isfinite(results[["green_score", "red_score"]]).all(axis=1)
    results.loc[missing_scores, "unresolved_reasons"] = results.loc[missing_scores, "unresolved_reasons"].map(
        lambda value: ";".join(filter(None, [value, "missing_local_reference"])))
    results["conditional_phase"] = results.reporter_state.map({"green_only": "G1_like", "red_only": "S_like", "both": "G2M_like", "unresolved": "unresolved"})
    reason_priority = ["reviewed_mask_questionable", "insufficient_measurement_support", "missing_local_reference",
                       "neither_reporter_detected", "threshold_uncertainty", "sensitive_to_measurement_choice"]
    results["primary_unresolved_reason"] = [next((reason for reason in reason_priority if reason in flags.split(";")), "")
                                            for flags in results.unresolved_reasons]
    if results.loc[results.reporter_state.eq("unresolved"), "primary_unresolved_reason"].eq("").any():
        raise ValueError("An unresolved result lacks a reason")
    results["visible_z35"] = results.geometry_id.isin(np.unique(components[35]))
    if results.reporter_state.isna().any() or len(results) != 578 or not results.CellposeLabel.is_unique:
        raise ValueError("Invalid all-label output")
    results.to_csv(OUT/"cell_reporter_states.csv", index=False)
    variants.to_csv(OUT/"variant_reporter_states.csv", index=False)
    scored.to_csv(OUT/"scored_measurement_variants.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})

    evaluation, review_rows = evaluate_reviews(results, frozen["models"])
    evaluation.to_csv(OUT/"review_agreement.csv", index=False)
    review_rows.to_csv(OUT/"review_predictions.csv", index=False)
    rows = []
    for scope, selected in [("full_stack", results), ("z35_intersections", results[results.visible_z35])]:
        for method in ["baseline_phase", "provisional_phase", "reporter_state_before_stability", "automatic_reporter_state", "reporter_state"]:
            for category, count in selected[method].value_counts().items():
                rows.append({"scope": scope, "method": method, "category": category, "n": int(count), "denominator": len(selected), "fraction": float(count/len(selected))})
    counts = pd.DataFrame(rows)
    counts.to_csv(OUT/"classification_counts.csv", index=False)
    for previous in ["baseline_phase", "provisional_phase"]:
        pd.crosstab(results[previous], results.reporter_state).reindex(columns=STATE_COLORS, fill_value=0).to_csv(OUT/f"{previous}_to_reporter_state.csv")
    primary_states = primary.set_index("geometry_id").reporter_state_before_stability
    stability = []
    for variant in VARIANTS:
        d = variants[variants.variant.eq(variant)].set_index("geometry_id")
        changed = d.reporter_state.ne(primary_states.reindex(d.index))
        stability.append({"variant": variant, "changed_from_primary": int(changed.sum()), "n": len(d),
                          **{state: int(d.reporter_state.eq(state).sum()) for state in STATE_COLORS}})
    stability = pd.DataFrame(stability)
    stability.to_csv(OUT/"stability_summary.csv", index=False)
    reasons = results.loc[results.reporter_state.eq("unresolved"), "unresolved_reasons"].str.split(";").explode()
    summary = {"n": len(results), "visible_z35": int(results.visible_z35.sum()),
        "corrected_scatter_finite_n": int((~missing_scores).sum()),
        "corrected_scatter_missing_labels": results.loc[missing_scores, "CellposeLabel"].astype(int).tolist(),
        "final_counts": {k: int(results.reporter_state.eq(k).sum()) for k in STATE_COLORS},
        "z35_final_counts": {k: int((results.reporter_state.eq(k) & results.visible_z35).sum()) for k in STATE_COLORS},
        "primary_counts": {k: int(results.reporter_state_before_stability.eq(k).sum()) for k in STATE_COLORS},
        "automatic_stable_counts": {k: int(results.automatic_reporter_state.eq(k).sum()) for k in STATE_COLORS},
        "unresolved_reasons_nonexclusive": {str(k): int(v) for k, v in reasons[reasons.ne("")].value_counts().items()},
        "primary_unresolved_reasons_exclusive": {str(k): int(v) for k, v in results.loc[results.reporter_state.eq("unresolved"), "primary_unresolved_reason"].value_counts().items()},
        "review_counts": annotations.groupby(["split", "mask_review"]).size().rename("n").reset_index().to_dict("records"),
        "reviewed_questionable_n": int(questionable.sum()),
        "reviewed_mask_flag_changed_call_n": int((questionable & results.automatic_reporter_state.ne("unresolved")).sum()),
        "unreviewed_mask_n": int(results.mask_review.eq("unreviewed").sum()),
        "reproducibility": {"frozen_calibration_sha256": sha256(OUT/"frozen_calibration.json"),
                            "check_annotations_sha256": sha256(OUT/"check_annotations_frozen.csv"),
                            "annotations_sha256": sha256(OUT/"review_annotations.csv"),
                            "script_sha256": sha256(Path(__file__)),
                            "outputs_code_sha256": sha256(Path(__file__).parent/"fucci_analysis/local_calibration_outputs.py")},
        "phase_validated": False, "other_fields_calibrated": False}
    write_json(OUT/"summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    render_figures(results, variants, scored, review_rows, stability, frozen, components, image_dir, manifest, FIGS, OUT)
    write_report(REPO, results, evaluation, stability, summary, frozen)
    print(f"Report: {REPO/'docs/fucci_fof5_recalibration.md'}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["prepare", "review-calibration", "fit", "review-check", "freeze-check", "report"], required=True)
    parser.add_argument("--mask-archive", type=Path, default=Path.home()/"Downloads/FoF5_241016_fucci.nucleus.zip")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True); FIGS.mkdir(parents=True, exist_ok=True)
    if args.stage == "prepare": prepare(args.mask_archive)
    elif args.stage == "review-calibration": review_pages(args.mask_archive, "calibration")
    elif args.stage == "fit": fit()
    elif args.stage == "review-check": review_pages(args.mask_archive, "check")
    elif args.stage == "freeze-check": freeze_check()
    elif args.stage == "report": report(args.mask_archive)


if __name__ == "__main__":
    main()
