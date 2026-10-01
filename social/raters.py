"""Rater registry and weighted ratings (spec §6.4, E17).

Identities and weights are private: the registry lives in social/private/ (gitignored) and
only an anonymous reliability histogram is published. Raters never see their own weight.

Weight = reliability × clout, capped:
- reliability: Beta(2,2)-smoothed accuracy on calibration cases (expert verdict known but
  not shown); domain experts Rex verifies get a floor of 0.8
- clout: 1 + 0.25·log10(followers/1000), clamped to [0.75, 1.5]
- no rater above 5% of a case's total weight; at most 20 counted ratings per rater per day
- ineligible raters (young, automated, few posts, blocklisted, < 3 calibration cases) and
  quarantined bursts are stored but weigh zero
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from lab import paths
from lab.scoring.human import wilson_lower


def private_dir() -> Path:
    d = paths.SOCIAL / "private"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class Rater:
    id: str
    created_at: str | None = None            # account creation date (ISO)
    posts: int = 0
    followers: int = 0
    automated: bool = False
    blocklisted: bool = False
    verified_expert: bool = False
    calib_n: int = 0
    calib_correct: int = 0
    weight_history: list[dict] = field(default_factory=list)


@dataclass
class Rating:
    rater: str
    case: str                                # "<experiment>/<item>"
    vote: int                                # 1 RIGHT, 0 WRONG
    ts: str
    source: str = "reply"                    # reply | page
    calibration: bool = False
    reason: str = ""


def cfg_raters(cfg) -> dict:
    return cfg.scoring["raters"]


# ------------------------------------------------------------------ components
def reliability(r: Rater, prior: tuple[float, float] = (2, 2), expert_floor: float = 0.8
                ) -> float:
    a, b = prior
    rel = (r.calib_correct + a) / (r.calib_n + a + b)
    return max(rel, expert_floor) if r.verified_expert else rel


def clout(followers: int, c: dict) -> float:
    x = 1 + c["slope"] * math.log10(max(followers, 1) / c["base_followers"])
    return min(c["max"], max(c["min"], x))


def eligible(r: Rater, rc: dict, now: datetime) -> tuple[bool, str]:
    e = rc["eligibility"]
    if r.blocklisted:
        return False, "blocklisted"
    if e.get("exclude_automated") and r.automated:
        return False, "automated account"
    if not r.created_at or now - datetime.fromisoformat(r.created_at) < \
            timedelta(days=e["min_account_age_days"]):
        return False, "account too new"
    if r.posts < e["min_posts"]:
        return False, "too few posts"
    if r.calib_n < e["min_calibration_cases"]:
        return False, "too few calibration cases"
    return True, "eligible"


def weight(r: Rater, rc: dict, now: datetime) -> float:
    ok, _ = eligible(r, rc, now)
    if not ok:
        return 0.0
    return reliability(r, tuple(rc["reliability_prior"]), rc["verified_expert_floor"]) * \
        clout(r.followers, rc["clout"])


def cap_shares(ws: dict[str, float], max_share: float) -> tuple[dict[str, float], bool]:
    """Water-filling: lower the largest weights until none exceeds max_share of the total.
    Returns (capped weights, feasible). With fewer than 1/max_share raters it is infeasible;
    weights are equalized and the case can't reach the effective-n threshold anyway."""
    w = {k: v for k, v in ws.items() if v > 0}
    n = len(w)
    if n == 0:
        return {}, True
    if n * max_share < 1:
        m = min(w.values())
        return dict.fromkeys(w, m), False
    for _ in range(100):
        total = sum(w.values())
        limit = max_share * total
        over = {k for k, v in w.items() if v > limit + 1e-12}
        if not over:
            break
        under_sum = sum(v for k, v in w.items() if k not in over)
        # Set capped raters to c with c = max_share * (under_sum + len(over) * c)
        c = max_share * under_sum / (1 - max_share * len(over))
        for k in over:
            w[k] = c
    return w, True


# ------------------------------------------------------------------ registry
class Registry:
    def __init__(self, cfg, root: Path | None = None):
        self.cfg = cfg
        self.rc = cfg_raters(cfg)
        self.dir = root or private_dir()
        self.raters: dict[str, Rater] = {}
        self.ratings: list[Rating] = []
        self.quarantined: set[tuple[str, str]] = set()
        self._load()

    def _load(self) -> None:
        f = self.dir / "raters.json"
        if f.exists():
            for k, v in json.loads(f.read_text()).items():
                self.raters[k] = Rater(**v)
        g = self.dir / "ratings.jsonl"
        if g.exists():
            self.ratings = [Rating(**json.loads(x)) for x in g.read_text().splitlines() if x]
        q = self.dir / "quarantine.json"
        if q.exists():
            self.quarantined = {tuple(x) for x in json.loads(q.read_text())}

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "raters.json").write_text(json.dumps(
            {k: vars(v) for k, v in self.raters.items()}, indent=1))
        (self.dir / "ratings.jsonl").write_text("".join(json.dumps(vars(r)) + "\n"
                                                        for r in self.ratings))
        (self.dir / "quarantine.json").write_text(json.dumps(sorted(self.quarantined)))

    def upsert(self, rid: str, **profile) -> Rater:
        r = self.raters.get(rid) or Rater(rid)
        for k, v in profile.items():
            if hasattr(r, k) and v is not None and k not in ("calib_n", "calib_correct"):
                setattr(r, k, v)
        self.raters[rid] = r
        return r

    def add(self, rating: Rating, gold: str | None = None, panel_verdict: str | None = None
            ) -> Rating:
        """Record a rating. For calibration cases, `gold` and `panel_verdict` say whether
        RIGHT was the correct call, which updates the rater's reliability."""
        self.ratings.append(rating)
        if rating.calibration and gold is not None and panel_verdict is not None:
            r = self.raters.setdefault(rating.rater, Rater(rating.rater))
            truth = 1 if panel_verdict == gold else 0
            r.calib_n += 1
            r.calib_correct += int(rating.vote == truth)
        return rating

    # ---- anti-gaming
    def detect_bursts(self, now: datetime | None = None) -> set[tuple[str, str]]:
        """New raters arriving together on one case are quarantined for review."""
        b = self.rc["burst"]
        now = now or datetime.now(UTC)
        by_case: dict[str, list[Rating]] = defaultdict(list)
        for r in self.ratings:
            if not r.calibration:
                by_case[r.case].append(r)
        found = set()
        for case, rs in by_case.items():
            new = []
            for r in rs:
                rr = self.raters.get(r.rater)
                created = datetime.fromisoformat(rr.created_at) if rr and rr.created_at else now
                ts = datetime.fromisoformat(r.ts)
                if ts - created < timedelta(days=b["new_rater_days"]):
                    new.append((ts, r))
            new.sort(key=lambda x: x[0])
            win = timedelta(minutes=b["window_minutes"])
            j = 0
            for i in range(len(new)):
                while new[i][0] - new[j][0] > win:
                    j += 1
                if i - j + 1 >= b["min_new_raters"]:
                    for _, r in new[j:i + 1]:
                        found.add((r.rater, r.case))
        self.quarantined |= found
        return found

    # ---- weights (recalculated weekly; scores use the latest snapshot)
    def recalc_weights(self, now: datetime | None = None) -> dict[str, float]:
        now = now or datetime.now(UTC)
        out = {}
        for rid, r in self.raters.items():
            w = weight(r, self.rc, now)
            r.weight_history.append({"ts": now.isoformat(timespec="seconds"), "w": round(w, 4)})
            r.weight_history = r.weight_history[-60:]
            out[rid] = w
        return out

    def current_weight(self, rid: str) -> float:
        r = self.raters.get(rid)
        return r.weight_history[-1]["w"] if r and r.weight_history else 0.0

    def over_daily_limit(self) -> set[int]:
        """Indexes of ratings beyond a rater's daily limit (counted across all cases)."""
        per_day: dict[tuple[str, str], int] = defaultdict(int)
        out = set()
        order = sorted(range(len(self.ratings)), key=lambda i: self.ratings[i].ts)
        for i in order:
            r = self.ratings[i]
            if r.calibration:
                continue
            k = (r.rater, r.ts[:10])
            per_day[k] += 1
            if per_day[k] > self.rc["max_ratings_per_day"]:
                out.add(i)
        return out

    def case_score(self, case: str) -> dict:
        """Weighted rater score for one case (spec §6.4)."""
        excluded = self.over_daily_limit()
        latest: dict[str, Rating] = {}
        for i in sorted(range(len(self.ratings)), key=lambda i: self.ratings[i].ts):
            r = self.ratings[i]
            if r.case != case or r.calibration or i in excluded:
                continue
            latest[r.rater] = r                           # a rater's last word counts once
        ws = {rid: (0.0 if (rid, case) in self.quarantined else self.current_weight(rid))
              for rid in latest}
        capped, feasible = cap_shares(ws, self.rc["max_share_per_case"])
        sw = sum(capped.values())
        sw2 = sum(v * v for v in capped.values())
        n_eff = sw * sw / sw2 if sw2 else 0.0
        score = sum(capped[k] * latest[k].vote for k in capped) / sw if sw else None
        counts = n_eff >= self.rc["min_effective_n"] and feasible
        return {"case": case, "n_ratings": len(latest), "n_weighted": len(capped),
                "score": score, "n_eff": round(n_eff, 2),
                "wilson": wilson_lower(score * n_eff, n_eff) if score is not None else None,
                "counts": counts, "cap_feasible": feasible,
                "max_share": max(capped.values()) / sw if sw else 0.0,
                "wrong_from_reliable": sum(1 for k in capped if latest[k].vote == 0
                                           and self.reliability_of(k) >= 0.75)}

    def reliability_of(self, rid: str) -> float:
        r = self.raters.get(rid)
        return reliability(r, tuple(self.rc["reliability_prior"]),
                           self.rc["verified_expert_floor"]) if r else 0.5

    def public_summary(self) -> dict:
        """Distribution of reliability among eligible raters. No identities."""
        now = datetime.now(UTC)
        rel = [self.reliability_of(k) for k, r in self.raters.items()
               if eligible(r, self.rc, now)[0]]
        bins = [0] * 10
        for x in rel:
            bins[min(int(x * 10), 9)] += 1
        return {"eligible_raters": len(rel), "total_raters": len(self.raters),
                "reliability_histogram": bins}


def parse_structured(text: str) -> tuple[int, str] | None:
    """'RIGHT ...' / 'WRONG ...' at the start of a reply (after any @-prefixes X adds)."""
    t = text.strip()
    while t.startswith("@"):
        t = t.split(None, 1)[1] if " " in t else ""
    head = t[:6].upper()
    if head.startswith("RIGHT"):
        return 1, t[5:].strip(" :-—,.")[:300]
    if head.startswith("WRONG"):
        return 0, t[5:].strip(" :-—,.")[:300]
    return None
