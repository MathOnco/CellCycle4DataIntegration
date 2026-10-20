# FUCCI component-input comparison

The previous main model used aggregated measurements for 21,653 original mask labels. This analysis tests two requested alternatives: the largest-volume component of every label, and only labels that originally had one component. These remain segmentation units rather than independently confirmed cells. The archived input and supplied labels are unchanged.

## Existing threshold classification

The original scatter plots counted all 48,475 component rows. Applying those same gates to one measurement per original mask label changes the class balance substantially:

| Input | Measurement units | G1 | S | G2M | G1S |
|---|---:|---:|---:|---:|---:|
| source_objects | 48,475 | 24.37% | 9.77% | 48.69% | 17.17% |
| aggregated | 21,653 | 23.65% | 0.55% | 75.07% | 0.73% |
| dominant | 21,653 | 23.77% | 0.75% | 74.61% | 0.88% |
| singletons | 13,981 | 22.00% | 0.48% | 76.88% | 0.64% |

The low-green classes (S and G1S under the supplied rules) are much less frequent when satellites no longer count separately. This does not establish their true biological prevalence. Exact counts are in `existing_gate_class_counts.csv`; `source_objects` denotes component rows, while the other rows count original mask labels.

## Refitted model results

| Input | Labels included | G1 | G2M | Uncertain | QC review | Gate-sensitive | Calls passing robustness checks |
|---|---:|---:|---:|---:|---:|---:|---:|
| aggregated | 21,653 | 6,791 | 6,086 | 8,643 | 133 | 37.3% | 59.5% |
| dominant | 21,653 | 6,482 | 5,951 | 9,087 | 133 | 39.7% | 57.4% |
| singletons | 13,981 | 4,701 | 3,872 | 5,408 | 0 | 35.8% | 61.3% |

All provisional categories, including any S or unresolved low-signal calls, are retained in `comparison_summary.csv`. Percentages use each input's own denominator. Gate sensitivity means a most-likely reporter-state change in at least one ±10% gate perturbation. The uncertain flag combines that diagnostic with a posterior score below 0.8; tiny-support QC takes precedence. These thresholds do not establish phase accuracy.

### Before uncertainty flags

| Input | Raw G1 mapping | Raw S mapping | Raw G2M mapping | Raw G1S mapping |
|---|---:|---:|---:|---:|
| aggregated | 11,583 | 0 | 10,070 | 0 |
| dominant | 11,629 | 473 | 9,551 | 0 |
| singletons | 7,324 | 0 | 6,657 | 0 |

The largest-component fit assigns 473 labels to the low-green/high-red state before uncertainty flags. Of these, 473 are flagged uncertain; 462 have posterior scores below 0.8 and 473 change under a gate perturbation (these flags may overlap). A fitted third reporter component therefore does not yield confident S-phase assignments under the stated rules.

## Matched-label comparisons

| Alternative | Same labels compared | Measurement change with reference model held fixed | Additional change from refitting | Combined raw state change | Baseline gate change |
|---|---:|---:|---:|---:|---:|
| dominant | 21,653 | 0.87% | 3.25% | 3.79% | 1.54% |
| singletons | 13,981 | 0.00% | 0.46% | 0.46% | 0.00% |

The changes in the table are separate contrasts and need not add up. The singleton comparison uses the same mask-label IDs before and after refitting, so it isolates refitting from removing multi-component labels. `population_vs_refit_counts.csv` in each alternative directory also shows the reference calls restricted to those same IDs. Excluding multi-component labels changes the studied population; it cannot establish that classification has improved.

## Fitting and stability

- **aggregated:** selected `joint`; joint density wins 28/31 field holdouts; unsupported reporter states: `low_low;low_high`; fit-versus-held-out state disagreement 0.34%; decreasing/increasing the red gate by 10% changes 33.6%/10.3% of calls.
- **dominant:** selected `joint`; joint density wins 28/31 field holdouts; unsupported reporter states: `low_low`; fit-versus-held-out state disagreement 2.56%; decreasing/increasing the red gate by 10% changes 35.0%/10.3% of calls.
- **singletons:** selected `joint`; joint density wins 29/31 field holdouts; unsupported reporter states: `low_low;low_high`; fit-versus-held-out state disagreement 0.41%; decreasing/increasing the red gate by 10% changes 33.1%/9.1% of calls.

For each alternative, both the joint and independent channel models were refitted, with 31 leave-FoF-out comparisons, four acquisition holdouts, and the same 14 sensitivity variants. Fields receive equal total training weight. The existing acquisition gates remain fixed in holdout tests; model selection uses those same folds. Density scores compare candidate models within an input, not biological accuracy between inputs. No size filtering was added to the requested input policies; size exclusions occur only in explicitly labeled sensitivity fits, with predictions retained for every included label.

## Interpretation

Largest-component measurements leave most assignments similar to the aggregated reference, but do not improve the measured gate robustness. Excluding multi-component labels removes 35.4% of the original mask labels and changes very few raw model assignments on the retained labels. Neither alternative establishes a reliable four-phase classification. Fluorescence calibration and independent phase validation remain necessary. No source masks or original phase labels were edited.

## Figures and files

- [All three inputs side by side](../figs4paper/fucci_component_comparison/three_input_scatter_comparison.png)
- [Class balance and stability comparison](../figs4paper/fucci_component_comparison/class_balance_and_stability_comparison.png)
- Largest component per original mask label: [existing-gate seven-panel scatter](../figs4paper/fucci_component_comparison/dominant/baseline_scatter_7_panels.png), [candidate seven-panel scatter](../figs4paper/fucci_component_comparison/dominant/candidate_scatter_7_panels.png), [all 31 FoFs](../figs4paper/fucci_component_comparison/dominant/candidate_scatter_all_31_fofs.pdf), [per-FoF class balance](../figs4paper/fucci_component_comparison/dominant/class_balance_by_fof.png), [sensitivity](../figs4paper/fucci_component_comparison/dominant/sensitivity_and_disagreement.png).
- Single-component mask labels only: [existing-gate seven-panel scatter](../figs4paper/fucci_component_comparison/singletons/baseline_scatter_7_panels.png), [candidate seven-panel scatter](../figs4paper/fucci_component_comparison/singletons/candidate_scatter_7_panels.png), [all 31 FoFs](../figs4paper/fucci_component_comparison/singletons/candidate_scatter_all_31_fofs.pdf), [per-FoF class balance](../figs4paper/fucci_component_comparison/singletons/class_balance_by_fof.png), [sensitivity](../figs4paper/fucci_component_comparison/singletons/sensitivity_and_disagreement.png).

Numeric outputs are under `results/fucci_component_comparison`. Each alternative includes the source-row selection ledger, input measurements, models, probabilities, per-FoF counts, holdouts, and sensitivity results. The original analysis is preserved under `results/fucci_classification`.

## Reproduce

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python scripts/compare_fucci_component_inputs.py --stage all
```

Use `--stage fit` for model computation and `--stage report` to regenerate figures and this report from saved predictions. `--case dominant` or `--case singletons` limits fitting to one alternative; the combined report requires both.
