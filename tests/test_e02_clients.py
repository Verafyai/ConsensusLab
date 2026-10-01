import json
from types import SimpleNamespace

import httpx
import pytest

from lab.clients.anthropic import AnthropicProvider
from lab.clients.base import Request, TransientError, Usage
from lab.clients.cache import ResponseCache
from lab.clients.fake import FakeProvider
from lab.clients.gateway import Gateway
from lab.clients.meter import BudgetExceeded, Meter, Scope, cost_usd
from lab.clients.xai import XAIProvider
from lab.config import load_config


@pytest.fixture
def gw(filled_config, tmp_path):
    cfg = load_config(filled_config)
    fake = FakeProvider("anthropic")
    g = Gateway(cfg, Meter(cfg, tmp_path / "spend.jsonl", tmp_path / "events.jsonl"),
                ResponseCache(tmp_path / "cache"), {"anthropic": fake, "xai": FakeProvider("xai")},
                sleep=lambda s: None)
    g.fake = fake
    return g


def req(**kw):
    return Request(model="claude-sonnet", messages=[{"role": "user", "content": "hello"}], **kw)


def test_cached_call_costs_zero(gw):
    s = Scope(experiment="E-1", caps={"exp": 1.0})
    a = gw.call(req(), s)
    b = gw.call(req(), s)
    assert a.usd > 0 and not a.cached
    assert b.usd == 0 and b.cached
    assert len(gw.fake.calls) == 1
    assert s.spent["exp"] == pytest.approx(a.usd)


def test_sample_index_is_a_distinct_call(gw):
    s = Scope()
    gw.call(req(sample=0), s)
    gw.call(req(sample=1), s)
    assert len(gw.fake.calls) == 2


def test_over_item_cap_refused_before_sending(gw):
    s = Scope(experiment="E-1").child("q-1", item_cap=1e-6)
    with pytest.raises(BudgetExceeded, match="item:q-1"):
        gw.call(req(max_tokens=4000), s)
    assert gw.fake.calls == []


def test_over_daily_cap_refused_before_sending(gw):
    gw.meter.record(Scope(), "x", Usage(), 49.99999, cached=False)  # cap is 50/day
    with pytest.raises(BudgetExceeded, match="day"):
        gw.call(req(max_tokens=4000), Scope())
    assert gw.fake.calls == []
    events = (gw.meter.events).read_text()
    assert "budget.halt" in events and "budget.alert" in events


def test_missing_price_refuses(gw):
    del gw.cfg.prices["models"]["claude-sonnet-5-5"]
    with pytest.raises(Exception, match="no price"):
        gw.call(req(), Scope())
    assert gw.fake.calls == []


def test_transient_errors_retry(gw):
    n = {"k": 0}
    orig = gw.fake.send

    def flaky(*a):
        n["k"] += 1
        if n["k"] < 3:
            raise TransientError("503")
        return orig(*a)
    gw.fake.send = flaky
    assert gw.call(req(), Scope()).text == "ok"
    assert n["k"] == 3


def test_ledger_rows_and_totals(gw, tmp_path):
    gw.call(req(), Scope(experiment="E-9"))
    rows = [json.loads(x) for x in (tmp_path / "spend.jsonl").read_text().splitlines()]
    assert rows[0]["experiment"] == "E-9" and rows[0]["usd"] > 0
    fresh = Meter(gw.cfg, tmp_path / "spend.jsonl", tmp_path / "e.jsonl")
    assert fresh.spent("lab", "day") == pytest.approx(rows[0]["usd"])


def test_cost_formula():
    p = {"input": 2.0, "output": 10.0, "cache_read": 0.2}
    u = Usage(input_tokens=1_000_000, output_tokens=100_000, cache_read_tokens=500_000)
    assert cost_usd(u, p) == pytest.approx(2.0 + 1.0 + 0.1)


def test_json_schema_parsed(gw):
    gw.fake.responder = lambda r, m: {"verdict": "refuted"}
    r = gw.call(req(json_schema={"type": "object"}), Scope())
    assert r.data == {"verdict": "refuted"}


def test_anthropic_request_shape():
    seen = {}

    class Msgs:
        def create(self, **kw):
            seen.update(kw)
            return SimpleNamespace(
                content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text="hi")],
                stop_reason="end_turn",
                usage=SimpleNamespace(input_tokens=10, output_tokens=5,
                                      cache_read_input_tokens=3, cache_creation_input_tokens=0))
    p = AnthropicProvider(client=SimpleNamespace(messages=Msgs()))
    r = p.send(Request(model="x", system="sys", messages=[{"role": "user", "content": "q"}],
                       json_schema={"type": "object"}), "claude-sonnet-5-5", {"effort": "low"})
    assert r.text == "hi" and r.usage.cache_read_tokens == 3
    assert seen["output_config"] == {"effort": "low", "format": {"type": "json_schema",
                                                                 "schema": {"type": "object"}}}
    assert seen["system"] == "sys"
    assert "temperature" not in seen


def test_xai_parses_reported_cost_and_retries(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        body = json.loads(request.content)
        assert body["response_format"]["type"] == "json_schema"
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20,
                      "prompt_tokens_details": {"cached_tokens": 40},
                      "cost_in_usd_ticks": 123_000_000}})
    p = XAIProvider(api_key="k", transport=httpx.MockTransport(handler))
    import lab.clients.openai_compat as oc
    monkeypatch.setattr(oc.time, "sleep", lambda s: None)
    r = p.send(Request(model="g", messages=[{"role": "user", "content": "q"}],
                       json_schema={"type": "object"}), "grok-4.7", {})
    assert r.usage.provider_usd == pytest.approx(0.0123)
    assert r.usage.input_tokens == 60 and r.usage.cache_read_tokens == 40
    assert calls["n"] == 2


@pytest.mark.live
def test_live_smoke():
    import os
    if os.environ.get("CL_LIVE") != "1":
        pytest.skip("set CL_LIVE=1 with keys in .env")
    from lab.clients.smoke import main
    assert main([]) == 0
