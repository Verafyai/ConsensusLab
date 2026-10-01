"""Shared offline test rig: config, gateway with fake providers, fake retriever, items."""

from __future__ import annotations

from pathlib import Path

from lab.clients.cache import ResponseCache
from lab.clients.fake import FakeProvider
from lab.clients.fakemodel import SchemaResponder
from lab.clients.gateway import Gateway
from lab.clients.meter import Meter
from lab.config import load_config
from lab.data.ingest import averitec
from lab.protocols.engine import Engine

RAW = Path(__file__).parent / "fixtures" / "raw"

PASSAGES = [
    ("Census", "The national census counted thirty one million residents across all regions of "
               "the country in its most recent official enumeration."),
    ("City estimate", "Officials estimate the city population at roughly fifteen million people, "
                      "though informal settlements make counting hard."),
    ("Analysis", "Demographers note that metropolitan estimates vary widely depending on the "
                 "boundaries used and the year of the survey."),
    ("Report", "A 2019 report found the metropolitan area grew faster than any other region "
               "but remained smaller than the national total."),
]


class FakeRetriever:
    def __init__(self):
        self.calls = 0

    def retrieve(self, item, max_sources, scope):
        self.calls += 1
        out = []
        for i, (title, text) in enumerate(PASSAGES[:max_sources]):
            words = text.split()
            out.append({"id": f"ev{i + 1}", "url": f"https://src{i}.example.org/a",
                        "title": title, "published": "2019-01-01",
                        "domain": f"src{i}.example.org", "excerpt": " ".join(words[:40]),
                        "passage": text})
        return out

    def page_text(self, url):
        i = int(url.split("src")[1].split(".")[0])
        return "Header text. " + PASSAGES[i][1] + " Footer."


def dev_items(n: int = 10) -> list[dict]:
    base = list(averitec.ingest(RAW / "averitec" / "dev.json"))
    out = []
    for i in range(n):
        it = dict(base[i % len(base)])
        it["id"] = f"q-test-{i:010x}"
        it["text"] = f"{it['text']} (variant {i})"
        it["split"] = "dev"
        out.append(it)
    return out


def rig(filled_config: Path, tmp_path: Path, responder=None):
    cfg = load_config(filled_config)
    responder = responder or SchemaResponder()
    providers = {"anthropic": FakeProvider("anthropic", responder, out_tokens=300),
                 "xai": FakeProvider("xai", responder, out_tokens=300)}
    meter = Meter(cfg, tmp_path / "spend.jsonl", tmp_path / "events.jsonl")
    gw = Gateway(cfg, meter, ResponseCache(tmp_path / "cache"), providers, sleep=lambda s: 0)
    return Engine(gw, FakeRetriever()), gw
