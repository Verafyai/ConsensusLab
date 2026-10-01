"""Build dev and holdout from approved raw sources.

    uv run python -m lab.data.build [--raw data/questions/raw]

Raw files live in data/questions/raw/<source>/ (gitignored). Only sources listed in
data/approved_sources.txt are ingested; that file is written when Rex approves
data/SOURCES.md (GATE G-002).
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

from lab import paths
from lab.config import PLACEHOLDER, get
from lab.data import splits
from lab.data.schema import validate, write_jsonl
from lab.orchestrator import holdout

APPROVED = paths.DATA / "approved_sources.txt"
DEV = paths.DATA / "questions" / "dev.jsonl"
RAW = paths.DATA / "questions" / "raw"
REPORT = paths.DATA / "SPLITS.md"
INGESTERS = ["averitec", "liar", "fever", "claimreview", "panel"]


def approved_sources(path: Path | None = None) -> list[str]:
    path = path or APPROVED
    if not path.exists():
        return []
    return [ln.strip() for ln in path.read_text().splitlines()
            if ln.strip() and not ln.startswith("#")]


def model_cutoff() -> str | None:
    """Latest knowledge cutoff across all panel models; None if any is unknown."""
    cutoffs = [m.get("knowledge_cutoff") for m in get().models["models"].values()]
    if any(c in (None, PLACEHOLDER) for c in cutoffs):
        return None
    return max(str(c) for c in cutoffs)


def collect(raw: Path, sources: list[str]) -> list[dict]:
    items: list[dict] = []
    for src in sources:
        if src not in INGESTERS:
            raise SystemExit(f"no ingester for approved source {src!r}")
        mod = importlib.import_module(f"lab.data.ingest.{src}")
        for f in sorted((raw / src).glob("*")):
            if f.is_file() and not f.name.startswith("."):
                items += [validate(it) for it in mod.ingest(f)]
    return items


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, default=RAW)
    args = ap.parse_args(argv)
    sources = approved_sources()
    if not sources:
        print("No approved sources. Rex approves data/SOURCES.md (ops/queue G-002) first.",
              file=sys.stderr)
        return 2
    cutoff = model_cutoff()
    items = splits.assign(splits.dedupe(collect(args.raw, sources)), cutoff)
    items = [validate(it) for it in items]
    write_jsonl(DEV, (it for it in items if it["split"] == "dev"))
    holdout.write([it for it in items if it["split"] == "holdout"])
    REPORT.write_text(splits.report(items, cutoff))
    print(REPORT.read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
