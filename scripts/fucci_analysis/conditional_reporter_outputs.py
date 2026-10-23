"""Figures and a reviewable report for conditional FoF5 reporter thresholds."""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb, ListedColormap
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from matplotlib.backends.backend_pdf import PdfPages

from .conditional_reporters import classify, STATES
from .outputs import save
from .local_calibration_outputs import load_planes, markdown_table
from plot_fucci_spatial_verification import stretch, selected_boundaries

COLORS = {"green_only": "#23a765", "red_only": "#e34c5b", "both": "#c6a52a", "neither": "#7394ba"}
NAMES = {s: s.replace("_", " ").capitalize() for s in STATES}


def handles():
    return [Patch(color=COLORS[s], label=NAMES[s]) for s in STATES]


def state_image(data, geometry, bright, column):
    palette = np.zeros((int(geometry.max())+1, 3))
    selected = np.zeros(len(palette), bool)
    visible = data[data.geometry_id.isin(np.unique(geometry))]
    selected[visible.geometry_id.to_numpy(int)] = True
    palette[visible.geometry_id.to_numpy(int)] = [to_rgb(COLORS[s]) for s in visible[column]]
    rgb = np.repeat(bright[..., None], 3, axis=2)
    inside = selected[geometry]
    rgb[inside] = .45*rgb[inside]+.55*palette[geometry[inside]]
    boundary = selected_boundaries(geometry, selected)
    rgb[boundary] = palette[geometry[boundary]]
    return rgb, boundary, visible


def spatial_figure(data, components, cache, limits, z, crop=None):
    region = (slice(None), slice(None)) if crop is None else (slice(crop[1], crop[3]), slice(crop[0], crop[2]))
    geometry = components[z][region]
    g, r, b = [stretch(cache[(c, z)], limits[c])[region] for c in ["green", "red", "bright"]]
    old, boundary, visible = state_image(data, geometry, b, "previous_reporter_state")
    new, _, _ = state_image(data, geometry, b, "reporter_state")
    merged = np.stack([r, g, np.zeros_like(g)], axis=-1)
    merged[boundary] = .25*merged[boundary]+.75
    fig, axes = plt.subplots(1, 3, figsize=(18, 7))
    for ax, im, title in zip(axes, [merged, old, new], ["A  Green + red fluorescence", "B  Previous four-state gates", "C  Conditional thresholds"]):
        ax.imshow(im, interpolation="nearest"); ax.axis("off"); ax.set_title(title, loc="left", fontsize=13)
    h, w = geometry.shape
    bar = 100 if w > 600 else 25
    axes[0].plot([w*.06, w*.06+bar], [h*.92, h*.92], color="white", lw=3)
    axes[0].text(w*.06+bar/2, h*.89, f"{bar} pixels", color="white", ha="center")
    for ax, column in zip(axes[1:], ["previous_reporter_state", "reporter_state"]):
        label = " / ".join(str(int(visible[column].eq(s).sum())) for s in STATES)
        ax.text(.5, -.035, f"Green / red / both / neither: {label}", transform=ax.transAxes, ha="center", fontsize=10)
    fig.suptitle(f"241016 / FoF5 · z={z} (zero-based) · {len(visible)} intersecting dominant components", fontsize=15)
    fig.legend(handles=handles(), loc="lower center", bbox_to_anchor=(.5, .055), ncol=4, frameon=False)
    fig.text(.5, .027, "White outlines in A match the colored objects in B/C. Calls use 3D local-background measurements; fluorescence display ranges are fixed.", ha="center", fontsize=10)
    fig.text(.5, .005, "Every original label receives a state. Neither is the residual rule outcome, including a weak signal in only one channel; it is not a cell-cycle phase.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .13, 1, .94))
    return fig


def gate_lines(ax, thresholds, low=True):
    for c, method in [("green", ax.axvline), ("red", ax.axhline)]:
        method(thresholds[c]["high"], color=COLORS[f"{c}_only"], lw=1.1, ls="-")
        if low: method(thresholds[c]["low"], color=COLORS[f"{c}_only"], lw=1.1, ls="--")


def points(ax, data, column):
    for s in ["neither", "both", "red_only", "green_only"]:
        d = data[data[column].eq(s)]
        ax.scatter(d.forced_green_score, d.forced_red_score, s=17, c=COLORS[s], alpha=.7, edgecolors="none", rasterized=True)


def scatter_figure(data, thresholds, reviews, figs):
    fig, axes = plt.subplots(2, 2, figsize=(13, 11))
    for ax, column, title in [(axes[0, 0], "previous_reporter_state", "Previous gates · all 578 labels"),
                               (axes[0, 1], "reporter_state", "Conditional thresholds · all 578 labels")]:
        points(ax, data, column); gate_lines(ax, thresholds, column == "reporter_state")
        ax.set_xscale("symlog", linthresh=.003); ax.set_yscale("symlog", linthresh=.003)
        ax.set(xlim=(min(-.004, data.forced_green_score.min()*1.2), data.forced_green_score.max()*1.2),
               ylim=(min(-.004, data.forced_red_score.min()*1.2), data.forced_red_score.max()*1.2), title=title)
        fallback = data[data.forced_reference_fallback]
        ax.scatter(fallback.forced_green_score, fallback.forced_red_score, s=55, facecolors="none", edgecolors="black")
    ax = axes[1, 0]
    points(ax, data, "reporter_state"); gate_lines(ax, thresholds)
    ax.set(xlim=(-.0005, .009), ylim=(-.0005, .007), title="Conditional thresholds · low-intensity detail")
    ax = axes[1, 1]
    gx, ry = np.meshgrid(np.linspace(0, .009, 250), np.linspace(0, .007, 250))
    state = classify(gx, ry, thresholds)
    index = np.zeros(state.shape, int)
    for i, s in enumerate(STATES): index[state == s] = i
    ax.pcolormesh(gx, ry, index, cmap=ListedColormap([COLORS[s] for s in STATES]), vmin=-.5, vmax=3.5, alpha=.13, shading="auto", rasterized=True)
    clear = reviews[reviews.fit_eligible]
    for split, marker in [("calibration", "o"), ("check", "^")]:
        for s in STATES:
            d = clear[clear.split.eq(split) & clear.review_state.eq(s)]
            ax.scatter(d.forced_green_score, d.forced_red_score, c=COLORS[s], marker=marker, s=44, edgecolors="black", linewidths=.5)
    errors = clear[clear.review_state.ne(clear.reporter_state)]
    for row in errors.itertuples():
        if 0 <= row.forced_green_score <= .009 and 0 <= row.forced_red_score <= .007:
            ax.annotate(row.review_id, (row.forced_green_score, row.forced_red_score), xytext=(4, 4), textcoords="offset points", fontsize=8)
    gate_lines(ax, thresholds)
    ax.set(xlim=(0, .009), ylim=(0, .007), title="Reviewed examples · low-intensity detail\nPoint color = visual judgment; background = rule")
    ax.legend(handles=[Line2D([], [], marker="o", color="black", linestyle="none", label="Calibration"),
                       Line2D([], [], marker="^", color="black", linestyle="none", label="Reserved check")], fontsize=8, loc="upper right")
    for ax in axes.flat:
        ax.set_xlabel("Green mean above local reference"); ax.set_ylabel("Red mean above local reference"); ax.grid(alpha=.12)
    fig.suptitle("FoF5 · separate thresholds for clear single reporters and dim coexpression", fontsize=15)
    fig.legend(handles=handles(), loc="lower center", bbox_to_anchor=(.5, .025), ncol=4, frameon=False)
    fig.text(.5, .005, "Solid lines: unchanged higher gates. Dashed lines: fitted lower gates. Top panels include all 578 labels; lower panels are explicit zooms.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .065, 1, .95)); save(fig, figs/"reporter_scatter_comparison")


def stability_figure(data, variants, grid, bootstrap_counts, figs):
    fig, axes = plt.subplots(2, 2, figsize=(13, 10))
    v = variants[variants.variant.ne("primary")]
    axes[0, 0].barh(np.arange(len(v)), v.changed_n, color="#b6a73e")
    for i, row in enumerate(v.itertuples()):
        axes[0, 0].text(row.changed_n+1, i, f"{row.changed_n}/{row.available_n} · missing {row.missing_n}", va="center", fontsize=8)
    axes[0, 0].set(yticks=np.arange(len(v)), yticklabels=v.variant.str.replace("_", " "), xlabel="Changes among finite score pairs", title="Measurement variants · fixed thresholds")
    axes[0, 0].set_xlim(0, max(v.changed_n)*1.65); axes[0, 0].invert_yaxis()
    for ax, value, title in [(axes[0, 1], "both_n", "Number called both"), (axes[1, 0], "changed_n", "Changes versus fitted lower gates")]:
        p = grid.pivot(index="red_multiplier", columns="green_multiplier", values=value)
        im = ax.imshow(p.to_numpy(), origin="lower", extent=(.775, 1.225, .775, 1.225), aspect="auto", cmap="viridis")
        ax.scatter([1], [1], marker="+", color="white", s=130)
        ax.set(xlabel="Green lower cutoff multiplier", ylabel="Red lower cutoff multiplier", title=title)
        fig.colorbar(im, ax=ax, fraction=.05)
    axes[1, 1].hist(bootstrap_counts.both_n, bins=20, color=COLORS["both"], edgecolor="white")
    axes[1, 1].axvline(data.reporter_state.eq("both").sum(), color="black", ls="--")
    axes[1, 1].set(xlabel="Labels called both / 578", ylabel="Bootstrap fits", title="500 resamples of calibration reviews")
    fig.suptitle("Conditional reporter calls · sensitivity retained as separate annotations", fontsize=15)
    fig.text(.5, .018, "Missing variant measurements are counted explicitly. Bootstrap frequencies describe threshold sensitivity, not calibrated probabilities.", ha="center", fontsize=10)
    fig.tight_layout(rect=(0, .05, 1, .94)); save(fig, figs/"classification_stability")


def examples_figure(data, reviews, components, image_dir, manifest, source, figs, out):
    # Include two neither->both successes, one reserved-check success, and all
    # three calibration false-both cases; selection is disclosed in the report.
    ids = ["C12", "C40", "C57", "C16", "C25", "C34"]
    examples = reviews.set_index("review_id").loc[ids].reset_index()
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
        old, boundary, _ = state_image(one, geometry, b, "previous_reporter_state")
        new, _, _ = state_image(one, geometry, b, "reporter_state")
        local = [np.clip((cache[(c, z)][region]-refs.loc[(obj, c, z), "main_median"])/upper, 0, 1) for c, upper in [("green", .012), ("red", .008)]]
        images = [g, r, *local, np.stack([r, g, np.zeros_like(g)], axis=-1), old, new]
        for j, im in enumerate(images):
            if j < 5:
                im = np.repeat(im[..., None], 3, axis=2) if im.ndim == 2 else im.copy()
                im[boundary] = .25*im[boundary]+.75
            axes[i, j].imshow(im, interpolation="nearest"); axes[i, j].axis("off")
            if i == 0: axes[i, j].set_title(["Green", "Red", "Green local", "Red local", "Raw merge", "Previous", "Conditional"][j], fontsize=12, pad=36)
        axes[i, 0].text(0, 1.03, f"Label {row.CellposeLabel} · {row.review_id} · z={z}\nReview: {NAMES[row.review_state]}", transform=axes[i, 0].transAxes, fontsize=9, va="bottom")
        axes[i, 5].text(.5, -.07, NAMES[row.previous_reporter_state], transform=axes[i, 5].transAxes, fontsize=10, ha="center")
        axes[i, 6].text(.5, -.07, NAMES[row.reporter_state], transform=axes[i, 6].transAxes, fontsize=10, ha="center")
    fig.suptitle("Successful changes and known mismatches\nTop three: visual support for both. Bottom three: the rule calls both but visual review disagrees.", fontsize=15)
    fig.legend(handles=handles(), loc="lower center", bbox_to_anchor=(.5, .025), ncol=4, frameon=False)
    fig.text(.5, .008, "One largest section shown per cell; review judgments used three sections. Raw ranges and enhanced local gains are fixed across examples. These are assistant image judgments.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .05, 1, .95), h_pad=2); save(fig, figs/"reviewed_changes_and_mismatches")
    examples.to_csv(out/"figure_examples.csv", index=False)


def render(data, reviews, frozen, components, image_dir, manifest, variants, grid, bootstrap_counts, source, figs, out):
    scatter_figure(data, frozen["thresholds"], reviews, figs)
    stability_figure(data, variants, grid, bootstrap_counts, figs)
    cache = load_planes(image_dir, manifest, [15, 25, 35, 45, 55])
    with PdfPages(figs/"reporter_map_slice_atlas.pdf") as pdf:
        for z in [15, 25, 35, 45, 55]:
            fig = spatial_figure(data, components, cache, manifest["display_limits"], z)
            pdf.savefig(fig, bbox_inches="tight", facecolor="white")
            if z == 35: save(fig, figs/"reporter_map_z35")
            else: plt.close(fig)
    save(spatial_figure(data, components, cache, manifest["display_limits"], 35, (64, 96, 576, 608)), figs/"reporter_map_cluster_z35")
    examples_figure(data, reviews, components, image_dir, manifest, source, figs, out)


def report(summary, frozen, agreement, variants, repo):
    t = frozen["thresholds"]
    counts = markdown_table(["State", "Previous / 578", "Conditional / 578", "Previous at z=35 / 180", "Conditional at z=35 / 180"],
        [[NAMES[s], summary["previous_counts"][s], summary["counts"][s], summary["previous_z35_counts"][s], summary["z35_counts"][s]] for s in STATES])
    a = agreement[agreement.quality.eq("usable")]
    scores = markdown_table(["Review split", "Method", "Exact state agreement", "Both found / reviewed both", "False both / reviewed non-both"],
        [[r.split, r.method, f"{r.exact_agree_n}/{r.clear_n}", f"{r.both_tp}/{r.both_review_n}", f"{r.both_fp}/{r.nonboth_review_n}"] for r in a.itertuples()])
    stable = markdown_table(["Measurement setting", "Finite pairs", "Missing pairs", "State changes"],
        [[r.variant, r.available_n, r.missing_n, r.changed_n] for r in variants.itertuples()])
    text = f"""# FoF5: conditional thresholds for four reporter states

The requested two-stage classifier is implemented for **241016/FoF5**, using all **578 original segmentation labels**, one dominant component per label. Every label receives **green only, red only, both, or neither**. There are zero unresolved assignments and no excluded labels in the final counts.

## Open these figures

- [Fluorescence, previous calls and conditional calls — enlarged cluster](../figs4paper/fucci_fof5_recalibration/conditional/reporter_map_cluster_z35.png).
- [Full field at z=35](../figs4paper/fucci_fof5_recalibration/conditional/reporter_map_z35.png) and [five-slice atlas](../figs4paper/fucci_fof5_recalibration/conditional/reporter_map_slice_atlas.pdf).
- [Scatter plots and decision regions](../figs4paper/fucci_fof5_recalibration/conditional/reporter_scatter_comparison.png).
- [Successful changes and known mismatches](../figs4paper/fucci_fof5_recalibration/conditional/reviewed_changes_and_mismatches.png).
- [Classification stability](../figs4paper/fucci_fof5_recalibration/conditional/classification_stability.png).
- [All 578 assignments](../results/fucci_fof5_recalibration/conditional/cell_reporter_states.csv), [transition table](../results/fucci_fof5_recalibration/conditional/previous_to_conditional.csv), and [summary/provenance](../results/fucci_fof5_recalibration/conditional/summary.json).

## Counts and interpretation

{counts}

**45 previous neither calls become both**, as do **62 previous red-only and 6 previous green-only calls**. All 32 previous both calls remain both. The threshold changes affect **113/578 labels**. The larger change in red-only cells is a direct consequence of applying the lower green cutoff to the opposite channel when identifying clear red-only cells.

The result improves agreement with this small image-review sample, with known mistakes. In the calibration sample, both is supported visually for newly reassigned labels **89 and 116** (previously neither), **444, 566 and 45** (previously red only), and **58** (previously green only). The reserved review supports the change of label **125** from red only to both. However, the classifier also calls **label 108** both despite a neither review, and **labels 209 and 47** both despite red-only reviews. The example figure deliberately includes these three failures alongside successful changes. They have no manual overrides.

## Frozen rules

Use the same 3D volume-weighted foreground mean minus local reference median, with raw TIFF intensities divided by 65,535. No feature selection or feature extraction was repeated.

| Reporter | Lower cutoff | Higher cutoff, unchanged | Bootstrap 5th–95th percentiles of lower cutoff |
| --- | --- | --- | --- |
| Green | {t['green']['low']:.9f} | {t['green']['high']:.9f} | {frozen['bootstrap_intervals']['green'][0]:.9f}–{frozen['bootstrap_intervals']['green'][1]:.9f} |
| Red | {t['red']['low']:.9f} | {t['red']['high']:.9f} | {frozen['bootstrap_intervals']['red'][0]:.9f}–{frozen['bootstrap_intervals']['red'][1]:.9f} |

1. Green only if `G > high_green` and `R <= low_red`.
2. Red only if `R > high_red` and `G <= low_green`.
3. Among the remaining cells, both if `G > low_green` and `R > low_red`; otherwise neither.

Equality belongs to the lower-signal side. A moderate signal in only one channel remains neither under this requested rule. Consequently neither is a residual classification outcome, not proof that neither reporter exists, and is not assigned a biological cell-cycle phase. The new `green_call`/`red_call` fields describe the final state; separate `*_above_low` and `*_above_high` fields expose all gate comparisons.

The one previous missing-score fallback, label 17, is retained unchanged and flagged: nearest 50 unmasked reference pixels, including distance ties. All final score pairs are finite. Mask quality, measurement support and instability remain annotations and never veto the four-state assignment.

## Image calibration and reserved check

The new sample contains **64 previously unreviewed examples**: 40 prior neither, all eight eligible prior both, eight green only and eight red only. Neither examples cover a 4×4 grid of score quantiles. Twenty-five percent of each sampling group was randomly reserved for checking: **48 calibration and 16 check**. Review eligibility requires volume ≥1,000 voxels and maximum cross-section ≥100 pixels; the 48 older reviews and six previously discussed labels are excluded. These conditions affect only the review sample, not the final 578-label output. Sampling enriches selected groups and is not a prevalence estimate.

Each example shows three substantial sections, separate raw channels, a raw merge, brightfield, and fixed enhanced local views. Numeric scores, original identities, sampling groups and predictions are hidden on the sheets. Local display ranges are 0–0.012 green and 0–0.008 red after subtracting the plane's local median reference; when unavailable in that section, the existing volume-weighted reference is used for display and logged. Display enhancement does not change the measurement used for classification. Spatially coherent interior enrichment in at least two sections can be positive even if dim; isolated speckles, bright neighbors and ambiguous localization are not positive review references.

The reviewer is the assistant, with prior exposure to this field. These are provisional image judgments, not independent expert or experimental ground truth. Green/red identity, bleed-through and biological phase are not independently validated by this procedure.

Of the 48 calibration examples, **31 masks were judged usable**, of which **28 had clear judgments in both channels**: seven both, 14 neither, five green only and two red only. Seventeen questionable masks and three ambiguous usable examples are retained in the review files but excluded from fitting. Jointly search lower threshold pairs from zero through the existing higher gates. Maximize balanced agreement for **both versus all other clear reviewed states**; single-positive examples act as negative controls for their opposite channel. Ties favor specificity, then larger normalized thresholds. No expected class proportions, old phase labels or check outcomes enter the fit. The unchanged high gates are permissible if the evidence does not support lowering them.

The model and calibration judgments were frozen before rendering the 16 reserved check examples. Check judgments were frozen before scoring. Thirteen check masks were usable; nine had clear judgments in both channels, while four had an ambiguous channel. Three check masks were questionable. The check contains two clear both, five neither and two green-only examples, **no clear red-only example**, and **no reviewed neither-to-both success**. It therefore does not independently establish the specificity of reassigning red-only cells or the accuracy of the 45 neither-to-both changes.

{scores}

Exact calibration agreement improves from 20/28 to 23/28; reserved-check agreement from 8/9 to 9/9. These small, deliberately selected same-field samples do not establish general accuracy. Two visually green-only calibration cells remain neither because their green score is below the unchanged higher gate. The three false-both calibration calls show a limitation of scalar mean-excess thresholds: spatially misplaced or neighboring fluorescence can overlap genuine dim coexpression in score space. Fitting the lower gates cannot recover that lost spatial information.

- [Calibration sheets](../figs4paper/fucci_fof5_recalibration/conditional/review_calibration.pdf) and [reserved check sheets](../figs4paper/fucci_fof5_recalibration/conditional/review_check.pdf).
- [All review judgments](../results/fucci_fof5_recalibration/conditional/review_annotations.csv), [identity key](../results/fucci_fof5_recalibration/conditional/review_key.csv), [per-example predictions](../results/fucci_fof5_recalibration/conditional/review_predictions.csv), and [agreement counts](../results/fucci_fof5_recalibration/conditional/review_agreement.csv).
- [Prespecified review/fitting protocol](../results/fucci_fof5_recalibration/conditional/review_protocol.json) and [frozen calibration](../results/fucci_fof5_recalibration/conditional/frozen_calibration.json).

## Stability

All sensitivity results are annotations; the delivered state remains one of four classes. Only the lower gates vary in threshold sensitivity; higher gates remain frozen.

The **45 neither-to-both reassignments** need particular caution: **{summary['neither_to_both_stability']['bootstrap_at_least_90pct_n']}/45** retain both in at least 90% of bootstrap fits, and **{summary['neither_to_both_stability']['grid_stable_n']}/45** retain both throughout the ±20% threshold grid. They are especially sensitive to the reference statistic: **0/45** remain both when subtracting the local reference mean instead of its median with the fitted gates held fixed; **20/45** remain both with a trimmed-mean reference. In comparison, **38/45** remain both with the nearer reference ring and **44/45** with the farther ring. No reassigned cell retains both in all 11 measurement settings. These perturbations demonstrate dependence on how background is summarized; they are not separately recalibrated alternative classifiers. [Reassignment-specific stability counts](../results/fucci_fof5_recalibration/conditional/neither_to_both_stability.csv).

- Among 500 stratified calibration bootstrap fits, **{summary['bootstrap_same_all_n']}/578** labels retain their fitted state in every resample. The central 90% range of total both calls is **{summary['bootstrap_both_count_interval'][0]:.0f}–{summary['bootstrap_both_count_interval'][1]:.0f}**. These frequencies describe sensitivity to the reviewed calibration sample and are not posterior probabilities or validation of phase.
- Across a 9×9 grid varying each lower cutoff by ±20%, **{summary['grid_stable_n']}/578** labels retain their state in every setting; total both calls range from **{summary['grid_both_min']} to {summary['grid_both_max']}**.
- **{summary['measurement_complete_n']}/578** have finite score pairs in all 11 measurement settings; **{summary['measurement_stable_all_n']}/578** both have complete measurements and retain their state in all 11. Missing or vanished masks in a perturbation are counted as unavailable, never as neither. Label 17's saved fallback is used for the primary setting only.

{stable}

The 11 settings reuse the original primary, near/far reference, trimmed/mean reference, erosion/dilation, alternate-section and large-section measurements. The historical stability fields remain in the export; the new fields begin with `conditional_`. The lower gates are kept fixed across measurement variants, so this is a perturbation analysis, not a recalibration for each feature.

## Reproduction and scope

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python scripts/classify_fucci_fof5_conditional.py --stage report
python -m unittest discover -s tests -p 'test_fucci*.py'
```

The preparation sequence is `prepare`, image annotations for calibration, `fit`, `review-check`, check annotations, `freeze-check`, then `report`. Existing samples and frozen fits refuse overwriting. The report verifies source tables, measurement hashes, classifier code, frozen reviews, review identities, protocol and bootstrap fits. Raw images and mask/archive inputs are needed to regenerate image panels.

This calibration applies only to the verified **241016/FoF5** image/mask/table combination. It is an exploratory reporter-detection result with explicit known mismatches. The [previous forced calls](fucci_fof5_forced_reporter_states.md) and [conservative calibration](fucci_fof5_recalibration.md) remain available.
"""
    (repo/"docs/fucci_fof5_conditional_reporter_states.md").write_text(text)
