import json
from datetime import date

from lab import paths, reports
from lab.config import load_config
from tests.test_e06_orchestrator import lab_root, make, proto  # noqa: F401


def test_three_consecutive_daily_digests_complete(filled_config, tmp_path, lab_root,  # noqa
                                                  monkeypatch):
    monkeypatch.setattr(paths, "REPORTS", lab_root / "ops" / "reports")
    monkeypatch.setattr(paths, "SOCIAL", lab_root / "social")
    monkeypatch.setattr(paths, "LEDGER_SPEND", tmp_path / "spend.jsonl")
    orch, _ = make(filled_config, tmp_path, lab_root,
                   [(proto("haiku-a", "claude-haiku"), {"n": 10})])
    orch.cfg.budget["holdout_evals_per_week"] = 0
    orch.cycle()
    (lab_root / "ops" / "queue" / "R-1-verdict-dispute.json").write_text("{}")
    (lab_root / "ops" / "queue" / "G-001-x.md").write_text("x")
    cfg = load_config(filled_config)
    today = date.today()
    days = [date.fromordinal(today.toordinal() - 2 + i) for i in range(3)]
    for d in days:
        r = reports.write_daily(d, cfg)
        assert reports.missing_fields(r) == []
        saved = json.loads((paths.REPORTS / f"{d.isoformat()}.json").read_text())
        assert reports.missing_fields(saved) == []
        assert (paths.REPORTS / f"{d.isoformat()}.md").exists()
    last = json.loads((paths.REPORTS / f"{today.isoformat()}.json").read_text())
    assert last["experiments_run"][0]["experiment"] == "E-0001"
    assert last["review_items"] == ["R-1-verdict-dispute.json"]
    assert "G-001-x.md" in last["approvals_waiting"]
    assert last["lessons"] and last["spend"]["today_total"] > 0
    md = (paths.REPORTS / f"{today.isoformat()}.md").read_text()
    assert "Review items waiting for Rex:** 1" in md


def test_weekly_update_data(filled_config, tmp_path, lab_root, monkeypatch):  # noqa: F811
    monkeypatch.setattr(paths, "REPORTS", lab_root / "ops" / "reports")
    w = reports.weekly(load_config(filled_config))
    assert set(w) >= {"champion", "holdout_macro_f1", "usd_per_item", "top_lesson", "season0",
                      "source_files"}
