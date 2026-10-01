"""Calibration (spec §6.1.1): Brier score and expected calibration error.

Confidence is the protocol's probability that its verdict is correct. For the multiclass
Brier score the remaining mass (1 - confidence) is spread uniformly over the other labels.
Abstentions are treated as confidence 0 on a wrong answer.
"""

from __future__ import annotations

from collections.abc import Sequence


def brier(gold: Sequence[str], pred: Sequence[str], conf: Sequence[float],
          labels: Sequence[str]) -> float:
    k = len(labels)
    total = 0.0
    for g, p, c in zip(gold, pred, conf, strict=True):
        if p not in labels:
            probs = {lab: 1.0 / k for lab in labels}
        else:
            probs = {lab: c if lab == p else (1 - c) / (k - 1) for lab in labels}
        total += sum((probs[lab] - (1.0 if lab == g else 0.0)) ** 2 for lab in labels)
    return total / len(gold) if gold else 0.0


def ece(gold: Sequence[str], pred: Sequence[str], conf: Sequence[float], bins: int = 10) -> float:
    """Equal-width bins over confidence; weighted mean |accuracy - mean confidence|."""
    if not gold:
        return 0.0
    buckets: list[list[tuple[float, bool]]] = [[] for _ in range(bins)]
    for g, p, c in zip(gold, pred, conf, strict=True):
        c = min(max(float(c), 0.0), 1.0)
        i = min(int(c * bins), bins - 1)
        buckets[i].append((c, g == p))
    n = len(gold)
    return sum(len(b) / n * abs(sum(ok for _, ok in b) / len(b) - sum(c for c, _ in b) / len(b))
               for b in buckets if b)


def reliability_curve(gold, pred, conf, bins: int = 10) -> list[dict]:
    buckets: list[list[tuple[float, bool]]] = [[] for _ in range(bins)]
    for g, p, c in zip(gold, pred, conf, strict=True):
        i = min(int(min(max(c, 0), 1) * bins), bins - 1)
        buckets[i].append((c, g == p))
    return [{"bin": i, "n": len(b), "confidence": sum(c for c, _ in b) / len(b),
             "accuracy": sum(ok for _, ok in b) / len(b)} for i, b in enumerate(buckets) if b]
