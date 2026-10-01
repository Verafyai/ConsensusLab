"""The learning file (spec §7.3): structured JSONL for agents, readable LEARNINGS.md.

Code decides `status`, `effect` and `ci`. The experimenter may refine `lesson` and `next`
by filing learnings/proposals/<L-id>.json; merge_proposals() takes only those two fields.

    uv run python -m lab.orchestrator.learnings render
    uv run python -m lab.orchestrator.learnings consolidate
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from lab import paths

STATUSES = ["confirmed", "refuted", "tentative", "superseded"]
ACTIVE_LIMIT = 60


def path() -> Path:
    return paths.LEARNINGS / "learnings.jsonl"


def load(p: Path | None = None) -> list[dict]:
    p = p or path()
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def save(rows: list[dict], p: Path | None = None) -> None:
    p = p or path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def next_id(rows: list[dict]) -> str:
    n = max((int(r["id"].split("-")[1]) for r in rows), default=0)
    return f"L-{n + 1:04d}"


def append(entry: dict, p: Path | None = None) -> dict:
    rows = load(p)
    entry = {"id": next_id(rows), "date": datetime.now(UTC).date().isoformat(), **entry}
    assert entry["status"] in STATUSES, entry["status"]
    rows.append(entry)
    save(rows, p)
    return entry


def from_result(result: dict, proposal: dict) -> dict:
    """Code-written learning for one experiment. Every experiment gets one, rejected or not."""
    status_map = {"better": "confirmed", "worse": "refuted"}
    vs = result.get("vs_champion") or result.get("vs_control") or {}
    label = vs.get("verdict")
    st = result["status"]
    if st in ("rejected_budget", "invalid", "error"):
        status = "tentative"
        lesson = f"Not run: {result.get('reason', st)}"
    elif st == "dev_only":
        status = "tentative"
        cd = result.get("vs_champion_dev") or {}
        lesson = (f"{result['protocol']} ({result.get('zone')} refinement): dev macro-F1 "
                  f"{result['dev']['macro_f1']:.3f}" +
                  (f", {cd['diff']:+.3f} vs champion on dev" if cd.get("diff") is not None
                   else "") + ".")
        vs = cd
    elif st == "stopped_at_dev":
        status = "tentative"
        lesson = (f"{result['protocol']} reached dev macro-F1 {result['dev']['macro_f1']:.3f}, "
                  f"below the champion's dev score by more than the holdout margin.")
    else:
        status = status_map.get(label, "tentative")
        d = result.get("dev", {}).get("cost", {}).get("usd_per_item_uncached")
        before = result.get("champion_before") or "no champion"
        lesson = (f"{result['protocol']}: {label} vs {before}"
                  f" on the holdout" + (f", ${d:.4f}/item" if d else "") + ".")
    eff = vs.get("diff")
    return {
        "track": proposal.get("track", "A"), "zone": result.get("zone"),
        "hypothesis": proposal.get("hypothesis", ""), "builds_on": proposal.get("builds_on", []),
        "experiments": [result["experiment"]],
        "effect": f"{eff:+.3f} macro-F1" if eff is not None else None,
        "ci": [round(x, 4) for x in vs["ci"]] if vs.get("ci") else None,
        "status": status, "lesson": lesson, "next": proposal.get("next", ""),
        "outcome": st,
    }


def merge_proposals(p: Path | None = None) -> int:
    """Apply experimenter refinements of lesson/next text. Returns how many were merged."""
    rows = load(p)
    by_id = {r["id"]: r for r in rows}
    n = 0
    for f in sorted((paths.LEARNINGS / "proposals").glob("L-*.json")):
        try:
            prop = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        r = by_id.get(f.stem)
        if r:
            for k in ("lesson", "next"):
                if isinstance(prop.get(k), str) and prop[k].strip():
                    r[k] = prop[k].strip()[:600]
            n += 1
        f.unlink()
    save(rows, p)
    return n


def hit_rate(results: list[dict], rows: list[dict] | None = None, window: int = 10) -> list[dict]:
    """Share of experiments that produced a promotion or a confirmed lesson, as a rolling
    series over experiments in order (spec §7.3)."""
    rows = rows if rows is not None else load()
    confirmed = {e for r in rows if r["status"] == "confirmed" for e in r["experiments"]}
    hits = [(r["experiment"], r.get("status") == "promoted" or r["experiment"] in confirmed)
            for r in sorted(results, key=lambda r: r["experiment"])]
    out = []
    for i in range(len(hits)):
        win = hits[max(0, i - window + 1): i + 1]
        out.append({"experiment": hits[i][0], "hit": hits[i][1],
                    "rate": sum(h for _, h in win) / len(win),
                    "cumulative": sum(h for _, h in hits[: i + 1]) / (i + 1)})
    return out


def _key(r: dict) -> str:
    return re.sub(r"\W+", " ", r.get("hypothesis", "").lower()).strip()


def consolidate(p: Path | None = None, limit: int = ACTIVE_LIMIT) -> dict:
    """Weekly: merge duplicate hypotheses, supersede old tentative ones, cap the active set."""
    rows = load(p)
    groups: dict[str, list[dict]] = {}
    for r in rows:
        if r["status"] != "superseded" and _key(r):
            groups.setdefault(_key(r), []).append(r)
    merged = 0
    for grp in groups.values():
        if len(grp) < 2:
            continue
        keep = grp[-1]
        for old in grp[:-1]:
            old["status"] = "superseded"
            old["superseded_by"] = keep["id"]
            keep["experiments"] = sorted(set(keep["experiments"]) | set(old["experiments"]))
            merged += 1
    active = [r for r in rows if r["status"] != "superseded"]
    overflow = len(active) - limit
    if overflow > 0:   # retire the oldest tentative lessons first
        for r in [r for r in active if r["status"] == "tentative"][:overflow]:
            r["status"] = "superseded"
            r["superseded_by"] = "consolidation"
    save(rows, p)
    return {"merged": merged, "active": sum(r["status"] != "superseded" for r in rows)}


def render(rows: list[dict] | None = None, feedback_themes: list[str] | None = None) -> str:
    rows = rows if rows is not None else load()
    out = ["# Learnings", "",
           "_Regenerated from `learnings/learnings.jsonl` by "
           "`python -m lab.orchestrator.learnings render`. Do not edit by hand._", ""]
    c = Counter(r["status"] for r in rows)
    out.append(f"{c['confirmed']} confirmed · {c['tentative']} tentative · {c['refuted']} refuted"
               f" · {c['superseded']} superseded")
    sections = [("Confirmed", "confirmed", "What the lab has established."),
                ("Tentative", "tentative", "Suggestive, not yet established."),
                ("Refuted: don't retry", "refuted", "Ideas the evidence went against.")]
    for title, st, blurb in sections:
        rs = [r for r in rows if r["status"] == st]
        out += ["", f"## {title}", "", blurb, ""]
        if not rs:
            out.append("_None yet._")
        for r in reversed(rs):
            ci = f" (95% CI {r['ci'][0]:+.3f} to {r['ci'][1]:+.3f})" if r.get("ci") else ""
            eff = f" **{r['effect']}**{ci}." if r.get("effect") else ""
            zone = f" [{r['zone']}]" if r.get("zone") else ""
            out.append(f"- **{r['id']}**{zone} {r['hypothesis'] or r['lesson']}.{eff} "
                       f"{r['lesson']}" + (f" _Next:_ {r['next']}" if r.get("next") else "")
                       + f" ({', '.join(r['experiments'])})")
    if feedback_themes:
        out += ["", "## Audience feedback themes (Track B)", ""] + [f"- {t}" for t in
                                                                     feedback_themes]
    return "\n".join(out) + "\n"


def write_markdown(rows: list[dict] | None = None) -> None:
    (paths.ROOT / "LEARNINGS.md").write_text(render(rows))


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "render"
    if cmd == "render":
        write_markdown()
    elif cmd == "consolidate":
        print(consolidate())
        write_markdown()
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
