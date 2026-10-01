"""Track B: presentation scoring and selection (spec §6.1.3–6, §6.3, E10, E15).

    uv run python -m lab.trackb score --experiment E-0005 [--variant v2] [--n 20]
    uv run python -m lab.trackb agreement
    uv run python -m lab.trackb select v2          # decide whether variant v2 becomes default

Scores land in experiments/trackb/scores.jsonl, one row per case per variant. Track B
never touches verdicts: it only decides how verdicts are shown (CHARTER.md §1).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

from lab import paths
from lab.clients.meter import Scope
from lab.scoring import glance, readability
from lab.scoring.human import wilson_lower

DEFAULT_VARIANT = "base"


def trackb_dir() -> Path:
    d = paths.EXPERIMENTS / "trackb"
    d.mkdir(parents=True, exist_ok=True)
    return d


def default_variant() -> str:
    f = paths.ROOT / "viz" / "variants" / "DEFAULT"
    return f.read_text().strip() if f.exists() else DEFAULT_VARIANT


def _rows(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def score_case(gateway, t: dict, variant: str, scope: Scope, png_dir: Path,
               glance_fn=None) -> dict:
    cfg = gateway.cfg.scoring
    r = readability.score(t, gateway, scope, cfg["readability"]["rationale_max_words"],
                          cfg["readability"]["max_grade_level"])
    png = png_dir / variant / f"{t['experiment']}__{t['item']}.png"
    g = (glance_fn or glance.five_second_test)(gateway, t, scope, png,
                                               None if variant == DEFAULT_VARIANT else variant,
                                               cfg["glance"]["confidence_tolerance"])
    row = {"ts": datetime.now(UTC).isoformat(timespec="seconds"),
           "experiment": t["experiment"], "item": t["item"], "protocol": t["protocol"],
           "variant": variant, "readability": r["readability"], "grade": r["grade"],
           "words": r["words"], "jargon": r["jargon"], "clarity": r["clarity"],
           "glance": g["glance"], "glance_fields": {k: g[k] for k in
                                                    ("verdict", "confidence", "main_reason")}}
    with (trackb_dir() / "scores.jsonl").open("a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def score_experiment(gateway, experiment: str, variant: str, n: int = 20,
                     glance_fn=None) -> list[dict]:
    from lab.protocols.runner import load_dev_transcripts
    ts = [t for t in load_dev_transcripts(experiment) if t["verdict"] != "abstain"][:n]
    scope = Scope(experiment=f"trackb-{experiment}-{variant}",
                  caps={"trackb": gateway.cfg.cap("max_usd_per_experiment")})
    png_dir = paths.ROOT / ".cache" / "cards"
    return [score_case(gateway, t, variant, scope, png_dir, glance_fn) for t in ts]


# ------------------------------------------------------------------ human signals
def human_by_case(variant: str | None = None) -> dict[tuple[str, str], tuple[int, int]]:
    out: dict[tuple[str, str], list[int]] = {}
    for r in _rows(paths.ROOT / "ratings.jsonl"):
        if variant is not None and (r.get("variant") or DEFAULT_VARIANT) != variant:
            continue
        k = (r["experiment"], r["item"])
        up_down = out.setdefault(k, [0, 0])
        up_down[0 if r["thumb"] == "up" else 1] += 1
    return {k: (v[0], v[1]) for k, v in out.items()}


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / (sx * sy)


def agreement_report() -> dict:
    """How well each automated measure agrees with human thumbs, per case (spec §6.1.3)."""
    scores = _rows(trackb_dir() / "scores.jsonl")
    human = human_by_case()
    latest: dict[tuple[str, str, str], dict] = {}
    for s in scores:
        latest[(s["experiment"], s["item"], s["variant"])] = s
    out: dict = {"measures": {}, "n_cases": 0}
    pairs = [(s, human[(s["experiment"], s["item"])]) for s in latest.values()
             if (s["experiment"], s["item"]) in human]
    out["n_cases"] = len(pairs)
    for m in ("readability", "glance", "clarity", "grade"):
        xs, ys = [], []
        for s, (up, down) in pairs:
            if s.get(m) is not None and up + down:
                xs.append(float(s[m]))
                ys.append(up / (up + down))
        out["measures"][m] = {"n": len(xs), "pearson_r": _pearson(xs, ys)}
    (trackb_dir() / "agreement.json").write_text(json.dumps(out, indent=1))
    return out


# ------------------------------------------------------------------ selection (§6.3)
def variant_summary(variant: str) -> dict:
    rows = [s for s in _rows(trackb_dir() / "scores.jsonl") if s["variant"] == variant]
    up = down = 0
    for _, (u, d) in human_by_case(variant).items():
        up, down = up + u, down + d
    return {"variant": variant, "n": len(rows),
            "glance": sum(r["glance"] for r in rows) / len(rows) if rows else None,
            "readability": sum(r["readability"] for r in rows) / len(rows) if rows else None,
            "human_up": up, "human_down": down,
            "human_wilson": wilson_lower(up, up + down) if up + down else None}


def select(candidate: str, cfg, min_human: int = 10) -> dict:
    """A variant becomes the default when it beats the current one on glanceability and on
    human rating, without falling below the readability floor. Poll and social scores are
    supporting evidence only and never decide this."""
    cur_name = default_variant()
    cur, cand = variant_summary(cur_name), variant_summary(candidate)
    floor = cfg.scoring["readability"]["floor"]
    reasons = []
    if cand["glance"] is None or cur["glance"] is None:
        reasons.append("glanceability not scored for both variants")
    elif cand["glance"] <= cur["glance"]:
        reasons.append(f"glanceability {cand['glance']:.2f} doesn't beat {cur['glance']:.2f}")
    if (cand["human_up"] + cand["human_down"]) < min_human or \
            (cur["human_up"] + cur["human_down"]) < min_human:
        reasons.append(f"fewer than {min_human} human ratings on one of the variants")
    elif (cand["human_wilson"] or 0) <= (cur["human_wilson"] or 0):
        reasons.append("human rating doesn't beat the current default")
    if cand["readability"] is not None and cand["readability"] < floor:
        reasons.append(f"readability {cand['readability']:.2f} below floor {floor}")
    adopted = not reasons
    if adopted:
        (paths.ROOT / "viz" / "variants").mkdir(parents=True, exist_ok=True)
        (paths.ROOT / "viz" / "variants" / "DEFAULT").write_text(candidate + "\n")
    out = {"candidate": cand, "current": cur, "adopted": adopted, "reasons": reasons,
           "ts": datetime.now(UTC).isoformat(timespec="seconds")}
    with (trackb_dir() / "selections.jsonl").open("a") as f:
        f.write(json.dumps(out) + "\n")
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["score", "agreement", "select"])
    ap.add_argument("variant", nargs="?", default=None)
    ap.add_argument("--experiment")
    ap.add_argument("--n", type=int, default=20)
    a = ap.parse_args(argv)
    if a.cmd == "agreement":
        print(json.dumps(agreement_report(), indent=1))
        return 0
    from lab.clients.gateway import Gateway
    gw = Gateway.default()
    gw.cfg.require_ready([])
    if a.cmd == "score":
        rows = score_experiment(gw, a.experiment, a.variant or DEFAULT_VARIANT, a.n)
        print(f"scored {len(rows)} cases")
        return 0
    print(json.dumps(select(a.variant, gw.cfg), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
