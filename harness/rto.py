"""Return To Office export (spec §10, E11b, optional).

Publishes the lab's activity in the format the Collective's RTO floor reads: an
append-only, hash-chained events.ndjson (same fields and hashing as the Collective's
agents/bin/eventlog.py: sha256 over canonical JSON, `prev` = previous hash, GENESIS first),
plus a roster of the lab's agents in one room and a KPI snapshot.

    uv run python -m harness.rto sync      # append new lab events, heartbeat and KPIs
    uv run python -m harness.rto verify    # check the chain

Output: ops/rto/{events.ndjson, HEAD.json, roster.json, room.json}. Wiring RTO to read it
is a change on the Collective's side (ops/queue/G-007).
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from lab import paths

ROOM = "consensus-lab"
AGENTS = [
    {"key": "cl-orchestrator", "name": "Orchestrator", "class": "judge",
     "about": "Plain code. Runs experiments, the holdout and the promotion rule."},
    {"key": "cl-experimenter", "name": "Experimenter", "class": "claude",
     "about": "Proposes one consensus experiment per cycle."},
    {"key": "cl-grok", "name": "Grok", "class": "grok",
     "about": "@VerafyAI's voice: case posts, polls, collection."},
    {"key": "cl-dashboard", "name": "Dashboard", "class": "service", "about": "Local dashboard."},
]
ACTOR = {"orchestrator": "cl-orchestrator", "experimenter": "cl-experimenter",
         "grok": "cl-grok", "dashboard": "cl-dashboard"}


def out_dir() -> Path:
    d = paths.OPS / "rto"
    d.mkdir(parents=True, exist_ok=True)
    return d


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def load_head() -> dict:
    f = out_dir() / "HEAD.json"
    return json.loads(f.read_text()) if f.exists() else {"seq": 0, "hash": "GENESIS",
                                                           "source_offset": 0}


def append(head: dict, actor: str, etype: str, data: dict, run: str | None = None,
           ts: str | None = None) -> dict:
    ev = {"seq": head["seq"] + 1, "ts": ts or datetime.now(UTC).isoformat(timespec="seconds"),
          "actor": actor, "type": etype, "run": run, "data": data, "prev": head["hash"]}
    ev["hash"] = sha(canon(ev))
    with (out_dir() / "events.ndjson").open("a") as f:
        f.write(json.dumps(ev, sort_keys=True) + "\n")
    head["seq"], head["hash"] = ev["seq"], ev["hash"]
    return ev


def kpis() -> dict:
    from lab.scoring import leaderboard
    results = leaderboard.load_results()
    lb = leaderboard.build(results)
    champ = next((r for r in lb["rows"] if r["protocol"] == lb.get("champion")), {})
    spend = 0.0
    if paths.LEDGER_SPEND.exists():
        today = datetime.now(UTC).date().isoformat()
        for line in paths.LEDGER_SPEND.read_text().splitlines():
            r = json.loads(line)
            if r["ts"][:10] == today:
                spend += r["usd"]
    return {"champion": lb.get("champion"),
            "champion_holdout_macro_f1": champ.get("holdout_macro_f1"),
            "experiments": len(results), "spend_today_usd": round(spend, 4),
            "queue_for_rex": len([p for p in paths.QUEUE.glob("*")
                                  if p.suffix in (".md", ".json") and p.name != "README.md"])}


def sync() -> int:
    """Append lab events since the last sync, one heartbeat per component, and KPIs."""
    from harness.health import status
    head = load_head()
    n = 0
    if paths.EVENTS.exists():
        lines = paths.EVENTS.read_text().splitlines()
        for line in lines[head.get("source_offset", 0):]:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            actor = ACTOR.get(e.get("actor", "orchestrator"), "cl-orchestrator")
            ts = datetime.fromtimestamp(e["ts"], UTC).isoformat(timespec="seconds")
            append(head, actor, f"lab.{e['type']}", e.get("data", {}),
                   run=(e.get("data") or {}).get("experiment"), ts=ts)
            n += 1
        head["source_offset"] = len(lines)
    for comp, s in status().items():
        if comp in ACTOR:
            append(head, ACTOR[comp], "heartbeat", {"state": s["state"], "ok": s["ok"],
                                                    "age_s": s["age_s"]})
            n += 1
    k = kpis()
    append(head, "cl-orchestrator", "kpi.update", k)
    (out_dir() / "HEAD.json").write_text(json.dumps(head))
    (out_dir() / "roster.json").write_text(json.dumps(
        {"agents": [{**a, "room": ROOM, "status": "active", "votes": False} for a in AGENTS]},
        indent=1))
    (out_dir() / "room.json").write_text(json.dumps(
        {"rooms": {ROOM: {"name": "Consensus Lab", "project": None,
                          "about": "Tests ways for AI panels to reach the right verdict",
                          "kpis": k}}}, indent=1))
    return n + 1


def verify() -> tuple[bool, int]:
    prev, seq = "GENESIS", 0
    f = out_dir() / "events.ndjson"
    if not f.exists():
        return True, 0
    for line in f.read_text().splitlines():
        ev = json.loads(line)
        h = ev.pop("hash")
        if ev["prev"] != prev or sha(canon(ev)) != h or ev["seq"] != seq + 1:
            return False, ev["seq"]
        prev, seq = h, ev["seq"]
    return load_head()["hash"] == prev, seq


if __name__ == "__main__":
    if sys.argv[1:2] == ["verify"]:
        ok, n = verify()
        print(f"{'ok' if ok else 'FAIL'}: {n} events")
        sys.exit(0 if ok else 1)
    print(f"appended {sync()} events")
