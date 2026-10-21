# FUCCI classification handoff

Resumed on 2026-10-19 from checkpoint `548e6da`. The available computational work, review-sheet generation, figure inspection, and report are now complete. See [the results report](fucci_classification_results.md), [visual inspection notes](fucci_visual_review.md), and the status table in [the implementation plan](fucci_classification_plan.md). Full image calibration, expert annotations, construct confirmation, and independent phase validation remain pending; the biological classification problem is not solved.

## Fluorescence versus classification audit — 2026-10-21

The user observed that the fluorescence in panel A does not convincingly correspond to C1/C2. A direct audit of the FoF5 dominant components confirms that the mean features reproduce the image pixels, but the absolute gates do not establish localized reporter positivity. All 180 components visible at z=35 are green-positive under the 3D cutoff; C1 splits them into 123 G2M and 57 G1 based on red. The green/red cutoffs sit at only 1.0%/2.9% of the fluorescence display ranges. All 180 local unmasked annuli also exceed the green cutoff, and 110 exceed both. Annuli can contain diffuse fluorescence and are not negative controls, so their subtraction is only diagnostic.

Single-slice means change 29/180 C1 calls, or 9/123 when restricting the comparison to intersections of at least 100 pixels. The slice/3D distinction therefore explains only part of the mismatch. Label 63 is a strong green example called G2M by both methods: its 3D red mean is 0.010471, above the 0.0095 gate but slightly below its local unmasked red mean of 0.010753. No biological phase is inferred from this contrast check.

The [spatial verification report](fucci_spatial_verification_241016_5.md#fluorescence-interpretation-audit--2026-10-21) now links six numerical/image examples, a diagnostic figure, per-cell measurements, and provenance. Reproduce with `OPENBLAS_NUM_THREADS=1 python scripts/audit_fucci_fluorescence.py`. Original predictions are preserved; saved C2 scores reproduce from their inputs. Background-aware reporter scores and image-reviewed positive/negative references should precede further interpretation or refitting of phase labels. The synthetic audit test checks a known 3D/slice discrepancy and exclusion of a bright neighboring label from the local annulus.

## FoF5 image–mask verification — 2026-10-20

The user supplied `/Users/4470246/Downloads/FoF5_241016_fucci.nucleus.zip` and requested Fig. 1A/C-style verification figures, explicitly dropping Fig. 1E. Its `FoF5_241016_fucci.nucleus_masks.tif` matches all 578 original labels and 1,314 connected components in the new feature table. Every parent/component ID, volume and bounding box matches. All 3,942 component/channel combinations reproduce their exported 3D mean and integrated intensity from the local green, red and brightfield images.

This provides **one verified image–mask pair**, superseding the earlier statement that image/mask overlap is zero. The historical `results/fucci_classification/image_inventory.csv` describes the earlier inputs; the new evidence and all source hashes are in `results/fucci_spatial_verification/241016_5/image_mask_verification.json`. Background calibration has not yet been performed.

The [spatial verification report](fucci_spatial_verification_241016_5.md) links the fluorescence and phase-colored mask overlays for source rows, aggregated labels, dominant components and singleton labels, plus magnified regions and a five-slice atlas. Main panels use z=35 and share fixed channel display ranges. Saved classification models were reused without refitting; no pseudotime was calculated. `scripts/plot_fucci_spatial_verification.py` reproduces the figures. Eleven tests pass, including a spatial mapping check for the distinction between global CellID and per-field ObjectNumber.

## Component-input extension — 2026-10-20

The user's requested largest-component and single-component-only analyses are complete. See [the comparison report](fucci_component_input_comparison.md) and [the mask-fragment inspection guide](fucci_mask_fragment_inspection.md).

- The previous main model already used 21,653 aggregated mask-label measurements. The original threshold scatter plots used all 48,475 component rows. The new report compares both reference units explicitly.
- Largest-component input retains 21,653 original labels and excludes 26,822 satellite rows from fitting. Single-component-only input retains 13,981 labels, excluding all 7,672 fragmented labels. Both policies keep a ledger accounting for every source row and add no size exclusion.
- Both candidate models were refitted separately for each policy, with all 31 FoF holdouts, four acquisition holdouts, and 14 sensitivity variants repeated. Joint models were selected in both cases.
- Raw state assignments change for 3.79% of labels with largest-component measurements, and 0.46% of the same retained labels after the singleton refit. Gate sensitivity remains 39.7% and 35.8%, respectively, versus 37.3% for the aggregated reference.
- The largest-component fit has a supported low-green/high-red mixture component and 473 S-like most-likely assignments, but all 473 are uncertain under the specified checks. The singleton fit and aggregated reference still lack support for both low-green states. None establishes a reliable four-phase classification.
- Across all labels, 64.6% have one component. Among fragmented labels, 63.8% place at least 95% of their volume in the largest component. Of the non-largest components, 91.7% contain eight voxels or fewer.
- Six examples from the two exact masks have a self-contained z-slice viewer, detailed PNG/PDF pages, and per-component volume/coordinate exports. Every component count and volume matches the measurement table. These examples are illustrative, not a prevalence sample.

New entry points are `scripts/compare_fucci_component_inputs.py` and `scripts/inspect_fucci_mask_fragments.py`. Numeric comparison outputs are in `results/fucci_component_comparison`, figures in `figs4paper/fucci_component_comparison`, and inspection outputs in the `fragment_inspection` subdirectories of the original results/figure directories. The original fitted predictions are preserved. Ten unit tests pass, and both comparison policies pass source-selection, measurement, probability, and holdout-coverage checks.

The sections below describe the aggregated reference analysis unless explicitly stated otherwise.

## Repository and input

- Working directory: `/Users/4470246/Repositories/CellCycle4DataIntegration`.
- Branch: `main`; remote: `https://github.com/MathOnco/CellCycle4DataIntegration.git`.
- The plan was committed and pushed as `dcea30a` before implementation began. The original pause checkpoint is `548e6da`; later commits complete the available rendering and reporting work.
- The input is `/Users/4470246/Downloads/Archive (6).zip`. It supersedes the older extracted `/Users/4470246/Downloads/I08_3DCellProfiler_FUCCI` directory. Read the replacement ZIP directly. It contains both unfiltered and labeled newer tables for `231005`, `2409`, and `2410`, plus two unchanged older tables.
- The ZIP is an external input, not checked into this repository. Its SHA256 and table metadata are in `results/fucci_classification/input_manifest.json`.
- Many unrelated modifications, deletions, and untracked files predate this task, particularly under `data4paper` and in the R Markdown document. They were deliberately excluded from task commits. Do not reset, clean, stage, or overwrite them.

## Completed work

The earlier seven-panel scatter figures were regenerated from the replacement ZIP. Their PNG, PDF, source manifests, updated per-FoF class-balance CSV, and replacement audit are under `figs4paper`. Their plotting script is `scripts/plot_fucci_mean_intensity.py`.

The implementation is in `scripts/fucci_analysis`, with CLI `scripts/run_fucci_classification.py`, configuration `scripts/fucci_analysis/config.json`, and pinned dependencies in `scripts/fucci_analysis/requirements.txt`. The computational outputs currently exist under `results/fucci_classification`.

1. Input and baseline audit completed. All **48,475 objects across 31 FoFs** are preserved. Raw/labeled identities and mean intensities match, and the existing strict gate rules reproduce every supplied label. The upstream exclusion strip is flagged, never applied.
2. Segmentation audit completed for the available evidence. The objects map to **21,653 original Cellpose labels**. There are **24,737 tiny objects** with volume at most eight voxels, but only **133 original labels** consist entirely of tiny components. Label-level means are reconstructed by summing integrated intensity and dividing by summed volume. These are original mask labels, not independently verified biological nuclei.
3. Feature comparisons and local image compatibility checks completed. Exact mask files for `241016/1` and `241016/14` in Downloads reproduce exported per-label and connected-component volumes. Raw images exist for 12 other FoFs; sampled complete small bounding boxes reproduce their exported intensities. The image/mask overlap is zero, so complete background calibration remains pending. A Pillow fallback handles LZW TIFF files without changing 16-bit intensity scaling.
4. Two gate-anchored reporter-density models were implemented: a joint four-state diagonal Gaussian mixture and independent two-state mixtures for each channel. They use log10(intensity / supplied acquisition gate), unequal state frequencies, and equal total training weight per FoF. Object-level sensitivity weights siblings together. Supplied biological labels remain intact.
5. Thirty-one FoF holdouts, four acquisition holdouts, and fourteen sensitivity variants completed. Candidate selection, models, held-out predictions, all source mappings, and updated uncertain flags are saved. The last operation reused the saved fitted model and held-out predictions to add gate-sensitivity flags; it did not rerun or change the model-selection folds.
6. Review sheets are generated for 72 candidates across 12 fluorescence fields and eight mask examples across two fields. Annotation status remains unreviewed. Representative fluorescence sheets from every acquisition date and both mask sheets were inspected; observations are documented separately from expert annotations.
7. Six summary figures (PNG/PDF), a four-page atlas covering all 31 FoFs, review PDFs and page PNGs, the results report, mutually exclusive per-FoF disposition counts, provenance, and export checks are complete. No model fitting was repeated on resumption. All source identities, means, phases, mappings, and parent scores were checked against the persisted outputs.

## Findings that govern the next steps

- Aggregating segmentation fragments changes class proportions markedly. With the existing gates, approximately **99.6% of `231005` original mask labels are G2M**. Report the measurement unit and denominator explicitly.
- The joint model has higher held-out fluorescence log density in **28 of 31 FoFs**, with mean advantage **0.16759** over the independent model. All 62 field-model fits converged. This is density fit, not biological accuracy; the same folds selected the candidate.
- The joint model has fewer than one effective weighted label in each low-green component. It therefore **does not support a reliable four-state replacement** under its current assumptions. See `state_support.json`. Do not present the disappearance of S/G1S calls as validated biology.
- Decreasing the red gate by 10% changes **33.6%** of calls. Across plus/minus 10% perturbations of either gate, **37.3%** of labels change their most likely state. Those labels now receive an uncertain flag, even if the fitted posterior is high.
- The current provisional disposition is **6,791 G1**, **6,086 G2M**, **8,643 uncertain**, and **133 QC review**, totaling 21,653 mask labels. These are provisional outputs of a diagnostic model, not approved replacements for the supplied phase labels.
- Changing to largest-component SignalCore measurements changes about **42.8%** of calls in a descriptive sensitivity analysis. Median/core variants use a dataset-derived scale alignment only for that analysis; this is neither image calibration nor held-out validation.
- The rules are consistent with a PIP-FUCCI-like green Cdt1/PIP and red Geminin configuration. The exact construct and fluorescent tags are still inferred. Independent time-lapse, EdU, DNA-content, or other phase validation is unavailable.

## Reproducing the completed artifacts

The previously pending review/rendering stage has run successfully. `docs/fucci_classification_results.md` and `figs4paper/fucci_classification` are populated. The remaining work needs expert review or additional experimental inputs, rather than another unmodified model run.

Run:

```bash
cd /Users/4470246/Repositories/CellCycle4DataIntegration
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -u scripts/run_fucci_classification.py --stage review
```

This loads the saved predictions, regenerates raw-image and mask review panels, preserves existing annotation fields, creates the classification/QC figures, and writes the results report and workflow status. Review sheets are candidates for annotation, not completed independent validation. `--stage report` regenerates figures/report after review exists. Both commands check that the archive and analysis parameters match the saved predictions before updating outputs. Avoid rerunning the completed model comparisons unless a substantive code or data change requires it.

The stages `audit` and `fit` were exercised before the pause; `review` and `report` were exercised on resumption. A fresh `--stage all` invocation has not been run because the input and fitted models are unchanged. All eight unit tests pass, and all task Python sources compile. The tests cover original gate boundary behavior, additive fragment reconstruction, field/sibling weighting, reporter-state identities and numeric model serialization, 16-bit LZW decoding, stale-input rejection, saved measurement coverage, and preservation of human review annotations:

```bash
MPLCONFIGDIR=/tmp/fucci-mpl XDG_CACHE_HOME=/tmp/fucci-cache OPENBLAS_NUM_THREADS=1 \
python -m unittest discover -s tests -p 'test_fucci_analysis.py'
```

The user was asked asynchronously for the matching raw images/masks and independent phase annotations. No answer had arrived, and `/Volumes/Expansion` was still unavailable on resumption. Calibration and independent phase validation remain pending until their inputs exist. The current candidate is unsuitable as a four-phase replacement under the available evidence. Use the image inventory and review CSV to identify the missing inputs and the objects requiring expert assessment.

## Code provenance and operational details

The public upstream revision is `f23b506e2ec3ed117db6cc42d21c89cef25f823b` in `saeedalahmari3/PMO_MeasuringFitnessperClone`. `3D_Imaging/cellprofiler_python_pipeline.py` measures features; `3D_Imaging/R/Manager.R` assigns phases. The Python pipeline splits disconnected components of each original mask label. Its default SignalCore uses voxels at or above the 99th percentile of max(green, red).

The upstream R script still removes a low-red strip from G2M before export. The replacement archive does not apply that exclusion. Its `2409` gates changed to green 0.003 / red 0.0095, relabeling 1,236 objects already present in the previous export. The current archive's labels otherwise match the code.

Direct public GitHub reads and Git pushes succeeded with sandbox escalation. The sandbox sometimes reports DNS failures; `gh auth status` also reported invalid credentials inside the sandbox, but `git push origin main` worked with escalation. Do not initiate authentication changes without cause. Do not expose credentials.

The user explicitly requested that all task work be committed and pushed at the pause. Commit only this task's files; preserve the unrelated dirty worktree. On resumption, follow any new instructions about further publication or commits.
