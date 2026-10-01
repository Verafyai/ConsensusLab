"""The Grok agent: @VerafyAI's voice (spec §9). Posts and collects on a schedule.

    uv run python -m social.agent            # run the schedule (the herdr grok pane)
    uv run python -m social.agent --once     # one pass
    uv run python -m social.agent --dry-run  # compose and check only; never posts

It writes captions with the xAI model (only a reworded reason line; templates carry every
claim), posts through the X API within social/policy.yaml, and collects polls, metrics
and replies. It never runs experiments or touches labels. `touch social/PAUSE` stops posting.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

from lab import paths
from lab.clients.meter import Scope
from social import compose, policy
from social.policy import PostRequest
from social.x import XError

CAPS_FILE = Path(__file__).with_name("x_capabilities.yaml")


def capabilities() -> dict:
    return yaml.safe_load(CAPS_FILE.read_text()) if CAPS_FILE.exists() else {}


def save_capability(key: str, value) -> None:
    caps = capabilities()
    caps[key] = value
    caps["checked"] = datetime.now(UTC).date().isoformat()
    CAPS_FILE.write_text(yaml.safe_dump(caps, sort_keys=True))


class Agent:
    def __init__(self, x, gateway, render_video=None, dry_run: bool = False):
        self.x, self.gw = x, gateway
        self.render_video = render_video
        self.dry_run = dry_run
        self.scope = Scope(track="social", experiment="social")

    # ---------------------------------------------------------------- send
    def _meter_post(self) -> None:
        from lab.clients.base import Usage
        price = self.gw.cfg.service_price("x_post")
        self.gw.meter.reserve(price, self.scope)
        self.gw.meter.record(self.scope, "service:x_post", Usage(), price, cached=False,
                             reserved=price)

    def send(self, req: PostRequest, media_ids: list[str] | None = None) -> dict | None:
        d = policy.check(req)
        if d.status == "needs_approval":
            f = policy.queue_for_approval(req, d)
            print(f"[grok] needs Rex's approval → {f.name}: {'; '.join(d.reasons)}",
                  file=sys.stderr)
            return None
        if not d.allowed:
            print(f"[grok] blocked: {'; '.join(d.reasons)}", file=sys.stderr)
            return None
        if self.dry_run:
            print(f"[grok] DRY RUN, would post ({req.kind}):\n{req.text}\n", file=sys.stderr)
            return {"post_id": "dry-run"}
        self._meter_post()
        data = self.x.create_post(req.text, media_ids=media_ids, poll=req.poll,
                                  reply_to=req.reply_to)
        return policy.log_post(req, data["id"])

    # ---------------------------------------------------------------- case post (§9.3)
    def case_post(self) -> dict | None:
        from social.select import select_case
        t = select_case()
        if t is None:
            print("[grok] no eligible case (flagged items are never auto-selected)",
                  file=sys.stderr)
            return None
        hook = None
        try:
            hook = compose.grok_hook(self.gw, t, self.scope)
        except Exception as e:  # noqa: BLE001 - template alone is fine
            print(f"[grok] hook skipped: {e}", file=sys.stderr)
        text = compose.case_text(t, hook)
        poll_text, poll = compose.poll_text(t)
        req = PostRequest("case_post", text, t["_result_file"], t.get("flags", ["unknown"]),
                          experiment=t["experiment"], item=t["item"])
        pre = policy.check(req)
        if not pre.allowed:
            return self.send(req)            # queues or reports the block
        media_ids = None
        if self.render_video and not self.dry_run:
            mp4 = paths.ROOT / ".cache" / "video" / f"{t['experiment']}__{t['item']}.mp4"
            mp4.parent.mkdir(parents=True, exist_ok=True)
            r = self.render_video(paths.RUNS / t["experiment"] / f"{t['item']}.json.gz", mp4)
            if r["problems"]:
                print(f"[grok] video failed X checks: {r['problems']}", file=sys.stderr)
                return None
            media_ids = [self.x.upload_video(mp4)]
        combined = capabilities().get("poll_with_media")
        if media_ids and combined is not False:
            req.poll = poll
            try:
                row = self.send(req, media_ids)
                if combined is None and row:
                    save_capability("poll_with_media", True)
                return row
            except XError as e:
                if e.status != 400 or "poll" not in json.dumps(e.body).lower():
                    raise
                save_capability("poll_with_media", False)   # verified, not assumed (§9.3)
                req.poll = None
        if not media_ids:
            req.poll = poll                  # no video: the poll goes on the post itself
            return self.send(req)
        root = self.send(req, media_ids)
        if root and root["post_id"] != "dry-run":
            preq = PostRequest("poll_reply", poll_text, t["_result_file"], t.get("flags", []),
                               reply_to=root["post_id"], thread_root=root["post_id"],
                               poll=poll, experiment=t["experiment"], item=t["item"])
            time.sleep(0 if self.dry_run else 1)
            prow = self._send_poll_reply(preq)
            if prow:
                rows = [json.loads(x) for x in policy.posts_log().read_text().splitlines()]
                for r in rows:
                    if r["post_id"] == root["post_id"]:
                        r["poll_post_id"] = prow["post_id"]
                policy.posts_log().write_text("".join(json.dumps(r) + "\n" for r in rows))
        return root

    def _send_poll_reply(self, req: PostRequest) -> dict | None:
        # The thread's poll is part of the cleared case post; the pacing rule between
        # posts doesn't apply to it, every other rule does.
        pol = policy.load_policy()
        pol["always"]["min_seconds_between_posts"] = 0
        d = policy.check(req, policy=pol)
        if not d.allowed:
            print(f"[grok] poll reply not sent: {d.reasons}", file=sys.stderr)
            return None
        self._meter_post()
        data = self.x.create_post(req.text, poll=req.poll, reply_to=req.reply_to)
        return policy.log_post(req, data["id"])

    # ---------------------------------------------------------------- weekly lab update
    def lab_update(self) -> dict | None:
        from lab.orchestrator import learnings
        from lab.scoring import leaderboard
        lb = leaderboard.build(leaderboard.load_results())
        champ = lb.get("champion")
        row = next((r for r in lb["rows"] if r["protocol"] == champ), None)
        if not row or row.get("holdout_macro_f1") is None:
            print("[grok] no champion with holdout results yet", file=sys.stderr)
            return None
        confirmed = [r for r in learnings.load() if r["status"] == "confirmed"]
        lesson = confirmed[-1]["lesson"] if confirmed else "No confirmed lesson yet."
        base = policy.load_policy()["dashboard_base_url"]
        text = compose.lab_update_text(champ, row["holdout_macro_f1"],
                                       row.get("usd_per_item") or 0.0, lesson, base)
        return self.send(PostRequest("lab_update", text, "experiments/leaderboard.json"))

    # ---------------------------------------------------------------- acknowledgments
    def ack(self, post: dict, reply: dict, n: int) -> None:
        url = compose.case_url({"experiment": post.get("experiment"), "item": post.get("item")})
        self.send(PostRequest("ack_reply", compose.ack_text(n, url), post.get("result_file"),
                              reply_to=reply["id"], thread_root=post["post_id"]))


def due(kind: str, now: datetime) -> bool:
    posts = policy.logged_posts()
    if kind == "case_post":
        today = now.date().isoformat()
        return 15 <= now.hour < 18 and not any(p["kind"] == "case_post" and
                                               p["ts"][:10] == today for p in posts)
    if kind == "lab_update":
        return now.weekday() == 0 and 16 <= now.hour < 18 and not any(
            p["kind"] == "lab_update" and (now - datetime.fromisoformat(p["ts"])).days < 6
            for p in posts)
    return False


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", choices=["case_post", "lab_update"])
    a = ap.parse_args(argv)
    from harness.health import Pulse
    from lab.clients.gateway import Gateway
    from social.collect import Collector
    from social.raters import Registry
    from social.x import XClient
    gw = Gateway.default()
    gw.cfg.require_ready([])
    x = XClient()
    from viz.render_video import render
    agent = Agent(x, gw, render, dry_run=a.dry_run)
    col = Collector(x, gw, gw.cfg, Registry(gw.cfg), own_user_id=x.me()["id"])
    with Pulse("grok") as pulse:
        while True:
            now = datetime.now(UTC)
            if paths.PAUSE.exists():
                pulse.state = "paused"
            else:
                pulse.state = "working"
                if a.force == "case_post" or due("case_post", now):
                    agent.case_post()
                if a.force == "lab_update" or due("lab_update", now):
                    agent.lab_update()
                col.collect_metrics(now)
                col.collect_replies(ack=None if a.dry_run else agent.ack)
                pulse.state = "idle"
            if a.once or a.force:
                return 0
            time.sleep(600)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
