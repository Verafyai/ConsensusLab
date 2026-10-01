"""Monitor pane (spec §10): spend, heartbeats, errors, queue count. Turns red on a cap
breach or a stalled/dead component.

    uv run python -m harness.monitor [--interval 5] [--once]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime

from harness import health
from lab import paths

RED, GREEN, YELLOW, BOLD, RESET = "\033[41;97m", "\033[32m", "\033[33m", "\033[1m", "\033[0m"
WATCHED = ["orchestrator", "dashboard", "grok"]


def recent_errors(hours: float = 24) -> list[dict]:
    if not paths.EVENTS.exists():
        return []
    cutoff = time.time() - hours * 3600
    out = []
    for line in paths.EVENTS.read_text().splitlines()[-2000:]:
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("ts", 0) >= cutoff and (e["type"] in ("budget.halt", "budget.refuse")
                                         or e["type"].endswith(".failed")):
            out.append(e)
    return out


def check(now: float | None = None) -> dict:
    """Everything the monitor shows, plus red/green. Pure enough to test."""
    from lab.config import get
    from lab.clients.meter import Meter
    st = health.status(now=now)
    problems = []
    for comp in WATCHED:
        s = st.get(comp)
        if s is None:
            continue                         # never started: not red, just absent
        if not s["ok"] and s["state"] != "stopped":
            problems.append(f"{comp}: {s['why']}")
    spend = {}
    try:
        cfg = get()
        m = Meter(cfg)
        for track, caps in (("lab", ("max_usd_per_day", "max_usd_per_month")),
                            ("social", ("social.max_usd_per_day", "social.max_usd_per_month"))):
            for period, key in zip(("day", "month"), caps, strict=True):
                used, cap = m.spent(track, period), cfg.cap(key)
                spend[f"{track}.{period}"] = (used, cap)
                if used >= cap:
                    problems.append(f"cap breached: {track} {period} ${used:.2f} ≥ ${cap:.2f}")
    except Exception as e:  # noqa: BLE001 - placeholders: show, don't crash
        spend["unset"] = (0.0, 0.0)
        problems_note = f"budget not configured ({str(e).splitlines()[0][:60]})"
        spend["note"] = problems_note  # type: ignore[assignment]
    errs = recent_errors()
    today = datetime.now(UTC).date().isoformat()
    if any(e["type"] == "budget.halt" and datetime.fromtimestamp(e["ts"], UTC).date().isoformat()
           == today for e in errs):
        problems.append("a run halted on a budget cap today")
    queue = sorted(p.name for p in paths.QUEUE.glob("*") if p.suffix in (".md", ".json")
                   and p.name != "README.md")
    return {"red": bool(problems), "problems": problems, "health": st, "spend": spend,
            "errors": errs[-5:], "queue": queue, "stopped": paths.STOP.exists(),
            "paused": paths.PAUSE.exists()}


def render(c: dict) -> str:
    head = (f"{RED} RED {RESET} " + "; ".join(c["problems"])) if c["red"] else \
        f"{GREEN}● all green{RESET}"
    lines = [f"{BOLD}Consensus Lab monitor{RESET}  {datetime.now():%H:%M:%S}", head, ""]
    for comp, s in sorted(c["health"].items()):
        mark = f"{GREEN}●{RESET}" if s["ok"] else ("○" if s["state"] == "stopped" else
                                                   f"\033[31m●{RESET}")
        lines.append(f" {mark} {comp:13} {s['state']:<12} {s['age_s']:>6.0f}s  {s['why'] or ''}")
    lines.append("")
    for k, v in c["spend"].items():
        if isinstance(v, tuple) and v[1]:
            frac = v[0] / v[1]
            col = "\033[31m" if frac >= 0.8 else YELLOW if frac >= 0.5 else ""
            lines.append(f" spend {k:13} {col}${v[0]:8.2f} / ${v[1]:.2f} ({frac:4.0%}){RESET}")
        elif k == "note":
            lines.append(f" {YELLOW}{v}{RESET}")
    lines.append("")
    flags = [x for x, on in (("ops/STOP", c["stopped"]), ("social/PAUSE", c["paused"])) if on]
    if flags:
        lines.append(f" {YELLOW}kill switch on: {', '.join(flags)}{RESET}")
    lines.append(f" queue for Rex: {len(c['queue'])}  " + ", ".join(c["queue"][:6]))
    for e in c["errors"]:
        lines.append(f" \033[31merror{RESET} {e['type']} {json.dumps(e.get('data', {}))[:90]}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args(argv)
    while True:
        c = check()
        out = render(c)
        if a.once:
            print(out)
            return 1 if c["red"] else 0
        sys.stdout.write("\033[2J\033[H" + out + "\n")
        sys.stdout.flush()
        time.sleep(a.interval)


if __name__ == "__main__":
    sys.exit(main())
