"""Config loading. The lab refuses to run while any budget or price is a placeholder."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from lab import paths

PLACEHOLDER = "PLACEHOLDER"


class LabNotReady(RuntimeError):
    """Raised when config is incomplete. The message lists every missing value."""


def load(name: str, root: Path | None = None) -> dict[str, Any]:
    path = (root or paths.CONFIG) / f"{name}.yaml"
    with path.open() as f:
        return yaml.safe_load(f) or {}


def placeholders(tree: Any, prefix: str = "") -> list[str]:
    """Dotted keys whose value is the PLACEHOLDER sentinel (or missing/None)."""
    out: list[str] = []
    if isinstance(tree, dict):
        for k, v in tree.items():
            out += placeholders(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(tree, list):
        for i, v in enumerate(tree):
            out += placeholders(v, f"{prefix}[{i}]")
    elif tree is None or tree == PLACEHOLDER:
        out.append(prefix)
    return out


@dataclass(frozen=True)
class Config:
    models: dict[str, Any]
    prices: dict[str, Any]
    budget: dict[str, Any]
    scoring: dict[str, Any]

    def model(self, alias: str) -> dict[str, Any]:
        try:
            return self.models["models"][alias]
        except KeyError:
            raise LabNotReady(f"unknown model alias {alias!r}") from None

    def price(self, model_id: str) -> dict[str, float]:
        p = self.prices.get("models", {}).get(model_id)
        if not p or placeholders(p):
            raise LabNotReady(f"no price for model {model_id!r} in config/prices.yaml")
        return p

    def service_price(self, name: str) -> float:
        v = self.prices.get("services", {}).get(name)
        if v is None or v == PLACEHOLDER:
            raise LabNotReady(f"no price for service {name!r} in config/prices.yaml")
        return float(v)

    def cap(self, dotted: str) -> float:
        node: Any = self.budget
        for part in dotted.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        if node is None or node == PLACEHOLDER:
            raise LabNotReady(f"budget cap {dotted!r} is not set in config/budget.yaml")
        return float(node)

    def missing(self, model_aliases: list[str] | None = None) -> list[str]:
        """Everything that blocks a run: all budget caps, plus prices for the models in use."""
        out = [f"budget.yaml: {k}" for k in placeholders(self.budget)]
        aliases = model_aliases if model_aliases is not None else list(self.models["models"])
        for alias in aliases:
            spec = self.models["models"].get(alias)
            if spec is None:
                out.append(f"models.yaml: unknown alias {alias}")
                continue
            p = self.prices.get("models", {}).get(spec["id"])
            if p is None:
                out.append(f"prices.yaml: models.{spec['id']} (missing)")
            else:
                out += [f"prices.yaml: models.{spec['id']}.{k}" for k in placeholders(p)]
        return out

    def require_ready(self, model_aliases: list[str] | None = None) -> None:
        missing = self.missing(model_aliases)
        if missing:
            raise LabNotReady(
                "Lab refuses to run: these budget/price values are placeholders or missing "
                "(Rex sets them, see ops/queue/):\n  " + "\n  ".join(missing)
            )


def load_config(root: Path | None = None) -> Config:
    return Config(*(load(n, root) for n in ("models", "prices", "budget", "scoring")))


@cache
def get() -> Config:
    return load_config()
