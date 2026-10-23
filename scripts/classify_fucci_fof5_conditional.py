#!/usr/bin/env python3
"""Image-reviewed conditional thresholds for the four FoF5 reporter states."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from recalibrate_fucci_fof5 import REPO, OUT as SOURCE, FIGS as SOURCE_FIGS, inputs
from fucci_analysis.data import sha256, write_json
from fucci_analysis.local_calibration_outputs import load_planes
from fucci_analysis.conditional_reporters import classify, fit_lower, STATES
from plot_fucci_spatial_verification import stretch, selected_boundaries
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

OUT = SOURCE/"conditional"
FIGS = SOURCE_FIGS/"conditional"
SEED = 20261023


def prepare():
    if (OUT/"review_key.csv").exists():
        raise ValueError("Existing review sample is preserved")
    data = pd.read_csv(SOURCE/"forced/cell_reporter_states.csv")
    old_key = pd.read_csv(SOURCE/"review_key.csv")
    eligible = data[data.volume.ge(1000) & data.green_max_plane_area.ge(100)
                    & ~data.geometry_id.isin(old_key.geometry_id)
                    & ~data.CellposeLabel.isin([63, 410, 42, 220, 127, 16])].copy()
    rng = np.random.default_rng(SEED)
    samples = []
    for state, n, n_check in [("neither", 40, 10), ("both", 8, 2), ("green_only", 8, 2), ("red_only", 8, 2)]:
        pool = eligible[eligible.reporter_state.eq(state)].copy()
        if len(pool) < n:
            raise ValueError(f"Insufficient review candidates for {state}")
        if state == "neither":
            pool["stratum"] = pd.qcut(pool.forced_green_score.rank(method="first"), 4, labels=False)*4 + pd.qcut(pool.forced_red_score.rank(method="first"), 4, labels=False)
            groups = {k: rng.permutation(v.index).tolist() for k, v in pool.groupby("stratum")}
            selected = []
            while len(selected) < n:
                for k in rng.permutation(list(groups)):
                    if groups[k] and len(selected) < n:
                        selected.append(groups[k].pop())
        else:
            selected = rng.choice(pool.index, n, replace=False)
        sample = pool.loc[rng.permutation(selected)].copy()
        sample["split"] = ["calibration"]*(n-n_check)+["check"]*n_check
        samples.append(sample)
    key = pd.concat(samples).sample(frac=1, random_state=SEED).sort_values("split", kind="stable")
    key = key[["geometry_id", "CellposeLabel", "split", "reporter_state"]].rename(columns={"reporter_state": "sampling_state"})
    key.insert(0, "review_id", [f"C{i+1:02}" for i in range(len(key))])
    key.to_csv(OUT/"review_key.csv", index=False)
    annotations = key[["review_id", "split"]].copy()
    for col in ["green", "red", "mask_review", "notes"]:
        annotations[col] = ""
    annotations["reviewer"] = "assistant_visual_review"
    annotations["experimental_ground_truth"] = False
    annotations.to_csv(OUT/"review_annotations.csv", index=False)
    protocol = {
        "seed": SEED, "n": 64, "calibration_n": 48, "check_n": 16,
        "sampling": "40 previous neither sampled round-robin across 4x4 excess-score quantiles; all 8 eligible previous both; 8 random previous green only and 8 red only; 25% of each group reserved for checking",
        "eligible": "Volume >=1000 voxels and maximum cross-section >=100 pixels; exclude all 48 previous reviews and the six previously discussed cells",
        "hidden_on_sheets": ["original label", "previous state", "sampling group", "numeric scores", "prediction"],
        "reviewer": "Assistant with prior exposure to the field; provisional observations, not expert or experimental ground truth",
        "positive": "Coherent interior fluorescence above adjacent background in at least two displayed substantial sections, even if dim; isolated speckles or signal only outside the outline do not suffice",
        "not_detected": "No coherent interior enrichment across the displayed sections, including the fixed enhanced display",
        "ambiguous": "Weak or inconsistent interior enrichment, overlap with a neighbor, or uncertain localization",
        "usable_mask": "Outline delineates a coherent region attributable to one object across the displayed sections; exclude clear edge slivers or merged distinct objects from calibration",
        "display": "Raw channels and merge use the frozen field ranges; enhanced channels subtract the plane's local reference median (existing volume-weighted reference if unavailable in that section) and show 0..0.012 green / 0..0.008 red with fixed gains; white outlines, no per-cell contrast normalization; reference fallbacks logged",
        "features": "Retain frozen mean_excess scores; no new feature selection",
        "fit": "Joint search over 0<=Lg<=Hg and 0<=Lr<=Hr; maximize balanced agreement for reviewed both versus all other clear states, usable calibration masks only; negative examples include singles; tie prefer specificity then larger sum of normalized lower thresholds then larger green threshold",
        "fit_minimum": "At least two clear usable both and two neither calibration examples; no forced relaxation if evidence is absent",
        "high_gates": "Frozen previous point gates; never refitted",
        "check": "Freeze lower thresholds and calibration annotations before rendering check images; freeze check annotations before scoring; no refit using check outcomes",
        "sensitivity": "500 stratified calibration bootstrap fits, +/-20% grid of lower gates, and 11 existing measurement variants; flags only, never an unresolved assignment",
        "source_sha256": sha256(SOURCE/"forced/cell_reporter_states.csv"),
        "old_calibration_sha256": sha256(SOURCE/"frozen_calibration.json"),
        "measurements_sha256": sha256(SOURCE/"measurement_variants.csv.gz"),
    }
    write_json(OUT/"review_protocol.json", protocol)
    print("Prepared 48 calibration and 16 reserved check examples", flush=True)


def review_pages(mask_archive, split):
    if split == "check" and not (OUT/"frozen_calibration.json").exists():
        raise ValueError("Freeze calibration before opening check images")
    _, _, components, image_dir, _, manifest = inputs(mask_archive)
    key = pd.read_csv(OUT/"review_key.csv")
    key = key[key.split.eq(split)]
    measured = pd.read_csv(SOURCE/"plane_measurements.csv.gz")
    layout = []
    for item in key.itertuples():
        d = measured[measured.geometry_id.eq(item.geometry_id) & measured.channel.eq("green")]
        peak = int(d.loc[d.original_n.idxmax(), "z"])
        zs = d[d.original_n >= .35*d.original_n.max()].z.to_numpy(int)
        if len(zs) < 3:
            zs = d.z.to_numpy(int)
        shown = sorted(set(int(zs[np.argmin(abs(zs-z))]) for z in [peak-4, peak, peak+4]))
        if len(shown) < 3:
            shown = sorted(set(shown+list(zs)))
            shown = [shown[i] for i in [0, len(shown)//2, len(shown)-1]]
        xy = np.argwhere((components[shown] == item.geometry_id).any(axis=0))
        y0, x0 = np.maximum(xy.min(axis=0)-12, 0)
        y1, x1 = np.minimum(xy.max(axis=0)+13, components.shape[1:])
        layout.append({"review_id": item.review_id, "geometry_id": int(item.geometry_id),
                       "split": split, "z_indices": ";".join(map(str, shown)),
                       "x0": int(x0), "x1": int(x1), "y0": int(y0), "y1": int(y1)})
    cache = load_planes(image_dir, manifest, sorted({int(z) for d in layout for z in d["z_indices"].split(";")}))
    references = measured.set_index(["geometry_id", "channel", "z"])
    pooled = pd.read_csv(SOURCE/"forced/cell_reporter_states.csv").set_index("geometry_id")
    display_references = []
    folder = FIGS/f"review_{split}"
    folder.mkdir(exist_ok=True)
    with PdfPages(FIGS/f"review_{split}.pdf") as pdf:
        for page, start in enumerate(range(0, len(layout), 4), start=1):
            fig = plt.figure(figsize=(19, 12))
            outer = fig.add_gridspec(2, 2, left=.015, right=.99, bottom=.065, top=.92, wspace=.06, hspace=.12)
            for position, item in enumerate(layout[start:start+4]):
                item["page"] = page
                obj = item["geometry_id"]
                region = (slice(item["y0"], item["y1"]), slice(item["x0"], item["x1"]))
                grid = outer[position//2, position%2].subgridspec(4, 6, height_ratios=[.18, 1, 1, 1], hspace=.05, wspace=.03)
                title = fig.add_subplot(grid[0, :]); title.axis("off")
                title.text(0, .5, f"{item['review_id']} · planes {item['z_indices']}", fontsize=12, weight="bold")
                for row, z in enumerate(map(int, item["z_indices"].split(";")), start=1):
                    g, r, b = [stretch(cache[(c, z)][region], manifest["display_limits"][c]) for c in ["green", "red", "bright"]]
                    enhanced = []
                    for c, upper in [("green", .012), ("red", .008)]:
                        bg = float(references.loc[(obj, c, z), "main_median"])
                        source = "plane_reference_median"
                        if not np.isfinite(bg):
                            bg = float(pooled.loc[obj, f"{c}_reference_mean"])
                            source = "volume_weighted_reference"
                        if not np.isfinite(bg): raise ValueError("No review display reference")
                        display_references.append({"review_id": item["review_id"], "z": z, "channel": c, "background": bg, "source": source})
                        enhanced.append(np.clip((cache[(c, z)][region]-bg)/upper, 0, 1))
                    boundary = selected_boundaries(components[z][region], np.arange(int(components.max())+1) == obj)
                    images = [g, r, *enhanced, np.stack([r, g, np.zeros_like(g)], axis=-1), b]
                    for col, (plane, caption) in enumerate(zip(images, ["Green", "Red", "Green local", "Red local", "Raw merge", "Brightfield"])):
                        ax = fig.add_subplot(grid[row, col])
                        rgb = np.repeat(plane[..., None], 3, axis=2) if plane.ndim == 2 else plane.copy()
                        rgb[boundary] = .25*rgb[boundary]+.75
                        ax.imshow(rgb, interpolation="nearest"); ax.axis("off")
                        if row == 1: ax.set_title(caption, fontsize=9, pad=3)
            fig.suptitle(f"FoF5 conditional-threshold image review · {split} · page {page}\nIdentities, previous states, numeric scores and predictions concealed", fontsize=15)
            fig.text(.5, .028, "Local views: local reference subtracted (pooled reference if absent in this plane); fixed range 0–0.012 green / 0–0.008 red.", ha="center", fontsize=10)
            fig.text(.5, .008, "Judge interior enrichment across sections: positive / not detected / ambiguous; separately judge whether the mask is usable.", ha="center", fontsize=10)
            pdf.savefig(fig)
            fig.savefig(folder/f"page_{page:02}.png", dpi=160, bbox_inches="tight", facecolor="white")
            plt.close(fig)
    pd.DataFrame(layout).to_csv(OUT/f"review_{split}_display.csv", index=False)
    pd.DataFrame(display_references).to_csv(OUT/f"review_{split}_display_references.csv", index=False)
    print(f"Review sheets: {folder}", flush=True)


def source_data():
    protocol = json.loads((OUT/"review_protocol.json").read_text())
    for key, path in [("source_sha256", SOURCE/"forced/cell_reporter_states.csv"),
                      ("old_calibration_sha256", SOURCE/"frozen_calibration.json"),
                      ("measurements_sha256", SOURCE/"measurement_variants.csv.gz")]:
        if sha256(path) != protocol[key]: raise ValueError(f"Changed input: {path}")
    return pd.read_csv(SOURCE/"forced/cell_reporter_states.csv")


def completed_reviews(split):
    ann = pd.read_csv(OUT/"review_annotations.csv", keep_default_na=False)
    key = pd.read_csv(OUT/"review_key.csv")
    if not ann.review_id.is_unique or set(ann.review_id) != set(key.review_id):
        raise ValueError("Review identities changed")
    ann = ann[ann.split.eq(split)].copy()
    expected = key[key.split.eq(split)]
    if set(ann.review_id) != set(expected.review_id): raise ValueError("Review split changed")
    if any(not set(ann[c]) <= {"positive", "not_detected", "ambiguous"} for c in ["green", "red"]):
        raise ValueError("Complete the image judgments before fitting or scoring")
    if not set(ann.mask_review) <= {"usable", "questionable"} or ann.notes.eq("").any():
        raise ValueError("Complete the mask judgments and notes")
    clear = ann.green.ne("ambiguous") & ann.red.ne("ambiguous")
    g, r = ann.green.eq("positive"), ann.red.eq("positive")
    ann["review_state"] = np.select([g & ~r, r & ~g, g & r], STATES[:3], default="neither")
    ann.loc[~clear, "review_state"] = "ambiguous"
    ann["fit_eligible"] = clear & ann.mask_review.eq("usable")
    return ann.merge(expected.drop(columns="split"), on="review_id", validate="one_to_one")


def fit():
    if (OUT/"frozen_calibration.json").exists(): raise ValueError("Calibration already frozen")
    data = source_data()
    ann = completed_reviews("calibration")
    ann.to_csv(OUT/"calibration_annotations_frozen.csv", index=False)
    d = ann[ann.fit_eligible].merge(data[["geometry_id", "forced_green_score", "forced_red_score"]], on="geometry_id", validate="one_to_one")
    high = {c: m["threshold"] for c, m in json.loads((SOURCE/"frozen_calibration.json").read_text())["models"].items()}
    thresholds, performance = fit_lower(d.forced_green_score, d.forced_red_score, d.review_state, high)
    rng = np.random.default_rng(SEED)
    bootstrap = []
    for i in range(500):
        sample = pd.concat([v.iloc[rng.integers(0, len(v), len(v))] for _, v in d.groupby("review_state", sort=True)])
        model, _ = fit_lower(sample.forced_green_score, sample.forced_red_score, sample.review_state, high)
        bootstrap.append({"replicate": i, "green_low": model["green"]["low"], "red_low": model["red"]["low"]})
    pd.DataFrame(bootstrap).to_csv(OUT/"bootstrap_thresholds.csv", index=False)
    frozen = {"thresholds": thresholds, "calibration_performance": performance,
        "fit_n": len(d), "fit_review_counts": {k: int(v) for k, v in d.review_state.value_counts().items()},
        "fit_review_ids": d.review_id.tolist(), "bootstrap_replicates": 500,
        "bootstrap_intervals": {c: np.quantile([b[f"{c}_low"] for b in bootstrap], [.05, .95]).tolist() for c in high},
        "high_gate_policy": "Frozen prior point thresholds; unchanged",
        "fitting_target": "Image-reviewed both versus all other clear reporter states, usable masks only; balanced sensitivity/specificity",
        "check_used": False, "old_phase_labels_used": False, "desired_class_counts_used": False,
        "calibration_annotations_sha256": sha256(OUT/"calibration_annotations_frozen.csv"),
        "review_key_sha256": sha256(OUT/"review_key.csv"),
        "protocol_sha256": sha256(OUT/"review_protocol.json"),
        "bootstrap_sha256": sha256(OUT/"bootstrap_thresholds.csv"),
        "classifier_sha256": sha256(REPO/"scripts/fucci_analysis/conditional_reporters.py")}
    write_json(OUT/"frozen_calibration.json", frozen)
    print(json.dumps({k: frozen[k] for k in ["thresholds", "fit_n", "fit_review_counts", "calibration_performance", "bootstrap_intervals"]}, indent=2), flush=True)


def frozen_model():
    frozen = json.loads((OUT/"frozen_calibration.json").read_text())
    for key, path in [("calibration_annotations_sha256", OUT/"calibration_annotations_frozen.csv"),
                      ("review_key_sha256", OUT/"review_key.csv"), ("protocol_sha256", OUT/"review_protocol.json"),
                      ("bootstrap_sha256", OUT/"bootstrap_thresholds.csv"),
                      ("classifier_sha256", REPO/"scripts/fucci_analysis/conditional_reporters.py")]:
        if sha256(path) != frozen[key]: raise ValueError(f"Changed frozen input: {path}")
    return frozen


def freeze_check():
    frozen_model()
    if (OUT/"check_annotations_frozen.csv").exists(): raise ValueError("Check judgments already frozen")
    completed_reviews("check").to_csv(OUT/"check_annotations_frozen.csv", index=False)
    write_json(OUT/"check_freeze.json", {"check_annotations_sha256": sha256(OUT/"check_annotations_frozen.csv"),
                                       "frozen_calibration_sha256": sha256(OUT/"frozen_calibration.json")})
    print("Check judgments frozen before scoring", flush=True)


def apply_model(data, frozen):
    data = data.rename(columns={c: f"previous_{c}" for c in ["reporter_state", "green_call", "red_call", "green_threshold_margin", "red_threshold_margin"]}).copy()
    t = frozen["thresholds"]
    data["reporter_state"] = classify(data.forced_green_score, data.forced_red_score, t)
    data["conditional_changed"] = data.reporter_state.ne(data.previous_reporter_state)
    for c in ["green", "red"]:
        data[f"{c}_call"] = np.where(data.reporter_state.isin([f"{c}_only", "both"]), "positive", "not_detected")
        for level in ["low", "high"]:
            data[f"conditional_{c}_above_{level}"] = data[f"forced_{c}_score"] > t[c][level]
            data[f"conditional_{c}_{level}_margin"] = data[f"forced_{c}_score"]-t[c][level]
    data["conditional_decision_stage"] = np.where(data.reporter_state.isin(["green_only", "red_only"]), "clear_single_reporter", "remaining_both_or_neither")
    return data


def sensitivity(data, frozen):
    t = frozen["thresholds"]
    bootstrap = pd.read_csv(OUT/"bootstrap_thresholds.csv")
    predictions, counts = [], []
    for row in bootstrap.itertuples():
        model = {"green": {**t["green"], "low": row.green_low}, "red": {**t["red"], "low": row.red_low}}
        state = classify(data.forced_green_score, data.forced_red_score, model)
        predictions.append(state)
        counts.append({"replicate": row.replicate, **{f"{s}_n": int((state == s).sum()) for s in STATES}})
    predictions = np.asarray(predictions)
    data["conditional_bootstrap_agreement"] = (predictions == data.reporter_state.to_numpy()[None, :]).mean(axis=0)
    for s in STATES: data[f"conditional_bootstrap_frequency_{s}"] = (predictions == s).mean(axis=0)
    bootstrap_counts = pd.DataFrame(counts)
    bootstrap_counts.to_csv(OUT/"bootstrap_counts.csv", index=False)
    grid, predictions = [], []
    for gm in np.linspace(.8, 1.2, 9):
        for rm in np.linspace(.8, 1.2, 9):
            model = {"green": {**t["green"], "low": min(t["green"]["high"], t["green"]["low"]*gm)},
                     "red": {**t["red"], "low": min(t["red"]["high"], t["red"]["low"]*rm)}}
            state = classify(data.forced_green_score, data.forced_red_score, model)
            predictions.append(state)
            grid.append({"green_multiplier": float(gm), "red_multiplier": float(rm),
                         "green_low": model["green"]["low"], "red_low": model["red"]["low"],
                         "changed_n": int((state != data.reporter_state).sum()),
                         **{f"{s}_n": int((state == s).sum()) for s in STATES}})
    data["conditional_grid_agreement"] = (np.asarray(predictions) == data.reporter_state.to_numpy()[None, :]).mean(axis=0)
    grid = pd.DataFrame(grid)
    grid.to_csv(OUT/"threshold_grid.csv", index=False)
    features = pd.read_csv(SOURCE/"measurement_variants.csv.gz")
    per_variant, variant_summary = [], []
    for name, frame in features.groupby("variant", sort=False):
        scores = frame.pivot(index="geometry_id", columns="channel", values="mean_excess").reindex(data.geometry_id)
        if name == "primary":
            # Exactly the previous scores, including the explicitly logged one-label fallback.
            scores.loc[:, "green"] = data.forced_green_score.to_numpy()
            scores.loc[:, "red"] = data.forced_red_score.to_numpy()
        available = np.isfinite(scores[["green", "red"]]).all(axis=1).to_numpy()
        states = np.full(len(data), "", dtype=object)
        states[available] = classify(scores.green.to_numpy()[available], scores.red.to_numpy()[available], t)
        agree = available & (states == data.reporter_state.to_numpy())
        per_variant.append(pd.DataFrame({"geometry_id": data.geometry_id.to_numpy(), "CellposeLabel": data.CellposeLabel.to_numpy(),
            "variant": name, "green_score": scores.green.to_numpy(), "red_score": scores.red.to_numpy(),
            "available": available, "reporter_state": states, "agrees_with_primary": agree,
            "primary_fallback_used": data.forced_reference_fallback.to_numpy() & (name == "primary")}))
        variant_summary.append({"variant": name, "available_n": int(available.sum()), "missing_n": int((~available).sum()),
            "changed_n": int((available & ~agree).sum()), **{f"{s}_n": int((states == s).sum()) for s in STATES}})
    variants = pd.concat(per_variant, ignore_index=True)
    variants.to_csv(OUT/"variant_reporter_states.csv", index=False)
    summary = pd.DataFrame(variant_summary)
    summary.to_csv(OUT/"measurement_stability.csv", index=False)
    by = variants.groupby("geometry_id")
    data["conditional_available_variants"] = data.geometry_id.map(by.available.sum()).astype(int)
    data["conditional_agreeing_variants"] = data.geometry_id.map(by.agrees_with_primary.sum()).astype(int)
    data["conditional_measurement_agreement_available"] = data.conditional_agreeing_variants/data.conditional_available_variants
    data["conditional_stable_all_11_measurements"] = data.conditional_agreeing_variants.eq(11) & data.conditional_available_variants.eq(11)
    return data, summary, grid, bootstrap_counts


def review_results(data):
    freeze = json.loads((OUT/"check_freeze.json").read_text())
    if sha256(OUT/"check_annotations_frozen.csv") != freeze["check_annotations_sha256"] or sha256(OUT/"frozen_calibration.json") != freeze["frozen_calibration_sha256"]:
        raise ValueError("Changed frozen check or model")
    ann = pd.concat([pd.read_csv(OUT/f"{split}_annotations_frozen.csv", keep_default_na=False) for split in ["calibration", "check"]], ignore_index=True)
    selected = ["geometry_id", "reporter_state", "previous_reporter_state", "forced_green_score", "forced_red_score",
                "conditional_bootstrap_agreement", "conditional_stable_all_11_measurements"]
    review = ann.merge(data[selected], on="geometry_id", validate="one_to_one")
    review.to_csv(OUT/"review_predictions.csv", index=False)
    rows = []
    for split, frame in review.groupby("split"):
        for quality in ["usable", "all_reviewed"]:
            d = frame if quality == "all_reviewed" else frame[frame.mask_review.eq("usable")]
            clear = d[d.review_state.ne("ambiguous")]
            pos = clear.review_state.eq("both")
            for method in ["previous_reporter_state", "reporter_state"]:
                both = clear[method].eq("both")
                rows.append({"split": split, "quality": quality, "method": "previous" if method.startswith("previous") else "conditional",
                    "reviewed_n": len(d), "clear_n": len(clear), "ambiguous_n": int(d.review_state.eq("ambiguous").sum()),
                    "exact_agree_n": int(clear[method].eq(clear.review_state).sum()),
                    "both_review_n": int(pos.sum()), "nonboth_review_n": int((~pos).sum()),
                    "both_tp": int((both & pos).sum()), "both_fp": int((both & ~pos).sum()),
                    "both_fn": int((~both & pos).sum()), "both_tn": int((~both & ~pos).sum())})
    agreement = pd.DataFrame(rows)
    agreement.to_csv(OUT/"review_agreement.csv", index=False)
    lookup = ann.set_index("geometry_id")
    for col in ["review_id", "split", "green", "red", "mask_review", "notes", "review_state"]:
        data[f"conditional_review_{col}"] = data.geometry_id.map(lookup[col]).fillna("unreviewed")
    data["conditional_any_reviewed_mask_questionable"] = data.mask_review.eq("questionable") | data.conditional_review_mask_review.eq("questionable")
    return data, review, agreement


def make_report(mask_archive):
    from fucci_analysis.conditional_reporter_outputs import render, report
    frozen = frozen_model()
    data = apply_model(source_data(), frozen)
    assert len(data) == 578 and data.geometry_id.is_unique and set(data.reporter_state) <= set(STATES)
    data, variants, grid, boot = sensitivity(data, frozen)
    data, reviews, agreement = review_results(data)
    data.to_csv(OUT/"cell_reporter_states.csv", index=False)
    transitions = pd.crosstab(data.previous_reporter_state, data.reporter_state).reindex(index=STATES, columns=STATES, fill_value=0)
    transitions.to_csv(OUT/"previous_to_conditional.csv")
    count_rows = []
    for scope, d in [("full_stack", data), ("z35_intersections", data[data.visible_z35])]:
        for s in STATES:
            count_rows.append({"scope": scope, "reporter_state": s, "n": int(d.reporter_state.eq(s).sum()),
                               "previous_n": int(d.previous_reporter_state.eq(s).sum()), "denominator": len(d)})
    pd.DataFrame(count_rows).to_csv(OUT/"classification_counts.csv", index=False)
    reassigned = data[data.previous_reporter_state.eq("neither") & data.reporter_state.eq("both")]
    v = pd.read_csv(OUT/"variant_reporter_states.csv")
    v = v[v.geometry_id.isin(reassigned.geometry_id)]
    v.groupby("variant", sort=False).agg(available_n=("available", "sum"), remain_both_n=("agrees_with_primary", "sum")).to_csv(OUT/"neither_to_both_stability.csv")
    summary = {"n": len(data), "counts": {s: int(data.reporter_state.eq(s).sum()) for s in STATES},
        "previous_counts": {s: int(data.previous_reporter_state.eq(s).sum()) for s in STATES},
        "z35_counts": {s: int((data.reporter_state.eq(s) & data.visible_z35).sum()) for s in STATES},
        "previous_z35_counts": {s: int((data.previous_reporter_state.eq(s) & data.visible_z35).sum()) for s in STATES},
        "changed_n": int(data.conditional_changed.sum()),
        "neither_to_both_n": int((data.previous_reporter_state.eq("neither") & data.reporter_state.eq("both")).sum()),
        "thresholds": frozen["thresholds"], "fallback_labels": data.loc[data.forced_reference_fallback, "CellposeLabel"].tolist(),
        "bootstrap_same_all_n": int(data.conditional_bootstrap_agreement.eq(1).sum()),
        "bootstrap_both_count_interval": boot.both_n.quantile([.05, .95]).tolist(),
        "grid_stable_n": int(data.conditional_grid_agreement.eq(1).sum()),
        "grid_both_min": int(grid.both_n.min()), "grid_both_max": int(grid.both_n.max()),
        "measurement_complete_n": int(data.conditional_available_variants.eq(11).sum()),
        "measurement_stable_all_n": int(data.conditional_stable_all_11_measurements.sum()),
        "neither_to_both_stability": {"bootstrap_at_least_90pct_n": int(reassigned.conditional_bootstrap_agreement.ge(.9).sum()),
            "grid_stable_n": int(reassigned.conditional_grid_agreement.eq(1).sum()),
            "measurement_stable_all_n": int(reassigned.conditional_stable_all_11_measurements.sum())},
        "quality_policy": "All 578 labels assigned; missing sensitivity measurements and reviewed mask concerns remain explicit flags",
        "limitations": ["Assistant image judgments; no experimental or independent expert validation", "One FoF only",
                        "Three calibration false-both calls; no clear red-only in reserved check; no reserved reviewed neither-to-both success",
                        "Neither includes a moderate single-channel signal under the requested hierarchy"],
        "reproducibility": {"source_results_sha256": sha256(SOURCE/"forced/cell_reporter_states.csv"),
            "frozen_calibration_sha256": sha256(OUT/"frozen_calibration.json"),
            "check_freeze_sha256": sha256(OUT/"check_freeze.json"),
            "script_sha256": sha256(Path(__file__)),
            "plot_helpers_sha256": sha256(REPO/"scripts/fucci_analysis/conditional_reporter_outputs.py"),
            "result_sha256": sha256(OUT/"cell_reporter_states.csv")}}
    write_json(OUT/"summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    units, _, components, image_dir, _, manifest = inputs(mask_archive)
    if set(data.geometry_id) != set(units.geometry_id): raise ValueError("Changed mask/table label coverage")
    render(data, reviews, frozen, components, image_dir, manifest, variants, grid, boot, SOURCE, FIGS, OUT)
    report(summary, frozen, agreement, variants, REPO)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["prepare", "review-calibration", "fit", "review-check", "freeze-check", "report"], required=True)
    parser.add_argument("--mask-archive", type=Path, default=Path.home()/"Downloads/FoF5_241016_fucci.nucleus.zip")
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True); FIGS.mkdir(exist_ok=True)
    if args.stage == "prepare":
        prepare()
        review_pages(args.mask_archive, "calibration")
    elif args.stage.startswith("review-"):
        review_pages(args.mask_archive, args.stage.split("-", 1)[1])
    elif args.stage == "fit": fit()
    elif args.stage == "freeze-check": freeze_check()
    elif args.stage == "report": make_report(args.mask_archive)


if __name__ == "__main__":
    main()
