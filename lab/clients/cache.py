"""Content-addressed response cache. Identical calls cost $0 (spec §11)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from lab import paths
from lab.clients.base import ProviderResult, Usage


class ResponseCache:
    def __init__(self, root: Path | None = None):
        self.root = (root or paths.CACHE) / "responses"

    @staticmethod
    def key(payload: str) -> str:
        return hashlib.sha256(payload.encode()).hexdigest()

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: str) -> ProviderResult | None:
        p = self._path(key)
        if not p.exists():
            return None
        d = json.loads(p.read_text())
        return ProviderResult(text=d["text"], usage=Usage(**d["usage"]), stop=d.get("stop"),
                              refused=d.get("refused", False))

    def put(self, key: str, result: ProviderResult) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(result)))
        tmp.replace(p)
