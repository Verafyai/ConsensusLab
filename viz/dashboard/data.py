"""Dashboard data snapshot (spec §8.2). Built only from committed files, so every number can
link to the result file it came from. Holdout items and transcripts are never included;
only aggregate holdout scores from results.json are.

    uv run python -m viz.dashboard.data > /tmp/snapshot.json
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from lab import paths
from lab.orchestrator import learnings
from lab.scoring import leaderboard


def _jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _json(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def spend_summary(cfg=None, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    rows = _jsonl(paths.LEDGER_SPEND)
    day, week, month = now.date().isoformat(), now - timedelta(days=7), now.strftime("%Y-%m")
    tot = defaultdict(float)
    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        ts = datetime.fromisoformat(r["ts"])
        k = r.get("track", "lab")
        if r["ts"][:10] == day:
            tot[f"{k}.day"] += r["usd"]
        if ts >= week:
            tot[f"{k}.week"] += r["usd"]
        if r["ts"][:7] == month:
            tot[f"{k}.month"] += r["usd"]
        if (r.get("experiment") or "").startswith("S0-"):
            tot["season0"] += r["usd"]
        by_day[r["ts"][:10]] += r["usd"]
    caps = {}
    if cfg is not None:
        for name, key in [("lab.day", "max_usd_per_day"), ("lab.month", "max_usd_per_month"),
                          ("social.day", "social.max_usd_per_day"),
                          ("social.month", "social.max_usd_per_month"),
                          ("season0", "season0.max_usd_screening")]:
            try:
                caps[name] = cfg.cap(key)
            except Exception:  # noqa: BLE001 - placeholders show as unset
                caps[name] = None
    cum, series = 0.0, []
    for d in sorted(by_day):
        cum += by_day[d]
        series.append({"date": d, "usd": round(by_day[d], 4), "cumulative": round(cum, 4)})
    return {"totals": {k: round(v, 4) for k, v in tot.items()}, "caps": caps,
            "series": series, "source": "ops/spend.jsonl"}


def experiments_view(results: list[dict]) -> list[dict]:
    out = []
    for r in sorted(results, key=lambda r: r["experiment"]):
        d = paths.EXPERIMENTS / r["experiment"]
        prop = (d / "proposal.md").read_text() if (d / "proposal.md").exists() else ""
        from lab.orchestrator.loop import Orchestrator
        pp = Orchestrator.parse_proposal(prop) if prop else {}
        dev = r.get("dev") or {}
        hold = (r.get("holdout") or {}).get("full") or {}
        out.append({
            "experiment": r["experiment"], "protocol": r.get("protocol"),
            "created": r.get("created"), "status": r.get("status"), "reason": r.get("reason"),
            "zone": r.get("zone"), "paper": r.get("paper"), "track": r.get("track", "A"),
            "hypothesis": pp.get("hypothesis"), "builds_on": pp.get("builds_on", []),
            "dev_macro_f1": dev.get("macro_f1"), "dev_n": dev.get("n"),
            "holdout_macro_f1": hold.get("macro_f1"), "ece": hold.get("ece", dev.get("ece")),
            "usd_per_item": (dev.get("cost") or {}).get("usd_per_item_uncached"),
            "usd_total": (dev.get("cost") or {}).get("usd_total"),
            "vs_champion": r.get("vs_champion"), "cases": r.get("cases", []),
            "source": f"experiments/{r['experiment']}/results.json"})
    return out


def trends(results: list[dict], hit: list[dict]) -> dict:
    """Per experiment, in order: Track A scores (dev and holdout), champion's holdout
    macro-F1 after the experiment, and the hit rate."""
    rows, champ_f1 = [], None
    hr = {h["experiment"]: h for h in hit}
    for r in sorted(results, key=lambda r: r["experiment"]):
        dev = r.get("dev") or {}
        hold = (r.get("holdout") or {}).get("full") or {}
        if r.get("status") == "promoted" and hold.get("macro_f1") is not None:
            champ_f1 = hold["macro_f1"]
        rows.append({"experiment": r["experiment"], "created": r.get("created"),
                     "dev_macro_f1": dev.get("macro_f1"), "holdout_macro_f1": hold.get("macro_f1"),
                     "ece": hold.get("ece", dev.get("ece")), "brier": hold.get("brier",
                                                                               dev.get("brier")),
                     "usd_per_item": (dev.get("cost") or {}).get("usd_per_item_uncached"),
                     "champion_macro_f1": champ_f1,
                     "hit_rate": (hr.get(r["experiment"]) or {}).get("rate")})
    return {"rows": rows}


def disagreement(results: list[dict], max_protocols: int = 12) -> dict:
    """How often each pair of protocols reaches different verdicts on the same dev items,
    from local dev transcripts (runs/), with the item ids where they split."""
    from lab.protocols.runner import load_dev_transcripts
    latest: dict[str, str] = {}
    for r in sorted(results, key=lambda r: r["experiment"]):
        if (r.get("dev") or {}).get("n"):
            latest[r["protocol"]] = r["experiment"]
    verdicts: dict[str, dict[str, str]] = {}
    for pid, exp in list(latest.items())[-max_protocols:]:
        ts = load_dev_transcripts(exp)
        if ts:
            verdicts[pid] = {t["item"]: t["verdict"] for t in ts}
    names = sorted(verdicts)
    cells = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            common = sorted(set(verdicts[a]) & set(verdicts[b]))
            if not common:
                continue
            split = [it for it in common if verdicts[a][it] != verdicts[b][it]]
            cells.append({"a": a, "b": b, "n": len(common), "rate": len(split) / len(common),
                          "experiments": [latest[a], latest[b]], "split_items": split[:20]})
    return {"protocols": names, "cells": cells}


def ratings_view() -> dict:
    from lab.scoring.human import wilson_lower
    rows = _jsonl(paths.ROOT / "ratings.jsonl")
    agg: dict[str, dict] = {}
    for r in rows:
        k = f"{r['experiment']}/{r['item']}"
        a = agg.setdefault(k, {"experiment": r["experiment"], "item": r["item"],
                               "protocol": r.get("protocol"), "up": 0, "down": 0, "notes": []})
        a["up" if r["thumb"] == "up" else "down"] += 1
        if r.get("note"):
            a["notes"].append(r["note"])
    for a in agg.values():
        a["wilson"] = wilson_lower(a["up"], a["up"] + a["down"])
    return {"cases": list(agg.values()), "n": len(rows), "source": "ratings.jsonl"}


def cases_view(results: list[dict], limit: int = 400) -> list[dict]:
    """Replayable dev cases (never holdout), with filters the browser uses."""
    from lab.protocols.runner import load_dev_transcripts
    out = []
    for r in sorted(results, key=lambda r: r["experiment"], reverse=True):
        why = {c["item"]: c["why"] for c in r.get("cases", [])}
        for t in load_dev_transcripts(r["experiment"]):
            out.append({"experiment": r["experiment"], "protocol": t["protocol"],
                        "item": t["item"], "question": t["question"][:200],
                        "verdict": t["verdict"], "gold": t.get("gold"),
                        "correct": t.get("gold") == t["verdict"] if t.get("gold") else None,
                        "confidence": t["confidence"], "why": why.get(t["item"], []),
                        "min_agreement": min(t["agreement"]) if t.get("agreement") else None,
                        "replay": f"/t/{r['experiment']}/{t['item']}"})
            if len(out) >= limit:
                return out
    return out


def social_view() -> dict:
    posts = _jsonl(paths.SOCIAL / "posts.jsonl")
    fb = _jsonl(paths.SOCIAL / "feedback.jsonl")
    scores = _jsonl(paths.SOCIAL / "scores.jsonl")
    by_post: dict[str, dict] = {}
    for s in scores:
        by_post.setdefault(s["post_id"], {}).update(s)
    themes: dict[str, int] = defaultdict(int)
    for f in fb:
        themes[f.get("category", "other")] += 1
    return {"posts": [{**p, "scores": by_post.get(p.get("post_id"), {})} for p in posts],
            "feedback_themes": dict(themes), "n_feedback": len(fb),
            "raters": _json(paths.SOCIAL / "raters_summary.json", {})}


def zones_view() -> list[dict]:
    from lab import zones
    out = []
    for z in zones.zone_ids():
        zz = zones.load(z)
        b = _json(zones.ZONES / z / "leaderboard.json", {}) or {}
        out.append({"zone": z, "name": zz.name, "control": zz.control, "knobs": zz.knobs,
                    "subs": {k: v["id"] for k, v in zz.subs.items()},
                    "board": b, "doc": f"zones/{z}/ZONE.md"})
    return out


def headline(lb: dict, results: list[dict], spend: dict) -> str:
    champ = lb.get("champion")
    rows = {r["protocol"]: r for r in lb.get("rows", [])}
    if not champ:
        n = len(results)
        return (f"No champion yet: {n} experiment{'s' if n != 1 else ''} run, "
                f"${sum(s['usd'] for s in spend['series']):.2f} spent.")
    c = rows.get(champ, {})
    singles = [r for r in rows.values() if r["protocol"].startswith("single-")
               and r.get("holdout_macro_f1") is not None]
    best_single = max(singles, key=lambda r: r["holdout_macro_f1"], default=None)
    total = sum(s["usd"] for s in spend["series"])
    f1 = c.get("holdout_macro_f1")
    s = f"Champion {champ}: holdout macro-F1 {f1:.3f}" if f1 is not None else f"Champion {champ}"
    if best_single and f1 is not None and best_single["protocol"] != champ:
        s += (f", {f1 - best_single['holdout_macro_f1']:+.3f} vs the best single model "
              f"({best_single['protocol']})")
    return s + f", ${total:.2f} spent to get here."


def snapshot(local: bool = True) -> dict:
    from lab.config import get
    results = leaderboard.load_results()
    lb = leaderboard.build(results)
    rows = learnings.load()
    hit = learnings.hit_rate(results, rows)
    try:
        cfg = get()
    except Exception:  # noqa: BLE001
        cfg = None
    spend = spend_summary(cfg)
    s0 = paths.EXPERIMENTS / "season0"
    holdout_left = None
    if cfg is not None:
        f = paths.OPS / "holdout_evals.jsonl"
        week_ago = datetime.now(UTC) - timedelta(days=7)
        used = sum(1 for r in _jsonl(f) if datetime.fromisoformat(r["ts"]) > week_ago)
        holdout_left = int(cfg.budget.get("holdout_evals_per_week", 10)) - used
    snap = {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"), "local": local,
        "headline": headline(lb, results, spend), "leaderboard": lb,
        "experiments": experiments_view(results), "trends": trends(results, hit),
        "hit_rate": hit, "learnings": [r for r in rows if r["status"] != "superseded"],
        "season0": {"scorecard": _json(s0 / "scorecard.json", []),
                    "screen": _json(s0 / "screen.json", {})},
        "zones": zones_view(), "disagreement": disagreement(results),
        "cases": cases_view(results), "social": social_view(), "spend": spend,
        "holdout_evals_left": holdout_left,
    }
    if local:
        snap["ratings"] = ratings_view()
    return snap


if __name__ == "__main__":
    json.dump(snapshot(), sys.stdout, indent=1, default=str)
    sys.exit(0)
