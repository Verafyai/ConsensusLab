"""E09: dashboard frontend (spec §8.2, §8.3).

Static checks on viz/dashboard/index.html + static/, API checks against a running demo
server (offline demo lab, no spend), and a Playwright browser pass (skipped when Playwright
or Chromium isn't available).
"""

from __future__ import annotations

import functools
import http.client
import json
import os
import re
import shutil
import threading
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from lab import config, paths
from viz.dashboard import server  # import before the demo repoints lab.paths

DASH = Path(__file__).resolve().parents[1] / "viz" / "dashboard"
TABS = ["overview", "season0", "leaderboard", "disagreement", "trends", "experiments", "cases",
        "zones", "social", "learnings", "budget"]
PATH_ATTRS = ["ROOT", "EXPERIMENTS", "LEARNINGS", "OPS", "QUEUE", "STOP", "EVENTS", "HEARTBEAT",
              "RUNS", "SOCIAL", "LEDGER_SPEND", "CONFIG"]


# ------------------------------------------------------------------ static checks
def _frontend_files() -> list[Path]:
    return [DASH / "index.html", *sorted((DASH / "static").rglob("*.*"))]


def test_index_exists_and_loads_local_assets():
    html = (DASH / "index.html").read_text()
    assert "./static/app.js" in html and "./static/style.css" in html
    for f in ("app.js", "views.js", "charts.js", "controls.js", "util.js", "style.css"):
        assert (DASH / "static" / f).is_file(), f


def test_no_external_urls():
    """No CDN, font or other network request: the only absolute URL allowed is the SVG
    namespace identifier, which is never fetched."""
    for f in _frontend_files():
        text = f.read_text()
        for m in re.finditer(r"https?://[^\s\"'`)]+", text):
            assert m.group(0) == "http://www.w3.org/2000/svg", f"{f.name}: {m.group(0)}"
        assert "@import" not in text and "fonts.googleapis" not in text


# ------------------------------------------------------------------ demo server
@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    import lab.zones as zmod
    from viz.dashboard import demo as demo_mod

    saved = {a: getattr(paths, a) for a in PATH_ATTRS}
    saved_zones, saved_env = zmod.ZONES, os.environ.get("CL_HOLDOUT_DIR")
    root = tmp_path_factory.mktemp("dash") / "lab"
    try:
        demo_mod.build(root)                     # repoints lab.paths at the demo lab
        paths.CONFIG = root / "tmp" / "config"   # the filled test config the demo ran with
        config.get.cache_clear()
        srv = server.serve(0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        from viz.dashboard.data import snapshot
        static_snap = snapshot(local=False)
        yield {"root": root, "base": f"http://127.0.0.1:{srv.server_address[1]}",
               "port": srv.server_address[1], "static_snap": static_snap}
        srv.shutdown()
    finally:
        for a, v in saved.items():
            setattr(paths, a, v)
        zmod.ZONES = saved_zones
        if saved_env is None:
            os.environ.pop("CL_HOLDOUT_DIR", None)
        else:
            os.environ["CL_HOLDOUT_DIR"] = saved_env
        config.get.cache_clear()


def _get(base, path):
    with urllib.request.urlopen(base + path) as r:
        return r.status, r.read()


def _post(base, path, body, lab_header=True):
    headers = {"Content-Type": "application/json"}
    if lab_header:
        headers["X-Lab"] = "1"
    req = urllib.request.Request(base + path, json.dumps(body).encode(), headers)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def _raw_get(port, path) -> int:
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request("GET", path)
    code = c.getresponse().status
    c.close()
    return code


# ------------------------------------------------------------------ API checks
def test_api_data_and_page_served(demo):
    code, body = _get(demo["base"], "/api/data")
    d = json.loads(body)
    assert code == 200 and d["local"] is True
    assert d["headline"] and d["leaderboard"]["rows"]
    code, html = _get(demo["base"], "/")
    assert code == 200 and b"static/app.js" in html
    code, js = _get(demo["base"], "/static/app.js")
    assert code == 200 and b"/api/data" in js


def test_rate_requires_header_and_appends(demo):
    d = json.loads(_get(demo["base"], "/api/data")[1])
    c = d["cases"][0]
    body = {"experiment": c["experiment"], "item": c["item"], "protocol": c["protocol"],
            "thumb": "up", "note": "api test"}
    code, _ = _post(demo["base"], "/api/rate", body, lab_header=False)
    assert code == 403
    f = demo["root"] / "ratings.jsonl"
    before = len(f.read_text().splitlines()) if f.exists() else 0
    code, out = _post(demo["base"], "/api/rate", body)
    assert code == 200 and out["ok"] is True
    lines = f.read_text().splitlines()
    assert len(lines) == before + 1 and json.loads(lines[-1])["note"] == "api test"


def test_estimate_ok_and_over_cap_refused(demo):
    code, est = _post(demo["base"], "/api/estimate",
                      {"zone": "Z1", "sub": "with-evidence", "knobs": {}, "n": 100})
    assert code == 200, est
    assert est["ok"] is True and est["token"] and est["estimate_usd"] > 0
    big = {"zone": "Z1", "sub": "with-evidence", "knobs": {}, "n": 10_000_000}
    code, est = _post(demo["base"], "/api/estimate", big)
    assert code == 200 and est["ok"] is False and "token" not in est
    assert any("cap" in p for p in est["problems"])
    code, out = _post(demo["base"], "/api/run", {**big, "confirm": True, "token": "forged"})
    assert code == 403 and "cap" in out["error"]


def test_compare_returns_pairs_with_ci(demo):
    rows = json.loads(_get(demo["base"], "/api/data")[1])["leaderboard"]["rows"]
    ids = [r["protocol"] for r in rows if r.get("dev_n")][:2]
    code, out = _post(demo["base"], "/api/compare", {"protocols": ids, "resamples": 300})
    assert code == 200, out
    assert out["pairs"] and len(out["pairs"][0]["ci"]) == 2
    assert set(out["metrics"]) == set(ids)


def test_arena_needs_confirm(demo):
    code, out = _post(demo["base"], "/api/arena", {"experiment": "E-0005"})
    assert code == 200 and out["needs_confirm"] is True
    assert "holdout evaluations" in out["message"]


def test_traversal_and_dotfiles_404(demo):
    for p in ["/t/../../etc/passwd", "/t/..%2F..%2Fetc/passwd", "/files/.env",
              "/files/../pyproject.toml", "/files/experiments/../../.env", "/static/../server.py"]:
        assert _raw_get(demo["port"], p) == 404, p


# ------------------------------------------------------------------ browser checks
@pytest.fixture(scope="module")
def browser():
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"chromium can't launch: {e}")
        yield b
        b.close()


OVERFLOW_JS = """() => {
  // elements wider than the viewport that aren't inside their own scroll container
  const W = window.innerWidth, bad = [];
  const scroller = (el) => { for (let p = el.parentElement; p; p = p.parentElement) {
    const o = getComputedStyle(p).overflowX; if (o === 'auto' || o === 'scroll') return true; } return false; };  # noqa: E501
  for (const el of document.querySelectorAll('section.view.active *, header *')) {
    const r = el.getBoundingClientRect();
    if (r.width && r.right > W + 1 && !scroller(el)) bad.push(el.tagName + '.' + el.className);
  }
  return {sw: document.documentElement.scrollWidth, bad: bad.slice(0, 5)};
}"""


def test_browser_local(demo, browser):
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(demo["base"] + "/")
    page.wait_for_selector("#headline")
    assert "Champion" in page.inner_text("#headline")
    page.wait_for_function("document.querySelectorAll('#view-overview svg circle.pt').length > 0")
    assert page.locator("#view-overview svg circle.pt").count() >= 5
    # controls exist locally
    assert page.locator('nav.tabs a[data-tab="controls"]').count() == 1

    # thumbs up on the first case -> POST /api/rate -> a line in ratings.jsonl
    f = demo["root"] / "ratings.jsonl"
    before = len(f.read_text().splitlines()) if f.exists() else 0
    page.goto(demo["base"] + "/#cases")
    page.wait_for_selector("#case-list .thumb-up")
    with page.expect_request(lambda r: r.url.endswith("/api/rate") and r.method == "POST") as req:
        page.locator("#case-list .thumb-up").first.click()
    assert req.value.headers.get("x-lab") == "1"
    assert json.loads(req.value.post_data)["thumb"] == "up"
    page.wait_for_selector("#case-list .case >> text=Saved")
    assert len(f.read_text().splitlines()) == before + 1

    # replay links point at the replay app with a /t/ transcript
    href = page.locator("#case-list a.replay-link").first.get_attribute("href")
    assert re.match(r"^/replay/index\.html\?t=/t/E-\d{4}/[\w.-]+$", href), href

    # estimate flow shows the server's number before confirm
    page.goto(demo["base"] + "/#controls")
    page.wait_for_selector("#run-estimate")
    assert page.locator("#run-confirm").is_disabled()
    page.click("#run-estimate")
    page.wait_for_selector("#run-estimate-result")
    assert "$" in page.inner_text("#run-estimate-result")
    assert page.locator("#run-confirm").is_enabled()
    assert not errors, errors
    page.close()


def test_browser_phone_no_horizontal_scroll(demo, browser):
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(demo["base"] + "/")
    page.wait_for_selector("body[data-ready]")
    for t in [*TABS, "controls"]:
        page.goto(f"{demo['base']}/#{t}")
        page.wait_for_selector(f"#view-{t}.active > *")
        page.wait_for_timeout(150)
        r = page.evaluate(OVERFLOW_JS)
        assert r["sw"] <= 390 and not r["bad"], (t, r)
    page.close()


def test_browser_static_export_is_read_only(demo, browser, tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    shutil.copy(DASH / "index.html", site / "index.html")
    shutil.copytree(DASH / "static", site / "static")
    snap = demo["static_snap"]
    assert snap["local"] is False and "ratings" not in snap
    (site / "data.json").write_text(json.dumps(snap, default=str))
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(site))
    handler.log_message = lambda *a, **k: None
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        posts = []
        page.on("request", lambda r: r.method == "POST" and posts.append(r.url))
        page.goto(base + "/index.html")
        page.wait_for_selector("#headline")
        assert "Read-only" in page.inner_text("#mode")
        assert page.locator('nav.tabs a[data-tab="controls"]').count() == 0
        for t in TABS:
            page.goto(f"{base}/index.html#{t}")
            page.wait_for_selector(f"#view-{t}.active > *")
            for sel in (".thumbs", ".thumb-up", ".thumb-down", ".local-only", "#run-card",
                        "#compare-card", "#jobs-panel", "textarea", "button.danger"):
                loc = page.locator(sel)
                assert all(not loc.nth(i).is_visible() for i in range(loc.count())), (t, sel)
        page.goto(f"{base}/index.html#cases")
        page.wait_for_selector("#case-list a.replay-link")
        href = page.locator("#case-list a.replay-link").first.get_attribute("href")
        assert re.match(r"^\./replay/index\.html\?t=\.\./t/E-\d{4}/[\w.-]+\.json$", href), href
        page.goto(f"{base}/index.html#experiments")
        page.wait_for_selector("#view-experiments a.num")
        fhref = page.locator("#view-experiments a.num").first.get_attribute("href")
        assert fhref.startswith("./files/experiments/"), fhref
        assert not posts
        page.close()
    finally:
        httpd.shutdown()
