import json
import os
from pathlib import Path

import pytest

from harness import live
from lab.experimenter import claude, tools
from lab.orchestrator import learnings
from tests.test_e06_orchestrator import lab_root, make  # noqa: F401

FAKE = str(Path(__file__).with_name("fake_claude.py"))


def test_prompt_renders_with_refinement():
    p = claude.render_prompt("E-0042", {"refinement": {
        "zone": "Z4", "name": "Adversarial debate", "rule": "Only knobs.",
        "sub_techniques": {"fixed-side-debate": "z4-fixed-side-debate"}, "budget_left": 3.5,
        "steer": "focus on conflicting"}})
    assert "E-0042" in p and "exactly one experiment" in p
    assert "zones/Z4/sub/fixed-side-debate.yaml" in p and "focus on conflicting" in p
    assert "{" not in p.split("learnings/proposals")[0].split("```")[0].replace("{{", "")


def test_command_is_sandboxed():
    cmd = claude.command("hi", 1.5, "claude-opus-5-5")
    assert "--restricted" in cmd and "dontAsk" in cmd
    assert cmd[cmd.index("--max-budget-usd") + 1] == "1.50"
    allowed = cmd[cmd.index("--allowedTools") + 1]
    assert "Bash(uv run python -m lab.experimenter.tools:*)" in allowed
    assert "Edit(./config/**)" not in allowed


def test_live_view_extracts_result(capsys):
    lines = [json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "hello"}, {"type": "tool_use", "name": "Read",
                                            "input": {"file_path": "STEERING.md"}}]}}),
             json.dumps({"type": "result", "total_cost_usd": 0.1, "num_turns": 2})]
    r = live.stream(lines)
    err = capsys.readouterr().err
    assert r["total_cost_usd"] == 0.1 and "hello" in err and "STEERING.md" in err


def test_live_cycles_with_fake_claude(filled_config, tmp_path, lab_root, monkeypatch):  # noqa
    monkeypatch.setenv("CL_CLAUDE_BIN", FAKE)
    monkeypatch.setattr(claude, "LIVE_LOG", tmp_path / "live.jsonl")
    monkeypatch.chdir(lab_root)
    monkeypatch.setattr(claude.paths, "ROOT", lab_root)
    orch, _ = make(filled_config, tmp_path, lab_root, [])
    orch.cfg.budget["holdout_evals_per_week"] = 0
    import lab.config
    monkeypatch.setattr(lab.config, "get", lambda: orch.cfg)
    orch.experimenter = claude.ClaudeExperimenter(meter=orch.engine.gw.meter)
    for _ in range(5):
        r = orch.cycle()
        assert r["status"] in ("promoted", "stopped_at_dev", "not_promoted"), r.get("reason")
    exps = sorted((lab_root / "experiments").glob("E-*"))
    assert len(exps) == 5
    for d in exps:
        assert (d / "proposal.md").exists() and (d / "results.json").exists()
        assert (lab_root / "ops" / "experimenter" / "logs" / f"{d.name}.jsonl").exists()
    assert len(learnings.load()) == 5
    spend = (tmp_path / "spend.jsonl").read_text()
    assert spend.count("claude-code:experimenter") == 5
    hr = json.loads((lab_root / "experiments" / "hitrate.json").read_text())
    assert len(hr) == 5 and 0 <= hr[-1]["rate"] <= 1


def test_experimenter_refused_when_day_cannot_afford_it(filled_config, tmp_path, lab_root,  # noqa
                                                       monkeypatch):
    from lab.clients.base import Usage
    from lab.clients.meter import BudgetExceeded, Scope
    monkeypatch.setenv("CL_CLAUDE_BIN", FAKE)
    orch, _ = make(filled_config, tmp_path, lab_root, [])
    import lab.config
    monkeypatch.setattr(lab.config, "get", lambda: orch.cfg)
    m = orch.engine.gw.meter
    m.record(Scope(), "x", Usage(), 49.5, cached=False)
    with pytest.raises(BudgetExceeded):
        claude.ClaudeExperimenter(meter=m).propose("E-0001", lab_root / "experiments", {})


def test_tools_validate_and_estimate(capsys, monkeypatch, filled_config):
    import lab.config
    monkeypatch.setattr(lab.config, "get", lambda: lab.config.load_config(filled_config))
    monkeypatch.setattr(tools, "get", lambda: lab.config.load_config(filled_config))
    lib = Path(__file__).parents[1] / "lab" / "protocols" / "library"
    assert tools.cmd_validate(lib / "debate-judge.yaml") == 0
    assert tools.cmd_estimate(lib / "debate-judge.yaml", 100) == 0
    out = capsys.readouterr().out
    assert "OK debate-judge" in out and '"dev_items": 100' in out
    bad = Path(os.environ.get("TMPDIR", "/tmp")) / "bad-proto.yaml"
    bad.write_text("id: x\n")
    assert tools.cmd_validate(bad) == 1
    with pytest.raises(SystemExit):
        tools.main(["validate", str(bad)])


def test_tools_never_touch_holdout():
    src = Path(tools.__file__).read_text()
    assert "orchestrator import holdout" not in src and "holdout_dir" not in src
    assert "holdout.load" not in src


def test_hit_rate_and_consolidation(tmp_path):
    p = tmp_path / "l.jsonl"
    rows = []
    for i in range(70):
        rows.append({"id": f"L-{i + 1:04d}", "status": "tentative", "experiments": [f"E-{i:04d}"],
                     "hypothesis": "same idea" if i < 3 else f"idea {i}", "lesson": "x"})
    rows[10]["status"] = "confirmed"
    learnings.save(rows, p)
    r = learnings.consolidate(p, limit=60)
    after = learnings.load(p)
    assert r["merged"] == 2 and r["active"] <= 60
    assert after[2]["experiments"] == ["E-0000", "E-0001", "E-0002"]
    assert after[10]["status"] == "confirmed"           # confirmed lessons are never retired
    results = [{"experiment": f"E-{i:04d}", "status": "promoted" if i == 4 else "x"}
               for i in range(12)]
    hr = learnings.hit_rate(results, after, window=10)
    assert hr[4]["hit"] and hr[10]["hit"] and not hr[0]["hit"]
    assert hr[-1]["cumulative"] == pytest.approx(2 / 12)
    md = learnings.render(after)
    assert md.index("## Confirmed") < md.index("## Tentative") < md.index("Refuted")


@pytest.mark.parametrize("bad", ["~/.consensus-lab/holdout/holdout.jsonl", ".env",
                                 "ops/spend.jsonl", "/etc/passwd.yaml", "../x/protocol.yaml"])
def test_tools_refuse_paths_outside_protocol_dirs(bad):
    with pytest.raises(SystemExit, match="refused"):
        tools.main(["validate", bad])


def test_experimenter_settings_sandboxed():
    s = json.loads(claude.SETTINGS.read_text())
    assert s["sandbox"]["enabled"] is True and s["sandbox"]["autoAllowBashIfSandboxed"] is False
    assert "Read(./.env)" in s["permissions"]["deny"]
