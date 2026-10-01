"""Accuracy against the human expert panel (spec §6.1.1). Track A.

Predictions outside the label set (e.g. "abstain") count as wrong for every label: they
add a false negative for the gold label and no false positive anywhere.
"""

from __future__ import annotations

from collections.abc import Sequence


def per_label(gold: Sequence[str], pred: Sequence[str], labels: Sequence[str]) -> dict:
    out = {}
    for lab in labels:
        tp = sum(g == lab and p == lab for g, p in zip(gold, pred, strict=True))
        fp = sum(g != lab and p == lab for g, p in zip(gold, pred, strict=True))
        fn = sum(g == lab and p != lab for g, p in zip(gold, pred, strict=True))
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        out[lab] = {"precision": prec, "recall": rec, "f1": f1, "support": tp + fn}
    return out


def macro_f1(gold: Sequence[str], pred: Sequence[str], labels: Sequence[str]) -> float:
    """Mean F1 over labels that appear in gold (labels with no support are skipped)."""
    pl = per_label(gold, pred, labels)
    present = [lab for lab in labels if pl[lab]["support"] > 0]
    return sum(pl[lab]["f1"] for lab in present) / len(present) if present else 0.0


def accuracy(gold: Sequence[str], pred: Sequence[str]) -> float:
    return sum(g == p for g, p in zip(gold, pred, strict=True)) / len(gold) if gold else 0.0


def report(gold: Sequence[str], pred: Sequence[str], labels: Sequence[str]) -> dict:
    pl = per_label(gold, pred, labels)
    return {"n": len(gold), "macro_f1": macro_f1(gold, pred, labels),
            "accuracy": accuracy(gold, pred),
            "recall": {lab: pl[lab]["recall"] for lab in labels},
            "support": {lab: pl[lab]["support"] for lab in labels},
            "abstain_rate": sum(p not in labels for p in pred) / len(pred) if pred else 0.0}
