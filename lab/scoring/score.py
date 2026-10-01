"""Track A scoring of a set of transcripts: accuracy, calibration, cost, side by side."""

from __future__ import annotations

from lab.scoring import accuracy, calibration, cost
from lab.scoring.bootstrap import paired_diff, verdict


def label_set(transcripts: list[dict]) -> list[str]:
    seen: list[str] = []
    for t in transcripts:
        for lab in t["label_set"]:
            if lab not in seen:
                seen.append(lab)
    return seen


def score(transcripts: list[dict], ece_bins: int = 10) -> dict:
    ts = [t for t in transcripts if t.get("gold")]
    if not ts:
        return {"n": 0}
    labels = label_set(ts)
    gold = [t["gold"] for t in ts]
    pred = [t["verdict"] for t in ts]
    conf = [t["confidence"] for t in ts]
    out = accuracy.report(gold, pred, labels)
    out["brier"] = calibration.brier(gold, pred, conf, labels)
    out["ece"] = calibration.ece(gold, pred, conf, ece_bins)
    out["cost"] = cost.summarize(ts)
    out["rounds"] = max((x.get("round", 0) for t in ts for x in t["turns"]), default=0)
    return out


def align(a: list[dict], b: list[dict]) -> tuple[list[str], list[str], list[str], list[str]]:
    """Gold, A preds, B preds on the items both protocols ran, plus the label set."""
    bm = {t["item"]: t for t in b}
    common = [t for t in a if t["item"] in bm and t.get("gold")]
    gold = [t["gold"] for t in common]
    return gold, [t["verdict"] for t in common], [bm[t["item"]]["verdict"] for t in common], \
        label_set(common)


def compare(a: list[dict], b: list[dict], resamples: int = 10_000, seed: int = 20261001) -> dict:
    gold, pa, pb, labels = align(a, b)
    if not gold:
        return {"n": 0, "verdict": "no overlap"}
    r = paired_diff(gold, pa, pb, labels, resamples=resamples, seed=seed)
    r["n"] = len(gold)
    r["verdict"] = verdict(r["ci"])
    r["disagreement"] = sum(x != y for x, y in zip(pa, pb, strict=True)) / len(gold)
    return r
