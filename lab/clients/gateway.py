"""The single entry point for model calls: cache → estimate → cap check → send → meter.

    gw = Gateway.default()
    resp = gw.call(Request(model="claude-sonnet", messages=[...]), scope)
"""

from __future__ import annotations

import json
import time
from typing import Any

from dotenv import load_dotenv

from lab import paths
from lab.clients.base import Provider, Request, Response, TransientError
from lab.clients.cache import ResponseCache
from lab.clients.meter import Meter, Scope, cost_usd, estimate_tokens
from lab.config import Config, LabNotReady, get


def _chars(req: Request) -> int:
    n = len(req.system)
    for m in req.messages:
        c = m["content"]
        if isinstance(c, str):
            n += len(c)
        else:
            for b in c:
                n += len(b.get("text", "")) if b["type"] == "text" else 6000  # ~1.6k-token image
    if req.json_schema:
        n += len(json.dumps(req.json_schema))
    return n


def default_providers() -> dict[str, Provider]:
    from lab.clients.anthropic import AnthropicProvider
    from lab.clients.jev import JevProvider
    from lab.clients.openrouter import OpenRouterProvider
    from lab.clients.xai import XAIProvider
    return {"anthropic": AnthropicProvider(), "xai": XAIProvider(),
            "openrouter": OpenRouterProvider(), "jev": JevProvider()}


class Gateway:
    def __init__(self, cfg: Config, meter: Meter, cache: ResponseCache,
                 providers: dict[str, Provider], sleep=time.sleep):
        self.cfg, self.meter, self.cache, self.providers = cfg, meter, cache, providers
        self.sleep = sleep

    @classmethod
    def default(cls) -> Gateway:
        load_dotenv(paths.ROOT / ".env")
        cfg = get()
        return cls(cfg, Meter(cfg), ResponseCache(), default_providers())

    def resolve(self, alias: str) -> tuple[dict[str, Any], dict[str, float]]:
        spec = self.cfg.model(alias)
        return spec, self.cfg.price(spec["id"])

    def estimate(self, req: Request) -> float:
        """Worst-case USD for one call: estimated input plus the full max_tokens of output."""
        spec, price = self.resolve(req.model)
        ins = estimate_tokens(_chars(req))
        return (ins * float(price["input"]) + req.max_tokens * float(price["output"])) / 1e6

    def call(self, req: Request, scope: Scope) -> Response:
        spec, price = self.resolve(req.model)
        provider = self.providers.get(spec["provider"])
        if provider is None:
            raise LabNotReady(f"no provider {spec['provider']!r} for model {req.model!r}")
        key = self.cache.key(req.cache_payload(spec["id"], spec["provider"]))
        hit = self.cache.get(key)
        if hit is not None:
            self.meter.record(scope, spec["id"], hit.usage, 0.0, cached=True)
            r = self._response(req, hit, spec["id"], usd=0.0, cached=True, latency=0.0)
            r.meta["list_usd"] = cost_usd(hit.usage, price)   # what it cost when first run
            return r

        est = self.estimate(req)
        self.meter.reserve(est, scope)       # raises before anything is sent
        t0 = time.monotonic()
        result, delay = None, 2.0
        try:
            for attempt in range(4):
                try:
                    result = provider.send(req, spec["id"], spec.get("params") or {})
                    break
                except TransientError:
                    if attempt == 3:
                        raise
                    self.sleep(delay)
                    delay *= 2
        except BaseException:
            self.meter.release(est, scope)
            raise
        assert result is not None
        latency = time.monotonic() - t0
        usd = cost_usd(result.usage, price)
        self.meter.record(scope, spec["id"], result.usage, usd, cached=False, latency_s=latency,
                          reserved=est)
        self.cache.put(key, result)
        r = self._response(req, result, spec["id"], usd=usd, cached=False, latency=latency)
        r.meta["list_usd"] = usd
        return r

    @staticmethod
    def _response(req, result, model_id, usd, cached, latency) -> Response:
        data = None
        if req.json_schema and result.text and not result.refused:
            try:
                data = json.loads(result.text)
            except json.JSONDecodeError:
                data = None
        return Response(text=result.text, usage=result.usage, usd=usd, model_id=model_id,
                        cached=cached, refused=result.refused, latency_s=latency, data=data,
                        raw_stop=result.stop)
