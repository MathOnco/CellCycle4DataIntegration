# FoF5 spatial verification: Fig. 1A/C-style overlays

The supplied `FoF5_241016_fucci.nucleus.zip` provides the first verified image–mask pair for this analysis. The figure uses the new Saeed feature table from `Archive (6).zip`. No pseudotime analysis or Fig. 1E reconstruction is included.

**Update, 2026-10-21:** the [local-background recalibration pilot](fucci_fof5_recalibration.md) now provides new reporter-state maps, image reviews and stability results. Start with its [magnified fluorescence/map comparison](../figs4paper/fucci_fof5_recalibration/reporter_map_cluster_z35.png). The C1/C2 figures below preserve the earlier classifications for comparison.

## Input verification

- **578 original mask labels and 1,314 connected components** match the new table, including parent IDs, component IDs, volumes and bounding boxes.
- All **3,942 component/channel pairs** reproduce their exported 3D mean and integrated intensity from the raw green, red and brightfield images. Maximum absolute mean error: `5e-10` on the normalized 0–1 scale.
- All 70 image planes align in native X/Y/Z coordinates. No registration transform or mask editing was applied.

## Figures

The main figure is a single actual plane at **z=35** of the 70-plane stack (default: the middle plane, z=35). Panel A merges green and red with thin white segmentation outlines; C1 colors masks using the supplied phase thresholds; C2 colors the same selected masks using the saved refitted model, including uncertainty and QC. The outlines in A use exactly the same selected mask boundaries as the classification panels, including boundaries between touching labels. The field's 3D assignment totals are below; each panel also states how many selected units intersect its plane.

- **Every exported connected component:** [PNG](../figs4paper/fucci_spatial_verification/241016_5/fig1AC_source_rows_z35.png) · [PDF](../figs4paper/fucci_spatial_verification/241016_5/fig1AC_source_rows_z35.pdf)
- **All components aggregated by original mask label:** [PNG](../figs4paper/fucci_spatial_verification/241016_5/fig1AC_aggregated_z35.png) · [PDF](../figs4paper/fucci_spatial_verification/241016_5/fig1AC_aggregated_z35.pdf)
- **Largest component per original mask label:** [PNG](../figs4paper/fucci_spatial_verification/241016_5/fig1AC_dominant_z35.png) · [PDF](../figs4paper/fucci_spatial_verification/241016_5/fig1AC_dominant_z35.pdf)
- **Only original labels with one component:** [PNG](../figs4paper/fucci_spatial_verification/241016_5/fig1AC_singletons_z35.png) · [PDF](../figs4paper/fucci_spatial_verification/241016_5/fig1AC_singletons_z35.pdf)
- [Largest-component view across z=15, 25, 35, 45, 55 (PDF)](../figs4paper/fucci_spatial_verification/241016_5/fig1AC_dominant_slice_atlas.pdf)
- [Magnified central-region comparison](../figs4paper/fucci_spatial_verification/241016_5/fig1AC_dominant_crop_z35.png)
- [Magnified upper-left cluster](../figs4paper/fucci_spatial_verification/241016_5/fig1AC_dominant_cluster_z35.png)

## Fluorescence interpretation audit — 2026-10-21

The images reveal a calibration problem that exact image–table agreement does not resolve. Among the **180 dominant components visible at z=35**, **180 exceed the green cutoff**. C1 assigns 123 to G2M, effectively splitting this displayed population by red intensity. The gates correspond to only 1.0% green and 2.9% red on panel A's display scale.

Unmasked local annuli also exceed the green cutoff for **180/180** displayed components and both cutoffs for **110/180**. Annuli pool pixels 3–12 X/Y pixels outside each component across its z extent and exclude every mask label. They can contain diffuse fluorescence and are not negative controls; these results show that the supplied absolute gates do not establish localized reporter positivity.

Using the displayed slice means changes **29/180** C1 calls. Among components with at least 100 pixels in the slice, only **9/123** change. Thus the slice/3D difference contributes but does not explain most of the visual mismatch. The table means reproduce the original pixels, and saved C2 probabilities reproduce from those means; C2 inherits the same raw features and gate anchors. Neither panel currently establishes a reliable biological phase map.

- [Six cells with separate channels, raw values, local references and C1/C2 calls](../figs4paper/fucci_spatial_verification/241016_5/fluorescence_audit/cell_examples_z35.png) · [PDF](../figs4paper/fucci_spatial_verification/241016_5/fluorescence_audit/cell_examples_z35.pdf)
- [Quantitative diagnostic figure](../figs4paper/fucci_spatial_verification/241016_5/fluorescence_audit/measurement_diagnostics_z35.png) · [PDF](../figs4paper/fucci_spatial_verification/241016_5/fluorescence_audit/measurement_diagnostics_z35.pdf)
- [Per-cell measurements](../results/fucci_spatial_verification/241016_5/fluorescence_audit/per_cell_measurements_z35.csv) · [Summary and provenance](../results/fucci_spatial_verification/241016_5/fluorescence_audit/summary_z35.json)

The next classification step is to evaluate background-aware reporter measurements against the images and reference reporter-positive/negative cells, retaining low-contrast objects as unresolved before refitting. The annular subtraction here is a diagnostic and was not used to issue new phase labels. Reproduce with `OPENBLAS_NUM_THREADS=1 python scripts/audit_fucci_fluorescence.py`.

## Counts in the full 3D field

| Input | Units | Supplied G1 | G1S | S | G2M | Candidate G1 | G2M | Uncertain | QC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| source_rows | 1314 | 378 | 169 | 145 | 622 | — | — | — | — |
| aggregated | 578 | 161 | 1 | 1 | 415 | 215 | 171 | 188 | 4 |
| dominant | 578 | 163 | 1 | 0 | 414 | 205 | 157 | 212 | 4 |
| singletons | 359 | 103 | 1 | 0 | 255 | 144 | 102 | 113 | 0 |

The source-row view colors every measured connected component by its own supplied phase. The aggregated view colors the full original label. The dominant view colors only its largest component. The singleton view colors only labels that originally had one component. Excluded regions retain the underlying brightfield image. No additional size filtering was applied.

## Display and interpretation

Each channel uses a fixed display stretch estimated across all 70 planes: 1st–99.8th percentiles for green/red, 0.5th–99.5th for brightfield, sampled every sixteenth X/Y pixel. Green and red have separate display ranges; these improve visibility and do not change the feature values or thresholds. Panel A draws one-pixel inner mask boundaries in white at 80% opacity, without filling the interiors; white has no phase meaning. C1/C2 mask interiors are drawn with 55% phase-color opacity and full-color boundaries. Scale bars are in pixels.

Labels use full 3D measurements, so fluorescence in a single slice need not show the same green/red balance as the object's 3D average. These panels check spatial registration and classification consistency; they do not independently validate biological phase accuracy. The candidate model was loaded from the completed analysis and was not refitted.

## Reproduce

```bash
OPENBLAS_NUM_THREADS=1 python scripts/plot_fucci_spatial_verification.py
```

Use `--z` to choose a different main plane. The verification JSON records input and prediction hashes, image paths/hashes, display ranges and exact slice/crop coordinates. Per-component checks and all plotted-unit assignments are saved beside it under `results/fucci_spatial_verification/241016_5`.
