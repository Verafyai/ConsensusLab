"""Heartbeat (spec §10). Each component writes its liveness to ops/heartbeat.json; the
monitor pane turns red when a heartbeat goes stale or a cap is breached.

    uv run python -m harness.health            # print status
"""

from __future__ import annotations

import fcntl
import json
import os
import sys
import time
from pathlib import Path

from lab import paths

STALE_AFTER_S = 90          # heartbeat interval is 15 s; stale after 6 missed beats


def _path() -> Path:
    return paths.HEARTBEAT


def beat(component: str, state: str, path: Path | None = None, **extra) -> None:
    p = path or _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p.with_suffix(".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = json.loads(p.read_text()) if p.exists() and p.stat().st_size else {}
        data[component] = {"ts": time.time(), "state": state, "pid": os.getpid(), **extra}
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1, sort_keys=True))
        tmp.replace(p)


def read(path: Path | None = None) -> dict:
    p = path or _path()
    return json.loads(p.read_text()) if p.exists() and p.stat().st_size else {}


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def status(path: Path | None = None, now: float | None = None,
           stale_after: float = STALE_AFTER_S) -> dict[str, dict]:
    """component -> {state, age_s, ok, why}."""
    now = now or time.time()
    out = {}
    for comp, hb in read(path).items():
        age = now - hb["ts"]
        why = None
        if age > stale_after:
            why = f"stale heartbeat ({age:.0f}s)"
        elif hb.get("pid") and not alive(hb["pid"]):
            why = "process gone"
        out[comp] = {"state": hb.get("state"), "age_s": round(age, 1), "ok": why is None,
                     "why": why}
    return out


if __name__ == "__main__":
    for c, s in status().items():
        print(f"{'OK ' if s['ok'] else 'RED'} {c:13} {s['state']:12} {s['age_s']:>6}s "
              f"{s['why'] or ''}")
    sys.exit(0)
