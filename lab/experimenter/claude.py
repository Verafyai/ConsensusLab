"""The Claude experimenter: headless Claude Code, one experiment per invocation (spec §7.1, §10).

Sandboxing, in layers:
- `--restricted` confines file tools to the repo (the holdout lives outside it), drops
  code-running tools except the ones named in --tools, and ignores user/project settings.
- `--settings harness/experimenter-settings.json` allows edits only under experiments/,
  the protocol library, cards, viz variants and learning proposals, and allows Bash only
  for `uv run python -m lab.experimenter.tools`.
- After it exits, the orchestrator reverts any change outside the allowed paths.
- `--max-budget-usd` caps its own spend, which is reserved and metered like any call.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from lab import paths
from lab.clients.base import Usage
from lab.clients.meter import Scope

PROMPT = Path(__file__).with_name("PROMPT.md")
SETTINGS = paths.ROOT / "harness" / "experimenter-settings.json"
TOOLS = "Read,Edit,Write,Grep,Glob,Bash"
LIVE_LOG = paths.OPS / "experimenter" / "live.jsonl"


def render_prompt(exp_id: str, context: dict) -> str:
    ref = context.get("refinement")
    block = ""
    if ref:
        block = (f"\n## Zone refinement run: {ref['zone']} ({ref['name']})\n\n"
                 f"{ref['rule']}\nSub-techniques: "
                 f"{', '.join(f'zones/{ref['zone']}/sub/{k}.yaml' for k in ref['sub_techniques'])}"
                 f"\nKnobs and ranges: zones/{ref['zone']}/knobs.yaml. Budget left for this run:"
                 f" ${ref['budget_left']:.2f}.\n"
                 + (f"Rex's steering for this run: {ref['steer']}\n" if ref.get("steer") else ""))
    return PROMPT.read_text().format(exp_id=exp_id, refinement=block)


def command(prompt: str, budget_usd: float, model: str | None) -> list[str]:
    allowed = json.loads(SETTINGS.read_text())["permissions"]["allow"]
    cmd = [os.environ.get("CL_CLAUDE_BIN", "claude"), "-p", prompt, "--restricted",
           "--tools", TOOLS, "--settings", str(SETTINGS), "--allowedTools", ",".join(allowed),
           "--permission-mode", "dontAsk", "--output-format", "stream-json", "--verbose",
           "--max-budget-usd", f"{budget_usd:.2f}"]
    if model:
        cmd += ["--model", model]
    return cmd


class ClaudeExperimenter:
    def __init__(self, budget_usd: float | None = None, model: str | None = None,
                 meter=None, timeout_s: int = 1800):
        self.budget_usd = budget_usd
        self.model = model
        self.meter = meter
        self.timeout_s = timeout_s

    def propose(self, exp_id: str, exp_dir: Path, context: dict) -> None:
        if not shutil.which(os.environ.get("CL_CLAUDE_BIN", "claude")):
            raise RuntimeError("claude CLI not found on PATH")
        ctx_dir = paths.OPS / "experimenter"
        ctx_dir.mkdir(parents=True, exist_ok=True)
        (ctx_dir / "context.json").write_text(json.dumps({"experiment": exp_id, **context},
                                                         indent=1, default=str))
        from lab.config import get
        cfg = get()
        budget = self.budget_usd or cfg.cap("experimenter_usd_per_invocation")
        model = self.model or cfg.models.get("experimenter", {}).get("model")
        scope = Scope(experiment=exp_id)
        if self.meter:
            self.meter.reserve(budget, scope)       # refuses if the day can't afford it
        log = ctx_dir / "logs" / f"{exp_id}.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        result = None
        try:
            proc = subprocess.Popen(command(render_prompt(exp_id, context), budget, model),
                                    cwd=paths.ROOT, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True)
            assert proc.stdout is not None
            with log.open("w") as lf, LIVE_LOG.open("a") as live:
                for line in proc.stdout:
                    lf.write(line)
                    live.write(line)
                    live.flush()
                    if line.startswith('{"type":"result"'):
                        try:
                            result = json.loads(line)
                        except json.JSONDecodeError:
                            pass
            proc.wait(timeout=self.timeout_s)
        finally:
            cost = float((result or {}).get("total_cost_usd") or 0.0)
            if self.meter:
                self.meter.record(scope, "claude-code:experimenter", Usage(provider_usd=cost),
                                  cost, cached=False, reserved=budget)
        print(f"[experimenter] {exp_id} done: ${(result or {}).get('total_cost_usd', 0):.4f}",
              file=sys.stderr)
