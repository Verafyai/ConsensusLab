"""The only module allowed to read or write the holdout (spec §3, §4.3).

The holdout lives outside the repo (default ~/.consensus-lab/holdout/). The experimenter's
Claude Code permissions deny reads there (harness/experimenter-settings.json) and
tests/test_e01_data.py checks that no other module touches this path.
"""

from __future__ import annotations

import os
from pathlib import Path

from lab import paths
from lab.data.schema import read_jsonl, validate, write_jsonl

FILE = "holdout.jsonl"


def _path() -> Path:
    return paths.holdout_dir() / FILE


def write(items: list[dict]) -> Path:
    d = paths.holdout_dir()
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    p = _path()
    write_jsonl(p, (validate(it) for it in items))
    os.chmod(p, 0o600)
    return p


def exists() -> bool:
    return _path().exists()


def load() -> list[dict]:
    """Load holdout items. Called only by the orchestrator when an experiment earns it."""
    items = list(read_jsonl(_path()))
    assert all(it["split"] == "holdout" for it in items)
    return items


def runs_dir(experiment: str) -> Path:
    """Holdout transcripts stay outside the repo, beside the holdout itself."""
    d = paths.holdout_dir() / "runs" / experiment
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(paths.holdout_dir(), 0o700)
    return d
