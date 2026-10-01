import shutil
from pathlib import Path

import pytest
import yaml

from lab import paths

FILLED_PRICES = {"input": 3.0, "output": 15.0, "cache_read": 0.3}


@pytest.fixture
def filled_config(tmp_path: Path) -> Path:
    """A copy of config/ with every placeholder replaced by a test value."""
    dst = tmp_path / "config"
    shutil.copytree(paths.CONFIG, dst)
    budget = yaml.safe_load((dst / "budget.yaml").read_text())
    budget.update(max_usd_per_item=0.10, max_usd_per_item_champion=0.08,
                  max_usd_per_experiment=20.0, max_usd_per_day=50.0, max_usd_per_month=500.0)
    budget["social"] = {"max_usd_per_day": 2.0, "max_usd_per_month": 30.0}
    budget["season0"].update(max_usd_screening=80.0, max_usd_holdout=200.0)
    (dst / "budget.yaml").write_text(yaml.safe_dump(budget))
    prices = yaml.safe_load((dst / "prices.yaml").read_text())
    for k in prices["models"]:
        prices["models"][k] = dict(FILLED_PRICES)
    prices["services"] = {"search_per_query": 0.005, "fetch_per_page": 0.0,
                          "x_post": 0.01, "x_read": 0.005}
    (dst / "prices.yaml").write_text(yaml.safe_dump(prices))
    models = yaml.safe_load((dst / "models.yaml").read_text())
    for m in models["models"].values():
        m["knowledge_cutoff"] = "2026-01-01"
    (dst / "models.yaml").write_text(yaml.safe_dump(models))
    return dst
