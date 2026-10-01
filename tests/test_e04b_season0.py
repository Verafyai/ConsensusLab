import io

import pytest

from lab import season0
from lab.clients.meter import Scope
from lab.config import load_config
from lab.evidence.quotes import verify
from lab.library import cards
from lab.protocols.runner import run_protocol
from lab.protocols.schema import validate_transcript
from tests.helpers import dev_items, rig

PDFS_PRESENT = all((cards.PDFS / f"{p}.pdf").exists() for p in cards.papers())


@pytest.mark.skipif(not PDFS_PRESENT, reason="run library/fetch.sh to verify cards")
def test_every_card_page_reference_resolves():
    checks = cards.check_all()
    assert len(checks) == 8
    for c in checks:
        assert c.ok, (c.card, c.problems, [r for r in c.refs if not r.ok])


@pytest.mark.skipif(not PDFS_PRESENT, reason="run library/fetch.sh")
def test_checker_rejects_a_fake_reference(tmp_path):
    r = cards.check_ref("02-du-2023-multiagent-debate", 3, "debate makes the moon taste of cheese")
    assert not r.ok


def test_fabricated_quote_rejected():
    src = "The census counted thirty one million residents across all regions."
    assert verify("counted thirty one million residents", src)[0]
    assert verify("“counted  thirty one million residents”", src)[0]   # quotes, spacing
    ok, why = verify("counted forty million residents", src)
    assert not ok and why == "not found in source"
    assert not verify("counted thirty one million residents", None)[0]
    assert not verify(" ".join(["word"] * 50), src, max_words=40)[0]


def test_seed_protocols_cover_plan():
    plan = season0.load_plan()
    ids = season0.configs(plan)
    for pid in ids:
        season0.find_protocol(pid)
    papers = {t["paper"] for t in plan["tests"]}
    assert papers == set(cards.papers())


@pytest.mark.parametrize("pid", season0.configs(season0.load_plan()))
def test_every_seed_runs_on_10_dev_items_within_budget(pid, filled_config, tmp_path):
    cfg = load_config(filled_config)
    p = season0.find_protocol(pid, set(cfg.models["models"]))
    engine, _ = rig(filled_config, tmp_path)
    ts = run_protocol(engine, p, dev_items(10), Scope(caps={"x": 20.0}), f"S0-{pid}",
                      workers=4, write=False)
    cap = engine.item_cap(p)
    assert len(ts) == 10
    for t in ts:
        validate_transcript(t)
        assert t["error"] is None and t["usd"] <= cap + 1e-9


def test_plan_estimate_printed_and_capped(filled_config):
    cfg = load_config(filled_config)
    plan = season0.load_plan()
    cfg.budget["season0"].update(max_usd_screening=1e6, max_usd_holdout=1e6)
    p = season0.plan_estimate(cfg, plan, 500)
    buf = io.StringIO()
    season0.print_plan(p, buf)
    assert p["ok"] and "WITHIN CAPS" in buf.getvalue()
    assert len(p["rows"]) == len(season0.configs(plan))
    cfg.budget["season0"]["max_usd_screening"] = 1.0
    p = season0.plan_estimate(cfg, plan, 500)
    assert not p["ok"]


@pytest.mark.parametrize("expect,ci,verdict", [
    ("better", [0.01, 0.05], "replicated"),
    ("better", [-0.04, 0.01], "not replicated"),
    ("better", [-0.04, 0.06], "unclear"),
    ("no_effect", [-0.01, 0.015], "replicated"),
    ("no_effect", [0.01, 0.05], "not replicated"),
    ("no_effect", [-0.05, 0.05], "unclear"),
    ("not_worse", [-0.015, 0.03], "replicated"),
    ("not_worse", [-0.08, -0.01], "not replicated"),
])
def test_scorecard_verdicts(expect, ci, verdict):
    assert season0.judge(expect, ci, 0.02) == verdict


def test_scorecard_from_transcripts(filled_config, tmp_path):
    from lab.clients.fakemodel import SchemaResponder
    items = dev_items(30)
    gold = {it["text"]: it["gold"] for it in items}
    engine, _ = rig(filled_config, tmp_path, SchemaResponder(
        accuracy={"claude-sonnet-5-5": 0.95, "claude-haiku-4-5": 0.3}, gold=gold))
    cfg = engine.gw.cfg
    plan = {"sesoi": 0.02, "tests": [{"paper": "07-x", "claim": "c",
                                      "protocol": "single-claude-sonnet",
                                      "control": "single-claude-haiku", "expect": "better"}]}
    res = season0.run_stage(engine, cfg, plan, items, "screen",
                            ["single-claude-sonnet", "single-claude-haiku"], 50.0,
                            runs_root=tmp_path / "runs")
    rows = season0.scorecard(plan, res, {}, resamples=1000)
    assert rows[0]["verdict"] == "replicated" and rows[0]["tests"][0]["split"] == "dev screen"
    assert "replicated" in season0.scorecard_md(rows)
