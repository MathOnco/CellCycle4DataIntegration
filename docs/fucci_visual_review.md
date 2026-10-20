# FUCCI visual inspection notes

Inspection date: 2026-10-19. This is an assistant inspection of rendered analysis artifacts and representative image crops. It is not expert segmentation annotation or independent biological phase validation. All 72 rows in `results/fucci_classification/image_review_annotations.csv` remain `unreviewed`.

## Artifacts inspected

- The seven-panel candidate scatter figure, all four pages of the 31-FoF scatter atlas, the class-distribution figure, the object-versus-mask-label comparison, held-out model scores, sensitivity/disagreement, and segmentation diagnostics were inspected for labeling, visibility, and consistency with the tables.
- Representative fluorescence sheets were inspected for `231005/1`, `240918/1`, `241016/5`, and `241017/21`, covering all four acquisition dates. The full review set contains six candidates in each of 12 fields; the other eight fluorescence sheets await detailed inspection.
- Both available mask sheets were inspected: `241016/1` and `241016/14`. Each shows four source labels with many components, as a single z slice and an all-z projection.
- PNGs are saved under `figs4paper/fucci_classification`, including individual image/mask pages under `review_pages`. The PDFs use the same rendered figures.

## Observations and limits

The scatter atlas shows the large difference between the rectangular supplied gates and the fitted density boundary. The solid line marks equal posterior scores for the high-green/low-red and high-green/high-red components. It is not a validated biological transition. In this fit the boundary is closed and curved; constraining component means to gate quadrants does not constrain predictions to the same quadrants or enforce a monotonic response to either reporter. The low-green components have little fitted support. The observed two-state fit and 37.3% gate sensitivity argue against adopting these calls as a four-phase replacement.

In the representative fluorescence sheets, several small-support candidates have faint, punctate, or background-like signal near the marked center, while some other crops contain a prominent bright structure. For example, `241016/5`, mask 220, shows a bright green structure and a much weaker red display at the selected plane. Its model score is near one but its disposition is uncertain because of gate sensitivity. `231005/1` includes small candidates with no clearly resolved bright nucleus at the marked center under the chosen display stretch. These observations motivate review; they do not establish false positives or authorize deleting rows. The channels use separate display scales, so visual brightness alone cannot define reporter positivity.

The masks visibly contain isolated islands around larger support regions. In `241016/14`, mask 92 has 53 connected components and only 15.5% of its volume in the largest component. This makes its aggregation particularly questionable as a biological nuclear measurement. Other examples have a dominant component plus small islands, such as mask 31 in the same field, with 99.9% of volume in its largest component. Component counts come from the 3D audit; a 2D projection can merge components visually.

There is no field with both the currently available fluorescence images and a matching original mask. Crosses in fluorescence sheets locate the largest-component centroid, not an outline. A single plane does not summarize the entire 3D object, and a centroid can lie outside an irregular support region. Mask-only sheets cannot determine reporter state or whether all islands belong to one biological nucleus. These limitations prevent adopting an image-based exclusion threshold here.

## Corrections and checks

- Expanded the fragmentation histogram through the full observed maximum of 215 components. The earlier display stopped at 40; no table rows were excluded.
- Included all source values in scatter limits and all mask-label volumes in histogram bins. Automated checks reject clipped scatter ranges and verify that the atlas includes each of the 31 FoFs once, totaling 21,653 labels.
- Made the class-frequency denominator explicit for every FoF. `disposition_by_fof.csv` contains mutually exclusive provisional calls, uncertainty, and QC review counts that sum to each field's total.
- Retained original object labels, measurements, and all 48,475 object-to-mask mappings. No visual observation changed a supplied label or removed a row.
- Added checks that prevent reusing predictions with changed inputs or analysis parameters. Review reruns preserve human annotation fields and retain previously selected candidates.

## Remaining review

An expert can annotate the review CSV using the linked page and crop coordinates, recording uncertainty when an object cannot be assessed. To evaluate segmentation and background, supply exact masks for the fluorescence fields or fluorescence images for the verified mask fields. Confirm the FUCCI construct and reporters from experimental records. Biological phase accuracy requires a matched independent reference, such as validated time-lapse trajectories, EdU, or DNA content. None of these steps is claimed complete by this inspection.
