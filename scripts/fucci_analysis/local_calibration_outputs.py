"""Audit tables and figures for the frozen, single-field reporter calibration."""
from __future__ import annotations

import json

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import to_rgb
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

from .data import sha256
from .local_calibration import CHANNELS, STATE_COLORS, VARIANTS, reporter_state
from .outputs import PHASE_COLORS, save
from .review import normalized_plane, planes

STATE_NAMES = {"green_only": "Green only", "red_only": "Red only", "both": "Both reporters", "unresolved": "Unresolved"}
VARIANT_NAMES = {"primary": "Primary reference", "near_reference": "Reference 2–8 px", "far_reference": "Reference 5–20 px",
    "trimmed_reference": "Reference trimmed mean", "mean_reference": "Reference mean", "erode_1px": "Mask erosion 1 px",
    "erode_2px": "Mask erosion 2 px", "dilate_1px": "Mask dilation 1 px", "even_z": "Even z planes",
    "odd_z": "Odd z planes", "large_cross_sections": "Larger cross-sections"}


def evaluate_reviews(results, models):
    rows = []
    reviewed = results[results.review_id.ne("unreviewed")]
    for row in reviewed.itertuples():
        for c, model in models.items():
            score = getattr(row, f"{c}_score")
            point = "positive" if score > model["threshold"] else "not_detected"
            if getattr(row, f"{c}_call") in {"missing", "insufficient_support"}:
                point = "insufficient_support"
            rows.append({"review_id": row.review_id, "geometry_id": row.geometry_id, "CellposeLabel": row.CellposeLabel,
                "split": row.split, "mask_review": row.mask_review, "channel": c, "review": getattr(row, f"review_{c}"),
                "score": score, "old_absolute_gate": "positive" if getattr(row, c) > getattr(row, f"{c}_gate") else "not_detected",
                "new_point_threshold": point, "new_threshold_interval": getattr(row, f"{c}_call"),
                "new_stable_channel": getattr(row, f"{c}_stable_call"), "automatic_reporter_state": row.automatic_reporter_state,
                "delivered_reporter_state": row.reporter_state})
    predictions = pd.DataFrame(rows)
    metrics = []
    for split in ["calibration", "check"]:
        for quality in ["usable", "all_reviewed_masks"]:
            for c in CHANNELS:
                d = predictions[predictions.split.eq(split) & predictions.channel.eq(c)]
                if quality == "usable":
                    d = d[d.mask_review.eq("usable")]
                clear = d[d.review.isin(["positive", "not_detected"])]
                for method in ["old_absolute_gate", "new_point_threshold", "new_threshold_interval", "new_stable_channel"]:
                    called = clear[method].isin(["positive", "not_detected"])
                    correct = clear[method].eq(clear.review)
                    pos, neg = clear.review.eq("positive"), clear.review.eq("not_detected")
                    metrics.append({"split": split, "mask_subset": quality, "channel": c, "method": method,
                        "reviewed_n": len(d), "ambiguous_review_n": int(d.review.eq("ambiguous").sum()),
                        "clear_review_n": len(clear), "positive_review_n": int(pos.sum()), "not_detected_review_n": int(neg.sum()),
                        "called_n": int(called.sum()), "correct_called_n": int((called & correct).sum()),
                        "incorrect_called_n": int((called & ~correct).sum()), "uncalled_n": int((~called).sum()),
                        "positive_correct_n": int((pos & correct).sum()), "not_detected_correct_n": int((neg & correct).sum()),
                        "called_fraction": float(called.mean()) if len(clear) else np.nan,
                        "agreement_among_called": float(correct[called].mean()) if called.any() else np.nan})
    return pd.DataFrame(metrics), predictions


def state_handles():
    return [Patch(color=STATE_COLORS[s], label=STATE_NAMES[s]) for s in STATE_COLORS]


def corrected_axes(ax, results, models, state_column="reporter_state", annotate=False):
    for state in ["unresolved", "both", "red_only", "green_only"]:
        d = results[results[state_column].eq(state)]
        ax.scatter(d.green_score, d.red_score, s=15, color=STATE_COLORS[state], alpha=.7, edgecolors="none", rasterized=True)
    g, r = models["green"], models["red"]
    ax.axvspan(g["bootstrap_threshold_low"], g["bootstrap_threshold_high"], color="#23a765", alpha=.12)
    ax.axhspan(r["bootstrap_threshold_low"], r["bootstrap_threshold_high"], color="#e34c5b", alpha=.12)
    ax.axvline(g["threshold"], color="#238b57", ls="--", lw=1)
    ax.axhline(r["threshold"], color="#b63847", ls="--", lw=1)
    ax.axvline(0, color="#555555", lw=.6); ax.axhline(0, color="#555555", lw=.6)
    ax.set_xscale("symlog", linthresh=.003); ax.set_yscale("symlog", linthresh=.003)
    ax.set(xlabel="Green mean above local reference", ylabel="Red mean above local reference")
    ax.grid(alpha=.15)
    if annotate:
        for label in [63, 410, 42, 220, 127, 16]:
            d = results[results.CellposeLabel.eq(label)]
            if len(d):
                row = d.iloc[0]
                ax.annotate(str(label), (row.green_score, row.red_score), xytext=(4, 5), textcoords="offset points", fontsize=8)


def scatter_figures(results, models, figs):
    fig, axes = plt.subplots(1, 3, figsize=(17, 5.8))
    for phase, d in results.groupby("baseline_phase"):
        axes[0].scatter(d.green, d.red, s=14, color=PHASE_COLORS[phase], alpha=.65, edgecolors="none", rasterized=True)
    axes[0].axvline(.003, color="#238b57", ls="--", lw=1)
    axes[0].axhline(.0095, color="#b63847", ls="--", lw=1)
    axes[0].set(xscale="log", yscale="log", xlabel="Exported green 3D mean", ylabel="Exported red 3D mean",
                title="Old absolute gates · all 578 labels")
    axes[0].legend(handles=[Patch(color=PHASE_COLORS[s], label=s) for s in ["G1", "G1S", "S", "G2M"]], fontsize=8, loc="upper left")
    axes[0].grid(alpha=.15)
    corrected_axes(axes[1], results, models, annotate=True)
    finite = np.isfinite(results[["green_score", "red_score"]]).all(axis=1)
    axes[1].set_title(f"New states · {int(finite.sum())}/{len(results)} labels plotted")
    corrected_axes(axes[2], results[results.visible_z35], models)
    axes[2].set_title(f"New states · {int(results.visible_z35.sum())} labels at z=35")
    for ax in axes[1:]:
        ax.set_xlim(min(-.004, results.green_score.min()*1.2), results.green_score.max()*1.3)
        ax.set_ylim(min(-.004, results.red_score.min()*1.2), results.red_score.max()*1.3)
    fig.legend(handles=state_handles(), loc="lower center", bbox_to_anchor=(.65, .045), ncol=4, frameon=False)
    fig.suptitle("FoF5: raw intensities and image-calibrated local fluorescence", fontsize=15)
    missing = int((~finite).sum())
    fig.text(.5, .024, f"{missing} label has no usable local reference for a corrected coordinate; it remains unresolved in the full output. Negative scores are retained.", ha="center", fontsize=9)
    fig.text(.5, .005, "Corrected axes use a symmetric log scale. Bands show bootstrap threshold ranges, not phase probabilities.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .13, 1, .94))
    save(fig, figs/"reporter_scatter_comparison")


def stability_figure(results, stability, figs):
    rows = [{"name": VARIANT_NAMES[row.variant], **{s: getattr(row, s) for s in STATE_COLORS},
             "changed": row.changed_from_primary} for row in stability.itertuples()]
    for name, column in [("Agree across all 11 variants", "automatic_reporter_state"), ("Delivered + reviewed mask flags", "reporter_state")]:
        rows.append({"name": name, **{s: int(results[column].eq(s).sum()) for s in STATE_COLORS}, "changed": None})
    fig, ax = plt.subplots(figsize=(12, 7.2))
    left = np.zeros(len(rows))
    for state, color in STATE_COLORS.items():
        values = np.array([r[state] for r in rows])
        ax.barh(range(len(rows)), values, left=left, color=color, label=STATE_NAMES[state])
        for i, (start, value) in enumerate(zip(left, values)):
            if value >= 18:
                ax.text(start+value/2, i, str(value), ha="center", va="center", fontsize=8)
        left += values
    ax.set_yticks(range(len(rows)), [r["name"] for r in rows]); ax.invert_yaxis()
    ax.set(xlabel="Original labels; one dominant component each", xlim=(0, 660), title="FoF5 reporter calls under prespecified measurement changes")
    for i, row in enumerate(rows):
        if row["changed"] is not None:
            ax.text(585, i, f"Δ {row['changed']}", va="center", fontsize=9)
    ax.text(585, -1, "Changes", fontsize=9)
    ax.axhline(10.5, color="white", lw=3)
    ax.legend(loc="upper center", bbox_to_anchor=(.5, -.1), ncol=4, frameon=False)
    fig.text(.5, .015, "All rows retain 578 labels. Δ counts state changes from the primary setting; unresolved can reflect weak signal, insufficient support or threshold uncertainty.", ha="center", fontsize=8)
    fig.tight_layout(rect=(0, .06, 1, 1))
    save(fig, figs/"measurement_stability")


def review_figure(review_rows, models, figs):
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), sharex="col")
    for i, split in enumerate(["calibration", "check"]):
        for j, c in enumerate(CHANNELS):
            ax, model = axes[i, j], models[c]
            d = review_rows[review_rows.split.eq(split) & review_rows.channel.eq(c)]
            ymap = {"not_detected": 0, "ambiguous": 1, "positive": 2}
            for quality, marker in [("usable", "o"), ("questionable", "x")]:
                sub = d[d.mask_review.eq(quality)]
                offsets = np.linspace(-.12, .12, len(sub))
                ax.scatter(sub.score, sub.review.map(ymap)+offsets, marker=marker, s=40,
                           color="#238b57" if c == "green" else "#b63847", alpha=.8, label=quality)
                for row, offset in zip(sub.itertuples(), offsets):
                    if split == "check":
                        ax.annotate(row.review_id, (row.score, ymap[row.review]+offset), xytext=(2, 4), textcoords="offset points", fontsize=7)
            ax.axvspan(model["bootstrap_threshold_low"], model["bootstrap_threshold_high"], color="#b3b3b3", alpha=.3)
            ax.axvline(model["threshold"], ls="--", color="black", lw=1)
            ax.set_xscale("symlog", linthresh=.003)
            ax.set(yticks=[0, 1, 2], yticklabels=["Not detected", "Ambiguous", "Positive"], ylim=(-.4, 2.5),
                   title=f"{split.title()} review · {c}", xlabel="Mean fluorescence above local reference")
            ax.grid(alpha=.15)
    axes[0, 0].legend(loc="upper left", fontsize=8)
    fig.suptitle("Image judgments and frozen fluorescence thresholds", fontsize=15)
    fig.text(.5, .025, "Circles: usable reviewed masks. Crosses: questionable masks, excluded from fitting. Check examples were reviewed after freezing the model.", ha="center", fontsize=9)
    fig.text(.5, .008, "Assistant image judgments from the same field; these are not experimental phase labels.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .06, 1, .94))
    save(fig, figs/"review_agreement")


def load_planes(image_dir, manifest, indices):
    files = {c: planes(image_dir, number) for c, number in {**CHANNELS, "bright": "01"}.items()}
    hashes = {(item["channel"], item["z"]): item["sha256"] for item in manifest["image_files"]}
    cache = {}
    for c in files:
        for z in indices:
            path = files[c][z]
            if sha256(path) != hashes[(c, z)]:
                raise ValueError(f"Changed image: {path}")
            cache[(c, z)] = normalized_plane(path)
    return cache


def map_images(results, components, cache, limits, z, crop=None):
    from plot_fucci_spatial_verification import stretch, selected_boundaries

    region = (slice(None), slice(None)) if crop is None else (slice(crop[1], crop[3]), slice(crop[0], crop[2]))
    g, r, b = [stretch(cache[(c, z)], limits[c])[region] for c in ["green", "red", "bright"]]
    geometry = components[z][region]
    selected = np.zeros(int(components.max())+1, dtype=bool)
    selected[results.geometry_id.to_numpy(int)] = True
    boundaries = selected_boundaries(geometry, selected)
    merged = np.stack([r, g, np.zeros_like(g)], axis=-1)
    merged[boundaries] = .25*merged[boundaries]+.75
    images = {"fluorescence": merged}
    for column, colors in [("baseline_phase", PHASE_COLORS), ("provisional_phase", PHASE_COLORS), ("reporter_state", STATE_COLORS)]:
        palette = np.zeros((len(selected), 3))
        palette[results.geometry_id.to_numpy(int)] = [to_rgb(colors[state]) for state in results[column]]
        rgb = np.repeat(b[..., None], 3, axis=2)
        use = selected[geometry]
        rgb[use] = .45*rgb[use]+.55*palette[geometry[use]]
        rgb[boundaries] = palette[geometry[boundaries]]
        images[column] = rgb
    visible = results[results.geometry_id.isin(np.unique(geometry))]
    return images, visible


def spatial_figure(results, components, cache, limits, z, crop=None, comparison=False):
    images, visible = map_images(results, components, cache, limits, z, crop)
    keys = ["fluorescence", "baseline_phase", "provisional_phase", "reporter_state"] if comparison else ["fluorescence", "reporter_state"]
    titles = {"fluorescence": "A  Green + red fluorescence\nWhite outlines: dominant components",
              "baseline_phase": "C1  Old absolute gates\nOriginal supplied phase labels",
              "provisional_phase": "C2  Previous mixture model\nOriginal uncertainty retained",
              "reporter_state": "D  New local reporter states\nWeak, unstable or flagged masks unresolved"}
    fig, axes = plt.subplots(1, len(keys), figsize=(6*len(keys), 7))
    for ax, key in zip(axes, keys):
        ax.imshow(images[key], interpolation="nearest")
        ax.set_title(titles[key], loc="left", fontsize=11)
        ax.axis("off")
    height, width = images["fluorescence"].shape[:2]
    bar = 100 if width > 500 else 25
    x0, y0 = width*.06, height*.92
    axes[0].plot([x0, x0+bar], [y0, y0], color="white", lw=3)
    axes[0].text(x0+bar/2, y0-height*.025, f"{bar} pixels", color="white", ha="center", fontsize=9)
    if comparison:
        old = ["G1", "G1S", "S", "G2M", "uncertain", "qc_review"]
        fig.legend(handles=[Patch(color=PHASE_COLORS[s], label=s.replace("_", " ")) for s in old],
                   title="C1/C2 phase labels", loc="lower center", bbox_to_anchor=(.47, .045), ncol=6, frameon=False, fontsize=8, title_fontsize=9)
        fig.legend(handles=state_handles(), title="D reporter states", loc="lower center", bbox_to_anchor=(.85, .045), ncol=2, frameon=False, fontsize=8, title_fontsize=9)
    else:
        fig.legend(handles=state_handles(), loc="lower center", bbox_to_anchor=(.5, .06), ncol=4, frameon=False)
    counts = " · ".join(f"{STATE_NAMES[s]} {int(visible.reporter_state.eq(s).sum())}" for s in STATE_COLORS)
    extra = "" if crop is None else f" · crop X={crop[0]}:{crop[2]}, Y={crop[1]}:{crop[3]}"
    fig.suptitle(f"241016 / FoF5 · z={z} (zero-based){extra}\n{len(visible)} labels intersect this view · {counts}", fontsize=13)
    fig.text(.5, .027, "Calls use 3D measurements. Fixed fluorescence display ranges across views. All 578 labels retained in the full-stack results.", ha="center", fontsize=9)
    fig.text(.5, .007, "Reporter states are provisional image-based calls; biological phase and unreviewed mask identity remain unvalidated.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .15, 1, .9))
    return fig


def example_figure(results, components, cache, manifest, figs, out):
    from plot_fucci_spatial_verification import stretch, selected_boundaries

    labels = [63, 410, 42, 220, 127, 16]
    rows = results.set_index("CellposeLabel").loc[labels].reset_index()
    rows.to_csv(out/"previously_discussed_examples.csv", index=False)
    fig = plt.figure(figsize=(17, 11))
    outer = fig.add_gridspec(3, 2, left=.02, right=.98, top=.89, bottom=.07, hspace=.2, wspace=.1)
    for i, row in enumerate(rows.itertuples()):
        xy = np.argwhere(components[35] == row.geometry_id)
        if not len(xy):
            raise ValueError("Expected example absent at z=35")
        y0, x0 = np.maximum(xy.min(axis=0)-12, 0)
        y1, x1 = np.minimum(xy.max(axis=0)+13, components.shape[1:])
        region = (slice(y0, y1), slice(x0, x1))
        g, r = [stretch(cache[(c, 35)], manifest["display_limits"][c])[region] for c in CHANNELS]
        images, _ = map_images(results[results.geometry_id.eq(row.geometry_id)], components, cache, manifest["display_limits"], 35, (x0, y0, x1, y1))
        lookup = np.zeros(int(components.max())+1, dtype=bool); lookup[row.geometry_id] = True
        boundary = selected_boundaries(components[35][region], lookup)
        for raw in [g, r]:
            raw[boundary] = .25*raw[boundary]+.75
        grid = outer[i//2, i%2].subgridspec(3, 4, height_ratios=[.22, 1, .18], hspace=.06, wspace=.04)
        title_ax = fig.add_subplot(grid[0, :]); title_ax.axis("off")
        title_ax.text(0, .65, f"Label {row.CellposeLabel} · old C1 {row.baseline_phase} / C2 {row.provisional_phase}", fontsize=11, weight="bold")
        for j, (plane, title) in enumerate(zip([g, r, images["fluorescence"], images["reporter_state"]], ["Green", "Red", "Merge", "New state"])):
            ax = fig.add_subplot(grid[1, j]); ax.imshow(plane, cmap="gray", vmin=0, vmax=1, interpolation="nearest"); ax.axis("off")
            ax.set_title(title, fontsize=9, pad=3)
        footer = fig.add_subplot(grid[2, :]); footer.axis("off")
        footer.text(0, .3, f"New: {STATE_NAMES[row.reporter_state]} · green excess {row.green_score:.5f} · red excess {row.red_score:.5f}", fontsize=9)
    fig.suptitle("Previously discussed cells after local-background recalibration\nThese six examples were excluded from threshold fitting and the reserved review sample", fontsize=14)
    fig.text(.5, .025, "Images: z=35 with fixed stretches. Scores/calls: 3D. White outlines show the selected component; dim channels can remain below their local reference.", ha="center", fontsize=9)
    save(fig, figs/"previously_discussed_cells")


def render_figures(results, variants, scored, review_rows, stability, frozen, components, image_dir, manifest, figs, out):
    models = frozen["models"]
    scatter_figures(results, models, figs)
    stability_figure(results, stability, figs)
    review_figure(review_rows, models, figs)
    indices = [15, 25, 35, 45, 55]
    cache = load_planes(image_dir, manifest, indices)
    view_counts = []
    with PdfPages(figs/"reporter_map_slice_atlas.pdf") as pdf:
        for z in indices:
            fig = spatial_figure(results, components, cache, manifest["display_limits"], z)
            pdf.savefig(fig, bbox_inches="tight", facecolor="white")
            save(fig, figs/f"reporter_map_z{z}")
            visible = results[results.geometry_id.isin(np.unique(components[z]))]
            view_counts.append({"z": z, "n": len(visible), **{s: int(visible.reporter_state.eq(s).sum()) for s in STATE_COLORS}})
            print(f"Rendered reporter map z={z}", flush=True)
    pd.DataFrame(view_counts).to_csv(out/"slice_counts.csv", index=False)
    crop = (64, 96, 576, 608)
    save(spatial_figure(results, components, cache, manifest["display_limits"], 35, comparison=True), figs/"old_new_comparison_z35")
    save(spatial_figure(results, components, cache, manifest["display_limits"], 35, crop), figs/"reporter_map_cluster_z35")
    save(spatial_figure(results, components, cache, manifest["display_limits"], 35, crop, comparison=True), figs/"old_new_comparison_cluster_z35")
    example_figure(results, components, cache, manifest, figs, out)


def markdown_table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"]*len(headers)) + " |"] +
                     ["| " + " | ".join(map(str, row)) + " |" for row in rows])


def write_report(repo, results, evaluation, stability, summary, frozen):
    counts = markdown_table(["Reporter state", "Primary setting", "Stable in all 11 settings", "Delivered (all 578)", "Delivered at z=35 (180)"],
        [[STATE_NAMES[s], summary["primary_counts"][s], summary["automatic_stable_counts"][s],
          f"{summary['final_counts'][s]} ({summary['final_counts'][s]/summary['n']:.1%})", summary["z35_final_counts"][s]] for s in STATE_COLORS])
    thresholds = markdown_table(["Channel", "Selected score", "Positive / not detected references", "Threshold", "Bootstrap 5th–95th percentile", "LOO balanced agreement"],
        [[c, m["feature"], f"{m['positive_n']} / {m['not_detected_n']}", f"{m['threshold']:.7f}",
          f"{m['bootstrap_threshold_low']:.7f}–{m['bootstrap_threshold_high']:.7f}", f"{m['loo_balanced_agreement']:.1%}"] for c, m in frozen["models"].items()])
    check = evaluation[evaluation.split.eq("check") & evaluation.mask_subset.eq("usable")]
    names = {"old_absolute_gate": "Old absolute gate", "new_point_threshold": "New point threshold", "new_threshold_interval": "New + threshold uncertainty", "new_stable_channel": "New + all measurement settings"}
    review_table = markdown_table(["Channel", "Method", "Called / clear reviews", "Agree / called", "Positive found / reviewed positive", "Not detected found / reviewed not detected"],
        [[r.channel, names[r.method], f"{r.called_n}/{r.clear_review_n}", f"{r.correct_called_n}/{r.called_n}",
          f"{r.positive_correct_n}/{r.positive_review_n}", f"{r.not_detected_correct_n}/{r.not_detected_review_n}"] for r in check.itertuples()])
    reason_table = markdown_table(["Reason (overlapping)", "Labels"], [[k.replace("_", " "), v] for k, v in summary["unresolved_reasons_nonexclusive"].items()])
    exclusive_reasons = markdown_table(["Primary unresolved reason (no double counting)", "Labels"],
        [[k.replace("_", " "), v] for k, v in summary["primary_unresolved_reasons_exclusive"].items()])
    stability_table = markdown_table(["Setting", "State changes versus primary", "Green only", "Red only", "Both", "Unresolved"],
        [[VARIANT_NAMES[r.variant], r.changed_from_primary, r.green_only, r.red_only, r.both, r.unresolved] for r in stability.itertuples()])
    old_table = markdown_table(["Previous result", "Full stack (578)", "z=35 intersections (180)"],
        [[f"{method} {state}", int(results[column].eq(state).sum()), int((results[column].eq(state) & results.visible_z35).sum())]
         for method, column, states in [("C1", "baseline_phase", ["G1", "G1S", "S", "G2M"]),
                                        ("C2", "provisional_phase", ["G1", "S", "G2M", "uncertain", "qc_review"])] for state in states])
    checks = results[results.split.eq("check") & results.mask_review.eq("usable")]
    clear = checks[checks.review_green.isin(["positive", "not_detected"]) & checks.review_red.isin(["positive", "not_detected"])].copy()
    clear["review_state"] = [reporter_state(g, r) for g, r in zip(clear.review_green, clear.review_red)]
    resolvable = clear[clear.review_state.ne("unresolved")]
    matched = int(resolvable.automatic_reporter_state.eq(resolvable.review_state).sum())
    wrong = int((clear.automatic_reporter_state.ne("unresolved") & clear.automatic_reporter_state.ne(clear.review_state)).sum())
    calibration_n = int(results.split.eq("calibration").sum())
    calibration_usable = int((results.split.eq("calibration") & results.mask_review.eq("usable")).sum())
    mask_checks = results[results.split.eq("check")]
    examples = results[results.CellposeLabel.isin([63, 410, 42, 220, 127, 16])].sort_values("CellposeLabel")
    example_table = markdown_table(["CellposeLabel", "C1", "C2", "Green excess", "Red excess", "Delivered state"],
        [[r.CellposeLabel, r.baseline_phase, r.provisional_phase, f"{r.green_score:.6f}", f"{r.red_score:.6f}", STATE_NAMES[r.reporter_state]] for r in examples.itertuples()])
    report = f"""# FoF5 local-background reporter recalibration

Completed 2026-10-21 for **241016 / FoF5 only**. All **578 original segmentation labels** are retained, using the largest connected component of each label. These are the same measurement units used in the preceding dominant-component comparison; their identity as individual biological nuclei is not independently established.

## Open these figures first

- [Fluorescence beside the new reporter map, z=35](../figs4paper/fucci_fof5_recalibration/reporter_map_z35.png) and [magnified cluster](../figs4paper/fucci_fof5_recalibration/reporter_map_cluster_z35.png).
- [Old C1/C2 and new calls beside fluorescence](../figs4paper/fucci_fof5_recalibration/old_new_comparison_z35.png), with [the same cluster enlarged](../figs4paper/fucci_fof5_recalibration/old_new_comparison_cluster_z35.png).
- [Raw versus corrected scatter plots](../figs4paper/fucci_fof5_recalibration/reporter_scatter_comparison.png), [measurement stability](../figs4paper/fucci_fof5_recalibration/measurement_stability.png), and [review agreement](../figs4paper/fucci_fof5_recalibration/review_agreement.png).
- [Six previously discussed cells](../figs4paper/fucci_fof5_recalibration/previously_discussed_cells.png) and [five-slice PDF atlas](../figs4paper/fucci_fof5_recalibration/reporter_map_slice_atlas.pdf).

White outlines in fluorescence panels identify the same dominant components colored in the classification panels. Display limits are unchanged from the earlier verification figures and fixed across slices. All calls use 3D measurements; a displayed section can contain only a small part of an object. The z=35 denominator counts every intersecting selected component, including small intersections.

## Result and interpretation

The fitted scores for both channels are **mean fluorescence above a local unmasked reference**. Thresholds are learned from clear image judgments; old phase labels and class proportions are not fitting targets. Weak signal, uncertainty about the threshold, sensitivity to measurement choices, inadequate measurement support, and reviewed questionable masks are retained as unresolved.

{counts}

The primary setting already includes threshold uncertainty and minimum measurement support. The next column additionally requires identical reporter states in all 11 prespecified settings. The delivered map then marks {summary['reviewed_questionable_n']} reviewed questionable masks unresolved; this changes {summary['reviewed_mask_flag_changed_call_n']} otherwise resolved automatic calls. No label is removed from the denominator. An unresolved label is not assigned G1S, quiescence, death, or a negative biological state.

The corrected scatter plot shows {summary['corrected_scatter_finite_n']}/578 labels with finite coordinates. Label(s) {', '.join(map(str, summary['corrected_scatter_missing_labels']))} lack a usable local reference and cannot be positioned on that scatter; they remain in the exported results and all counts as unresolved. The original raw-intensity scatter contains all 578 labels.

The earlier labels remain available unchanged:

{old_table}

These counts do **not** establish a new cell-cycle composition. Reporter detection is the measured target. Under the still inferred PIP-FUCCI-like interpretation, green only is G1-like, red only S-like, and both G2/M-like. Exact construct/tag identity and phase accuracy remain unconfirmed. Grant et al. distinguish these reporter combinations using their known construct and validate transitions with independent imaging and experimental measurements; that evidence is not available for these cells. [Primary reporter reference](https://pmc.ncbi.nlm.nih.gov/articles/PMC6342071/).

## Measurements and feature selection

1. Reuse the verified native alignment of the 70-plane mask and images. Raw 16-bit TIFF intensities are divided by 65,535. Each dominant component's volume and full-stack raw mean are checked against the new CellProfiler table. Image hashes are checked against the earlier verification manifest; no source image, mask, table or old prediction is edited.
2. For each component and z plane, use unmasked pixels at distances greater than 3 and at most 12 XY pixels from its boundary as the primary local reference. All original segmentation labels, including satellite components, are excluded from reference pixels. A reference needs at least 50 pixels in that plane. The primary background statistic is the reference median.
3. Compare six predefined fluorescence features: foreground mean, median, or 75th percentile minus the local reference, either in intensity units or divided by local robust variability (1.4826 × MAD, with a one-count numerical floor). Scores are weighted averages of per-plane differences, with foreground pixel count as weight. Median and percentile features are therefore **pooled per-plane summaries, not whole-volume percentiles**. Signed differences are retained.
4. Choose one feature per channel by leave-one-cell-out balanced agreement on clear, usable calibration examples only. Fit a single cutoff; ties prefer specificity and then a larger threshold. Morphology, texture, old labels and class balance do not enter reporter prediction. Mask geometry is used for measurement and quality checks.
5. Refit the cutoff in 500 stratified bootstrap resamples of the calibration examples, retaining the chosen feature. Scores above the 95th-percentile cutoff are positive; scores at or below the 5th-percentile cutoff are not detected; intermediate scores are ambiguous. These bands describe threshold sensitivity conditional on this sample and feature, not calibrated phase probabilities or complete uncertainty.

{thresholds}

Leave-one-cell-out scores were used for feature selection and are not an unbiased performance estimate after selection. Both selected features are the first, simplest candidate in the predefined ordering. See [all six feature comparisons](../results/fucci_fof5_recalibration/feature_comparison_calibration_only.csv) and [the frozen model](../results/fucci_fof5_recalibration/frozen_calibration.json).

Local reference pixels can contain diffuse fluorescence, out-of-focus signal or unsegmented structures. They are not experimental negative controls. No flat-field correction, channel-unmixing correction or validation across acquisitions is inferred from this pilot.

The preceding fluorescence audit used a pooled local mean as its diagnostic reference. This pilot's primary reference is a per-plane median, so the numerical excesses differ from that audit; the mean-reference setting is included in the stability analysis.

## Image review and separate check

The sample contains 48 examples drawn across a 4 × 4 grid of preliminary green/red contrast quantiles, with volume at least 1,000 voxels and a largest cross-section of at least 100 pixels. Random assignment gives 32 calibration and 16 check examples (seed 20261021). The six previously discussed labels are excluded. Sampling is deliberately broad across fluorescence and is not a prevalence sample.

Each review shows three substantial cross-sections, separate channels, fixed fourfold display enhancement, merged fluorescence, brightfield, and mask outlines. Original IDs, numeric measurements, old classes and new predictions are hidden. The reviewer is the assistant, with prior exposure to the overall field. These are provisional image judgments, not an independent human annotation or experimental ground truth.

- Calibration: {calibration_n} reviewed, {calibration_usable} masks marked usable, {calibration_n-calibration_usable} questionable. Only clear per-channel judgments with usable masks enter fitting.
- Separate check: {len(mask_checks)} reviewed, {len(checks)} usable masks, {len(mask_checks)-len(checks)} questionable. Features, cutoffs, bootstrap bands, support rules, stability rules and handling of questionable masks were frozen before viewing these examples. The judgments were then frozen before scoring. The check did not trigger any threshold refit.
- Positive means coherent localized interior signal across at least two displayed sections; not detected means no convincing localized signal even with the fixed enhanced display; ambiguous covers weak or spatially uncertain signal.
- [Calibration review PDF](../figs4paper/fucci_fof5_recalibration/review_calibration.pdf), [check review PDF](../figs4paper/fucci_fof5_recalibration/review_check.pdf), [all judgments and notes](../results/fucci_fof5_recalibration/review_annotations.csv), and [identity key](../results/fucci_fof5_recalibration/review_key.csv) are saved.

### Check-set agreement, usable masks only

{review_table}

The table evaluates automatic channel calls **before applying manual mask flags**. Ambiguous image judgments are excluded from agreement denominators but retained in the review files. Abstentions count against coverage. The full audit also reports all reviewed masks, including those marked questionable. With only {len(checks)} usable check masks, these fractions are descriptive and cannot establish transfer, sensitivity or specificity in a new field.

Among the usable check masks, {len(clear)} have clear judgments in both channels. {len(resolvable)} have at least one visibly positive reporter; {matched} receive the same automatic stable reporter state. There are {wrong} conflicting resolved automatic states among the {len(clear)} clear two-channel judgments. This comparison has very little positive support and does not validate four biological phases. No usable double-positive example was identified in either review split, so the combined double-positive state has no clean reviewed example supporting it here. Read per-example outcomes in [review_predictions.csv](../results/fucci_fof5_recalibration/review_predictions.csv).

## Stability and unresolved labels

Keep the fitted thresholds fixed while changing the measurement: reference rings 2–8 and 5–20 pixels; reference trimmed mean or mean; foreground erosion by 1 or 2 XY pixels and dilation by 1 pixel without entering another label; even or odd z planes; and cross-sections at least half the component's maximum area. These are XY perturbations, not isotropic 3D erosion or physical-distance calibration.

Each setting requires at least 100 valid foreground voxels, three valid planes, a maximum original cross-section of at least 25 pixels, and local-reference coverage for at least 80% of that setting's eligible foreground volume. Short or thin objects can therefore become unresolved, particularly under erosion or alternate-plane selection. The all-settings rule is intentionally conservative and was set before the check review.

{stability_table}

The following breakdown counts each unresolved label once, prioritizing reviewed mask concerns, inadequate support, neither reporter detected, threshold uncertainty, and then sensitivity to measurement choices:

{exclusive_reasons}

All contributing reasons are also saved. These counts overlap and must not be summed:

{reason_table}

Mask review covered 48 examples, leaving **{summary['unreviewed_mask_n']} masks unreviewed**. A stable automatic reporter state does not certify that its segmentation corresponds to one intact nucleus. Apparent thin edge fragments and possible merged structures remain an important limitation. No segmentation repair was performed.

## Previously discussed examples

These examples were excluded from calibration and the separate review sample. They are useful for following the same cells from the previous audit into the new map, but are not an additional validation set.

{example_table}

## Data and reproduction

- [All 578 label-level results](../results/fucci_fof5_recalibration/cell_reporter_states.csv): original identifiers/measurements/classes, local scores, automatic calls, delivered states, conditional phase names, stability, review status and unresolved reasons.
- [Per-setting states](../results/fucci_fof5_recalibration/variant_reporter_states.csv), [state counts and denominators](../results/fucci_fof5_recalibration/classification_counts.csv), [stability summary](../results/fucci_fof5_recalibration/stability_summary.csv), and [review agreement](../results/fucci_fof5_recalibration/review_agreement.csv).
- Per-plane measurements and all six features for every setting are saved as compressed CSV files under `results/fucci_fof5_recalibration`.
- [Input provenance](../results/fucci_fof5_recalibration/input_provenance.json), frozen calibration/check annotations and [summary with hashes](../results/fucci_fof5_recalibration/summary.json) record the analysis inputs and decisions. The external ZIP inputs and raw images are required to regenerate image panels.

Regenerate predictions, numeric summaries, figures and this report from the frozen calibration and reviews:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python scripts/recalibrate_fucci_fof5.py --stage report
python -m unittest discover -s tests -p 'test_fucci*.py'
```

The preparation/review sequence is `prepare`, `review-calibration`, completed calibration annotations, `fit`, `review-check`, completed check annotations, `freeze-check`, then `report`. The fitting stage refuses to overwrite an existing frozen calibration. Review judgments are saved observations, not generated from model predictions. The report stage rejects changed frozen measurements, changed calibration code or changed frozen judgments.

## What remains

This completes the authorized one-field computational pilot. The outputs are suitable for inspection and deciding whether the measurements better track visible fluorescence. Expert review of the saved examples, verified construct identity, independent phase validation and matched masks for additional FoFs are still needed before treating these as validated cell-cycle labels or extending this calibration to all 31 FoFs.
"""
    (repo/"docs/fucci_fof5_recalibration.md").write_text(report)
