"""Read-only static export of the dashboard for GitHub Pages (spec §8.2).

    uv run python -m viz.dashboard.export site/ [--with-cases]

Writes index.html + static/ + data.json (snapshot with local=False: no ratings, no
controls) + the result files the numbers link to. With --with-cases it also publishes the
dev replays (transcripts include claim text, so this waits on the source licenses: see
data/SOURCES.md, decision 12). Holdout items and transcripts are never exported.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from lab import paths

HERE = Path(__file__).parent


def export(out: Path, with_cases: bool = False) -> dict:
    from viz.dashboard.data import snapshot
    from viz.dashboard.server import dev_transcript, safe_file
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copy(HERE / "index.html", out / "index.html")
    if (HERE / "static").exists():
        shutil.copytree(HERE / "static", out / "static")
    snap = snapshot(local=False)
    snap.pop("ratings", None)
    if not with_cases:
        snap["cases"] = []
        for e in snap["experiments"]:
            e["cases"] = []
        snap["disagreement"]["cells"] = [{**c, "split_items": []}
                                         for c in snap["disagreement"]["cells"]]
    (out / "data.json").write_text(json.dumps(snap, default=str))
    # The result files every number links to.
    files = {e["source"] for e in snap["experiments"]}
    for e in snap["experiments"]:
        for name in ("summary.md", "proposal.md", "protocol.yaml"):
            files.add(f"experiments/{e['experiment']}/{name}")
    files |= {f"library/cards/{p.name}" for p in (paths.ROOT / "library/cards").glob("*.md")}
    files |= {f"zones/{z}/{n}" for z in [p.name for p in (paths.ROOT / "zones").glob("Z*")]
              for n in ("ZONE.md", "leaderboard.json")}
    files |= {"LEARNINGS.md", "experiments/leaderboard.json", "experiments/season0/SCORECARD.md"}
    n_files = 0
    for rel in sorted(files):
        src = safe_file(rel)
        if src:
            dst = out / "files" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dst)
            n_files += 1
    n_cases = 0
    if with_cases:
        replay = paths.ROOT / "viz" / "replay"
        if replay.exists():
            shutil.copytree(replay, out / "replay",
                            ignore=shutil.ignore_patterns("*.py", "__pycache__", "samples"))
        for c in snap["cases"]:
            t = dev_transcript(c["experiment"], c["item"])
            if t:
                dst = out / "t" / c["experiment"] / f"{c['item']}.json"
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text(json.dumps(t))
                n_cases += 1
    (out / ".nojekyll").write_text("")
    return {"files": n_files, "cases": n_cases, "out": str(out)}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--with-cases", action="store_true")
    a = ap.parse_args(argv)
    print(export(a.out, a.with_cases))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
