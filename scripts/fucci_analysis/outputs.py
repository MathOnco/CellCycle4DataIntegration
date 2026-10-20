"""Scientific figures and a report with explicit validation limits."""
from __future__ import annotations

from pathlib import Path
import json

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

from .data import STATES, PHASES, gate_coordinates, write_json
from .model import model_from_dict

COLORS = {"low_low": "#777777", "high_low": "#209c68", "low_high": "#d04b58", "high_high": "#b69a23"}
PHASE_COLORS = {"G1": "#209c68", "G1S": "#6067a5", "S": "#d04b58", "G2M": "#b69a23",
                "low_signal_phase_unresolved": "#6067a5", "uncertain": "#bdbdbd", "qc_review": "#202020"}


def save(fig, path):
    for suffix in ["png", "pdf"]:
        fig.savefig(path.with_suffix(f".{suffix}"), dpi=180, facecolor="white", bbox_inches="tight")
    plt.close(fig)


def scatter_axes(ax, df):
    for state in STATES:
        group = df[(df.candidate_state == state) & ~df.uncertain & ~df.all_components_tiny]
        ax.scatter(group.green, group.red, s=4, alpha=.22, linewidths=0, c=COLORS[state], rasterized=True)
    group = df[df.uncertain | df.all_components_tiny]
    ax.scatter(group.green, group.red, s=5, alpha=.35, linewidths=0, c="#a5a5a5", rasterized=True)
    ax.set(xscale="log", yscale="log", xlim=(5e-4, 1), ylim=(5e-3, .2),
           xlabel="Mean green intensity", ylabel="Mean red intensity")
    ax.grid(alpha=.15, linewidth=.5)


def figures(objects, labels, out, figs, unit_description="Original mask labels"):
    for frame in [objects, labels]:
        if not (frame.green.between(5e-4, 1) & frame.red.between(5e-3, .2)).all():
            raise ValueError("Scatter limits would hide measurements; expand the limits before plotting")
    fig, axes = plt.subplots(2, 4, figsize=(17, 8.5), constrained_layout=True)
    groups = [("All 31 FoFs", labels)] + [(f"Folder {f}", labels[labels.folder == f]) for f in ["231005", "2409", "2410"]]
    groups += [(f"{f}: FoF 1", labels[(labels.folder == f) & (labels.FoF == "1")]) for f in ["231005", "2409", "2410"]]
    for ax, (name, frame) in zip(axes.flat, groups):
        scatter_axes(ax, frame)
        ax.set_title(f"{name}; {len(frame):,} mask labels", fontsize=10)
    axes[1, 3].axis("off")
    axes[1, 3].legend(handles=[Patch(color=COLORS[s], label=f"{s.replace('_', '/')} reporter state") for s in STATES] +
                             [Patch(color="#a5a5a5", label="Uncertain or QC review")], loc="center", frameon=False)
    fig.suptitle(f"FUCCI candidate reporter states: {unit_description}\nProvisional phase interpretation; no independent biological validation", fontsize=13)
    save(fig, figs / "candidate_scatter_7_panels")

    fig, axes = plt.subplots(2, 3, figsize=(14, 8), constrained_layout=True)
    for col, folder in enumerate(["231005", "2409", "2410"]):
        for row, (name, df) in enumerate([("Input objects", objects), (unit_description, labels)]):
            d = df[df.folder == folder]
            for state, phase in enumerate(PHASES):
                group = d[d.baseline_state == state]
                axes[row, col].scatter(group.green, group.red, s=3, c=PHASE_COLORS[phase], alpha=.25, linewidths=0, rasterized=True)
            axes[row, col].set(xscale="log", yscale="log", xlim=(5e-4, 1), ylim=(5e-3, .2), xlabel="Mean green", ylabel="Mean red")
            axes[row, col].set_title(f"{folder}: {name}, n={len(d):,}")
    fig.legend(handles=[Patch(color=PHASE_COLORS[p], label=p) for p in PHASES], loc="lower center", ncol=4, bbox_to_anchor=(.5,-.04))
    fig.suptitle("Effect of the measurement unit on the supplied gates")
    save(fig, figs / "objects_vs_mask_labels")

    fields = sorted(labels.field_id.unique(), key=lambda s: tuple(map(int, s.split("/"))))
    field_scatter_atlas(labels, fields, out, figs, unit_description)
    fig, axes = plt.subplots(1, 2, figsize=(15, 12), sharey=True, constrained_layout=True)
    for ax, column, title, categories in [
        (axes[0], "baseline_phase", "Supplied gates applied to mask-label means", list(PHASES)),
        (axes[1], "provisional_phase", "Candidate calls, including uncertainty", ["G1", "S", "G2M", "low_signal_phase_unresolved", "uncertain", "qc_review"])]:
        matrix = pd.crosstab(labels.field_id, labels[column]).reindex(index=fields, columns=categories, fill_value=0)
        matrix = matrix.div(matrix.sum(axis=1), axis=0)*100
        left = np.zeros(len(fields))
        for category in categories:
            ax.barh(range(len(fields)), matrix[category], left=left, color=PHASE_COLORS[category], label=category.replace("_", " "))
            left += matrix[category].to_numpy()
        ax.set(title=title, xlabel="Percent of original mask labels", xlim=(0, 100))
        ax.set_yticks(range(len(fields)))
        ax.set_yticklabels([f"{f} (n={int(labels.field_id.eq(f).sum()):,})" for f in fields], fontsize=8)
        ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(.5,-.065), ncol=2)
    axes[0].invert_yaxis()
    fig.suptitle(f"{unit_description}: class distributions by FoF; all included labels in denominator")
    save(fig, figs / "class_balance_by_fof")

    validation = pd.read_csv(out / "held_out_fields.csv")
    scores = validation.pivot(index="held_out", columns="model", values="mean_log_density").reindex(fields)
    delta = scores.joint-scores.independent
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar(range(len(fields)), delta, color=np.where(delta >= 0, "#327e9e", "#d27b46"))
    ax.axhline(0, c="black", lw=.7)
    ax.set_xticks(range(len(fields))); ax.set_xticklabels(fields, rotation=90, fontsize=8)
    ax.set(ylabel="Joint minus independent held-out log density", title="Density-model comparison by held-out FoF; not phase accuracy")
    fig.tight_layout(); save(fig, figs / "held_out_model_comparison")

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.3), constrained_layout=True)
    bins = np.linspace(0, np.log10(max(objects.volume.max(), labels.volume.max()))+.05, 60)
    axes[0].hist(np.log10(objects.volume), bins=bins, alpha=.65, label="Objects")
    axes[0].hist(np.log10(labels.volume), bins=bins, alpha=.65, label="Mask labels")
    axes[0].set(xlabel="log10(volume in voxels)", ylabel="Count"); axes[0].legend()
    original_components = labels.get("original_n_components", labels.n_components)
    original_largest_fraction = labels.get("original_largest_component_fraction", labels.largest_component_fraction)
    axes[1].hist(original_components, bins=np.arange(.5, original_components.max()+1.5), color="#7158a8")
    axes[1].set(xlabel="Original components per included mask label", ylabel="Mask labels", yscale="log")
    axes[2].hist(original_largest_fraction, bins=40, color="#268c76")
    axes[2].set(xlabel="Fraction of volume in the largest component", ylabel="Mask labels", yscale="log")
    fig.suptitle(f"Segmentation audit: {unit_description}\nOriginal component counts and volume fractions describe the included source labels")
    save(fig, figs / "segmentation_audit")
    sensitivity_figure(labels, out, figs)


def field_scatter_atlas(labels, fields, out, figs, unit_description="Original mask labels"):
    """Show every FoF with its own gate constants and the saved diagnostic boundary."""
    model = model_from_dict(json.loads((out / "reporter_state_model.json").read_text()))
    green, red = np.meshgrid(np.geomspace(5e-4, 1, 180), np.geomspace(5e-3, .2, 180))
    handles = [Patch(color=COLORS[s], label=s.replace("_", "/")) for s in STATES]
    handles += [Patch(color="#a5a5a5", label="Uncertain or QC"),
                Line2D([0], [0], color="black", ls="--", label="Supplied gates"),
                Line2D([0], [0], color="black", label="Equal high/low vs high/high posterior")]
    rows = []
    with PdfPages(figs / "candidate_scatter_all_31_fofs.pdf") as pdf:
        for page, start in enumerate(range(0, len(fields), 8), start=1):
            fig, axes = plt.subplots(2, 4, figsize=(17, 9))
            page_fields = fields[start:start+8]
            for ax, field in zip(axes.flat, page_fields):
                frame = labels[labels.field_id == field]
                scatter_axes(ax, frame)
                gates = frame[["green_gate", "red_gate"]].iloc[0].to_numpy(float)
                ax.axvline(gates[0], c="black", ls="--", lw=.7, alpha=.6)
                ax.axhline(gates[1], c="black", ls="--", lw=.7, alpha=.6)
                grid = np.log10(np.column_stack([green.ravel(), red.ravel()]) / gates)
                scores = model.predict_proba(grid)
                ax.contour(green, red, (scores[:, 1]-scores[:, 3]).reshape(green.shape),
                           levels=[0], colors="black", linewidths=.8)
                unassigned = (frame.uncertain | frame.all_components_tiny).mean()
                ax.set_title(f"{field}; n={len(frame):,}; flagged={unassigned:.1%}", fontsize=10)
                rows.append({"field_id": field, "pdf_page": page, "plotted_mask_labels": len(frame),
                             "uncertain_or_qc_fraction": unassigned,
                             "png": f"candidate_scatter_by_fof_{page:02}.png"})
            for ax in axes.flat[len(page_fields):]:
                ax.axis("off")
            fig.suptitle(f"{unit_description}: candidate reporter states by FoF — page {page}\nGreen/red state order; boundary conditional on supplied gates; no phase validation", fontsize=12)
            fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=9, frameon=False)
            fig.tight_layout(rect=(0, .075, 1, .93))
            pdf.savefig(fig)
            fig.savefig(figs / f"candidate_scatter_by_fof_{page:02}.png", dpi=180, facecolor="white")
            plt.close(fig)
    pd.DataFrame(rows).to_csv(out / "scatter_field_index.csv", index=False)


def sensitivity_figure(labels, out, figs):
    variants = pd.read_csv(out / "sensitivity.csv").dropna(subset=["changed_calls_fraction"])
    variants = variants.sort_values("changed_calls_fraction", ascending=False)
    fig, axes = plt.subplots(1, 2, figsize=(15, 7), gridspec_kw={"width_ratios": [1.2, 1]})
    axes[0].barh(range(len(variants)), 100*variants.changed_calls_fraction, color="#327e9e")
    axes[0].set_yticks(range(len(variants)))
    axes[0].set_yticklabels(variants.variant.str.replace("_", " "), fontsize=8)
    axes[0].invert_yaxis()
    axes[0].set(xlabel="Changed most likely reporter state (%)", title=f"Sensitivity over all {len(labels):,} included mask labels")
    for i, value in enumerate(100*variants.changed_calls_fraction):
        axes[0].text(value+.3, i, f"{value:.2f}%", va="center", fontsize=8)
    axes[0].set_xlim(0, max(100*variants.changed_calls_fraction)*1.2)
    categories = ["G1", "G2M", "uncertain", "qc_review", "S", "low_signal_phase_unresolved"]
    categories = [c for c in categories if c in labels.provisional_phase.unique()]
    counts = pd.crosstab(labels.baseline_phase, labels.provisional_phase).reindex(index=PHASES, columns=categories, fill_value=0)
    image = axes[1].imshow(counts, cmap="Blues", aspect="auto")
    for row in range(len(counts)):
        for col in range(len(categories)):
            value = counts.iloc[row, col]
            axes[1].text(col, row, f"{value:,}", ha="center", va="center",
                         color="white" if value > counts.to_numpy().max()*.55 else "black")
    axes[1].set_xticks(range(len(categories)))
    axes[1].set_xticklabels([c.replace("_", " ") for c in categories], rotation=25, ha="right")
    axes[1].set_yticks(range(len(PHASES))); axes[1].set_yticklabels(PHASES)
    axes[1].set(xlabel="Provisional disposition", ylabel="Baseline gates on mask-label means",
                title="Agreement counts; no independent phase truth")
    fig.colorbar(image, ax=axes[1], shrink=.7, label="Mask labels")
    fig.suptitle("Robustness and baseline disagreement")
    fig.tight_layout(); save(fig, figs / "sensitivity_and_disagreement")


def feature_diagnostics(objects, labels, out):
    rows = []
    for date, d in objects.groupby("Date"):
        for feature in ["median", "core"]:
            for channel in ["green", "red"]:
                valid = (d[f"{channel}_{feature}"] > 0) & np.isfinite(d[f"{channel}_{feature}"])
                rows.append({"Date": date, "unit": "exported_object", "feature": f"{channel}_{feature}",
                             "rows": len(d), "valid_rows": int(valid.sum()),
                             "median_ratio_to_object_mean": float(np.median(d.loc[valid, f"{channel}_{feature}"] / d.loc[valid, channel])),
                             "spearman_with_object_mean": d.loc[valid, [channel, f"{channel}_{feature}"]].corr(method="spearman").iloc[0,1],
                             "tiny_object_fraction": d.tiny_object.mean()})
    pd.DataFrame(rows).to_csv(out / "feature_comparison.csv", index=False)
    summary = {"source_objects": len(objects), "mask_labels": len(labels),
               "tiny_objects": int(objects.tiny_object.sum()), "all_tiny_mask_labels": int(labels.all_components_tiny.sum()),
               "global_median_core_volume": float(objects.core_volume.median()),
               "core_one_voxel_objects": int((objects.core_volume == 1).sum()),
               "median_largest_component_fraction": float(labels.largest_component_fraction.median()),
               "aggregate_measurement_rule": "sum integrated intensity / sum voxel volume; median and signal-core features are not averaged into nuclear features"}
    write_json(out / "measurement_summary.json", summary)


def report(objects, labels, inventory, selection, config, repo, out, figs, review_count):
    sensitivity = pd.read_csv(out / "sensitivity.csv")
    state_support = json.loads((out / "state_support.json").read_text())
    baseline = pd.crosstab(labels.folder, labels.baseline_phase, normalize="index").reindex(columns=PHASES, fill_value=0)*100
    state_counts = labels.provisional_phase.value_counts().to_dict()
    categories = ["G1", "S", "G2M", "low_signal_phase_unresolved", "uncertain", "qc_review"]
    disposition = pd.crosstab(labels.field_id, labels.provisional_phase).reindex(columns=categories, fill_value=0)
    disposition.columns = [f"{c}_count" for c in categories]
    disposition["denominator_mask_labels"] = labels.groupby("field_id").size()
    disposition["source_objects"] = labels.groupby("field_id").n_components.sum()
    np.testing.assert_array_equal(disposition[[f"{c}_count" for c in categories]].sum(axis=1),
                                  disposition.denominator_mask_labels)
    disposition.to_csv(out / "disposition_by_fof.csv")
    annotations = pd.read_csv(out / "image_review_annotations.csv")
    unreviewed = int(annotations.review_status.eq("unreviewed").sum())
    status = {
        "1_input_and_baseline": "complete; all source rows retained and supplied labels reproduced",
        "2_segmentation": f"table audit complete; {int(inventory.mask_components_match.sum())}/31 masks compatible by component volumes; biological nuclei not independently confirmed",
        "3_features_and_calibration": f"feature comparison complete; {int(inventory.calibration_ready.sum())}/31 fields have both compatible raw images and exact masks; background calibration pending",
        "4_candidate_classifier": "complete; gate-anchored reporter-state models, provisional phase mapping",
        "5_stability_evaluation": "complete; 31 field holdouts, 4 acquisition holdouts, sensitivity variants; no independent phase accuracy estimate",
        "6_review_and_validation": f"{review_count} current review candidates prepared; {unreviewed} rows await expert review; independent phase validation pending",
        "7_reproducible_package": "complete for computational artifacts; experimental validation dependencies remain",
    }
    write_json(out / "workflow_status.json", status)
    metrics = {"objects": len(objects), "mask_labels": len(labels), "fields": labels.field_id.nunique(),
               "selected_model": selection["selected_model"],
               "confidence_threshold": config["confidence_threshold"],
               "confidence_coverage": float((labels.confidence >= config["confidence_threshold"]).mean()),
               "gate_sensitive_fraction": float(labels.gate_sensitive.mean()),
               "robust_call_coverage": float((~labels.uncertain & ~labels.all_components_tiny).mean()),
               "unsupported_reporter_states": state_support["unsupported_states"],
               "approved_as_four_phase_replacement": False,
               "fit_vs_oof_disagreement_fraction": float(labels.fit_vs_oof_disagreement.mean()),
               "baseline_disagreement_fraction": float(labels.baseline_disagreement.mean()),
               "provisional_calls": state_counts, "independent_biological_validation": False}
    write_json(out / "summary.json", metrics)
    table = "| Folder | G1S | G1 | S | G2M |\n|---|---:|---:|---:|---:|\n"
    for folder, row in baseline.iterrows():
        table += f"| {folder} | " + " | ".join(f"{row[p]:.2f}%" for p in PHASES) + " |\n"
    call_table = "| Provisional disposition | Mask labels | Percent of all labels |\n|---|---:|---:|\n"
    for category in categories:
        count = state_counts.get(category, 0)
        call_table += f"| {category.replace('_', ' ')} | {count:,} | {count/len(labels):.2%} |\n"
    sens = sensitivity.dropna(subset=["changed_calls_fraction"])
    text = f"""# FUCCI classification results

The computational analysis retains all {len(objects):,} exported objects and reconstructs measurements for {len(labels):,} original Cellpose mask labels across 31 FoFs. Each original label is a segmentation unit whose interpretation as one biological nucleus remains provisional. The fitted model is not approved as a replacement for four biological phase labels: it has insufficient support for {', '.join(state_support['unsupported_states'])}, and calls are sensitive to red-channel calibration. Independent phase accuracy has not been established.

The available computational stages and review-sheet generation are complete. Expert annotations, full image calibration, and independent phase validation remain pending. Original-mask aggregation is a measurement-unit sensitivity analysis; it does not establish that every resulting label is a cell. The existing object-level phase labels are preserved.

## Figures

- [Seven-panel candidate scatter plot](../figs4paper/fucci_classification/candidate_scatter_7_panels.png)
- [All 31 FoFs, including supplied gates and the candidate boundary (PDF)](../figs4paper/fucci_classification/candidate_scatter_all_31_fofs.pdf)
- [Class distributions for every FoF](../figs4paper/fucci_classification/class_balance_by_fof.png)
- [Sensitivity and baseline disagreement](../figs4paper/fucci_classification/sensitivity_and_disagreement.png)
- [Objects versus original mask labels](../figs4paper/fucci_classification/objects_vs_mask_labels.png)
- [Image review sheets (PDF)](../figs4paper/fucci_classification/image_review.pdf) and [mask review sheets (PDF)](../figs4paper/fucci_classification/mask_review.pdf)

## Inputs and baseline

The input is `Archive (6).zip`; checksums, schemas, package versions, parameters, and the upstream code revision are recorded in `results/fucci_classification/input_manifest.json`. The strict threshold comparisons reproduce every supplied phase label. The upstream G2M exclusion strip is recorded as a flag and removes no rows from this analysis.

## Segmentation units

There are {int(objects.tiny_object.sum()):,} objects of eight voxels or fewer, but only {int(labels.all_components_tiny.sum()):,} original mask labels consist entirely of such components. Integrated intensity and volume are additive across components of a source mask label; their ratio reconstructs its mean intensity. Medians, textures, and per-component percentile cores are not treated as additive nuclear measurements.

The original masks available for {', '.join(inventory.loc[inventory.mask_components_match, 'field_id'])} reproduce exported component counts and volumes. Other fields retain the source label grouping without individual image verification. These are original mask labels, not newly validated biological cells.

Applying the supplied gates to reconstructed mask-label means gives:

{table}
## Candidate model and evaluation

The selected candidate is `{selection['selected_model']}`. Both candidates use log10(intensity / supplied acquisition gate), unequal reporter-state frequencies, and equal total training weight per FoF. The joint candidate is a four-state diagonal Gaussian mixture; the simpler comparator fits the channels independently. State means are constrained to their appropriate sides of the supplied gates. This preserves an explicit calibration assumption and cannot establish that those gates are biologically correct. No field is forced to contain equal state proportions.

The joint model's mean advantage over the independent model in held-out log density is {selection['joint_minus_independent_mean_log_density']:.4f}; it wins in {selection['joint_winning_fields']}/31 fields. The descriptive paired-field bootstrap interval is {selection['paired_field_bootstrap_95_interval']}. Only four acquisitions are available. The same folds select a candidate, so these are model-selection diagnostics rather than a separate final test. Acquisition holdouts retain the supplied gate constants and do not demonstrate calibration of an entirely new experiment.

At posterior score {config['confidence_threshold']}, {metrics['confidence_coverage']:.1%} of mask labels pass the model-confidence threshold alone. Gate changes of plus/minus {config['gate_perturbation_fraction']:.0%} in either channel change {metrics['gate_sensitive_fraction']:.1%} of calls; these labels also receive an uncertain flag. The resulting coverage after gate-sensitivity and tiny-support flags is {metrics['robust_call_coverage']:.1%}. This is a declared robustness rule rather than an experimentally calibrated error rate.

{call_table}
These categories are mutually exclusive and retain all {len(labels):,} mask labels in the denominator. Tiny-support QC takes precedence over uncertainty; overlapping diagnostic flags are also retained separately. The per-FoF counts are in `disposition_by_fof.csv`.

Fitted and held-out calls differ for {metrics['fit_vs_oof_disagreement_fraction']:.1%} of labels. Candidate reporter-to-phase mappings differ from mask-label baseline gates for {metrics['baseline_disagreement_fraction']:.1%}. These are stability and agreement measures, not biological accuracy. The low/low state is reported as `low_signal_phase_unresolved`, and labels made entirely of tiny components receive `qc_review`. Every label remains in the frequency denominator. The two low-green states have fewer than {config['minimum_component_effective_labels']} effective weighted labels in the fitted mixture, so the model does not establish a four-state population. The supplied labels remain intact for comparison.

The {len(sens)} fitted sensitivity variants change {sens.changed_calls_fraction.min():.1%} to {sens.changed_calls_fraction.max():.1%} of calls. Variants include gate changes, initialization, fit-only size exclusions, field weighting, and largest-component intensity summaries. Median/core variants use a descriptive feature-scale alignment fitted on this dataset; it is not background correction and is not used in held-out evaluations. The object-level sensitivity model weights siblings together, so split fragments do not gain extra training weight.

## Image review and remaining validation

Local raw images are available for {int(inventory.raw_images_available.sum())}/31 FoFs. Small fully occupied bounding boxes provide an image-to-table intensity check: {int(inventory.image_measurements_match.sum())} fields match the sampled measurements. Exact masks are available for {int(inventory.mask_components_match.sum())} different fields. Their intersection currently gives {int(inventory.calibration_ready.sum())} fields ready for mask-based background calibration. Complete matching images and masks are required to perform that calibration.

The review PDF contains {review_count} candidates spanning confidence, disagreements, reporter states, and small supports. Crosses mark largest-component centers, not segmentation outlines; display stretches are shared within a field and channel. The annotation sheet has {unreviewed} rows marked `unreviewed`. Rerunning the review stage preserves human annotations and retains earlier candidates that are no longer selected, marked `in_current_review_set=False`. Per-page PNGs and crop coordinates are included for traceability. The mask sheets show both a single slice and the projection of all z slices.

The sheets support human inspection but do not constitute independent phase validation. Exact reporter documentation and matched time-lapse, EdU, DNA-content, or another independent phase reference remain necessary for that step. See [visual inspection notes](fucci_visual_review.md) for the distinction between artifact inspection and experimental annotations.

## Run the analysis

```bash
MPLCONFIGDIR=/tmp/fucci-mpl XDG_CACHE_HOME=/tmp/fucci-cache OPENBLAS_NUM_THREADS=1 \\
python scripts/run_fucci_classification.py --stage all
```

The default archive path is in `scripts/fucci_analysis/config.json`. Override it with `--archive`. Stages `audit`, `fit`, `review`, and `report` can be run separately in order. Outputs go to `results/fucci_classification` and `figs4paper/fucci_classification`. Checks run with `python -m unittest discover -s tests -p 'test_fucci_analysis.py'`.

Install the recorded dependencies with `python -m pip install -r scripts/fucci_analysis/requirements.txt` in your analysis environment. Review/report reject changes to the archive or fitted-analysis configuration before modifying provenance. `prediction_provenance.json` records the inputs associated with saved calls; `implementation_versions.json` records the source/configuration checksums used to render the current report. External image and mask paths are listed in `image_inventory.csv`; the archive and raw images are not bundled into this analysis package.

## Artifacts

- `object_mapping.csv.gz` and `object_predictions.csv.gz`: all source rows, original labels, parent mapping, QC flags, candidate scores, and object-level sensitivity results.
- `mask_label_measurements.csv.gz` and `mask_label_predictions.csv.gz`: additive measurements, baseline gates, candidate states, confidence, held-out predictions, and provisional phases.
- `segmentation_audit_by_fof.csv`, `class_balance_by_fof.csv`, and `confidence_coverage.csv`: counts with explicit denominators.
- `held_out_fields.csv`, `held_out_acquisitions.csv`, and `sensitivity.csv`: evaluation diagnostics.
- `image_inventory.csv`, `image_value_checks.csv`, and `image_review_annotations.csv`: image compatibility and pending annotations.
- `workflow_status.json`: completed computational stages and outstanding validation dependencies.
- `artifact_checks.json`: source-row, mapping, probability, denominator, and holdout-coverage checks.
- `scatter_field_index.csv`: figure page for each FoF and the number of plotted labels.

The classifier's biological interpretation is conditional on the PIP-FUCCI-like reporter mapping described in [the implementation plan](fucci_classification_plan.md). The existing phase labels, inferred mapping, and model posterior scores are preserved as distinct evidence sources.
"""
    (repo / "docs/fucci_classification_results.md").write_text(text)
    return metrics
