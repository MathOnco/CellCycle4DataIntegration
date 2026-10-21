#!/usr/bin/env python3
"""Verify the supplied FoF5 mask and render Fig. 1A/C-style spatial checks."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import zipfile

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "fucci_mpl_cache"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import to_rgb
from matplotlib.patches import Patch
import numpy as np
import pandas as pd
from scipy import ndimage
from skimage import measure, segmentation
import tifffile

from fucci_analysis.data import PHASES, gates, sha256, write_json
from fucci_analysis.outputs import PHASE_COLORS, save
from fucci_analysis.review import normalized_plane, planes

FIELD = "241016/5"
IMAGE_SET = "FoF5_241016_fucci.nucleus"
MASK_MEMBER = f"{IMAGE_SET}/{IMAGE_SET}_masks.tif"
CATEGORIES = ["G1", "G1S", "S", "G2M", "uncertain", "qc_review", "low_signal_phase_unresolved"]
CODE = {phase: i + 1 for i, phase in enumerate(CATEGORIES)}
PALETTE = np.array([[0, 0, 0]] + [to_rgb(PHASE_COLORS[p]) for p in CATEGORIES])
FLUORESCENCE_OUTLINE_ALPHA = .8
TITLES = {
    "source_rows": "Every exported connected component",
    "aggregated": "All components aggregated by original mask label",
    "dominant": "Largest component per original mask label",
    "singletons": "Only original labels with one component",
}


def read_sources(repo, mask_archive):
    reference = repo / "results/fucci_classification"
    manifest = json.loads((reference / "input_manifest.json").read_text())
    archive = Path(manifest["archive"])
    if sha256(archive) != manifest["archive_sha256"]:
        raise ValueError("The feature archive changed since the fitted analyses")
    keys = ["Date", "FoF", "ObjectNumber", "CellposeLabel", "AreaShape_Volume"]
    means = [f"Intensity_{stat}_{channel}" for channel in ["bright", "green", "red"]
             for stat in ["MeanIntensity", "IntegratedIntensity"]]
    boxes = [f"AreaShape_BoundingBox{side}_{axis}" for side in ["Minimum", "Maximum"] for axis in "XYZ"]
    with zipfile.ZipFile(archive) as zipped:
        with zipped.open("2410/object_features_new.csv") as member:
            source = pd.read_csv(member, usecols=keys + means + boxes)
    source = source[source.Date.eq(241016) & source.FoF.eq(5)].sort_values("ObjectNumber")
    mapping = pd.read_csv(reference / "object_mapping.csv.gz")
    mapping = mapping[mapping.Date.eq(241016) & mapping.FoF.eq(5)].sort_values("ObjectNumber")
    for column in ["ObjectNumber", "CellposeLabel"]:
        np.testing.assert_array_equal(source[column], mapping[column])
    np.testing.assert_array_equal(source.AreaShape_Volume, mapping.volume)
    source["object_id"] = mapping.object_id.to_numpy()
    source["baseline_phase"] = mapping.cellCycle.to_numpy()
    supplied = PHASES[gates(source.Intensity_MeanIntensity_green.to_numpy(),
                           source.Intensity_MeanIntensity_red.to_numpy(), .003, .0095)]
    np.testing.assert_array_equal(supplied, source.baseline_phase)
    with zipfile.ZipFile(mask_archive) as zipped:
        mask_bytes = zipped.read(MASK_MEMBER)
    mask = tifffile.imread(io.BytesIO(mask_bytes))
    if mask.ndim != 3 or not np.issubdtype(mask.dtype, np.integer):
        raise ValueError("Expected an integer Z/Y/X label mask")
    components = measure.label(mask, background=0, connectivity=3).astype(np.int32)
    component_ids = source.ObjectNumber.to_numpy(int)
    np.testing.assert_array_equal(component_ids, np.arange(1, components.max() + 1))
    volumes = np.bincount(components.ravel())
    np.testing.assert_array_equal(volumes[component_ids], source.AreaShape_Volume)
    parent_by_component = np.zeros(len(volumes), dtype=mask.dtype)
    parent_by_component[component_ids] = source.CellposeLabel
    for z in range(len(mask)):
        np.testing.assert_array_equal(parent_by_component[components[z]], mask[z])
    bounds = ndimage.find_objects(components)
    for axis, position in zip("XYZ", [2, 1, 0]):
        np.testing.assert_array_equal([b[position].start for b in bounds],
                                      source[f"AreaShape_BoundingBoxMinimum_{axis}"])
        np.testing.assert_array_equal([b[position].stop for b in bounds],
                                      source[f"AreaShape_BoundingBoxMaximum_{axis}"])
    predictions = {}
    prediction_paths = {}
    for policy, directory in [
        ("aggregated", reference),
        ("dominant", repo / "results/fucci_component_comparison/dominant"),
        ("singletons", repo / "results/fucci_component_comparison/singletons"),
    ]:
        path = directory / "mask_label_predictions.csv.gz"
        frame = pd.read_csv(path)
        predictions[policy] = frame[frame.field_id.eq(FIELD)].copy()
        prediction_paths[policy] = {"path": str(path.relative_to(repo)), "sha256": sha256(path)}
    parents = predictions["aggregated"]
    np.testing.assert_array_equal(np.flatnonzero(np.bincount(mask.ravel()))[1:],
                                  np.sort(parents.CellposeLabel.to_numpy(int)))
    np.testing.assert_array_equal(np.bincount(mask.ravel())[parents.CellposeLabel.to_numpy(int)], parents.volume)
    image_dir = repo / "data4paper/A01_rawData" / IMAGE_SET
    provenance = {
        "field_id": FIELD, "mask_archive": str(mask_archive), "mask_member": MASK_MEMBER,
        "mask_archive_sha256": sha256(mask_archive),
        "mask_member_sha256": hashlib.sha256(mask_bytes).hexdigest(),
        "feature_archive": str(archive), "feature_archive_sha256": manifest["archive_sha256"],
        "feature_member": "2410/object_features_new.csv",
        "prediction_files": prediction_paths,
        "mask_shape_zyx": list(mask.shape), "original_mask_labels": len(parents),
        "exported_components": len(source), "connectivity": 26,
        "all_parent_ids_component_ids_volumes_and_bounding_boxes_match": True,
    }
    return source, mask, components, predictions, image_dir, provenance


def verify_images(source, components, image_dir, slice_indices, out):
    """Recompute all 3D component means/sums from original pixels in all three channels."""
    volumes = np.bincount(components.ravel())
    ids = source.ObjectNumber.to_numpy(int)
    cached = {}
    limits = {}
    checks = []
    files = []
    for channel, number in [("green", "00"), ("red", "02"), ("bright", "01")]:
        channel_files = planes(image_dir, number)
        if len(channel_files) != len(components):
            raise ValueError(f"Missing planes for {channel}")
        sums = np.zeros(len(volumes), dtype=np.float64)
        samples = []
        for z, path in enumerate(channel_files):
            expected_suffix = f"_z{z:02}_ch{number}.tif"
            if not path.name.endswith(expected_suffix):
                raise ValueError("Missing or reordered image plane")
            plane = normalized_plane(path)
            if plane.shape != components.shape[1:]:
                raise ValueError("Image and mask dimensions differ")
            sums += np.bincount(components[z].ravel(), weights=plane.ravel(), minlength=len(volumes))
            samples.append(plane[::16, ::16].ravel())
            if z in slice_indices:
                cached[(channel, z)] = plane
            files.append({"channel": channel, "z": z, "path": str(path), "sha256": sha256(path)})
        observed = sums[ids] / volumes[ids]
        expected = source[f"Intensity_MeanIntensity_{channel}"].to_numpy()
        expected_sum = source[f"Intensity_IntegratedIntensity_{channel}"].to_numpy()
        mean_match = np.isclose(observed, expected, rtol=2e-5, atol=5e-7)
        sum_match = np.isclose(sums[ids], expected_sum, rtol=2e-5, atol=5e-7)
        checks.extend({"ObjectNumber": int(obj), "CellposeLabel": int(parent), "channel": channel,
                       "volume": int(volume), "table_mean": float(exp), "image_mean": float(obs),
                       "absolute_mean_error": float(abs(exp-obs)), "mean_matches": bool(ok),
                       "table_sum": float(exp_sum), "image_sum": float(obs_sum),
                       "sum_matches": bool(sum_ok)}
                      for obj, parent, volume, exp, obs, ok, exp_sum, obs_sum, sum_ok in
                      zip(ids, source.CellposeLabel, source.AreaShape_Volume, expected, observed,
                          mean_match, expected_sum, sums[ids], sum_match))
        if not mean_match.all() or not sum_match.all():
            raise ValueError(f"The supplied mask does not reproduce all {channel} measurements")
        quantiles = [.01, .998] if channel != "bright" else [.005, .995]
        low, high = np.quantile(np.concatenate(samples), quantiles)
        if not high > low:
            raise ValueError(f"Constant display signal for {channel}")
        limits[channel] = {"low": float(low), "high": float(high), "quantiles": quantiles,
                           "sampling": "Every sixteenth pixel in X and Y from all 70 planes"}
        print(f"{channel}: all {len(ids)} component means and sums match", flush=True)
    check_frame = pd.DataFrame(checks)
    check_frame.to_csv(out / "component_image_measurement_checks.csv", index=False)
    return cached, limits, files, float(check_frame.absolute_mean_error.max())


def build_policies(source, mask, components, predictions):
    policies = {}
    all_assignments = []
    for policy in TITLES:
        if policy == "source_rows":
            frame = source.rename(columns={"ObjectNumber": "geometry_id"}).copy()
            frame["unit_id"] = frame.object_id
            frame["provisional_phase"] = ""
            geometry = components
        else:
            frame = predictions[policy].copy()
            frame["unit_id"] = frame.mask_label_id
            geometry = mask if policy == "aggregated" else components
            # object_id ends in CellID, which can differ from the per-field ObjectNumber.
            frame["geometry_id"] = (frame.CellposeLabel if policy == "aggregated" else
                                    source.set_index("object_id").loc[frame.largest_object_id, "ObjectNumber"].to_numpy())
            if policy != "aggregated":
                selected = source.set_index("ObjectNumber").loc[frame.geometry_id]
                # Exported means and reconstructed sums/volumes can differ by CSV rounding.
                np.testing.assert_allclose(selected.Intensity_MeanIntensity_green, frame.green, rtol=2e-7, atol=1e-9)
                np.testing.assert_allclose(selected.Intensity_MeanIntensity_red, frame.red, rtol=2e-7, atol=1e-9)
                np.testing.assert_array_equal(selected.baseline_phase, frame.baseline_phase)
        if not frame.geometry_id.is_unique or not frame.unit_id.is_unique:
            raise ValueError("Each selected measurement must map to exactly one geometry")
        lookups = {}
        for name in ["baseline_phase"] + ([] if policy == "source_rows" else ["provisional_phase"]):
            lookup = np.zeros(int(geometry.max()) + 1, dtype=np.uint8)
            lookup[frame.geometry_id.to_numpy(int)] = [CODE[p] for p in frame[name]]
            lookups[name] = lookup
        policies[policy] = {"frame": frame, "geometry": geometry, "lookups": lookups}
        record = frame[["unit_id", "CellposeLabel", "geometry_id", "baseline_phase", "provisional_phase"]].copy()
        record.insert(0, "policy", policy)
        all_assignments.append(record)
    return policies, pd.concat(all_assignments, ignore_index=True)


def stretch(plane, limits):
    return np.clip((plane-limits["low"]) / (limits["high"]-limits["low"]), 0, 1)


def selected_boundaries(geometry, lookup):
    return segmentation.find_boundaries(geometry, mode="inner") & (lookup[geometry] > 0)


def overlay(bright, geometry, lookup):
    code = lookup[geometry]
    selected = code > 0
    rgb = np.repeat(bright[..., None], 3, axis=2)
    rgb[selected] = .45*rgb[selected] + .55*PALETTE[code[selected]]
    boundaries = selected_boundaries(geometry, lookup)
    rgb[boundaries] = PALETTE[code[boundaries]]
    return rgb


def draw_figure(policy, item, z, cached, limits, crop=None):
    region = (slice(None), slice(None)) if crop is None else (slice(crop[1], crop[3]), slice(crop[0], crop[2]))
    green = stretch(cached[("green", z)], limits["green"])[region]
    red = stretch(cached[("red", z)], limits["red"])[region]
    bright = stretch(cached[("bright", z)], limits["bright"])[region]
    merged = np.stack([red, green, np.zeros_like(red)], axis=-1)
    geometry = item["geometry"][z][region]
    baseline = item["lookups"]["baseline_phase"]
    boundaries = selected_boundaries(geometry, baseline)
    merged[boundaries] = (1-FLUORESCENCE_OUTLINE_ALPHA)*merged[boundaries] + FLUORESCENCE_OUTLINE_ALPHA
    visible_ids = np.unique(geometry)
    visible = int(np.count_nonzero(baseline[visible_ids]))
    ncols = 2 if policy == "source_rows" else 3
    fig, axes = plt.subplots(1, ncols, figsize=(6*ncols, 7))
    axes[0].imshow(merged, interpolation="nearest")
    axes[0].set_title("A  Green + red fluorescence\nWhite outlines: selected segmentation masks", loc="left", fontsize=12)
    axes[1].imshow(overlay(bright, geometry, baseline), interpolation="nearest")
    axes[1].set_title(f"C1  Supplied phase thresholds\n{visible} selected units intersect this plane", loc="left", fontsize=12)
    if ncols == 3:
        candidate = item["lookups"]["provisional_phase"]
        axes[2].imshow(overlay(bright, geometry, candidate), interpolation="nearest")
        axes[2].set_title("C2  Refitted candidate\nUncertainty and QC retained", loc="left", fontsize=12)
    for ax in axes:
        ax.axis("off")
    height, width = merged.shape[:2]
    bar = 100 if width > 500 else 25
    x0, y0 = width*.06, height*.92
    axes[0].plot([x0, x0+bar], [y0, y0], color="white", lw=3)
    axes[0].text(x0+bar/2, y0-height*.025, f"{bar} pixels", color="white", ha="center", fontsize=9)
    present = list(PHASES) + ([] if ncols == 2 else ["uncertain", "qc_review"])
    fig.legend(handles=[Patch(color=PHASE_COLORS[p], label=p.replace("_", " ")) for p in present],
               loc="lower center", bbox_to_anchor=(.5, .062), ncol=len(present), frameon=False)
    extra = "" if crop is None else f"; crop X={crop[0]}:{crop[2]}, Y={crop[1]}:{crop[3]}"
    fig.suptitle(f"241016 / FoF 5 — z={z} (zero-based){extra}\n{TITLES[policy]}; n={len(item['frame']):,} in the full 3D stack", fontsize=14)
    fig.text(.5, .035, "Phase assignments use full 3D measurements. Fixed display stretches across all panels and slices; native image/mask coordinates.",
             ha="center", fontsize=9)
    footer = "C1: green gate 0.003; red gate 0.0095. Only the selected measurement units are colored."
    if ncols == 3:
        footer += " C2 is provisional."
    fig.text(.5, .012, footer,
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .12, 1, .91))
    return fig


def write_report(repo, out, figs, provenance, policies, z, slice_indices):
    relative = lambda p: "../" + str(p.relative_to(repo))
    text = "# FoF5 spatial verification: Fig. 1A/C-style overlays\n\n"
    text += "The supplied `FoF5_241016_fucci.nucleus.zip` provides the first verified image–mask pair for this analysis. The figure uses the new Saeed feature table from `Archive (6).zip`. No pseudotime analysis or Fig. 1E reconstruction is included.\n\n"
    text += "## Input verification\n\n"
    text += f"- **578 original mask labels and 1,314 connected components** match the new table, including parent IDs, component IDs, volumes and bounding boxes.\n- All **3,942 component/channel pairs** reproduce their exported 3D mean and integrated intensity from the raw green, red and brightfield images. Maximum absolute mean error: `{provenance['maximum_absolute_mean_error']:.3g}` on the normalized 0–1 scale.\n- All 70 image planes align in native X/Y/Z coordinates. No registration transform or mask editing was applied.\n\n"
    text += "## Figures\n\n"
    text += f"The main figure is a single actual plane at **z={z}** of the 70-plane stack (default: the middle plane, z=35). Panel A merges green and red with thin white segmentation outlines; C1 colors masks using the supplied phase thresholds; C2 colors the same selected masks using the saved refitted model, including uncertainty and QC. The outlines in A use exactly the same selected mask boundaries as the classification panels, including boundaries between touching labels. The field's 3D assignment totals are below; each panel also states how many selected units intersect its plane.\n\n"
    for policy in TITLES:
        p = figs / f"fig1AC_{policy}_z{z:02}.png"
        text += f"- **{TITLES[policy]}:** [PNG]({relative(p)}) · [PDF]({relative(p.with_suffix('.pdf'))})\n"
    text += f"- [Largest-component view across z={', '.join(map(str, slice_indices))} (PDF)]({relative(figs/'fig1AC_dominant_slice_atlas.pdf')})\n"
    text += f"- [Magnified central-region comparison]({relative(figs/f'fig1AC_dominant_crop_z{z:02}.png')})\n"
    text += f"- [Magnified upper-left cluster]({relative(figs/f'fig1AC_dominant_cluster_z{z:02}.png')})\n\n"
    audit_path = out / "fluorescence_audit" / f"summary_z{z:02}.json"
    if audit_path.exists():
        audit = json.loads(audit_path.read_text())
        visible = audit["visible"]
        substantial = audit["visible_at_least_100_pixels"]
        audit_figs = figs / "fluorescence_audit"
        text += "## Fluorescence interpretation audit — 2026-10-21\n\n"
        text += f"The images reveal a calibration problem that exact image–table agreement does not resolve. Among the **{visible['n']} dominant components visible at z={z}**, **{visible['green_above_gate']} exceed the green cutoff**. C1 assigns {visible['C1_counts'].get('G2M', 0)} to G2M, effectively splitting this displayed population by red intensity. The gates correspond to only {audit['gate_display_fraction']['green']*100:.1f}% green and {audit['gate_display_fraction']['red']*100:.1f}% red on panel A's display scale.\n\n"
        text += f"Unmasked local annuli also exceed the green cutoff for **{visible['green_annulus_above_gate']}/{visible['green_annulus_valid_n']}** displayed components and both cutoffs for **{visible['annulus_above_both_gates']}/{visible['annulus_both_channels_valid_n']}**. Annuli pool pixels 3–12 X/Y pixels outside each component across its z extent and exclude every mask label. They can contain diffuse fluorescence and are not negative controls; these results show that the supplied absolute gates do not establish localized reporter positivity.\n\n"
        text += f"Using the displayed slice means changes **{visible['slice_vs_3d_calls_changed']}/{visible['n']}** C1 calls. Among components with at least 100 pixels in the slice, only **{substantial['slice_vs_3d_calls_changed']}/{substantial['n']}** change. Thus the slice/3D difference contributes but does not explain most of the visual mismatch. The table means reproduce the original pixels, and saved C2 probabilities reproduce from those means; C2 inherits the same raw features and gate anchors. Neither panel currently establishes a reliable biological phase map.\n\n"
        text += f"- [Six cells with separate channels, raw values, local references and C1/C2 calls]({relative(audit_figs/f'cell_examples_z{z:02}.png')}) · [PDF]({relative(audit_figs/f'cell_examples_z{z:02}.pdf')})\n"
        text += f"- [Quantitative diagnostic figure]({relative(audit_figs/f'measurement_diagnostics_z{z:02}.png')}) · [PDF]({relative(audit_figs/f'measurement_diagnostics_z{z:02}.pdf')})\n"
        text += f"- [Per-cell measurements]({relative(audit_path.parent/f'per_cell_measurements_z{z:02}.csv')}) · [Summary and provenance]({relative(audit_path)})\n\n"
        text += "The next classification step is to evaluate background-aware reporter measurements against the images and reference reporter-positive/negative cells, retaining low-contrast objects as unresolved before refitting. The annular subtraction here is a diagnostic and was not used to issue new phase labels. Reproduce with `OPENBLAS_NUM_THREADS=1 python scripts/audit_fucci_fluorescence.py`.\n\n"
    text += "## Counts in the full 3D field\n\n| Input | Units | Supplied G1 | G1S | S | G2M | Candidate G1 | G2M | Uncertain | QC |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n"
    for policy, item in policies.items():
        f = item["frame"]
        b, c = f.baseline_phase.value_counts(), f.provisional_phase.value_counts()
        candidate = ["—"]*4 if policy == "source_rows" else [str(int(c.get(p, 0))) for p in ["G1", "G2M", "uncertain", "qc_review"]]
        text += f"| {policy} | {len(f)} | " + " | ".join(str(int(b.get(p, 0))) for p in ["G1", "G1S", "S", "G2M"]) + " | " + " | ".join(candidate) + " |\n"
    text += "\nThe source-row view colors every measured connected component by its own supplied phase. The aggregated view colors the full original label. The dominant view colors only its largest component. The singleton view colors only labels that originally had one component. Excluded regions retain the underlying brightfield image. No additional size filtering was applied.\n\n"
    text += "## Display and interpretation\n\nEach channel uses a fixed display stretch estimated across all 70 planes: 1st–99.8th percentiles for green/red, 0.5th–99.5th for brightfield, sampled every sixteenth X/Y pixel. Green and red have separate display ranges; these improve visibility and do not change the feature values or thresholds. Panel A draws one-pixel inner mask boundaries in white at 80% opacity, without filling the interiors; white has no phase meaning. C1/C2 mask interiors are drawn with 55% phase-color opacity and full-color boundaries. Scale bars are in pixels.\n\n"
    text += "Labels use full 3D measurements, so fluorescence in a single slice need not show the same green/red balance as the object's 3D average. These panels check spatial registration and classification consistency; they do not independently validate biological phase accuracy. The candidate model was loaded from the completed analysis and was not refitted.\n\n"
    text += "## Reproduce\n\n```bash\nOPENBLAS_NUM_THREADS=1 python scripts/plot_fucci_spatial_verification.py\n```\n\n"
    text += "Use `--z` to choose a different main plane. The verification JSON records input and prediction hashes, image paths/hashes, display ranges and exact slice/crop coordinates. Per-component checks and all plotted-unit assignments are saved beside it under `results/fucci_spatial_verification/241016_5`.\n"
    (repo / "docs/fucci_spatial_verification_241016_5.md").write_text(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mask-archive", type=Path, default=Path.home() / "Downloads/FoF5_241016_fucci.nucleus.zip")
    parser.add_argument("--z", type=int, default=35)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    out = repo / "results/fucci_spatial_verification/241016_5"
    figs = repo / "figs4paper/fucci_spatial_verification/241016_5"
    out.mkdir(parents=True, exist_ok=True)
    figs.mkdir(parents=True, exist_ok=True)
    source, mask, components, predictions, image_dir, provenance = read_sources(repo, args.mask_archive)
    if args.z < 0 or args.z >= len(mask):
        raise ValueError("Main slice lies outside the mask")
    slice_indices = sorted(set([15, 25, 35, 45, 55, args.z]))
    cached, limits, files, error = verify_images(source, components, image_dir, slice_indices, out)
    policies, assignments = build_policies(source, mask, components, predictions)
    assignments.to_csv(out / "plotted_unit_assignments.csv", index=False)
    for policy, item in policies.items():
        save(draw_figure(policy, item, args.z, cached, limits), figs / f"fig1AC_{policy}_z{args.z:02}")
    with PdfPages(figs / "fig1AC_dominant_slice_atlas.pdf") as pdf:
        for z in slice_indices:
            fig = draw_figure("dominant", policies["dominant"], z, cached, limits)
            pdf.savefig(fig)
            plt.close(fig)
    crop = [256, 256, 768, 768]
    save(draw_figure("dominant", policies["dominant"], args.z, cached, limits, crop),
         figs / f"fig1AC_dominant_crop_z{args.z:02}")
    cluster_crop = [64, 96, 576, 608]
    save(draw_figure("dominant", policies["dominant"], args.z, cached, limits, cluster_crop),
         figs / f"fig1AC_dominant_cluster_z{args.z:02}")
    provenance.update({
        "all_checks_passed": True, "all_component_means_and_sums_match_all_three_channels": True,
        "component_channel_comparisons": len(source)*3, "maximum_absolute_mean_error": error,
        "image_files": files, "display_limits": limits, "primary_z": args.z,
        "atlas_z_indices": slice_indices, "crop_xyxy": crop, "cluster_crop_xyxy": cluster_crop,
        "coordinate_transform": "none",
        "fluorescence_mask_outlines": {
            "color": "white", "alpha": FLUORESCENCE_OUTLINE_ALPHA,
            "width_in_mask_pixels": 1, "boundary_mode": "inner",
            "selection": "same selected mask geometry as the classification panels",
        },
        "models_refitted": False, "mask_voxels_changed": False, "independent_phase_validation": False,
        "script_sha256": sha256(Path(__file__)),
    })
    write_json(out / "image_mask_verification.json", provenance)
    write_report(repo, out, figs, provenance, policies, args.z, slice_indices)
    print(f"Verified {len(source)} components. Figures: {figs}", flush=True)


if __name__ == "__main__":
    main()
