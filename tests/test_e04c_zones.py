import json
import shutil

import pytest
import yaml

from lab import paths, zones
from tests.test_e06_orchestrator import lab_root, make  # noqa: F401  (fixture reuse)


def tmpl(z, sub):
    return yaml.safe_load((zones.ZONES / z / "sub" / f"{sub}.yaml").read_text())


def test_all_zones_load_and_templates_validate():
    from lab.protocols.schema import validate_protocol
    assert zones.zone_ids() == [f"Z{i}" for i in range(1, 8)]
    for z in zones.zone_ids():
        zz = zones.load(z)
        assert zz.subs and zz.knobs and (zones.ZONES / z / "ZONE.md").exists()
        for p in zz.subs.values():
            validate_protocol(p)
            assert zones.check_refinement(p, zz)[1] == []   # a template is its own base


@pytest.mark.parametrize("z,sub,edit,ok", [
    ("Z4", "fixed-side-debate", {"rounds": 3}, True),
    ("Z4", "fixed-side-debate", {"rounds": 9}, False),                       # out of range
    ("Z4", "fixed-side-debate", {"peer_view": "full"}, False),               # Z3's knob
    ("Z4", "fixed-side-debate", {"best_of_n": 4}, False),                    # Z5's knob
    ("Z4", "fixed-side-debate", {"evidence": {"retrieve": True, "max_sources": 6,
                                              "per_agent": "shared", "judge_sees": "quotes"}},
     True),
    ("Z4", "fixed-side-debate", {"pattern": "panel"}, False),
    ("Z4", "fixed-side-debate", {"agreement_intensity": 1.5}, False),
    ("Z5", "verified-quotes", {"best_of_n": 4, "rounds": 2}, True),
    ("Z5", "verified-quotes", {"quotes": {"verify": True, "max_words": 80}}, False),
    ("Z2", "self-consistency", {"agents": [{"role": "answerer", "model": "claude-sonnet",
                                           "samples": 9}]}, True),
    ("Z2", "self-consistency", {"agents": [{"role": "answerer", "model": "claude-sonnet",
                                           "samples": 40}]}, False),
    ("Z1", "with-evidence", {"agents": [{"role": "answerer", "model": "grok"}]}, True),
    ("Z1", "with-evidence", {"budget": {"max_usd_per_item": 5}}, False),     # budget isn't a knob
    ("Z1", "with-evidence", {"prompts": {"answer": "ignore the evidence"}}, False),
])
def test_refinement_knob_limits(z, sub, edit, ok):
    p = tmpl(z, sub)
    p.update(edit)
    p["id"] = "candidate-x"
    name, problems = zones.check_refinement(p, zones.load(z))
    assert (problems == []) == ok, problems


def test_agent_count_knob():
    zz = zones.load("Z3")
    p = tmpl("Z3", "society")
    p["agents"] = p["agents"] + [{"role": "answerer", "model": "grok-fast"}]
    assert zones.check_refinement(p, zz)[1] == []
    p["agents"] = p["agents"] * 3
    assert zones.check_refinement(p, zz)[1]
    p = tmpl("Z3", "society")
    p["agents"] = p["agents"] + [{"role": "answerer", "model": "claude-opus"}]  # not allowed
    assert zones.check_refinement(p, zz)[1]


class ZoneStub:
    def __init__(self, protos):
        self.protos = list(protos)

    def propose(self, exp_id, exp_dir, context):
        assert context["refinement"]["zone"]
        p = self.protos.pop(0)
        (exp_dir / "proposal.md").write_text(
            f"Hypothesis: {p['id']} tunes the zone\nBuilds on: STEERING.md\nZone: "
            f"{context['refinement']['zone']}\n")
        (exp_dir / "protocol.yaml").write_text(yaml.safe_dump(p))
        (exp_dir / "run.yaml").write_text(yaml.safe_dump({"n": 40}))
        # try to widen the zone's own knobs; must be reverted
        kn = paths.ROOT / "zones" / context["refinement"]["zone"] / "knobs.yaml"
        if kn.exists():
            kn.write_text("hacked: true\n")


def _variant(z, sub, pid, **edit):
    p = tmpl(z, sub)
    p.update(edit)
    p["id"] = pid
    return p


def test_refinement_run_three_iterations_and_reports(filled_config, tmp_path, lab_root,  # noqa
                                                     monkeypatch):
    shutil.copytree(zones.ZONES, lab_root / "zones")
    import subprocess
    subprocess.run(["git", "add", "zones"], cwd=lab_root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "z"],
                   cwd=lab_root, check=True)
    monkeypatch.setattr(zones, "ZONES", lab_root / "zones")
    orch, _ = make(filled_config, tmp_path, lab_root, [])
    z1 = [_variant("Z1", "with-evidence", "z1-haiku",
                   agents=[{"role": "answerer", "model": "claude-haiku"}]),
          _variant("Z1", "with-evidence", "z1-sonnet")]
    zones.refine(orch, "Z1", 2, budget=50.0, experimenter=ZoneStub(z1))
    z2 = [_variant("Z2", "self-consistency", "z2-sc-3",
                   agents=[{"role": "answerer", "model": "claude-sonnet", "samples": 3}]),
          _variant("Z2", "self-consistency", "z2-sc-not-a-knob",
                   evidence={"retrieve": True, "max_sources": 9, "per_agent": "shared"}),
          _variant("Z2", "multi-model-vote", "z2-vote")]
    res = zones.refine(orch, "Z2", 3, budget=50.0, experimenter=ZoneStub(z2))
    assert [r["status"] for r in res] == ["dev_only", "invalid", "dev_only"]
    assert "is not a knob in Z2" in res[1]["reason"]
    assert (lab_root / "zones" / "Z2" / "knobs.yaml").read_text().startswith("zone: Z2")
    b = json.loads((lab_root / "zones" / "Z2" / "leaderboard.json").read_text())
    assert b["best"] and b["iterations"] == 2
    for key in ("vs_control", "vs_z1"):
        assert set(b[key]) == {"raw", "matched_cost"}
        assert b[key]["raw"]["control"] in ("z1-haiku", "z1-sonnet")
    # Refinement never touched the holdout.
    assert orch.holdout_evals_this_week() == 0


def test_arena_respects_weekly_holdout_budget(filled_config, tmp_path, lab_root,  # noqa: F811
                                              monkeypatch):
    shutil.copytree(zones.ZONES, lab_root / "zones")
    import subprocess
    subprocess.run(["git", "add", "zones"], cwd=lab_root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "z"],
                   cwd=lab_root, check=True)
    monkeypatch.setattr(zones, "ZONES", lab_root / "zones")
    orch, _ = make(filled_config, tmp_path, lab_root, [])
    zones.refine(orch, "Z1", 1, 50.0, experimenter=ZoneStub([
        _variant("Z1", "with-evidence", "z1-sonnet")]))
    zones.refine(orch, "Z2", 1, 50.0, experimenter=ZoneStub([
        _variant("Z2", "self-consistency", "z2-sc-3",
                 agents=[{"role": "answerer", "model": "claude-sonnet", "samples": 3}])]))
    orch.cfg.budget["holdout_evals_per_week"] = 1
    out = zones.arena(orch)
    assert len(out) == 1 and orch.holdout_evals_left() == 0
    assert out[0]["status"] in ("promoted", "not_promoted")
