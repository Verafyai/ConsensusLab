"""E08 evidence replay: static checks, server path guard, and an optional browser test."""

from __future__ import annotations

import gzip
import json
import shutil
import subprocess
import threading
import urllib.request
from http.client import HTTPConnection
from pathlib import Path

import pytest

from lab.protocols.schema import validate_transcript
from viz.replay.serve import make_server, resolve_request

REPLAY = Path(__file__).resolve().parent.parent / "viz" / "replay"
SAMPLES = sorted((REPLAY / "samples").glob("*.json"))


# --- static ---------------------------------------------------------------------------------

def test_static_files_exist():
    for name in ("index.html", "replay.js", "replay.css", "text.js", "serve.py", "__init__.py"):
        assert (REPLAY / name).is_file(), name
    html = (REPLAY / "index.html").read_text()
    assert 'type="module"' in html and "replay.js" in html
    # No external network dependencies.
    for f in ("index.html", "replay.js", "replay.css", "text.js"):
        text = (REPLAY / f).read_text()
        assert "http://" not in text.replace("http://www.w3.org/2000/svg", "")
        assert "https://" not in text


def test_samples_validate_and_cover_patterns():
    assert len(SAMPLES) >= 3
    protocols, mismatches = set(), 0
    for p in SAMPLES:
        t = validate_transcript(json.loads(p.read_text()))
        protocols.add(t["protocol"])
        for ev in t["evidence"]:
            assert len(ev["excerpt"].rstrip("…").split()) <= 40, (p.name, ev["id"])
        if t.get("gold") and t["gold"] != t["verdict"]:
            mismatches += 1
    assert mismatches >= 1
    assert any(p.startswith("society") or p.startswith("panel") for p in protocols)
    assert any(p.startswith("evidence-first") for p in protocols)


def test_renderer_caps_excerpts_at_40_words():
    js = (REPLAY / "replay.js").read_text()
    assert "capWords(e.excerpt, MAX_EXCERPT_WORDS)" in js
    assert "MAX_EXCERPT_WORDS = 40" in (REPLAY / "text.js").read_text()
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed; JS unit check skipped")
    script = (
        f"import('{(REPLAY / 'text.js').as_uri()}').then(m => {{"
        "  const long = Array.from({length: 75}, (_, i) => 'w' + i).join(' ');"
        "  const out = m.capWords(long, m.MAX_EXCERPT_WORDS);"
        "  const short = m.capWords('a b c');"
        "  console.log(JSON.stringify({n: m.wordCount(out), end: out.endsWith('…'),"
        "    short, exact: m.capWords(long.split(' ').slice(0, 40).join(' '))"
        "      .split(' ').length}));"
        "});"
    )
    res = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True,
                         text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    assert out["n"] == 40 and out["end"] and out["short"] == "a b c" and out["exact"] == 40


def test_variant_and_captions_hooks():
    js = (REPLAY / "replay.js").read_text()
    assert "new URL(`../variants/${opts.variant}.css`, location.href)" in js
    assert "/^[a-z0-9-]{1,40}$/" in js
    assert 'params.get("captions") === "1"' in js and "window.__captions" in js


# --- server ---------------------------------------------------------------------------------

@pytest.fixture
def site(tmp_path: Path):
    (tmp_path / ".env").write_text("SECRET=1\n")
    (tmp_path / "ops").mkdir()
    (tmp_path / "ops" / "heartbeat.json").write_text("{}")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "models.yaml").write_text("x: 1\n")
    (tmp_path / "viz" / "replay").mkdir(parents=True)
    (tmp_path / "viz" / "replay" / "index.html").write_text("<!doctype html><title>r</title>")
    (tmp_path / "viz" / ".env").write_text("SECRET=2\n")
    run = tmp_path / "runs" / "E-0001"
    run.mkdir(parents=True)
    payload = {"item": "q-1", "verdict": "refuted"}
    (run / "q-1.json.gz").write_bytes(gzip.compress(json.dumps(payload).encode()))
    srv = make_server(tmp_path, 0, verbose=False)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield tmp_path, srv.server_address[1], payload
    srv.shutdown()
    srv.server_close()


def _get(port: int, raw_path: str) -> tuple[int, bytes, str]:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", raw_path)       # raw path: http.client does not normalise '..'
    r = conn.getresponse()
    body = r.read()
    conn.close()
    return r.status, body, r.getheader("Content-Type") or ""


@pytest.mark.parametrize("path", [
    "/.env", "/ops/heartbeat.json", "/config/models.yaml", "/viz/../ops/heartbeat.json",
    "/viz/%2e%2e/ops/heartbeat.json", "/viz/..%2f.env", "/../.env", "/viz/.env",
    "/data/x.json", "/t/E-0001/..", "/t/../q-1", "/runs/E-0001/../../.env",
])
def test_server_refuses(site, path):
    _, port, _ = site
    status, body, _ = _get(port, path)
    assert status in (403, 404)
    assert b"SECRET" not in body


def test_server_serves_allowed_and_transcripts(site):
    root, port, payload = site
    status, body, ctype = _get(port, "/viz/replay/index.html")
    assert status == 200 and b"<title>r</title>" in body and "text/html" in ctype
    status, body, _ = _get(port, "/viz/replay/")
    assert status == 200 and b"<title>r</title>" in body
    status, body, ctype = _get(port, "/t/E-0001/q-1")
    assert status == 200 and "application/json" in ctype
    assert json.loads(body) == payload
    assert _get(port, "/t/E-0001/q-1.json")[0] == 200
    assert _get(port, "/t/E-0001/missing")[0] == 404
    assert resolve_request(root, "/viz/x.js?t=../../runs/a.json") is not None
    assert resolve_request(root, "/library/cards/a.md") is not None
    assert resolve_request(root, "/library/other/a.md") is None
    assert resolve_request(root, "/experiments/E-0001/protocol.yaml") is not None


# --- browser (optional) -------------------------------------------------------------------

@pytest.fixture(scope="module")
def browser_site():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    srv = make_server(REPLAY.parent.parent, 0, verbose=False)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/viz/replay/"
    with urllib.request.urlopen(base) as r:
        assert r.status == 200
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.launch()
    except Exception as e:  # noqa: BLE001 - any launch failure means no browser here
        pw.stop()
        srv.shutdown()
        pytest.skip(f"chromium not available: {e}")
    yield browser, base
    browser.close()
    pw.stop()
    srv.shutdown()
    srv.server_close()


def test_browser_card_mode(browser_site):
    browser, base = browser_site
    page = browser.new_page(viewport={"width": 1080, "height": 1080})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{base}?mode=card&aspect=square")
    page.wait_for_selector("body[data-ready='1']", timeout=15000)
    t = json.loads((REPLAY / "samples" / "debate-sample.json").read_text())
    for text in ("Refuted", f"{round(t['confidence'] * 100)}%", t["reasons"][0], t["reasons"][1],
                 "4 sources", "Human fact-checkers"):
        assert page.get_by_text(text, exact=False).first.is_visible(), text
    # Card mode shows only the card: no evidence excerpts or turns.
    assert page.locator(".ev, .turn").count() == 0
    assert not errors, errors
    page.close()


def test_browser_autoplay_finishes(browser_site):
    browser, base = browser_site
    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{base}?autoplay=1&aspect=wide")
    page.wait_for_selector("body[data-done='1']", timeout=60000)
    assert page.locator(".verdict").is_visible()
    # The renderer never shows more than 40 words of any excerpt.
    counts = page.eval_on_selector_all(
        ".ev-excerpt", "els => els.map(e => e.textContent.trim().split(/\\s+/).length)")
    assert counts and max(counts) <= 40
    assert not errors, errors
    page.close()


@pytest.mark.parametrize("sample", ["debate", "society", "evidence-first"])
def test_browser_phone_no_horizontal_scroll(browser_site, sample):
    browser, base = browser_site
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(f"{base}?t=samples/{sample}-sample.json")
    page.wait_for_selector(".controls button")
    page.keyboard.press("End")
    page.wait_for_timeout(300)
    assert page.evaluate("document.documentElement.scrollWidth") <= 390
    size = page.eval_on_selector(".turn-text", "e => parseFloat(getComputedStyle(e).fontSize)")
    assert size >= 15
    page.goto(f"{base}?t=samples/{sample}-sample.json&mode=card")
    page.wait_for_selector("body[data-ready='1']")
    assert page.evaluate("document.documentElement.scrollWidth") <= 390
    page.close()


@pytest.mark.parametrize("aspect,size", [("square", (720, 720)), ("wide", (1280, 720))])
def test_browser_captions_at_video_sizes(browser_site, aspect, size):
    browser, base = browser_site
    w, h = size
    page = browser.new_page(viewport={"width": w, "height": h})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{base}?autoplay=1&captions=1&aspect={aspect}")
    page.wait_for_selector("body[data-done='1']", timeout=60000)
    caps = page.evaluate("window.__captions")
    texts = [c["text"] for c in caps]
    assert texts[0] == "The claim" and "4 sources found" in texts
    assert "Judge rules (Claude)" in texts
    assert texts[-1].startswith("Verdict: Refuted, 93%") and "Human experts: Refuted" in texts[-1]
    assert all(c["end_ms"] is not None and c["end_ms"] >= c["start_ms"] for c in caps)
    assert all(a["end_ms"] == b["start_ms"] for a, b in zip(caps, caps[1:], strict=False))
    box = page.locator(".caption").bounding_box()
    font = page.eval_on_selector(".caption-text", "e => parseFloat(getComputedStyle(e).fontSize)")
    scale = box["width"] / w                    # caption spans the full (scaled) frame width
    assert box["y"] + box["height"] <= h + 1 and box["height"] <= h * 0.25
    assert font * scale >= 0.04 * h
    # The whole design fits the video frame: the stage is scaled into the viewport.
    stage = page.locator("#app").bounding_box()
    assert stage["width"] <= w + 1 and stage["height"] <= h + 1
    assert not errors, errors
    page.close()


def test_browser_captions_off_by_default(browser_site):
    browser, base = browser_site
    page = browser.new_page(viewport={"width": 1280, "height": 720})
    page.goto(f"{base}?aspect=wide")
    page.wait_for_selector(".controls button", state="attached")
    assert page.locator(".caption").count() == 0
    page.close()


def test_browser_connectors_drawn_when_scaled(browser_site):
    browser, base = browser_site
    page = browser.new_page(viewport={"width": 720, "height": 720})
    page.goto(f"{base}?aspect=square&captions=1")
    page.wait_for_selector(".controls button", state="attached")
    for _ in range(6):                      # past the claim and 4 sources, to turn 2
        page.keyboard.press("ArrowRight")
    page.wait_for_timeout(1300)
    assert page.locator("svg.links path").count() == 3      # turn 2 cites ev1, ev3, ev4
    assert page.eval_on_selector("svg.links", "e => getComputedStyle(e).display") != "none"
    page.close()
