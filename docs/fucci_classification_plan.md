# FUCCI classification implementation plan

Implement and compare candidate classifiers for the replacement FUCCI feature tables supplied on 2026-10-06 in `Archive (6).zip`. Preserve all 48,475 source objects from 31 fields of view (FoFs), distinguish segmentation objects from nuclei, and report uncertainty. Biological phase assignments remain provisional until the reporter construct and independent validation evidence are available.

The archive contains unfiltered `object_features_new.csv` tables and corresponding `object_features_new_withCellCycle.csv` tables in `231005`, `2409`, and `2410`. The older CellProfiler tables provide a historical comparison. Preliminary inspection found 24,737 objects with volumes of eight voxels or fewer and repeated Cellpose labels; this motivates checking the unit of analysis before interpreting class frequencies as cell frequencies.

## 1 Freeze inputs and reproduce the existing classification

Record the archive checksum, table schemas, code revision, package versions, and random seeds. Preserve date, FoF, CellID, ObjectNumber, CellposeLabel, and supplied phase labels. Use the unfiltered newer tables as the measurement source and join the supplied labels by verified unique identifiers.

Reproduce the current rectangular gates and verify agreement with all supplied labels. For `231005`, the green and red thresholds are 0.005 and 0.009; for `2409` and `2410`, they are 0.003 and 0.0095. Record the additional exclusion rule present in the upstream R script separately; the replacement tables retain those objects.

Deliver an input manifest, reproducible baseline, and counts by folder and FoF. Every source row must remain traceable.

## 2 Audit segmentation and establish the unit of analysis

Examine object volumes, repeated CellposeLabel values within each date and FoF, and spatial relationships. Inspect representative small objects and repeated labels against the available images and matching masks. Distinguish confirmed mask matches from files that merely share a field name.

Where fragments belong to the same nucleus, determine whether to recompute nuclear measurements or combine measurements that aggregate exactly, such as voxel volume and integrated intensity. Choose exclusion criteria from image review. Preserve every original row with its QC status and any link to a reconstructed nucleus. Eight voxels is an audit diagnostic, not an adopted biological size cutoff.

Deliver a mapping of objects to original mask labels, QC flags, and an explicit record of the evidence supporting any reconstructed nuclear measurements. Treat unverified mask-label aggregation as a sensitivity analysis.

## 3 Select fluorescence measurements and assess technical variation

Start with log-transformed green and red mean intensities. Compare median intensities and SignalCore measurements as alternatives. SignalCore uses the brightest voxels by default; assess its sensitivity to tiny fragments and unusually bright pixels.

For FoFs with verified images and masks, estimate local background and examine illumination effects. Keep measurements requiring image correction distinct from features available only as table exports. Preserve genuine variation in class proportions when evaluating technical corrections. Record acquisition identifiers separately from folder names.

Deliver a feature comparison and a documented preprocessing recipe. Complete image calibration is conditional on access to the exact images and masks.

## 4 Implement a small probabilistic classifier

Compare the existing gates with a joint model of green and red intensities that estimates support for four reporter states: low/low, high/low, low/high, and high/high. Allow unequal state frequencies. Use the existing gates for initialization without treating their labels as independent biological truth. Avoid forcing a missing or unsupported state into a field.

Use the inferred PIP-FUCCI interpretation for provisional phase mapping. Keep the low/low reporter state distinct from a validated G1S phase assignment. Record the exact construct and fluorophore identities as unresolved assumptions. Retain model confidence, an uncertain flag, and model-fit diagnostics with every candidate call. Model posterior probabilities require independent evidence before they can be interpreted as calibrated biological accuracy.

Deliver fitted models, configuration, and candidate calls in separate columns from the supplied labels.

## 5 Evaluate stability across FoFs and acquisitions

Hold out entire FoFs during model comparison. Evaluate sensitivity to initialization, measurement choice, QC criteria, and modest gate changes. Assess acquisition transfer separately and disclose any adaptation that uses a held-out acquisition. Keep related fragments in the same evaluation group.

Compare boundaries, uncertain fractions, and class proportions for all 31 FoFs. Use stability and predictive fit diagnostics for model selection. Agreement with existing labels and class balance are descriptive measures, not independent biological validation. Report the possibility that technical shifts and true changes in phase composition cannot be identified separately from these tables alone.

Deliver model comparisons, disagreement plots, and sensitivity results.

## 6 Review disagreements and pursue independent validation

Create review panels covering confident, uncertain, and baseline-discordant objects in FoFs with available images. Check segmentation and reporter-state assignments, retaining any uncertainty about image-to-table matching.

Evaluate biological phase accuracy separately when matched time-lapse, EdU, DNA-content, or other independent annotations become available. Keep morphology out of phase prediction if those labels will train a downstream morphology-based model. Do not infer experimental ground truth from a second interpretation of the same fluorescence measurements.

Deliver a review set with explicit annotation status and a record of which conclusions have independent validation. Do not fabricate completion of image or biological validation steps when their inputs are unavailable.

## 7 Package the analysis for reproducible use

Deliver runnable scripts, configuration, input and code versions, object-level results, per-FoF summaries, and scatter plots displaying candidate calls and uncertainty. Include the disposition of all source rows. Report QC and uncertain counts and clearly identify denominators in every class-frequency summary.

Store code under `scripts`, documentation under `docs`, numeric outputs under `results/fucci_classification`, and figures under `figs4paper/fucci_classification`. Include meaningful checks for row preservation, label reconstruction, aggregation, and evaluation leakage. Separate completed computational work from remaining experimental validation.

## Sources

- [Feature extraction pipeline](https://github.com/saeedalahmari3/PMO_MeasuringFitnessperClone/blob/f23b506e2ec3ed117db6cc42d21c89cef25f823b/3D_Imaging/cellprofiler_python_pipeline.py)
- [Classification and exclusion rules](https://github.com/saeedalahmari3/PMO_MeasuringFitnessperClone/blob/f23b506e2ec3ed117db6cc42d21c89cef25f823b/3D_Imaging/R/Manager.R#L99-L144)
- [Grant et al. 2018: PIP-FUCCI reporter interpretation and validation](https://pmc.ncbi.nlm.nih.gov/articles/PMC6342071/)
