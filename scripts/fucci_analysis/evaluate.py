"""Field-held-out evaluation and explicitly descriptive sensitivity analyses."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data import gate_coordinates, training_weights, write_json, PHASES, STATES
from .model import make_model


def evaluate_models(labels, config, out):
    x = gate_coordinates(labels)
    field_rows, date_rows = [], []
    oof = {name: np.full((len(labels), 4), np.nan) for name in ["joint", "independent"]}
    for group_column, results in [("field_id", field_rows), ("Date", date_rows)]:
        for fold, group in enumerate(sorted(labels[group_column].unique())):
            test = labels[group_column].eq(group).to_numpy()
            train = ~test
            assert not set(labels.loc[train, group_column]) & set(labels.loc[test, group_column])
            assert not set(labels.loc[train, "mask_label_id"]) & set(labels.loc[test, "mask_label_id"])
            weight = training_weights(labels.loc[train])
            for name in ["joint", "independent"]:
                model = make_model(name, config).fit(x[train], weight, config["seed"])
                proba = model.predict_proba(x[test])
                np.testing.assert_allclose(proba.sum(axis=1), 1, atol=1e-10)
                row = {"held_out": group, "model": name, "train_labels": int(train.sum()),
                       "test_labels": int(test.sum()), "converged": model.converged,
                       "mean_log_density": float(np.average(model.score_samples(x[test]),
                                                            weights=training_weights(labels.loc[test]))),
                       "baseline_agreement": float(np.mean(proba.argmax(axis=1) == labels.loc[test, "baseline_state"])),
                       "confidence_coverage": float(np.mean(proba.max(axis=1) >= config["confidence_threshold"])),
                       "interpretation": "Reporter-density validation; supplied gates fixed before each split"}
                results.append(row)
                if group_column == "field_id":
                    oof[name][test] = proba
            if group_column == "field_id" and (fold + 1) % 5 == 0:
                print(f"  completed {fold + 1}/31 field holdouts", flush=True)
    field_results = pd.DataFrame(field_rows)
    date_results = pd.DataFrame(date_rows)
    field_results.to_csv(out / "held_out_fields.csv", index=False)
    date_results.to_csv(out / "held_out_acquisitions.csv", index=False)
    scores = field_results.pivot(index="held_out", columns="model", values="mean_log_density")
    delta = scores.joint - scores.independent
    # Paired field bootstrap is descriptive; only four acquisitions are available.
    rng = np.random.default_rng(config["seed"])
    means = delta.to_numpy()[rng.integers(0, len(delta), (2000, len(delta)))].mean(axis=1)
    lower, upper = np.quantile(means, [.025, .975])
    # Prefer the smaller model unless joint density improves in both mean and most fields.
    selected = "joint" if delta.mean() > 0 and (delta > 0).mean() > .5 else "independent"
    selection = {"selected_model": selected, "criterion": "Higher mean held-out field log density and wins in a majority of fields; otherwise simpler independent model",
                 "joint_minus_independent_mean_log_density": float(delta.mean()),
                 "joint_winning_fields": int((delta > 0).sum()),
                 "paired_field_bootstrap_95_interval": [float(lower), float(upper)],
                 "bootstrap_caveat": "Descriptive field resampling; four acquisitions limit independence",
                 "nested_validation": False,
                 "selection_caveat": "These folds select a candidate; a separate independent test set is needed for final performance",
                 "biological_accuracy_estimated": False}
    write_json(out / "model_selection.json", selection)
    fitted = make_model(selected, config).fit(x, training_weights(labels), config["seed"])
    write_json(out / "reporter_state_model.json", fitted.as_dict())
    support = np.average(fitted.predict_proba(x), axis=0, weights=training_weights(labels))*len(labels)
    write_json(out / "state_support.json", {
        "effective_weighted_labels": dict(zip(STATES, support.tolist())),
        "minimum_effective_labels_diagnostic": config["minimum_component_effective_labels"],
        "unsupported_states": [s for s, mass in zip(STATES, support) if mass < config["minimum_component_effective_labels"]],
        "biological_label_replacement_approved": False,
        "reason": "No independent phase validation; inspect state support and gate sensitivity before using biological labels"})
    return selected, fitted, oof[selected], selection


def sensitivity(labels, objects, fitted, selected, config, out):
    base_x = gate_coordinates(labels)
    reference = fitted.predict_proba(base_x)
    rows = []
    gate_sensitive = np.zeros(len(labels), dtype=bool)

    def compare(name, train_x, train_frame, test_x=base_x, train_seed=None, detail=""):
        model = make_model(selected, config).fit(train_x, training_weights(train_frame),
                    config["seed"] if train_seed is None else train_seed)
        p = model.predict_proba(test_x)
        row = {"variant": name, "training_labels": len(train_frame), "evaluated_labels": len(labels),
               "changed_calls_fraction": float(np.mean(p.argmax(axis=1) != reference.argmax(axis=1))),
               "mean_absolute_probability_change": float(np.abs(p-reference).mean()),
               "confidence_coverage": float(np.mean(p.max(axis=1) >= config["confidence_threshold"])),
               "converged": model.converged, "detail": detail}
        rows.append(row)
        return p

    for axis, channel in enumerate(["green", "red"]):
        for multiplier in [1-config["gate_perturbation_fraction"], 1+config["gate_perturbation_fraction"]]:
            shifted = base_x.copy()
            shifted[:, axis] -= np.log10(multiplier)
            p = compare(f"{channel}_gate_x{multiplier}", shifted, labels, shifted,
                    detail="Both fit and prediction use perturbed supplied gates; no rows removed")
            gate_sensitive |= p.argmax(1) != reference.argmax(1)
    for cutoff in [8, 50, 100]:
        eligible = labels.volume > cutoff
        compare(f"fit_volume_gt_{cutoff}", base_x[eligible], labels.loc[eligible],
                detail="Sensitivity only; excluded from this fit, predicted for every source label")
    for offset in [1, 7, 29]:
        compare(f"initialization_seed_plus_{offset}", base_x, labels, train_seed=config["seed"]+offset)
    for suffix in ["", "_median", "_core"]:
        columns = [f"largest_green{suffix}", f"largest_red{suffix}"]
        alt = labels[columns].to_numpy(float)
        valid = np.isfinite(alt).all(axis=1) & (alt > 0).all(axis=1)
        if not valid.all():
            rows.append({"variant": f"largest_component{suffix or '_mean'}", "detail":
                f"Not fitted: {int((~valid).sum())} labels have nonpositive or missing alternate features"})
            continue
        alternate_x = np.log10(alt / labels[["green_gate", "red_gate"]].to_numpy())
        if suffix:
            # Feature-scale alignment for this descriptive sensitivity only.
            # It is not an illumination correction and is never used in validation folds.
            for date in labels.Date.unique():
                ii = labels.Date.eq(date).to_numpy()
                alternate_x[ii] -= np.median(alternate_x[ii] - base_x[ii], axis=0)
        compare(f"largest_component{suffix or '_mean'}", alternate_x, labels, alternate_x,
                detail="Largest-component measurement; median/core scale aligned on this dataset for descriptive comparison only")
    unweighted = make_model(selected, config).fit(base_x, np.ones(len(labels)), config["seed"])
    p = unweighted.predict_proba(base_x)
    rows.append({"variant": "pooled_labels_without_field_weights", "training_labels": len(labels),
                 "evaluated_labels": len(labels), "changed_calls_fraction": float(np.mean(p.argmax(1) != reference.argmax(1))),
                 "mean_absolute_probability_change": float(np.abs(p-reference).mean()),
                 "confidence_coverage": float(np.mean(p.max(1) >= config["confidence_threshold"])),
                 "converged": unweighted.converged, "detail": "Checks influence of unequal field sizes"})
    pd.DataFrame(rows).to_csv(out / "sensitivity.csv", index=False)
    pd.DataFrame({"mask_label_id": labels.mask_label_id, "gate_sensitive": gate_sensitive}).to_csv(out / "gate_sensitivity_by_label.csv.gz", index=False)
    ox = gate_coordinates(objects)
    object_model = make_model(selected, config).fit(ox, training_weights(objects, object_level=True), config["seed"])
    object_p = object_model.predict_proba(ox)
    write_json(out / "object_sensitivity_model.json", object_model.as_dict())
    return object_p, gate_sensitive


def export_predictions(objects, labels, fitted, oof, object_p, config, out, gate_sensitive):
    labels = labels.copy()
    p = fitted.predict_proba(gate_coordinates(labels))
    for j, state in enumerate(STATES):
        labels[f"p_{state}"] = p[:, j]
        labels[f"oof_p_{state}"] = oof[:, j]
    labels["candidate_state"] = np.asarray(STATES)[p.argmax(1)]
    labels["model_phase_mapping"] = PHASES[p.argmax(1)]
    labels["confidence"] = p.max(1)
    labels["entropy"] = -(p * np.log(np.maximum(p, 1e-300))).sum(1) / np.log(4)
    labels["posterior_uncertain"] = labels.confidence < config["confidence_threshold"]
    labels["gate_sensitive"] = gate_sensitive
    labels["uncertain"] = labels.posterior_uncertain | labels.gate_sensitive
    labels["oof_candidate_state"] = np.asarray(STATES)[oof.argmax(1)]
    labels["oof_confidence"] = oof.max(1)
    labels["fit_vs_oof_disagreement"] = p.argmax(1) != oof.argmax(1)
    labels["baseline_disagreement"] = labels.model_phase_mapping != labels.baseline_phase
    labels["provisional_phase"] = labels.model_phase_mapping
    labels.loc[labels.candidate_state == "low_low", "provisional_phase"] = "low_signal_phase_unresolved"
    labels.loc[labels.uncertain, "provisional_phase"] = "uncertain"
    labels.loc[labels.all_components_tiny, "provisional_phase"] = "qc_review"
    labels["biology_validated"] = False
    labels["unit"] = "original_mask_label_unverified_nucleus"
    labels.to_csv(out / "mask_label_predictions.csv.gz", index=False)
    join_columns = ["mask_label_id", "candidate_state", "provisional_phase", "confidence", "uncertain",
                    "baseline_phase", "all_components_tiny", "posterior_uncertain", "gate_sensitive"] + [f"p_{s}" for s in STATES]
    predicted = objects.merge(labels[join_columns], on="mask_label_id", how="left", validate="many_to_one")
    assert len(predicted) == len(objects) and predicted.object_id.is_unique and predicted.confidence.notna().all()
    assert np.array_equal(predicted.object_id, objects.object_id)
    for j, state in enumerate(STATES):
        predicted[f"object_sensitivity_p_{state}"] = object_p[:, j]
    predicted["object_sensitivity_state"] = np.asarray(STATES)[object_p.argmax(1)]
    predicted["object_vs_parent_state_disagreement"] = predicted.object_sensitivity_state != predicted.candidate_state
    predicted.to_csv(out / "object_predictions.csv.gz", index=False)
    rows = []
    for field_id, d in labels.groupby("field_id"):
        row = {"field_id": field_id, "folder": d.folder.iloc[0], "Date": d.Date.iloc[0], "FoF": d.FoF.iloc[0],
               "denominator_mask_labels": len(d), "source_objects": int(d.n_components.sum()),
               "uncertain_labels": int(d.uncertain.sum()), "all_tiny_labels": int(d.all_components_tiny.sum()),
               "gate_sensitive_labels": int(d.gate_sensitive.sum()),
               "low_signal_labels": int((d.candidate_state == "low_low").sum()),
               "baseline_disagreement_percent": 100*d.baseline_disagreement.mean(),
               "fit_vs_oof_disagreement_percent": 100*d.fit_vs_oof_disagreement.mean()}
        for phase in PHASES:
            row[f"baseline_{phase}_count"] = int(d.baseline_phase.eq(phase).sum())
            row[f"provisional_{phase}_count"] = int(d.provisional_phase.eq(phase).sum())
        for state in STATES:
            row[f"reporter_{state}_count"] = int(d.candidate_state.eq(state).sum())
            row[f"expected_{state}_count"] = d[f"p_{state}"].sum()
        rows.append(row)
    pd.DataFrame(rows).to_csv(out / "class_balance_by_fof.csv", index=False)
    pd.crosstab(labels.baseline_phase, labels.provisional_phase).to_csv(out / "baseline_vs_candidate.csv")
    pd.DataFrame([{"threshold": t, "mask_labels": len(labels), "confidence_pass": int((labels.confidence >= t).sum()),
                   "coverage": float((labels.confidence >= t).mean()), "biological_calibration": False}
                  for t in [.6, .7, .8, .9, .95]]).to_csv(out / "confidence_coverage.csv", index=False)
    return labels, predicted
