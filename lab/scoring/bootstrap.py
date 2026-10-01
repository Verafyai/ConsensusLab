"""Paired bootstrap for the promotion rule (spec §6.2). Deterministic given a seed."""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np

from lab.scoring.accuracy import macro_f1


def paired_diff(gold: Sequence[str], pred_a: Sequence[str], pred_b: Sequence[str],
                labels: Sequence[str], resamples: int = 10_000, seed: int = 20261001,
                ci: float = 0.95,
                metric: Callable[[Sequence[str], Sequence[str], Sequence[str]], float] = macro_f1,
                ) -> dict:
    """Bootstrap the difference metric(A) - metric(B) over items resampled with replacement.

    Both protocols are scored on the same resampled items (paired). Returns the observed
    difference, the percentile CI, and P(diff <= 0).
    """
    n = len(gold)
    assert n == len(pred_a) == len(pred_b) and n > 0
    g = np.asarray(gold, dtype=object)
    a = np.asarray(pred_a, dtype=object)
    b = np.asarray(pred_b, dtype=object)
    rng = np.random.default_rng(seed)
    observed = metric(gold, pred_a, labels) - metric(gold, pred_b, labels)
    diffs = np.empty(resamples)
    lab_idx = {lab: i for i, lab in enumerate(labels)}
    # Vectorized macro-F1 via confusion counts when the metric is macro_f1.
    if metric is macro_f1:
        gi = np.array([lab_idx.get(x, -1) for x in g])
        ai = np.array([lab_idx.get(x, -1) for x in a])
        bi = np.array([lab_idx.get(x, -1) for x in b])
        for r in range(resamples):
            idx = rng.integers(0, n, n)
            diffs[r] = _mf1(gi[idx], ai[idx], len(labels)) - _mf1(gi[idx], bi[idx], len(labels))
    else:
        for r in range(resamples):
            idx = rng.integers(0, n, n)
            diffs[r] = metric(g[idx].tolist(), a[idx].tolist(), labels) - \
                metric(g[idx].tolist(), b[idx].tolist(), labels)
    lo, hi = np.percentile(diffs, [(1 - ci) / 2 * 100, (1 + ci) / 2 * 100])
    return {"diff": float(observed), "ci": [float(lo), float(hi)],
            "p_le_zero": float((diffs <= 0).mean()), "resamples": resamples, "seed": seed}


def _mf1(g: np.ndarray, p: np.ndarray, k: int) -> float:
    f1s = []
    for lab in range(k):
        support = np.sum(g == lab)
        if support == 0:
            continue
        tp = np.sum((g == lab) & (p == lab))
        fp = np.sum((g != lab) & (p == lab))
        fn = support - tp
        denom = 2 * tp + fp + fn
        f1s.append(2 * tp / denom if denom else 0.0)
    return float(np.mean(f1s)) if f1s else 0.0


def verdict(ci: Sequence[float]) -> str:
    """Spec §6.2: within noise is 'no detectable difference', never better/worse."""
    lo, hi = ci
    if lo > 0:
        return "better"
    if hi < 0:
        return "worse"
    return "no detectable difference"
