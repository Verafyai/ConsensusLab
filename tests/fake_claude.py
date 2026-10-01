#!/usr/bin/env python3
"""Stand-in for the `claude` CLI in tests: checks its flags, writes one proposal, and
emits a stream-json transcript like Claude Code does."""
import json
import re
import sys
from pathlib import Path

args = sys.argv[1:]
prompt = args[args.index("-p") + 1]
assert "--restricted" in args and "--settings" in args and "--max-budget-usd" in args
assert args[args.index("--permission-mode") + 1] == "dontAsk"
exp = re.search(r"Experiment id: \*\*(E-\d{4})\*\*", prompt).group(1)
d = Path("experiments") / exp
d.mkdir(parents=True, exist_ok=True)
(d / "proposal.md").write_text("Hypothesis: haiku with evidence is a cheap floor\n"
                               "Builds on: STEERING.md\nTrack: A\nZone: Z1\n")
(d / "protocol.yaml").write_text(
    "id: fake-single-haiku\ndescription: t\npattern: single\nevidence: {retrieve: true}\n"
    "agents:\n  - {role: answerer, model: claude-haiku}\naggregation: majority\ntags: [z1]\n")
(d / "run.yaml").write_text("n: 10\n")
for ev in [{"type": "system", "subtype": "init"},
           {"type": "assistant", "message": {"content": [
               {"type": "text", "text": f"Proposing {exp}."},
               {"type": "tool_use", "name": "Write", "input": {"file_path": str(d)}}]}},
           {"type": "result", "subtype": "success", "num_turns": 3, "total_cost_usd": 0.42}]:
    print(json.dumps(ev), flush=True)
