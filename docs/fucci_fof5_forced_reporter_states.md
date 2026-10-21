# FoF5: forced assignment to four reporter states

All **578** original segmentation labels receive one of **green only, red only, both, neither**, as requested. There are **zero unresolved assignments**. The 530 previously unresolved labels now have a forced state; the 48 previously resolved calls are unchanged.

## Figures and results

- [Fluorescence beside forced states, enlarged](../figs4paper/fucci_fof5_recalibration/forced/reporter_map_cluster_z35.png).
- [Full field at z=35](../figs4paper/fucci_fof5_recalibration/forced/reporter_map_z35.png) and [old C1/C2 versus forced calls](../figs4paper/fucci_fof5_recalibration/forced/old_new_comparison_z35.png).
- [Forced-state scatter plots](../figs4paper/fucci_fof5_recalibration/forced/reporter_scatter.png) and [five-slice PDF atlas](../figs4paper/fucci_fof5_recalibration/forced/reporter_map_slice_atlas.pdf).
- [All-label result table](../results/fucci_fof5_recalibration/forced/cell_reporter_states.csv), [transition counts](../results/fucci_fof5_recalibration/forced/conservative_to_forced.csv) and [provenance](../results/fucci_fof5_recalibration/forced/summary.json).

| State | Full stack (578) | z=35 intersections (180) |
| --- | --- | --- |
| Green only | 90 | 41 |
| Red only | 72 | 31 |
| Both | 32 | 5 |
| Neither | 384 | 103 |

## Assignment rule

Use the frozen fitted **point** thresholds on the primary 3D local-background measurements: green **0.0065016**, red **0.0041954**. A channel is positive if its mean excess is strictly greater than its threshold; equality counts as not detected. Combining the two binary decisions produces the four states. Neither means below both reporter-detection cutoffs; it is not mapped to a biological phase.

There is no bootstrap uncertainty band, minimum-support exclusion, stability veto or mask-quality veto in the forced state decision. Those flags and the previous conservative calls remain in the result table. The thresholds, feature selection and image-review judgments are unchanged; no model was refitted. Scatter plots retain signed scores and show all 578 labels.

## One missing-measurement fallback

Label 17 contains seven voxels in z=27 and has no unmasked reference pixels in the original local rings. Its missing scores are measured using the nearest unmasked pixels beyond a 3-pixel gap, with at least 50 reference pixels and all ties at the outer distance included. Reference pixels exclude every segmentation label. The fallback subtracts their median from the foreground mean, using the same intensity units as the fitted cutoffs. It is flagged by `forced_reference_fallback` and outlined on the scatter plot.

| Label | Channel | Reference pixels | Outer radius (XY pixels) | Mean excess |
| --- | --- | --- | --- | --- |
| 17 | green | 51 | 30.067 | 0.0087718 |
| 17 | red | 51 | 30.067 | 0.0010463 |

## Export columns and reproduction

`reporter_state`, `green_call` and `red_call` contain the forced calls. `forced_green_score` and `forced_red_score` contain the scores actually used; their source fields identify the fallback. `conservative_reporter_state`, `conservative_unresolved_reasons`, `mask_review`, `stable_across_variants` and the existing measurement-support fields retain the earlier uncertainty information. The [original conservative pilot](fucci_fof5_recalibration.md) remains available.

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python scripts/force_fucci_fof5_reporter_states.py
```
