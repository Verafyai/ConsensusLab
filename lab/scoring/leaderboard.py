"""Leaderboard built from committed experiment results (spec §6, §8.2)."""

from __future__ import annotations

import json
from pathlib import Path

from lab import paths

FILE = "leaderboard.json"


def load_results(root: Path | None = None) -> list[dict]:
    root = root or paths.EXPERIMENTS
    out = []
    for f in sorted(root.glob("E-*/results.json")):
        try:
            out.append(json.loads(f.read_text()))
        except json.JSONDecodeError:
            continue
    return out


def _m(block: dict | None, *keys: str):
    for k in keys:
        if not isinstance(block, dict):
            return None
        block = block.get(k)
    return block


def build(results: list[dict]) -> dict:
    """One row per protocol: its latest dev result and its latest holdout result."""
    rows: dict[str, dict] = {}
    for r in sorted(results, key=lambda r: r["experiment"]):
        pid = r["protocol"]
        row = rows.setdefault(pid, {"protocol": pid, "paper": r.get("paper"),
                                    "zone": r.get("zone"), "tags": r.get("tags", []),
                                    "experiments": []})
        row["experiments"].append(r["experiment"])
        if r.get("dev", {}).get("n"):
            row["dev_macro_f1"] = r["dev"]["macro_f1"]
            row["dev_n"] = r["dev"]["n"]
            row["usd_per_item"] = _m(r, "dev", "cost", "usd_per_item_uncached")
            row["median_latency_s"] = _m(r, "dev", "cost", "median_latency_s")
            row["rounds"] = r["dev"].get("rounds")
            row["dev_ece"] = r["dev"].get("ece")
            row["dev_recall"] = r["dev"].get("recall")
            row["dev_source"] = f"experiments/{r['experiment']}/results.json"
        hold = r.get("holdout") or {}
        if _m(hold, "full", "n"):
            row["holdout_macro_f1"] = hold["full"]["macro_f1"]
            row["holdout_ece"] = hold["full"].get("ece")
            row["holdout_recall"] = hold["full"].get("recall")
            row["post_cutoff_macro_f1"] = _m(hold, "post_cutoff", "macro_f1")
            row["vs_champion"] = r.get("vs_champion")
            row["vs_best_single"] = r.get("vs_best_single")
            row["holdout_source"] = f"experiments/{r['experiment']}/results.json"
        row["status"] = r.get("status")
    champion = current_champion(results)
    for row in rows.values():
        if row["protocol"] == champion:
            row["status"] = "champion"
    table = sorted(rows.values(), key=lambda x: -(x.get("holdout_macro_f1")
                                                  or x.get("dev_macro_f1") or 0))
    return {"champion": champion, "rows": table, "pareto": pareto(table)}


def current_champion(results: list[dict]) -> str | None:
    champ = None
    for r in sorted(results, key=lambda r: r["experiment"]):
        if r.get("status") == "promoted":
            champ = r["protocol"]
    return champ


def pareto(rows: list[dict]) -> list[str]:
    """Protocols not dominated on (higher accuracy, lower cost)."""
    pts = [(r["protocol"], r.get("holdout_macro_f1") or r.get("dev_macro_f1"),
            r.get("usd_per_item")) for r in rows]
    pts = [p for p in pts if p[1] is not None and p[2] is not None]
    front = []
    for pid, acc, usd in pts:
        dominated = any((a >= acc and u <= usd) and (a > acc or u < usd) for _, a, u in pts)
        if not dominated:
            front.append(pid)
    return front


def write(root: Path | None = None) -> dict:
    root = root or paths.EXPERIMENTS
    lb = build(load_results(root))
    (root / FILE).write_text(json.dumps(lb, indent=2, sort_keys=True))
    return lb
