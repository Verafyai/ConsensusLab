"""Item schema (spec §4.1) and validator."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import jsonschema

LABELS = ["supported", "refuted", "not_enough_evidence", "conflicting"]
DEBATE_LABELS = ["affirm_wins", "deny_wins"]
FLAGS = ["political", "named_person", "health", "crowd_labeled"]

ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["id", "kind", "text", "label_set", "gold", "expert_source", "split"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "pattern": r"^q-[a-z0-9]+-[0-9a-f]{10}$"},
        "kind": {"enum": ["claim", "question", "debate"]},
        "text": {"type": "string", "minLength": 3, "maxLength": 2000},
        "context": {"type": ["string", "null"], "maxLength": 4000},
        "date": {"type": ["string", "null"], "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        "label_set": {"type": "array", "items": {"type": "string"}, "minItems": 2,
                      "uniqueItems": True},
        "gold": {"type": "string"},
        "expert_source": {"type": "string", "minLength": 3},
        "expert_rationale": {"type": ["string", "null"], "maxLength": 1200},
        "split": {"enum": ["dev", "holdout", "unassigned"]},
        "flags": {"type": "array", "items": {"enum": FLAGS}, "uniqueItems": True},
        "source": {"type": "string"},          # dataset key, e.g. "averitec"
        "source_label": {"type": ["string", "null"]},  # original label before mapping
        "source_url": {"type": ["string", "null"]},    # page that must be blocked from retrieval
    },
}

_validator = jsonschema.Draft202012Validator(ITEM_SCHEMA)


class InvalidItem(ValueError):
    pass


def validate(item: dict[str, Any]) -> dict[str, Any]:
    errors = sorted(_validator.iter_errors(item), key=lambda e: list(e.path))
    if errors:
        e = errors[0]
        where = "/".join(map(str, e.path)) or "<root>"
        raise InvalidItem(f"{item.get('id', '?')}: {where}: {e.message}")
    if item["gold"] not in item["label_set"]:
        raise InvalidItem(f"{item['id']}: gold {item['gold']!r} not in label_set")
    return item


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open() as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
            n += 1
    return n
