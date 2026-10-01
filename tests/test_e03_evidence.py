import httpx
import pytest

from lab.clients.meter import BudgetExceeded, Meter, Scope
from lab.config import load_config
from lab.evidence import filters
from lab.evidence.retrieve import BraveSearch, Hit, Page, Retriever, html_to_page

BL = filters.load_blocklist()


@pytest.mark.parametrize("url", [
    "https://www.politifact.com/factchecks/2024/x", "https://snopes.com/a",
    "https://factcheck.afp.com/doc", "https://www.reuters.com/fact-check/abc",
    "http://sub.fullfact.org/y", "https://huggingface.co/datasets/averitec"])
def test_blocklisted_urls_blocked(url):
    assert filters.is_blocked(url, BL)


@pytest.mark.parametrize("url", [
    "https://www.reuters.com/world/abc", "https://apnews.com/article/x",
    "https://notsnopes.com/a", "https://en.wikipedia.org/wiki/Lagos"])
def test_ordinary_urls_allowed(url):
    assert not filters.is_blocked(url, BL)


def test_date_filter():
    assert filters.before("2024-01-01", "2024-03-02")
    assert not filters.before("2024-03-02", "2024-03-02")
    assert not filters.before("2025-01-01", "2024-03-02")
    assert not filters.before(None, "2024-03-02")
    assert filters.before(None, "2024-03-02", require_date=False)
    assert filters.before("2030-01-01", None)


def test_excerpt_cap():
    text = " ".join(f"w{i}" for i in range(500)) + " lagos ghana population census"
    ex = filters.best_excerpt(text, "Lagos population exceeds Ghana")
    assert filters.excerpt_ok(ex) and len(ex.rstrip("…").split()) <= 40
    assert "lagos" in ex
    assert filters.cap_words("a " * 100).count("a") == 40


def test_html_extract_date_and_text():
    p = html_to_page("u", "<html><head><title>T</title><meta property='article:published_time'"
                          " content='2023-05-04T10:00:00Z'><script>x()</script></head>"
                          "<body><nav>menu</nav><p>Real text here.</p></body></html>")
    assert p.published == "2023-05-04" and p.text == "Real text here." and p.title == "T"


class FakeSearch:
    name = "fake"

    def __init__(self, hits):
        self.hits, self.calls = hits, 0

    def search(self, q, n, before):
        self.calls += 1
        return self.hits


class FakeFetch:
    def __init__(self, pages):
        self.pages = pages

    def fetch(self, url):
        return self.pages.get(url)


LONG = "The Lagos state population was estimated at fifteen million while Ghana counted " \
       "about thirty million residents in its census " + "filler words " * 200


@pytest.fixture
def retriever(filled_config, tmp_path):
    cfg = load_config(filled_config)
    hits = [
        Hit("https://www.politifact.com/x", "Lagos vs Ghana", "s", "2020-01-01"),
        Hit("https://news.example.com/after", "Population news", "s", "2023-01-01"),
        Hit("https://news2.example.com/fc", "Fact check: Lagos bigger than Ghana?", "s",
            "2020-01-01"),
        Hit("https://africacheck.org/fact-checks/lagos-ghana", "Lagos", "s", "2020-01-01"),
        Hit("https://stats.example.org/a", "Census", "s", None),
        Hit("https://good.example.org/b", "Lagos population", "s", "2021-06-01"),
        Hit("https://item-source.example.net/claim/123", "Lagos", "s", "2020-01-01"),
    ]
    pages = {h.url: Page(h.url, h.title, LONG, h.published) for h in hits}
    return Retriever(cfg, Meter(cfg, tmp_path / "s.jsonl", tmp_path / "e.jsonl"),
                     FakeSearch(hits), FakeFetch(pages), cache_dir=tmp_path, blocklist=BL)


ITEM = {"id": "q-x-0000000001", "text": "Lagos has more residents than all of Ghana.",
        "date": "2022-03-14", "source_url": "https://item-source.example.net/claim/123",
        "expert_source": "AVeriTeC from https://africacheck.org/fact-checks/lagos-ghana"}


def test_retrieve_applies_leakage_guard(retriever):
    ev = retriever.retrieve(ITEM, 6, Scope())
    urls = [e["url"] for e in ev]
    assert urls == ["https://good.example.org/b"]
    assert ev[0]["id"] == "ev1" and filters.excerpt_ok(ev[0]["excerpt"])
    assert ev[0]["published"] < ITEM["date"]


def test_search_is_cached_and_metered(retriever, tmp_path):
    retriever.retrieve(ITEM, 6, Scope())
    retriever.retrieve(ITEM, 6, Scope())
    assert retriever.backend.calls == 1
    assert "service:fake" in (tmp_path / "s.jsonl").read_text()


def test_search_refused_over_cap(retriever):
    with pytest.raises(BudgetExceeded):
        retriever.retrieve(ITEM, 6, Scope(caps={"x": 0.0}))
    assert retriever.backend.calls == 0


def test_brave_request_has_freshness_before_item_date():
    seen = {}

    def handler(req):
        seen.update(dict(req.url.params))
        return httpx.Response(200, json={"web": {"results": [
            {"url": "https://a.org", "title": "A", "description": "<b>x</b>",
             "page_age": "2021-01-01T00:00:00"}]}})
    hits = BraveSearch("k", transport=httpx.MockTransport(handler)).search("q", 5, "2022-03-14")
    assert seen["freshness"] == "1990-01-01to2022-03-13"
    assert hits[0].published == "2021-01-01" and hits[0].snippet == "x"
