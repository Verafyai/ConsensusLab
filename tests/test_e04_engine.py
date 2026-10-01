from pathlib import Path

import pytest
import yaml

from lab import paths
from lab.clients.meter import BudgetExceeded, Scope
from lab.config import load_config
from lab.protocols.estimate import estimate
from lab.protocols.runner import load_dev_transcripts, run_protocol
from lab.protocols.schema import (
    InvalidProtocol,
    load_protocol,
    validate_protocol,
    validate_transcript,
)
from tests.helpers import dev_items, rig

LIB = paths.ROOT / "lab" / "protocols" / "library"
BASELINES = sorted(LIB.glob("*.yaml"))


def known(cfg_dir):
    return set(load_config(cfg_dir).models["models"])


@pytest.mark.parametrize("path", BASELINES, ids=lambda p: p.stem)
def test_baseline_runs_end_to_end_on_10_items_within_budget(path, filled_config, tmp_path):
    proto = load_protocol(path, known(filled_config))
    engine, gw = rig(filled_config, tmp_path)
    items = dev_items(10)
    scope = Scope(experiment="E-test", caps={"experiment": 20.0})
    ts = run_protocol(engine, proto, items, scope, "E-test", workers=3,
                      runs_root=tmp_path / "runs")
    assert len(ts) == 10
    cap = engine.item_cap(proto)
    for t in ts:
        validate_transcript(t)
        assert t["verdict"] in t["label_set"] + ["abstain"]
        assert t["usd"] <= cap + 1e-9
        assert t["error"] is None
        assert all(len(e["excerpt"].split()) <= 40 for e in t["evidence"])
        assert "passage" not in str(t["evidence"])  # long passages never leave the run
    assert len(load_dev_transcripts("E-test", tmp_path / "runs")) == 10


def test_rerun_is_free(filled_config, tmp_path):
    proto = load_protocol(LIB / "debate-judge.yaml", known(filled_config))
    engine, gw = rig(filled_config, tmp_path)
    items = dev_items(3)
    a = run_protocol(engine, proto, items, Scope(), "E-a", write=False)
    b = run_protocol(engine, proto, items, Scope(), "E-b", write=False)
    assert sum(t["usd"] for t in a) > 0
    assert sum(t["usd"] for t in b) == 0
    assert [t["verdict"] for t in a] == [t["verdict"] for t in b]


def test_debate_transcript_shape(filled_config, tmp_path):
    proto = load_protocol(LIB / "debate-judge.yaml", known(filled_config))
    engine, _ = rig(filled_config, tmp_path)
    t = engine.run_item(proto, dev_items(1)[0], Scope(), "E-x")
    agents = [x["agent"] for x in t["turns"]]
    assert agents == ["advocate-affirm", "advocate-deny"] * 2 + ["judge"]
    assert len(t["agreement"]) == 2
    assert t["reasons"] and len(t["rationale"].split()) <= 60
    assert any(t["evidence"][0]["stance"].values())


def _asym(**kw):
    p = {"id": "asym-test", "description": "x", "pattern": "debate",
         "evidence": {"retrieve": True, "max_sources": 4, "judge_sees": "quotes"},
         "agents": [{"role": "advocate", "side": "affirm", "model": "claude-sonnet"},
                    {"role": "advocate", "side": "deny", "model": "grok-fast"},
                    {"role": "judge", "model": "claude-haiku"}],
         "rounds": 1, "aggregation": "judge"}
    p.update(kw)
    return validate_protocol(p)


def test_quotes_verified_and_judge_blind(filled_config, tmp_path):
    engine, gw = rig(filled_config, tmp_path)
    t = engine.run_item(_asym(), dev_items(1)[0], Scope(), "E-x")
    qs = [q for x in t["turns"] for q in x.get("quotes", [])]
    assert qs and all(q["verified"] for q in qs)
    judge_prompt = gw.providers["anthropic"].calls[-1].messages[0]["content"]
    assert "Evidence:" not in judge_prompt and "VERIFIED quote" in judge_prompt


def test_best_of_n_records_one_turn_per_speaker(filled_config, tmp_path):
    engine, _ = rig(filled_config, tmp_path)
    t = engine.run_item(_asym(best_of_n=3), dev_items(1)[0], Scope(), "E-x")
    adv = [x for x in t["turns"] if x["agent"].startswith("advocate")]
    assert len(adv) == 2 and all(x.get("best_of") == 3 for x in adv)


def test_item_cap_abstains_without_halting(filled_config, tmp_path):
    engine, _ = rig(filled_config, tmp_path)
    proto = load_protocol(LIB / "self-consistency.yaml")
    proto = dict(proto, budget={"max_usd_per_item": 0.0001})
    t = engine.run_item(proto, dev_items(1)[0], Scope(), "E-x")
    assert t["verdict"] == "abstain" and "item budget" in t["error"]


def test_experiment_cap_halts_batch(filled_config, tmp_path):
    engine, _ = rig(filled_config, tmp_path)
    proto = load_protocol(LIB / "debate-judge.yaml")
    with pytest.raises(BudgetExceeded):
        run_protocol(engine, proto, dev_items(10), Scope(caps={"experiment": 0.01}), "E-x",
                     write=False)


def test_society_and_chateval_patterns(filled_config, tmp_path):
    engine, _ = rig(filled_config, tmp_path)
    soc = validate_protocol({
        "id": "soc", "description": "x", "pattern": "society", "rounds": 2,
        "evidence": {"retrieve": True}, "agreement_intensity": 0.2,
        "agents": [{"role": "answerer", "model": "claude-haiku"},
                   {"role": "answerer", "model": "grok-fast"},
                   {"role": "answerer", "model": "claude-sonnet"}], "aggregation": "majority"})
    t = engine.run_item(soc, dev_items(1)[0], Scope(), "E-x")
    assert len(t["agreement"]) >= 1 and len(t["turns"]) in (3, 6, 9)
    for mode in ("one_by_one", "simultaneous", "simultaneous_summarizer"):
        ce = validate_protocol({
            "id": f"ce-{mode.replace('_', '-')}", "description": "x", "pattern": "chateval",
            "rounds": 2, "communication": mode, "evidence": {"retrieve": True},
            "agents": [{"role": "judge", "model": "claude-haiku", "persona": "a statistician"},
                       {"role": "judge", "model": "claude-haiku", "persona": "a journalist"}],
            "aggregation": "majority"})
        t = engine.run_item(ce, dev_items(1)[0], Scope(), "E-x")
        assert t["verdict"] != "abstain"


def test_consultancy_assigns_side(filled_config, tmp_path):
    engine, _ = rig(filled_config, tmp_path)
    p = validate_protocol({
        "id": "cons", "description": "x", "pattern": "consultancy", "rounds": 2,
        "evidence": {"retrieve": True, "judge_sees": "quotes"},
        "agents": [{"role": "consultant", "model": "claude-sonnet"},
                   {"role": "judge", "model": "claude-haiku"}], "aggregation": "judge"})
    t = engine.run_item(p, dev_items(1)[0], Scope(), "E-x")
    assert [x["agent"] for x in t["turns"]] == ["consultant", "consultant", "judge"]
    assert t["turns"][0]["position"] in ("affirm", "deny")


@pytest.mark.parametrize("bad,msg", [
    ({"pattern": "debate"}, "don't fit"),
    ({"aggregation": "judge"}, "judge agent"),
    ({"agents": [{"role": "answerer", "model": "nope"}]}, "unknown model"),
    ({"rounds": 99}, "rounds"),
])
def test_invalid_protocols(bad, msg, filled_config):
    p = yaml.safe_load((LIB / "single-claude-sonnet.yaml").read_text())
    p.update(bad)
    with pytest.raises(InvalidProtocol, match=msg):
        validate_protocol(p, known(filled_config))


def test_estimates_scale_with_rounds(filled_config):
    cfg = load_config(filled_config)
    d1 = load_protocol(LIB / "debate-judge.yaml")
    d3 = dict(d1, rounds=3)
    s = load_protocol(LIB / "single-claude-sonnet.yaml")
    e1, e3, es = estimate(d1, cfg, False), estimate(d3, cfg, False), estimate(s, cfg, False)
    assert es.calls == 1 and e1.calls == 5 and e3.calls == 7
    assert es.expected_usd < e1.expected_usd < e3.expected_usd
    assert e1.worst_usd > e1.expected_usd


def test_library_ids_match_filenames():
    for p in BASELINES:
        assert yaml.safe_load(Path(p).read_text())["id"] == p.stem
