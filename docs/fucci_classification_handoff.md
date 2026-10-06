# FUCCI classification handoff

Paused at the user's request after the table analysis, grouped validation, and sensitivity exports completed. No analysis process is running. Resume the remaining stages of [the implementation plan](fucci_classification_plan.md); do not assume that the biological classification problem is solved.

## Repository and input

- Working directory: `/Users/4470246/Repositories/CellCycle4DataIntegration`.
- Branch: `main`; remote: `https://github.com/MathOnco/CellCycle4DataIntegration.git`.
- The plan was committed and pushed as `dcea30a` before implementation began. The checkpoint commit containing this handoff follows it.
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

## Findings that govern the next steps

- Aggregating segmentation fragments changes class proportions markedly. With the existing gates, approximately **99.6% of `231005` original mask labels are G2M**. Report the measurement unit and denominator explicitly.
- The joint model has higher held-out fluorescence log density in **28 of 31 FoFs**, with mean advantage **0.16759** over the independent model. All 62 field-model fits converged. This is density fit, not biological accuracy; the same folds selected the candidate.
- The joint model has fewer than one effective weighted label in each low-green component. It therefore **does not support a reliable four-state replacement** under its current assumptions. See `state_support.json`. Do not present the disappearance of S/G1S calls as validated biology.
- Decreasing the red gate by 10% changes **33.6%** of calls. Across plus/minus 10% perturbations of either gate, **37.3%** of labels change their most likely state. Those labels now receive an uncertain flag, even if the fitted posterior is high.
- The current provisional disposition is **6,791 G1**, **6,086 G2M**, **8,643 uncertain**, and **133 QC review**, totaling 21,653 mask labels. These are provisional outputs of a diagnostic model, not approved replacements for the supplied phase labels.
- Changing to largest-component SignalCore measurements changes about **42.8%** of calls in a descriptive sensitivity analysis. Median/core variants use a dataset-derived scale alignment only for that analysis; this is neither image calibration nor held-out validation.
- The rules are consistent with a PIP-FUCCI-like green Cdt1/PIP and red Geminin configuration. The exact construct and fluorescent tags are still inferred. Independent time-lapse, EdU, DNA-content, or other phase validation is unavailable.

## Remaining work

Stage 6 and final stage 7 artifacts are implemented but **not yet executed or visually inspected**. In particular, the new classification figure directory is currently empty, and `docs/fucci_classification_results.md` has not been generated. This is the natural resume point.

Run:

```bash
cd /Users/4470246/Repositories/CellCycle4DataIntegration
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -u scripts/run_fucci_classification.py --stage review
```

This loads the saved predictions, creates raw-image review panels and annotation templates, creates the classification/QC figures, and writes the results report and workflow status. Fix any errors in this unexecuted rendering stage, then inspect the generated figures with `view_image`. Review sheets are candidates for annotation, not completed independent validation. `--stage report` regenerates figures/report after review exists. Avoid rerunning the already completed model comparisons unless a substantive code or data change requires it.

The stages `audit` and `fit` have been exercised. `--stage all` should reproduce the full computation, but the complete all-stage invocation has not yet been run. All five unit tests passed at the checkpoint, and all task Python sources compiled successfully. The tests cover original gate boundary behavior, additive fragment reconstruction, field/sibling weighting, reporter-state identities and numeric model serialization, and 16-bit LZW decoding:

```bash
MPLCONFIGDIR=/tmp/fucci-mpl XDG_CACHE_HOME=/tmp/fucci-cache OPENBLAS_NUM_THREADS=1 \
python -m unittest discover -s tests -p 'test_fucci_analysis.py'
```

The user was asked asynchronously for the matching raw images/masks and independent phase annotations. At the pause, no answer had arrived and `/Volumes/Expansion` was unavailable. Continue the available computational and review work; report calibration and independent phase validation as pending until their inputs exist. The conclusion may remain that this candidate is unsuitable as a four-phase classifier without better measurement calibration.

## Code provenance and operational details

The public upstream revision is `f23b506e2ec3ed117db6cc42d21c89cef25f823b` in `saeedalahmari3/PMO_MeasuringFitnessperClone`. `3D_Imaging/cellprofiler_python_pipeline.py` measures features; `3D_Imaging/R/Manager.R` assigns phases. The Python pipeline splits disconnected components of each original mask label. Its default SignalCore uses voxels at or above the 99th percentile of max(green, red).

The upstream R script still removes a low-red strip from G2M before export. The replacement archive does not apply that exclusion. Its `2409` gates changed to green 0.003 / red 0.0095, relabeling 1,236 objects already present in the previous export. The current archive's labels otherwise match the code.

Direct public GitHub reads and Git pushes succeeded with sandbox escalation. The sandbox sometimes reports DNS failures; `gh auth status` also reported invalid credentials inside the sandbox, but `git push origin main` worked with escalation. Do not initiate authentication changes without cause. Do not expose credentials.

The user explicitly requested that all task work be committed and pushed at the pause. Commit only this task's files; preserve the unrelated dirty worktree. On resumption, follow any new instructions about further publication or commits.
