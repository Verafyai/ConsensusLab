"""Local dashboard server (spec §8.2, §8.3). Binds to 127.0.0.1 only.

    uv run python -m viz.dashboard.server [--port 8770]

Read-only views plus the lab controls (run, refine, compare, arena) and local thumbs
ratings. Controls only enqueue jobs; the orchestrator executes them and re-checks every
cap. Nothing here can change budget caps, the holdout, labels, scoring or the clearance
policy, and it never serves holdout items or transcripts.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import hmac
import json
import mimetypes
import re
import secrets
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from lab import paths

HERE = Path(__file__).parent
REPLAY = paths.ROOT / "viz" / "replay"
VARIANTS = paths.ROOT / "viz" / "variants"
FILE_PREFIXES = ("experiments/", "library/cards/", "zones/", "LEARNINGS.md", "STEERING.md",
                 "docs/", "data/SOURCES.md", "data/SPLITS.md", "ops/reports/")
ID = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
SECRET = secrets.token_bytes(32)        # signs estimate tokens for this server's lifetime


def sign(payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True).encode()
    return hmac.new(SECRET, body, hashlib.sha256).hexdigest()


def safe_file(rel: str) -> Path | None:
    rel = unquote(rel).lstrip("/")
    if ".." in rel or rel.startswith(".") or "/." in rel:
        return None
    if not any(rel == p.rstrip("/") or rel.startswith(p) for p in FILE_PREFIXES):
        return None
    p = (paths.ROOT / rel).resolve()
    if not p.is_relative_to(paths.ROOT.resolve()) or not p.is_file():
        return None
    return p


def dev_transcript(exp: str, item: str) -> dict | None:
    if not (ID.match(exp) and ID.match(item)):
        return None
    p = paths.RUNS / exp / f"{item}.json.gz"
    if not p.is_file():
        return None
    with gzip.open(p, "rb") as f:
        t = json.loads(f.read())
    return t if t.get("split", "dev") == "dev" else None


# ------------------------------------------------------------------ controls
def estimate_run(body: dict) -> dict:
    from lab import zones
    from lab.config import get
    from lab.protocols.estimate import estimate
    from lab.protocols.schema import validate_protocol
    cfg = get()
    zid, sub = body["zone"], body["sub"]
    p = zones.apply_knobs(zid, sub, body.get("knobs", {}))
    validate_protocol(p, set(cfg.models["models"]))
    _, problems = zones.check_refinement(p, zones.load(zid))
    n = int(body.get("n") or 100)
    e = estimate(p, cfg)
    usd = e.total(n)
    from lab.clients.meter import Meter
    day_left = cfg.cap("max_usd_per_day") - Meter(cfg).spent("lab", "day")
    cap = cfg.cap("max_usd_per_experiment")
    ok = not problems and usd <= cap and usd <= day_left
    out = {"protocol": p, "n": n, "estimate_usd": round(usd, 4),
           "per_item_usd": round(e.expected_usd, 5), "cap_usd": cap,
           "day_left_usd": round(day_left, 4), "ok": ok, "problems": problems}
    if not ok and not problems:
        out["problems"] = [f"estimate ${usd:.2f} exceeds the "
                           f"{'experiment cap' if usd > cap else 'remaining daily budget'}"]
    if ok:
        out["token"] = sign({"kind": "run", "protocol": p, "n": n})
    return out


def compare_configs(body: dict) -> dict:
    """2-4 configurations (protocol ids) on their latest shared dev items."""
    from lab.protocols.runner import load_dev_transcripts
    from lab.scoring import leaderboard
    from lab.scoring.score import compare, score
    ids = body.get("protocols", [])[:4]
    if len(ids) < 2:
        raise ValueError("pick 2 to 4 configurations")
    latest: dict[str, str] = {}
    for r in sorted(leaderboard.load_results(), key=lambda r: r["experiment"]):
        if (r.get("dev") or {}).get("n"):
            latest[r["protocol"]] = r["experiment"]
    ts = {}
    for pid in ids:
        if pid not in latest:
            raise ValueError(f"{pid} has no dev run")
        ts[pid] = load_dev_transcripts(latest[pid])
        if not ts[pid]:
            raise ValueError(f"{pid}: transcripts for {latest[pid]} aren't on this machine")
    common = set.intersection(*({t["item"] for t in v} for v in ts.values()))
    sub = {k: [t for t in v if t["item"] in common] for k, v in ts.items()}
    metrics = {k: score(v) for k, v in sub.items()}
    pairs = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            c = compare(sub[a], sub[b], resamples=int(body.get("resamples", 10_000)))
            ca = metrics[a]["cost"]["usd_per_item_uncached"]
            cb = metrics[b]["cost"]["usd_per_item_uncached"]
            c["cost_ratio"] = ca / cb if cb else None
            # Matched cost: the gain per extra dollar per item (None if no extra spend).
            c["diff_per_extra_usd"] = c["diff"] / (ca - cb) if ca - cb > 1e-9 else None
            va = {t["item"]: t["verdict"] for t in sub[a]}
            vb = {t["item"]: t["verdict"] for t in sub[b]}
            c["split_items"] = [{"item": it, "a": va[it], "b": vb[it],
                                 "replays": [f"/t/{latest[a]}/{it}", f"/t/{latest[b]}/{it}"]}
                                for it in sorted(common) if va[it] != vb[it]][:30]
            pairs.append({"a": a, "b": b, **c})
    return {"n_common": len(common), "metrics": metrics, "pairs": pairs,
            "experiments": {k: latest[k] for k in ids}}


class Handler(BaseHTTPRequestHandler):
    server_version = "ConsensusLab/0.1"

    def log_message(self, fmt, *args):  # quieter
        pass

    def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, default=str).encode())

    def _static(self, base: Path, rel: str) -> None:
        rel = unquote(rel).lstrip("/") or "index.html"
        p = (base / rel).resolve()
        if ".." in rel or not p.is_relative_to(base.resolve()) or not p.is_file():
            return self._send(404, b"not found", "text/plain")
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        self._send(200, p.read_bytes(), ctype)

    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        path = u.path
        if path in ("/", "/index.html"):
            return self._static(HERE, "index.html")
        if path.startswith("/static/"):
            return self._static(HERE / "static", path[len("/static/"):])
        if path.startswith("/replay/"):
            return self._static(REPLAY, path[len("/replay/"):])
        if path.startswith("/variants/"):
            return self._static(VARIANTS, path[len("/variants/"):])
        if path == "/api/data":
            from viz.dashboard.data import snapshot
            return self._json(snapshot(local=True))
        if path == "/api/status":
            from harness.health import status
            from lab.orchestrator import jobs
            return self._json({"health": status(), "jobs": jobs.all_jobs()[-20:]})
        m = re.match(r"^/t/([^/]+)/([^/]+?)(?:\.json)?$", path)
        if m:
            t = dev_transcript(m.group(1), m.group(2))
            return self._json(t) if t else self._send(404, b"not found", "text/plain")
        if path.startswith("/files/"):
            p = safe_file(path[len("/files/"):])
            if not p:
                return self._send(404, b"not found", "text/plain")
            ctype = mimetypes.guess_type(p.name)[0] or "text/plain"
            return self._send(200, p.read_bytes(), ctype + "; charset=utf-8")
        return self._send(404, b"not found", "text/plain")

    def do_POST(self):  # noqa: N802
        if self.headers.get("X-Lab") != "1":           # same-origin guard for the controls
            return self._json({"error": "missing X-Lab header"}, 403)
        n = int(self.headers.get("Content-Length") or 0)
        if n > 1_000_000:
            return self._json({"error": "too large"}, 413)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "bad json"}, 400)
        path = urlparse(self.path).path
        try:
            return self._json(self.route(path, body))
        except PermissionError as e:
            return self._json({"error": str(e)}, 403)
        except (ValueError, KeyError, FileNotFoundError) as e:
            return self._json({"error": str(e)}, 400)
        except Exception as e:  # noqa: BLE001
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def route(self, path: str, body: dict) -> dict:
        from lab.orchestrator import jobs
        by = body.get("by") or "dashboard"
        if path == "/api/rate":
            if body.get("thumb") not in ("up", "down"):
                raise ValueError("thumb must be up or down")
            for k in ("experiment", "item"):
                if not ID.match(str(body.get(k, ""))):
                    raise ValueError(f"bad {k}")
            row = {"ts": datetime.now(UTC).isoformat(timespec="seconds"),
                   "experiment": body["experiment"], "item": body["item"],
                   "protocol": body.get("protocol"), "variant": body.get("variant"),
                   "thumb": body["thumb"], "note": str(body.get("note") or "")[:500]}
            with (paths.ROOT / "ratings.jsonl").open("a") as f:
                f.write(json.dumps(row) + "\n")
            return {"ok": True}
        if path == "/api/estimate":
            return estimate_run(body)
        if path == "/api/run":
            if not body.get("confirm"):
                raise PermissionError("confirmation required")
            est = estimate_run(body)          # re-estimate; never trust the browser's numbers
            if not est["ok"]:
                raise PermissionError("; ".join(est["problems"]))
            if not hmac.compare_digest(body.get("token", ""), est["token"]):
                raise PermissionError("estimate changed; review the new estimate and confirm")
            job = jobs.enqueue("run", {"protocol": est["protocol"], "n": est["n"],
                                       "zone": body["zone"]}, by, est["estimate_usd"])
            return {"job": job}
        if path == "/api/refine":
            from lab.clients.meter import Meter
            from lab.config import get
            if not body.get("confirm"):
                raise PermissionError("confirmation required")
            cfg = get()
            budget = float(body["budget"])
            left = cfg.cap("max_usd_per_day") - Meter(cfg).spent("lab", "day")
            if budget <= 0 or budget > left:
                raise PermissionError(f"budget ${budget:.2f} exceeds today's remaining "
                                      f"${left:.2f}")
            it = int(body["iterations"])
            if not 1 <= it <= 20:
                raise ValueError("iterations must be 1..20")
            from lab import zones
            if body["zone"] not in zones.zone_ids():
                raise ValueError("unknown zone")
            job = jobs.enqueue("refine", {"zone": body["zone"], "iterations": it,
                                          "budget": budget,
                                          "steer": str(body.get("steer", ""))[:500]}, by, budget)
            return {"job": job}
        if path == "/api/compare":
            return compare_configs(body)
        if path == "/api/arena":
            from viz.dashboard.data import snapshot
            if not body.get("confirm"):
                left = snapshot(local=False).get("holdout_evals_left")
                return {"needs_confirm": True, "holdout_evals_left": left,
                        "message": f"This uses 1 of this week's holdout evaluations "
                                   f"({left} left)."}
            exp = str(body.get("experiment", ""))
            if not re.match(r"^E-\d{4}$", exp) or \
                    not (paths.EXPERIMENTS / exp / "protocol.yaml").exists():
                raise ValueError("unknown experiment")
            job = jobs.enqueue("arena", {"experiment": exp, "zone": body.get("zone")}, by)
            return {"job": job}
        raise ValueError(f"unknown endpoint {path}")


def serve(port: int = 8770, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("the local dashboard binds to localhost only")
    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8770)
    a = ap.parse_args()
    from harness.health import Pulse
    srv = serve(a.port)
    print(f"dashboard: http://127.0.0.1:{a.port}/")
    with Pulse("dashboard") as p:
        p.state = f"serving :{a.port}"
        srv.serve_forever()


if __name__ == "__main__":
    main()
