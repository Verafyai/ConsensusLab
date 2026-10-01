"""xAI (Grok) provider. xAI reports cost per call as usage.cost_in_usd_ticks (1e-10 USD)."""

from __future__ import annotations

from typing import Any

from lab.clients.openai_compat import OpenAICompatProvider


class XAIProvider(OpenAICompatProvider):
    name = "xai"
    base_url = "https://api.x.ai/v1"
    key_env = "XAI_API_KEY"

    def provider_cost(self, usage: dict[str, Any]) -> float | None:
        ticks = usage.get("cost_in_usd_ticks")
        return ticks / 1e10 if ticks is not None else None
