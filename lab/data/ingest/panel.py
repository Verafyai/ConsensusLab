"""Rex's own expert panel set (spec §4.2). Raw format: JSONL already in our item schema,
minus id/split; `key` gives a stable identity. Rex is the only writer of this file."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from lab.data.ingest import base_item
from lab.data.schema import read_jsonl

SOURCE = "panel"
LABEL_MAP = None  # already in our labels


def ingest(path: Path) -> Iterator[dict]:
    for row in read_jsonl(Path(path)):
        key = row.pop("key")
        for k in ("id", "split"):
            row.pop(k, None)
        text, gold, src = row.pop("text"), row.pop("gold"), row.pop("expert_source")
        yield base_item(SOURCE, key, text, gold, src, **row)
