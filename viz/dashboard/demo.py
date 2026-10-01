"""Demo data for building and testing the dashboard before real runs exist.

    uv run python -m viz.dashboard.demo /tmp/cl-demo     # builds a fake lab there

Runs a handful of offline experiments with the schema-aware fake model (no network, no
spend) in a scratch lab root, plus a sample Season 0 scorecard and social data, then
writes the dashboard snapshot to <root>/snapshot.json. Never touches the real repo.
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from lab import paths

LABELS = ["supported", "refuted", "not_enough_evidence", "conflicting"]
CLAIMS = [
    "Lagos has more residents than the whole of Ghana.",
    "Drinking hot water kills the coronavirus.",
    "Solar capacity in India doubled between 2018 and 2022.",
    "A new EU law bans cash payments over 1,000 euros.",
    "The Great Wall of China is visible from the Moon with the naked eye.",
    "Wind turbines cause cancer in nearby residents.",
    "Global sea level rose about 20 cm between 1900 and 2018.",
    "Vitamin D supplements prevent all respiratory infections.",
    "Norway gets more than 90% of its electricity from hydropower.",
    "Lightning never strikes the same place twice.",
]


def _point_paths(root: Path) -> None:
    for name, rel in [("ROOT", ""), ("EXPERIMENTS", "experiments"), ("LEARNINGS", "learnings"),
                      ("OPS", "ops"), ("QUEUE", "ops/queue"), ("STOP", "ops/STOP"),
                      ("EVENTS", "ops/events.jsonl"), ("HEARTBEAT", "ops/heartbeat.json"),
                      ("RUNS", "runs"), ("SOCIAL", "social"),
                      ("LEDGER_SPEND", "ops/spend.jsonl")]:
        setattr(paths, name, root / rel if rel else root)


def items(n: int, split: str, seed: int, start: int = 0) -> list[dict]:
    rnd = random.Random(seed)
    out = []
    for i in range(start, start + n):
        out.append({"id": f"q-demo-{i:010x}", "kind": "claim",
                    "text": f"{CLAIMS[i % len(CLAIMS)]} (case {i})",
                    "label_set": LABELS, "gold": rnd.choice(LABELS), "expert_source": "demo",
                    "split": split, "date": "2026-08-01" if i % 4 == 0 else "2024-01-01",
                    "flags": []})
    return out


def build(root: Path) -> dict:
    from lab.clients.cache import ResponseCache
    from lab.clients.fake import FakeProvider
    from lab.clients.fakemodel import SchemaResponder
    from lab.clients.gateway import Gateway
    from lab.clients.meter import Meter
    from lab.config import load_config
    from lab.orchestrator.loop import Data, Orchestrator
    from lab.protocols.engine import Engine
    from lab.zones import CodeProposer, write_boards
    from tests.conftest import make_filled_config
    from tests.helpers import FakeRetriever

    if root.exists():
        shutil.rmtree(root)
    (root / "experiments").mkdir(parents=True)
    (root / "learnings").mkdir()
    (root / "ops" / "queue").mkdir(parents=True)
    (root / "social").mkdir()
    shutil.copytree(paths.ROOT / "zones", root / "zones")
    (root / "STEERING.md").write_text("demo\n")
    (root / "learnings" / "learnings.jsonl").write_text("")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=d@d", "-c", "user.name=d", "add", "-A"], cwd=root,
                   check=True)
    subprocess.run(["git", "-c", "user.email=d@d", "-c", "user.name=d", "commit", "-qm", "demo"],
                   cwd=root, check=True)
    real_root = paths.ROOT
    _point_paths(root)
    import lab.zones as zmod
    zmod.ZONES = root / "zones"

    cfg = load_config(make_filled_config(root / "tmp"))
    dev, hold = items(80, "dev", 1), items(150, "holdout", 2, start=5000)
    gold = {it["text"]: it["gold"] for it in dev + hold}
    resp = SchemaResponder(accuracy={"claude-haiku-4-5": 0.45, "claude-sonnet-5-5": 0.72,
                                     "grok-4.7-fast": 0.6, "grok-4.7": 0.68,
                                     "claude-opus-5-5": 0.8}, gold=gold)
    prov = {"anthropic": FakeProvider("anthropic", resp, 300),
            "xai": FakeProvider("xai", resp, 300)}
    gw = Gateway(cfg, Meter(cfg), ResponseCache(root / ".cache"), prov, sleep=lambda s: 0)
    import os
    os.environ["CL_HOLDOUT_DIR"] = str(root / "holdout")
    orch = Orchestrator(cfg, Engine(gw, FakeRetriever()), None, Data(dev, lambda: hold,
                                                                     "2026-06-30"),
                        root=root, workers=8, resamples=2000)
    orch.cfg.scoring["promotion"]["holdout_gate_margin"] = 0.15
    lib = real_root / "lab" / "protocols" / "library"
    plan = [("single-claude-haiku", "Z1"), ("single-claude-sonnet", "Z1"),
            ("self-consistency", "Z2"), ("panel-vote", "Z2"), ("debate-judge", "Z4"),
            ("seed/michael-asymmetric", "Z5"), ("seed/chateval-panel", "Z6"),
            ("evidence-first", "Z7"), ("single-claude-opus", "Z1")]
    for name, zone in plan:
        p = yaml.safe_load((lib / f"{name}.yaml").read_text())
        orch.experimenter = CodeProposer(p, f"{p['id']} improves on the current champion",
                                         zone)
        orch.cycle()
    write_boards(orch.results(), root / "zones")
    s0 = root / "experiments" / "season0"
    s0.mkdir()
    papers = ["01-irving", "02-du", "03-liang", "04-chan", "05-michael", "06-khan",
              "07-kenton", "08-smit"]
    verdicts = ["unclear", "not replicated", "replicated", "unclear", "unclear", "replicated",
                "not replicated", "unclear"]
    card = []
    for p, v in zip(papers, verdicts, strict=True):
        lo = {"replicated": 0.01, "not replicated": -0.06, "unclear": -0.03}[v]
        card.append({"paper": p, "claim": f"Headline finding of {p}", "verdict": v,
                     "card": f"library/cards/{p}.md",
                     "tests": [{"protocol": f"{p.split('-')[1]}-seed", "control": "control",
                                "diff": lo + 0.03, "ci": [lo, lo + 0.06], "split": "dev screen",
                                "verdict": v, "cost_usd": 3.2, "n": 100}]})
    (s0 / "scorecard.json").write_text(json.dumps(card, indent=1))
    social = root / "social"
    social.joinpath("posts.jsonl").write_text(json.dumps(
        {"post_id": "1850000000000000001", "kind": "case", "experiment": "E-0005",
         "item": dev[3]["id"], "text": "Did the AI panel get this right?",
         "result_file": "experiments/E-0005/results.json", "ts": "2026-09-30T15:00:00+00:00"})
        + "\n")
    social.joinpath("scores.jsonl").write_text(json.dumps(
        {"post_id": "1850000000000000001", "poll": {"n": 41, "score": 0.38, "wrong_share": 0.12},
         "weighted": {"score": 0.71, "n_eff": 17.4, "wilson": 0.52},
         "social_index": 1.3, "engagement_rate": 0.031}) + "\n")
    social.joinpath("feedback.jsonl").write_text("".join(json.dumps(x) + "\n" for x in [
        {"category": "praise"}, {"category": "confusing"}, {"category": "design suggestion"},
        {"category": "verdict dispute"}]))
    from viz.dashboard.data import snapshot
    snap = snapshot(local=True)
    (root / "snapshot.json").write_text(json.dumps(snap, indent=1, default=str))
    return snap


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/cl-demo")
    s = build(out)
    print(f"wrote {out/'snapshot.json'}: {len(s['experiments'])} experiments, "
          f"{len(s['cases'])} cases")
