# FoF5: preserve the original classifier and refine only neither

The original classification **code** is preserved and rerun on the fluorescence measurements. Saved assignments are not prediction inputs. Only when the original function returns **neither** do the lower cutoffs decide whether to change that result to **both**. This implements the user's correction to the earlier conditional method.

## Figures and results

- [Magnified fluorescence / original / refined comparison](../figs4paper/fucci_fof5_recalibration/neither_refinement/reporter_map_cluster_z35.png).
- [Full field at z=35](../figs4paper/fucci_fof5_recalibration/neither_refinement/reporter_map_z35.png) and [five-slice atlas](../figs4paper/fucci_fof5_recalibration/neither_refinement/reporter_map_slice_atlas.pdf).
- [Scatter plots and decision regions](../figs4paper/fucci_fof5_recalibration/neither_refinement/reporter_scatter_comparison.png), [reviewed examples](../figs4paper/fucci_fof5_recalibration/neither_refinement/reviewed_examples.png), and [stability](../figs4paper/fucci_fof5_recalibration/neither_refinement/classification_stability.png).
- [All 578 results](../results/fucci_fof5_recalibration/neither_refinement/cell_reporter_states.csv), [transition table](../results/fucci_fof5_recalibration/neither_refinement/original_to_refined.csv), and [summary with code/input hashes](../results/fucci_fof5_recalibration/neither_refinement/summary.json).

| State | Original / 578 | Refined / 578 | Original at z=35 / 180 | Refined at z=35 / 180 |
| --- | --- | --- | --- | --- |
| Green only | 90 | 90 | 41 | 41 |
| Red only | 72 | 72 | 31 | 31 |
| Both | 32 | 77 | 5 | 21 |
| Neither | 384 | 339 | 103 | 87 |

Exactly **45 neither results become both**. The original code reproduces all 578 historical classifications on these unchanged inputs. Its 90 green-only, 72 red-only and 32 both results pass through the additional step unchanged. All original segmentation labels remain represented by one dominant component, with no excluded or unresolved final assignments.

## Deterministic rule

Use the existing 3D volume-weighted foreground mean minus the per-plane local reference median; TIFF intensities were divided by 65,535. No features or thresholds were refitted for this correction.

| Reporter | Original higher cutoff | Additional lower cutoff |
| --- | --- | --- |
| Green | 0.0065016187699577996 | 0.0024075655915692497 |
| Red | 0.0041954068962762499 | 0.0030311886595230002 |

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

| Review split | Scope | Method | Exact agreement | Both found / reviewed both | False both / reviewed non-both |
| --- | --- | --- | --- | --- | --- |
| calibration | all_reviewed | original | 20/28 | 1/7 | 0/21 |
| calibration | all_reviewed | refined | 21/28 | 3/7 | 1/21 |
| calibration | original_neither | original | 14/18 | 0/2 | 0/16 |
| calibration | original_neither | refined | 15/18 | 2/2 | 1/16 |
| check | all_reviewed | original | 8/9 | 1/2 | 0/7 |
| check | all_reviewed | refined | 8/9 | 1/2 | 0/7 |
| check | original_neither | original | 5/5 | 0/0 | 0/5 |
| check | original_neither | refined | 5/5 | 0/0 | 0/5 |

The two visually supported neither-to-both examples, labels **89 and 116**, are retained. Label **108** still becomes both despite a neither review. The two earlier false-both red-only examples, labels **209 and 47**, now retain red only. The figure shows these cases and an unchanged green-only example. Some original single-positive calls disagree with visual both judgments; those disagreements remain because the original single-positive rules are retained. In particular, check label **125** remains red only despite a both review. Agreement is consequently **21/28 calibration and 8/9 check**, versus **20/28 and 8/9** for the original code.

The check has no clear red-only example or reviewed neither-to-both success. It was previously inspected under the earlier method, so it is not a fresh independent test of this revised routing. The lower thresholds were calibrated under the earlier rule and are reused, rather than claimed optimal for the restricted neither region. The small selected sample does not establish general accuracy or biological phase validity.

## Stability

Only lower thresholds vary in the 500 bootstrap fits and 81-setting ±20% grid. In every setting, the original 90 green-only, 72 red-only and 32 both results are retained by the extra step. Total both calls have a central 90% bootstrap range of **50–88** and a grid range of **49–118**. **489/578** retain their state in all bootstrap fits and **509/578** throughout the grid. These are sensitivity measures, not calibrated probabilities.

Of the 45 neither-to-both changes, **16** retain both in at least 90% of bootstrap fits and **17** throughout the threshold grid. Their dependence on reference subtraction persists: **0/45** remain both with a mean reference at fixed gates. [Counts by measurement setting](../results/fucci_fof5_recalibration/neither_refinement/promoted_cell_stability.csv) report how many still satisfy the full corrected rule. The rule now also requires these cells to remain within the original neither region or to exceed both original high gates; changes in measurements can instead make a cell single positive.

For each of the 11 measurement settings, both stages run again on that setting's numeric scores. The additional step still permits only neither → both relative to the original code on the **same** input. Original-stage results can change across settings; they are not frozen cell assignments. Both sets of changes are shown below. **368/578** have measurements in all settings and **249/578** retain the final state in all 11 with complete measurements.

| Measurement setting | Finite pairs | Missing pairs | Final state changes | Original-stage changes |
| --- | --- | --- | --- | --- |
| primary | 578 | 0 | 0 | 0 |
| near_reference | 574 | 4 | 30 | 22 |
| far_reference | 577 | 1 | 37 | 21 |
| trimmed_reference | 577 | 1 | 67 | 42 |
| mean_reference | 577 | 1 | 145 | 101 |
| erode_1px | 506 | 72 | 60 | 44 |
| erode_2px | 369 | 209 | 49 | 40 |
| dilate_1px | 577 | 1 | 36 | 24 |
| even_z | 577 | 1 | 45 | 33 |
| odd_z | 574 | 4 | 47 | 33 |
| large_cross_sections | 576 | 2 | 32 | 22 |

The [variant results](../results/fucci_fof5_recalibration/neither_refinement/variant_reporter_states.csv) expose both freshly computed stages. The all-cell export retains historical annotations, with new stability/review fields prefixed `refinement_`. Fixed cutoffs across changed measurements measure sensitivity, not separately recalibrated alternatives.

## Reproduce

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python scripts/refine_fucci_fof5_neither.py
python -m unittest discover -s tests -p 'test_fucci*.py'
```

The CLI reproduces this verified 241016/FoF5 snapshot, checking source, original code, frozen calibration and review hashes. Image regeneration requires the raw images and matching mask archive. The reusable classifier operates on supplied numeric scores. Tests verify that original code is called anew, changed measurements can change its decision, saved labels do not determine predictions, and the only added transition is neither → both, including gate boundaries.

The [earlier conditional outputs](fucci_fof5_conditional_reporter_states.md) are preserved as history and superseded for current use by this report.
