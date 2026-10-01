"""Deterministic offline provider for tests and dry runs. Never touches the network."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from lab.clients.base import ProviderResult, Request, Usage


class FakeProvider:
    def __init__(self, name: str = "fake",
                 responder: Callable[[Request, str], str | dict] | None = None,
                 out_tokens: int = 50):
        self.name = name
        self.responder = responder
        self.out_tokens = out_tokens
        self.calls: list[Request] = []

    def send(self, req: Request, model_id: str, params: dict[str, Any]) -> ProviderResult:
        self.calls.append(req)
        out = self.responder(req, model_id) if self.responder else "ok"
        text = json.dumps(out) if isinstance(out, dict) else out
        n_in = sum(len(str(m["content"])) for m in req.messages) // 4 + len(req.system) // 4
        return ProviderResult(text=text, usage=Usage(input_tokens=n_in,
                                                     output_tokens=self.out_tokens),
                              stop="end_turn")


def hash_choice(*parts: str, options: list[str]) -> str:
    h = int(hashlib.sha256("|".join(parts).encode()).hexdigest(), 16)
    return options[h % len(options)]
