"""Live view of a headless Claude Code stream (like checkworthy's dashboard/live.py).

    claude -p ... --output-format stream-json --verbose | python -m harness.live

Prints what the agent says and each tool call to stderr; writes the final result event
as JSON to stdout. `--follow FILE` tails a log instead (the herdr claude pane).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

DIM, BOLD, RED, RESET = "\033[2m", "\033[1m", "\033[31m", "\033[0m"


def describe(ev: dict) -> list[str]:
    out = []
    t = ev.get("type")
    if t == "assistant":
        for b in ev.get("message", {}).get("content", []):
            if b.get("type") == "text" and b.get("text", "").strip():
                out.append(f"{BOLD}says:{RESET} {b['text'].strip()[:400]}")
            elif b.get("type") == "tool_use":
                inp = b.get("input", {})
                arg = inp.get("command") or inp.get("file_path") or inp.get("pattern") or ""
                out.append(f"{DIM}{b['name']}:{RESET} {str(arg)[:200]}")
    elif t == "user":
        for b in ev.get("message", {}).get("content", []):
            if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("is_error"):
                c = b.get("content")
                txt = c if isinstance(c, str) else json.dumps(c)[:200]
                out.append(f"{RED}tool error:{RESET} {txt[:200]}")
    elif t == "result":
        out.append(f"{BOLD}done{RESET} turns={ev.get('num_turns')} "
                   f"cost=${ev.get('total_cost_usd', 0):.4f} {ev.get('subtype', '')}")
    return out


def stream(lines, err=None) -> dict | None:
    err = err or sys.stderr
    result = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        for s in describe(ev):
            print(s, file=err, flush=True)
        if ev.get("type") == "result":
            result = ev
    return result


def follow(path: Path):
    path.touch()
    with path.open() as f:
        f.seek(0, 2)
        while True:
            line = f.readline()
            if line:
                yield line
            else:
                time.sleep(0.5)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--follow"]:
        stream(follow(Path(sys.argv[2])), err=sys.stdout)
    else:
        r = stream(sys.stdin)
        if r:
            print(json.dumps(r))
