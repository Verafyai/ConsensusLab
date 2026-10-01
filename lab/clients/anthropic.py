"""Anthropic Messages API provider (official SDK)."""

from __future__ import annotations

import os
from typing import Any

import anthropic

from lab.clients.base import ProviderResult, Request, TransientError, Usage


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, client: anthropic.Anthropic | None = None):
        self._client = client

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise RuntimeError("ANTHROPIC_API_KEY is not set (see .env.example)")
            self._client = anthropic.Anthropic(max_retries=4, timeout=180.0)
        return self._client

    def send(self, req: Request, model_id: str, params: dict[str, Any]) -> ProviderResult:
        output_config: dict[str, Any] = {}
        effort = req.effort or params.get("effort")
        if effort:
            output_config["effort"] = effort
        if req.json_schema:
            output_config["format"] = {"type": "json_schema", "schema": req.json_schema}
        kwargs: dict[str, Any] = {"model": model_id, "max_tokens": req.max_tokens,
                                  "messages": req.messages}
        if req.system:
            kwargs["system"] = req.system
        if output_config:
            kwargs["output_config"] = output_config
        try:
            msg = self.client.messages.create(**kwargs)
        except (anthropic.RateLimitError, anthropic.InternalServerError,
                anthropic.APIConnectionError) as e:
            raise TransientError(str(e)) from e
        u = msg.usage
        usage = Usage(input_tokens=u.input_tokens, output_tokens=u.output_tokens,
                      cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
                      cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0)
        text = "".join(b.text for b in msg.content if b.type == "text")
        return ProviderResult(text=text, usage=usage, stop=msg.stop_reason,
                              refused=msg.stop_reason == "refusal")
