"""Season 0 (spec §5.3): reproduce the library papers in fact-checking.

    uv run python -m lab.season0 plan        # configurations × items × $/item vs the caps
    uv run python -m lab.season0 screen      # all configurations on the same dev items
    uv run python -m lab.season0 holdout     # finalists + their controls on the holdout
    uv run python -m lab.season0 scorecard   # the replication scorecard

The full run is GATE G-004: Rex approves the Season 0 budget and the cards' faithfulness
notes first. `screen` and `holdout` refuse to run until ops/queue/G-004 is closed
(library/season0.approved exists).
"""

from __future__ import annotations

import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from lab import paths
from lab.clients.meter import Scope
from lab.config import Config
from lab.protocols.engine import Engine
from lab.protocols.estimate import estimate
from lab.protocols.runner import run_protocol
from lab.protocols.schema import load_protocol
from lab.scoring.score import compare, score

PLAN = paths.ROOT / "library" / "season0.yaml"
APPROVED = paths.ROOT / "library" / "season0.approved"
LIBRARY = paths.ROOT / "lab" / "protocols" / "library"


def out_dir() -> Path:
    return paths.EXPERIMENTS / "season0"


def load_plan(path: Path | None = None) -> dict:
    return yaml.safe_load((path or PLAN).read_text())


def find_protocol(pid: str, known: set[str] | None = None) -> dict:
    for d in (LIBRARY, LIBRARY / "seed"):
        f = d / f"{pid}.yaml"
        if f.exists():
            return load_protocol(f, known)
    raise FileNotFoundError(f"protocol {pid!r} not in the library")


def configs(plan: dict) -> list[str]:
    ids: list[str] = []
    for t in plan["tests"]:
        for pid in [t["protocol"], t["control"]] + [x.get("protocol", t["protocol"])
                                                    for x in t.get("also", [])] + \
                [x["control"] for x in t.get("also", [])]:
            if pid not in ids:
                ids.append(pid)
    for pid in plan.get("extra_configs", []):
        if pid not in ids:
            ids.append(pid)
    return ids


def controls(plan: dict) -> set[str]:
    out = set()
    for t in plan["tests"]:
        out.add(t["control"])
        out |= {x["control"] for x in t.get("also", [])}
    return out


@dataclass
class PlanRow:
    protocol: str
    calls: int
    per_item: float
    screening: float


def plan_estimate(cfg: Config, plan: dict, n_holdout: int) -> dict:
    known = set(cfg.models["models"])
    rows = []
    for pid in configs(plan):
        e = estimate(find_protocol(pid, known), cfg)
        rows.append(PlanRow(pid, e.calls, e.expected_usd, e.total(plan["screening_items"])))
    screening = sum(r.screening for r in rows)
    # Holdout upper bound: the most expensive finalists plus every control.
    tests = sorted((r for r in rows if r.protocol not in controls(plan)),
                   key=lambda r: -r.per_item)[: plan["finalists"]]
    ctl = [r for r in rows if r.protocol in controls(plan)]
    holdout = sum(r.per_item for r in tests + ctl) * n_holdout
    caps = {"screening": cfg.cap("season0.max_usd_screening"),
            "holdout": cfg.cap("season0.max_usd_holdout")}
    return {"rows": rows, "screening_usd": screening, "holdout_usd_max": holdout,
            "n_holdout": n_holdout, "caps": caps,
            "ok": screening <= caps["screening"] and holdout <= caps["holdout"]}


def print_plan(p: dict, out=sys.stdout) -> None:
    print(f"{'configuration':32} {'calls':>5} {'$/item':>8} {'screen $':>9}", file=out)
    for r in sorted(p["rows"], key=lambda r: -r.per_item):
        print(f"{r.protocol:32} {r.calls:5} {r.per_item:8.4f} {r.screening:9.2f}", file=out)
    n = len(p["rows"])
    print(f"\n{n} configurations × screening items: ${p['screening_usd']:.2f} "
          f"(cap ${p['caps']['screening']:.2f})", file=out)
    print(f"holdout, finalists + controls × {p['n_holdout']} items, at most: "
          f"${p['holdout_usd_max']:.2f} (cap ${p['caps']['holdout']:.2f})", file=out)
    print("WITHIN CAPS" if p["ok"] else "OVER CAP: Season 0 will not start", file=out)


def screening_items(dev: list[dict], plan: dict) -> list[dict]:
    rnd = random.Random(plan.get("screening_seed", 0))
    n = plan["screening_items"]
    return rnd.sample(dev, n) if n < len(dev) else list(dev)


def run_stage(engine: Engine, cfg: Config, plan: dict, items: list[dict], stage: str,
              pids: list[str], cap: float, runs_root: Path | None = None
              ) -> dict[str, list[dict]]:
    known = set(cfg.models["models"])
    scope = Scope(experiment=f"S0-{stage}", caps={f"season0.{stage}": cap})
    out = {}
    for pid in pids:
        out[pid] = run_protocol(engine, find_protocol(pid, known), items, scope,
                                f"S0-{stage}-{pid}", runs_root=runs_root)
    return out


def judge(expect: str, ci: list[float], sesoi: float) -> str:
    lo, hi = ci
    if expect == "better":
        return "replicated" if lo > 0 else "not replicated" if hi < sesoi else "unclear"
    if expect == "not_worse":
        return "replicated" if lo > -sesoi else "not replicated" if hi < 0 else "unclear"
    if expect == "no_effect":
        if -sesoi < lo and hi < sesoi:
            return "replicated"
        return "not replicated" if lo > 0 or hi < 0 else "unclear"
    raise ValueError(expect)


def scorecard(plan: dict, screen: dict[str, list[dict]], hold: dict[str, list[dict]],
              resamples: int = 10_000, seed: int = 20261001) -> list[dict]:
    rows = []
    sesoi = plan.get("sesoi", 0.02)
    for t in plan["tests"]:
        checks = [{"protocol": t["protocol"], "control": t["control"], "expect": t["expect"]}]
        checks += [{"protocol": x.get("protocol", t["protocol"]), "control": x["control"],
                    "expect": x["expect"]} for x in t.get("also", [])]
        results = []
        for c in checks:
            src = hold if c["protocol"] in hold and c["control"] in hold else screen
            if c["protocol"] not in src or c["control"] not in src:
                results.append({**c, "verdict": "not run"})
                continue
            cmp = compare(src[c["protocol"]], src[c["control"]], resamples, seed)
            cost = sum(x.get("usd_uncached", x["usd"]) for x in src[c["protocol"]]) + \
                sum(x.get("usd_uncached", x["usd"]) for x in src[c["control"]])
            results.append({**c, "split": "holdout" if src is hold else "dev screen",
                            "n": cmp["n"], "diff": cmp["diff"], "ci": cmp["ci"],
                            "verdict": judge(c["expect"], cmp["ci"], sesoi),
                            "cost_usd": round(cost, 4),
                            "protocol_score": score(src[c["protocol"]]).get("macro_f1"),
                            "control_score": score(src[c["control"]]).get("macro_f1")})
        main = results[0]
        overall = main["verdict"]
        if t["paper"].startswith("08-") and len(results) > 1:
            # Smit: replicated only if untuned debate shows no effect AND tuning helps.
            tuned = [r["verdict"] for r in results[1:]]
            overall = ("replicated" if main["verdict"] == "replicated" and "replicated" in tuned
                       else "not replicated" if main["verdict"] == "not replicated"
                       else "unclear")
        rows.append({"paper": t["paper"], "claim": t["claim"], "verdict": overall,
                     "tests": results, "card": f"library/cards/{t['paper']}.md"})
    return rows


def scorecard_md(rows: list[dict]) -> str:
    out = ["# Season 0 replication scorecard", "",
           "Did each paper's headline finding hold up in fact-checking? Each test compares a "
           "protocol with its control on the same items (paired bootstrap, 95% CI on the "
           "macro-F1 difference). 'Unclear' means the interval is too wide to say.", "",
           "| Paper | Claim | Protocol vs control | Δ macro-F1 [95% CI] | Split | Verdict | Cost |",
           "|---|---|---|---|---|---|---|"]
    for r in rows:
        m = r["tests"][0]
        if m.get("ci"):
            d = f"{m['diff']:+.3f} [{m['ci'][0]:+.3f}, {m['ci'][1]:+.3f}]"
        else:
            d = "–"
        out.append(f"| [{r['paper'][:2]}]({r['card']}) | {r['claim']} | {m['protocol']} vs "
                   f"{m['control']} | {d} | {m.get('split', '–')} | **{r['verdict']}** | "
                   f"${m.get('cost_usd', 0):.2f} |")
    return "\n".join(out) + "\n"


def _engine_and_data():
    from lab.data.build import DEV, model_cutoff  # noqa: F401
    from lab.data.schema import read_jsonl
    from lab.orchestrator.factory import build

    class _Nop:
        def propose(self, *a):
            raise RuntimeError("Season 0 has no experimenter")
    orch = build(_Nop(), commit=False)
    return orch, list(read_jsonl(DEV))


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "plan"
    plan = load_plan()
    od = out_dir()
    od.mkdir(parents=True, exist_ok=True)
    if cmd == "plan":
        from lab.config import get
        from lab.orchestrator import holdout
        n_hold = len(holdout.load()) if holdout.exists() else 500
        p = plan_estimate(get(), plan, n_hold)
        print_plan(p)
        return 0 if p["ok"] else 3
    if cmd in ("screen", "holdout") and not APPROVED.exists():
        print("Season 0 needs Rex's approval (ops/queue/G-004).", file=sys.stderr)
        return 2
    orch, dev = _engine_and_data()
    cfg = orch.cfg
    if cmd == "screen":
        p = plan_estimate(cfg, plan, len(orch.data.holdout()) or 500)
        print_plan(p, sys.stderr)
        if not p["ok"]:
            return 3
        res = run_stage(orch.engine, cfg, plan, screening_items(dev, plan), "screen",
                        configs(plan), cfg.cap("season0.max_usd_screening"))
        (od / "screen.json").write_text(json.dumps(
            {pid: score(ts) for pid, ts in res.items()}, indent=2, sort_keys=True))
        return 0
    if cmd == "holdout":
        scr = json.loads((od / "screen.json").read_text())
        ctl = controls(plan)
        finalists = sorted((p for p in scr if p not in ctl),
                           key=lambda p: -scr[p].get("macro_f1", 0))[: plan["finalists"]]
        needed = list(finalists)
        for t in plan["tests"]:
            if t["protocol"] in finalists and t["control"] not in needed:
                needed.append(t["control"])
        orch.use_holdout_eval("season0", ",".join(needed))
        res = run_stage(orch.engine, cfg, plan, orch.data.holdout(), "holdout", needed,
                        cfg.cap("season0.max_usd_holdout"))
        (od / "holdout.json").write_text(json.dumps(
            {pid: score(ts) for pid, ts in res.items()}, indent=2, sort_keys=True))
        return 0
    if cmd == "scorecard":
        from lab.protocols.runner import load_dev_transcripts
        screen = {pid: load_dev_transcripts(f"S0-screen-{pid}") for pid in configs(plan)}
        screen = {k: v for k, v in screen.items() if v}
        hold = {}
        hold_file = od / "holdout.json"
        if hold_file.exists():
            from lab.orchestrator import holdout as h
            from lab.protocols.runner import read_transcript
            for pid in json.loads(hold_file.read_text()):
                d = h.runs_dir(f"S0-holdout-{pid}")
                hold[pid] = [read_transcript(p) for p in sorted(d.glob("*.json.gz"))]
        rows = scorecard(plan, screen, hold)
        (od / "scorecard.json").write_text(json.dumps(rows, indent=2))
        (od / "SCORECARD.md").write_text(scorecard_md(rows))
        print(scorecard_md(rows))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
