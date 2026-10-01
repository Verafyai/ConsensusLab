"""Canonical filesystem locations. Everything resolves from the repo root."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = ROOT / "data"
EXPERIMENTS = ROOT / "experiments"
RUNS = ROOT / "runs"
LEARNINGS = ROOT / "learnings"
OPS = ROOT / "ops"
QUEUE = OPS / "queue"
REPORTS = OPS / "reports"
STOP = OPS / "STOP"
HEARTBEAT = OPS / "heartbeat.json"
EVENTS = OPS / "events.jsonl"
SOCIAL = ROOT / "social"
PAUSE = SOCIAL / "PAUSE"
CACHE = Path(os.environ.get("CL_CACHE_DIR", ROOT / ".cache"))
LEDGER_SPEND = OPS / "spend.jsonl"


def holdout_dir() -> Path:
    """Holdout location outside the repo. Only lab.orchestrator.holdout should call this."""
    return Path(os.environ.get("CL_HOLDOUT_DIR", "~/.consensus-lab/holdout")).expanduser()
