"""Run a protocol over a set of items, write transcripts and return them.

Dev transcripts go to runs/<experiment>/<item>.json.gz; holdout transcripts never enter the
repo (they go beside the holdout via lab.orchestrator.holdout.runs_dir).
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Callable
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from pathlib import Path

from lab import paths
from lab.clients.meter import BudgetExceeded, Scope
from lab.protocols.engine import Engine, transcript_json


def transcript_path(experiment: str, item_id: str, split: str, root: Path | None = None) -> Path:
    if split == "holdout":
        from lab.orchestrator import holdout
        return holdout.runs_dir(experiment) / f"{item_id}.json.gz"
    return (root or paths.RUNS) / experiment / f"{item_id}.json.gz"


def write_transcript(t: dict, split: str, root: Path | None = None) -> Path:
    p = transcript_path(t["experiment"], t["item"], split, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, "wb") as f:
        f.write(transcript_json(t))
    return p


def read_transcript(p: Path) -> dict:
    with gzip.open(p, "rb") as f:
        return json.loads(f.read())


def load_dev_transcripts(experiment: str, root: Path | None = None) -> list[dict]:
    d = (root or paths.RUNS) / experiment
    return [read_transcript(p) for p in sorted(d.glob("*.json.gz"))] if d.exists() else []


def run_protocol(engine: Engine, protocol: dict, items: list[dict], scope: Scope,
                 experiment: str, workers: int = 4, write: bool = True,
                 runs_root: Path | None = None,
                 progress: Callable[[int, int], None] | None = None) -> list[dict]:
    """Run on every item. A global cap breach (day/month/experiment) stops the batch."""
    out: list[dict] = []
    halted: BudgetExceeded | None = None

    def one(it: dict) -> dict:
        return engine.run_item(protocol, it, scope, experiment=experiment)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = {ex.submit(one, it): it for it in items}
        for f in as_completed(futs):
            try:
                t = f.result()
            except CancelledError:
                continue
            except BudgetExceeded as e:
                halted = halted or e
                for g in futs:
                    g.cancel()
                continue
            if write:
                write_transcript(t, futs[f].get("split", "dev"), runs_root)
            out.append(t)
            if progress:
                progress(len(out), len(items))
    if halted:
        raise halted
    order = {it["id"]: i for i, it in enumerate(items)}
    return sorted(out, key=lambda t: order[t["item"]])
