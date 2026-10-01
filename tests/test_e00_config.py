import subprocess
import sys

import pytest
import yaml

from lab import paths
from lab.config import LabNotReady, load_config, placeholders


def test_repo_config_refuses_while_placeholders():
    cfg = load_config()
    if not cfg.missing():
        pytest.skip("Rex has filled in budget and prices")
    with pytest.raises(LabNotReady) as e:
        cfg.require_ready()
    assert "budget.yaml" in str(e.value)


def test_cli_check_exits_nonzero_on_placeholder():
    if not load_config().missing():
        pytest.skip("Rex has filled in budget and prices")
    r = subprocess.run([sys.executable, "-m", "lab", "check"], cwd=paths.ROOT,
                       capture_output=True, text=True, check=False)
    assert r.returncode == 2
    assert "refuses to run" in r.stderr


def test_filled_config_is_ready(filled_config):
    load_config(filled_config).require_ready()


@pytest.mark.parametrize("key", ["max_usd_per_day", "max_usd_per_month", "max_usd_per_item"])
def test_any_single_budget_placeholder_blocks(filled_config, key):
    p = filled_config / "budget.yaml"
    b = yaml.safe_load(p.read_text())
    b[key] = "PLACEHOLDER"
    p.write_text(yaml.safe_dump(b))
    with pytest.raises(LabNotReady, match=key):
        load_config(filled_config).require_ready()


def test_missing_price_blocks(filled_config):
    p = filled_config / "prices.yaml"
    pr = yaml.safe_load(p.read_text())
    del pr["models"]["claude-sonnet-5-5"]
    p.write_text(yaml.safe_dump(pr))
    cfg = load_config(filled_config)
    with pytest.raises(LabNotReady, match="claude-sonnet-5-5"):
        cfg.require_ready()
    with pytest.raises(LabNotReady):
        cfg.price("claude-sonnet-5-5")
    cfg.require_ready(["claude-haiku"])  # only models in use are required


def test_placeholders_walks_nested():
    assert placeholders({"a": {"b": "PLACEHOLDER", "c": 1}, "d": [None]}) == ["a.b", "d[0]"]


def test_layout_exists():
    for rel in ["README.md", "STEERING.md", "LEARNINGS.md", "CHARTER.md", "config/models.yaml",
                "config/prices.yaml", "config/budget.yaml", "config/scoring.yaml",
                "data/blocklist.txt", "learnings/learnings.jsonl", "ops/queue"]:
        assert (paths.ROOT / rel).exists(), rel
