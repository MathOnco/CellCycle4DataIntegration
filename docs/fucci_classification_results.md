# FUCCI classification results

The computational analysis retains all 48,475 exported objects and reconstructs measurements for 21,653 original Cellpose mask labels across 31 FoFs. Each original label is a segmentation unit whose interpretation as one biological nucleus remains provisional. The fitted model is not approved as a replacement for four biological phase labels: it has insufficient support for low_low, low_high, and calls are sensitive to red-channel calibration. Independent phase accuracy has not been established.

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

There are 24,737 objects of eight voxels or fewer, but only 133 original mask labels consist entirely of such components. Integrated intensity and volume are additive across components of a source mask label; their ratio reconstructs its mean intensity. Medians, textures, and per-component percentile cores are not treated as additive nuclear measurements.

The original masks available for 241016/1, 241016/14 reproduce exported component counts and volumes. Other fields retain the source label grouping without individual image verification. These are original mask labels, not newly validated biological cells.

Applying the supplied gates to reconstructed mask-label means gives:

| Folder | G1S | G1 | S | G2M |
|---|---:|---:|---:|---:|
| 231005 | 0.04% | 0.32% | 0.04% | 99.61% |
| 2409 | 1.14% | 6.20% | 2.27% | 90.39% |
| 2410 | 0.79% | 30.03% | 0.40% | 68.78% |

## Candidate model and evaluation

The selected candidate is `joint`. Both candidates use log10(intensity / supplied acquisition gate), unequal reporter-state frequencies, and equal total training weight per FoF. The joint candidate is a four-state diagonal Gaussian mixture; the simpler comparator fits the channels independently. State means are constrained to their appropriate sides of the supplied gates. This preserves an explicit calibration assumption and cannot establish that those gates are biologically correct. No field is forced to contain equal state proportions.

The joint model's mean advantage over the independent model in held-out log density is 0.1676; it wins in 28/31 fields. The descriptive paired-field bootstrap interval is [0.11975093303313775, 0.2128351506759717]. Only four acquisitions are available. The same folds select a candidate, so these are model-selection diagnostics rather than a separate final test. Acquisition holdouts retain the supplied gate constants and do not demonstrate calibration of an entirely new experiment.

At posterior score 0.8, 88.2% of mask labels pass the model-confidence threshold alone. Gate changes of plus/minus 10% in either channel change 37.3% of calls; these labels also receive an uncertain flag. The resulting coverage after gate-sensitivity and tiny-support flags is 59.5%. This is a declared robustness rule rather than an experimentally calibrated error rate.

| Provisional disposition | Mask labels | Percent of all labels |
|---|---:|---:|
| G1 | 6,791 | 31.36% |
| S | 0 | 0.00% |
| G2M | 6,086 | 28.11% |
| low signal phase unresolved | 0 | 0.00% |
| uncertain | 8,643 | 39.92% |
| qc review | 133 | 0.61% |

These categories are mutually exclusive and retain all 21,653 mask labels in the denominator. Tiny-support QC takes precedence over uncertainty; overlapping diagnostic flags are also retained separately. The per-FoF counts are in `disposition_by_fof.csv`.

Fitted and held-out calls differ for 0.3% of labels. Candidate reporter-to-phase mappings differ from mask-label baseline gates for 36.4%. These are stability and agreement measures, not biological accuracy. The low/low state is reported as `low_signal_phase_unresolved`, and labels made entirely of tiny components receive `qc_review`. Every label remains in the frequency denominator. The two low-green states have fewer than 5 effective weighted labels in the fitted mixture, so the model does not establish a four-state population. The supplied labels remain intact for comparison.

The 14 fitted sensitivity variants change 0.0% to 42.8% of calls. Variants include gate changes, initialization, fit-only size exclusions, field weighting, and largest-component intensity summaries. Median/core variants use a descriptive feature-scale alignment fitted on this dataset; it is not background correction and is not used in held-out evaluations. The object-level sensitivity model weights siblings together, so split fragments do not gain extra training weight.

## Image review and remaining validation

Local raw images are available for 12/31 FoFs. Small fully occupied bounding boxes provide an image-to-table intensity check: 12 fields match the sampled measurements. Exact masks are available for 2 different fields. Their intersection currently gives 0 fields ready for mask-based background calibration. Complete matching images and masks are required to perform that calibration.

The review PDF contains 72 candidates spanning confidence, disagreements, reporter states, and small supports. Crosses mark largest-component centers, not segmentation outlines; display stretches are shared within a field and channel. The annotation sheet has 72 rows marked `unreviewed`. Rerunning the review stage preserves human annotations and retains earlier candidates that are no longer selected, marked `in_current_review_set=False`. Per-page PNGs and crop coordinates are included for traceability. The mask sheets show both a single slice and the projection of all z slices.

The sheets support human inspection but do not constitute independent phase validation. Exact reporter documentation and matched time-lapse, EdU, DNA-content, or another independent phase reference remain necessary for that step. See [visual inspection notes](fucci_visual_review.md) for the distinction between artifact inspection and experimental annotations.

## Run the analysis

```bash
MPLCONFIGDIR=/tmp/fucci-mpl XDG_CACHE_HOME=/tmp/fucci-cache OPENBLAS_NUM_THREADS=1 \
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
