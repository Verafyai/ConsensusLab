import json
import random
import subprocess

import pytest
import yaml

from lab import paths
from lab.clients.fakemodel import SchemaResponder
from lab.orchestrator import learnings
from lab.orchestrator.loop import Data, Orchestrator
from tests.helpers import rig

LABELS = ["supported", "refuted", "not_enough_evidence", "conflicting"]


def items(n, split, seed, start=0):
    rnd = random.Random(seed)
    out = []
    for i in range(start, start + n):
        g = rnd.choice(LABELS)
        out.append({"id": f"q-syn-{i:010x}", "kind": "claim", "text": f"Synthetic claim {i}",
                    "label_set": LABELS, "gold": g, "expert_source": "test", "split": split,
                    "date": "2026-08-01" if i % 3 == 0 else "2024-01-01", "flags": []})
    return out


DEV = items(120, "dev", 1)
HOLD = items(250, "holdout", 2, start=10_000)
GOLD = {it["text"]: it["gold"] for it in DEV + HOLD}


def proto(pid, model, samples=None):
    a = {"role": "answerer", "model": model}
    if samples:
        a["samples"] = samples
    return {"id": pid, "description": "t", "pattern": "sample_vote" if samples else "single",
            "evidence": {"retrieve": True, "max_sources": 2}, "agents": [a],
            "aggregation": "majority", "tags": ["z1"]}


class StubExperimenter:
    """Writes queued proposals; optionally vandalizes locked paths."""

    def __init__(self, queue, vandal=False):
        self.queue = list(queue)
        self.vandal = vandal
        self.contexts = []

    def propose(self, exp_id, exp_dir, context):
        self.contexts.append(context)
        p, run = self.queue.pop(0)
        cite = "STEERING.md" if not context["learnings_top"] else \
            context["learnings_top"][-1]["id"]
        (exp_dir / "proposal.md").write_text(
            f"# {exp_id}\n\nHypothesis: {p['id']} beats the champion\nBuilds on: {cite}\n"
            f"Track: A\nZone: Z1\nExpected effect: +0.05\n")
        (exp_dir / "protocol.yaml").write_text(yaml.safe_dump(p))
        if run:
            (exp_dir / "run.yaml").write_text(yaml.safe_dump(run))
        if self.vandal:
            root = exp_dir.parent.parent
            (root / "CHARTER.md").write_text("rules are gone\n")
            (root / "lab" / "scoring").mkdir(parents=True, exist_ok=True)
            (root / "lab" / "scoring" / "evil.py").write_text("x = 1\n")


@pytest.fixture
def lab_root(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "experiments").mkdir(parents=True)
    (root / "learnings").mkdir()
    (root / "ops" / "queue").mkdir(parents=True)
    (root / "CHARTER.md").write_text("entrenched\n")
    (root / "STEERING.md").write_text("focus on baselines\n")
    (root / "learnings" / "learnings.jsonl").write_text("")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A"],
                   cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
                   cwd=root, check=True)
    for name, rel in [("ROOT", ""), ("EXPERIMENTS", "experiments"), ("LEARNINGS", "learnings"),
                      ("OPS", "ops"), ("QUEUE", "ops/queue"), ("STOP", "ops/STOP"),
                      ("EVENTS", "ops/events.jsonl"), ("HEARTBEAT", "ops/heartbeat.json"),
                      ("RUNS", "runs")]:
        monkeypatch.setattr(paths, name, root / rel if rel else root)
    monkeypatch.setenv("CL_HOLDOUT_DIR", str(tmp_path / "hold"))
    return root


def make(filled_config, tmp_path, root, queue, vandal=False):
    responder = SchemaResponder(accuracy={"claude-haiku-4-5": 0.35, "claude-sonnet-5-5": 0.9,
                                          "grok-4.7": 0.9}, gold=GOLD)
    engine, gw = rig(filled_config, tmp_path, responder)
    exp = StubExperimenter(queue, vandal)
    orch = Orchestrator(gw.cfg, engine, exp, Data(DEV, lambda: HOLD, post_cutoff="2026-06-30"),
                        root=root, workers=8, resamples=2000)
    orch.cfg.scoring["promotion"]["holdout_gate_margin"] = 0.1
    return orch, exp


def test_better_promoted_noise_not_overbudget_refused(filled_config, tmp_path, lab_root):
    queue = [(proto("weak-haiku", "claude-haiku"), None),
             (proto("strong-sonnet", "claude-sonnet"), None),
             (proto("strong-grok", "grok"), None),
             (proto("huge-vote", "claude-sonnet", samples=15), None)]
    orch, exp = make(filled_config, tmp_path, lab_root, queue)
    orch.cfg.budget["max_usd_per_experiment"] = 6.0
    r1 = orch.cycle()
    assert r1["status"] == "promoted" and r1["vs_champion"] is None   # initial champion
    r2 = orch.cycle()
    assert r2["status"] == "promoted", r2.get("reason")
    assert r2["vs_champion"]["verdict"] == "better" and r2["vs_champion"]["ci"][0] > 0
    assert r2["holdout"]["post_cutoff"]["n"] > 0
    r3 = orch.cycle()
    assert r3["status"] == "not_promoted"
    assert r3["vs_champion"]["verdict"] == "no detectable difference"
    r4 = orch.cycle()
    assert r4["status"] == "rejected_budget" and "shrink" in r4["reason"]
    assert "dev" not in r4                       # nothing was run

    # Every experiment has a proposal, a result, a summary and a learning.
    rows = learnings.load()
    assert len(rows) == 4
    for i in range(1, 5):
        d = lab_root / "experiments" / f"E-{i:04d}"
        assert (d / "proposal.md").exists() and (d / "results.json").exists()
        assert (d / "summary.md").exists()
    assert rows[1]["status"] == "confirmed" and rows[2]["status"] == "tentative"
    lb = json.loads((lab_root / "experiments" / "leaderboard.json").read_text())
    assert lb["champion"] == "strong-sonnet"
    assert "Confirmed" in (lab_root / "LEARNINGS.md").read_text()
    # Holdout transcripts never land in the repo.
    assert not list((lab_root / "runs").glob("*/q-syn-00000027*"))
    # The experimenter only ever saw aggregate leaderboard data, never holdout items.
    assert "Synthetic claim 10000" not in json.dumps(exp.contexts)


def test_stopped_at_dev_and_holdout_budget(filled_config, tmp_path, lab_root):
    queue = [(proto("strong-sonnet", "claude-sonnet"), None),
             (proto("weak-haiku", "claude-haiku"), None),
             (proto("strong-grok", "grok"), None)]
    orch, _ = make(filled_config, tmp_path, lab_root, queue)
    orch.cfg.budget["holdout_evals_per_week"] = 1
    assert orch.cycle()["status"] == "promoted"
    r = orch.cycle()
    assert r["status"] == "stopped_at_dev" and "dev macro-F1" in r["reason"]
    r = orch.cycle()
    assert r["status"] == "stopped_at_dev" and "holdout evaluation budget" in r["reason"]


def test_locked_paths_reverted(filled_config, tmp_path, lab_root):
    orch, _ = make(filled_config, tmp_path, lab_root,
                   [(proto("weak-haiku", "claude-haiku"), {"n": 20})], vandal=True)
    orch.cfg.budget["holdout_evals_per_week"] = 0
    r = orch.cycle()
    assert (lab_root / "CHARTER.md").read_text() == "entrenched\n"
    assert not (lab_root / "lab" / "scoring" / "evil.py").exists()
    reverted = (lab_root / "experiments" / "E-0001" / "reverted.txt").read_text()
    assert "CHARTER.md" in reverted and "lab/scoring/evil.py" in reverted
    assert r["dev"]["n"] == 20


def test_invalid_proposal_still_gets_learning(filled_config, tmp_path, lab_root):
    class Bad:
        def propose(self, exp_id, exp_dir, context):
            (exp_dir / "proposal.md").write_text("no hypothesis here\n")
    orch, _ = make(filled_config, tmp_path, lab_root, [])
    orch.experimenter = Bad()
    r = orch.cycle()
    assert r["status"] == "invalid" and "Hypothesis" in r["reason"]
    assert learnings.load()[-1]["outcome"] == "invalid"


def test_stop_file_halts(filled_config, tmp_path, lab_root):
    orch, _ = make(filled_config, tmp_path, lab_root, [(proto("a", "claude-haiku"), None)])
    (lab_root / "ops" / "STOP").write_text("")
    assert orch.cycle()["status"] == "stopped"
    assert not list((lab_root / "experiments").glob("E-*"))


def test_heartbeat_written(filled_config, tmp_path, lab_root):
    from harness import health
    orch, _ = make(filled_config, tmp_path, lab_root, [(proto("a", "claude-haiku"), {"n": 5})])
    orch.cfg.budget["holdout_evals_per_week"] = 0
    orch.cycle()
    st = health.status(lab_root / "ops" / "heartbeat.json")
    assert st["orchestrator"]["ok"] and st["orchestrator"]["state"] == "idle"
    assert not health.status(lab_root / "ops" / "heartbeat.json",
                             now=__import__("time").time() + 1000)["orchestrator"]["ok"]


def test_proposal_parser():
    p = Orchestrator.parse_proposal(
        "## Hypothesis\nTwo rounds beat one.\n\n**Builds on:** L-0003, L-0007\n**Track:** A\n")
    assert p["hypothesis"] == "Two rounds beat one." and p["builds_on"] == ["L-0003", "L-0007"]
