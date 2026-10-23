# Run the accepted FUCCI reporter classifier on any FoF

The portable entry point is [`scripts/run_fucci_reporters.py`](../scripts/run_fucci_reporters.py). It supports a single field or every field listed in a CSV manifest. It uses the accepted **original classifier followed by a neither → both refinement**, with one dominant connected component per original segmentation label.

The runner calculates local-background measurements from raw inputs. It does not read previous assignments, review annotations, old CellProfiler tables, earlier analysis results, or any author's Downloads directory. Clone the repository and supply the inputs below. Copying only the entry-point file is insufficient: keep the entire `scripts` directory, including its model files.

**Scope:** the software can process all FoFs with matching inputs. The fixed cutoffs were calibrated on **241016/FoF5**. Applying them elsewhere is a transfer of that calibration, not evidence that reporter detection or biological phase accuracy is established across acquisitions. No per-field fitting, feature selection, desired class proportions, or manual label overrides occur during a run.

## Install

Use a Python environment compatible with the pinned requirements; the regression run used **Python 3.9.20** and the exact versions below. Python 3.11 can also be used with these dependency pins.

```bash
git clone https://github.com/MathOnco/CellCycle4DataIntegration.git
cd CellCycle4DataIntegration
python3.11 -m venv ~/venvs/fucci
source ~/venvs/fucci/bin/activate
python -m pip install -r scripts/fucci_analysis/requirements.txt
python scripts/run_fucci_reporters.py --help
```

Dependencies are NumPy 1.26.4, pandas 2.2.3, SciPy 1.13.1, Matplotlib 3.6.3, tifffile 2024.8.30, scikit-image 0.24.0 and Pillow 9.4.0. No R, CellProfiler installation, GPU or network connection is required for classification after installation. Run FoFs sequentially; memory use is driven by the full 3D mask and its component-label volume.

## Required inputs per FoF

| Input | Requirements |
| --- | --- |
| New feature table | `object_features_new.csv`, directly or inside a ZIP. A table can contain many fields; `Date` and `FoF` select the requested one. It must contain every exported component for that field. |
| Original segmentation mask | Matching nonnegative integer TIFF in **Z,Y,X** order, background zero. Supply the original parent labels, including all disconnected fragments. A ZIP containing one mask TIFF is accepted; name `mask_member` explicitly if it contains several. |
| Raw images | One directory per FoF containing individual **uint16 2D TIFF planes**, named `*_zNN_chCC.tif` or `.tiff`. Z indices must be unique and contiguous from 0 through mask depth minus one. No resizing, registration, channel mixing or display stretching is applied to measurements. |
| Reporter channels | Defaults: green `00`, red `02`. Set `--green-channel` and `--red-channel`, or the corresponding manifest columns, if the acquisition uses different identifiers. Brightfield is not required. |
| Identity | Acquisition `date` and numeric `fof`, plus a source `folder` tag such as `231005`, `2409` or `2410`. The folder is a namespace, not a different threshold set. |

Required table columns: `Date`, `FoF`, `ObjectNumber`, `CellposeLabel`, `AreaShape_Volume`; `AreaShape_BoundingBoxMinimum_X/Y/Z` and `AreaShape_BoundingBoxMaximum_X/Y/Z`; and `Intensity_MeanIntensity_green/red` and `Intensity_IntegratedIntensity_green/red`. Inventory generation additionally uses `ImageSet` and `FileName_mask`. Optional `CellID` is retained for joins.

Raw CellProfiler mean intensities are **not** the classifier inputs. The classifier uses new local-background scores calculated from the images and masks. A feature CSV alone cannot reproduce this version. Images must be on the same raw scale and spatial grid used to generate the feature table. The supplied mask must reproduce the table before dominant components are selected.

## Run one FoF

Replace the paths with your own. This example selects FoF5 from the `2410` table inside the replacement feature archive:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python scripts/run_fucci_reporters.py field \
  --folder 2410 --date 241016 --fof 5 \
  --features '/data/Archive (6).zip' \
  --features-member 2410/object_features_new.csv \
  --images /data/raw/FoF5_241016_fucci.nucleus \
  --mask /data/masks/FoF5_241016_fucci.nucleus.zip \
  --output /data/results/fucci/241016_FoF5
```

For an extracted table, use `--features /data/features/2410/object_features_new.csv` and omit `--features-member`. An extracted mask TIFF can replace the mask ZIP directly. For an ambiguous mask ZIP, add, for example, `--mask-member FoF5_241016_fucci.nucleus/FoF5_241016_fucci.nucleus_masks.tif`.

Add `--check` to validate table/mask correspondence, channel files, dimensions, dtype and Z coverage without writing output. Full image intensity reconstruction occurs during the actual run. Add `--no-plots` to retain all numerical outputs without PNG/PDF figures.

## Run all FoFs

### 1. Generate a manifest

The feature root may be the replacement ZIP, an extracted directory containing the three source folders, or one CSV. Only `object_features_new.csv` files are discovered automatically.

```bash
python scripts/run_fucci_reporters.py inventory \
  --features-root '/data/Archive (6).zip' \
  --images-root /data/raw \
  --masks-root /data/masks \
  --output /data/fields.csv
```

For the current replacement archive, this produces **31 rows**, one per FoF across all three folders. Images are expected under `images-root/ImageSet`. Mask candidates are `masks-root/ImageSet/FileName_mask`, `masks-root/FileName_mask`, and `masks-root/ImageSet.zip`. The generator uses a unique existing candidate when available. Review `path_note`, `images_exist` and `mask_candidates_found`; edit paths if your layout differs or multiple candidates exist. Presence alone does not establish a match.

### 2. Check the manifest

```bash
python scripts/run_fucci_reporters.py batch \
  --manifest /data/fields.csv \
  --output /data/results/fucci_all \
  --check
```

The check reports every requested field and exits with a nonzero status if any field fails. It creates no output directory. Correct missing or mismatched inputs before a full run.

The required manifest columns are `date,fof,features,images,mask`. Optional columns are `folder,features_member,mask_member,green_channel,red_channel`. Paths may be absolute or relative to the **manifest's directory**, including when the command runs elsewhere. Empty channel entries use `00` and `02`. Date/FoF values must contain digits; folder tags may contain letters, digits, underscores and hyphens. Duplicate folder/date/FoF entries are rejected. Extra inventory columns are ignored by the runner. A small [example manifest](../examples/fucci_reporters/fields.example.csv) illustrates the format.

### 3. Run and resume

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python scripts/run_fucci_reporters.py batch \
  --manifest /data/fields.csv \
  --output /data/results/fucci_all
```

The runner processes fields sequentially and records failures explicitly while continuing with other fields. It exits nonzero if any field fails. Every completed field is published atomically after its measurements, classifications and figures have succeeded. An interrupted or failed field does not leave a partial result that looks complete.

To continue an interrupted batch, repeat the same command with `--resume`. Completed fields are reused only when their input, code, model, software-version and output hashes still match. Incomplete fields are rerun. Use a new output directory if inputs, code, model, Python/dependency versions or plot settings have changed. Source data and previous outputs are never overwritten to make a run pass. A pre-existing destination requires `--resume`; the inventory command also refuses to overwrite a manifest.

## What the runner does

1. Select the requested Date/FoF, split the mask into **26-connected components of each original label**, and require exact agreement with all table ObjectNumbers, parent labels, volumes and bounding boxes.
2. Choose the largest component of each original label. Ties use the smallest ObjectNumber. Retain a mapping of every source fragment, including the unselected ones. No parent label is removed.
3. Reconstruct every component's raw green/red mean and integrated intensity and compare with the table. Wrong channels, scaling and alignment fail this check. Tolerances are the existing verification tolerances: relative `2e-5`, absolute `5e-7` on the normalized scale.
4. Divide uint16 intensities by 65,535 using the original normalization code. Within each plane, measure foreground means and an unmasked reference annulus **more than 3 and at most 12 pixels** from the dominant component. Exclude pixels belonging to any original mask label, including fragments and neighbors. Use planes with at least 50 reference pixels and weight their mean-minus-median differences by foreground volume. Keep signed scores.
5. For a label lacking a finite primary score, use the accepted nearest-unmasked-reference fallback: at least 50 pixels beyond the 3-pixel gap, including distance ties, in every occupied plane; weight by foreground volume. Fallbacks and their pixel statistics are exported. If a finite score cannot be obtained, fail the field explicitly instead of treating missing data as neither.
6. Call the unchanged original `point_states` function on those scores, then the accepted neither refinement. Saved state assignments never enter this decision.

| Reporter | Original higher cutoff | Lower cutoff for original neither only |
| --- | --- | --- |
| Green | 0.0065016187699578 | 0.0024075655915692497 |
| Red | 0.00419540689627625 | 0.003031188659523 |

The original classifier returns green only, red only, both or neither using the higher cutoffs. If and only if it returns neither, and **both** lower cutoffs are strictly exceeded, the final state becomes both. Equality belongs to the lower-signal side. The added step cannot change an original single-positive or both result. Changed measurements can change the original-stage result, which is always recomputed.

The runner imports the existing measurement, normalization, original-classifier and refinement functions; their accepted hashes are locked in [`fof5_neither_v1.json`](../scripts/fucci_analysis/models/fof5_neither_v1.json). Model and implementation snapshots are recorded with each result. `--model` can name another explicitly prepared model bundle with the same schema; this command performs no fitting. The default bundle requires no files under the repository's `results` directory.

## Outputs

Each field gets the following files. In a batch, they are under `output/folder/date_FoFnumber/`.

| File | Contents |
| --- | --- |
| `cell_reporter_states.csv` | One row per original mask label; stable `unit_id`, source identifiers, dominant component, volume/fraction, numeric scores, freshly computed original and final states, promotion/fallback flags and stability annotations. |
| `component_to_label.csv` | All exported components linked to original labels; identifies the selected dominant component. |
| `component_image_measurement_checks.csv` | Verification of every source component against both raw channels. |
| `plane_measurements.csv.gz`, `measurement_variants.csv.gz` | Reproducible local measurements and diagnostic alternatives. Other features are retained for audit; only mean excess enters this classifier. |
| `fallback_measurements.csv` | Nearest-reference measurements where needed; a header-only file if none. |
| `variant_reporter_states.csv.gz`, `measurement_stability.csv` | Both classification stages rerun for 11 measurement settings. Missing variants are unavailable, never assigned neither. |
| `bootstrap_counts.csv`, `grid_counts.csv` | The 500 frozen FoF5 calibration bootstrap pairs and an 81-setting ±20% lower-cutoff grid applied to this field. Higher gates stay fixed. |
| `original_to_refined.csv` | Transition matrix; only neither → both is added. |
| `reporter_scatter.*`, `reporter_map_middle_z.*`, `classification_stability.*` | PNG/PDF inspection figures. Maps show the middle Z slice with matched outlines; assignments use full 3D measurements. |
| `model.json`, `calibration_bootstrap_thresholds.csv`, `run.json` | Model snapshot, fixed bootstrap pairs, input/code/output hashes, environment and summary. |

Batch-level files are `field_status.csv`, `counts_by_field.csv`, `all_cell_reporter_states.csv.gz` and `batch_summary.json`. **Combined exports contain only completed fields**; `all_requested_fields_complete` must be true before describing them as the full dataset. Full label IDs include source folder, date, FoF and CellposeLabel, preventing collisions across fields.

Neither is a rule-defined reporter state and is not mapped to a cell-cycle phase. Mask quality and sensitivity are separate from the four-state decision. The dim both calls remain sensitive to reference subtraction. FoF5 bootstrap frequencies describe sensitivity to its calibration sample, not new calibration or validated probabilities for another field.

## Verification

The runner was tested on the real FoF5 raw images, feature ZIP and mask ZIP from a separate directory containing **only a copy of `scripts`**, with no previous result files. It reproduced all **578** accepted states: **90 green only, 72 red only, 77 both, 339 neither**. Selected components, local scores, fallback flags and stability annotations also matched. The [validation record](../results/fucci_reporter_runner_validation/validation.json) records the numerical comparisons and input/code hashes.

Automated tests cover two fields with repeated parent IDs, dominant-fragment selection, original-code preservation, missing/duplicate planes, ambiguous mask archives, mismatched geometry and channels, relative manifest paths, read-only dependency checks, output integrity on resume, and explicit partial-batch accounting. Run:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m unittest discover -s tests -p 'test_fucci*.py'
```

The implementation was not run on all 31 real FoFs: complete matching raw images and masks were not verified locally for that set. The collaborator supplies those inputs and runs the batch checks above. The [FoF5 report](fucci_fof5_neither_refinement.md) documents the accepted calibration and its scientific limitations.
