"""Read-only local server for the evidence replay.

    uv run python -m viz.replay.serve [--port 8765]

Serves the repo root, but only these prefixes: viz/, runs/, experiments/, library/cards/.
Never serves dot-files (.env), ops/, config/, data/, or any path containing '..'.
/t/<experiment>/<item> decompresses runs/<experiment>/<item>.json.gz and returns JSON, so
http://127.0.0.1:8765/viz/replay/?t=/t/E-0001/<item> replays a real run.
"""

from __future__ import annotations

import argparse
import gzip
import mimetypes
import re
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ALLOWED_PREFIXES = ("viz/", "runs/", "experiments/", "library/cards/")
_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
_TYPES = {".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
          ".json": "application/json", ".html": "text/html", ".svg": "image/svg+xml",
          ".md": "text/markdown", ".yaml": "text/yaml", ".yml": "text/yaml"}


def resolve_request(root: Path, raw_path: str) -> tuple[str, Path] | None:
    """Map a request path to ("file" | "transcript", path), or None if refused.

    Pure function so the guard can be tested without a socket.
    """
    path = urlsplit(raw_path).path
    decoded = unquote(path)
    if ".." in path or ".." in decoded or "\\" in decoded or "\x00" in decoded:
        return None
    rel = decoded.lstrip("/")
    parts = [p for p in rel.split("/") if p]
    if any(p.startswith(".") for p in parts):
        return None
    if len(parts) == 3 and parts[0] == "t":
        exp, item = parts[1], parts[2]
        if item.endswith(".json"):
            item = item[: -len(".json")]
        if not (_SEGMENT.match(exp) and _SEGMENT.match(item)):
            return None
        target = root / "runs" / exp / f"{item}.json.gz"
        return ("transcript", target) if _inside(root / "runs", target) else None
    prefix = next((p for p in ALLOWED_PREFIXES if rel.startswith(p) or rel + "/" == p), None)
    if prefix is None:
        return None
    target = root / rel
    if not _inside(root / prefix, target):
        return None
    if target.is_dir():
        target = target / "index.html"
    return "file", target


def _inside(base: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except (ValueError, OSError):
        return False


class ReplayHandler(BaseHTTPRequestHandler):
    server_version = "ConsensusLabReplay/1"

    def __init__(self, *args, root: Path, **kwargs):
        self.root = root
        super().__init__(*args, **kwargs)

    def log_message(self, fmt, *args):  # quieter: one short line per request
        if getattr(self.server, "verbose", True):
            super().log_message(fmt, *args)

    def do_HEAD(self):
        self._serve(head=True)

    def do_GET(self):
        self._serve(head=False)

    def _refuse(self, status=HTTPStatus.NOT_FOUND):
        body = b"not found\n" if status == HTTPStatus.NOT_FOUND else b"forbidden\n"
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve(self, head: bool):
        if urlsplit(self.path).path in ("", "/"):
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/viz/replay/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        res = resolve_request(self.root, self.path)
        if res is None:
            self._refuse(HTTPStatus.FORBIDDEN)
            return
        kind, target = res
        if not target.is_file():
            self._refuse(HTTPStatus.NOT_FOUND)
            return
        if kind == "transcript":
            try:
                body = gzip.decompress(target.read_bytes())
            except (OSError, EOFError):
                self._refuse(HTTPStatus.NOT_FOUND)
                return
            ctype = "application/json; charset=utf-8"
        else:
            body = target.read_bytes()
            ctype = _TYPES.get(target.suffix.lower()) or (
                mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            if ctype.startswith("text/") or ctype == "application/json":
                ctype += "; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if not head:
            self.wfile.write(body)


def make_server(root: Path = REPO_ROOT, port: int = 8765, host: str = "127.0.0.1",
                verbose: bool = True) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer((host, port), partial(ReplayHandler, root=Path(root)))
    srv.verbose = verbose
    srv.daemon_threads = True
    return srv


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Serve the evidence replay (read-only).")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args(argv)
    srv = make_server(REPO_ROOT, args.port, args.host)
    port = srv.server_address[1]
    print(f"Evidence replay: http://{args.host}:{port}/viz/replay/")
    print(f"  card mode:  http://{args.host}:{port}/viz/replay/?mode=card&aspect=square")
    print(f"  a real run: http://{args.host}:{port}/viz/replay/?t=/t/<experiment>/<item>")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
