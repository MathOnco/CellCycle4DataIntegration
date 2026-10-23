"""Rerun the original reporter classifier, then refine only its neither region."""
from __future__ import annotations

import numpy as np

from force_fucci_fof5_reporter_states import point_states


def classify(green, red, thresholds):
    """Return final states, freshly computed original states, and promotion flags.

    No saved state or cell identifier is accepted as a prediction input. Every
    invocation, including measurement perturbations, runs the original function.
    """
    g, r = np.asarray(green, float), np.asarray(red, float)
    lg, hg = thresholds["green"]["low"], thresholds["green"]["high"]
    lr, hr = thresholds["red"]["low"], thresholds["red"]["high"]
    if not (np.isfinite([lg, hg, lr, hr]).all() and 0 <= lg <= hg and 0 <= lr <= hr):
        raise ValueError("Require finite 0 <= lower <= original thresholds")
    original_models = {"green": {"threshold": hg}, "red": {"threshold": hr}}
    original, _, _ = point_states(g, r, original_models)
    promoted = (original == "neither") & (g > lg) & (r > lr)
    refined = np.where(promoted, "both", original)
    return refined, original, promoted
