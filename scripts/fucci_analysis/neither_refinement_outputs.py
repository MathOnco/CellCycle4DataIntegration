"""Figures for rerunning the original classifier and refining its neither region."""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.lines import Line2D
from matplotlib.backends.backend_pdf import PdfPages

from .neither_refinement import classify
from .conditional_reporters import STATES
from .conditional_reporter_outputs import (
    COLORS, NAMES, handles, points, state_image, spatial_figure, stability_figure,
)
from .local_calibration_outputs import load_planes, markdown_table
from .outputs import save
from plot_fucci_spatial_verification import stretch


def gates(ax, t, refine):
    ax.axvline(t["green"]["high"], color=COLORS["green_only"], lw=1.1)
    ax.axhline(t["red"]["high"], color=COLORS["red_only"], lw=1.1)
    if refine:
        # Lower gates apply only inside the original neither rectangle.
        ax.plot([t["green"]["low"]]*2, [0, t["red"]["high"]], "--", color=COLORS["green_only"], lw=1.1)
        ax.plot([0, t["green"]["high"]], [t["red"]["low"]]*2, "--", color=COLORS["red_only"], lw=1.1)


def scatter_figure(data, thresholds, reviews, figs):
    fig, axes = plt.subplots(2, 2, figsize=(13, 11))
    for ax, column, title in [
        (axes[0, 0], "original_reporter_state", "Original classifier, rerun · all 578 labels"),
        (axes[0, 1], "reporter_state", "Neither → both refinement · all 578 labels"),
    ]:
        points(ax, data, column); gates(ax, thresholds, column == "reporter_state")
        ax.set_xscale("symlog", linthresh=.003); ax.set_yscale("symlog", linthresh=.003)
        ax.set(xlim=(min(-.004, data.forced_green_score.min()*1.2), data.forced_green_score.max()*1.2),
               ylim=(min(-.004, data.forced_red_score.min()*1.2), data.forced_red_score.max()*1.2), title=title)
        fallback = data[data.forced_reference_fallback]
        ax.scatter(fallback.forced_green_score, fallback.forced_red_score, s=55, facecolors="none", edgecolors="black")
    ax = axes[1, 0]
    points(ax, data, "reporter_state"); gates(ax, thresholds, True)
    ax.set(xlim=(-.0005, .009), ylim=(-.0005, .007), title="Refined calls · low-intensity detail")
    ax = axes[1, 1]
    gx, ry = np.meshgrid(np.linspace(0, .009, 300), np.linspace(0, .007, 300))
    state, _, _ = classify(gx, ry, thresholds)
    index = np.zeros(state.shape, int)
    for i, s in enumerate(STATES): index[state == s] = i
    ax.pcolormesh(gx, ry, index, cmap=ListedColormap([COLORS[s] for s in STATES]),
                  vmin=-.5, vmax=3.5, alpha=.15, shading="auto", rasterized=True)
    clear = reviews[reviews.fit_eligible]
    for split, marker in [("calibration", "o"), ("check", "^")]:
        for s in STATES:
            d = clear[clear.split.eq(split) & clear.review_state.eq(s)]
            ax.scatter(d.forced_green_score, d.forced_red_score, c=COLORS[s], marker=marker,
                       s=44, edgecolors="black", linewidths=.5)
    for row in clear[clear.review_state.ne(clear.reporter_state)].itertuples():
        if 0 <= row.forced_green_score <= .009 and 0 <= row.forced_red_score <= .007:
            ax.annotate(row.review_id, (row.forced_green_score, row.forced_red_score),
                        xytext=(4, 4), textcoords="offset points", fontsize=8)
    gates(ax, thresholds, True)
    ax.set(xlim=(0, .009), ylim=(0, .007), title="Reviewed examples · low-intensity detail\nPoint color = visual judgment; background = rule")
    ax.legend(handles=[Line2D([], [], marker=m, color="black", linestyle="none", label=s)
                       for m, s in [("o", "Calibration"), ("^", "Reserved check")]], fontsize=8, loc="upper right")
    for ax in axes.flat:
        ax.set_xlabel("Green mean above local reference"); ax.set_ylabel("Red mean above local reference"); ax.grid(alpha=.12)
    fig.suptitle("FoF5 · original classification code followed by a neither-only refinement", fontsize=15)
    fig.legend(handles=handles(), loc="lower center", bbox_to_anchor=(.5, .025), ncol=4, frameon=False)
    fig.text(.5, .005, "Solid: original gates. Dashed: lower gates within original neither only. Top: all 578 labels; bottom: explicit zooms.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .065, 1, .95)); save(fig, figs/"reporter_scatter_comparison")


def refined_spatial_figure(data, components, cache, limits, z, crop=None):
    # This alias is for the existing plotting helper; its values were just
    # computed from measurements, never read as prediction inputs.
    figure_data = data.assign(previous_reporter_state=data.original_reporter_state)
    fig = spatial_figure(figure_data, components, cache, limits, z, crop)
    fig.axes[1].set_title("B  Original classifier, rerun", loc="left", fontsize=13)
    fig.axes[2].set_title("C  Neither → both refinement", loc="left", fontsize=13)
    for label in fig.texts:
        if label.get_text().startswith("Every original label"):
            label.set_text("Original code is rerun on measurements. Lower gates can change only its neither results to both; all four states remain available.")
    return fig


def examples_figure(data, reviews, components, image_dir, manifest, source, figs):
    # Two supported neither->both changes, one known false change, and three
    # preserved single-positive examples (no new image judgments or overrides).
    examples = reviews.set_index("review_id").loc[["C12", "C40", "C16", "C25", "C34", "C03"]].reset_index()
    planes = pd.read_csv(source/"plane_measurements.csv.gz")
    peak = planes[planes.channel.eq("green")].sort_values(["original_n", "z"], ascending=[False, True]).drop_duplicates("geometry_id").set_index("geometry_id").z
    examples["display_z"] = examples.geometry_id.map(peak).astype(int)
    cache = load_planes(image_dir, manifest, examples.display_z.unique().tolist())
    refs = planes.set_index(["geometry_id", "channel", "z"])
    fig, axes = plt.subplots(len(examples), 7, figsize=(19, 18))
    for i, row in enumerate(examples.itertuples()):
        z, obj = row.display_z, row.geometry_id
        xy = np.argwhere(components[z] == obj)
        y0, x0 = np.maximum(xy.min(axis=0)-12, 0); y1, x1 = np.minimum(xy.max(axis=0)+13, components.shape[1:])
        region = (slice(y0, y1), slice(x0, x1)); geometry = components[z][region]
        one = data[data.geometry_id.eq(obj)]
        g, r, b = [stretch(cache[(c, z)][region], manifest["display_limits"][c]) for c in ["green", "red", "bright"]]
        old, boundary, _ = state_image(one, geometry, b, "original_reporter_state")
        new, _, _ = state_image(one, geometry, b, "reporter_state")
        local = []
        for c, upper in [("green", .012), ("red", .008)]:
            reference = float(refs.loc[(obj, c, z), "main_median"])
            if not np.isfinite(reference): raise ValueError("Selected example has no plane reference")
            local.append(np.clip((cache[(c, z)][region]-reference)/upper, 0, 1))
        images = [g, r, *local, np.stack([r, g, np.zeros_like(g)], axis=-1), old, new]
        for j, im in enumerate(images):
            if j < 5:
                im = np.repeat(im[..., None], 3, axis=2) if im.ndim == 2 else im.copy()
                im[boundary] = .25*im[boundary]+.75
            axes[i, j].imshow(im, interpolation="nearest"); axes[i, j].axis("off")
            if i == 0: axes[i, j].set_title(["Green", "Red", "Green local", "Red local", "Raw merge", "Original rerun", "Refined"][j], fontsize=12, pad=36)
        axes[i, 0].text(0, 1.03, f"Label {row.CellposeLabel} · {row.review_id} · z={z}\nReview: {NAMES[row.review_state]}", transform=axes[i, 0].transAxes, fontsize=9, va="bottom")
        for j, state in [(5, row.original_reporter_state), (6, row.reporter_state)]:
            axes[i, j].text(.5, -.07, NAMES[state], transform=axes[i, j].transAxes, fontsize=10, ha="center")
    fig.suptitle("Neither-to-both examples and retained single-reporter calls\nRows 1–2: visually supported changes. Row 3: known false change. Rows 4–6: original single-positive code retained.", fontsize=14)
    fig.legend(handles=handles(), loc="lower center", bbox_to_anchor=(.5, .025), ncol=4, frameon=False)
    fig.text(.5, .008, "One largest section per cell; prior reviews used three sections. Fixed raw ranges and local gains. Reviews are assistant image judgments.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .05, 1, .95), h_pad=2); save(fig, figs/"reviewed_examples")
    examples.to_csv(source/"neither_refinement/figure_examples.csv", index=False)


def render(data, reviews, frozen, components, image_dir, manifest, variants, grid, bootstrap_counts, source, figs):
    scatter_figure(data, frozen["thresholds"], reviews, figs)
    stability_figure(data, variants, grid, bootstrap_counts, figs)
    cache = load_planes(image_dir, manifest, [15, 25, 35, 45, 55])
    with PdfPages(figs/"reporter_map_slice_atlas.pdf") as pdf:
        for z in [15, 25, 35, 45, 55]:
            fig = refined_spatial_figure(data, components, cache, manifest["display_limits"], z)
            pdf.savefig(fig, bbox_inches="tight", facecolor="white")
            if z == 35: save(fig, figs/"reporter_map_z35")
            else: plt.close(fig)
    save(refined_spatial_figure(data, components, cache, manifest["display_limits"], 35, (64, 96, 576, 608)), figs/"reporter_map_cluster_z35")
    examples_figure(data, reviews, components, image_dir, manifest, source, figs)


def report(summary, agreement, variants, repo):
    t = summary["thresholds"]
    counts = markdown_table(["State", "Original / 578", "Refined / 578", "Original at z=35 / 180", "Refined at z=35 / 180"],
        [[NAMES[s], summary["original_counts"][s], summary["counts"][s], summary["original_z35_counts"][s], summary["z35_counts"][s]] for s in STATES])
    a = agreement[agreement.quality.eq("usable")]
    scores = markdown_table(["Review split", "Scope", "Method", "Exact agreement", "Both found / reviewed both", "False both / reviewed non-both"],
        [[r.split, r.scope, r.method, f"{r.exact_agree_n}/{r.clear_n}", f"{r.both_tp}/{r.both_review_n}", f"{r.both_fp}/{r.nonboth_review_n}"] for r in a.itertuples()])
    stable = markdown_table(["Measurement setting", "Finite pairs", "Missing pairs", "Final state changes", "Original-stage changes"],
        [[r.variant, r.available_n, r.missing_n, r.changed_n, r.original_stage_changes_vs_primary_n] for r in variants.itertuples()])
    text = f"""# FoF5: preserve the original classifier and refine only neither

The original classification **code** is preserved and rerun on the fluorescence measurements. Saved assignments are not prediction inputs. Only when the original function returns **neither** do the lower cutoffs decide whether to change that result to **both**. This implements the user's correction to the earlier conditional method.

## Figures and results

- [Magnified fluorescence / original / refined comparison](../figs4paper/fucci_fof5_recalibration/neither_refinement/reporter_map_cluster_z35.png).
- [Full field at z=35](../figs4paper/fucci_fof5_recalibration/neither_refinement/reporter_map_z35.png) and [five-slice atlas](../figs4paper/fucci_fof5_recalibration/neither_refinement/reporter_map_slice_atlas.pdf).
- [Scatter plots and decision regions](../figs4paper/fucci_fof5_recalibration/neither_refinement/reporter_scatter_comparison.png), [reviewed examples](../figs4paper/fucci_fof5_recalibration/neither_refinement/reviewed_examples.png), and [stability](../figs4paper/fucci_fof5_recalibration/neither_refinement/classification_stability.png).
- [All 578 results](../results/fucci_fof5_recalibration/neither_refinement/cell_reporter_states.csv), [transition table](../results/fucci_fof5_recalibration/neither_refinement/original_to_refined.csv), and [summary with code/input hashes](../results/fucci_fof5_recalibration/neither_refinement/summary.json).

{counts}

Exactly **{summary['promoted_n']} neither results become both**. The original code reproduces all 578 historical classifications on these unchanged inputs. Its 90 green-only, 72 red-only and 32 both results pass through the additional step unchanged. All original segmentation labels remain represented by one dominant component, with no excluded or unresolved final assignments.

## Deterministic rule

Use the existing 3D volume-weighted foreground mean minus the per-plane local reference median; TIFF intensities were divided by 65,535. No features or thresholds were refitted for this correction.

| Reporter | Original higher cutoff | Additional lower cutoff |
| --- | --- | --- |
| Green | {t['green']['high']:.17g} | {t['green']['low']:.17g} |
| Red | {t['red']['high']:.17g} | {t['red']['low']:.17g} |

```python
original, _, _ = point_states(G, R, original_models)
promote = (original == "neither") & (G > low_green) & (R > low_red)
final = np.where(promote, "both", original)
```

`point_states` is imported directly from the unchanged [original script](../scripts/force_fucci_fof5_reporter_states.py). Its file hash and original higher thresholds are checked against the saved calibration. The [new classifier](../scripts/fucci_analysis/neither_refinement.py) accepts only numeric scores and thresholds. It does not accept saved assignments or cell identifiers. Changing a measurement can therefore change the original-stage result; that result is recomputed on every invocation, including measurement perturbations. Historical labels are retained only for an audit comparison after prediction.

The original rules are green only when `G > high_green` and `R <= high_red`; red only when `R > high_red` and `G <= high_green`; both when both higher gates are exceeded; otherwise neither. The second stage operates exclusively inside that last region. Equality to a cutoff belongs to the lower-signal side. The dashed lower gates in the scatter figure stop at the original neither region.

All score pairs are finite. The existing nearest-unmasked-reference fallback for label 17 is reused and flagged unchanged. Missing values in sensitivity variants are explicitly unavailable, never silently classified as neither. Mask quality and stability remain annotations. These are reporter states, without a new biological phase assignment.

## Existing review evidence

The lower cutoffs and 500 bootstrap fits are reused from the [earlier calibration](fucci_fof5_conditional_reporter_states.md). Its 64 examples comprised 48 calibration and 16 reserved check reviews; 28 calibration and nine check examples had usable masks and clear judgments in both channels. These are assistant image judgments from this field. No new reviews, feature selection, threshold optimization, or manual label overrides were performed for this correction.

The changed routing is evaluated against both the whole review sample and the subset where the rerun original classifier returns neither:

{scores}

The two visually supported neither-to-both examples, labels **89 and 116**, are retained. Label **108** still becomes both despite a neither review. The two earlier false-both red-only examples, labels **209 and 47**, now retain red only. The figure shows these cases and an unchanged green-only example. Some original single-positive calls disagree with visual both judgments; those disagreements remain because the original single-positive rules are retained. In particular, check label **125** remains red only despite a both review. Agreement is consequently **21/28 calibration and 8/9 check**, versus **20/28 and 8/9** for the original code.

The check has no clear red-only example or reviewed neither-to-both success. It was previously inspected under the earlier method, so it is not a fresh independent test of this revised routing. The lower thresholds were calibrated under the earlier rule and are reused, rather than claimed optimal for the restricted neither region. The small selected sample does not establish general accuracy or biological phase validity.

## Stability

Only lower thresholds vary in the 500 bootstrap fits and 81-setting ±20% grid. In every setting, the original 90 green-only, 72 red-only and 32 both results are retained by the extra step. Total both calls have a central 90% bootstrap range of **{summary['bootstrap_both_count_interval'][0]:.0f}–{summary['bootstrap_both_count_interval'][1]:.0f}** and a grid range of **{summary['grid_both_range'][0]}–{summary['grid_both_range'][1]}**. **{summary['bootstrap_agree_all_n']}/578** retain their state in all bootstrap fits and **{summary['grid_stable_n']}/578** throughout the grid. These are sensitivity measures, not calibrated probabilities.

Of the 45 neither-to-both changes, **{summary['promotion_stability']['bootstrap_at_least_90pct_n']}** retain both in at least 90% of bootstrap fits and **{summary['promotion_stability']['grid_stable_n']}** throughout the threshold grid. Their dependence on reference subtraction persists: **0/45** remain both with a mean reference at fixed gates. [Counts by measurement setting](../results/fucci_fof5_recalibration/neither_refinement/promoted_cell_stability.csv) report how many still satisfy the full corrected rule. The rule now also requires these cells to remain within the original neither region or to exceed both original high gates; changes in measurements can instead make a cell single positive.

For each of the 11 measurement settings, both stages run again on that setting's numeric scores. The additional step still permits only neither → both relative to the original code on the **same** input. Original-stage results can change across settings; they are not frozen cell assignments. Both sets of changes are shown below. **{summary['measurement_complete_n']}/578** have measurements in all settings and **{summary['measurement_stable_all_n']}/578** retain the final state in all 11 with complete measurements.

{stable}

The [variant results](../results/fucci_fof5_recalibration/neither_refinement/variant_reporter_states.csv) expose both freshly computed stages. The all-cell export retains historical annotations, with new stability/review fields prefixed `refinement_`. Fixed cutoffs across changed measurements measure sensitivity, not separately recalibrated alternatives.

## Reproduce

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python scripts/refine_fucci_fof5_neither.py
python -m unittest discover -s tests -p 'test_fucci*.py'
```

The CLI reproduces this verified 241016/FoF5 snapshot, checking source, original code, frozen calibration and review hashes. Image regeneration requires the raw images and matching mask archive. The reusable classifier operates on supplied numeric scores. Tests verify that original code is called anew, changed measurements can change its decision, saved labels do not determine predictions, and the only added transition is neither → both, including gate boundaries.

The [earlier conditional outputs](fucci_fof5_conditional_reporter_states.md) are preserved as history and superseded for current use by this report.
"""
    (repo/"docs/fucci_fof5_neither_refinement.md").write_text(text)
