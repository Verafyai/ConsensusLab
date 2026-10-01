"""Ingesters turn raw source files into validated items (spec §4).

Each ingester exposes `SOURCE` (its key), `LABEL_MAP` (source label → our label, or None to drop)
and `ingest(path) -> Iterator[dict]`. Ingestion runs only for sources Rex has approved in
data/SOURCES.md (GATE G-002); `lab.data.build` enforces this via data/approved_sources.txt.
"""

from __future__ import annotations

import hashlib
import re

from lab.data.schema import LABELS

POLITICAL_HINTS = re.compile(
    r"\b(democrat|republican|gop|congress|senat|parliament|election|ballot|president|"
    r"governor|mayor|minister|campaign|vote[sd]?|voting|labour|tory|biden|trump|harris|"
    r"obama|clinton|putin|zelensk|netanyahu|modi|abortion|immigra|gun control)\w*",
    re.I,
)
# Two capitalized words in a row, not at sentence start, is a cheap named-person signal;
# ingesters with a speaker field use that instead.
NAME_HINT = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-z]+ [A-Z][a-z]+\b")


def item_id(source: str, key: str) -> str:
    return f"q-{source}-{hashlib.sha256(f'{source}:{key}'.encode()).hexdigest()[:10]}"


def flags_for(text: str, speaker: str | None = None, party: str | None = None,
              extra: list[str] | None = None) -> list[str]:
    flags = set(extra or [])
    if party or POLITICAL_HINTS.search(text) or (speaker and POLITICAL_HINTS.search(speaker)):
        flags.add("political")
    if speaker or NAME_HINT.search(text):
        flags.add("named_person")
    return sorted(flags)


def base_item(source: str, key: str, text: str, gold: str, expert_source: str, **kw) -> dict:
    item = {
        "id": item_id(source, key), "kind": kw.pop("kind", "claim"), "text": text.strip(),
        "label_set": kw.pop("label_set", list(LABELS)), "gold": gold,
        "expert_source": expert_source, "split": "unassigned", "source": source,
        "flags": kw.pop("flags", []),
    }
    item.update({k: v for k, v in kw.items() if v is not None})
    return item
