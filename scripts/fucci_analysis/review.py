"""Local image compatibility checks and unannotated review sheets."""
from __future__ import annotations

import re
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import pandas as pd
import tifffile


def planes(image_dir, channel):
    found = []
    for path in Path(image_dir).glob(f"*_ch{channel}.tif"):
        match = re.search(r"_z(\d+)_ch", path.name)
        if match:
            found.append((int(match.group(1)), path))
    return [p for _, p in sorted(found)]


def normalized_plane(path):
    try:
        image = tifffile.imread(path)
    except ValueError as error:
        if "imagecodecs" not in str(error):
            raise
        # Pillow's bundled libtiff decodes LZW while preserving the source bit depth.
        from PIL import Image
        with tifffile.TiffFile(path) as tif:
            source_dtype = tif.pages[0].dtype
        with Image.open(path) as pil:
            image = np.asarray(pil).astype(source_dtype, copy=False)
    if np.issubdtype(image.dtype, np.integer):
        return image.astype(np.float32) / np.iinfo(image.dtype).max
    return image.astype(float)


def check_raw_images(objects, inventory, config, out):
    inventory = inventory.copy()
    checks = []
    for i, field in inventory.iterrows():
        if not field.raw_images_available:
            continue
        subset = objects[objects.field_id == field.field_id]
        bbox_volume = np.prod(subset[[f"{a}_max" for a in "xyz"]].to_numpy() -
                              subset[[f"{a}_min" for a in "xyz"]].to_numpy(), axis=1)
        eligible = subset[(subset.volume == bbox_volume) & (subset.volume <= 8)]
        selected = eligible.sample(min(10, len(eligible)), random_state=config["seed"])
        plane_lists = {c: planes(field.image_dir, ch) for c, ch in [("green", "00"), ("red", "02")]}
        cache = {}
        errors = []
        for _, obj in selected.iterrows():
            for channel in ["green", "red"]:
                values = []
                for z in range(int(obj.z_min), int(obj.z_max)):
                    key = (channel, z)
                    if z >= len(plane_lists[channel]):
                        raise ValueError(f"Insufficient planes for {field.field_id}")
                    if key not in cache:
                        cache[key] = normalized_plane(plane_lists[channel][z])
                    values.extend(cache[key][int(obj.y_min):int(obj.y_max), int(obj.x_min):int(obj.x_max)].ravel())
                observed = float(np.mean(np.asarray(values, dtype=np.float64)))
                error = abs(observed - obj[channel])
                matched = bool(np.isclose(observed, obj[channel], rtol=2e-5, atol=5e-7))
                errors.append(matched)
                checks.append({"field_id": field.field_id, "object_id": obj.object_id, "channel": channel,
                               "volume": obj.volume, "exported_mean": obj[channel], "image_mean": observed,
                               "absolute_error": error, "matched": matched,
                               "method": "Full occupied bounding box of <=8 voxels; integer dtype normalization"})
        inventory.at[i, "image_measurements_checked"] = bool(errors)
        inventory.at[i, "image_measurements_match"] = bool(errors and all(errors))
        inventory.at[i, "image_measurements_compared"] = len(errors)
        inventory.at[i, "calibration_ready"] = bool(errors and all(errors) and field.mask_components_match)
        del cache
    pd.DataFrame(checks).to_csv(out / "image_value_checks.csv", index=False)
    inventory.to_csv(out / "image_inventory.csv", index=False)
    return inventory


def choose_review(labels, count):
    selected = []
    # Include low confidence, disagreements, dominant states, and tiny supports.
    choices = [labels.sort_values("confidence"),
               labels[labels.baseline_disagreement].sort_values("confidence", ascending=False),
               labels[labels.all_components_tiny].sort_values("volume"),
               labels[labels.candidate_state == "high_low"].sort_values("confidence", ascending=False),
               labels[labels.candidate_state == "low_high"].sort_values("confidence", ascending=False),
               labels[labels.candidate_state == "high_high"].sort_values("confidence", ascending=False)]
    for choice in choices:
        choice = choice[~choice.mask_label_id.isin(selected)]
        if len(choice):
            selected.append(choice.mask_label_id.iloc[0])
    rest = labels[~labels.mask_label_id.isin(selected)].sort_values("confidence")
    selected.extend(rest.mask_label_id.tolist()[:max(0, count - len(selected))])
    return labels.set_index("mask_label_id").loc[selected[:count]].reset_index()


def create_review_sheets(labels, objects, inventory, config, out, figs):
    selected_rows = []
    obj_lookup = objects.set_index("object_id")
    with PdfPages(figs / "image_review.pdf") as pdf:
        for _, field in inventory[inventory.raw_images_available].iterrows():
            subset = labels[labels.field_id == field.field_id]
            selected = choose_review(subset, config["review_objects_per_field"])
            files = {c: planes(field.image_dir, ch) for c, ch in [("green", "00"), ("red", "02")]}
            n = len(selected)
            fig, axes = plt.subplots(3, n, figsize=(max(12, 2.8*n), 8), squeeze=False)
            cached = {}
            # Display stretches are shared across selected planes in each field/channel.
            z_values = sorted(set(int(round(v)) for v in selected.largest_z))
            scale = {}
            for channel in files:
                for z in z_values:
                    cached[(channel, z)] = normalized_plane(files[channel][z])
                samples = np.concatenate([cached[(channel, z)][::8, ::8].ravel() for z in z_values])
                scale[channel] = np.quantile(samples, [.01, .995])
            for col, (_, parent) in enumerate(selected.iterrows()):
                obj = obj_lookup.loc[parent.largest_object_id]
                z = int(round(obj.z))
                cx, cy = int(round(obj.x)), int(round(obj.y))
                radius = max(24, min(96, int(max(obj.x_max-obj.x_min, obj.y_max-obj.y_min)/2)+8))
                shape = cached[("green", z)].shape
                x0, x1 = max(0, cx-radius), min(shape[1], cx+radius)
                y0, y1 = max(0, cy-radius), min(shape[0], cy+radius)
                crops = {c: cached[(c, z)][y0:y1, x0:x1] for c in files}
                for row, channel in enumerate(["green", "red"]):
                    axes[row, col].imshow(crops[channel], cmap="gray", vmin=scale[channel][0], vmax=scale[channel][1])
                    axes[row, col].plot([cx-x0], [cy-y0], "+", color="cyan", ms=6)
                merged = np.zeros(crops["green"].shape + (3,))
                for channel, rgb_axis in [("red", 0), ("green", 1)]:
                    lo, hi = scale[channel]
                    merged[:, :, rgb_axis] = np.clip((crops[channel]-lo)/max(hi-lo, 1e-8), 0, 1)
                axes[2, col].imshow(merged)
                axes[2, col].plot([cx-x0], [cy-y0], "+", color="cyan", ms=6)
                axes[0, col].set_title(f"Mask {parent.CellposeLabel}; z={z}\n{parent.candidate_state}; p={parent.confidence:.2f}", fontsize=9)
                axes[2, col].set_xlabel(f"Baseline {parent.baseline_phase}; {parent.provisional_phase}\n{int(parent.volume):,} voxels; {int(parent.n_components)} components", fontsize=8)
                rec = {c: parent[c] for c in ["mask_label_id", "field_id", "CellposeLabel", "largest_object_id", "volume", "n_components", "baseline_phase", "candidate_state", "confidence", "provisional_phase"]}
                rec.update(raw_image_sample_check=bool(field.image_measurements_match),
                           mask_verified=bool(field.mask_components_match),
                           crop_z=z, review_status="unreviewed", reviewer_reporter_state="",
                           reviewer_phase="", independent_phase_evidence="", reviewer_notes="")
                selected_rows.append(rec)
            for row, name in enumerate(["Green", "Red", "Merge"]):
                axes[row, 0].set_ylabel(name)
            for ax in axes.flat:
                ax.set_xticks([]); ax.set_yticks([])
            fig.suptitle(f"{field.field_id}: image review candidates, not validated phase labels\nLargest-component center marked; common display stretch per channel; matching mask unavailable", fontsize=11)
            fig.tight_layout(rect=(0, 0, 1, .91))
            pdf.savefig(fig)
            if field.field_id == inventory[inventory.raw_images_available].field_id.iloc[0]:
                fig.savefig(figs / "image_review_example.png", dpi=150)
            plt.close(fig)
    pd.DataFrame(selected_rows).to_csv(out / "image_review_annotations.csv", index=False)
    # Verify fragmentation visually where the original mask exists but raw images do not.
    with PdfPages(figs / "mask_review.pdf") as pdf:
        for _, field in inventory[inventory.mask_components_match].iterrows():
            mask = tifffile.imread(field.mask_path)
            subset = labels[labels.field_id == field.field_id].sort_values("n_components", ascending=False).head(4)
            fig, axes = plt.subplots(1, len(subset), figsize=(14, 4), squeeze=False)
            for ax, (_, parent) in zip(axes.flat, subset.iterrows()):
                z = int(round(parent.largest_z))
                x0, x1 = max(0, int(parent.x_min)-4), min(mask.shape[2], int(parent.x_max)+4)
                y0, y1 = max(0, int(parent.y_min)-4), min(mask.shape[1], int(parent.y_max)+4)
                ax.imshow(mask[z, y0:y1, x0:x1] == int(parent.CellposeLabel), cmap="gray")
                ax.set_title(f"Mask {parent.CellposeLabel}; z={z}\n{int(parent.n_components)} 3D components\nLargest component: {parent.largest_component_fraction:.1%}", fontsize=9)
                ax.axis("off")
            fig.suptitle(f"{field.field_id}: verified mask components; fluorescence images unavailable")
            fig.tight_layout(); pdf.savefig(fig); plt.close(fig)
            del mask
    return len(selected_rows)
