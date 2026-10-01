"""The only commands the experimenter may run (harness/experimenter-settings.json).

    uv run python -m lab.experimenter.tools validate <protocol.yaml>
    uv run python -m lab.experimenter.tools estimate <protocol.yaml> [n_items]
    uv run python -m lab.experimenter.tools dev-eval <protocol.yaml> --n 10

Dev only. Nothing here can reach the holdout: it reads data/questions/dev.jsonl and never
imports lab.orchestrator.holdout.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

from lab.config import LabNotReady, get
from lab.protocols.schema import InvalidProtocol, load_protocol, models_used

MAX_DEV_EVAL_ITEMS = 20
ALLOWED_DIRS = ("experiments", "lab/protocols/library", "zones")


def safe_path(path: Path) -> Path:
    """Only protocol files inside the repo's experiment/library/zone folders. Anything else
    (the holdout, .env, ops logs) is refused before it is opened."""
    from lab import paths
    rp = path.expanduser().resolve()
    if rp.suffix not in (".yaml", ".yml"):
        raise SystemExit(f"refused: {path} is not a protocol YAML file")
    for d in ALLOWED_DIRS:
        if rp.is_relative_to((paths.ROOT / d).resolve()):
            return rp
    raise SystemExit(f"refused: {path} is outside {', '.join(ALLOWED_DIRS)}")


def cmd_validate(path: Path) -> int:
    try:
        p = load_protocol(path, set(get().models["models"]))
    except InvalidProtocol as e:
        print(f"INVALID: {e}")
        return 1
    except Exception as e:   # noqa: BLE001 - don't echo file content from parse errors
        print(f"INVALID: could not load {path.name} ({type(e).__name__})")
        return 1
    print(f"OK {p['id']} ({p['pattern']}, models: {', '.join(models_used(p))})")
    return 0


def cmd_estimate(path: Path, n: int | None) -> int:
    from lab.protocols.estimate import estimate
    cfg = get()
    p = load_protocol(path, set(cfg.models["models"]))
    try:
        e = estimate(p, cfg)
    except LabNotReady as err:
        print(f"Can't estimate yet: {err}")
        return 2
    ctx_file = Path("ops/experimenter/context.json")
    dev_n = n or (json.loads(ctx_file.read_text()).get("dev_items") if ctx_file.exists() else 0)
    total = e.total(dev_n or 0)
    print(json.dumps({"protocol": p["id"], "calls_per_item": e.calls,
                      "usd_per_item_expected": round(e.expected_usd, 5),
                      "usd_per_item_worst": round(e.worst_usd, 5), "dev_items": dev_n,
                      "dev_total_expected": round(total, 4),
                      "max_usd_per_experiment": cfg.cap("max_usd_per_experiment")}, indent=1))
    return 0


def cmd_dev_eval(path: Path, n: int) -> int:
    from lab.clients.gateway import Gateway
    from lab.clients.meter import Scope
    from lab.data.build import DEV
    from lab.data.schema import read_jsonl
    from lab.evidence.retrieve import Retriever
    from lab.protocols.engine import Engine
    from lab.protocols.runner import run_protocol
    from lab.scoring.score import score
    n = min(n, MAX_DEV_EVAL_ITEMS)
    gw = Gateway.default()
    p = load_protocol(path, set(gw.cfg.models["models"]))
    gw.cfg.require_ready(models_used(p))
    items = [it for it in read_jsonl(DEV) if it["split"] == "dev"]
    items = random.Random(0).sample(items, min(n, len(items)))
    cap = min(gw.cfg.cap("max_usd_per_experiment") * 0.1, 2.0)
    ts = run_protocol(Engine(gw, Retriever.default(gw.cfg, gw.meter)), p, items,
                      Scope(experiment="experimenter-dev-eval", caps={"dev-eval": cap}),
                      "experimenter-dev-eval", write=False)
    s = score(ts)
    print(json.dumps({"n": s["n"], "macro_f1": round(s["macro_f1"], 3),
                      "abstain_rate": round(s["abstain_rate"], 3),
                      "usd": round(sum(t["usd"] for t in ts), 4),
                      "errors": [t["error"] for t in ts if t.get("error")][:3]}, indent=1))
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="lab.experimenter.tools")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("path", type=Path)
    e = sub.add_parser("estimate")
    e.add_argument("path", type=Path)
    e.add_argument("n", type=int, nargs="?")
    d = sub.add_parser("dev-eval")
    d.add_argument("path", type=Path)
    d.add_argument("--n", type=int, default=10)
    a = ap.parse_args(argv)
    a.path = safe_path(a.path)
    if a.cmd == "validate":
        return cmd_validate(a.path)
    if a.cmd == "estimate":
        return cmd_estimate(a.path, a.n)
    return cmd_dev_eval(a.path, a.n)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
