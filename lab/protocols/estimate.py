"""Dry-run cost estimates for protocols (spec §7.1 step 3, §11).

Enumerates the calls a protocol will make per item and prices them with config/prices.yaml.
`expected` uses typical token counts; `worst` assumes every call hits max_tokens. When
committed results have real observations for a protocol, those calibrate `expected`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from lab import paths
from lab.config import Config

BASE_IN = 700            # system + instructions + claim
EV_IN = 230              # one evidence passage (≈150 words + header)
TURN_IN = 260            # one prior turn shown back to an agent
OUT_EXPECTED = 450       # typical output incl. low-effort thinking
DEFAULT_MAX_TOKENS = 2000


@dataclass
class Estimate:
    calls: int
    expected_usd: float
    worst_usd: float
    search_usd: float
    by_model: dict[str, int] = field(default_factory=dict)

    def total(self, n_items: int, worst: bool = False) -> float:
        return n_items * (self.worst_usd if worst else self.expected_usd)


def call_plan(p: dict) -> list[tuple[str, int]]:
    """[(model alias, approx input tokens)] for one item."""
    ev = p.get("evidence", {})
    n_ev = ev.get("max_sources", 6) if ev.get("retrieve") else 0
    ev_in = n_ev * EV_IN
    agents = p["agents"]
    pat = p["pattern"]
    R = max(1, p.get("rounds", 2))
    plan: list[tuple[str, int]] = []
    if pat == "single":
        plan.append((agents[0]["model"], BASE_IN + ev_in))
    elif pat == "sample_vote":
        plan += [(agents[0]["model"], BASE_IN + ev_in)] * agents[0].get("samples", 5)
    elif pat in ("panel", "evidence_first"):
        plan += [(a["model"], BASE_IN + ev_in) for a in agents]
    elif pat == "society":
        k = len(agents)
        R = p.get("rounds", 2)
        plan += [(a["model"], BASE_IN + ev_in) for a in agents]
        for _ in range(R):
            plan += [(a["model"], BASE_IN + ev_in + k * TURN_IN) for a in agents]
            if p.get("communication") == "simultaneous_summarizer":
                plan.append((agents[0]["model"], BASE_IN + k * TURN_IN))
    elif pat in ("debate", "consultancy"):
        judge = next(a for a in agents if a["role"] == "judge")
        speakers = [a for a in agents if a["role"] in ("advocate", "consultant")]
        n = p.get("best_of_n", 1)
        judge_ev = ev_in if ev.get("judge_sees", "full") == "full" else 0
        for r in range(R):
            for a in speakers:
                hist = r * len(speakers) * TURN_IN
                plan += [(a["model"], BASE_IN + ev_in + hist)] * n
                if n > 1:
                    plan.append((judge["model"], BASE_IN + n * TURN_IN))
            if p.get("early_stop", {}).get("judge_can_end") and r < R - 1:
                plan.append((judge["model"],
                             BASE_IN + judge_ev + (r + 1) * len(speakers) * TURN_IN))
        plan.append((judge["model"], BASE_IN + judge_ev + R * len(speakers) * TURN_IN))
    elif pat == "chateval":
        judges = [a for a in agents if a["role"] == "judge"]
        for r in range(R):
            for i, a in enumerate(judges):
                plan.append((a["model"], BASE_IN + ev_in + (r * len(judges) + i) * TURN_IN))
            if p.get("communication") == "simultaneous_summarizer":
                plan.append((judges[0]["model"], BASE_IN + len(judges) * TURN_IN))
    return plan


def observed_per_item(protocol_id: str) -> float | None:
    """Mean actual uncached USD per item from committed results, if this protocol ran."""
    vals = []
    for f in paths.EXPERIMENTS.glob("*/results.json"):
        try:
            r = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        v = r.get("dev", {}).get("usd_per_item_uncached")
        if r.get("protocol") == protocol_id and v:
            vals.append(v)
    return sum(vals) / len(vals) if vals else None


def estimate(p: dict, cfg: Config, use_observed: bool = True) -> Estimate:
    plan = call_plan(p)
    max_out = p.get("max_tokens", DEFAULT_MAX_TOKENS)
    exp = worst = 0.0
    by_model: dict[str, int] = {}
    for alias, n_in in plan:
        price = cfg.price(cfg.model(alias)["id"])
        exp += (n_in * float(price["input"]) + OUT_EXPECTED * float(price["output"])) / 1e6
        worst += (n_in * float(price["input"]) + max_out * float(price["output"])) / 1e6
        by_model[alias] = by_model.get(alias, 0) + 1
    search = 0.0
    ev = p.get("evidence", {})
    if ev.get("retrieve"):
        q = len(p["agents"]) if ev.get("per_agent") == "independent" else 1
        search = q * cfg.service_price("search_per_query")
    exp += search
    worst += search
    if use_observed:
        obs = observed_per_item(p["id"])
        if obs is not None:
            exp = max(exp * 0.5, obs)     # trust real data, but never below half the model
    return Estimate(len(plan), exp, worst, search, by_model)
