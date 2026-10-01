"""Daily digest and weekly lab-update data (spec §7, E16).

    uv run python -m lab.reports daily [--date 2026-10-02]
    uv run python -m lab.reports weekly

The daily digest goes to ops/reports/<date>.md and .json; every field is always present
(empty lists and explicit nulls, never missing keys).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, timedelta

from lab import paths

DAILY_FIELDS = ["date", "champion", "experiments_run", "spend", "lessons", "review_items",
                "approvals_waiting", "holdout_evals_left", "posts", "health", "generated"]


def _rows(p):
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def daily(day: date | None = None, cfg=None) -> dict:
    from lab.orchestrator import learnings
    from lab.scoring import leaderboard
    day = day or datetime.now(UTC).date()
    d = day.isoformat()
    results = leaderboard.load_results()
    lb = leaderboard.build(results)
    champ_row = next((r for r in lb["rows"] if r["protocol"] == lb.get("champion")), None)
    ran = [r for r in results if (r.get("created") or "")[:10] == d]
    spend_rows = _rows(paths.LEDGER_SPEND)
    by_track: dict[str, float] = {}
    month = d[:7]
    month_total = 0.0
    for r in spend_rows:
        if r["ts"][:10] == d:
            by_track[r.get("track", "lab")] = by_track.get(r.get("track", "lab"), 0) + r["usd"]
        if r["ts"][:7] == month and r.get("track", "lab") == "lab":
            month_total += r["usd"]
    caps = {"day": None, "month": None}
    if cfg is not None:
        for k, key in (("day", "max_usd_per_day"), ("month", "max_usd_per_month")):
            try:
                caps[k] = cfg.cap(key)
            except Exception:  # noqa: BLE001 - unset caps stay null
                caps[k] = None
    lessons = [{"id": r["id"], "status": r["status"], "lesson": r["lesson"]}
               for r in learnings.load() if r.get("date") == d]
    queue = sorted(paths.QUEUE.glob("*")) if paths.QUEUE.exists() else []
    reviews = [p.name for p in queue if p.name.startswith("R-")]
    approvals = [p.name for p in queue if p.name.startswith(("G-", "P-"))]
    posts = [{"kind": p["kind"], "post_id": p["post_id"]}
             for p in _rows(paths.SOCIAL / "posts.jsonl") if p["ts"][:10] == d]
    week_ago = datetime.combine(day, datetime.min.time(), UTC) - timedelta(days=6)
    used = sum(1 for r in _rows(paths.OPS / "holdout_evals.jsonl")
               if datetime.fromisoformat(r["ts"]) >= week_ago)
    left = (int(cfg.budget.get("holdout_evals_per_week", 10)) - used) if cfg else None
    try:
        from harness.health import status
        health = {k: v["ok"] for k, v in status().items()}
    except Exception:  # noqa: BLE001
        health = {}
    out = {
        "date": d,
        "champion": {"protocol": lb.get("champion"),
                     "holdout_macro_f1": (champ_row or {}).get("holdout_macro_f1"),
                     "usd_per_item": (champ_row or {}).get("usd_per_item")},
        "experiments_run": [{"experiment": r["experiment"], "protocol": r.get("protocol"),
                             "status": r.get("status"), "reason": r.get("reason") or ""}
                            for r in ran],
        "spend": {"today": {k: round(v, 4) for k, v in by_track.items()},
                  "today_total": round(sum(by_track.values()), 4),
                  "month_lab": round(month_total, 4), "caps": caps},
        "lessons": lessons,
        "review_items": reviews,
        "approvals_waiting": approvals,
        "holdout_evals_left": left,
        "posts": posts,
        "health": health,
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    assert set(out) == set(DAILY_FIELDS)
    return out


def missing_fields(d: dict) -> list[str]:
    return [f for f in DAILY_FIELDS if f not in d]


def daily_md(r: dict) -> str:
    c = r["champion"]
    f1 = f"{c['holdout_macro_f1']:.3f}" if c["holdout_macro_f1"] is not None else "n/a"
    lines = [f"# Consensus Lab · daily digest · {r['date']}", "",
             f"**Champion:** {c['protocol'] or 'none yet'} (holdout macro-F1 {f1})", "",
             f"**Experiments run today:** {len(r['experiments_run'])}"]
    lines += [f"- {e['experiment']} `{e['protocol']}`: {e['status']}"
              + (f": {e['reason']}" if e['reason'] else "") for e in r["experiments_run"]]
    cap = r["spend"]["caps"]["day"]
    lines += ["", f"**Spend today:** ${r['spend']['today_total']:.2f}"
                  + (f" of ${cap:.2f}" if cap else " (cap not set)")
              + f" · month (lab): ${r['spend']['month_lab']:.2f}", "",
              f"**New lessons:** {len(r['lessons'])}"]
    lines += [f"- {x['id']} ({x['status']}): {x['lesson']}" for x in r["lessons"]]
    lines += ["", f"**Review items waiting for Rex:** {len(r['review_items'])}"]
    lines += [f"- {x}" for x in r["review_items"]]
    lines += ["", f"**Gates and approvals waiting:** {len(r['approvals_waiting'])}"]
    lines += [f"- {x}" for x in r["approvals_waiting"]]
    lines += ["", f"**Holdout evaluations left this week:** {r['holdout_evals_left']}",
              f"**Posts today:** {len(r['posts'])}",
              "**Health:** " + (", ".join(f"{k} {'ok' if v else 'RED'}"
                                          for k, v in r["health"].items()) or "no heartbeats")]
    return "\n".join(lines) + "\n"


def write_daily(day: date | None = None, cfg=None) -> dict:
    r = daily(day, cfg)
    paths.REPORTS.mkdir(parents=True, exist_ok=True)
    (paths.REPORTS / f"{r['date']}.json").write_text(json.dumps(r, indent=1))
    (paths.REPORTS / f"{r['date']}.md").write_text(daily_md(r))
    return r


def weekly(cfg=None) -> dict:
    """Data for Grok's weekly lab update: committed results only."""
    from lab.orchestrator import learnings
    from lab.scoring import leaderboard
    lb = leaderboard.build(leaderboard.load_results())
    champ = next((r for r in lb["rows"] if r["protocol"] == lb.get("champion")), {})
    confirmed = [r for r in learnings.load() if r["status"] == "confirmed"]
    sc = paths.EXPERIMENTS / "season0" / "scorecard.json"
    card = json.loads(sc.read_text()) if sc.exists() else []
    out = {"week": datetime.now(UTC).strftime("%G-W%V"), "champion": lb.get("champion"),
           "holdout_macro_f1": champ.get("holdout_macro_f1"),
           "vs_best_single": champ.get("vs_best_single"),
           "usd_per_item": champ.get("usd_per_item"),
           "top_lesson": confirmed[-1]["lesson"] if confirmed else None,
           "season0": {v: sum(1 for r in card if r["verdict"] == v)
                       for v in ("replicated", "not replicated", "unclear")},
           "source_files": ["experiments/leaderboard.json", "learnings/learnings.jsonl"]
           + (["experiments/season0/scorecard.json"] if card else [])}
    paths.REPORTS.mkdir(parents=True, exist_ok=True)
    (paths.REPORTS / f"weekly-{out['week']}.json").write_text(json.dumps(out, indent=1))
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["daily", "weekly"])
    ap.add_argument("--date")
    a = ap.parse_args(argv)
    from lab.config import get
    try:
        cfg = get()
    except Exception:  # noqa: BLE001
        cfg = None
    if a.cmd == "daily":
        r = write_daily(date.fromisoformat(a.date) if a.date else None, cfg)
        print(daily_md(r))
    else:
        print(json.dumps(weekly(cfg), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
