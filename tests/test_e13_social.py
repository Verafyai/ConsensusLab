import json
import subprocess
from datetime import UTC, datetime, timedelta

import pytest

from lab import paths
from social import agent as agent_mod
from social import compose, policy, select
from social.policy import PostRequest
from social.x import XError, oauth1_header

BASE = policy.load_policy()["dashboard_base_url"]


class FakeX:
    def __init__(self, poll_with_media=False):
        self.posts, self.uploads, self.n = [], [], 0
        self.poll_with_media = poll_with_media
        self.reply_data, self.metrics = {}, {}

    def create_post(self, text, media_ids=None, poll=None, reply_to=None, made_with_ai=True):
        if poll and media_ids and not self.poll_with_media:
            raise XError(400, {"errors": [{"message": "poll and media can't be combined"}]})
        self.n += 1
        pid = f"190000000000000{self.n:04d}"
        self.posts.append({"id": pid, "text": text, "media": media_ids, "poll": poll,
                           "reply_to": reply_to})
        return {"id": pid}

    def upload_video(self, path):
        self.uploads.append(path)
        return "media-1"

    def get_post(self, pid):
        m = self.metrics.get(pid, {})
        return {"data": {"id": pid, "public_metrics": {
            "like_count": m.get("likes", 30), "retweet_count": 5, "reply_count": 4,
            "quote_count": 1, "bookmark_count": 0, "impression_count": 1000}},
            "includes": {"polls": [{"options": [
                {"label": "Yes, and convincing", "votes": 12},
                {"label": "Right, but weak evidence", "votes": 6},
                {"label": "Wrong verdict", "votes": 14},
                {"label": "Can't tell", "votes": 3}]}]} if m.get("poll", True) else {}}

    def replies(self, conversation_id):
        return self.reply_data.get(conversation_id, [])

    def me(self):
        return {"id": "lab-user"}


@pytest.fixture
def social_root(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "experiments" / "E-0001").mkdir(parents=True)
    (root / "experiments" / "E-0001" / "results.json").write_text(json.dumps({
        "experiment": "E-0001", "protocol": "debate-judge", "status": "promoted",
        "cases": [{"item": "q-a", "why": ["panel split"]}]}))
    (root / "ops" / "queue").mkdir(parents=True)
    (root / "social").mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A"], cwd=root,
                   check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "i"],
                   cwd=root, check=True)
    for name, rel in [("ROOT", ""), ("EXPERIMENTS", "experiments"), ("RUNS", "runs"),
                      ("SOCIAL", "social"), ("PAUSE", "social/PAUSE"), ("QUEUE", "ops/queue"),
                      ("OPS", "ops"), ("LEDGER_SPEND", "ops/spend.jsonl"),
                      ("EVENTS", "ops/events.jsonl")]:
        monkeypatch.setattr(paths, name, root / rel if rel else root)
    from lab.protocols.runner import write_transcript
    sample = json.loads((__import__("pathlib").Path(__file__).parents[1] /
                         "viz/replay/samples/debate-sample.json").read_text())
    for item, flags in [("q-a", []), ("q-pol", ["political"]), ("q-nam", ["named_person"])]:
        write_transcript(dict(sample, experiment="E-0001", item=item, flags=flags,
                              confidence=0.99 if item != "q-a" else 0.6), "dev", root / "runs")
    return root


def req(**kw):
    t = {"experiment": "E-0001", "item": "q-a"}
    base = dict(kind="case_post", text=f"Claim: x\nProduced by an AI panel. Full evidence: "
                                         f"{compose.case_url(t)}",
                result_file="experiments/E-0001/results.json")
    base.update(kw)
    return PostRequest(**base)


def test_flagged_items_never_auto_selected(social_root):
    for _ in range(3):
        t = select.select_case()
        assert t is not None and t["item"] == "q-a" and not t["flags"]
    # Even when the unflagged case has been posted, flagged ones stay ineligible.
    policy.log_post(req(experiment="E-0001", item="q-a"), "1")
    assert select.select_case() is None


def test_transcript_without_flags_is_not_selected(social_root):
    from lab.protocols.runner import load_dev_transcripts, write_transcript
    for t in load_dev_transcripts("E-0001"):
        t.pop("flags")
        write_transcript(t, "dev", social_root / "runs")
    assert select.select_case() is None


def test_post_without_committed_result_file_refused(social_root):
    assert policy.check(req()).allowed
    d = policy.check(req(result_file=None))
    assert d.status == "needs_approval" and "no result file" in d.reasons[0]
    (social_root / "experiments" / "E-0001" / "results.json").write_text("{\"edited\": 1}")
    d = policy.check(req())
    assert d.status == "needs_approval" and "not a committed file" in d.reasons[0]
    d = policy.check(req(result_file="experiments/E-9999/results.json"))
    assert d.status == "needs_approval"


def test_pause_blocks_posting(social_root):
    (social_root / "social" / "PAUSE").write_text("")
    d = policy.check(req())
    assert d.status == "blocked" and "PAUSE" in d.reasons[0]
    x = FakeX()
    from tests.helpers import rig  # noqa: F401
    a = agent_mod.Agent(x, None)
    assert a.send(req()) is None and x.posts == []


@pytest.mark.parametrize("edit,status,why", [
    ({"text": "Claim: x @someone\nProduced by an AI panel. Full evidence: " + BASE},
     "needs_approval", "mentions"),
    ({"flags": ["political"]}, "needs_approval", "flagged"),
    ({"kind": "quote_post"}, "needs_approval", "not a cleared kind"),
    ({"kind": "ack_reply", "text": "Thanks " + BASE, "reply_to": "77", "thread_root": "999"},
     "needs_approval", "outside the lab's own threads"),
    ({"text": "Claim: x " + BASE}, "blocked", "disclosure"),
    ({"text": "Claim: x\nProduced by an AI panel."}, "blocked", "evidence"),
    ({"text": "Produced by an AI panel " + BASE + " " + "x" * 300}, "blocked", "characters"),
])
def test_policy_rules(social_root, edit, status, why):
    d = policy.check(req(**edit))
    assert d.status == status and any(why in r for r in d.reasons), d


def test_rate_limits_and_daily_case_cap(social_root):
    now = datetime.now(UTC)
    policy.log_post(req(), "1")
    d = policy.check(req(), now=now + timedelta(seconds=10))
    assert d.status == "blocked" and any("too soon" in r for r in d.reasons)
    d = policy.check(req(), now=now + timedelta(hours=2))
    assert any("today's case post" in r for r in d.reasons)
    assert policy.check(req(), now=now + timedelta(days=1, minutes=1)).allowed


def test_case_post_falls_back_to_thread_when_poll_rejected(social_root, filled_config,
                                                          tmp_path, monkeypatch):
    from tests.helpers import rig
    _, gw = rig(filled_config, tmp_path, lambda r, m: {"hook": "Ghana's census counted 30.8 "
                                                               "million people"})
    monkeypatch.setattr(agent_mod, "CAPS_FILE", tmp_path / "caps.yaml")
    x = FakeX(poll_with_media=False)
    fake_video = lambda src, out: (out.write_bytes(b"mp4"), {"problems": []})[1]  # noqa: E731
    a = agent_mod.Agent(x, gw, render_video=fake_video)
    root = a.case_post()
    assert root and len(x.posts) == 2
    assert x.posts[0]["media"] == ["media-1"] and x.posts[0]["poll"] is None
    assert x.posts[1]["reply_to"] == root["post_id"] and x.posts[1]["poll"]["options"][2] == \
        "Wrong verdict"
    assert all(len(o) <= 25 for o in x.posts[1]["poll"]["options"])
    assert agent_mod.capabilities()["poll_with_media"] is False
    logged = policy.logged_posts()
    assert [p["kind"] for p in logged] == ["case_post", "poll_reply"]
    assert logged[0]["result_file"] == "experiments/E-0001/results.json"
    assert logged[0]["poll_post_id"] == x.posts[1]["id"]
    assert "Produced by an AI panel" in x.posts[0]["text"] and BASE in x.posts[0]["text"]
    assert "30.8 million" in x.posts[0]["text"]


def test_case_post_single_post_when_poll_with_media_allowed(social_root, filled_config,
                                                           tmp_path, monkeypatch):
    from tests.helpers import rig
    _, gw = rig(filled_config, tmp_path, lambda r, m: {"hook": "A 99 billion person city"})
    monkeypatch.setattr(agent_mod, "CAPS_FILE", tmp_path / "caps.yaml")
    x = FakeX(poll_with_media=True)
    a = agent_mod.Agent(x, gw, render_video=lambda s, o: (o.write_bytes(b"v"),
                                                         {"problems": []})[1])
    a.case_post()
    assert len(x.posts) == 1 and x.posts[0]["poll"] and x.posts[0]["media"]
    assert "99 billion" not in x.posts[0]["text"]          # invented number rejected
    assert agent_mod.capabilities()["poll_with_media"] is True


def test_oauth1_signature_known_vector():
    # Twitter's documented example (developer.x.com "Creating a signature").
    h = oauth1_header(
        "POST", "https://api.twitter.com/1.1/statuses/update.json",
        {"status": "Hello Ladies + Gentlemen, a signed OAuth request!",
         "include_entities": "true"},
        "xvz1evFS4wEEPTGEFPHBog", "kAcSOqF21Fu85e7zjz7ZN2U4ZRhfV3WpwPAoE3Z7kBw",
        "370773112-GmHxMAgYyLbNEtIKZeRNFsMKPR9EyMZeS9weJAEb",
        "LswwdoUaIvS8ltyTt5jkRh4J50vUPVVHtR2YPi5kE",
        nonce="kYjzVBB8Y0ZFabxSWbWovY3uYSQ2pTgmZeNu2VS4cg", timestamp="1318622958")
    assert 'oauth_signature="hCtSmYh%2BiHYCEqBWrE7C7hYmtUk%3D"' in h


def test_lab_update_from_committed_results(social_root, monkeypatch):
    x = FakeX()
    a = agent_mod.Agent(x, None, dry_run=True)
    assert a.lab_update() is None       # no holdout champion yet: nothing to claim
