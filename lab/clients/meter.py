"""Token and cost meter with pre-call cap enforcement (spec §11).

Every model call is estimated *before* it is sent. If the worst-case cost would push any
cap over its limit, BudgetExceeded is raised and nothing is sent. Actual spend is appended
to ops/spend.jsonl, which is the source of truth for daily and monthly totals.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from lab import paths
from lab.clients.base import Usage
from lab.config import Config


class BudgetExceeded(RuntimeError):
    def __init__(self, cap: str, would_be: float, limit: float):
        self.cap, self.would_be, self.limit = cap, would_be, limit
        super().__init__(f"cap {cap}: ${would_be:.4f} would exceed ${limit:.4f}; refused")


@dataclass
class Scope:
    """Spend context for a run. Caps here are in addition to the global day/month caps."""
    track: str = "lab"                       # lab | social
    experiment: str | None = None
    item: str | None = None
    caps: dict[str, float] = field(default_factory=dict)    # name -> limit
    spent: dict[str, float] = field(default_factory=dict)   # name -> spent so far

    def child(self, item: str, item_cap: float) -> Scope:
        """A per-item scope that shares this scope's running totals (dicts are shared)."""
        s = Scope(self.track, self.experiment, item, self.caps, self.spent)
        s.caps[f"item:{item}"] = item_cap
        s.spent.setdefault(f"item:{item}", 0.0)
        return s


def cost_usd(usage: Usage, price: dict[str, float]) -> float:
    inp = float(price["input"])
    return (usage.input_tokens * inp
            + usage.output_tokens * float(price["output"])
            + usage.cache_read_tokens * float(price.get("cache_read", inp))
            + usage.cache_write_tokens * float(price.get("cache_write", inp * 1.25))) / 1e6


def estimate_tokens(text_chars: int) -> int:
    """Conservative input-token estimate: ~3 chars per token (real English is ~4)."""
    return text_chars // 3 + 16


class Meter:
    def __init__(self, cfg: Config, ledger: Path | None = None, events: Path | None = None):
        self.cfg = cfg
        self.ledger = ledger or paths.LEDGER_SPEND
        self.events = events or paths.EVENTS
        self._totals: dict[tuple[str, str], float] | None = None
        self._alerted: set[str] = set()

    # -- totals ---------------------------------------------------------------------------
    def _load(self) -> dict[tuple[str, str], float]:
        if self._totals is None:
            self._totals = {}
            if self.ledger.exists():
                for line in self.ledger.read_text().splitlines():
                    if line.strip():
                        r = json.loads(line)
                        self._add(r["track"], r["ts"], r["usd"])
        return self._totals

    def _add(self, track: str, ts: str, usd: float) -> None:
        t = self._totals
        assert t is not None
        for key in ((track, "day:" + ts[:10]), (track, "month:" + ts[:7])):
            t[key] = t.get(key, 0.0) + usd

    def spent(self, track: str, period: str, now: datetime | None = None) -> float:
        now = now or datetime.now(UTC)
        key = f"day:{now.date().isoformat()}" if period == "day" else f"month:{now:%Y-%m}"
        return self._load().get((track, key), 0.0)

    def global_caps(self, track: str) -> dict[str, float]:
        if track == "social":
            return {"social.day": self.cfg.cap("social.max_usd_per_day"),
                    "social.month": self.cfg.cap("social.max_usd_per_month")}
        return {"day": self.cfg.cap("max_usd_per_day"), "month": self.cfg.cap("max_usd_per_month")}

    # -- enforcement ----------------------------------------------------------------------
    def check(self, est_usd: float, scope: Scope) -> None:
        """Raise BudgetExceeded if est_usd would breach any cap. Called before every call."""
        g = self.global_caps(scope.track)
        for name, limit in g.items():
            period = "day" if name.endswith("day") else "month"
            would = self.spent(scope.track, period) + est_usd
            if would > limit:
                self._event("budget.halt", {"cap": name, "would_be": would, "limit": limit})
                raise BudgetExceeded(name, would, limit)
        for name, limit in scope.caps.items():
            would = scope.spent.get(name, 0.0) + est_usd
            if would > limit:
                self._event("budget.refuse", {"cap": name, "would_be": would, "limit": limit,
                                              "experiment": scope.experiment})
                raise BudgetExceeded(name, would, limit)

    def record(self, scope: Scope, model_id: str, usage: Usage, usd: float, cached: bool,
               latency_s: float = 0.0) -> None:
        ts = datetime.now(UTC).isoformat(timespec="seconds")
        row = {"ts": ts, "track": scope.track, "experiment": scope.experiment,
               "item": scope.item, "model": model_id, "usd": round(usd, 8), "cached": cached,
               "in": usage.input_tokens, "out": usage.output_tokens,
               "cache_read": usage.cache_read_tokens, "provider_usd": usage.provider_usd,
               "latency_s": round(latency_s, 3)}
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger.open("a") as f:
            f.write(json.dumps(row) + "\n")
        self._load()
        self._add(scope.track, ts, usd)
        for name in scope.caps:
            scope.spent[name] = scope.spent.get(name, 0.0) + usd
        self._alerts(scope.track)

    def _alerts(self, track: str) -> None:
        thresholds = self.cfg.budget.get("alerts", [0.5, 0.8])
        for name, limit in self.global_caps(track).items():
            period = "day" if name.endswith("day") else "month"
            frac = self.spent(track, period) / limit if limit else 1.0
            for t in thresholds:
                stamp = datetime.now(UTC).strftime("%Y-%m-%d" if period == "day" else "%Y-%m")
                tag = f"{track}:{name}:{t}:{stamp}"
                if frac >= t and tag not in self._alerted:
                    self._alerted.add(tag)
                    self._event("budget.alert", {"cap": name, "fraction": round(frac, 3),
                                                 "threshold": t})
                    print(f"[budget] {name} at {frac:.0%} of ${limit:.2f}", file=sys.stderr)

    def _event(self, kind: str, data: dict) -> None:
        self.events.parent.mkdir(parents=True, exist_ok=True)
        with self.events.open("a") as f:
            f.write(json.dumps({"ts": time.time(), "type": kind, "data": data}) + "\n")
