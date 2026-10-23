"""Four reporter states with high single-channel and lower joint-detection gates."""
from __future__ import annotations

import numpy as np

STATES = ("green_only", "red_only", "both", "neither")


def classify(green, red, thresholds):
    g, r = np.asarray(green, float), np.asarray(red, float)
    if g.shape != r.shape or not (np.isfinite(g).all() and np.isfinite(r).all()):
        raise ValueError("Both scores must be finite; missing is not neither")
    lg, hg = thresholds["green"]["low"], thresholds["green"]["high"]
    lr, hr = thresholds["red"]["low"], thresholds["red"]["high"]
    if not (0 <= lg <= hg and 0 <= lr <= hr and np.isfinite([lg, hg, lr, hr]).all()):
        raise ValueError("Require finite 0 <= low <= high thresholds")
    return np.select([(g > hg) & (r <= lr), (r > hr) & (g <= lg), (g > lg) & (r > lr)],
                     ["green_only", "red_only", "both"], default="neither")


def candidates(values, high):
    # One representative per interval with distinct training predictions; include
    # the unchanged high gate so the fit need not invent evidence for relaxation.
    edges = np.unique(np.r_[0., np.asarray(values)[(values > 0) & (values < high)], high])
    return np.unique(np.r_[0., (edges[:-1]+edges[1:])/2, high])


def fit_lower(green, red, labels, high):
    g, r, y = np.asarray(green, float), np.asarray(red, float), np.asarray(labels)
    if not (len(g) == len(r) == len(y)) or not np.isfinite([g, r]).all() or not set(y) <= set(STATES):
        raise ValueError("Fit requires finite paired scores and clear reviewed states")
    positive = y == "both"
    if positive.sum() < 2 or (y == "neither").sum() < 2:
        raise ValueError("Need at least two usable reviewed both and two neither examples")
    cg, cr = candidates(g, high["green"]), candidates(r, high["red"])
    gg, rr = np.meshgrid(cg, cr, indexing="ij")
    gl, rl = gg.ravel(), rr.ravel()
    joint = (g[None, :] > gl[:, None]) & (r[None, :] > rl[:, None])
    sensitivity = joint[:, positive].mean(axis=1)
    specificity = (~joint[:, ~positive]).mean(axis=1)
    balanced = (sensitivity+specificity)/2
    # The objective concerns coexpression; single-positive reviews are negative
    # controls for the opposite channel. No desired class proportions enter.
    order = np.lexsort((gl, gl/high["green"]+rl/high["red"], specificity, np.round(balanced, 12)))
    best = int(order[-1])
    thresholds = {"green": {"low": float(gl[best]), "high": high["green"]},
                  "red": {"low": float(rl[best]), "high": high["red"]}}
    return thresholds, {"balanced_both_agreement": float(balanced[best]),
                        "both_sensitivity": float(sensitivity[best]),
                        "nonboth_specificity": float(specificity[best]),
                        "candidate_pairs": len(gl)}
