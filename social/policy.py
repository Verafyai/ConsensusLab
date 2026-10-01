"""The clearance policy in code (spec §9.2). Every post passes through check() first.

Outcomes: allowed, needs_approval (written to ops/queue/ for Rex), or blocked (PAUSE, rate
limits, malformed). Nothing here can be relaxed by an agent: policy.yaml is a locked path.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from lab import paths

POLICY = Path(__file__).with_name("policy.yaml")
KINDS = {"case_post", "poll_reply", "lab_update", "ack_reply"}
MENTION = re.compile(r"(?<![\w.])@\w")


@dataclass
class PostRequest:
    kind: str
    text: str
    result_file: str | None = None           # committed file that backs every claim
    flags: list[str] = field(default_factory=list)
    reply_to: str | None = None              # post id this replies to
    thread_root: str | None = None           # our own post that starts the thread
    media: str | None = None
    poll: dict | None = None
    experiment: str | None = None
    item: str | None = None


@dataclass
class Decision:
    status: str                              # allowed | needs_approval | blocked
    reasons: list[str] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.status == "allowed"


def load_policy() -> dict:
    return yaml.safe_load(POLICY.read_text())


def posts_log() -> Path:
    return paths.SOCIAL / "posts.jsonl"


def logged_posts() -> list[dict]:
    p = posts_log()
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def committed(rel: str, root: Path | None = None) -> bool:
    """True if `rel` is tracked by git and has no uncommitted changes."""
    root = root or paths.ROOT
    if not (root / rel).is_file():
        return False
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=root,
                             capture_output=True).returncode == 0
    clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", rel], cwd=root,
                           capture_output=True).returncode == 0
    return tracked and clean


def own_thread_ids(posts: list[dict]) -> set[str]:
    ids = set()
    for p in posts:
        for k in ("post_id", "thread_root"):
            if p.get(k):
                ids.add(str(p[k]))
    return ids


def check(req: PostRequest, now: datetime | None = None, policy: dict | None = None,
          posts: list[dict] | None = None) -> Decision:
    now = now or datetime.now(UTC)
    pol = policy or load_policy()
    posts = posts if posts is not None else logged_posts()
    if paths.PAUSE.exists():
        return Decision("blocked", ["social/PAUSE is present"])
    if req.kind not in KINDS:
        return Decision("needs_approval", [f"'{req.kind}' is not a cleared kind of post"])
    reasons: list[str] = []
    approval: list[str] = []
    always = pol["always"]
    text = req.text or ""
    # --- content rules
    if len(text) > always["max_chars"]:
        reasons.append(f"{len(text)} characters > {always['max_chars']}")
    if MENTION.search(text):
        approval.append("mentions another account")
    if req.kind != "ack_reply" and always["disclosure"].lower() not in text.lower():
        reasons.append(f"missing disclosure '{always['disclosure']}'")
    if always.get("evidence_link") and pol["dashboard_base_url"] not in text:
        reasons.append("missing link to the full evidence")
    # --- backing
    if req.kind in ("case_post", "poll_reply", "lab_update"):
        if not req.result_file:
            approval.append("no result file backs this post")
        elif not committed(req.result_file):
            approval.append(f"{req.result_file} is not a committed file")
    bad_flags = sorted(set(req.flags) & set(pol["never_without_approval"]["flags"]))
    if bad_flags:
        approval.append(f"item flagged {', '.join(bad_flags)}")
    # --- threads
    if req.kind in ("ack_reply", "poll_reply"):
        if not req.reply_to or str(req.thread_root or "") not in own_thread_ids(posts):
            approval.append("reply outside the lab's own threads")
        if req.kind == "ack_reply" and len(text) > pol["cleared"]["ack_reply"]["max_chars"]:
            reasons.append("acknowledgment too long")
    elif req.reply_to:
        approval.append("replies are only cleared inside the lab's own threads")
    # --- rate limits and caps
    day_ago, week_ago = now - timedelta(days=1), now - timedelta(days=7)
    recent = [p for p in posts if datetime.fromisoformat(p["ts"]) > day_ago]
    if len(recent) >= always["max_posts_per_day"]:
        reasons.append("daily post cap reached")
    if posts:
        last = max(datetime.fromisoformat(p["ts"]) for p in posts)
        if (now - last).total_seconds() < always["min_seconds_between_posts"]:
            reasons.append("rate limit: too soon after the last post")
    caps = pol["cleared"]
    if req.kind == "case_post" and sum(p["kind"] == "case_post" for p in recent) >= \
            caps["case_post"]["max_per_day"]:
        reasons.append("already made today's case post")
    if req.kind == "lab_update" and sum(p["kind"] == "lab_update" for p in posts
                                        if datetime.fromisoformat(p["ts"]) > week_ago) >= \
            caps["lab_update"]["max_per_week"]:
        reasons.append("already made this week's lab update")
    if req.kind == "ack_reply" and sum(p["kind"] == "ack_reply" for p in recent) >= \
            caps["ack_reply"]["max_per_day"]:
        reasons.append("daily acknowledgment cap reached")
    if reasons:
        return Decision("blocked", reasons + approval)
    if approval:
        return Decision("needs_approval", approval)
    return Decision("allowed", [])


def queue_for_approval(req: PostRequest, decision: Decision) -> Path:
    paths.QUEUE.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    f = paths.QUEUE / f"P-{stamp}-{req.kind}.json"
    f.write_text(json.dumps({"request": asdict(req), "reasons": decision.reasons,
                             "how_to_approve": "post it by hand, or move this file to "
                                               "ops/queue/approved/ for the agent to send"},
                            indent=1))
    return f


def log_post(req: PostRequest, post_id: str, extra: dict | None = None) -> dict:
    row = {"ts": datetime.now(UTC).isoformat(timespec="seconds"), "post_id": post_id,
           "kind": req.kind, "text": req.text, "result_file": req.result_file,
           "experiment": req.experiment, "item": req.item, "reply_to": req.reply_to,
           "thread_root": req.thread_root or post_id, **(extra or {})}
    posts_log().parent.mkdir(parents=True, exist_ok=True)
    with posts_log().open("a") as f:
        f.write(json.dumps(row) + "\n")
    return row
