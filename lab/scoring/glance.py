"""Glanceability: the five-second test (spec §6.1.3). Track B.

Render the still evidence card as an image, give a vision model ONLY that image, and ask
for the verdict, the confidence and the main reason. The score is the fraction of those
three it recovers. If a model can't read it off the card, a scrolling human won't either.
"""

from __future__ import annotations

import base64
import contextlib
import re
import threading
from pathlib import Path

GLANCE_PROMPT = (
    "This image is a fact-check card. Look only at the image. Report what it says: the "
    "verdict, the confidence as a number from 0 to 1 (null if you can't find one), and the "
    "main reason in a short phrase. If something isn't readable, say 'unclear'.")


def glance_schema(labels: list[str]) -> dict:
    return {"type": "object", "additionalProperties": False,
            "required": ["verdict", "confidence", "main_reason"],
            "properties": {"verdict": {"enum": list(labels) + ["unclear"]},
                           "confidence": {"type": ["number", "null"]},
                           "main_reason": {"type": "string"}}}


_TOK = re.compile(r"[a-z0-9]+")
_STOP = set("the a an of to in and or is are was were be for on at by with that this it as from"
            " than".split())


def _terms(s: str) -> set[str]:
    return {t for t in _TOK.findall(s.lower()) if t not in _STOP}


def reason_match(read: str, reasons: list[str], threshold: float = 0.4) -> bool:
    """Recovered if the phrase read off the card shares at least two content words with one
    of the transcript's two reasons, covering enough of the shorter of the two."""
    r = _terms(read)
    for reason in reasons:
        t = _terms(reason)
        shared = r & t
        if len(shared) >= 2 and len(shared) / min(len(r), len(t)) >= threshold:
            return True
    return False


def grade(read: dict, transcript: dict, conf_tol: float = 0.1) -> dict:
    v_ok = read.get("verdict") == transcript["verdict"]
    c = read.get("confidence")
    if isinstance(c, int | float) and c > 1:
        c = c / 100.0
    c_ok = isinstance(c, int | float) and abs(c - transcript["confidence"]) <= conf_tol
    r_ok = reason_match(str(read.get("main_reason", "")), transcript.get("reasons", []))
    return {"verdict": v_ok, "confidence": c_ok, "main_reason": r_ok,
            "glance": (v_ok + c_ok + r_ok) / 3}


@contextlib.contextmanager
def card_server():
    """The dashboard server on a free localhost port (it serves /replay/)."""
    from viz.dashboard.server import serve
    srv = serve(0)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()


def render_card(transcript: dict, out_png: Path, variant: str | None = None,
                size: int = 1080, base_url: str | None = None) -> Path:
    """Screenshot ?mode=card for one transcript. The transcript is injected by request
    interception, so holdout or unsaved transcripts never need to be served."""
    import json

    from playwright.sync_api import sync_playwright
    ctx = card_server() if base_url is None else contextlib.nullcontext(base_url)
    with ctx as base, sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": size, "height": size})
        page.route("**/__card_transcript.json", lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(transcript)))
        url = f"{base}/replay/index.html?mode=card&aspect=square&t=/__card_transcript.json"
        if variant:
            url += f"&variant={variant}"
        page.goto(url)
        page.wait_for_selector("body[data-ready='1']", timeout=20_000)
        out_png.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out_png))
        browser.close()
    return out_png


def read_card(gateway, png: Path, labels: list[str], scope) -> dict:
    from lab.clients.base import Request
    alias = gateway.cfg.models.get("roles", {}).get("glance_reader", "claude-haiku")
    img = base64.standard_b64encode(png.read_bytes()).decode()
    r = gateway.call(Request(model=alias, max_tokens=400, json_schema=glance_schema(labels),
                             messages=[{"role": "user", "content": [
                                 {"type": "image", "source": {"type": "base64",
                                                              "media_type": "image/png",
                                                              "data": img}},
                                 {"type": "text", "text": GLANCE_PROMPT}]}]), scope)
    d = r.data if isinstance(r.data, dict) else {}
    return {**d, "usd": r.usd}


def five_second_test(gateway, transcript: dict, scope, out_png: Path,
                     variant: str | None = None, conf_tol: float = 0.1) -> dict:
    render_card(transcript, out_png, variant)
    read = read_card(gateway, out_png, transcript["label_set"], scope)
    return {"read": read, **grade(read, transcript, conf_tol)}
