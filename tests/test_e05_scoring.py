import json

import pytest

from lab.scoring import accuracy, calibration, cost, leaderboard
from lab.scoring.bootstrap import paired_diff, verdict
from lab.scoring.score import compare, score

L4 = ["s", "r", "n", "c"]
GOLD = ["s", "s", "r", "r", "n", "c"]
PRED = ["s", "r", "r", "r", "s", "abstain"]


def test_per_label_hand_computed():
    pl = accuracy.per_label(GOLD, PRED, L4)
    assert pl["s"]["precision"] == 0.5 and pl["s"]["recall"] == 0.5 and pl["s"]["f1"] == 0.5
    assert pl["r"]["precision"] == pytest.approx(2 / 3) and pl["r"]["recall"] == 1.0
    assert pl["r"]["f1"] == pytest.approx(0.8)
    assert pl["n"]["f1"] == 0 and pl["c"]["f1"] == 0


def test_macro_f1_and_accuracy_hand_computed():
    assert accuracy.macro_f1(GOLD, PRED, L4) == pytest.approx(0.325)
    assert accuracy.accuracy(GOLD, PRED) == 0.5
    rep = accuracy.report(GOLD, PRED, L4)
    assert rep["abstain_rate"] == pytest.approx(1 / 6)


def test_macro_f1_skips_labels_without_support():
    assert accuracy.macro_f1(["s", "r"], ["s", "r"], L4) == 1.0


def test_brier_hand_computed():
    b = calibration.brier(["s", "r"], ["s", "s"], [0.7, 0.6], ["s", "r"])
    assert b == pytest.approx((0.18 + 0.72) / 2)


def test_brier_abstain_uniform():
    assert calibration.brier(["s"], ["abstain"], [0.0], ["s", "r"]) == pytest.approx(0.5)


def test_ece_hand_computed():
    e = calibration.ece(["a"] * 4, ["a", "b", "a", "a"], [0.95, 0.95, 0.55, 0.55], bins=10)
    assert e == pytest.approx(0.45)
    assert calibration.ece(["a", "a"], ["a", "a"], [1.0, 1.0]) == pytest.approx(0.0)


def test_cost_summary():
    ts = [{"usd": 0.02, "usd_uncached": 0.03, "latency_s": 2.0,
           "turns": [{"tokens": 100}, {"tokens": 50}]},
          {"usd": 0.0, "usd_uncached": 0.01, "latency_s": 4.0, "turns": [{"tokens": 10}]}]
    c = cost.summarize(ts)
    assert c["usd_per_item"] == pytest.approx(0.01)
    assert c["usd_per_item_uncached"] == pytest.approx(0.02)
    assert c["tokens_per_item"] == 80 and c["median_latency_s"] == 3.0
    assert cost.efficiency(0.02, 0.01) == pytest.approx(2.0)


def _preds(n=300, acc_a=0.85, acc_b=0.6, seed=1):
    import random
    rnd = random.Random(seed)
    gold = [rnd.choice(L4) for _ in range(n)]
    a = [g if rnd.random() < acc_a else rnd.choice(L4) for g in gold]
    b = [g if rnd.random() < acc_b else rnd.choice(L4) for g in gold]
    return gold, a, b


def test_bootstrap_deterministic_given_seed():
    gold, a, b = _preds()
    r1 = paired_diff(gold, a, b, L4, resamples=2000, seed=7)
    r2 = paired_diff(gold, a, b, L4, resamples=2000, seed=7)
    r3 = paired_diff(gold, a, b, L4, resamples=2000, seed=8)
    assert r1 == r2 and r1["ci"] != r3["ci"]


def test_bootstrap_detects_real_gap_and_not_noise():
    gold, a, b = _preds()
    assert verdict(paired_diff(gold, a, b, L4, resamples=2000)["ci"]) == "better"
    gold, a, b = _preds(acc_a=0.7, acc_b=0.7, seed=3)
    assert verdict(paired_diff(gold, a, a, L4, resamples=500)["ci"]) == \
        "no detectable difference"


def test_vectorized_matches_reference_metric():
    gold, a, b = _preds(n=80)
    fast = paired_diff(gold, a, b, L4, resamples=300, seed=5)
    slow = paired_diff(gold, a, b, L4, resamples=300, seed=5,
                       metric=lambda g, p, labs: accuracy.macro_f1(g, p, labs))
    assert fast["ci"] == pytest.approx(slow["ci"])


def _t(item, gold, verdict_, conf=0.7):
    return {"item": item, "gold": gold, "verdict": verdict_, "confidence": conf,
            "label_set": L4, "usd": 0.01, "latency_s": 1.0, "turns": [{"tokens": 5}]}


def test_score_and_compare_transcripts():
    a = [_t(f"q{i}", g, g) for i, g in enumerate(GOLD)]
    b = [_t(f"q{i}", g, p) for i, (g, p) in enumerate(zip(GOLD, PRED, strict=True))]
    s = score(b)
    assert s["macro_f1"] == pytest.approx(0.325) and "ece" in s and s["cost"]["n"] == 6
    c = compare(a, b, resamples=500)
    assert c["n"] == 6 and c["diff"] == pytest.approx(1 - 0.325)


def test_leaderboard_and_pareto(tmp_path):
    def res(e, pid, f1, usd, status="not_promoted"):
        d = tmp_path / e
        d.mkdir()
        (d / "results.json").write_text(json.dumps({
            "experiment": e, "protocol": pid, "status": status,
            "dev": {"n": 100, "macro_f1": f1, "cost": {"usd_per_item_uncached": usd}}}))
    res("E-0001", "single", 0.60, 0.01)
    res("E-0002", "debate", 0.70, 0.05, "promoted")
    res("E-0003", "wasteful", 0.65, 0.09)
    lb = leaderboard.write(tmp_path)
    assert lb["champion"] == "debate"
    assert set(lb["pareto"]) == {"single", "debate"}
    assert [r["protocol"] for r in lb["rows"]][0] == "debate"
    assert (tmp_path / "leaderboard.json").exists()
