"""Provider-neutral request/response types for every model call the lab makes."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


@dataclass
class Request:
    model: str                                  # alias from config/models.yaml
    messages: list[dict[str, Any]]              # [{"role": "user"|"assistant", "content": ...}]
    system: str = ""
    max_tokens: int = 1024
    json_schema: dict[str, Any] | None = None   # constrain output to this JSON schema
    sample: int = 0                             # distinguishes repeated samples (self-consistency)
    effort: str | None = None                   # overrides the model's default effort

    def cache_payload(self, model_id: str, provider: str) -> str:
        d = asdict(self)
        d.pop("model")
        d.update(model_id=model_id, provider=provider)
        return json.dumps(d, sort_keys=True, ensure_ascii=False)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    provider_usd: float | None = None   # cost as reported by the provider, when it reports one


@dataclass
class Response:
    text: str
    usage: Usage
    usd: float                         # metered: tokens × config/prices.yaml (0 when cached)
    model_id: str
    cached: bool = False
    refused: bool = False
    latency_s: float = 0.0
    data: Any = None                   # parsed JSON when json_schema was set
    raw_stop: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def tokens(self) -> int:
        return self.usage.input_tokens + self.usage.output_tokens + self.usage.cache_read_tokens


@dataclass
class ProviderResult:
    text: str
    usage: Usage
    stop: str | None = None
    refused: bool = False


class TransientError(RuntimeError):
    """Retryable provider failure (429, 5xx, connection)."""


class Provider(Protocol):
    name: str

    def send(self, req: Request, model_id: str, params: dict[str, Any]) -> ProviderResult: ...
