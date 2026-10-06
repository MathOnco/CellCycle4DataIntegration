"""Small gate-anchored density models; posterior scores are not phase validation.

Coordinates are log10(intensity / the supplied acquisition-specific gate).
Each Gaussian mean stays on the appropriate side of zero. This gives stable
reporter-state identities and explicitly retains the baseline's calibration
assumption. The joint model learns unrestricted state frequencies; diagonal
within-state covariances keep the model small and expose this fit assumption.
"""
from __future__ import annotations

import numpy as np
from scipy.special import logsumexp

PATTERNS = np.array([[0, 0], [1, 0], [0, 1], [1, 1]])


class AnchoredMixture:
    def __init__(self, patterns=PATTERNS, variance_floor=1e-4, max_iter=250, tol=1e-6):
        self.patterns = np.asarray(patterns)
        self.variance_floor = variance_floor
        self.max_iter = max_iter
        self.tol = tol

    def _anchor(self, means):
        return np.where(self.patterns, np.maximum(means, .005), np.minimum(means, -.005))

    def _log_components(self, x):
        delta = x[:, None, :] - self.means[None, :, :]
        return (np.log(self.weights)[None, :] - .5 *
                (np.log(2 * np.pi * self.variances)[None, :, :] + delta ** 2 / self.variances).sum(axis=2))

    def fit(self, x, sample_weight=None, seed=0):
        x = np.asarray(x, float)
        if not np.isfinite(x).all() or x.ndim != 2:
            raise ValueError("Model input must be a finite 2D matrix")
        w = np.ones(len(x)) if sample_weight is None else np.asarray(sample_weight, float)
        if not len(x) or np.any(w <= 0):
            raise ValueError("Nonempty data and positive training weights are required")
        self.training_rows = len(x)
        k, d = self.patterns.shape
        initial = ((x[:, None, :] > 0) == self.patterns).all(axis=2)
        count = (initial * w[:, None]).sum(axis=0)
        self.means = np.empty((k, d))
        self.variances = np.empty((k, d))
        for j in range(k):
            selected = initial[:, j]
            if count[j] > 0:
                self.means[j] = np.average(x[selected], axis=0, weights=w[selected])
                self.variances[j] = np.average((x[selected] - self.means[j]) ** 2, axis=0, weights=w[selected])
            else:
                self.means[j] = np.where(self.patterns[j], .2, -.2)
                self.variances[j] = np.var(x, axis=0)
        self.means = self._anchor(self.means + np.random.default_rng(seed).normal(0, .015, (k, d)))
        self.variances = np.maximum(self.variances, self.variance_floor)
        self.weights = np.maximum(count, .01) / np.maximum(count, .01).sum()
        previous = -np.inf
        self.converged = False
        for iteration in range(self.max_iter):
            logp = self._log_components(x)
            normalizer = logsumexp(logp, axis=1)
            resp = np.exp(logp - normalizer[:, None])
            rw = resp * w[:, None]
            mass = np.maximum(rw.sum(axis=0), 1e-12)
            self.means = self._anchor((rw.T @ x) / mass[:, None])
            self.variances = np.maximum(
                ((rw[:, :, None] * (x[:, None, :] - self.means[None, :, :]) ** 2).sum(axis=0)
                 / mass[:, None]), self.variance_floor)
            self.weights = np.maximum(mass / mass.sum(), 1e-9)
            self.weights /= self.weights.sum()
            score = float(np.average(normalizer, weights=w))
            if abs(score - previous) < self.tol:
                self.converged = True
                break
            previous = score
        self.iterations = iteration + 1
        self.training_log_density = float(np.average(self.score_samples(x), weights=w))
        return self

    def predict_proba(self, x):
        logp = self._log_components(np.asarray(x, float))
        return np.exp(logp - logsumexp(logp, axis=1)[:, None])

    def score_samples(self, x):
        return logsumexp(self._log_components(np.asarray(x, float)), axis=1)

    def as_dict(self):
        return {"type": "gate_anchored_diagonal_gaussian_mixture", "patterns": self.patterns.tolist(),
                "means": self.means.tolist(), "variances": self.variances.tolist(),
                "weights": self.weights.tolist(), "converged": self.converged,
                "effective_weighted_state_mass": (self.weights*self.training_rows).tolist(),
                "iterations": self.iterations, "training_rows": self.training_rows,
                "training_log_density": self.training_log_density,
                "means_at_constraint": (np.abs(self.means) <= .005001).tolist(),
                "interpretation": "Reporter-state density model conditional on supplied gates; no biological calibration"}


class IndependentChannels:
    """Two ordered channel mixtures; a simpler density-model comparator."""
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def fit(self, x, sample_weight=None, seed=0):
        self.models = [AnchoredMixture(np.array([[0], [1]]), **self.kwargs).fit(
            x[:, j:j+1], sample_weight, seed + j) for j in range(2)]
        self.converged = all(m.converged for m in self.models)
        return self

    def predict_proba(self, x):
        g, r = [model.predict_proba(x[:, j:j+1]) for j, model in enumerate(self.models)]
        return np.column_stack([g[:, 0]*r[:, 0], g[:, 1]*r[:, 0], g[:, 0]*r[:, 1], g[:, 1]*r[:, 1]])

    def score_samples(self, x):
        return sum(m.score_samples(x[:, j:j+1]) for j, m in enumerate(self.models))

    def as_dict(self):
        return {"type": "independent_gate_anchored_channel_mixtures", "channels": [m.as_dict() for m in self.models]}


def make_model(name, config):
    kwargs = dict(variance_floor=config["variance_floor"], max_iter=config["maximum_iterations"],
                  tol=config["convergence_tolerance"])
    return AnchoredMixture(**kwargs) if name == "joint" else IndependentChannels(**kwargs)


def model_from_dict(payload):
    """Restore a saved numeric model without executing serialized code."""
    if payload["type"] == "independent_gate_anchored_channel_mixtures":
        model = IndependentChannels()
        model.models = [model_from_dict(p) for p in payload["channels"]]
        model.converged = all(m.converged for m in model.models)
        return model
    model = AnchoredMixture(patterns=np.array(payload["patterns"]))
    for attr in ["means", "variances", "weights"]:
        setattr(model, attr, np.array(payload[attr], dtype=float))
    for attr in ["converged", "iterations", "training_rows", "training_log_density"]:
        setattr(model, attr, payload[attr])
    return model
