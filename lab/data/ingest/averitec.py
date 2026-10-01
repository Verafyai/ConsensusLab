"""AVeriTeC (Schlichtkrull et al. 2023): real-world claims with fact-checker-derived QA evidence.

Raw format: a JSON list; fields used: claim, label, claim_date (DD-MM-YYYY), speaker,
original_claim_url, fact_checking_article, justification, claim_types.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from lab.data.ingest import base_item, flags_for

SOURCE = "averitec"
LABEL_MAP = {
    "Supported": "supported",
    "Refuted": "refuted",
    "Not Enough Evidence": "not_enough_evidence",
    "Conflicting Evidence/Cherrypicking": "conflicting",
}


def _date(s: str | None) -> str | None:
    if not s:
        return None
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return None


def ingest(path: Path) -> Iterator[dict]:
    for i, row in enumerate(json.loads(Path(path).read_text())):
        gold = LABEL_MAP.get(row.get("label", ""))
        if not gold or not row.get("claim"):
            continue
        speaker = row.get("speaker") or None
        article = row.get("fact_checking_article") or row.get("original_claim_url") or ""
        yield base_item(
            SOURCE, f"{path.name}:{i}:{row['claim']}", row["claim"], gold,
            expert_source=f"AVeriTeC annotators from fact-check: {article}".strip(),
            context=f"Speaker: {speaker}" if speaker else None,
            date=_date(row.get("claim_date")),
            expert_rationale=(row.get("justification") or None),
            source_label=row.get("label"),
            source_url=row.get("fact_checking_article") or None,
            flags=flags_for(row["claim"], speaker),
        )
