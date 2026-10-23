# FoF5: conditional thresholds for four reporter states

**Superseded for current use:** the user requested retention of the original classification code and lower gates only for its neither results. See [the corrected method and results](fucci_fof5_neither_refinement.md). The earlier method below also changes single-positive calls and is retained as analysis history; its frozen lower-threshold calibration is reused in the correction.

The requested two-stage classifier is implemented for **241016/FoF5**, using all **578 original segmentation labels**, one dominant component per label. Every label receives **green only, red only, both, or neither**. There are zero unresolved assignments and no excluded labels in the final counts.

## Open these figures

- [Fluorescence, previous calls and conditional calls — enlarged cluster](../figs4paper/fucci_fof5_recalibration/conditional/reporter_map_cluster_z35.png).
- [Full field at z=35](../figs4paper/fucci_fof5_recalibration/conditional/reporter_map_z35.png) and [five-slice atlas](../figs4paper/fucci_fof5_recalibration/conditional/reporter_map_slice_atlas.pdf).
- [Scatter plots and decision regions](../figs4paper/fucci_fof5_recalibration/conditional/reporter_scatter_comparison.png).
- [Successful changes and known mismatches](../figs4paper/fucci_fof5_recalibration/conditional/reviewed_changes_and_mismatches.png).
- [Classification stability](../figs4paper/fucci_fof5_recalibration/conditional/classification_stability.png).
- [All 578 assignments](../results/fucci_fof5_recalibration/conditional/cell_reporter_states.csv), [transition table](../results/fucci_fof5_recalibration/conditional/previous_to_conditional.csv), and [summary/provenance](../results/fucci_fof5_recalibration/conditional/summary.json).

## Counts and interpretation

| State | Previous / 578 | Conditional / 578 | Previous at z=35 / 180 | Conditional at z=35 / 180 |
| --- | --- | --- | --- | --- |
| Green only | 90 | 84 | 41 | 39 |
| Red only | 72 | 10 | 31 | 6 |
| Both | 32 | 145 | 5 | 48 |
| Neither | 384 | 339 | 103 | 87 |

**45 previous neither calls become both**, as do **62 previous red-only and 6 previous green-only calls**. All 32 previous both calls remain both. The threshold changes affect **113/578 labels**. The larger change in red-only cells is a direct consequence of applying the lower green cutoff to the opposite channel when identifying clear red-only cells.

The result improves agreement with this small image-review sample, with known mistakes. In the calibration sample, both is supported visually for newly reassigned labels **89 and 116** (previously neither), **444, 566 and 45** (previously red only), and **58** (previously green only). The reserved review supports the change of label **125** from red only to both. However, the classifier also calls **label 108** both despite a neither review, and **labels 209 and 47** both despite red-only reviews. The example figure deliberately includes these three failures alongside successful changes. They have no manual overrides.

## Frozen rules

Use the same 3D volume-weighted foreground mean minus local reference median, with raw TIFF intensities divided by 65,535. No feature selection or feature extraction was repeated.

| Reporter | Lower cutoff | Higher cutoff, unchanged | Bootstrap 5th–95th percentiles of lower cutoff |
| --- | --- | --- | --- |
| Green | 0.002407566 | 0.006501619 | 0.002265244–0.003520859 |
| Red | 0.003031189 | 0.004195407 | 0.002847897–0.003654433 |

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

| Review split | Method | Exact state agreement | Both found / reviewed both | False both / reviewed non-both |
| --- | --- | --- | --- | --- |
| calibration | previous | 20/28 | 1/7 | 0/21 |
| calibration | conditional | 23/28 | 7/7 | 3/21 |
| check | previous | 8/9 | 1/2 | 0/7 |
| check | conditional | 9/9 | 2/2 | 0/7 |

Exact calibration agreement improves from 20/28 to 23/28; reserved-check agreement from 8/9 to 9/9. These small, deliberately selected same-field samples do not establish general accuracy. Two visually green-only calibration cells remain neither because their green score is below the unchanged higher gate. The three false-both calibration calls show a limitation of scalar mean-excess thresholds: spatially misplaced or neighboring fluorescence can overlap genuine dim coexpression in score space. Fitting the lower gates cannot recover that lost spatial information.

- [Calibration sheets](../figs4paper/fucci_fof5_recalibration/conditional/review_calibration.pdf) and [reserved check sheets](../figs4paper/fucci_fof5_recalibration/conditional/review_check.pdf).
- [All review judgments](../results/fucci_fof5_recalibration/conditional/review_annotations.csv), [identity key](../results/fucci_fof5_recalibration/conditional/review_key.csv), [per-example predictions](../results/fucci_fof5_recalibration/conditional/review_predictions.csv), and [agreement counts](../results/fucci_fof5_recalibration/conditional/review_agreement.csv).
- [Prespecified review/fitting protocol](../results/fucci_fof5_recalibration/conditional/review_protocol.json) and [frozen calibration](../results/fucci_fof5_recalibration/conditional/frozen_calibration.json).

## Stability

All sensitivity results are annotations; the delivered state remains one of four classes. Only the lower gates vary in threshold sensitivity; higher gates remain frozen.

The **45 neither-to-both reassignments** need particular caution: **16/45** retain both in at least 90% of bootstrap fits, and **17/45** retain both throughout the ±20% threshold grid. They are especially sensitive to the reference statistic: **0/45** remain both when subtracting the local reference mean instead of its median with the fitted gates held fixed; **20/45** remain both with a trimmed-mean reference. In comparison, **38/45** remain both with the nearer reference ring and **44/45** with the farther ring. No reassigned cell retains both in all 11 measurement settings. These perturbations demonstrate dependence on how background is summarized; they are not separately recalibrated alternative classifiers. [Reassignment-specific stability counts](../results/fucci_fof5_recalibration/conditional/neither_to_both_stability.csv).

- Among 500 stratified calibration bootstrap fits, **411/578** labels retain their fitted state in every resample. The central 90% range of total both calls is **105–158**. These frequencies describe sensitivity to the reviewed calibration sample and are not posterior probabilities or validation of phase.
- Across a 9×9 grid varying each lower cutoff by ±20%, **492/578** labels retain their state in every setting; total both calls range from **110 to 196**.
- **368/578** have finite score pairs in all 11 measurement settings; **242/578** both have complete measurements and retain their state in all 11. Missing or vanished masks in a perturbation are counted as unavailable, never as neither. Label 17's saved fallback is used for the primary setting only.

| Measurement setting | Finite pairs | Missing pairs | State changes |
| --- | --- | --- | --- |
| primary | 578 | 0 | 0 |
| near_reference | 574 | 4 | 20 |
| far_reference | 577 | 1 | 31 |
| trimmed_reference | 577 | 1 | 50 |
| mean_reference | 577 | 1 | 150 |
| erode_1px | 506 | 72 | 48 |
| erode_2px | 369 | 209 | 42 |
| dilate_1px | 577 | 1 | 23 |
| even_z | 577 | 1 | 38 |
| odd_z | 574 | 4 | 38 |
| large_cross_sections | 576 | 2 | 21 |

The 11 settings reuse the original primary, near/far reference, trimmed/mean reference, erosion/dilation, alternate-section and large-section measurements. The historical stability fields remain in the export; the new fields begin with `conditional_`. The lower gates are kept fixed across measurement variants, so this is a perturbation analysis, not a recalibration for each feature.

## Reproduction and scope

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python scripts/classify_fucci_fof5_conditional.py --stage report
python -m unittest discover -s tests -p 'test_fucci*.py'
```

The preparation sequence is `prepare`, image annotations for calibration, `fit`, `review-check`, check annotations, `freeze-check`, then `report`. Existing samples and frozen fits refuse overwriting. The report verifies source tables, measurement hashes, classifier code, frozen reviews, review identities, protocol and bootstrap fits. Raw images and mask/archive inputs are needed to regenerate image panels.

This calibration applies only to the verified **241016/FoF5** image/mask/table combination. It is an exploratory reporter-detection result with explicit known mismatches. The [previous forced calls](fucci_fof5_forced_reporter_states.md) and [conservative calibration](fucci_fof5_recalibration.md) remain available.
