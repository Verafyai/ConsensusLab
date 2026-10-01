"""Job queue for runs started from the dashboard (spec §8.3). The dashboard only enqueues;
the orchestrator executes, re-checking every cap. Every action is logged to the Record.

Job types:
  run     {protocol, n, zone}     dev-only experiment from a zone template + knob values
  refine  {zone, iterations, budget, steer}
  arena   {experiment}            one configuration to the holdout (uses a weekly eval)
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from lab import paths


def jobs_dir() -> Path:
    d = paths.OPS / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def record(action: str, by: str, **data) -> None:
    """The Record: who started what, and what it cost (spec §8.3)."""
    f = paths.OPS / "record.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a") as fh:
        fh.write(json.dumps({"ts": datetime.now(UTC).isoformat(timespec="seconds"),
                             "action": action, "by": by, **data}) + "\n")


def enqueue(kind: str, params: dict, by: str, estimate_usd: float | None = None) -> dict:
    job = {"id": f"J-{int(time.time())}-{uuid.uuid4().hex[:6]}", "type": kind,
           "params": params, "by": by, "state": "queued", "estimate_usd": estimate_usd,
           "created": datetime.now(UTC).isoformat(timespec="seconds")}
    (jobs_dir() / f"{job['id']}.json").write_text(json.dumps(job, indent=1))
    record(f"job.{kind}.queued", by, job=job["id"], params=params, estimate_usd=estimate_usd)
    return job


def all_jobs() -> list[dict]:
    out = []
    for f in sorted(jobs_dir().glob("J-*.json")):
        try:
            out.append(json.loads(f.read_text()))
        except json.JSONDecodeError:
            continue
    return out


def update(job: dict, **changes) -> dict:
    job.update(changes)
    (jobs_dir() / f"{job['id']}.json").write_text(json.dumps(job, indent=1))
    return job


def pending() -> list[dict]:
    return [j for j in all_jobs() if j["state"] == "queued"]


def run_job(orch, job: dict) -> dict:
    from lab import zones
    update(job, state="running", started=datetime.now(UTC).isoformat(timespec="seconds"))
    saved = orch.experimenter
    last = [0.0]

    def progress(stage: str, done: int, total: int) -> None:
        if time.time() - last[0] > 2 or done == total:      # throttle file writes
            last[0] = time.time()
            update(job, progress=f"{stage} {done}/{total}")
    orch.on_progress = progress
    try:
        p = job["params"]
        if job["type"] == "run":
            orch.experimenter = zones.CodeProposer(
                p["protocol"], f"Dashboard run of {p['protocol']['id']} ({p.get('zone')})",
                p.get("zone"), {"n": p["n"]} if p.get("n") else None)
            orch.constraint = {"zone": p["zone"], "dev_only": True,
                               "budget": p.get("budget", orch.cfg.cap("max_usd_per_experiment")),
                               "spent": 0.0} if p.get("zone") else None
            try:
                res = [orch.cycle()]
            finally:
                orch.constraint = None
        elif job["type"] == "refine":
            res = zones.refine(orch, p["zone"], int(p["iterations"]), float(p["budget"]),
                               p.get("steer", ""), experimenter=saved)
        elif job["type"] == "arena":
            import yaml
            src = paths.EXPERIMENTS / p["experiment"] / "protocol.yaml"
            proto = yaml.safe_load(src.read_text())
            orch.experimenter = zones.CodeProposer(
                proto, f"{proto['id']} beats the champion on the holdout", p.get("zone"))
            res = [orch.cycle()]
        else:
            raise ValueError(job["type"])
        usd = sum(((r.get("dev") or {}).get("cost") or {}).get("usd_total", 0) for r in res)
        update(job, state="done", results=[{"experiment": r.get("experiment"),
                                            "status": r.get("status")} for r in res],
               usd=round(usd, 4))
        record(f"job.{job['type']}.done", job["by"], job=job["id"], usd=round(usd, 4))
    except Exception as e:  # noqa: BLE001 - a failed job must not kill the orchestrator
        update(job, state="failed", error=str(e)[:500])
        record(f"job.{job['type']}.failed", job["by"], job=job["id"], error=str(e)[:200])
    finally:
        orch.experimenter = saved
        orch.on_progress = None
    return job
