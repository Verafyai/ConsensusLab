"""Evidence search and fetch (spec §4.3, E03).

Every returned source passes the leakage guard: not on data/blocklist.txt, not the item's
own fact-check page, not titled like a fact-check, and published before the item's date
when the item has one. Excerpts never exceed 40 words. Full page text stays in the local
cache (.cache/pages) so quotes can be verified (E04b) but never enters the repo.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Protocol

import httpx

from lab import paths
from lab.clients.base import Usage
from lab.clients.meter import Meter, Scope
from lab.config import Config
from lab.evidence import filters

URL_RE = re.compile(r"https?://\S+")


@dataclass
class Hit:
    url: str
    title: str = ""
    snippet: str = ""
    published: str | None = None


@dataclass
class Page:
    url: str
    title: str
    text: str
    published: str | None


class SearchBackend(Protocol):
    name: str

    def search(self, query: str, n: int, before: str | None) -> list[Hit]: ...


class Fetcher(Protocol):
    def fetch(self, url: str) -> Page | None: ...


# --- Brave Search -------------------------------------------------------------------------

class BraveSearch:
    name = "brave"
    URL = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str | None = None, transport: httpx.BaseTransport | None = None):
        self.key = api_key or os.environ.get("BRAVE_API_KEY")
        self.http = httpx.Client(timeout=30.0, transport=transport)

    def search(self, query: str, n: int, before: str | None) -> list[Hit]:
        if not self.key:
            raise RuntimeError("BRAVE_API_KEY is not set (see .env.example)")
        params: dict[str, str | int] = {"q": query[:380], "count": min(n, 20),
                                        "safesearch": "moderate"}
        if before:
            end = date.fromisoformat(before[:10]) - timedelta(days=1)
            params["freshness"] = f"1990-01-01to{end.isoformat()}"
        r = self.http.get(self.URL, params=params,
                          headers={"X-Subscription-Token": self.key, "Accept": "application/json"})
        r.raise_for_status()
        out = []
        for x in r.json().get("web", {}).get("results", []):
            out.append(Hit(url=x["url"], title=x.get("title", ""),
                           snippet=re.sub(r"<[^>]+>", "", x.get("description", "")),
                           published=(x.get("page_age") or "")[:10] or None))
        return out


# --- HTML fetch ---------------------------------------------------------------------------

DATE_META = {"article:published_time", "og:published_time", "datepublished", "date",
             "pubdate", "publishdate", "dc.date", "dc.date.issued", "sailthru.date",
             "parsely-pub-date"}


class _Extract(HTMLParser):
    SKIP = {"script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.title = ""
        self.published: str | None = None
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            name = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if name in DATE_META and not self.published:
                self.published = _iso(a.get("content", ""))
        elif tag == "time" and not self.published and a.get("datetime"):
            self.published = _iso(a["datetime"])

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def _iso(s: str) -> str | None:
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def html_to_page(url: str, html: str) -> Page:
    p = _Extract()
    p.feed(html)
    text = re.sub(r"\s+", " ", " ".join(p.parts)).strip()
    if not p.published:
        m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html)
        p.published = _iso(m.group(1)) if m else None
    return Page(url=url, title=p.title.strip(), text=text, published=p.published)


class HttpFetcher:
    def __init__(self, cache_dir: Path | None = None, transport: httpx.BaseTransport | None = None):
        self.cache = (cache_dir or paths.CACHE) / "pages"
        self.http = httpx.Client(timeout=20.0, follow_redirects=True, transport=transport,
                                 headers={"User-Agent": "ConsensusLab/0.1 (+research)"})

    def _path(self, url: str) -> Path:
        return self.cache / f"{hashlib.sha256(url.encode()).hexdigest()}.json"

    def fetch(self, url: str) -> Page | None:
        p = self._path(url)
        if p.exists():
            d = json.loads(p.read_text())
            return Page(**d) if d else None
        page = None
        try:
            r = self.http.get(url)
            if r.status_code == 200 and "html" in r.headers.get("content-type", "html"):
                page = html_to_page(str(r.url), r.text[:2_000_000])
        except httpx.HTTPError:
            page = None
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(page) if page else None))
        return page


# --- Retriever ----------------------------------------------------------------------------

class Retriever:
    def __init__(self, cfg: Config, meter: Meter, backend: SearchBackend, fetcher: Fetcher,
                 cache_dir: Path | None = None, blocklist: list[str] | None = None,
                 require_source_date: bool = True):
        self.cfg, self.meter, self.backend, self.fetcher = cfg, meter, backend, fetcher
        self.cache = (cache_dir or paths.CACHE) / "search"
        self.blocklist = blocklist if blocklist is not None else filters.load_blocklist()
        self.require_source_date = require_source_date

    @classmethod
    def default(cls, cfg: Config, meter: Meter) -> Retriever:
        return cls(cfg, meter, BraveSearch(), HttpFetcher())

    def estimate(self) -> float:
        return self.cfg.service_price("search_per_query")

    def _search(self, query: str, n: int, before: str | None, scope: Scope) -> list[Hit]:
        key = hashlib.sha256(json.dumps([self.backend.name, query, n, before]).encode())
        p = self.cache / f"{key.hexdigest()}.json"
        if p.exists():
            return [Hit(**h) for h in json.loads(p.read_text())]
        price = self.estimate()
        self.meter.check(price, scope)
        hits = self.backend.search(query, n, before)
        self.meter.record(scope, f"service:{self.backend.name}", Usage(), price, cached=False)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps([asdict(h) for h in hits]))
        return hits

    def item_blocklist(self, item: dict) -> list[str]:
        """The dataset's own source pages for this item are blocked too."""
        extra = []
        for s in (item.get("source_url"), *URL_RE.findall(item.get("expert_source", ""))):
            if s:
                host = (httpx.URL(s).host or "").removeprefix("www.")
                extra.append(host + httpx.URL(s).path.rstrip("/"))
        return self.blocklist + extra

    def retrieve(self, item: dict, max_sources: int, scope: Scope,
                 query: str | None = None) -> list[dict]:
        query = query or item["text"]
        block = self.item_blocklist(item)
        hits = self._search(query, max(10, max_sources * 3), item.get("date"), scope)
        out: list[dict] = []
        seen_hosts: set[str] = set()
        for h in hits:
            if len(out) >= max_sources:
                break
            if filters.is_blocked(h.url, block) or filters.looks_like_factcheck(h.title):
                continue
            page = self.fetcher.fetch(h.url)
            published = (page.published if page else None) or h.published
            if not filters.before(published, item.get("date"), self.require_source_date):
                continue
            title = (page.title if page and page.title else h.title)
            if filters.looks_like_factcheck(title):
                continue
            body = page.text if page and len(page.text) > 200 else h.snippet
            if not body:
                continue
            host = httpx.URL(h.url).host or ""
            if host in seen_hosts:          # one source per site keeps the panel diverse
                continue
            seen_hosts.add(host)
            out.append({
                "id": f"ev{len(out) + 1}", "url": h.url, "title": title[:200],
                "published": published, "domain": host.removeprefix("www."),
                "excerpt": filters.best_excerpt(body, query),
                "retrieved": datetime.now(UTC).date().isoformat(),
                "text_sha256": hashlib.sha256(body.encode()).hexdigest(),
            })
        for ev in out:
            assert filters.excerpt_ok(ev["excerpt"]), ev["id"]
        return out
