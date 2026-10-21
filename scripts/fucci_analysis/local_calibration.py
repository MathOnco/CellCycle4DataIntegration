"""Local reporter measurements and simple image-reviewed thresholds for one FoF."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import ndimage, stats

from .data import sha256
from .review import normalized_plane, planes

CHANNELS = {"green": "00", "red": "02"}
FEATURES = ["mean_excess", "median_excess", "q75_excess", "mean_contrast", "median_contrast", "q75_contrast"]
RINGS = {"main": (3, 12), "near": (2, 8), "far": (5, 20)}
VARIANTS = {
    "primary": ("original", "main", "median", "all"),
    "near_reference": ("original", "near", "median", "all"),
    "far_reference": ("original", "far", "median", "all"),
    "trimmed_reference": ("original", "main", "trimmed", "all"),
    "mean_reference": ("original", "main", "mean", "all"),
    "erode_1px": ("erode1", "main", "median", "all"),
    "erode_2px": ("erode2", "main", "median", "all"),
    "dilate_1px": ("dilate1", "main", "median", "all"),
    "even_z": ("original", "main", "median", "even"),
    "odd_z": ("original", "main", "median", "odd"),
    "large_cross_sections": ("original", "main", "median", "core"),
}
STATE_COLORS = {"green_only": "#23a765", "red_only": "#e34c5b", "both": "#c6a52a", "unresolved": "#a0a0a0"}


def local_masks(geometry, all_labels, obj):
    inside = geometry == obj
    distance_out = ndimage.distance_transform_edt(~inside)
    distance_in = ndimage.distance_transform_edt(np.pad(inside, 1))[1:-1, 1:-1]
    foreground = {"original": inside, "erode1": inside & (distance_in > 1),
                  "erode2": inside & (distance_in > 2),
                  "dilate1": (distance_out <= 1) & ((all_labels == 0) | inside)}
    rings = {name: (distance_out > lo) & (distance_out <= hi) & (all_labels == 0)
             for name, (lo, hi) in RINGS.items()}
    return foreground, rings


def pixel_stats(values, background=False):
    if not len(values):
        names = ["mean", "median", "trimmed", "mad"] if background else ["mean", "median", "q75"]
        return {"n": 0, **dict.fromkeys(names, np.nan)}
    median = np.median(values)
    result = {"n": len(values), "mean": float(np.mean(values, dtype=np.float64)), "median": float(median)}
    if background:
        result.update(trimmed=float(stats.trim_mean(values, .2)), mad=float(1.4826*np.median(np.abs(values-median))))
    else:
        result["q75"] = float(np.quantile(values, .75))
    return result


def measure_planes(mask, components, units, image_dir, manifest):
    ids = set(units.geometry_id.astype(int))
    expected = {(v["channel"], v["z"]): v["sha256"] for v in manifest["image_files"]}
    files = {c: planes(image_dir, number) for c, number in CHANNELS.items()}
    rows = []
    for z in range(len(mask)):
        raw = {}
        for c in CHANNELS:
            path = files[c][z]
            if sha256(path) != expected[(c, z)]:
                raise ValueError(f"Image changed: {path}")
            raw[c] = normalized_plane(path)
        geometry = components[z]
        boxes = ndimage.find_objects(geometry)
        for obj in sorted(ids.intersection(np.unique(geometry))):
            box = boxes[obj-1]
            region = tuple(slice(max(0, b.start-21), min(size, b.stop+21)) for b, size in zip(box, geometry.shape))
            foreground, rings = local_masks(geometry[region], mask[z][region], obj)
            for c in CHANNELS:
                image = raw[c][region]
                row = {"geometry_id": obj, "z": z, "channel": c}
                for name, pixels in foreground.items():
                    row.update({f"{name}_{k}": v for k, v in pixel_stats(image[pixels]).items()})
                for name, pixels in rings.items():
                    row.update({f"{name}_{k}": v for k, v in pixel_stats(image[pixels], background=True).items()})
                rows.append(row)
        if (z+1) % 10 == 0:
            print(f"Local measurements: {z+1}/{len(mask)} planes", flush=True)
    result = pd.DataFrame(rows)
    for c in CHANNELS:
        d = result[result.channel.eq(c)]
        sums = (d.original_mean*d.original_n).groupby(d.geometry_id).sum()
        counts = d.original_n.groupby(d.geometry_id).sum()
        expected_means = units.set_index("geometry_id")[c].reindex(sums.index)
        np.testing.assert_allclose(sums/counts, expected_means, rtol=2e-7, atol=1e-9)
        np.testing.assert_array_equal(counts, units.set_index("geometry_id").volume.reindex(counts.index))
    return result


def aggregate_features(plane_measurements):
    rows = []
    for (obj, channel), whole in plane_measurements.groupby(["geometry_id", "channel"], sort=True):
        for variant, (fg, bg, summary, z_subset) in VARIANTS.items():
            d = whole.copy()
            if z_subset == "even":
                d = d[d.z.mod(2).eq(0)]
            elif z_subset == "odd":
                d = d[d.z.mod(2).eq(1)]
            elif z_subset == "core":
                d = d[d.original_n >= whole.original_n.max()*.5]
            total = d[f"{fg}_n"].sum()
            valid = d[f"{fg}_n"].gt(0) & d[f"{bg}_n"].ge(50)
            d = d[valid]
            weights = d[f"{fg}_n"].to_numpy(float)
            row = {"geometry_id": obj, "channel": channel, "variant": variant,
                   "valid_voxels": float(weights.sum()), "reference_coverage": float(weights.sum()/total) if total else 0,
                   "valid_planes": len(d), "max_plane_area": int(whole.original_n.max())}
            if weights.sum():
                reference = d[f"{bg}_{summary}"].to_numpy(float)
                noise = np.maximum(d[f"{bg}_mad"].to_numpy(float), 1/65535)
                row["reference_mean"] = float(np.average(reference, weights=weights))
                row["reference_robust_sd"] = float(np.average(noise, weights=weights))
                for stat in ["mean", "median", "q75"]:
                    excess = d[f"{fg}_{stat}"].to_numpy(float) - reference
                    row[f"{stat}_excess"] = float(np.average(excess, weights=weights))
                    row[f"{stat}_contrast"] = float(np.average(excess/noise, weights=weights))
            else:
                row.update(dict.fromkeys(FEATURES+["reference_mean", "reference_robust_sd"], np.nan))
            rows.append(row)
    return pd.DataFrame(rows)


def threshold_fit(x, y):
    x, y = np.asarray(x, float), np.asarray(y, int)
    if set(y) != {0, 1} or not np.isfinite(x).all():
        raise ValueError("Threshold fitting needs finite scores and both reviewed channel states")
    unique = np.unique(x)
    thresholds = np.r_[np.nextafter(unique[0], -np.inf), (unique[:-1]+unique[1:])/2, unique[-1]]
    predictions = x[:, None] > thresholds
    sensitivity = predictions[y == 1].mean(axis=0)
    specificity = (~predictions[y == 0]).mean(axis=0)
    balanced = (sensitivity+specificity)/2
    # Ties favor specificity and then the larger threshold; cell counts never set prevalence.
    order = np.lexsort((thresholds, specificity, balanced))
    i = order[-1]
    return {"threshold": float(thresholds[i]), "balanced_agreement": float(balanced[i]),
            "positive_agreement": float(sensitivity[i]), "not_detected_agreement": float(specificity[i])}


def select_thresholds(features, annotations, seed=20261021):
    models, comparisons = {}, []
    if not annotations.split.eq("calibration").all():
        raise ValueError("Only calibration annotations may enter threshold selection")
    for c in CHANNELS:
        reference = annotations[annotations[c].isin(["positive", "not_detected"]) & annotations.mask_review.eq("usable")]
        d = reference.merge(features[features.channel.eq(c) & features.variant.eq("primary")], on="geometry_id", validate="one_to_one")
        d = d[d.reference_coverage.ge(.8) & d.valid_voxels.ge(100) & d.valid_planes.ge(3) & d.max_plane_area.ge(25)]
        y = d[c].eq("positive").to_numpy(int)
        if min(np.bincount(y, minlength=2)) < 3:
            raise ValueError(f"Too few clear references for {c}")
        for feature in FEATURES:
            x = d[feature].to_numpy(float)
            predicted = np.zeros(len(d), dtype=bool)
            for i in range(len(d)):
                train = np.arange(len(d)) != i
                predicted[i] = x[i] > threshold_fit(x[train], y[train])["threshold"]
            ba = .5*(predicted[y == 1].mean()+(~predicted[y == 0]).mean())
            comparisons.append({"channel": c, "feature": feature, "n": len(d), "positive_n": int(y.sum()),
                                "not_detected_n": int((y == 0).sum()), "loo_balanced_agreement": float(ba),
                                "loo_positive_agreement": float(predicted[y == 1].mean()),
                                "loo_not_detected_agreement": float((~predicted[y == 0]).mean())})
        candidates = [r for r in comparisons if r["channel"] == c]
        best = max(candidates, key=lambda r: (r["loo_balanced_agreement"], r["loo_not_detected_agreement"], -FEATURES.index(r["feature"])))
        x = d[best["feature"]].to_numpy(float)
        model = threshold_fit(x, y)
        rng = np.random.default_rng(seed + list(CHANNELS).index(c))
        bootstrap = []
        for _ in range(500):
            sample = np.r_[rng.choice(np.flatnonzero(y == 0), sum(y == 0)), rng.choice(np.flatnonzero(y == 1), sum(y == 1))]
            bootstrap.append(threshold_fit(x[sample], y[sample])["threshold"])
        model.update(best)
        model.update(bootstrap_threshold_low=float(np.quantile(bootstrap, .05)),
                     bootstrap_threshold_high=float(np.quantile(bootstrap, .95)),
                     bootstrap_replicates=500, calibration_review_ids=d.review_id.tolist())
        models[c] = model
    return models, pd.DataFrame(comparisons)


def channel_call(score, model):
    score = np.asarray(score, float)
    low, high = model["bootstrap_threshold_low"], model["bootstrap_threshold_high"]
    return np.where(~np.isfinite(score), "missing", np.where(score > high, "positive", np.where(score <= low, "not_detected", "ambiguous")))


def reporter_state(green, red):
    if green == "positive" and red == "not_detected":
        return "green_only"
    if green == "not_detected" and red == "positive":
        return "red_only"
    if green == "positive" and red == "positive":
        return "both"
    return "unresolved"


def apply_thresholds(features, models):
    d = features.copy()
    for c, model in models.items():
        use = d.channel.eq(c)
        d.loc[use, "score"] = d.loc[use, model["feature"]]
        d.loc[use, "channel_call"] = channel_call(d.loc[use, "score"], model)
        supported = d.reference_coverage.ge(.8) & d.valid_voxels.ge(100) & d.valid_planes.ge(3) & d.max_plane_area.ge(25)
        d.loc[use & ~supported, "channel_call"] = "insufficient_support"
    pivot = d.pivot(index=["geometry_id", "variant"], columns="channel", values="channel_call").reset_index()
    pivot["reporter_state"] = [reporter_state(g, r) for g, r in zip(pivot.green, pivot.red)]
    primary = pivot[pivot.variant.eq("primary")].copy().set_index("geometry_id")
    matrix = pivot.pivot(index="geometry_id", columns="variant", values="reporter_state")
    primary["variant_agreement"] = matrix.eq(primary.reporter_state, axis=0).mean(axis=1)
    primary["reporter_state_before_stability"] = primary.reporter_state
    primary["stable_across_variants"] = matrix.nunique(axis=1).eq(1)
    primary.loc[~primary.stable_across_variants, "reporter_state"] = "unresolved"
    reasons = []
    for row in primary.itertuples():
        flags = []
        if "insufficient_support" in (row.green, row.red): flags.append("insufficient_measurement_support")
        if "ambiguous" in (row.green, row.red): flags.append("threshold_uncertainty")
        if "missing" in (row.green, row.red): flags.append("missing_local_reference")
        if row.green == row.red == "not_detected": flags.append("neither_reporter_detected")
        if not row.stable_across_variants: flags.append("sensitive_to_measurement_choice")
        reasons.append(";".join(flags))
    primary["unresolved_reasons"] = reasons
    primary["conditional_phase"] = primary.reporter_state.map({"green_only": "G1_like", "red_only": "S_like", "both": "G2M_like", "unresolved": "unresolved"})
    return primary.reset_index(), pivot, d
