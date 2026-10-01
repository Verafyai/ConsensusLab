"""Minimal X API v2 client for @VerafyAI (spec §9). OAuth 1.0a user context.

Only the calls the clearance policy permits are implemented: create a post (optionally
with media, a poll, or as a reply in the lab's own thread), upload video, and read posts,
metrics and replies. There is deliberately no like, follow, DM, quote or delete.
Credentials come from .env and are never logged.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.parse
from pathlib import Path
from typing import Any

import httpx

API = "https://api.x.com"


class XError(RuntimeError):
    def __init__(self, status: int, body: Any):
        self.status, self.body = status, body
        super().__init__(f"X API {status}: {json.dumps(body)[:300]}")


def _pct(s: str) -> str:
    return urllib.parse.quote(s, safe="~-._")


def oauth1_header(method: str, url: str, params: dict[str, str], key: str, secret: str,
                  token: str, token_secret: str, nonce: str | None = None,
                  timestamp: str | None = None) -> str:
    """RFC 5849 HMAC-SHA1 Authorization header. `params` = query + form params (not JSON)."""
    oauth = {"oauth_consumer_key": key, "oauth_nonce": nonce or secrets.token_hex(16),
             "oauth_signature_method": "HMAC-SHA1",
             "oauth_timestamp": timestamp or str(int(time.time())),
             "oauth_token": token, "oauth_version": "1.0"}
    allp = {**params, **oauth}
    base_params = "&".join(f"{_pct(k)}={_pct(v)}" for k, v in sorted(allp.items()))
    base_url = url.split("?")[0]
    base = "&".join([method.upper(), _pct(base_url), _pct(base_params)])
    signing_key = f"{_pct(secret)}&{_pct(token_secret)}"
    sig = base64.b64encode(hmac.new(signing_key.encode(), base.encode(),
                                    hashlib.sha1).digest()).decode()
    oauth["oauth_signature"] = sig
    return "OAuth " + ", ".join(f'{_pct(k)}="{_pct(v)}"' for k, v in sorted(oauth.items()))


class XClient:
    def __init__(self, transport: httpx.BaseTransport | None = None,
                 creds: dict[str, str] | None = None, sleep=time.sleep):
        c = creds or {k: os.environ.get(k, "") for k in
                      ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")}
        missing = [k for k, v in c.items() if not v]
        if missing:
            raise RuntimeError(f"X credentials missing: {', '.join(missing)} (ops/queue/G-005)")
        self.c = c
        self.http = httpx.Client(timeout=60.0, transport=transport)
        self.sleep = sleep

    def _auth(self, method: str, url: str, params: dict[str, str] | None = None) -> dict:
        return {"Authorization": oauth1_header(method, url, params or {}, self.c["X_API_KEY"],
                                               self.c["X_API_SECRET"], self.c["X_ACCESS_TOKEN"],
                                               self.c["X_ACCESS_TOKEN_SECRET"])}

    def _req(self, method: str, path: str, *, params: dict | None = None, json_body=None,
             files=None, data=None) -> dict:
        url = API + path
        q = {k: str(v) for k, v in (params or {}).items()}
        # OAuth 1.0a signs query params; JSON and multipart bodies are not part of the base.
        r = self.http.request(method, url, params=q or None, json=json_body, files=files,
                              data=data, headers=self._auth(method, url, q))
        try:
            body = r.json() if r.content else {}
        except ValueError:
            body = {"raw": r.text[:300]}
        if r.status_code >= 400:
            raise XError(r.status_code, body)
        return body

    # ---------------------------------------------------------------- writes
    def create_post(self, text: str, media_ids: list[str] | None = None,
                    poll: dict | None = None, reply_to: str | None = None,
                    made_with_ai: bool = True) -> dict:
        body: dict[str, Any] = {"text": text}
        if media_ids:
            body["media"] = {"media_ids": media_ids}
        if poll:
            body["poll"] = poll
        if reply_to:
            body["reply"] = {"in_reply_to_tweet_id": reply_to}
        if made_with_ai and media_ids:
            body["made_with_ai"] = True
        return self._req("POST", "/2/tweets", json_body=body)["data"]

    def upload_video(self, path: Path, category: str = "tweet_video",
                     chunk: int = 4 * 1024 * 1024) -> str:
        data = path.read_bytes()
        init = self._req("POST", "/2/media/upload/initialize", json_body={
            "media_type": "video/mp4", "total_bytes": len(data), "media_category": category})
        mid = init["data"]["id"]
        for i in range(0, len(data), chunk):
            self._req("POST", f"/2/media/upload/{mid}/append",
                      data={"segment_index": str(i // chunk)},
                      files={"media": ("chunk", data[i:i + chunk], "application/octet-stream")})
        fin = self._req("POST", f"/2/media/upload/{mid}/finalize")
        info = fin.get("data", {}).get("processing_info")
        while info and info.get("state") in ("pending", "in_progress"):
            self.sleep(info.get("check_after_secs", 3))
            st = self._req("GET", "/2/media/upload", params={"command": "STATUS",
                                                               "media_id": mid})
            info = st.get("data", {}).get("processing_info")
        if info and info.get("state") == "failed":
            raise XError(422, info)
        return mid

    # ---------------------------------------------------------------- reads
    def get_post(self, post_id: str) -> dict:
        return self._req("GET", f"/2/tweets/{post_id}", params={
            "tweet.fields": "public_metrics,non_public_metrics,organic_metrics,created_at,"
                            "conversation_id,attachments",
            "expansions": "attachments.poll_ids", "poll.fields": "options,voting_status"})

    def replies(self, conversation_id: str, max_results: int = 100) -> list[dict]:
        r = self._req("GET", "/2/tweets/search/recent", params={
            "query": f"conversation_id:{conversation_id}", "max_results": max_results,
            "tweet.fields": "author_id,created_at,in_reply_to_user_id,conversation_id",
            "expansions": "author_id",
            "user.fields": "created_at,public_metrics,verified_type,affiliation"})
        users = {u["id"]: u for u in r.get("includes", {}).get("users", [])}
        return [{**t, "author": users.get(t.get("author_id"), {})} for t in r.get("data", [])]

    def me(self) -> dict:
        return self._req("GET", "/2/users/me", params={"user.fields": "id,username"})["data"]
