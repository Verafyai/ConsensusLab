"""Hosted rating page with Sign in with X (spec §6.4, E17). Hosting is GATE G-006.

    X_CLIENT_ID=... RATEPAGE_URL=https://rate.example.org RATEPAGE_SECRET=... \
        uv run python -m social.ratepage --port 8780

OAuth 2.0 authorization code flow with PKCE. Raters sign in, then see a mix of live cases
and rotating calibration cases (expert verdict known to the lab, never shown). They vote
RIGHT or WRONG with an optional reason. Votes carry identity, so they can be weighted.
Nobody ever sees a weight, their own included.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import os
import random
import secrets
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from social.raters import Rating, Registry

AUTHORIZE = "https://x.com/i/oauth2/authorize"
TOKEN = "https://api.x.com/2/oauth2/token"
ME = "https://api.x.com/2/users/me?user.fields=created_at,public_metrics,verified_type"
CALIBRATION_EVERY = 3        # one calibration case in every three shown


def pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()) \
        .decode().rstrip("=")
    return verifier, challenge


def calibration_pool(cases: list[dict], week: str, k: int = 30) -> list[dict]:
    """Rotate calibration cases weekly so they can't be memorized and shared."""
    pool = [c for c in cases if c.get("gold") and c["verdict"] != "abstain"]
    rnd = random.Random(f"calibration:{week}")
    return rnd.sample(pool, min(k, len(pool)))


class RatePage:
    def __init__(self, registry: Registry, cases_fn, client_id: str, base_url: str,
                 secret: bytes, transport: httpx.BaseTransport | None = None):
        self.reg, self.cases_fn = registry, cases_fn
        self.client_id, self.base_url, self.secret = client_id, base_url.rstrip("/"), secret
        self.http = httpx.Client(timeout=20, transport=transport)
        self.pending: dict[str, tuple[str, float]] = {}       # state -> (verifier, created)
        self.shown: dict[str, int] = {}

    # ---- session cookies (HMAC-signed rater id)
    def cookie(self, rid: str) -> str:
        sig = hmac.new(self.secret, rid.encode(), hashlib.sha256).hexdigest()[:32]
        return f"{rid}.{sig}"

    def rater_from_cookie(self, value: str | None) -> str | None:
        if not value or "." not in value:
            return None
        rid, sig = value.rsplit(".", 1)
        good = hmac.new(self.secret, rid.encode(), hashlib.sha256).hexdigest()[:32]
        return rid if hmac.compare_digest(sig, good) else None

    # ---- OAuth
    def login_url(self) -> str:
        state = secrets.token_urlsafe(24)
        verifier, challenge = pkce()
        self.pending[state] = (verifier, time.time())
        return AUTHORIZE + "?" + urlencode({
            "response_type": "code", "client_id": self.client_id,
            "redirect_uri": f"{self.base_url}/callback", "scope": "users.read tweet.read",
            "state": state, "code_challenge": challenge, "code_challenge_method": "S256"})

    def callback(self, code: str, state: str) -> str:
        verifier, created = self.pending.pop(state, (None, 0))
        if not verifier or time.time() - created > 600:
            raise PermissionError("sign-in expired; try again")
        tok = self.http.post(TOKEN, data={
            "grant_type": "authorization_code", "code": code, "client_id": self.client_id,
            "redirect_uri": f"{self.base_url}/callback", "code_verifier": verifier})
        tok.raise_for_status()
        me = self.http.get(ME, headers={"Authorization": f"Bearer {tok.json()['access_token']}"})
        me.raise_for_status()
        u = me.json()["data"]
        pm = u.get("public_metrics", {})
        self.reg.upsert(u["id"], created_at=(u.get("created_at") or "").replace("Z", "+00:00")
                        or None, posts=pm.get("tweet_count"),
                        followers=pm.get("followers_count"),
                        automated=u.get("verified_type") == "automated")
        self.reg.save()
        return u["id"]

    # ---- rating flow
    def next_case(self, rid: str) -> tuple[dict, bool]:
        n = self.shown.get(rid, 0)
        self.shown[rid] = n + 1
        cases = self.cases_fn()
        rated = {r.case for r in self.reg.ratings if r.rater == rid}
        week = datetime.now(UTC).strftime("%G-W%V")
        if n % CALIBRATION_EVERY == CALIBRATION_EVERY - 1:
            pool = [c for c in calibration_pool(cases, week)
                    if f"{c['experiment']}/{c['item']}" not in rated]
            if pool:
                return pool[0], True
        live = [c for c in cases if f"{c['experiment']}/{c['item']}" not in rated]
        return (live[0], False) if live else ({}, False)

    def rate(self, rid: str, case_key: str, vote: int, reason: str, calibration: bool) -> None:
        cases = {f"{c['experiment']}/{c['item']}": c for c in self.cases_fn()}
        c = cases.get(case_key)
        if c is None or vote not in (0, 1):
            raise ValueError("unknown case")
        self.reg.add(Rating(rid, case_key, vote, datetime.now(UTC).isoformat(timespec="seconds"),
                            "page", calibration=calibration, reason=reason[:300]),
                     gold=c.get("gold") if calibration else None,
                     panel_verdict=c["verdict"] if calibration else None)
        self.reg.save()

    @staticmethod
    def render_case(c: dict, calibration: bool) -> str:
        """The rater sees the claim and the panel's call, never the expert verdict or any
        weight. Calibration cases look exactly like live ones."""
        key = f"{c['experiment']}/{c['item']}"
        reasons = "".join(f"<li>{html.escape(r)}</li>" for r in c.get("reasons", []))
        return (f"<article><h2>{html.escape(c['question'])}</h2>"
                f"<p>The AI panel says: <b>{html.escape(c['verdict'])}</b> "
                f"({round(c['confidence'] * 100)}%)</p><ul>{reasons}</ul>"
                f"<form method=post action=/rate><input type=hidden name=case value='"
                f"{html.escape(key)}'><input type=hidden name=c value="
                f"'{int(calibration)}'><textarea name=reason maxlength=300 "
                f"placeholder='Why? (optional)'></textarea>"
                f"<button name=vote value=1>RIGHT</button>"
                f"<button name=vote value=0>WRONG</button></form></article>")


def handler_for(page: RatePage):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _html(self, body: str, code=200, headers=None):
            b = f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-" \
                f"width'><title>Rate the AI panel</title><body>{body}</body>".encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(b)

        def _rid(self):
            for part in (self.headers.get("Cookie") or "").split(";"):
                k, _, v = part.strip().partition("=")
                if k == "rater":
                    return page.rater_from_cookie(v)
            return None

        def do_GET(self):  # noqa: N802
            u = urlparse(self.path)
            if u.path == "/login":
                self.send_response(302)
                self.send_header("Location", page.login_url())
                return self.end_headers()
            if u.path == "/callback":
                q = parse_qs(u.query)
                try:
                    rid = page.callback(q["code"][0], q["state"][0])
                except Exception as e:  # noqa: BLE001
                    return self._html(f"<p>{html.escape(str(e))}</p>", 400)
                return self._html("<p>Signed in. <a href=/>Start rating</a></p>", 200,
                                  {"Set-Cookie": f"rater={page.cookie(rid)}; HttpOnly; Secure;"
                                                 " SameSite=Lax; Path=/"})
            rid = self._rid()
            if not rid:
                return self._html("<h1>Did the AI panel get it right?</h1>"
                                  "<p><a href=/login>Sign in with X</a> to rate.</p>")
            c, cal = page.next_case(rid)
            if not c:
                return self._html("<p>No cases to rate right now. Thanks!</p>")
            return self._html(page.render_case(c, cal))

        def do_POST(self):  # noqa: N802
            rid = self._rid()
            if not rid:
                return self._html("<p>Please sign in.</p>", 403)
            n = int(self.headers.get("Content-Length") or 0)
            f = parse_qs(self.rfile.read(min(n, 10_000)).decode())
            try:
                page.rate(rid, f["case"][0], int(f["vote"][0]), f.get("reason", [""])[0],
                          f.get("c", ["0"])[0] == "1")
            except (KeyError, ValueError) as e:
                return self._html(f"<p>{html.escape(str(e))}</p>", 400)
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
    return H


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8780)
    a = ap.parse_args()
    from lab.config import get
    from lab.scoring import leaderboard
    from viz.dashboard.data import cases_view
    page = RatePage(Registry(get()), lambda: cases_view(leaderboard.load_results()),
                    os.environ["X_CLIENT_ID"], os.environ["RATEPAGE_URL"],
                    os.environ["RATEPAGE_SECRET"].encode())
    ThreadingHTTPServer(("0.0.0.0", a.port), handler_for(page)).serve_forever()


if __name__ == "__main__":
    main()
