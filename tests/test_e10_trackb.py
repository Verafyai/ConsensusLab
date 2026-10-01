import json
from pathlib import Path

import pytest

from lab import paths, trackb
from lab.clients.meter import Scope
from lab.config import load_config
from lab.scoring import glance, readability
from lab.scoring.human import wilson_lower
from lab.scoring.poll import poll_score
from lab.scoring.social import engagement_rate, social_index

SAMPLE = json.loads((paths.ROOT / "viz/replay/samples/debate-sample.json").read_text())


def test_fk_grade_known_texts():
    easy = "The cat sat on the mat. It was warm. The sun was out."
    hard = ("Notwithstanding methodological considerations, epidemiological investigations "
            "substantiate comprehensive hypotheses regarding cardiovascular pathophysiology.")
    assert readability.fk_grade(easy) < 3
    assert readability.fk_grade(hard) > 15
    assert readability.syllables("population") == 4


def test_code_scores_and_composite():
    c = readability.code_scores(SAMPLE["rationale"])
    assert c["words"] <= 60 and c["grade_ok"] > 0.5 and c["jargon"] == []
    bad = readability.code_scores("Notwithstanding the epistemic provenance, the aforementioned "
                                  "evidentiary corroboration is dispositive. " * 8)
    assert bad["jargon_ok"] == 0 and bad["length_ok"] < 1
    assert readability.composite(c, 5) > readability.composite(bad, 1)


def test_rubric_via_gateway(filled_config, tmp_path):
    from tests.helpers import rig
    _, gw = rig(filled_config, tmp_path, lambda req, m: {"clarity": 4, "why": "plain"})
    r = readability.score(SAMPLE, gw, Scope())
    assert r["clarity"] == 4 and 0 < r["readability"] <= 1


@pytest.mark.parametrize("read,expect", [
    ({"verdict": "refuted", "confidence": 0.93, "main_reason": "Ghana census counted 30.8 million"},
     1.0),
    ({"verdict": "refuted", "confidence": 93, "main_reason": "Lagos is smaller"}, 2 / 3),
    ({"verdict": "supported", "confidence": 0.5, "main_reason": "unclear"}, 0.0),
])
def test_glance_grading(read, expect):
    assert glance.grade(read, SAMPLE)["glance"] == pytest.approx(expect)


def test_wilson_poll_social():
    assert wilson_lower(40, 50) > wilson_lower(2, 2)
    assert wilson_lower(0, 0) == 0
    p = poll_score({"Yes, and convincing": 10, "Wrong verdict": 15, "Can't tell": 5})
    assert p["counted"] and p["review"] and p["n"] == 30
    assert not poll_score({"Yes, and convincing": 3})["counted"]
    m = {"impressions": 1000, "likes": 20, "reposts": 5, "replies": 3, "quotes": 1,
         "bookmarks": 1}
    assert engagement_rate(m) == pytest.approx(0.03)
    from datetime import datetime, timedelta
    now = datetime(2026, 10, 1)
    hist = [(now - timedelta(days=d), 0.02) for d in range(1, 10)]
    assert social_index(0.03, hist, now) == pytest.approx(1.5)


@pytest.fixture
def tb_root(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    monkeypatch.setattr(paths, "EXPERIMENTS", tmp_path / "experiments")
    return tmp_path


def test_scores_per_case_and_variant_and_agreement(filled_config, tmp_path, tb_root):
    from lab.protocols.runner import write_transcript
    from tests.helpers import rig
    t = dict(SAMPLE, experiment="E-0001")
    for i in range(4):
        write_transcript(dict(t, item=f"q-s-{i}", verdict=["refuted", "supported"][i % 2]),
                         "dev", tb_root / "runs")
    paths.RUNS = tb_root / "runs"
    _, gw = rig(filled_config, tmp_path, lambda req, m: {"clarity": 3, "why": "ok"})

    def fake_glance(gw_, tr, scope, png, variant, tol):
        return {"glance": 1.0 if tr["verdict"] == "refuted" else 0.0, "verdict": True,
                "confidence": True, "main_reason": tr["verdict"] == "refuted"}
    for v in ("base", "bold"):
        rows = trackb.score_experiment(gw, "E-0001", v, n=4, glance_fn=fake_glance)
        assert len(rows) == 4 and all(r["variant"] == v for r in rows)
    lines = (tb_root / "experiments/trackb/scores.jsonl").read_text().splitlines()
    assert len(lines) == 8
    with (tb_root / "ratings.jsonl").open("w") as f:
        for i in range(4):
            for _ in range(3):
                f.write(json.dumps({"experiment": "E-0001", "item": f"q-s-{i}",
                                    "thumb": "up" if i % 2 == 0 else "down"}) + "\n")
    rep = trackb.agreement_report()
    assert rep["n_cases"] >= 4 and rep["measures"]["glance"]["pearson_r"] == pytest.approx(1.0)


def test_variant_selection_rule(filled_config, tb_root):
    cfg = load_config(filled_config)
    d = tb_root / "experiments" / "trackb"
    d.mkdir(parents=True)
    rows = [{"experiment": "E-1", "item": f"i{k}", "variant": v, "glance": g,
             "readability": r} for k in range(5)
            for v, g, r in (("base", 0.6, 0.8), ("bold", 0.9, 0.85), ("tiny", 0.95, 0.3))]
    (d / "scores.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows))
    out = trackb.select("bold", cfg)
    assert not out["adopted"] and any("human ratings" in r for r in out["reasons"])
    with (tb_root / "ratings.jsonl").open("w") as f:
        for v, ups in (("base", 6), ("bold", 11), ("tiny", 12)):
            for k in range(12):
                f.write(json.dumps({"experiment": "E-1", "item": f"i{k % 5}", "variant": v,
                                    "thumb": "up" if k < ups else "down"}) + "\n")
    assert not trackb.select("tiny", cfg)["adopted"]     # below the readability floor
    out = trackb.select("bold", cfg)
    assert out["adopted"] and trackb.default_variant() == "bold"


def test_render_card_and_glance_live(tmp_path):
    pytest.importorskip("playwright")
    if not (paths.ROOT / "viz/replay/index.html").exists():
        pytest.skip("replay app not built")
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as pw:
            pw.chromium.launch().close()
    except Exception as e:  # noqa: BLE001 - only a missing browser is a skip
        pytest.skip(f"browser unavailable: {e}")
    png = glance.render_card(SAMPLE, tmp_path / "card.png")
    assert png.exists() and png.stat().st_size > 10_000
    assert Path(png).read_bytes()[:4] == b"\x89PNG"
