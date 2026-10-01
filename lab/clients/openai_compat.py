"""Shared OpenAI-compatible chat-completions transport (xAI, OpenRouter)."""

from __future__ import annotations

import time
from typing import Any

import httpx

from lab.clients.base import ProviderResult, Request, TransientError, Usage


def to_openai_messages(req: Request) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if req.system:
        out.append({"role": "system", "content": req.system})
    for m in req.messages:
        c = m["content"]
        if isinstance(c, list):
            parts = []
            for b in c:
                if b["type"] == "text":
                    parts.append({"type": "text", "text": b["text"]})
                elif b["type"] == "image":
                    s = b["source"]
                    parts.append({"type": "image_url", "image_url": {
                        "url": f"data:{s['media_type']};base64,{s['data']}"}})
            c = parts
        out.append({"role": m["role"], "content": c})
    return out


class OpenAICompatProvider:
    name = "openai_compat"
    base_url = ""
    key_env = ""

    def __init__(self, api_key: str | None = None, transport: httpx.BaseTransport | None = None):
        self.api_key = api_key
        self.http = httpx.Client(timeout=180.0, transport=transport)

    def _key(self) -> str:
        import os
        k = self.api_key or os.environ.get(self.key_env)
        if not k:
            raise RuntimeError(f"{self.key_env} is not set (see .env.example)")
        return k

    def body(self, req: Request, model_id: str, params: dict[str, Any]) -> dict[str, Any]:
        b: dict[str, Any] = {"model": model_id, "messages": to_openai_messages(req),
                             "max_tokens": req.max_tokens}
        if req.json_schema:
            b["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "output", "schema": req.json_schema, "strict": True}}
        b.update(params.get("extra_body", {}))
        return b

    def provider_cost(self, usage: dict[str, Any]) -> float | None:
        return None

    def send(self, req: Request, model_id: str, params: dict[str, Any]) -> ProviderResult:
        body = self.body(req, model_id, params)
        delay = 2.0
        for attempt in range(5):
            try:
                r = self.http.post(f"{self.base_url}/chat/completions", json=body,
                                   headers={"Authorization": f"Bearer {self._key()}"})
            except httpx.TransportError as e:
                err: Exception = e
            else:
                if r.status_code == 429 or r.status_code >= 500:
                    err = TransientError(f"{self.name} HTTP {r.status_code}")
                else:
                    r.raise_for_status()
                    return self.parse(r.json())
            if attempt == 4:
                raise TransientError(str(err)) from err
            time.sleep(delay)
            delay *= 2
        raise AssertionError("unreachable")

    def parse(self, d: dict[str, Any]) -> ProviderResult:
        ch = d["choices"][0]
        u = d.get("usage", {})
        cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
        usage = Usage(input_tokens=u.get("prompt_tokens", 0) - cached,
                      output_tokens=u.get("completion_tokens", 0),
                      cache_read_tokens=cached, provider_usd=self.provider_cost(u))
        stop = ch.get("finish_reason")
        msg = ch.get("message", {})
        return ProviderResult(text=msg.get("content") or "", usage=usage, stop=stop,
                              refused=bool(msg.get("refusal")))
