#!/usr/bin/env python3
"""Assign all FoF5 labels to four reporter states with frozen point thresholds."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import ndimage

from recalibrate_fucci_fof5 import inputs, REPO, OUT as SOURCE, FIGS as SOURCE_FIGS
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb
from matplotlib.patches import Patch
from matplotlib.backends.backend_pdf import PdfPages
from fucci_analysis.data import sha256, write_json
from fucci_analysis.outputs import save, PHASE_COLORS
from fucci_analysis.local_calibration_outputs import load_planes, map_images, markdown_table
from plot_fucci_spatial_verification import stretch, selected_boundaries

OUT = SOURCE/"forced"
FIGS = SOURCE_FIGS/"forced"
COLORS = {"green_only": "#23a765", "red_only": "#e34c5b", "both": "#c6a52a", "neither": "#7394ba"}
NAMES = {"green_only": "Green only", "red_only": "Red only", "both": "Both", "neither": "Neither"}


def point_states(green, red, models):
    green, red = np.asarray(green, float), np.asarray(red, float)
    if green.shape != red.shape or not (np.isfinite(green).all() and np.isfinite(red).all()):
        raise ValueError("Forced calls require a finite score in both channels; missing is not neither")
    g, r = green > models["green"]["threshold"], red > models["red"]["threshold"]
    state = np.select([g & ~r, ~g & r, g & r], ["green_only", "red_only", "both"], default="neither")
    return state, g, r


def nearest_reference(geometry, mask, obj, minimum=50, gap=3):
    inside = geometry == obj
    if not inside.any():
        raise ValueError("Missing foreground in fallback plane")
    distance = ndimage.distance_transform_edt(~inside)
    eligible = (mask == 0) & (distance > gap)
    values = distance[eligible]
    if len(values) < minimum:
        raise ValueError("Too few unmasked reference pixels for fallback")
    radius = float(np.partition(values, minimum-1)[minimum-1])
    return eligible & (distance <= radius), radius


def force_assignments(source, models, mask, components, image_dir, manifest):
    if any(model["feature"] != "mean_excess" for model in models.values()):
        raise ValueError("This forced-call extension expects the frozen mean-excess calibration")
    data = source.rename(columns={name: f"conservative_{name}" for name in [
        "reporter_state", "conditional_phase", "green_call", "red_call", "unresolved_reasons", "primary_unresolved_reason"]}).copy()
    for c in ["green", "red"]:
        data[f"forced_{c}_score"] = data[f"{c}_score"]
        data[f"forced_{c}_score_source"] = "primary_local_reference"
    fallback_rows = []
    missing = ~np.isfinite(data[["green_score", "red_score"]]).all(axis=1)
    for index, row in data[missing].iterrows():
        obj = int(row.geometry_id)
        zs = np.flatnonzero(np.any(components == obj, axis=(1, 2))).tolist()
        cache = load_planes(image_dir, manifest, zs)
        for z in zs:
            foreground = components[z] == obj
            reference, radius = nearest_reference(components[z], mask[z], obj)
            for c in ["green", "red"]:
                image = cache[(c, z)]
                foreground_mean = float(np.mean(image[foreground], dtype=np.float64))
                background = float(np.median(image[reference]))
                fallback_rows.append({"geometry_id": obj, "CellposeLabel": int(row.CellposeLabel), "z": z, "channel": c,
                    "foreground_n": int(foreground.sum()), "reference_n": int(reference.sum()),
                    "reference_outer_radius_pixels": radius, "reference_median": background,
                    "foreground_mean": foreground_mean, "mean_excess": foreground_mean-background})
        for c in ["green", "red"]:
            if not np.isfinite(row[f"{c}_score"]):
                rows = [r for r in fallback_rows if r["geometry_id"] == obj and r["channel"] == c]
                data.loc[index, f"forced_{c}_score"] = np.average([r["mean_excess"] for r in rows], weights=[r["foreground_n"] for r in rows])
                data.loc[index, f"forced_{c}_score_source"] = "nearest_50_unmasked_pixels_with_distance_ties"
    states, g, r = point_states(data.forced_green_score, data.forced_red_score, models)
    data["reporter_state"] = states
    data["green_call"] = np.where(g, "positive", "not_detected")
    data["red_call"] = np.where(r, "positive", "not_detected")
    data["forced_on_previous_unresolved"] = data.conservative_reporter_state.eq("unresolved")
    data["forced_reference_fallback"] = missing
    for c in ["green", "red"]:
        data[f"{c}_threshold_margin"] = data[f"forced_{c}_score"]-models[c]["threshold"]
    return data, pd.DataFrame(fallback_rows)


def handles():
    return [Patch(color=COLORS[state], label=NAMES[state]) for state in COLORS]


def map_figure(data, components, cache, limits, z, crop=None, comparison=False):
    original = data.assign(reporter_state=data.conservative_reporter_state)
    images, visible = map_images(original, components, cache, limits, z, crop)
    region = (slice(None), slice(None)) if crop is None else (slice(crop[1], crop[3]), slice(crop[0], crop[2]))
    geometry = components[z][region]
    lookup = np.zeros(int(components.max())+1, dtype=bool)
    lookup[data.geometry_id.to_numpy(int)] = True
    palette = np.zeros((len(lookup), 3))
    palette[data.geometry_id.to_numpy(int)] = [to_rgb(COLORS[state]) for state in data.reporter_state]
    b = stretch(cache[("bright", z)], limits["bright"])[region]
    colored = np.repeat(b[..., None], 3, axis=2)
    selected = lookup[geometry]
    colored[selected] = .45*colored[selected]+.55*palette[geometry[selected]]
    boundary = selected_boundaries(geometry, lookup)
    colored[boundary] = palette[geometry[boundary]]
    images["forced"] = colored
    keys = ["fluorescence", "baseline_phase", "provisional_phase", "forced"] if comparison else ["fluorescence", "forced"]
    titles = {"fluorescence": "A  Green + red fluorescence\nWhite outlines: dominant components",
              "baseline_phase": "C1  Old absolute gates\nOriginal phase labels",
              "provisional_phase": "C2  Previous mixture model\nOriginal uncertainty retained",
              "forced": "D  Forced reporter states\nEvery label assigned to one of four states"}
    fig, axes = plt.subplots(1, len(keys), figsize=(6*len(keys), 7))
    for ax, key in zip(axes, keys):
        ax.imshow(images[key], interpolation="nearest"); ax.axis("off")
        ax.set_title(titles[key], loc="left", fontsize=11)
    height, width = geometry.shape
    bar = 100 if width > 500 else 25
    x0, y0 = width*.06, height*.92
    axes[0].plot([x0, x0+bar], [y0, y0], color="white", lw=3)
    axes[0].text(x0+bar/2, y0-height*.025, f"{bar} pixels", color="white", ha="center", fontsize=9)
    selected_rows = data[data.geometry_id.isin(visible.geometry_id)]
    counts = " · ".join(f"{NAMES[s]} {int(selected_rows.reporter_state.eq(s).sum())}" for s in COLORS)
    extra = "" if crop is None else f" · crop X={crop[0]}:{crop[2]}, Y={crop[1]}:{crop[3]}"
    fig.suptitle(f"241016 / FoF5 · z={z} (zero-based){extra}\n{len(visible)} intersecting labels · {counts}", fontsize=13)
    if comparison:
        old = ["G1", "G1S", "S", "G2M", "uncertain", "qc_review"]
        fig.legend(handles=[Patch(color=PHASE_COLORS[s], label=s.replace("_", " ")) for s in old],
                   title="C1/C2 phase labels", loc="lower center", bbox_to_anchor=(.47, .04), ncol=6, frameon=False, fontsize=8)
        fig.legend(handles=handles(), title="D forced reporter states", loc="lower center", bbox_to_anchor=(.85, .04), ncol=2, frameon=False, fontsize=8)
    else:
        fig.legend(handles=handles(), loc="lower center", bbox_to_anchor=(.5, .055), ncol=4, frameon=False)
    fig.text(.5, .025, "3D local fluorescence compared with fitted point thresholds. Neither = below both thresholds. No uncertainty or QC abstention.", ha="center", fontsize=9)
    fig.text(.5, .005, "Fixed fluorescence display ranges. Quality and stability flags remain in the exported table.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .15, 1, .9))
    return fig


def scatter_figure(data, models):
    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    for ax, d, title in [(axes[0], data, "All 578 original labels"), (axes[1], data[data.visible_z35], "180 labels intersecting z=35")]:
        for state in ["neither", "both", "red_only", "green_only"]:
            subset = d[d.reporter_state.eq(state)]
            ax.scatter(subset.forced_green_score, subset.forced_red_score, s=17, c=COLORS[state], alpha=.7, edgecolors="none", rasterized=True)
        fallback = d[d.forced_reference_fallback]
        if len(fallback):
            ax.scatter(fallback.forced_green_score, fallback.forced_red_score, s=55, facecolors="none", edgecolors="black", linewidths=1)
            for row in fallback.itertuples():
                ax.annotate(f"{row.CellposeLabel}*", (row.forced_green_score, row.forced_red_score), xytext=(4, 5), textcoords="offset points", fontsize=8)
        ax.axvline(models["green"]["threshold"], color="#238b57", ls="--", lw=1)
        ax.axhline(models["red"]["threshold"], color="#b63847", ls="--", lw=1)
        ax.axvline(0, color="#777777", lw=.5); ax.axhline(0, color="#777777", lw=.5)
        ax.set_xscale("symlog", linthresh=.003); ax.set_yscale("symlog", linthresh=.003)
        ax.set(xlim=(min(-.004, data.forced_green_score.min()*1.2), data.forced_green_score.max()*1.3),
               ylim=(min(-.004, data.forced_red_score.min()*1.2), data.forced_red_score.max()*1.3),
               xlabel="Green mean above local reference", ylabel="Red mean above local reference", title=title)
        ax.grid(alpha=.15)
    fig.suptitle("FoF5 · forced assignment to four reporter states", fontsize=15)
    fig.legend(handles=handles(), loc="lower center", bbox_to_anchor=(.5, .055), ncol=4, frameon=False)
    fig.text(.5, .025, "Dashed lines: fitted point thresholds. All 578 labels plotted; *label 17 uses a nearest-unmasked-pixel reference fallback.", ha="center", fontsize=9)
    fig.text(.5, .005, "Signed scores retained; axes use a symmetric log scale. Uncertainty and QC do not suppress a state assignment.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .13, 1, .94))
    save(fig, FIGS/"reporter_scatter")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mask-archive", type=Path, default=Path.home()/"Downloads/FoF5_241016_fucci.nucleus.zip")
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True); FIGS.mkdir(exist_ok=True)
    frozen = json.loads((SOURCE/"frozen_calibration.json").read_text())
    original_summary = json.loads((SOURCE/"summary.json").read_text())
    if sha256(SOURCE/"frozen_calibration.json") != original_summary["reproducibility"]["frozen_calibration_sha256"]:
        raise ValueError("Changed frozen thresholds")
    if sha256(SOURCE/"measurement_variants.csv.gz") != frozen["measurement_variants_sha256"]:
        raise ValueError("Changed frozen measurements")
    source = pd.read_csv(SOURCE/"cell_reporter_states.csv")
    units, mask, components, image_dir, provenance, manifest = inputs(args.mask_archive)
    if len(source) != 578 or set(source.geometry_id) != set(units.geometry_id):
        raise ValueError("Changed source label coverage")
    features = pd.read_csv(SOURCE/"measurement_variants.csv.gz")
    for c, model in frozen["models"].items():
        primary = features[features.channel.eq(c) & features.variant.eq("primary")].set_index("geometry_id")
        np.testing.assert_allclose(source[f"{c}_score"], source.geometry_id.map(primary[model["feature"]]), rtol=0, atol=0, equal_nan=True)
    data, fallback = force_assignments(source, frozen["models"], mask, components, image_dir, manifest)
    assert len(data) == 578 and data.geometry_id.is_unique and set(data.reporter_state) <= set(COLORS)
    previous_resolved = data.conservative_reporter_state.ne("unresolved")
    assert data.loc[previous_resolved, "reporter_state"].eq(data.loc[previous_resolved, "conservative_reporter_state"]).all()
    data.to_csv(OUT/"cell_reporter_states.csv", index=False)
    fallback.to_csv(OUT/"fallback_measurements.csv", index=False)
    pd.crosstab(data.conservative_reporter_state, data.reporter_state).reindex(columns=COLORS, fill_value=0).to_csv(OUT/"conservative_to_forced.csv")
    counts = []
    for scope, d in [("full_stack", data), ("z35_intersections", data[data.visible_z35])]:
        for state in COLORS:
            counts.append({"scope": scope, "reporter_state": state, "n": int(d.reporter_state.eq(state).sum()), "denominator": len(d)})
    pd.DataFrame(counts).to_csv(OUT/"classification_counts.csv", index=False)
    summary = {"n": len(data), "counts": {s: int(data.reporter_state.eq(s).sum()) for s in COLORS},
        "z35_counts": {s: int((data.reporter_state.eq(s) & data.visible_z35).sum()) for s in COLORS},
        "previously_unresolved_assigned": int(data.forced_on_previous_unresolved.sum()),
        "previous_resolved_calls_unchanged": int(previous_resolved.sum()),
        "fallback_labels": data.loc[data.forced_reference_fallback, "CellposeLabel"].astype(int).tolist(),
        "thresholds": {c: m["threshold"] for c, m in frozen["models"].items()},
        "rule": "Strict greater-than point threshold in each channel; all four combinations retained; no abstention",
        "fallback": "For missing primary scores only, use at least the nearest 50 unmasked pixels per occupied XY plane beyond a 3-pixel gap, including distance ties; foreground-volume-weighted mean excess",
        "source_results_sha256": sha256(SOURCE/"cell_reporter_states.csv"),
        "frozen_calibration_sha256": sha256(SOURCE/"frozen_calibration.json"),
        "script_sha256": sha256(Path(__file__)),
        "plot_helpers_sha256": sha256(REPO/"scripts/fucci_analysis/local_calibration_outputs.py")}
    write_json(OUT/"summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    scatter_figure(data, frozen["models"])
    cache = load_planes(image_dir, manifest, [15, 25, 35, 45, 55])
    with PdfPages(FIGS/"reporter_map_slice_atlas.pdf") as pdf:
        for z in [15, 25, 35, 45, 55]:
            fig = map_figure(data, components, cache, manifest["display_limits"], z)
            pdf.savefig(fig, bbox_inches="tight", facecolor="white")
            if z == 35:
                save(fig, FIGS/"reporter_map_z35")
            else:
                plt.close(fig)
    save(map_figure(data, components, cache, manifest["display_limits"], 35, (64, 96, 576, 608)), FIGS/"reporter_map_cluster_z35")
    save(map_figure(data, components, cache, manifest["display_limits"], 35, comparison=True), FIGS/"old_new_comparison_z35")
    report(data, fallback, summary)


def report(data, fallback, summary):
    table = markdown_table(["State", "Full stack (578)", "z=35 intersections (180)"],
        [[NAMES[s], summary["counts"][s], summary["z35_counts"][s]] for s in COLORS])
    fallback_table = markdown_table(["Label", "Channel", "Reference pixels", "Outer radius (XY pixels)", "Mean excess"],
        [[r.CellposeLabel, r.channel, r.reference_n, f"{r.reference_outer_radius_pixels:.3f}", f"{r.mean_excess:.7f}"] for r in fallback.itertuples()])
    text = f"""# FoF5: forced assignment to four reporter states

All **578** original segmentation labels receive one of **green only, red only, both, neither**, as requested. There are **zero unresolved assignments**. The 530 previously unresolved labels now have a forced state; the 48 previously resolved calls are unchanged.

## Figures and results

- [Fluorescence beside forced states, enlarged](../figs4paper/fucci_fof5_recalibration/forced/reporter_map_cluster_z35.png).
- [Full field at z=35](../figs4paper/fucci_fof5_recalibration/forced/reporter_map_z35.png) and [old C1/C2 versus forced calls](../figs4paper/fucci_fof5_recalibration/forced/old_new_comparison_z35.png).
- [Forced-state scatter plots](../figs4paper/fucci_fof5_recalibration/forced/reporter_scatter.png) and [five-slice PDF atlas](../figs4paper/fucci_fof5_recalibration/forced/reporter_map_slice_atlas.pdf).
- [All-label result table](../results/fucci_fof5_recalibration/forced/cell_reporter_states.csv), [transition counts](../results/fucci_fof5_recalibration/forced/conservative_to_forced.csv) and [provenance](../results/fucci_fof5_recalibration/forced/summary.json).

{table}

## Assignment rule

Use the frozen fitted **point** thresholds on the primary 3D local-background measurements: green **{summary['thresholds']['green']:.7f}**, red **{summary['thresholds']['red']:.7f}**. A channel is positive if its mean excess is strictly greater than its threshold; equality counts as not detected. Combining the two binary decisions produces the four states. Neither means below both reporter-detection cutoffs; it is not mapped to a biological phase.

There is no bootstrap uncertainty band, minimum-support exclusion, stability veto or mask-quality veto in the forced state decision. Those flags and the previous conservative calls remain in the result table. The thresholds, feature selection and image-review judgments are unchanged; no model was refitted. Scatter plots retain signed scores and show all 578 labels.

## One missing-measurement fallback

Label 17 contains seven voxels in z=27 and has no unmasked reference pixels in the original local rings. Its missing scores are measured using the nearest unmasked pixels beyond a 3-pixel gap, with at least 50 reference pixels and all ties at the outer distance included. Reference pixels exclude every segmentation label. The fallback subtracts their median from the foreground mean, using the same intensity units as the fitted cutoffs. It is flagged by `forced_reference_fallback` and outlined on the scatter plot.

{fallback_table}

## Export columns and reproduction

`reporter_state`, `green_call` and `red_call` contain the forced calls. `forced_green_score` and `forced_red_score` contain the scores actually used; their source fields identify the fallback. `conservative_reporter_state`, `conservative_unresolved_reasons`, `mask_review`, `stable_across_variants` and the existing measurement-support fields retain the earlier uncertainty information. The [original conservative pilot](fucci_fof5_recalibration.md) remains available.

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python scripts/force_fucci_fof5_reporter_states.py
```
"""
    (REPO/"docs/fucci_fof5_forced_reporter_states.md").write_text(text)


if __name__ == "__main__":
    main()
