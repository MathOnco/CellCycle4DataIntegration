# FoF5 spatial verification: Fig. 1A/C-style overlays

The supplied `FoF5_241016_fucci.nucleus.zip` provides the first verified image–mask pair for this analysis. The figure uses the new Saeed feature table from `Archive (6).zip`. No pseudotime analysis or Fig. 1E reconstruction is included.

## Input verification

- **578 original mask labels and 1,314 connected components** match the new table, including parent IDs, component IDs, volumes and bounding boxes.
- All **3,942 component/channel pairs** reproduce their exported 3D mean and integrated intensity from the raw green, red and brightfield images. Maximum absolute mean error: `5e-10` on the normalized 0–1 scale.
- All 70 image planes align in native X/Y/Z coordinates. No registration transform or mask editing was applied.

## Figures

The main figure is a single actual plane at **z=35** of the 70-plane stack (default: the middle plane, z=35). Panel A merges green and red; C1 colors masks using the supplied phase thresholds; C2 colors the same selected masks using the saved refitted model, including uncertainty and QC. The field's 3D assignment totals are below; each panel also states how many selected units intersect its plane.

- **Every exported connected component:** [PNG](../figs4paper/fucci_spatial_verification/241016_5/fig1AC_source_rows_z35.png) · [PDF](../figs4paper/fucci_spatial_verification/241016_5/fig1AC_source_rows_z35.pdf)
- **All components aggregated by original mask label:** [PNG](../figs4paper/fucci_spatial_verification/241016_5/fig1AC_aggregated_z35.png) · [PDF](../figs4paper/fucci_spatial_verification/241016_5/fig1AC_aggregated_z35.pdf)
- **Largest component per original mask label:** [PNG](../figs4paper/fucci_spatial_verification/241016_5/fig1AC_dominant_z35.png) · [PDF](../figs4paper/fucci_spatial_verification/241016_5/fig1AC_dominant_z35.pdf)
- **Only original labels with one component:** [PNG](../figs4paper/fucci_spatial_verification/241016_5/fig1AC_singletons_z35.png) · [PDF](../figs4paper/fucci_spatial_verification/241016_5/fig1AC_singletons_z35.pdf)
- [Largest-component view across z=15, 25, 35, 45, 55 (PDF)](../figs4paper/fucci_spatial_verification/241016_5/fig1AC_dominant_slice_atlas.pdf)
- [Magnified central-region comparison](../figs4paper/fucci_spatial_verification/241016_5/fig1AC_dominant_crop_z35.png)
- [Magnified upper-left cluster](../figs4paper/fucci_spatial_verification/241016_5/fig1AC_dominant_cluster_z35.png)

## Counts in the full 3D field

| Input | Units | Supplied G1 | G1S | S | G2M | Candidate G1 | G2M | Uncertain | QC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| source_rows | 1314 | 378 | 169 | 145 | 622 | — | — | — | — |
| aggregated | 578 | 161 | 1 | 1 | 415 | 215 | 171 | 188 | 4 |
| dominant | 578 | 163 | 1 | 0 | 414 | 205 | 157 | 212 | 4 |
| singletons | 359 | 103 | 1 | 0 | 255 | 144 | 102 | 113 | 0 |

The source-row view colors every measured connected component by its own supplied phase. The aggregated view colors the full original label. The dominant view colors only its largest component. The singleton view colors only labels that originally had one component. Excluded regions retain the underlying brightfield image. No additional size filtering was applied.

## Display and interpretation

Each channel uses a fixed display stretch estimated across all 70 planes: 1st–99.8th percentiles for green/red, 0.5th–99.5th for brightfield, sampled every sixteenth X/Y pixel. Green and red have separate display ranges; these improve visibility and do not change the feature values or thresholds. Mask interiors are drawn with 55% phase-color opacity and full-color boundaries. Scale bars are in pixels.

Labels use full 3D measurements, so fluorescence in a single slice need not show the same green/red balance as the object's 3D average. These panels check spatial registration and classification consistency; they do not independently validate biological phase accuracy. The candidate model was loaded from the completed analysis and was not refitted.

## Reproduce

```bash
OPENBLAS_NUM_THREADS=1 python scripts/plot_fucci_spatial_verification.py
```

Use `--z` to choose a different main plane. The verification JSON records input and prediction hashes, image paths/hashes, display ranges and exact slice/crop coordinates. Per-component checks and all plotted-unit assignments are saved beside it under `results/fucci_spatial_verification/241016_5`.
