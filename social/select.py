"""Case selection for posts (spec §7.1 step 9, §9.2). Flagged items are never auto-selected.

Only dev cases from committed experiments are eligible: the holdout is never shown
publicly (it would stop being hidden).
"""

from __future__ import annotations

from lab.protocols.runner import load_dev_transcripts
from lab.scoring import leaderboard
from social.policy import load_policy, logged_posts

BLOCKED_FLAGS_KEY = ("never_without_approval", "flags")


def eligible(t: dict, blocked: set[str], posted: set[tuple[str, str]]) -> bool:
    if "flags" not in t:                       # unknown flags: treat as flagged
        return False
    if set(t["flags"]) & blocked:
        return False
    if t.get("gold") is None or t["verdict"] == "abstain" or t.get("error"):
        return False
    if t.get("split", "dev") != "dev":
        return False
    return (t["experiment"], t["item"]) not in posted


def interest(t: dict, why: list[str]) -> float:
    """Prefer cases people learn from: split panels that resolved, confident calls, upsets."""
    s = len(why) * 1.0
    if t.get("agreement") and min(t["agreement"]) < 0.6:
        s += 1.0
    s += t["confidence"]
    s += 0.5 if t["verdict"] != t["gold"] else 0.0       # honest misses are worth showing too
    return s


def select_case(results: list[dict] | None = None) -> dict | None:
    pol = load_policy()
    blocked = set(pol[BLOCKED_FLAGS_KEY[0]][BLOCKED_FLAGS_KEY[1]])
    posted = {(p.get("experiment"), p.get("item")) for p in logged_posts()}
    results = results if results is not None else leaderboard.load_results()
    best, best_s = None, -1.0
    for r in sorted(results, key=lambda r: r["experiment"], reverse=True)[:10]:
        why = {c["item"]: c["why"] for c in r.get("cases", [])}
        for t in load_dev_transcripts(r["experiment"]):
            if not eligible(t, blocked, posted):
                continue
            s = interest(t, why.get(t["item"], []))
            if s > best_s:
                best, best_s = {**t, "_result_file": f"experiments/{r['experiment']}/"
                                                     "results.json"}, s
    return best
