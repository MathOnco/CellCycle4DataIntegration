#!/usr/bin/env python3
"""Compare FoF5 fluorescence appearance, measured means, and saved phase calls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import ndimage, stats

from plot_fucci_spatial_verification import (
    build_policies, read_sources, selected_boundaries, stretch, write_report,
)
import matplotlib.pyplot as plt
from fucci_analysis.data import PHASES, STATES, gate_coordinates, sha256, write_json
from fucci_analysis.data import gates
from fucci_analysis.model import model_from_dict
from fucci_analysis.outputs import PHASE_COLORS, save
from fucci_analysis.review import normalized_plane, planes

CHANNELS = {"green": "00", "red": "02"}
GATES = {"green": .003, "red": .0095}
RING_INNER, RING_OUTER = 3, 12


def measure_images(frame, mask, components, image_dir, display, z_main, source, manifest):
    """Use original pixels; annuli are descriptive unmasked references, not controls."""
    frame = frame.copy()
    ids = frame.geometry_id.to_numpy(int)
    n = int(components.max()) + 1
    selected = np.zeros(n, dtype=bool)
    selected[ids] = True
    counts_3d = np.bincount(components.ravel(), minlength=n)
    sums_3d = {c: np.zeros(n) for c in CHANNELS}
    ring_count = np.zeros(n, dtype=np.int64)
    ring_sum = {c: np.zeros(n) for c in CHANNELS}
    files = {c: planes(image_dir, number) for c, number in CHANNELS.items()}
    expected_hashes = {(v["channel"], v["z"]): v["sha256"] for v in manifest["image_files"]}
    cached, slice_values = {}, {}
    for z in range(len(mask)):
        raw = {}
        geometry = components[z]
        area = np.bincount(geometry.ravel(), minlength=n)
        visible_ids = np.flatnonzero(selected & (area > 0))
        boxes = ndimage.find_objects(geometry, max_label=n-1)
        for c in CHANNELS:
            path = files[c][z]
            if sha256(path) != expected_hashes[(c, z)]:
                raise ValueError(f"Image changed since the spatial verification: {path}")
            raw[c] = normalized_plane(path)
            sums = np.bincount(geometry.ravel(), weights=raw[c].ravel(), minlength=n)
            sums_3d[c] += sums
            if z == z_main:
                cached[c] = raw[c]
                slice_values[c] = np.divide(sums, area, out=np.full(n, np.nan), where=area > 0)
                shown = np.bincount(geometry.ravel(), weights=stretch(raw[c], display[c]).ravel(), minlength=n)
                slice_values[c+"_display_mean"] = np.divide(shown, area, out=np.full(n, np.nan), where=area > 0)
        per_plane_count = np.zeros(n, dtype=np.int64)
        per_plane_sum = {c: np.zeros(n) for c in CHANNELS}
        for obj in visible_ids:
            box = boxes[obj-1]
            region = tuple(slice(max(0, b.start-RING_OUTER), min(size, b.stop+RING_OUTER))
                           for b, size in zip(box, geometry.shape))
            distance = ndimage.distance_transform_edt(geometry[region] != obj)
            ring = (distance > RING_INNER) & (distance <= RING_OUTER) & (mask[z][region] == 0)
            per_plane_count[obj] = ring.sum()
            for c in CHANNELS:
                per_plane_sum[c][obj] = raw[c][region][ring].sum(dtype=np.float64)
        ring_count += per_plane_count
        for c in CHANNELS:
            ring_sum[c] += per_plane_sum[c]
        if z == z_main:
            frame["slice_area_pixels"] = area[ids]
            frame["slice_annulus_pixels"] = per_plane_count[ids]
            for c in CHANNELS:
                frame[c+"_slice_mean"] = slice_values[c][ids]
                frame[c+"_slice_display_mean"] = slice_values[c+"_display_mean"][ids]
                frame[c+"_slice_annulus_mean"] = np.divide(
                    per_plane_sum[c][ids], per_plane_count[ids],
                    out=np.full(len(ids), np.nan), where=per_plane_count[ids] > 0)
        if (z+1) % 20 == 0:
            print(f"Measured {z+1}/{len(mask)} planes", flush=True)
    source_ids = source.ObjectNumber.to_numpy(int)
    max_errors = {}
    for c in CHANNELS:
        observed = sums_3d[c][source_ids] / counts_3d[source_ids]
        expected = source[f"Intensity_MeanIntensity_{c}"].to_numpy()
        np.testing.assert_allclose(observed, expected, atol=1e-9, rtol=2e-7)
        max_errors[c] = float(np.max(np.abs(observed-expected)))
        np.testing.assert_allclose(sums_3d[c][ids]/counts_3d[ids], frame[c], atol=1e-9, rtol=2e-7)
        frame[c+"_annulus_mean_3d"] = np.divide(
            ring_sum[c][ids], ring_count[ids], out=np.full(len(ids), np.nan), where=ring_count[ids] > 0)
        frame[c+"_excess_over_annulus_3d"] = frame[c] - frame[c+"_annulus_mean_3d"]
    frame["annulus_voxels_3d"] = ring_count[ids]
    frame["visible_in_slice"] = frame.slice_area_pixels > 0
    visible = frame.visible_in_slice
    frame.loc[visible, "slice_threshold_phase"] = PHASES[gates(
        frame.loc[visible, "green_slice_mean"], frame.loc[visible, "red_slice_mean"], .003, .0095)]
    frame.loc[visible, "slice_vs_3d_threshold_changed"] = (
        frame.loc[visible, "slice_threshold_phase"] != frame.loc[visible, "baseline_phase"])
    frame["slice_display_brightness"] = frame[[c+"_slice_display_mean" for c in CHANNELS]].max(axis=1)
    return frame, cached, max_errors


def select_examples(frame):
    """Six illustrative selections; no area restriction applies to summary counts."""
    eligible = frame[frame.slice_area_pixels >= 100].copy()
    choices = [
        ("Strongest green signal", eligible.sort_values("green_slice_display_mean", ascending=False)),
        ("Strongest red signal", eligible.sort_values("red_slice_display_mean", ascending=False)),
        ("Dimmest C1 G2M example", eligible[eligible.baseline_phase.eq("G2M")].sort_values("slice_display_brightness")),
        ("Strongest green with C1 G1", eligible[eligible.baseline_phase.eq("G1")].sort_values("green_slice_display_mean", ascending=False)),
        ("C1 G2M becomes C2 G1", eligible[eligible.baseline_phase.eq("G2M") & eligible.provisional_phase.eq("G1")].sort_values("slice_display_brightness")),
        ("Strongest green with both calls G1", eligible[eligible.baseline_phase.eq("G1") & eligible.provisional_phase.eq("G1")].sort_values("green_slice_display_mean", ascending=False)),
    ]
    examples, seen = [], set()
    for title, subset in choices:
        subset = subset[~subset.geometry_id.isin(seen)]
        if not len(subset):
            continue
        row = subset.iloc[0].copy()
        row["selection"] = title
        examples.append(row)
        seen.add(int(row.geometry_id))
    return pd.DataFrame(examples).reset_index(drop=True)


def example_figure(examples, raw, geometry, limits, z, visible_count, path):
    fig = plt.figure(figsize=(18, 12))
    outer = fig.add_gridspec(2, 3, left=.025, right=.975, top=.89, bottom=.11, wspace=.12, hspace=.25)
    boxes = ndimage.find_objects(geometry)
    for i, row in examples.iterrows():
        grid = outer[i//3, i%3].subgridspec(3, 3, height_ratios=[.25, 1, .62], hspace=.05, wspace=.035)
        title = fig.add_subplot(grid[0, :])
        title.axis("off")
        title.text(0, .9, f"{i+1}. Label {int(row.CellposeLabel)} — {row.selection}", fontsize=11, weight="bold", va="top")
        box = boxes[int(row.geometry_id)-1]
        center = [(b.start+b.stop)//2 for b in box]
        radius = max(30, max(b.stop-b.start for b in box)//2 + 8)
        region = tuple(slice(max(0, c-radius), min(size, c+radius)) for c, size in zip(center, geometry.shape))
        cut = geometry[region]
        lookup = np.zeros(int(geometry.max())+1, dtype=np.uint8)
        lookup[int(row.geometry_id)] = 1
        boundary = selected_boundaries(cut, lookup)
        g, r = [stretch(raw[c][region], limits[c]) for c in CHANNELS]
        merged = np.stack([r, g, np.zeros_like(g)], axis=-1)
        for j, (name, plane) in enumerate([("Green", g), ("Red", r), ("Merge", merged)]):
            ax = fig.add_subplot(grid[1, j])
            rgb = np.repeat(plane[..., None], 3, axis=2) if plane.ndim == 2 else plane.copy()
            rgb[boundary] = .2*rgb[boundary] + .8
            ax.imshow(rgb, interpolation="nearest")
            ax.set_title(name, fontsize=10, pad=4)
            ax.axis("off")
        details = fig.add_subplot(grid[2, :])
        details.axis("off")
        values = [["Whole 3D mean", f"{row.green:.5f}", f"{row.red:.5f}"],
                  [f"Slice z={z} mean", f"{row.green_slice_mean:.5f}", f"{row.red_slice_mean:.5f}"],
                  ["Local unmasked mean (3D)", f"{row.green_annulus_mean_3d:.5f}", f"{row.red_annulus_mean_3d:.5f}"]]
        table = details.table(cellText=values, colLabels=["Measurement", "Green", "Red"],
                              colWidths=[.58, .21, .21], bbox=[0, .24, 1, .75], cellLoc="left")
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        for cell in table.get_celld().values():
            cell.set_edgecolor("#dddddd")
            cell.set_linewidth(.5)
        details.text(0, .04, f"C1: {row.baseline_phase}     C2: {row.provisional_phase}     Slice area: {int(row.slice_area_pixels)} pixels", fontsize=10)
    fig.suptitle("Fluorescence versus the values used for classification\n241016 / FoF 5 · largest component per original label", fontsize=17, y=.98)
    fig.text(.5, .925, "C1 gates: green > 0.003 and red > 0.0095 gives G2M. C2 reuses these two raw mean features and gate anchors.", ha="center", fontsize=11)
    fig.text(.5, .068, "Channel display ranges are identical to panel A and fixed across examples. White outlines identify the measured component.", ha="center", fontsize=10)
    fig.text(.5, .044, "Local reference: unmasked pixels 3–12 pixels outside each slice of the object, pooled across its z extent; this may include diffuse fluorescence.", ha="center", fontsize=10)
    fig.text(.5, .020, f"Examples require at least 100 mask pixels in this slice. All {visible_count} visible units remain in the quantitative audit. No new phase calls were fitted.", ha="center", fontsize=10)
    save(fig, path)


def summary_figure(frame, examples, summary, z, path):
    visible = frame[frame.visible_in_slice]
    fig, axes = plt.subplots(2, 3, figsize=(17, 10.5))
    for j, (column, title) in enumerate([("baseline_phase", "C1: supplied thresholds"),
                                       ("provisional_phase", "C2: saved candidate")]):
        ax = axes[0, j]
        for phase, group in visible.groupby(column):
            ax.scatter(group.green, group.red, color=PHASE_COLORS[phase], s=27, alpha=.8, edgecolors="none", label=f"{phase} ({len(group)})")
        ax.axvline(.003, color="#444444", ls="--", lw=1)
        ax.axhline(.0095, color="#444444", ls="--", lw=1)
        for i, row in examples.iterrows():
            ax.scatter([row.green], [row.red], s=65, facecolors="none", edgecolors="black", lw=.8)
            ax.annotate(str(i+1), (row.green, row.red), xytext=(5, 5), textcoords="offset points", fontsize=9)
        ax.set(xscale="log", yscale="log", xlim=(.002, .12), ylim=(.007, .10),
               xlabel="Whole-object 3D mean green", ylabel="Whole-object 3D mean red", title=title)
        ax.legend(fontsize=9, loc="upper left")
        ax.grid(alpha=.16)
    ax = axes[0, 2]
    ax.axis("off")
    text = [f"{len(visible)} units intersect z={z}",
            f"{summary['visible']['green_above_gate']}/{len(visible)} above the green gate",
            f"{summary['visible']['red_above_gate']}/{len(visible)} above the red gate", "",
            f"{summary['visible']['slice_vs_3d_calls_changed']}/{len(visible)} C1 calls change using slice means", "",
            "Gate brightness on panel A's display:",
            f"  Green: {summary['gate_display_fraction']['green']*100:.1f}% of full brightness",
            f"  Red: {summary['gate_display_fraction']['red']*100:.1f}% of full brightness", "",
            "Numbers 1–6 link to the example sheet.",
            "Axes use the original normalized intensities.",
            "These counts do not measure phase accuracy."]
    ax.text(.02, .95, "\n".join(text), va="top", fontsize=12, linespacing=1.5)
    for j, c in enumerate(CHANNELS):
        ax = axes[1, j]
        ax.scatter(visible[c], visible[c+"_slice_mean"], s=20, alpha=.65,
                   color="#209c68" if c == "green" else "#d04b58", edgecolors="none")
        lo = min(visible[c].min(), visible[c+"_slice_mean"].min())*.85
        hi = max(visible[c].max(), visible[c+"_slice_mean"].max())*1.15
        ax.plot([lo, hi], [lo, hi], color="#666666", lw=1)
        ax.axvline(GATES[c], color="#444444", ls="--", lw=1)
        ax.axhline(GATES[c], color="#444444", ls="--", lw=1)
        rho = summary["visible"][c+"_slice_vs_3d_spearman"]
        ax.set(xscale="log", yscale="log", xlim=(lo, hi), ylim=(lo, hi),
               xlabel=f"Whole-object 3D mean {c}", ylabel=f"Slice z={z} mean {c}",
               title=f"{c.capitalize()}: slice versus full object (rank r={rho:.2f})")
        ax.grid(alpha=.16)
    ax = axes[1, 2]
    ax.axhline(0, color="#777777", lw=1)
    for j, c in enumerate(CHANNELS):
        valid = visible[visible[c+"_annulus_mean_3d"].notna()]
        offsets = np.linspace(-.18, .18, len(valid))
        ax.scatter(j+offsets, valid[c+"_excess_over_annulus_3d"], s=13, alpha=.55,
                   color="#209c68" if c == "green" else "#d04b58", edgecolors="none")
        median = valid[c+"_excess_over_annulus_3d"].median()
        ax.plot([j-.22, j+.22], [median, median], color="black", lw=2)
    ax.set_xticks([0, 1], ["Green", "Red"])
    ax.set(yscale="symlog", ylim=(-.08, .13), ylabel="3D cell mean − local unmasked mean",
           title="Local contrast diagnostic; no new phase gates")
    ax.set_yscale("symlog", linthresh=.001)
    fig.suptitle(f"Why panel A and the classification maps disagree\n241016 / FoF 5 · dominant components visible at z={z}", fontsize=16)
    fig.text(.5, .025, "Raw image means reproduce the table values. Threshold calibration and biological phase accuracy are separate questions.", ha="center", fontsize=11)
    fig.tight_layout(rect=(0, .055, 1, .93), h_pad=2.5, w_pad=2)
    save(fig, path)


def summarize(frame, display):
    summary = {"gate_display_fraction": {c: float(stretch(np.array([GATES[c]]), display[c])[0]) for c in CHANNELS}}
    for name, group in [("all_dominant", frame), ("visible", frame[frame.visible_in_slice]),
                        ("visible_at_least_100_pixels", frame[frame.slice_area_pixels >= 100])]:
        values = {"n": len(group), "C1_counts": group.baseline_phase.value_counts().to_dict(),
                  "C2_counts": group.provisional_phase.value_counts().to_dict()}
        valid_annuli = group[[c+"_annulus_mean_3d" for c in CHANNELS]].notna().all(axis=1)
        values["annulus_both_channels_valid_n"] = int(valid_annuli.sum())
        values["annulus_above_both_gates"] = int((valid_annuli &
            (group.green_annulus_mean_3d > GATES["green"]) &
            (group.red_annulus_mean_3d > GATES["red"])).sum())
        for c in CHANNELS:
            valid = group[group[c+"_annulus_mean_3d"].notna()]
            values[c+"_above_gate"] = int((group[c] > GATES[c]).sum())
            values[c+"_annulus_valid_n"] = len(valid)
            values[c+"_annulus_above_gate"] = int((valid[c+"_annulus_mean_3d"] > GATES[c]).sum())
            values[c+"_cell_not_above_annulus"] = int((valid[c] <= valid[c+"_annulus_mean_3d"]).sum())
            values[c+"_median_annulus_mean"] = float(valid[c+"_annulus_mean_3d"].median())
            if name != "all_dominant":
                values[c+"_slice_vs_3d_spearman"] = float(stats.spearmanr(group[c], group[c+"_slice_mean"]).statistic)
        if name != "all_dominant":
            values["slice_vs_3d_calls_changed"] = int(group.slice_vs_3d_threshold_changed.sum())
            values["slice_C1_counts"] = group.slice_threshold_phase.value_counts().to_dict()
        summary[name] = values
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mask-archive", type=Path, default=Path.home()/"Downloads/FoF5_241016_fucci.nucleus.zip")
    parser.add_argument("--z", type=int, default=35)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    reference = repo/"results/fucci_spatial_verification/241016_5/image_mask_verification.json"
    manifest = json.loads(reference.read_text())
    source, mask, components, predictions, image_dir, provenance = read_sources(repo, args.mask_archive)
    if not 0 <= args.z < len(mask):
        raise ValueError("Slice outside mask")
    if provenance["mask_member_sha256"] != manifest["mask_member_sha256"]:
        raise ValueError("Mask changed since spatial verification")
    policies, _ = build_policies(source, mask, components, predictions)
    frame = policies["dominant"]["frame"]
    model_path = repo/"results/fucci_component_comparison/dominant/reporter_state_model.json"
    model = model_from_dict(json.loads(model_path.read_text()))
    probabilities = model.predict_proba(gate_coordinates(frame))
    np.testing.assert_allclose(probabilities, frame[[f"p_{s}" for s in STATES]], atol=1e-10)
    frame, raw, errors = measure_images(frame, mask, components, image_dir, manifest["display_limits"], args.z, source, manifest)
    summary = summarize(frame, manifest["display_limits"])
    examples = select_examples(frame)
    out = repo/"results/fucci_spatial_verification/241016_5/fluorescence_audit"
    figs = repo/"figs4paper/fucci_spatial_verification/241016_5/fluorescence_audit"
    out.mkdir(parents=True, exist_ok=True)
    figs.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out/f"per_cell_measurements_z{args.z:02}.csv", index=False)
    examples.to_csv(out/f"illustrative_examples_z{args.z:02}.csv", index=False)
    visible = frame[frame.visible_in_slice]
    pd.crosstab(visible.baseline_phase, visible.slice_threshold_phase).to_csv(out/f"slice_vs_3d_C1_counts_z{args.z:02}.csv")
    summary.update({"field_id": "241016/5", "z": args.z, "policy": "dominant",
                    "source_provenance": provenance, "spatial_manifest_sha256": sha256(reference),
                    "model_sha256": sha256(model_path), "script_sha256": sha256(Path(__file__)),
                    "display_limits": manifest["display_limits"], "maximum_absolute_mean_errors": errors,
                    "all_image_hashes_match": True, "saved_model_scores_reproduced": True,
                    "models_refitted": False, "phase_assignments_changed": False,
                    "annulus_method": {"inner_radius_xy_pixels_exclusive": RING_INNER,
                                       "outer_radius_xy_pixels_inclusive": RING_OUTER,
                                       "exclude_all_mask_labels": True,
                                       "pooling": "Mean of annular pixels across z planes intersecting the component",
                                       "interpretation": "Unmasked local reference may include diffuse or unsegmented fluorescence; no negative controls"},
                    "example_labels": examples.CellposeLabel.astype(int).tolist(),
                    "example_minimum_slice_area": 100})
    write_json(out/f"summary_z{args.z:02}.json", summary)
    example_figure(examples, raw, components[args.z], manifest["display_limits"], args.z, len(visible), figs/f"cell_examples_z{args.z:02}")
    summary_figure(frame, examples, summary, args.z, figs/f"measurement_diagnostics_z{args.z:02}")
    if args.z == manifest["primary_z"]:
        write_report(repo, out.parent, figs.parent, manifest, policies, args.z, manifest["atlas_z_indices"])
    print(json.dumps({k: summary[k] for k in ["all_dominant", "visible", "visible_at_least_100_pixels"]}, indent=2), flush=True)
    print(f"Figures: {figs}", flush=True)


if __name__ == "__main__":
    main()
