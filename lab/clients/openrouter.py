"""OpenRouter provider (optional, spec §14.3). Reports cost via usage accounting."""

from __future__ import annotations

from typing import Any

from lab.clients.base import Request
from lab.clients.openai_compat import OpenAICompatProvider


class OpenRouterProvider(OpenAICompatProvider):
    name = "openrouter"
    base_url = "https://openrouter.ai/api/v1"
    key_env = "OPENROUTER_API_KEY"

    def body(self, req: Request, model_id: str, params: dict[str, Any]) -> dict[str, Any]:
        b = super().body(req, model_id, params)
        b["usage"] = {"include": True}
        return b

    def provider_cost(self, usage: dict[str, Any]) -> float | None:
        c = usage.get("cost")
        return float(c) if c is not None else None
