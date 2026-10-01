"""The orchestrator: plain code, the judge (spec §3, §7).

    uv run python -m lab.orchestrator.loop            # run cycles until STOP or budget
    uv run python -m lab.orchestrator.loop --once     # one cycle

One cycle: snapshot → experimenter proposes one experiment → revert locked-path edits →
validate → estimate → dev run → gate → holdout + bootstrap → promotion rule → results,
summary, leaderboard → learning → interesting cases → heartbeat. Agents propose; this
module decides. It never shows the holdout to the experimenter.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

import yaml

from lab import paths
from lab.clients.meter import BudgetExceeded, Scope
from lab.config import Config, LabNotReady
from lab.orchestrator import learnings, locks, promote
from lab.protocols.engine import Engine
from lab.protocols.estimate import estimate
from lab.protocols.runner import run_protocol
from lab.protocols.schema import InvalidProtocol, load_protocol, models_used
from lab.scoring import leaderboard
from lab.scoring.score import compare, score

EXP_RE = re.compile(r"^E-(\d{4})$")
HOLDOUT_LOG = "holdout_evals.jsonl"


class Experimenter(Protocol):
    def propose(self, exp_id: str, exp_dir: Path, context: dict) -> None:
        """Write proposal.md and protocol.yaml (and optional run.yaml) into exp_dir."""


@dataclass
class Data:
    """Item access. Holdout items arrive only through lab.orchestrator.holdout."""
    dev: list[dict]
    holdout_loader: object = None          # callable -> list[dict]
    post_cutoff: str | None = None         # items dated after this are the post-cutoff slice

    def holdout(self) -> list[dict]:
        if self.holdout_loader is None:
            from lab.orchestrator import holdout
            return holdout.load() if holdout.exists() else []
        return self.holdout_loader()  # type: ignore[operator]


@dataclass
class Orchestrator:
    cfg: Config
    engine: Engine
    experimenter: Experimenter
    data: Data
    root: Path = field(default_factory=lambda: paths.ROOT)
    workers: int = 4
    resamples: int | None = None
    commit: bool = False                     # git-commit outputs at the end of each cycle
    constraint: dict | None = None           # zone refinement run (lab.zones.refine)
    log: list[str] = field(default_factory=list)
    _zone_snapshot: object = None

    # ------------------------------------------------------------------ paths and state
    @property
    def exp_root(self) -> Path:
        return self.root / "experiments"

    def next_exp_id(self) -> str:
        nums = [int(m.group(1)) for p in self.exp_root.glob("E-*")
                if (m := EXP_RE.match(p.name))]
        return f"E-{max(nums, default=0) + 1:04d}"

    def results(self) -> list[dict]:
        return leaderboard.load_results(self.exp_root)

    def champion(self) -> tuple[str | None, dict | None]:
        """(protocol id, its committed protocol dict) of the current champion."""
        champ_id, proto = None, None
        for r in self.results():
            if r.get("status") == "promoted":
                champ_id = r["protocol"]
                proto = yaml.safe_load((self.exp_root / r["experiment"] / "protocol.yaml")
                                       .read_text())
        return champ_id, proto

    def emit(self, kind: str, **data) -> None:
        paths.EVENTS.parent.mkdir(parents=True, exist_ok=True)
        with paths.EVENTS.open("a") as f:
            f.write(json.dumps({"ts": time.time(), "type": kind, "actor": "orchestrator",
                                "data": data}) + "\n")
        self.log.append(f"{kind} {data}")

    def heartbeat(self, state: str, **extra) -> None:
        from harness.health import beat
        if getattr(self, "pulse", None) is not None:
            self.pulse.state, self.pulse.extra = state, extra
        beat("orchestrator", state, **extra)

    # ------------------------------------------------------------------ holdout budget
    def holdout_evals_this_week(self) -> int:
        f = paths.OPS / HOLDOUT_LOG
        if not f.exists():
            return 0
        week_ago = datetime.now(UTC) - timedelta(days=7)
        return sum(1 for ln in f.read_text().splitlines() if ln.strip()
                   and datetime.fromisoformat(json.loads(ln)["ts"]) > week_ago)

    def holdout_evals_left(self) -> int:
        return int(self.cfg.budget.get("holdout_evals_per_week", 10)) - \
            self.holdout_evals_this_week()

    def use_holdout_eval(self, exp_id: str, protocol: str) -> None:
        f = paths.OPS / HOLDOUT_LOG
        f.parent.mkdir(parents=True, exist_ok=True)
        with f.open("a") as fh:
            fh.write(json.dumps({"ts": datetime.now(UTC).isoformat(), "experiment": exp_id,
                                 "protocol": protocol}) + "\n")

    # ------------------------------------------------------------------ context for agent
    def context(self) -> dict:
        lb = leaderboard.build(self.results())
        meter = self.engine.gw.meter
        rows = learnings.load()
        open_reviews = len(list((paths.QUEUE).glob("R-*.json")))
        return {
            "steering": (self.root / "STEERING.md").read_text()
            if (self.root / "STEERING.md").exists() else "",
            "learnings_top": [r for r in rows if r["status"] != "superseded"][-25:],
            "leaderboard": {"champion": lb["champion"],
                            "rows": [{k: r.get(k) for k in ("protocol", "dev_macro_f1",
                                                            "usd_per_item", "status", "zone")}
                                     for r in lb["rows"]][:25]},
            "open_review_items": open_reviews,
            "budget_remaining_today": self.cfg.cap("max_usd_per_day") - meter.spent("lab", "day"),
            "max_usd_per_experiment": self.cfg.cap("max_usd_per_experiment"),
            "dev_items": len(self.data.dev),
            "holdout_evals_left_this_week": self.holdout_evals_left(),
            "refinement": self._refinement_context(),
        }

    def _refinement_context(self) -> dict | None:
        if not self.constraint:
            return None
        from lab import zones
        z = zones.load(self.constraint["zone"])
        b = zones.board(z.id, self.results(), z)
        return {"zone": z.id, "name": z.name, "knobs": z.knobs,
                "sub_techniques": {k: v["id"] for k, v in z.subs.items()},
                "best": b.get("best"), "rows": b.get("rows", [])[:10],
                "budget_left": self.constraint["budget"] - self.constraint.get("spent", 0.0),
                "steer": self.constraint.get("steer", ""),
                "rule": "Propose one of this zone's sub-technique templates with only its knobs "
                        "changed, inside knobs.yaml ranges. Dev split only."}

    # ------------------------------------------------------------------ proposal parsing
    @staticmethod
    def parse_proposal(text: str) -> dict:
        def field_(name: str) -> str:
            m = re.search(rf"^\*?\*?{name}\*?\*?\s*:\s*(.+)$", text, re.M | re.I)
            if m:
                return m.group(1).strip()
            m = re.search(rf"^#+\s*{name}\s*\n+(.+?)(?=\n\s*\n|\n#|\Z)", text,
                          re.M | re.I | re.S)
            return m.group(1).strip() if m else ""
        builds = re.findall(r"\bL-\d{4}\b", field_("builds on") or text)
        cites_steering = bool(re.search(r"steering", field_("builds on"), re.I))
        track = field_("track").upper()[:1] or "A"
        return {"hypothesis": field_("hypothesis"), "builds_on": sorted(set(builds)),
                "cites_steering": cites_steering, "track": track,
                "zone": (field_("zone").split() or [None])[0],
                "expected": field_("expected effect"), "next": field_("next")}

    def validate_proposal(self, prop: dict, n_learnings: int) -> list[str]:
        problems = []
        if not prop["hypothesis"]:
            problems.append("proposal has no Hypothesis")
        if n_learnings and not prop["builds_on"] and not prop["cites_steering"]:
            problems.append("hypothesis must cite a learning (L-NNNN) or STEERING.md")
        if n_learnings == 0 and not prop["builds_on"] and not prop["cites_steering"]:
            problems.append("hypothesis must cite STEERING.md while there are no learnings yet")
        return problems

    # ------------------------------------------------------------------ the cycle
    def cycle(self) -> dict:
        if paths.STOP.exists():
            self.emit("stop", reason="ops/STOP present")
            return {"status": "stopped"}
        self.cfg.require_ready([])
        exp_id = self.next_exp_id()
        exp_dir = self.exp_root / exp_id
        exp_dir.mkdir(parents=True)
        self.heartbeat("proposing", experiment=exp_id)
        self.emit("cycle.start", experiment=exp_id)

        head, dirty = locks.snapshot(self.root) if (self.root / ".git").exists() else ("", set())
        if self.constraint:
            from lab import zones
            # Freeze the zone before the experimenter runs, so it can't widen its own knobs.
            self._zone_snapshot = zones.load(self.constraint["zone"])
        self.experimenter.propose(exp_id, exp_dir, self.context())
        if head:
            deny = ["zones/**"] if self.constraint else None
            reverted = locks.enforce(self.root, head, extra_allowed=[f"experiments/{exp_id}/**"],
                                     ignore=dirty, deny=deny)
            if reverted:
                self.emit("locks.reverted", experiment=exp_id, paths=reverted)
                (exp_dir / "reverted.txt").write_text("\n".join(reverted) + "\n")
        try:
            return self._evaluate(exp_id, exp_dir)
        finally:
            self.heartbeat("idle", last=exp_id)

    def _finish(self, exp_id: str, exp_dir: Path, result: dict, prop: dict) -> dict:
        result.setdefault("experiment", exp_id)
        result.setdefault("created", datetime.now(UTC).isoformat(timespec="seconds"))
        (exp_dir / "results.json").write_text(json.dumps(result, indent=2, sort_keys=True))
        (exp_dir / "summary.md").write_text(summary_md(result, prop))
        leaderboard.write(self.exp_root)
        entry = learnings.append(learnings.from_result(result, prop))
        learnings.merge_proposals()
        self._weekly_consolidation()
        learnings.write_markdown()
        (self.exp_root / "hitrate.json").write_text(json.dumps(
            learnings.hit_rate(self.results()), indent=1))
        self.emit("cycle.end", experiment=exp_id, status=result["status"], learning=entry["id"])
        if self.commit:
            self._git_commit(f"{exp_id}: {result['protocol']} → {result['status']}")
        return result

    def _evaluate(self, exp_id: str, exp_dir: Path) -> dict:
        base = {"experiment": exp_id, "protocol": "?", "track": "A"}
        prop_path, proto_path = exp_dir / "proposal.md", exp_dir / "protocol.yaml"
        prop = self.parse_proposal(prop_path.read_text()) if prop_path.exists() else {}
        problems = [] if prop_path.exists() else ["missing proposal.md"]
        if not proto_path.exists():
            problems.append("missing protocol.yaml")
        if prop:
            problems += self.validate_proposal(prop, len(learnings.load()))
        protocol = None
        if not problems:
            try:
                protocol = load_protocol(proto_path, set(self.cfg.models["models"]))
                base["protocol"] = protocol["id"]
            except (InvalidProtocol, yaml.YAMLError) as e:
                problems.append(str(e))
        if problems:
            return self._finish(exp_id, exp_dir, {**base, "status": "invalid",
                                                  "reason": "; ".join(problems)}, prop or {})
        assert protocol is not None
        base.update(protocol=protocol["id"], zone=prop.get("zone") or _zone(protocol),
                    paper=protocol.get("paper"), tags=protocol.get("tags", []),
                    track=prop.get("track", "A"))
        if self.constraint:
            from lab import zones
            sub, zproblems = zones.check_refinement(protocol, self._zone_snapshot)
            base["zone"] = self.constraint["zone"]
            base["refinement"] = {"zone": self.constraint["zone"], "sub": sub}
            if zproblems:
                return self._finish(exp_id, exp_dir, {**base, "status": "invalid",
                                                      "reason": "; ".join(zproblems)}, prop)
        try:
            self.cfg.require_ready(models_used(protocol))
        except LabNotReady as e:
            return self._finish(exp_id, exp_dir, {**base, "status": "invalid",
                                                  "reason": str(e)}, prop)

        # --- items and estimate (§7.1 step 3)
        run_cfg = yaml.safe_load((exp_dir / "run.yaml").read_text()) \
            if (exp_dir / "run.yaml").exists() else {}
        dev = self.select_dev(run_cfg)
        est = estimate(protocol, self.cfg)
        n_hold = len(self.data.holdout()) if self.holdout_evals_left() > 0 else 0
        dev_cost = est.total(len(dev))
        champ_id, champ_proto = self.champion()
        champ_dev_cost = estimate(champ_proto, self.cfg).total(len(dev)) \
            if champ_proto and champ_proto["id"] != protocol["id"] else 0.0
        exp_cap = self.cfg.cap("max_usd_per_experiment")
        day_left = self.cfg.cap("max_usd_per_day") - self.engine.gw.meter.spent("lab", "day")
        base["estimate"] = {"per_item_expected": round(est.expected_usd, 5),
                            "per_item_worst": round(est.worst_usd, 5), "dev_items": len(dev),
                            "dev_usd": round(dev_cost, 4),
                            "holdout_usd_if_gated": round(est.total(n_hold), 4)}
        print(f"[estimate] {exp_id} {protocol['id']}: {len(dev)} dev items × "
              f"${est.expected_usd:.4f} = ${dev_cost:.2f} (cap ${exp_cap:.2f}, "
              f"day left ${day_left:.2f})", file=sys.stderr)
        if dev_cost + champ_dev_cost > exp_cap or dev_cost + champ_dev_cost > day_left:
            reason = (f"estimated dev cost ${dev_cost + champ_dev_cost:.2f} exceeds "
                      f"{'experiment cap' if dev_cost > exp_cap else 'remaining daily budget'};"
                      " shrink it (fewer items via run.yaml n, cheaper models, fewer rounds)")
            return self._finish(exp_id, exp_dir, {**base, "status": "rejected_budget",
                                                  "reason": reason}, prop)

        # --- dev run (§7.1 step 4)
        caps = {"experiment": exp_cap}
        if self.constraint:
            caps["refinement"] = max(0.0, self.constraint["budget"] -
                                     self.constraint.get("spent", 0.0))
        scope = Scope(experiment=exp_id, caps=caps)
        self.heartbeat("dev", experiment=exp_id, protocol=protocol["id"])
        try:
            dev_ts = run_protocol(self.engine, protocol, dev, scope, exp_id, self.workers,
                                  runs_root=self.root / "runs")
            dev_score = score(dev_ts)
            base["dev"] = dev_score
            # Champion on the same items (cached when it has run them before).
            champ_dev = None
            if champ_proto and champ_proto["id"] != protocol["id"]:
                champ_dev_ts = run_protocol(self.engine, champ_proto, dev, scope,
                                            f"{exp_id}-champion", self.workers, write=False)
                champ_dev = score(champ_dev_ts)
                base["champion_dev"] = {"protocol": champ_id, "macro_f1": champ_dev["macro_f1"]}
                base["vs_champion_dev"] = compare(dev_ts, champ_dev_ts,
                                                  resamples=self._resamples(), seed=self._seed())
        except BudgetExceeded as e:
            return self._finish(exp_id, exp_dir, {**base, "status": "halted_budget",
                                                  "reason": str(e)}, prop)
        base["cases"] = interesting_cases(dev_ts)
        base["champion_before"] = champ_id
        if self.constraint and self.constraint.get("dev_only"):
            return self._finish(exp_id, exp_dir, {**base, "status": "dev_only",
                                                  "reason": "zone refinement run (dev only)"},
                                prop)

        # --- gate to holdout (§7.1 step 5)
        margin = self.cfg.scoring["promotion"]["holdout_gate_margin"]
        if champ_dev is not None and dev_score["macro_f1"] < champ_dev["macro_f1"] - margin:
            return self._finish(exp_id, exp_dir, {**base, "status": "stopped_at_dev",
                                                  "reason": "dev macro-F1 "
                                                  f"{dev_score['macro_f1']:.3f}"
                                                  f" < champion {champ_dev['macro_f1']:.3f} − "
                                                  f"{margin}"}, prop)
        if champ_id == protocol["id"]:
            return self._finish(exp_id, exp_dir, {**base, "status": "not_promoted",
                                                  "reason": "already champion"}, prop)
        if self.holdout_evals_left() <= 0:
            return self._finish(exp_id, exp_dir, {**base, "status": "stopped_at_dev",
                                                  "reason": "weekly holdout evaluation budget "
                                                            "used up"}, prop)
        holdout_items = self.data.holdout()
        if not holdout_items:
            return self._finish(exp_id, exp_dir, {**base, "status": "stopped_at_dev",
                                                  "reason": "no holdout available"}, prop)
        hold_est = est.total(len(holdout_items))
        if champ_proto and not self._champion_holdout_cached(champ_id, len(holdout_items)):
            hold_est += estimate(champ_proto, self.cfg).total(len(holdout_items))
        if scope.spent.get("experiment", 0) + hold_est > exp_cap:
            return self._finish(exp_id, exp_dir, {**base, "status": "stopped_at_dev",
                                                  "reason": f"holdout estimate ${hold_est:.2f} "
                                                            "would exceed the experiment cap"},
                                prop)

        # --- holdout + bootstrap (§6.2)
        self.use_holdout_eval(exp_id, protocol["id"])
        self.heartbeat("holdout", experiment=exp_id, protocol=protocol["id"])
        try:
            cand = self._holdout_block(protocol, holdout_items, scope, exp_id)
            champ_block, vs = None, None
            if champ_proto:
                champ_block = self._holdout_block(champ_proto, holdout_items, scope,
                                                  f"{exp_id}-champion")
                vs = compare(cand["_ts"], champ_block["_ts"], resamples=self._resamples(),
                             seed=self._seed())
        except BudgetExceeded as e:
            return self._finish(exp_id, exp_dir, {**base, "status": "halted_budget",
                                                  "reason": str(e)}, prop)
        decision = promote.decide(cand, champ_block, vs, self.cfg)
        base["holdout"] = {k: v for k, v in cand.items() if k != "_ts"}
        if champ_block:
            base["champion_holdout"] = {k: v for k, v in champ_block.items() if k != "_ts"}
        base["vs_champion"] = vs
        if vs:
            base["vs_champion"]["verdict"] = decision.label
        base["status"] = decision.status
        base["reason"] = "; ".join(decision.reasons)
        self.emit("decision", experiment=exp_id, protocol=protocol["id"],
                  status=decision.status, label=decision.label)
        return self._finish(exp_id, exp_dir, base, prop)

    def _holdout_block(self, protocol: dict, items: list[dict], scope: Scope,
                       exp_id: str) -> dict:
        ts = run_protocol(self.engine, protocol, items, scope, exp_id, self.workers)
        post_ids = {it["id"] for it in items
                    if self.data.post_cutoff and it.get("date")
                    and it["date"] > self.data.post_cutoff}
        post = [t for t in ts if t["item"] in post_ids]
        # Only aggregate numbers leave this function; transcripts stay outside the repo.
        return {"full": score(ts), "post_cutoff": score(post) if post else None, "_ts": ts}

    def _champion_holdout_cached(self, champ_id: str | None, n: int) -> bool:
        """The champion's holdout responses are cached if it was evaluated on this holdout."""
        return any(r.get("protocol") == champ_id and
                   ((r.get("holdout") or {}).get("full") or {}).get("n") == n
                   for r in self.results())

    def _weekly_consolidation(self) -> None:
        stamp = paths.OPS / "last_consolidation.txt"
        last = datetime.fromisoformat(stamp.read_text().strip()) if stamp.exists() else None
        now = datetime.now(UTC)
        if last is None:
            stamp.parent.mkdir(parents=True, exist_ok=True)
            stamp.write_text(now.isoformat())
        elif now - last > timedelta(days=7):
            self.emit("learnings.consolidated", **learnings.consolidate())
            stamp.write_text(now.isoformat())

    def _resamples(self) -> int:
        return self.resamples or self.cfg.scoring["promotion"]["bootstrap_resamples"]

    def _seed(self) -> int:
        return int(self.cfg.scoring["promotion"]["seed"])

    def select_dev(self, run_cfg: dict) -> list[dict]:
        n = run_cfg.get("n")
        items = list(self.data.dev)
        if n and n < len(items):
            rnd = random.Random(run_cfg.get("seed", 0))
            items = rnd.sample(items, n)
        return items

    def _git_commit(self, msg: str) -> None:
        import subprocess
        subprocess.run(["git", "add", "experiments", "learnings", "LEARNINGS.md", "ops/spend.jsonl",
                        "ops/holdout_evals.jsonl"], cwd=self.root, capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", msg], cwd=self.root, capture_output=True)

    # ------------------------------------------------------------------ main loop
    def run(self, max_cycles: int | None = None) -> None:
        n = 0
        while max_cycles is None or n < max_cycles:
            if paths.STOP.exists():
                self.emit("stop", reason="ops/STOP present")
                break
            from lab.orchestrator import jobs
            for job in jobs.pending():          # dashboard runs go first
                jobs.run_job(self, job)
            try:
                r = self.cycle()
            except BudgetExceeded as e:
                self.emit("budget.halt", reason=str(e))
                break
            if r.get("status") == "halted_budget":
                break
            n += 1


def _zone(protocol: dict) -> str | None:
    for t in protocol.get("tags", []):
        if re.fullmatch(r"z\d", t):
            return t.upper()
    return None


def interesting_cases(ts: list[dict], k: int = 8) -> list[dict]:
    """Cases worth a replay (spec §7.1 step 8): wrong at high confidence, split panels,
    correct after disagreement."""
    scored = []
    for t in ts:
        why = []
        if t.get("gold") and t["verdict"] != t["gold"] and t["confidence"] >= 0.8:
            why.append("confidently wrong")
        if t.get("agreement") and min(t["agreement"]) < 0.6:
            why.append("panel split")
            if t.get("gold") and t["verdict"] == t["gold"]:
                why.append("resolved correctly")
        if t.get("gold") and t["verdict"] == t["gold"] and t["confidence"] >= 0.9:
            why.append("high confidence")
        if why:
            scored.append({"item": t["item"], "why": why})
    scored.sort(key=lambda c: -len(c["why"]))
    return scored[:k]


def summary_md(r: dict, prop: dict) -> str:
    lines = [f"# {r['experiment']} · {r.get('protocol', '?')}", "",
             f"**Status:** {r['status']}" + (f": {r['reason']}" if r.get("reason") else ""), ""]
    if prop.get("hypothesis"):
        lines += [f"**Hypothesis:** {prop['hypothesis']}",
                  f"**Builds on:** {', '.join(prop.get('builds_on') or []) or 'STEERING.md'}", ""]
    if r.get("estimate"):
        e = r["estimate"]
        lines.append(f"**Estimate:** {e['dev_items']} dev items × ${e['per_item_expected']:.4f}"
                     f" = ${e['dev_usd']:.2f}")
    d = r.get("dev")
    if d and d.get("n"):
        lines += ["", "| split | n | macro-F1 | accuracy | ECE | $/item |",
                  "|---|---|---|---|---|---|",
                  f"| dev | {d['n']} | {d['macro_f1']:.3f} | {d['accuracy']:.3f} | {d['ece']:.3f}"
                  f" | {d['cost']['usd_per_item_uncached']:.4f} |"]
        h = (r.get("holdout") or {}).get("full")
        if h:
            lines.append(f"| holdout | {h['n']} | {h['macro_f1']:.3f} | {h['accuracy']:.3f} | "
                         f"{h['ece']:.3f} | {h['cost']['usd_per_item_uncached']:.4f} |")
            pc = r["holdout"].get("post_cutoff")
            if pc:
                lines.append(f"| post-cutoff | {pc['n']} | {pc['macro_f1']:.3f} | "
                             f"{pc['accuracy']:.3f} | {pc['ece']:.3f} | |")
    vs = r.get("vs_champion")
    if vs:
        lines += ["", f"**vs champion ({r.get('champion_before')}):** {vs['diff']:+.3f} macro-F1,"
                      f" 95% CI [{vs['ci'][0]:+.3f}, {vs['ci'][1]:+.3f}] → {vs['verdict']}"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--cycles", type=int)
    ap.add_argument("--no-commit", action="store_true")
    args = ap.parse_args(argv)
    from harness.health import Pulse
    from lab.experimenter.claude import ClaudeExperimenter
    from lab.orchestrator.factory import build
    with Pulse("orchestrator") as pulse:
        orch = build(ClaudeExperimenter(), commit=not args.no_commit)
        orch.pulse = pulse
        orch.run(1 if args.once else args.cycles)
        if not args.once and args.cycles is None:
            # Event-driven: when budget or STOP ends the loop, stay alive (heartbeat green,
            # state "waiting") so the dashboard queue can still be served tomorrow.
            import time

            from lab.orchestrator import jobs
            while not paths.STOP.exists():
                pulse.state = "waiting"
                for job in jobs.pending():
                    jobs.run_job(orch, job)
                time.sleep(30)
    return 0


if __name__ == "__main__":
    sys.exit(main())
