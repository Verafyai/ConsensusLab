import os
import signal
import subprocess
import sys
import textwrap
import time
import tomllib
from pathlib import Path

import pytest

from harness import health, monitor
from lab import paths

ROOT = Path(__file__).parents[1]


@pytest.fixture
def ops(tmp_path, monkeypatch):
    for name, rel in [("OPS", "ops"), ("HEARTBEAT", "ops/heartbeat.json"),
                      ("EVENTS", "ops/events.jsonl"), ("QUEUE", "ops/queue"),
                      ("STOP", "ops/STOP"), ("PAUSE", "social/PAUSE"),
                      ("LEDGER_SPEND", "ops/spend.jsonl")]:
        monkeypatch.setattr(paths, name, tmp_path / rel)
    (tmp_path / "ops" / "queue").mkdir(parents=True)
    return tmp_path


def test_killing_orchestrator_turns_monitor_red_within_one_interval(ops):
    hb = ops / "ops" / "heartbeat.json"
    code = textwrap.dedent(f"""
        import time
        from pathlib import Path
        from harness.health import Pulse
        with Pulse("orchestrator", interval=1.0, path=Path({str(hb)!r})) as p:
            p.state = "dev"
            time.sleep(120)
    """)
    proc = subprocess.Popen([sys.executable, "-c", code], cwd=ROOT)
    try:
        for _ in range(50):
            if hb.exists() and "orchestrator" in health.read(hb):
                break
            time.sleep(0.1)
        assert monitor.check()["health"]["orchestrator"]["ok"]
        assert "orchestrator" not in " ".join(monitor.check()["problems"])
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait()
        t0 = time.time()
        c = monitor.check()
        assert c["red"] and any("orchestrator" in p for p in c["problems"])
        assert time.time() - t0 < 1.0          # well within one heartbeat interval (15 s)
        assert "RED" in monitor.render(c)
    finally:
        if proc.poll() is None:
            proc.kill()


def test_stale_heartbeat_is_red(ops):
    health.beat("orchestrator", "dev", ops / "ops" / "heartbeat.json")
    c = monitor.check(now=time.time() + health.STALE_AFTER_S + 5)
    assert c["red"]


def test_cap_breach_is_red(ops, filled_config, monkeypatch):
    import lab.config
    from lab.clients.base import Usage
    from lab.clients.meter import Meter, Scope
    cfg = lab.config.load_config(filled_config)
    monkeypatch.setattr(lab.config, "get", lambda: cfg)
    Meter(cfg).record(Scope(), "x", Usage(), 50.0, cached=False)
    c = monitor.check()
    assert c["red"] and any("cap breached" in p for p in c["problems"])


def test_queue_and_kill_switches_shown(ops):
    (ops / "ops" / "queue" / "G-001-x.md").write_text("x")
    (ops / "ops" / "STOP").write_text("")
    out = monitor.render(monitor.check())
    assert "queue for Rex: 1" in out and "ops/STOP" in out


def test_herdr_template_has_all_panes():
    t = tomllib.loads((ROOT / "harness/herdr/consensus-lab.toml").read_text())
    labels = [p["label"] for p in t["tabs"][0]["panes"]]
    assert labels == ["orchestrator", "claude", "grok", "dashboard", "monitor"]
    for p in t["tabs"][0]["panes"]:
        script = ROOT / p["command"].split()[0]
        assert script.exists() and os.access(script, os.X_OK), script
    assert t["working_dir"] == "__LAB_ROOT__"


def test_launch_dry_run():
    r = subprocess.run(["bash", str(ROOT / "harness/launch.sh"), "--dry-run"],
                       capture_output=True, text=True, check=False)
    assert "herdr-plus open \"Consensus Lab\"" in r.stdout or "not found" in r.stdout
