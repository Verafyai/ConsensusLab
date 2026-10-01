"""LIAR (Wang 2017): PolitiFact statements with six-way truth ratings.

Raw format: TSV with columns id, label, statement, subjects, speaker, job, state, party,
5 credit-history counts, context. No dates or rationales; flagged political by construction.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

from lab.data.ingest import base_item, flags_for

SOURCE = "liar"
# Six-way PolitiFact scale collapsed to our set. half-true is ambiguous by design and maps
# to conflicting; barely-true leans refuted. Rex approves this mapping in data/SOURCES.md.
LABEL_MAP = {
    "true": "supported",
    "mostly-true": "supported",
    "half-true": "conflicting",
    "barely-true": "refuted",
    "false": "refuted",
    "pants-fire": "refuted",
}


def ingest(path: Path) -> Iterator[dict]:
    with Path(path).open(newline="") as f:
        for row in csv.reader(f, delimiter="\t"):
            if len(row) < 3:
                continue
            sid, label, statement = row[0], row[1], row[2]
            gold = LABEL_MAP.get(label)
            if not gold:
                continue
            speaker = row[4] if len(row) > 4 and row[4] else None
            party = row[7] if len(row) > 7 and row[7] not in ("", "none") else None
            ctx = row[13] if len(row) > 13 and row[13] else None
            yield base_item(
                SOURCE, sid, statement, gold,
                expert_source=f"PolitiFact rating '{label}' (LIAR {sid.removesuffix('.json')})",
                context="; ".join(x for x in [f"Speaker: {speaker}" if speaker else "",
                                              f"Venue: {ctx}" if ctx else ""] if x) or None,
                source_label=label,
                flags=flags_for(statement, speaker, party, extra=["political"]),
            )
