#!/usr/bin/env python3
"""Compare aggregated masks, their largest components, and single-component masks."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "fucci_mpl_cache"))
os.environ.setdefault("XDG_CACHE_HOME", str(Path(tempfile.gettempdir()) / "fucci_xdg_cache"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from fucci_analysis.data import (STATES, PHASES, load_inputs, aggregate_mask_labels,
                                 gate_coordinates, gates, sha256, write_json)
from fucci_analysis.evaluate import evaluate_models, sensitivity, export_predictions
from fucci_analysis.model import model_from_dict
from fucci_analysis.outputs import figures, PHASE_COLORS

CASES = {"dominant": "Largest component per original mask label",
         "singletons": "Single-component mask labels only"}
DISPOSITIONS = ["G1", "S", "G2M", "low_signal_phase_unresolved", "uncertain", "qc_review"]


def select_inputs(objects, original, case):
    """Choose source rows first, then reconstruct one-component measurement units."""
    if case not in CASES:
        raise ValueError(f"Unknown input policy: {case}")
    eligible = original if case == "dominant" else original[original.n_components == 1]
    chosen = objects.set_index("object_id", drop=False).loc[eligible.largest_object_id].reset_index(drop=True)
    if not chosen.mask_label_id.is_unique or len(chosen) != len(eligible):
        raise ValueError("Selection must contain exactly one source object per retained mask label")
    if case == "dominant":
        expected = objects.groupby("mask_label_id").volume.max().reindex(chosen.mask_label_id)
        np.testing.assert_array_equal(chosen.volume, expected)
    else:
        np.testing.assert_array_equal(objects.groupby("mask_label_id").size().reindex(chosen.mask_label_id), 1)
    labels = aggregate_mask_labels(chosen)
    provenance = original[["mask_label_id", "volume", "n_components", "largest_component_fraction", "baseline_phase"]].rename(
        columns={"volume": "original_mask_volume", "n_components": "original_n_components",
                 "largest_component_fraction": "original_largest_component_fraction",
                 "baseline_phase": "aggregated_baseline_phase"})
    labels = labels.merge(provenance, on="mask_label_id", how="left", validate="one_to_one", sort=False)
    np.testing.assert_array_equal(labels.baseline_phase, chosen.cellCycle)
    return chosen, labels


def fit_case(case, objects, original, config, root):
    out = root / case
    out.mkdir(parents=True, exist_ok=True)
    chosen, labels = select_inputs(objects, original, case)
    local = {**config, "expected_rows": len(chosen), "analysis_unit": CASES[case]}
    write_json(out / "config.json", local)
    policy = objects[["object_id", "mask_label_id", "volume", "cellCycle"]].copy()
    policy["used_for_fit_and_prediction"] = policy.object_id.isin(chosen.object_id)
    policy["original_label_retained"] = policy.mask_label_id.isin(labels.mask_label_id)
    policy["selection_reason"] = np.where(policy.used_for_fit_and_prediction, "included",
        "satellite_component_not_selected" if case == "dominant" else "multi_component_mask_label_excluded")
    policy.to_csv(out / "source_row_selection.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    labels.to_csv(out / "input_measurements.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    print(f"{case}: {len(chosen):,} source components, {labels.field_id.nunique()} fields", flush=True)
    selected, fitted, oof, selection = evaluate_models(labels, local, out)
    print(f"{case}: selected {selected}; running the 14 sensitivity variants", flush=True)
    object_p, gate_sensitive = sensitivity(labels, chosen, fitted, selected, local, out)
    predicted, _ = export_predictions(chosen, labels, fitted, oof, object_p, local, out, gate_sensitive)
    # Core exporter uses a generic mask-label unit; specify this analysis's measurement unit.
    predicted["unit"] = case + "_component_input_unverified_nucleus"
    predicted.to_csv(out / "mask_label_predictions.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    counts = pd.crosstab(predicted.field_id, predicted.provisional_phase).reindex(columns=DISPOSITIONS, fill_value=0)
    counts["denominator"] = predicted.groupby("field_id").size()
    np.testing.assert_array_equal(counts[DISPOSITIONS].sum(axis=1), counts.denominator)
    counts.to_csv(out / "disposition_by_fof.csv")
    write_json(out / "selection_manifest.json", {
        "policy": CASES[case], "original_objects": len(objects), "original_mask_labels": len(original),
        "selected_objects": len(chosen), "retained_mask_labels": len(labels),
        "excluded_source_components": len(objects)-len(chosen),
        "excluded_original_mask_labels": len(original)-len(labels), "fields": labels.field_id.nunique(),
        "source_identity_checks_passed": True, "largest_volume_or_single_component_check_passed": True,
        "original_phase_labels_preserved": True, "additional_size_filter_applied": False,
        "largest_component_tie_rule": "First maximum-volume component in the deterministic loaded source-row order",
        "note": "Original mask labels are segmentation units, not independently validated cells"})


def load_predictions(path):
    return pd.read_csv(path, dtype={c: str for c in ["folder", "Date", "FoF", "CellposeLabel"]})


def summarize(repo, root, figs):
    reference_dir = repo / "results/fucci_classification"
    reference = load_predictions(reference_dir / "mask_label_predictions.csv.gz")
    ref_model = model_from_dict(json.loads((reference_dir / "reporter_state_model.json").read_text()))
    frames = {"aggregated": reference}
    frames.update({case: load_predictions(root / case / "mask_label_predictions.csv.gz") for case in CASES})
    summaries, contrasts, balance_rows = [], [], []
    for name, frame in frames.items():
        directory = reference_dir if name == "aggregated" else root / name
        selection = json.loads((directory / "model_selection.json").read_text())
        support = json.loads((directory / "state_support.json").read_text())
        sens = pd.read_csv(directory / "sensitivity.csv")
        summary = {"input": name, "mask_labels": len(frame), "fields": frame.field_id.nunique(),
                   "excluded_original_mask_labels": len(reference)-len(frame),
                   "selected_model": selection["selected_model"],
                   "joint_winning_fields": selection["joint_winning_fields"],
                   "joint_log_density_advantage": selection["joint_minus_independent_mean_log_density"],
                   "unsupported_states": ";".join(support["unsupported_states"]),
                   "posterior_pass_fraction": float((frame.confidence >= .8).mean()),
                   "gate_sensitive_fraction": float(frame.gate_sensitive.mean()),
                   "robust_call_fraction": float((~frame.uncertain & ~frame.all_components_tiny).mean()),
                   "fit_vs_oof_disagreement_fraction": float(frame.fit_vs_oof_disagreement.mean()),
                   "baseline_disagreement_fraction": float(frame.baseline_disagreement.mean()),
                   "red_gate_down_changed_fraction": float(sens.loc[sens.variant == "red_gate_x0.9", "changed_calls_fraction"].iloc[0]),
                   "red_gate_up_changed_fraction": float(sens.loc[sens.variant == "red_gate_x1.1", "changed_calls_fraction"].iloc[0])}
        for phase in DISPOSITIONS:
            summary[f"provisional_{phase}_count"] = int(frame.provisional_phase.eq(phase).sum())
        for phase in PHASES:
            summary[f"baseline_{phase}_count"] = int(frame.baseline_phase.eq(phase).sum())
            summary[f"raw_model_{phase}_count"] = int(frame.model_phase_mapping.eq(phase).sum())
        summaries.append(summary)
        for field, sub in frame.groupby("field_id"):
            row = {"input": name, "field_id": field, "mask_labels": len(sub),
                   "gate_sensitive_fraction": sub.gate_sensitive.mean(),
                   "robust_call_fraction": (~sub.uncertain & ~sub.all_components_tiny).mean()}
            for phase in DISPOSITIONS:
                row[f"{phase}_count"] = int(sub.provisional_phase.eq(phase).sum())
            balance_rows.append(row)
        if name == "aggregated":
            continue
        common = reference.set_index("mask_label_id").loc[frame.mask_label_id]
        old = common[[f"p_{s}" for s in STATES]].to_numpy().argmax(1)
        frozen = ref_model.predict_proba(gate_coordinates(frame)).argmax(1)
        new = frame[[f"p_{s}" for s in STATES]].to_numpy().argmax(1)
        contrasts.append({"input": name, "common_mask_labels": len(frame),
            "measurement_only_changed_fraction": float(np.mean(old != frozen)),
            "refitting_changed_fraction_on_new_measurements": float(np.mean(frozen != new)),
            "combined_changed_fraction": float(np.mean(old != new)),
            "baseline_gates_changed_fraction": float(np.mean(common.baseline_phase.to_numpy() != frame.baseline_phase.to_numpy())),
            "note": "All contrasts use identical mask-label IDs; changes are not additive and are not accuracy estimates"})
        pd.crosstab(common.provisional_phase.to_numpy(), frame.provisional_phase.to_numpy(),
                    rownames=["aggregated_reference_on_same_labels"], colnames=[name]).to_csv(directory / "reference_disposition_comparison.csv")
        # Same-label baseline separates population exclusion from re-estimation of the model.
        pd.DataFrame([{"phase": p, "reference_all": int(reference.provisional_phase.eq(p).sum()),
                       "reference_on_retained_labels": int(common.provisional_phase.eq(p).sum()),
                       "refitted_on_retained_labels": int(frame.provisional_phase.eq(p).sum())}
                      for p in DISPOSITIONS]).to_csv(directory / "population_vs_refit_counts.csv", index=False)
    summary = pd.DataFrame(summaries)
    summary.to_csv(root / "comparison_summary.csv", index=False)
    source_counts = pd.read_csv(root / "baseline_counts.csv").groupby("cellCycle").objects.sum()
    gate_summary = pd.DataFrame([{
        "input": "source_objects", "measurement_units": int(source_counts.sum()),
        **{f"baseline_{p}_count": int(source_counts.get(p, 0)) for p in PHASES}
    }] + [{"input": s.input, "measurement_units": int(s.mask_labels),
           **{f"baseline_{p}_count": int(s[f"baseline_{p}_count"]) for p in PHASES}}
          for _, s in summary.iterrows()])
    gate_summary.to_csv(root / "existing_gate_class_counts.csv", index=False)
    pd.DataFrame(contrasts).to_csv(root / "matched_label_contrasts.csv", index=False)
    pd.DataFrame(balance_rows).to_csv(root / "comparison_by_fof.csv", index=False)
    comparison_figures(frames, summary, root, figs)
    write_report(summary, pd.DataFrame(contrasts), repo, root)
    print(summary.to_string(index=False), flush=True)


def comparison_figures(frames, summary, root, figs):
    from fucci_analysis.outputs import save
    from matplotlib.patches import Patch
    titles = {"source_objects": "All component rows", "aggregated": "All components aggregated", "dominant": "Largest component only",
              "singletons": "Single-component labels only"}
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    for col, (name, frame) in enumerate(frames.items()):
        for row, column in enumerate(["model_phase_mapping", "provisional_phase"]):
            ax=axes[row,col]
            for phase in list(PHASES)+["low_signal_phase_unresolved", "uncertain", "qc_review"]:
                sub = frame[frame[column] == phase]
                ax.scatter(sub.green, sub.red, c=PHASE_COLORS[phase], s=4, alpha=.3, linewidths=0, rasterized=True)
            ax.set(xscale="log", yscale="log", xlim=(5e-4, 1), ylim=(5e-3, .2), xlabel="Mean green intensity", ylabel="Mean red intensity",
                   title=f"{titles[name]}; n={len(frame):,}\n"+("Before uncertainty flags" if row==0 else "With uncertainty and QC flags"))
    fig.suptitle("Component-input comparison: model phase mappings are provisional")
    fig.legend(handles=[Patch(color=PHASE_COLORS[p],label=p.replace('_',' ')) for p in [*PHASES,'uncertain','qc_review']],loc='lower center',ncol=6,frameon=False)
    fig.tight_layout(rect=(0,.05,1,.95))
    save(fig, figs / "three_input_scatter_comparison")
    fig, axes = plt.subplots(1, 3, figsize=(16, 5), constrained_layout=True)
    names = summary.input.tolist()
    x = np.arange(len(names))
    for ax, prefix, phases, title in [(axes[0], "baseline", list(PHASES), "Existing gates on each input"),
                                    (axes[1], "provisional", DISPOSITIONS, "Refitted candidate, uncertainty retained")]:
        data = (pd.read_csv(root / "existing_gate_class_counts.csv") if prefix == "baseline"
                else summary.rename(columns={"mask_labels": "measurement_units"}))
        positions = np.arange(len(data))
        bottom = np.zeros(len(data))
        for phase in phases:
            values = 100*data[f"{prefix}_{phase}_count"]/data.measurement_units
            ax.bar(positions, values, bottom=bottom, color=PHASE_COLORS[phase], label=phase.replace("_", " "))
            bottom += values
        ax.set(title=title, ylabel="Percent of included measurement units", ylim=(0, 100))
        ax.set_xticks(positions); ax.set_xticklabels([titles[n].replace(" ", "\n", 1) for n in data.input], fontsize=7)
        ax.legend(fontsize=7, loc="upper center", bbox_to_anchor=(.5, -.16), ncol=2)
    for offset, (column, title, color) in enumerate([
            ("gate_sensitive_fraction", "Changes under gate tests", "#b26342"),
            ("fit_vs_oof_disagreement_fraction", "Fit vs held-out disagreement", "#327e9e"),
            ("robust_call_fraction", "Calls passing confidence + gate checks", "#299477")]):
        axes[2].bar(x+(offset-1)*.25, summary[column]*100, width=.25, label=title, color=color)
    axes[2].set(title="Stability and call coverage", ylabel="Percent of included mask labels", ylim=(0, 100))
    axes[2].set_xticks(x); axes[2].set_xticklabels([titles[n].replace(" ", "\n", 1) for n in names], fontsize=8)
    axes[2].legend(fontsize=7, loc="upper center", bbox_to_anchor=(.5,-.16))
    fig.suptitle("Input selection changes both measurements and population; no independent phase accuracy estimate")
    save(fig, figs / "class_balance_and_stability_comparison")


def write_report(summary, contrasts, repo, root):
    text = "# FUCCI component-input comparison\n\n"
    text += "The previous main model used aggregated measurements for 21,653 original mask labels. This analysis tests two requested alternatives: the largest-volume component of every label, and only labels that originally had one component. These remain segmentation units rather than independently confirmed cells. The archived input and supplied labels are unchanged.\n\n"
    text += "## Existing threshold classification\n\nThe original scatter plots counted all 48,475 component rows. Applying those same gates to one measurement per original mask label changes the class balance substantially:\n\n"
    text += "| Input | Measurement units | G1 | S | G2M | G1S |\n|---|---:|---:|---:|---:|---:|\n"
    gate_summary = pd.read_csv(root / "existing_gate_class_counts.csv")
    for _, s in gate_summary.iterrows():
        percentages = " | ".join(f"{s[f'baseline_{p}_count']/s.measurement_units:.2%}" for p in ["G1", "S", "G2M", "G1S"])
        text += f"| {s.input} | {s.measurement_units:,} | {percentages} |\n"
    text += "\nThe low-green classes (S and G1S under the supplied rules) are much less frequent when satellites no longer count separately. This does not establish their true biological prevalence. Exact counts are in `existing_gate_class_counts.csv`; `source_objects` denotes component rows, while the other rows count original mask labels.\n\n"
    text += "## Refitted model results\n\n| Input | Labels included | G1 | G2M | Uncertain | QC review | Gate-sensitive | Calls passing robustness checks |\n|---|---:|---:|---:|---:|---:|---:|---:|\n"
    for _, s in summary.iterrows():
        text += f"| {s.input} | {s.mask_labels:,} | {s.provisional_G1_count:,} | {s.provisional_G2M_count:,} | {s.provisional_uncertain_count:,} | {s.provisional_qc_review_count:,} | {s.gate_sensitive_fraction:.1%} | {s.robust_call_fraction:.1%} |\n"
    text += "\nAll provisional categories, including any S or unresolved low-signal calls, are retained in `comparison_summary.csv`. Percentages use each input's own denominator. Gate sensitivity means a most-likely reporter-state change in at least one ±10% gate perturbation. The uncertain flag combines that diagnostic with a posterior score below 0.8; tiny-support QC takes precedence. These thresholds do not establish phase accuracy.\n\n"
    text += "### Before uncertainty flags\n\n| Input | Raw G1 mapping | Raw S mapping | Raw G2M mapping | Raw G1S mapping |\n|---|---:|---:|---:|---:|\n"
    for _,s in summary.iterrows():
        text += f"| {s.input} | {s.raw_model_G1_count:,} | {s.raw_model_S_count:,} | {s.raw_model_G2M_count:,} | {s.raw_model_G1S_count:,} |\n"
    dominant=load_predictions(root/'dominant/mask_label_predictions.csv.gz')
    s_like=dominant[dominant.candidate_state=='low_high']
    text += f"\nThe largest-component fit assigns {len(s_like):,} labels to the low-green/high-red state before uncertainty flags. Of these, {int(s_like.uncertain.sum()):,} are flagged uncertain; {int(s_like.posterior_uncertain.sum()):,} have posterior scores below 0.8 and {int(s_like.gate_sensitive.sum()):,} change under a gate perturbation (these flags may overlap). A fitted third reporter component therefore does not yield confident S-phase assignments under the stated rules.\n\n"
    text += "## Matched-label comparisons\n\n| Alternative | Same labels compared | Measurement change with reference model held fixed | Additional change from refitting | Combined raw state change | Baseline gate change |\n|---|---:|---:|---:|---:|---:|\n"
    for _, c in contrasts.iterrows():
        text += f"| {c.input} | {c.common_mask_labels:,} | {c.measurement_only_changed_fraction:.2%} | {c.refitting_changed_fraction_on_new_measurements:.2%} | {c.combined_changed_fraction:.2%} | {c.baseline_gates_changed_fraction:.2%} |\n"
    text += "\nThe changes in the table are separate contrasts and need not add up. The singleton comparison uses the same mask-label IDs before and after refitting, so it isolates refitting from removing multi-component labels. `population_vs_refit_counts.csv` in each alternative directory also shows the reference calls restricted to those same IDs. Excluding multi-component labels changes the studied population; it cannot establish that classification has improved.\n\n"
    text += "## Fitting and stability\n\n"
    for _, s in summary.iterrows():
        text += f"- **{s.input}:** selected `{s.selected_model}`; joint density wins {s.joint_winning_fields}/31 field holdouts; unsupported reporter states: `{s.unsupported_states}`; fit-versus-held-out state disagreement {s.fit_vs_oof_disagreement_fraction:.2%}; decreasing/increasing the red gate by 10% changes {s.red_gate_down_changed_fraction:.1%}/{s.red_gate_up_changed_fraction:.1%} of calls.\n"
    text += "\nFor each alternative, both the joint and independent channel models were refitted, with 31 leave-FoF-out comparisons, four acquisition holdouts, and the same 14 sensitivity variants. Fields receive equal total training weight. The existing acquisition gates remain fixed in holdout tests; model selection uses those same folds. Density scores compare candidate models within an input, not biological accuracy between inputs. No size filtering was added to the requested input policies; size exclusions occur only in explicitly labeled sensitivity fits, with predictions retained for every included label.\n\n"
    text += "## Interpretation\n\nLargest-component measurements leave most assignments similar to the aggregated reference, but do not improve the measured gate robustness. Excluding multi-component labels removes 35.4% of the original mask labels and changes very few raw model assignments on the retained labels. Neither alternative establishes a reliable four-phase classification. Fluorescence calibration and independent phase validation remain necessary. No source masks or original phase labels were edited.\n\n"
    text += "## Figures and files\n\n"
    for filename, title in [("three_input_scatter_comparison.png", "All three inputs side by side"), ("class_balance_and_stability_comparison.png", "Class balance and stability comparison")]:
        text += f"- [{title}](../figs4paper/fucci_component_comparison/{filename})\n"
    for case in CASES:
        text += f"- {CASES[case]}: [existing-gate seven-panel scatter](../figs4paper/fucci_component_comparison/{case}/baseline_scatter_7_panels.png), [candidate seven-panel scatter](../figs4paper/fucci_component_comparison/{case}/candidate_scatter_7_panels.png), [all 31 FoFs](../figs4paper/fucci_component_comparison/{case}/candidate_scatter_all_31_fofs.pdf), [per-FoF class balance](../figs4paper/fucci_component_comparison/{case}/class_balance_by_fof.png), [sensitivity](../figs4paper/fucci_component_comparison/{case}/sensitivity_and_disagreement.png).\n"
    text += "\nNumeric outputs are under `results/fucci_component_comparison`. Each alternative includes the source-row selection ledger, input measurements, models, probabilities, per-FoF counts, holdouts, and sensitivity results. The original analysis is preserved under `results/fucci_classification`.\n\n## Reproduce\n\n```bash\nOPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python scripts/compare_fucci_component_inputs.py --stage all\n```\n\nUse `--stage fit` for model computation and `--stage report` to regenerate figures and this report from saved predictions. `--case dominant` or `--case singletons` limits fitting to one alternative; the combined report requires both.\n"
    (repo / "docs/fucci_component_input_comparison.md").write_text(text)


def baseline_scatter(frame, case, figs):
    from matplotlib.patches import Patch
    from fucci_analysis.outputs import save
    groups=[("All 31 FoFs",frame)]+[(f"Folder {f}",frame[frame.folder==f]) for f in ['231005','2409','2410']]
    groups += [(f"{f}: FoF 1",frame[(frame.folder==f)&(frame.FoF=='1')]) for f in ['231005','2409','2410']]
    fig,axes=plt.subplots(2,4,figsize=(17,8.5),constrained_layout=True)
    for ax,(title,sub) in zip(axes.flat,groups):
        for phase in PHASES:
            d=sub[sub.baseline_phase==phase]
            ax.scatter(d.green,d.red,s=4,c=PHASE_COLORS[phase],alpha=.3,linewidths=0,rasterized=True)
        ax.set(xscale='log',yscale='log',xlim=(5e-4,1),ylim=(5e-3,.2),xlabel='Mean green intensity',ylabel='Mean red intensity',title=f'{title}; n={len(sub):,}')
    axes[1,3].axis('off');axes[1,3].legend(handles=[Patch(color=PHASE_COLORS[p],label=p) for p in PHASES],loc='center',frameon=False)
    fig.suptitle(f'{CASES[case]}\nSupplied threshold rules; all selected input rows shown')
    save(fig,figs/'baseline_scatter_7_panels')


def verify_case_outputs(objects, chosen, current, saved, case, out):
    """Check the requested population, source measurements, scores, and evaluation coverage."""
    if not saved.mask_label_id.is_unique or set(saved.mask_label_id)!=set(current.mask_label_id):
        raise ValueError('Saved predictions do not match the requested selection')
    indexed=current.set_index('mask_label_id').loc[saved.mask_label_id]
    for column in ['volume','green','red','green_gate','red_gate']:
        np.testing.assert_allclose(saved[column],indexed[column],rtol=1e-12,atol=1e-15)
    np.testing.assert_array_equal(saved.largest_object_id,indexed.largest_object_id)
    np.testing.assert_array_equal(saved.baseline_phase,indexed.baseline_phase)
    model=model_from_dict(json.loads((out/'reporter_state_model.json').read_text()))
    np.testing.assert_allclose(saved[[f'p_{s}' for s in STATES]],model.predict_proba(gate_coordinates(saved)),rtol=1e-10,atol=1e-12)
    np.testing.assert_allclose(saved[[f'oof_p_{s}' for s in STATES]].sum(axis=1),1,atol=1e-10)
    ledger=pd.read_csv(out/'source_row_selection.csv.gz')
    assert len(ledger)==len(objects) and ledger.object_id.is_unique
    assert set(ledger.object_id)==set(objects.object_id)
    assert set(ledger.loc[ledger.used_for_fit_and_prediction,'object_id'])==set(chosen.object_id)
    for filename,column in [('held_out_fields.csv','field_id'),('held_out_acquisitions.csv','Date')]:
        folds=pd.read_csv(out/filename,dtype={'held_out':str})
        assert not folds.duplicated(['held_out','model']).any()
        for name in ['joint','independent']:
            sub=folds[folds.model==name]
            assert set(sub.held_out)==set(saved[column])
            np.testing.assert_array_equal(sub.test_labels,saved.groupby(column).size().reindex(sub.held_out))
            np.testing.assert_array_equal(sub.test_labels+sub.train_labels,len(saved))
    write_json(out/'artifact_checks.json',{'all_checks_passed':True,'policy':case,'source_rows_accounted_for':len(objects),
        'selected_objects':len(chosen),'mask_labels':len(saved),'fields':saved.field_id.nunique(),
        'source_measurements_and_phase_labels_match':True,'numeric_model_reproduces_saved_probabilities':True,
        'source_selection_and_all_holdouts_verified':True,'biological_validation':False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["all", "fit", "report"], default="all")
    parser.add_argument("--case", choices=["both", *CASES], default="both")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    root = repo / "results/fucci_component_comparison"
    figs = repo / "figs4paper/fucci_component_comparison"
    root.mkdir(exist_ok=True); figs.mkdir(exist_ok=True)
    config = json.loads((repo / "scripts/fucci_analysis/config.json").read_text())
    previous = json.loads((repo / "results/fucci_classification/input_manifest.json").read_text())
    if sha256(Path(config["archive"]).expanduser()) != previous["archive_sha256"]:
        raise ValueError("Reference and comparison must use the same input archive")
    if args.stage=='report':
        for case in CASES:
            fitted_config=json.loads((root/case/'config.json').read_text())
            if any(fitted_config.get(k)!=v for k,v in config.items() if k!='expected_rows'):
                raise ValueError('Configuration changed; rerun fitting before reporting')
    objects, manifest = load_inputs(config, root)
    original = aggregate_mask_labels(objects)
    if args.stage in ["all", "fit"]:
        for case in CASES if args.case == "both" else [args.case]:
            fit_case(case, objects, original, config, root)
    if args.stage in ["all", "report"]:
        for case in CASES:
            chosen, current = select_inputs(objects, original, case)
            predicted = load_predictions(root / case / "mask_label_predictions.csv.gz")
            verify_case_outputs(objects,chosen,current,predicted,case,root/case)
            dest = figs / case
            dest.mkdir(exist_ok=True)
            figures(chosen, predicted, root / case, dest, unit_description=CASES[case])
            baseline_scatter(predicted, case, dest)
        summarize(repo, root, figs)
    sources = [Path(__file__)] + sorted((repo / "scripts/fucci_analysis").glob("*.py"))
    write_json(root / "implementation_versions.json", {str(p.relative_to(repo)): sha256(p) for p in sources})


if __name__ == "__main__":
    main()
