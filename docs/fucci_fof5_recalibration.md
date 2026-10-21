# FoF5 local-background reporter recalibration

Completed 2026-10-21 for **241016 / FoF5 only**. All **578 original segmentation labels** are retained, using the largest connected component of each label. These are the same measurement units used in the preceding dominant-component comparison; their identity as individual biological nuclei is not independently established.

## Open these figures first

- [Fluorescence beside the new reporter map, z=35](../figs4paper/fucci_fof5_recalibration/reporter_map_z35.png) and [magnified cluster](../figs4paper/fucci_fof5_recalibration/reporter_map_cluster_z35.png).
- [Old C1/C2 and new calls beside fluorescence](../figs4paper/fucci_fof5_recalibration/old_new_comparison_z35.png), with [the same cluster enlarged](../figs4paper/fucci_fof5_recalibration/old_new_comparison_cluster_z35.png).
- [Raw versus corrected scatter plots](../figs4paper/fucci_fof5_recalibration/reporter_scatter_comparison.png), [measurement stability](../figs4paper/fucci_fof5_recalibration/measurement_stability.png), and [review agreement](../figs4paper/fucci_fof5_recalibration/review_agreement.png).
- [Six previously discussed cells](../figs4paper/fucci_fof5_recalibration/previously_discussed_cells.png) and [five-slice PDF atlas](../figs4paper/fucci_fof5_recalibration/reporter_map_slice_atlas.pdf).

White outlines in fluorescence panels identify the same dominant components colored in the classification panels. Display limits are unchanged from the earlier verification figures and fixed across slices. All calls use 3D measurements; a displayed section can contain only a small part of an object. The z=35 denominator counts every intersecting selected component, including small intersections.

## Result and interpretation

The fitted scores for both channels are **mean fluorescence above a local unmasked reference**. Thresholds are learned from clear image judgments; old phase labels and class proportions are not fitting targets. Weak signal, uncertainty about the threshold, sensitivity to measurement choices, inadequate measurement support, and reviewed questionable masks are retained as unresolved.

| Reporter state | Primary setting | Stable in all 11 settings | Delivered (all 578) | Delivered at z=35 (180) |
| --- | --- | --- | --- | --- |
| Green only | 55 | 33 | 31 (5.4%) | 25 |
| Red only | 36 | 16 | 16 (2.8%) | 14 |
| Both reporters | 15 | 4 | 1 (0.2%) | 1 |
| Unresolved | 472 | 525 | 530 (91.7%) | 140 |

The primary setting already includes threshold uncertainty and minimum measurement support. The next column additionally requires identical reporter states in all 11 prespecified settings. The delivered map then marks 20 reviewed questionable masks unresolved; this changes 5 otherwise resolved automatic calls. No label is removed from the denominator. An unresolved label is not assigned G1S, quiescence, death, or a negative biological state.

The corrected scatter plot shows 577/578 labels with finite coordinates. Label(s) 17 lack a usable local reference and cannot be positioned on that scatter; they remain in the exported results and all counts as unresolved. The original raw-intensity scatter contains all 578 labels.

The earlier labels remain available unchanged:

| Previous result | Full stack (578) | z=35 intersections (180) |
| --- | --- | --- |
| C1 G1 | 163 | 57 |
| C1 G1S | 1 | 0 |
| C1 S | 0 | 0 |
| C1 G2M | 414 | 123 |
| C2 G1 | 205 | 66 |
| C2 S | 0 | 0 |
| C2 G2M | 157 | 44 |
| C2 uncertain | 212 | 70 |
| C2 qc_review | 4 | 0 |

These counts do **not** establish a new cell-cycle composition. Reporter detection is the measured target. Under the still inferred PIP-FUCCI-like interpretation, green only is G1-like, red only S-like, and both G2/M-like. Exact construct/tag identity and phase accuracy remain unconfirmed. Grant et al. distinguish these reporter combinations using their known construct and validate transitions with independent imaging and experimental measurements; that evidence is not available for these cells. [Primary reporter reference](https://pmc.ncbi.nlm.nih.gov/articles/PMC6342071/).

## Measurements and feature selection

1. Reuse the verified native alignment of the 70-plane mask and images. Raw 16-bit TIFF intensities are divided by 65,535. Each dominant component's volume and full-stack raw mean are checked against the new CellProfiler table. Image hashes are checked against the earlier verification manifest; no source image, mask, table or old prediction is edited.
2. For each component and z plane, use unmasked pixels at distances greater than 3 and at most 12 XY pixels from its boundary as the primary local reference. All original segmentation labels, including satellite components, are excluded from reference pixels. A reference needs at least 50 pixels in that plane. The primary background statistic is the reference median.
3. Compare six predefined fluorescence features: foreground mean, median, or 75th percentile minus the local reference, either in intensity units or divided by local robust variability (1.4826 × MAD, with a one-count numerical floor). Scores are weighted averages of per-plane differences, with foreground pixel count as weight. Median and percentile features are therefore **pooled per-plane summaries, not whole-volume percentiles**. Signed differences are retained.
4. Choose one feature per channel by leave-one-cell-out balanced agreement on clear, usable calibration examples only. Fit a single cutoff; ties prefer specificity and then a larger threshold. Morphology, texture, old labels and class balance do not enter reporter prediction. Mask geometry is used for measurement and quality checks.
5. Refit the cutoff in 500 stratified bootstrap resamples of the calibration examples, retaining the chosen feature. Scores above the 95th-percentile cutoff are positive; scores at or below the 5th-percentile cutoff are not detected; intermediate scores are ambiguous. These bands describe threshold sensitivity conditional on this sample and feature, not calibrated phase probabilities or complete uncertainty.

| Channel | Selected score | Positive / not detected references | Threshold | Bootstrap 5th–95th percentile | LOO balanced agreement |
| --- | --- | --- | --- | --- | --- |
| green | mean_excess | 6 / 12 | 0.0065016 | 0.0063821–0.0085066 | 100.0% |
| red | mean_excess | 5 / 15 | 0.0041954 | 0.0031994–0.0049148 | 86.7% |

Leave-one-cell-out scores were used for feature selection and are not an unbiased performance estimate after selection. Both selected features are the first, simplest candidate in the predefined ordering. See [all six feature comparisons](../results/fucci_fof5_recalibration/feature_comparison_calibration_only.csv) and [the frozen model](../results/fucci_fof5_recalibration/frozen_calibration.json).

Local reference pixels can contain diffuse fluorescence, out-of-focus signal or unsegmented structures. They are not experimental negative controls. No flat-field correction, channel-unmixing correction or validation across acquisitions is inferred from this pilot.

The preceding fluorescence audit used a pooled local mean as its diagnostic reference. This pilot's primary reference is a per-plane median, so the numerical excesses differ from that audit; the mean-reference setting is included in the stability analysis.

## Image review and separate check

The sample contains 48 examples drawn across a 4 × 4 grid of preliminary green/red contrast quantiles, with volume at least 1,000 voxels and a largest cross-section of at least 100 pixels. Random assignment gives 32 calibration and 16 check examples (seed 20261021). The six previously discussed labels are excluded. Sampling is deliberately broad across fluorescence and is not a prevalence sample.

Each review shows three substantial cross-sections, separate channels, fixed fourfold display enhancement, merged fluorescence, brightfield, and mask outlines. Original IDs, numeric measurements, old classes and new predictions are hidden. The reviewer is the assistant, with prior exposure to the overall field. These are provisional image judgments, not an independent human annotation or experimental ground truth.

- Calibration: 32 reviewed, 21 masks marked usable, 11 questionable. Only clear per-channel judgments with usable masks enter fitting.
- Separate check: 16 reviewed, 7 usable masks, 9 questionable. Features, cutoffs, bootstrap bands, support rules, stability rules and handling of questionable masks were frozen before viewing these examples. The judgments were then frozen before scoring. The check did not trigger any threshold refit.
- Positive means coherent localized interior signal across at least two displayed sections; not detected means no convincing localized signal even with the fixed enhanced display; ambiguous covers weak or spatially uncertain signal.
- [Calibration review PDF](../figs4paper/fucci_fof5_recalibration/review_calibration.pdf), [check review PDF](../figs4paper/fucci_fof5_recalibration/review_check.pdf), [all judgments and notes](../results/fucci_fof5_recalibration/review_annotations.csv), and [identity key](../results/fucci_fof5_recalibration/review_key.csv) are saved.

### Check-set agreement, usable masks only

| Channel | Method | Called / clear reviews | Agree / called | Positive found / reviewed positive | Not detected found / reviewed not detected |
| --- | --- | --- | --- | --- | --- |
| green | Old absolute gate | 6/6 | 2/6 | 2/2 | 0/4 |
| green | New point threshold | 6/6 | 6/6 | 2/2 | 4/4 |
| green | New + threshold uncertainty | 5/6 | 5/5 | 1/2 | 4/4 |
| green | New + all measurement settings | 5/6 | 5/5 | 1/2 | 4/4 |
| red | Old absolute gate | 7/7 | 3/7 | 1/1 | 2/6 |
| red | New point threshold | 7/7 | 7/7 | 1/1 | 6/6 |
| red | New + threshold uncertainty | 7/7 | 7/7 | 1/1 | 6/6 |
| red | New + all measurement settings | 7/7 | 7/7 | 1/1 | 6/6 |

The table evaluates automatic channel calls **before applying manual mask flags**. Ambiguous image judgments are excluded from agreement denominators but retained in the review files. Abstentions count against coverage. The full audit also reports all reviewed masks, including those marked questionable. With only 7 usable check masks, these fractions are descriptive and cannot establish transfer, sensitivity or specificity in a new field.

Among the usable check masks, 6 have clear judgments in both channels. 3 have at least one visibly positive reporter; 2 receive the same automatic stable reporter state. There are 0 conflicting resolved automatic states among the 6 clear two-channel judgments. This comparison has very little positive support and does not validate four biological phases. No usable double-positive example was identified in either review split, so the combined double-positive state has no clean reviewed example supporting it here. Read per-example outcomes in [review_predictions.csv](../results/fucci_fof5_recalibration/review_predictions.csv).

## Stability and unresolved labels

Keep the fitted thresholds fixed while changing the measurement: reference rings 2–8 and 5–20 pixels; reference trimmed mean or mean; foreground erosion by 1 or 2 XY pixels and dilation by 1 pixel without entering another label; even or odd z planes; and cross-sections at least half the component's maximum area. These are XY perturbations, not isotropic 3D erosion or physical-distance calibration.

Each setting requires at least 100 valid foreground voxels, three valid planes, a maximum original cross-section of at least 25 pixels, and local-reference coverage for at least 80% of that setting's eligible foreground volume. Short or thin objects can therefore become unresolved, particularly under erosion or alternate-plane selection. The all-settings rule is intentionally conservative and was set before the check review.

| Setting | State changes versus primary | Green only | Red only | Both | Unresolved |
| --- | --- | --- | --- | --- | --- |
| Primary reference | 0 | 55 | 36 | 15 | 472 |
| Reference 2–8 px | 9 | 52 | 35 | 14 | 477 |
| Reference 5–20 px | 6 | 55 | 41 | 16 | 466 |
| Reference trimmed mean | 10 | 52 | 37 | 13 | 476 |
| Reference mean | 48 | 40 | 27 | 11 | 500 |
| Mask erosion 1 px | 24 | 51 | 32 | 7 | 488 |
| Mask erosion 2 px | 31 | 47 | 32 | 6 | 493 |
| Mask dilation 1 px | 7 | 55 | 34 | 14 | 475 |
| Even z planes | 16 | 52 | 37 | 9 | 480 |
| Odd z planes | 17 | 53 | 37 | 7 | 481 |
| Larger cross-sections | 11 | 54 | 37 | 12 | 475 |

The following breakdown counts each unresolved label once, prioritizing reviewed mask concerns, inadequate support, neither reporter detected, threshold uncertainty, and then sensitivity to measurement choices:

| Primary unresolved reason (no double counting) | Labels |
| --- | --- |
| neither reporter detected | 227 |
| insufficient measurement support | 166 |
| threshold uncertainty | 67 |
| sensitive to measurement choice | 50 |
| reviewed mask questionable | 20 |

All contributing reasons are also saved. These counts overlap and must not be summed:

| Reason (overlapping) | Labels |
| --- | --- |
| neither reporter detected | 234 |
| insufficient measurement support | 166 |
| sensitive to measurement choice | 79 |
| threshold uncertainty | 72 |
| reviewed mask questionable | 20 |
| missing local reference | 1 |

Mask review covered 48 examples, leaving **530 masks unreviewed**. A stable automatic reporter state does not certify that its segmentation corresponds to one intact nucleus. Apparent thin edge fragments and possible merged structures remain an important limitation. No segmentation repair was performed.

## Previously discussed examples

These examples were excluded from calibration and the separate review sample. They are useful for following the same cells from the previous audit into the new map, but are not an additional validation set.

| CellposeLabel | C1 | C2 | Green excess | Red excess | Delivered state |
| --- | --- | --- | --- | --- | --- |
| 16 | G1 | G1 | 0.003642 | 0.001233 | Unresolved |
| 42 | G2M | G1 | 0.002118 | 0.001581 | Unresolved |
| 63 | G2M | G2M | 0.070985 | 0.002045 | Green only |
| 127 | G2M | G1 | 0.001488 | 0.001874 | Unresolved |
| 220 | G1 | uncertain | 0.080488 | 0.001284 | Green only |
| 410 | G2M | G2M | 0.005400 | 0.030039 | Red only |

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
