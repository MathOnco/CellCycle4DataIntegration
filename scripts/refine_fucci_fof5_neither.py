#!/usr/bin/env python3
"""Apply lower FUCCI thresholds only after the original code returns neither."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from classify_fucci_fof5_conditional import source_data, frozen_model, OUT as CALIBRATION
from recalibrate_fucci_fof5 import REPO, OUT as SOURCE, FIGS as SOURCE_FIGS, inputs
from fucci_analysis.data import sha256, write_json
from fucci_analysis.neither_refinement import classify
from fucci_analysis.conditional_reporters import STATES

OUT = SOURCE/"neither_refinement"
FIGS = SOURCE_FIGS/"neither_refinement"


def checked_inputs():
    frozen = frozen_model()
    source = source_data()
    original_summary = json.loads((SOURCE/"forced/summary.json").read_text())
    original_script = REPO/"scripts/force_fucci_fof5_reporter_states.py"
    if sha256(original_script) != original_summary["script_sha256"]:
        raise ValueError("The original classification code changed")
    original_models = json.loads((SOURCE/"frozen_calibration.json").read_text())["models"]
    for c in ["green", "red"]:
        if frozen["thresholds"][c]["high"] != original_models[c]["threshold"]:
            raise ValueError("The original threshold changed")
    check = json.loads((CALIBRATION/"check_freeze.json").read_text())
    for key, path in [("check_annotations_sha256", CALIBRATION/"check_annotations_frozen.csv"),
                      ("frozen_calibration_sha256", CALIBRATION/"frozen_calibration.json")]:
        if sha256(path) != check[key]: raise ValueError("Changed frozen review/calibration")
    return source, frozen


def apply_model(source, thresholds):
    data = source.rename(columns={c: f"stored_original_{c}" for c in
        ["reporter_state", "green_call", "red_call", "green_threshold_margin", "red_threshold_margin"]}).copy()
    final, original, promoted = classify(data.forced_green_score, data.forced_red_score, thresholds)
    data["original_reporter_state"] = original
    data["reporter_state"] = final
    data["refinement_eligible"] = original == "neither"
    data["refinement_promoted"] = promoted
    # Historical labels are compared only after the numeric prediction is complete.
    data["original_reproduces_stored_assignment"] = original == data.stored_original_reporter_state.to_numpy()
    for c in ["green", "red"]:
        data[f"{c}_call"] = np.where(data.reporter_state.isin([f"{c}_only", "both"]), "positive", "not_detected")
        data[f"refinement_{c}_above_lower"] = data[f"forced_{c}_score"] > thresholds[c]["low"]
        data[f"refinement_{c}_lower_margin"] = data[f"forced_{c}_score"]-thresholds[c]["low"]
    return data


def sensitivity(data, thresholds):
    g, r = data.forced_green_score, data.forced_red_score
    bootstrap = pd.read_csv(CALIBRATION/"bootstrap_thresholds.csv")
    states, rows = [], []
    for row in bootstrap.itertuples():
        model = {"green": {**thresholds["green"], "low": row.green_low},
                 "red": {**thresholds["red"], "low": row.red_low}}
        final, original, promoted = classify(g, r, model)
        assert np.array_equal(original, data.original_reporter_state)
        assert (final[original != "neither"] == original[original != "neither"]).all()
        states.append(final)
        rows.append({"replicate": row.replicate, "promoted_n": int(promoted.sum()),
                     **{f"{s}_n": int((final == s).sum()) for s in STATES}})
    state_array = np.asarray(states)
    data["refinement_bootstrap_agreement"] = (state_array == data.reporter_state.to_numpy()[None, :]).mean(axis=0)
    for s in STATES: data[f"refinement_bootstrap_frequency_{s}"] = (state_array == s).mean(axis=0)
    boot = pd.DataFrame(rows); boot.to_csv(OUT/"bootstrap_counts.csv", index=False)
    states, rows = [], []
    for gm in np.linspace(.8, 1.2, 9):
        for rm in np.linspace(.8, 1.2, 9):
            model = {"green": {**thresholds["green"], "low": min(thresholds["green"]["high"], thresholds["green"]["low"]*gm)},
                     "red": {**thresholds["red"], "low": min(thresholds["red"]["high"], thresholds["red"]["low"]*rm)}}
            final, original, promoted = classify(g, r, model)
            assert (final[original != "neither"] == original[original != "neither"]).all()
            states.append(final)
            rows.append({"green_multiplier": float(gm), "red_multiplier": float(rm),
                "green_low": model["green"]["low"], "red_low": model["red"]["low"],
                "changed_n": int((final != data.reporter_state).sum()), "promoted_n": int(promoted.sum()),
                **{f"{s}_n": int((final == s).sum()) for s in STATES}})
    data["refinement_grid_agreement"] = (np.asarray(states) == data.reporter_state.to_numpy()[None, :]).mean(axis=0)
    grid = pd.DataFrame(rows); grid.to_csv(OUT/"threshold_grid.csv", index=False)
    features = pd.read_csv(SOURCE/"measurement_variants.csv.gz")
    variant_rows, variant_counts = [], []
    for variant, frame in features.groupby("variant", sort=False):
        scores = frame.pivot(index="geometry_id", columns="channel", values="mean_excess").reindex(data.geometry_id)
        if variant == "primary":
            scores.loc[:, "green"] = g.to_numpy(); scores.loc[:, "red"] = r.to_numpy()
        available = np.isfinite(scores[["green", "red"]]).all(axis=1).to_numpy()
        final, original = np.full(len(data), "", object), np.full(len(data), "", object)
        promoted = np.zeros(len(data), bool)
        final[available], original[available], promoted[available] = classify(scores.green.to_numpy()[available], scores.red.to_numpy()[available], thresholds)
        assert (final[available & (original != "neither")] == original[available & (original != "neither")]).all()
        agree = available & (final == data.reporter_state.to_numpy())
        variant_rows.append(pd.DataFrame({"geometry_id": data.geometry_id.to_numpy(), "CellposeLabel": data.CellposeLabel.to_numpy(),
            "variant": variant, "green_score": scores.green.to_numpy(), "red_score": scores.red.to_numpy(),
            "available": available, "original_reporter_state": original, "reporter_state": final,
            "promoted": promoted, "agrees_with_primary": agree,
            "primary_fallback_used": data.forced_reference_fallback.to_numpy() & (variant == "primary")}))
        variant_counts.append({"variant": variant, "available_n": int(available.sum()), "missing_n": int((~available).sum()),
            "changed_n": int((available & ~agree).sum()),
            "original_stage_changes_vs_primary_n": int((available & (original != data.original_reporter_state.to_numpy())).sum()),
            "promoted_n": int(promoted.sum()), "illegal_refinement_changes_n": 0,
            **{f"{s}_n": int((final == s).sum()) for s in STATES}})
    variants = pd.concat(variant_rows, ignore_index=True); variants.to_csv(OUT/"variant_reporter_states.csv", index=False)
    counts = pd.DataFrame(variant_counts); counts.to_csv(OUT/"measurement_stability.csv", index=False)
    by = variants.groupby("geometry_id")
    data["refinement_available_variants"] = data.geometry_id.map(by.available.sum()).astype(int)
    data["refinement_agreeing_variants"] = data.geometry_id.map(by.agrees_with_primary.sum()).astype(int)
    data["refinement_stable_all_11_measurements"] = data.refinement_agreeing_variants.eq(11) & data.refinement_available_variants.eq(11)
    promoted = variants[variants.geometry_id.isin(data.loc[data.refinement_promoted, "geometry_id"])]
    promoted.groupby("variant", sort=False).agg(available_n=("available", "sum"), remain_both_n=("agrees_with_primary", "sum")).to_csv(OUT/"promoted_cell_stability.csv")
    return data, counts, grid, boot


def review_results(data):
    ann = pd.concat([pd.read_csv(CALIBRATION/f"{s}_annotations_frozen.csv", keep_default_na=False)
                     for s in ["calibration", "check"]], ignore_index=True)
    cols = ["geometry_id", "original_reporter_state", "reporter_state", "refinement_eligible", "refinement_promoted", "forced_green_score", "forced_red_score"]
    reviews = ann.merge(data[cols], on="geometry_id", validate="one_to_one")
    reviews.to_csv(OUT/"review_predictions.csv", index=False)
    rows = []
    for split, group in reviews.groupby("split"):
        for scope in ["all_reviewed", "original_neither"]:
            selected = group if scope == "all_reviewed" else group[group.refinement_eligible]
            for quality in ["usable", "all_masks"]:
                reviewed = selected if quality == "all_masks" else selected[selected.mask_review.eq("usable")]
                clear = reviewed[reviewed.review_state.ne("ambiguous")]
                positive = clear.review_state.eq("both")
                for column in ["original_reporter_state", "reporter_state"]:
                    both = clear[column].eq("both")
                    rows.append({"split": split, "scope": scope, "quality": quality,
                        "method": "original" if column.startswith("original") else "refined",
                        "reviewed_n": len(reviewed), "clear_n": len(clear), "exact_agree_n": int(clear[column].eq(clear.review_state).sum()),
                        "both_review_n": int(positive.sum()), "nonboth_review_n": int((~positive).sum()),
                        "both_tp": int((both & positive).sum()), "both_fp": int((both & ~positive).sum())})
    agreement = pd.DataFrame(rows); agreement.to_csv(OUT/"review_agreement.csv", index=False)
    key = ann.set_index("geometry_id")
    for col in ["review_id", "split", "green", "red", "mask_review", "notes", "review_state"]:
        data[f"refinement_review_{col}"] = data.geometry_id.map(key[col]).fillna("unreviewed")
    data["refinement_any_reviewed_mask_questionable"] = data.mask_review.eq("questionable") | data.refinement_review_mask_review.eq("questionable")
    return data, reviews, agreement


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mask-archive", type=Path, default=Path.home()/"Downloads/FoF5_241016_fucci.nucleus.zip")
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True); FIGS.mkdir(exist_ok=True)
    source, frozen = checked_inputs()
    data = apply_model(source, frozen["thresholds"])
    if not data.original_reproduces_stored_assignment.all(): raise ValueError("Original-code rerun no longer matches the reference export")
    assert len(data) == 578 and data.geometry_id.is_unique
    data, variants, grid, boot = sensitivity(data, frozen["thresholds"])
    data, reviews, agreement = review_results(data)
    data.to_csv(OUT/"cell_reporter_states.csv", index=False)
    pd.crosstab(data.original_reporter_state, data.reporter_state).reindex(index=STATES, columns=STATES, fill_value=0).to_csv(OUT/"original_to_refined.csv")
    rows = []
    for scope, d in [("full_stack", data), ("z35_intersections", data[data.visible_z35])]:
        for s in STATES:
            rows.append({"scope": scope, "reporter_state": s, "original_n": int(d.original_reporter_state.eq(s).sum()),
                         "n": int(d.reporter_state.eq(s).sum()), "denominator": len(d)})
    pd.DataFrame(rows).to_csv(OUT/"classification_counts.csv", index=False)
    changed = data.reporter_state.ne(data.original_reporter_state)
    assert (data.loc[changed, "original_reporter_state"] == "neither").all() and (data.loc[changed, "reporter_state"] == "both").all()
    summary = {"n": len(data), "counts": {s: int(data.reporter_state.eq(s).sum()) for s in STATES},
        "original_counts": {s: int(data.original_reporter_state.eq(s).sum()) for s in STATES},
        "z35_counts": {s: int((data.reporter_state.eq(s) & data.visible_z35).sum()) for s in STATES},
        "original_z35_counts": {s: int((data.original_reporter_state.eq(s) & data.visible_z35).sum()) for s in STATES},
        "promoted_n": int(data.refinement_promoted.sum()), "illegal_refinement_changes_n": 0,
        "original_code_matches_reference_n": int(data.original_reproduces_stored_assignment.sum()),
        "thresholds": frozen["thresholds"], "lower_thresholds_refitted": False,
        "state_inputs": "Only numeric scores and thresholds; stage one calls the original point_states function on each invocation",
        "bootstrap_both_count_interval": boot.both_n.quantile([.05, .95]).tolist(),
        "bootstrap_agree_all_n": int(data.refinement_bootstrap_agreement.eq(1).sum()),
        "grid_both_range": [int(grid.both_n.min()), int(grid.both_n.max())],
        "grid_stable_n": int(data.refinement_grid_agreement.eq(1).sum()),
        "measurement_complete_n": int(data.refinement_available_variants.eq(11).sum()),
        "measurement_stable_all_n": int(data.refinement_stable_all_11_measurements.sum()),
        "promotion_stability": {
            "bootstrap_at_least_90pct_n": int((data.refinement_promoted & data.refinement_bootstrap_agreement.ge(.9)).sum()),
            "grid_stable_n": int((data.refinement_promoted & data.refinement_grid_agreement.eq(1)).sum())},
        "fallback_labels": data.loc[data.forced_reference_fallback, "CellposeLabel"].tolist(),
        "provenance": {"original_code_sha256": sha256(REPO/"scripts/force_fucci_fof5_reporter_states.py"),
            "original_calibration_sha256": sha256(SOURCE/"frozen_calibration.json"),
            "source_results_sha256": sha256(SOURCE/"forced/cell_reporter_states.csv"),
            "lower_calibration_sha256": sha256(CALIBRATION/"frozen_calibration.json"),
            "bootstrap_thresholds_sha256": sha256(CALIBRATION/"bootstrap_thresholds.csv"),
            "check_freeze_sha256": sha256(CALIBRATION/"check_freeze.json"),
            "classifier_sha256": sha256(REPO/"scripts/fucci_analysis/neither_refinement.py"),
            "script_sha256": sha256(Path(__file__)),
            "plot_helpers_sha256": sha256(REPO/"scripts/fucci_analysis/neither_refinement_outputs.py"),
            "shared_plot_helpers_sha256": sha256(REPO/"scripts/fucci_analysis/conditional_reporter_outputs.py"),
            "result_sha256": sha256(OUT/"cell_reporter_states.csv")}}
    write_json(OUT/"summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    units, _, components, image_dir, _, manifest = inputs(args.mask_archive)
    if set(units.geometry_id) != set(data.geometry_id): raise ValueError("Mask/table coverage changed")
    from fucci_analysis.neither_refinement_outputs import render, report
    render(data, reviews, frozen, components, image_dir, manifest, variants, grid, boot, SOURCE, FIGS)
    report(summary, agreement, variants, REPO)


if __name__ == "__main__":
    main()
