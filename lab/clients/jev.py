"""Jev provider (optional, spec §5.1 jev-aggregate, §11 cheap rubric judge).

No Jev API was found on disk; this provider is wired only when JEV_BASE_URL is set and
assumes an OpenAI-compatible endpoint. Until Rex points the lab at a Jev deployment,
protocols using aggregation: jev are rejected by the engine.
"""

from __future__ import annotations

import os

from lab.clients.openai_compat import OpenAICompatProvider


class JevProvider(OpenAICompatProvider):
    name = "jev"
    key_env = "JEV_API_KEY"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.base_url = os.environ.get("JEV_BASE_URL", "").rstrip("/")

    @staticmethod
    def available() -> bool:
        return bool(os.environ.get("JEV_BASE_URL"))
