import json

from harness import health, rto
from lab import paths
from tests.test_e11_harness import ops  # noqa: F401


def test_rto_feed_is_hash_chained_and_tamper_evident(ops, monkeypatch):  # noqa: F811
    monkeypatch.setattr(paths, "EXPERIMENTS", ops / "experiments")
    (ops / "experiments").mkdir()
    paths.EVENTS.parent.mkdir(parents=True, exist_ok=True)
    paths.EVENTS.write_text("".join(json.dumps({"ts": 1790000000 + i, "type": "cycle.start",
                                                "actor": "orchestrator",
                                                "data": {"experiment": f"E-000{i}"}}) + "\n"
                                    for i in range(3)))
    health.beat("orchestrator", "dev", paths.HEARTBEAT)
    n1 = rto.sync()
    assert n1 == 5 and rto.verify() == (True, 5)
    assert rto.sync() == 2                       # no re-export of old events
    roster = json.loads((ops / "ops" / "rto" / "roster.json").read_text())
    assert {a["room"] for a in roster["agents"]} == {"consensus-lab"}
    f = ops / "ops" / "rto" / "events.ndjson"
    lines = f.read_text().splitlines()
    ev = json.loads(lines[1])
    ev["data"]["experiment"] = "E-9999"
    lines[1] = json.dumps(ev)
    f.write_text("\n".join(lines) + "\n")
    assert rto.verify()[0] is False


def test_hash_matches_collective_scheme():
    ev = {"seq": 1, "ts": "2026-10-01T00:00:00+00:00", "actor": "a", "type": "t", "run": None,
          "data": {}, "prev": "GENESIS"}
    import hashlib
    expect = hashlib.sha256(json.dumps(ev, sort_keys=True, separators=(",", ":"),
                                       ensure_ascii=False).encode()).hexdigest()
    assert rto.sha(rto.canon(ev)) == expect
