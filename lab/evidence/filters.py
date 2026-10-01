"""Leakage guard and copyright limits for evidence (spec §4.3, §11)."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from lab import paths

MAX_EXCERPT_WORDS = 40
FACTCHECK_TITLE = re.compile(
    r"\b(fact[- ]?check\w*|debunk\w*|false claim|misleading claim|viral claim|hoax|"
    r"pants on fire|pinocchio|verdict:|rated (false|true|misleading))\b", re.I)


def load_blocklist(path: Path | None = None) -> list[str]:
    path = path or paths.DATA / "blocklist.txt"
    out = []
    for line in path.read_text().splitlines():
        line = line.strip().lower()
        if line and not line.startswith("#"):
            out.append(line.removeprefix("https://").removeprefix("http://").removeprefix("www."))
    return out


def _host_path(url: str) -> tuple[str, str]:
    u = urlparse(url if "://" in url else f"https://{url}")
    host = (u.hostname or "").lower().removeprefix("www.")
    return host, (u.path or "/").lower()


def is_blocked(url: str, blocklist: list[str]) -> bool:
    """Blocked if host equals or is a subdomain of an entry; entries with a path also
    require the URL path to start with that path."""
    host, path = _host_path(url)
    for entry in blocklist:
        e_host, _, e_path = entry.partition("/")
        if host == e_host or host.endswith("." + e_host):
            if not e_path or path.startswith("/" + e_path):
                return True
    return False


def looks_like_factcheck(title: str | None) -> bool:
    return bool(title and FACTCHECK_TITLE.search(title))


def before(published: str | None, item_date: str | None, require_date: bool = True) -> bool:
    """True if a source may be shown for an item.

    No item date → anything goes. Item date known → source must be strictly earlier; an
    undated source is dropped when require_date (the default), since leakage is the bigger risk.
    """
    if not item_date:
        return True
    if not published:
        return not require_date
    try:
        return date.fromisoformat(published[:10]) < date.fromisoformat(item_date[:10])
    except ValueError:
        return not require_date


def words(text: str) -> list[str]:
    return text.split()


def cap_words(text: str, n: int = MAX_EXCERPT_WORDS) -> str:
    w = words(text)
    return " ".join(w[:n]) + ("…" if len(w) > n else "")


def excerpt_ok(text: str, n: int = MAX_EXCERPT_WORDS) -> bool:
    return len(words(text.rstrip("…"))) <= n


_TOKEN = re.compile(r"[a-z0-9]+")
STOP = set("the a an of to in and or is are was were be been for on at by with that this it "
           "as from has have had not no but its their his her they he she we you i".split())


def _terms(s: str) -> set[str]:
    return {t for t in _TOKEN.findall(s.lower()) if t not in STOP and len(t) > 2}


def best_excerpt(text: str, query: str, n: int = MAX_EXCERPT_WORDS) -> str:
    """The n-word window of `text` that overlaps most with the query's content words."""
    w = words(text)
    if len(w) <= n:
        return " ".join(w)
    q = _terms(query)
    best, best_i = -1, 0
    step = max(1, n // 4)
    starts = list(range(0, len(w) - n + 1, step)) + [len(w) - n]
    for i in starts:
        score = len(q & _terms(" ".join(w[i:i + n])))
        if score > best:
            best, best_i = score, i
    return cap_words(" ".join(w[best_i:best_i + n]), n)
