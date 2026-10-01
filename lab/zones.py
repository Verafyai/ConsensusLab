"""Testing zones (spec §5.4, E04c): knob checks, zone leaderboards, refinement runs, arena.

    uv run python -m lab.zones list
    uv run python -m lab.zones leaderboard            # writes zones/*/leaderboard.json
    uv run python -m lab.zones refine Z4 --iterations 3 --budget 10 [--steer "..."]
    uv run python -m lab.zones arena                  # zone champions → holdout

A zone refinement run hands the experimenter one zone; every proposal must be one of that
zone's sub-technique templates with only its knobs changed, inside the ranges in
knobs.yaml. Refinement is dev-only. The arena sends each zone's best configuration to the
holdout, which spends the weekly holdout-evaluation budget.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from lab import paths
from lab.scoring import leaderboard

ZONES = paths.ROOT / "zones"
SEL = re.compile(r"^agents\[(\*|\d+|role=\w+)\]\.(\w+)$")


@dataclass
class Zone:
    id: str
    name: str
    control: dict | None
    knobs: dict[str, dict]
    free: list[str]
    subs: dict[str, dict] = field(default_factory=dict)


def zone_ids(root: Path | None = None) -> list[str]:
    return sorted(p.name for p in (root or ZONES).glob("Z*") if (p / "knobs.yaml").exists())


def load(zid: str, root: Path | None = None) -> Zone:
    d = (root or ZONES) / zid
    k = yaml.safe_load((d / "knobs.yaml").read_text())
    subs = {f.stem: yaml.safe_load(f.read_text()) for f in sorted((d / "sub").glob("*.yaml"))}
    return Zone(zid, k["name"], k.get("control"), k["knobs"], k.get("free", []), subs)


def template_ids(root: Path | None = None) -> dict[str, dict]:
    """All zone sub-technique templates by protocol id (they're runnable protocols)."""
    out = {}
    for z in zone_ids(root):
        for p in load(z, root).subs.values():
            out[p["id"]] = p
    return out


# ------------------------------------------------------------------ knob checking
def flatten(p: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(p, dict):
        for k, v in p.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(p, list) and prefix == "agents":
        for i, a in enumerate(p):
            out.update(flatten(a, f"agents[{i}]"))
    else:
        out[prefix] = p
    return out


def _value_ok(spec: dict, v: Any) -> bool:
    if spec.get("free_text"):
        return isinstance(v, str) and len(v) <= 600
    if "values" in spec:
        return v in spec["values"]
    if "range" in spec:
        lo, hi = spec["range"]
        if isinstance(v, bool) or not isinstance(v, int | float):
            return False
        if spec.get("int") and not float(v).is_integer():
            return False
        return lo <= v <= hi
    return False


def _knob_for(path: str, prop: dict, zone: Zone) -> dict | None:
    m = SEL.match(path)
    for spec in zone.knobs.values():
        kp = spec["path"]
        if kp == path:
            return spec
        if m and (km := SEL.match(kp)) and km.group(2) == m.group(2):
            sel = km.group(1)
            idx = int(m.group(1)) if m.group(1).isdigit() else None
            if sel == "*":
                return spec
            if sel.startswith("role=") and idx is not None and idx < len(prop.get("agents", [])):
                if prop["agents"][idx].get("role") == sel[5:]:
                    return spec
            if sel.isdigit() and idx == int(sel):
                return spec
    return None


def violations(prop: dict, base: dict, zone: Zone) -> list[str]:
    """Differences between a proposal and one template that the zone's knobs don't allow."""
    out: list[str] = []
    if prop.get("pattern") != base.get("pattern"):
        return [f"pattern {prop.get('pattern')!r} differs from template {base.get('pattern')!r}"]
    agents_knob = next((s for s in zone.knobs.values() if s["path"] == "agents"), None)
    pa, ba = prop.get("agents", []), base.get("agents", [])
    if len(pa) != len(ba) or [a["role"] for a in pa] != [a["role"] for a in ba]:
        if not agents_knob:
            return [f"agents changed ({len(ba)}→{len(pa)}) but zone has no agents knob"]
        lo, hi = agents_knob["count"]
        if not lo <= len(pa) <= hi:
            out.append(f"agents count {len(pa)} outside {lo}..{hi}")
        for a in pa:
            if a["role"] not in agents_knob["roles"]:
                out.append(f"agent role {a['role']!r} not allowed")
        compare_agents = False
    else:
        compare_agents = True
    fp, fb = flatten(prop), flatten(base)
    for path in sorted(set(fp) | set(fb)):
        if path.split(".")[0] in zone.free or path.split("[")[0] in zone.free:
            continue
        if path.startswith("agents[") and not compare_agents:
            # agent list was restructured: check each agent field on its own
            if path in fp:
                field_ = path.split(".", 1)[1]
                if field_ in ("role", "name"):
                    continue
                spec = _knob_for(path, prop, zone)
                if field_ == "model" and agents_knob and fp[path] in agents_knob["models"]:
                    continue
                if spec is None or not _value_ok(spec, fp[path]):
                    out.append(f"{path}={fp[path]!r} not allowed")
            continue
        if fp.get(path, "<unset>") == fb.get(path, "<unset>") or path.endswith(".name"):
            continue
        spec = _knob_for(path, prop, zone)
        if spec is None:
            if path.startswith("agents[") and path.endswith(".model") and agents_knob and \
                    fp.get(path) in agents_knob["models"]:
                continue
            out.append(f"{path} is not a knob in {zone.id}")
        elif path not in fp:
            continue          # removing an optional knob setting returns it to the default
        elif not _value_ok(spec, fp[path]):
            out.append(f"{path}={fp[path]!r} outside allowed values")
    return out


def check_refinement(prop: dict, zone: Zone) -> tuple[str | None, list[str]]:
    """(matching sub-technique, problems). A proposal passes if some template in the zone
    differs from it only by allowed knob changes."""
    best: tuple[str | None, list[str]] = (None, ["no sub-technique templates"])
    best_rank: tuple[bool, int] = (True, 10**9)
    for name, base in zone.subs.items():
        v = violations(prop, base, zone)
        if not v:
            return name, []
        rank = (base.get("pattern") != prop.get("pattern"), len(v))
        if best[0] is None or rank < best_rank:
            best, best_rank = (name, v), rank
    return None, [f"closest template sub/{best[0]}.yaml: " + "; ".join(best[1])]


# ------------------------------------------------------------------ leaderboards
def zone_of(result: dict) -> str | None:
    z = result.get("zone")
    if z:
        return z.upper()
    for t in result.get("tags", []):
        if re.fullmatch(r"z\d", t):
            return t.upper()
    return None


def _dev(r: dict) -> tuple[float | None, float | None]:
    d = r.get("dev") or {}
    return d.get("macro_f1"), (d.get("cost") or {}).get("usd_per_item_uncached")


def board(zid: str, results: list[dict], zone: Zone | None = None) -> dict:
    zone = zone or load(zid)
    mine = [r for r in results if zone_of(r) == zid and _dev(r)[0] is not None]
    rows: dict[str, dict] = {}
    for r in sorted(mine, key=lambda r: r["experiment"]):
        f1, usd = _dev(r)
        rows[r["protocol"]] = {"protocol": r["protocol"], "dev_macro_f1": f1, "usd_per_item": usd,
                               "experiment": r["experiment"], "status": r.get("status"),
                               "source": f"experiments/{r['experiment']}/results.json"}
    table = sorted(rows.values(), key=lambda x: -x["dev_macro_f1"])
    best = table[0] if table else None
    out: dict[str, Any] = {"zone": zid, "name": zone.name, "iterations": len(mine),
                           "spend_usd": round(sum((r.get("dev") or {}).get("cost", {})
                                                  .get("usd_total", 0) for r in mine), 4),
                           "best": best, "rows": table}
    if best:
        out["vs_control"] = _versus(best, control_rows(zone, results), raw=zone.control)
        if zid != "Z1":
            out["vs_z1"] = _versus(best, [r for r in results if zone_of(r) == "Z1"])
    return out


def control_rows(zone: Zone, results: list[dict]) -> list[dict]:
    c = zone.control or {}
    if "zone_best" in c:
        return [r for r in results if zone_of(r) == c["zone_best"]]
    if "protocol" in c:
        return [r for r in results if r["protocol"] == c["protocol"]]
    return []


def _versus(best: dict, candidates: list[dict], raw: dict | None = None) -> dict | None:
    """Raw: against the best control result. Matched cost: against the best control that
    costs no more per item than the zone's best (what the same money buys elsewhere)."""
    rows = [(r["protocol"], *_dev(r)) for r in candidates if _dev(r)[0] is not None]
    if not rows:
        return None
    top = max(rows, key=lambda x: x[1])
    out = {"raw": {"control": top[0], "control_f1": top[1], "diff": best["dev_macro_f1"] - top[1],
                   "cost_ratio": (best["usd_per_item"] / top[2]) if top[2] else None}}
    affordable = [x for x in rows if x[2] is not None and best["usd_per_item"] is not None
                  and x[2] <= best["usd_per_item"]]
    if affordable:
        m = max(affordable, key=lambda x: x[1])
        out["matched_cost"] = {"control": m[0], "control_f1": m[1],
                               "diff": best["dev_macro_f1"] - m[1]}
    else:
        out["matched_cost"] = None    # every control costs more than this configuration
    return out


def write_boards(results: list[dict] | None = None, root: Path | None = None) -> dict[str, dict]:
    results = results if results is not None else leaderboard.load_results()
    out = {}
    for z in zone_ids(root):
        b = board(z, results, load(z, root))
        ((root or ZONES) / z / "leaderboard.json").write_text(json.dumps(b, indent=2))
        out[z] = b
    return out


# ------------------------------------------------------------------ runs
class CodeProposer:
    """Proposes a fixed protocol with a written hypothesis (arena, dashboard runs)."""

    def __init__(self, protocol: dict, hypothesis: str, zone: str | None, run: dict | None = None,
                 builds_on: str = "STEERING.md"):
        self.protocol, self.hypothesis, self.zone, self.run = protocol, hypothesis, zone, run
        self.builds_on = builds_on

    def propose(self, exp_id: str, exp_dir: Path, context: dict) -> None:
        cite = self.builds_on
        if cite == "STEERING.md" and context.get("learnings_top"):
            cite = f"STEERING.md, {context['learnings_top'][-1]['id']}"
        (exp_dir / "proposal.md").write_text(
            f"# {exp_id}\n\nHypothesis: {self.hypothesis}\nBuilds on: {cite}\nTrack: A\n"
            f"Zone: {self.zone or ''}\nProposed by: code\n")
        (exp_dir / "protocol.yaml").write_text(yaml.safe_dump(self.protocol, sort_keys=False))
        if self.run:
            (exp_dir / "run.yaml").write_text(yaml.safe_dump(self.run))


def refine(orch, zid: str, iterations: int, budget: float, steer: str = "",
           experimenter=None) -> list[dict]:
    """A zone refinement run: N dev-only iterations, knobs constrained to the zone."""
    zone = load(zid)
    orch.constraint = {"zone": zid, "dev_only": True, "budget": budget, "steer": steer,
                       "spent": 0.0}
    if experimenter is not None:
        orch.experimenter = experimenter
    out = []
    try:
        for _ in range(iterations):
            if orch.constraint["spent"] >= budget:
                break
            r = orch.cycle()
            out.append(r)
            if r.get("status") in ("stopped", "halted_budget"):
                break
            orch.constraint["spent"] += ((r.get("dev") or {}).get("cost") or {}).get(
                "usd_total", 0.0)
    finally:
        orch.constraint = None
    write_boards(orch.results())
    _ = zone
    return out


def arena(orch) -> list[dict]:
    """Each zone's best dev configuration goes to the holdout (spec §5.4, weekly)."""
    out = []
    results = orch.results()
    for z in zone_ids():
        b = board(z, results)
        if not b.get("best") or orch.holdout_evals_left() <= 0:
            continue
        best = b["best"]
        src = paths.EXPERIMENTS / best["experiment"] / "protocol.yaml"
        if not src.exists():
            continue
        proto = yaml.safe_load(src.read_text())
        orch.experimenter = CodeProposer(proto, f"{best['protocol']}, the {z} champion, "
                                                f"beats the overall champion on the holdout", z)
        out.append(orch.cycle())
    write_boards(orch.results())
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "leaderboard", "refine", "arena"])
    ap.add_argument("zone", nargs="?")
    ap.add_argument("--iterations", type=int, default=3)
    ap.add_argument("--budget", type=float, default=10.0)
    ap.add_argument("--steer", default="")
    a = ap.parse_args(argv)
    if a.cmd == "list":
        for z in zone_ids():
            zz = load(z)
            print(f"{z} {zz.name}: {', '.join(zz.subs)} | knobs: {', '.join(zz.knobs)}")
        return 0
    if a.cmd == "leaderboard":
        for z, b in write_boards().items():
            best = b.get("best") or {}
            print(f"{z}: best {best.get('protocol', '–')} {best.get('dev_macro_f1', '')}")
        return 0
    from lab.experimenter.claude import ClaudeExperimenter
    from lab.orchestrator.factory import build
    orch = build(ClaudeExperimenter())
    if a.cmd == "refine":
        if not a.zone:
            print("refine needs a zone, e.g. Z4", file=sys.stderr)
            return 2
        for r in refine(orch, a.zone.upper(), a.iterations, a.budget, a.steer):
            print(r["experiment"], r["protocol"], r["status"])
        return 0
    for r in arena(orch):
        print(r["experiment"], r["protocol"], r["status"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))


# ------------------------------------------------------------------ knob application
def set_path(p: dict, path: str, value: Any) -> None:
    """Set a knob path on a protocol dict, e.g. 'rounds', 'early_stop.judge_can_end',
    'agents[role=judge].model', 'agents[*].samples'."""
    m = SEL.match(path)
    if m:
        sel, fld = m.groups()
        for i, a in enumerate(p.get("agents", [])):
            if sel == "*" or (sel.isdigit() and int(sel) == i) or \
                    (sel.startswith("role=") and a.get("role") == sel[5:]):
                a[fld] = value
        return
    node = p
    parts = path.split(".")
    for k in parts[:-1]:
        node = node.setdefault(k, {})
    node[parts[-1]] = value


def apply_knobs(zid: str, sub: str, knobs: dict[str, Any], pid: str | None = None) -> dict:
    """A protocol built from a zone template with named knob values (dashboard runs)."""
    import copy
    z = load(zid)
    if sub not in z.subs:
        raise ValueError(f"{zid} has no sub-technique {sub!r}")
    p = copy.deepcopy(z.subs[sub])
    for name, value in knobs.items():
        if name not in z.knobs:
            raise ValueError(f"{name!r} is not a {zid} knob")
        spec = z.knobs[name]
        if spec["path"] == "agents":
            p["agents"] = value
        else:
            set_path(p, spec["path"], value)
    p["id"] = pid or f"{p['id']}-" + "-".join(
        f"{k}{str(v).lower().replace('.', '')[:8]}" for k, v in sorted(knobs.items())
        if not isinstance(v, list))[:40].rstrip("-")
    return p
