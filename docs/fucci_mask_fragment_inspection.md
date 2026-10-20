# FUCCI mask-fragment inspection

## Does a dominant component plus tiny pieces describe most labels?

Of all **21,653 original mask labels**, **13,981 (64.6%) have one connected component**. The remaining **7,672 (35.4%) have multiple components**. These are segmentation labels, not confirmed biological cells.

Among multi-component labels:

- **4,896 (63.8%)** have at least 95% of their volume in the largest component.
- **3,185 (41.5%)** have at least 99% in the largest component.
- The median largest-component fraction is **98.2%**; the median number of components is **3**.

Of the **26,822 non-largest components**, **24,604 (91.7%) contain eight voxels or fewer**; their median size is **one voxel**. Eight voxels is a descriptive threshold, not an adopted exclusion rule. Thus tiny satellites are common among fragmented labels, while the example with 28 components is more fragmented than typical. A large component plus satellites is not the geometry of the majority of all labels, because most have just one component.

## Inspect the actual masks

- [Interactive slice viewer](../figs4paper/fucci_classification/fragment_inspection/mask_component_viewer.html): open the local HTML file in a browser, choose an example, drag the z slider, or play the slices. Toggle smaller components to see satellites separately. The viewer is self-contained and needs no network.
- [Six detailed inspection pages (PDF)](../figs4paper/fucci_classification/fragment_inspection/mask_component_details.pdf)
- [Fragmentation summary across all 31 FoFs](../figs4paper/fucci_classification/fragment_inspection/fragmentation_summary.png)

The detailed figures show projections, actual z slices, and every component's voxel count. Turquoise denotes the largest 3D component; warm/purple colors denote smaller components, with stable colors across slices. Gray shows context from other labels (or the main component in the satellite projection). Projections can hide or superimpose disconnected pieces; the slice viewer resolves the z dimension. Component ranks are local to an example and are not the source ObjectNumber.

Only the two available original masks, FoFs 1 and 14 of acquisition 241016, are visualized. Their checksums match the previous audit, and every selected label's component count and individual component volumes match the exported table. No mask voxel or supplied class label was changed. Matching fluorescence images are unavailable for these two FoFs; these figures establish mask geometry but cannot independently determine whether each disconnected piece belongs to a real nucleus.

Four examples were deliberately selected for fragmentation, so they do not estimate its prevalence. The additional three-component example has a dominant fraction close to the median across fragmented labels; the single-component example has a volume close to the median across all single-component labels. The prevalence statistics use every label across all 31 FoFs.

## Reproduce

```bash
python scripts/inspect_fucci_mask_fragments.py
```

Counts, component coordinates, page mappings, and mask provenance are saved under `results/fucci_classification/fragment_inspection`.
