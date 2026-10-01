import json
import re
from pathlib import Path

import pytest

from lab import paths
from lab.data import build, splits
from lab.data.ingest import averitec, claimreview, fever, liar
from lab.data.schema import InvalidItem, validate

RAW = Path(__file__).parent / "fixtures" / "raw"


def test_averitec_ingest_and_validate():
    items = list(averitec.ingest(RAW / "averitec" / "dev.json"))
    assert len(items) == 5  # unknown label dropped
    for it in items:
        validate(it)
    assert items[0]["gold"] == "refuted" and items[0]["date"] == "2022-03-14"
    assert items[4]["date"] is None if "date" in items[4] else True  # bad date → omitted
    assert {it["gold"] for it in items} == {"refuted", "supported", "conflicting",
                                            "not_enough_evidence"}


def test_liar_mapping_and_political_flag():
    items = list(liar.ingest(RAW / "liar" / "train.tsv"))
    assert [it["gold"] for it in items] == ["refuted", "conflicting", "supported"]
    assert all("political" in it["flags"] for it in items)
    assert "named_person" in items[0]["flags"]
    for it in items:
        validate(it)


def test_fever_is_crowd_labeled_three_way():
    items = list(fever.ingest(RAW / "fever" / "train.jsonl"))
    assert all("crowd_labeled" in it["flags"] for it in items)
    assert items[0]["label_set"] == ["supported", "refuted", "not_enough_evidence"]
    for it in items:
        validate(it)


def test_claimreview_drops_disagreement_and_unmapped():
    items = list(claimreview.ingest(RAW / "claimreview" / "search.json"))
    assert len(items) == 1
    assert items[0]["gold"] == "refuted" and items[0]["date"] == "2026-08-12"
    validate(items[0])


@pytest.mark.parametrize("patch,msg", [
    ({"gold": "maybe"}, "not in label_set"),
    ({"kind": "rumor"}, "kind"),
    ({"date": "03/02/2024"}, "date"),
    ({"extra": 1}, "Additional properties"),
])
def test_schema_rejects_bad_items(patch, msg):
    it = next(averitec.ingest(RAW / "averitec" / "dev.json"))
    it.update(patch)
    with pytest.raises(InvalidItem, match=msg):
        validate(it)


def _many(n=2000):
    base = next(averitec.ingest(RAW / "averitec" / "dev.json"))
    out = []
    for i in range(n):
        it = dict(base, id=f"q-test-{i:010x}", text=f"claim number {i}")
        it["date"] = "2026-09-01" if i % 10 == 0 else "2023-01-01"
        out.append(it)
    return out


def test_split_is_deterministic_and_respects_rules():
    items = _many()
    a = splits.assign(items, cutoff="2026-06-30")
    b = splits.assign(items, cutoff="2026-06-30")
    assert [x["split"] for x in a] == [x["split"] for x in b]
    hold = [x for x in a if x["split"] == "holdout"]
    assert 0.55 < len(hold) / len(a) < 0.70
    post = [x for x in a if splits.is_post_cutoff(x, "2026-06-30")]
    assert sum(x["split"] == "holdout" for x in post) / len(post) > 0.7
    crowd = splits.assign([dict(items[0], flags=["crowd_labeled"])], cutoff=None)
    assert crowd[0]["split"] == "dev"


def test_dedupe_prefers_dated():
    a = {"id": "q-x-0000000001", "text": "Same claim!", "date": None}
    b = {"id": "q-x-0000000002", "text": "same  claim", "date": "2020-01-01"}
    assert splits.dedupe([a, b]) == [b]


def test_mde_shrinks_with_n():
    assert splits.mde(500, 0.2) < splits.mde(100, 0.2)
    assert splits.mde(500, 0.2) == pytest.approx(0.0560, abs=1e-3)
    assert splits.mde(0, 0.2) == float("inf")


def test_report_has_sizes_and_mde():
    r = splits.report(splits.assign(_many(200), "2026-06-30"), "2026-06-30")
    assert "Dev:" in r and "Holdout:" in r and "Minimum detectable effect" in r


def test_build_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("CL_HOLDOUT_DIR", str(tmp_path / "hold"))
    approved = tmp_path / "approved.txt"
    approved.write_text("averitec\nliar\nfever\nclaimreview\n")
    monkeypatch.setattr(build, "APPROVED", approved)
    monkeypatch.setattr(build, "DEV", tmp_path / "dev.jsonl")
    monkeypatch.setattr(build, "REPORT", tmp_path / "SPLITS.md")
    assert build.main(["--raw", str(RAW)]) == 0
    from lab.orchestrator import holdout
    held = holdout.load()
    dev = [json.loads(x) for x in (tmp_path / "dev.jsonl").read_text().splitlines()]
    assert len(held) + len(dev) == 11
    assert not {h["id"] for h in held} & {d["id"] for d in dev}
    assert all("crowd_labeled" not in h["flags"] for h in held)
    assert oct((tmp_path / "hold" / "holdout.jsonl").stat().st_mode)[-3:] == "600"


def test_build_refuses_without_approval(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "APPROVED", tmp_path / "none.txt")
    assert build.main([]) == 2


# --- holdout isolation -------------------------------------------------------------------

def test_experimenter_permissions_deny_holdout():
    s = json.loads((paths.ROOT / "harness" / "experimenter-settings.json").read_text())
    deny = s["permissions"]["deny"]
    assert "Read(~/.consensus-lab/**)" in deny
    assert "Read(//**/.consensus-lab/**)" in deny
    allow = s["permissions"]["allow"]
    # No general shell: the only Bash the experimenter gets is the dev-only tools entrypoint.
    bash = [a for a in allow if a.startswith("Bash")]
    assert bash == ["Bash(uv run python -m lab.experimenter.tools:*)"]


def test_only_holdout_module_touches_holdout_path():
    offenders = []
    for py in (paths.ROOT / "lab").rglob("*.py"):
        rel = py.relative_to(paths.ROOT).as_posix()
        if rel in {"lab/orchestrator/holdout.py", "lab/paths.py"}:
            continue
        src = py.read_text()
        if re.search(r"holdout_dir\(|\.consensus-lab", src):
            offenders.append(rel)
    assert offenders == []


def test_holdout_dir_is_outside_repo():
    assert not paths.holdout_dir().resolve().is_relative_to(paths.ROOT)


def test_scifact_claim_level_labels():
    from lab.data.ingest import scifact
    items = list(scifact.ingest(RAW / "scifact" / "claims_dev.jsonl"))
    assert [(i["gold"], i["mapping"]) for i in items] == [
        ("supported", "exact"), ("conflicting", "manual"), ("not_enough_evidence", "exact")]
    for it in items:
        validate(it)


def test_factors_mapping():
    from lab.data.ingest import factors
    items = list(factors.ingest(RAW / "factors" / "factors.csv"))
    assert [(i["gold"], i["mapping"]) for i in items] == [("refuted", "exact"),
                                                          ("conflicting", "lossy")]
    assert items[0]["date"] == "2024-05-01"
    for it in items:
        validate(it)


def test_datacommons_post_cutoff_and_manual_drop():
    from lab.data.ingest import datacommons
    items = list(datacommons.ingest(RAW / "datacommons" / "feed.json"))
    assert len(items) == 1
    it = validate(items[0])
    assert it["gold"] == "refuted" and it["date"] == "2026-07-28"
    assert splits.is_post_cutoff(it, "2026-06-30")
