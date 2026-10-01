"""FACTors (Altuncu et al. 2025): IFCN/EFCSN fact-checks with normalized ratings. CC BY 4.0.

Raw format: CSV. Column names follow the paper (claim, normalised_rating, original_verdict,
url, date_published, organisation, author, claim_id); confirm against the release and adjust
COLS if they differ. No rationale ships with the data.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

from lab.data.ingest import base_item, flags_for

SOURCE = "factors"
COLS = {"claim": "claim", "rating": "normalised_rating", "verdict": "original_verdict",
        "url": "url", "date": "date_published", "org": "organisation", "id": "claim_id"}
LABEL_MAP = {"true": ("supported", "exact"), "false": ("refuted", "exact"),
             "partially true": ("conflicting", "lossy"), "misleading": ("conflicting", "lossy"),
             "unverifiable": ("not_enough_evidence", "exact")}


def ingest(path: Path) -> Iterator[dict]:
    with Path(path).open(newline="") as f:
        for row in csv.DictReader(f):
            mapped = LABEL_MAP.get((row.get(COLS["rating"]) or "").strip().lower())
            text = (row.get(COLS["claim"]) or "").strip()
            if not mapped or len(text) < 3:
                continue
            gold, kind = mapped
            url = row.get(COLS["url"]) or None
            org = row.get(COLS["org"]) or "fact-checker"
            yield base_item(
                SOURCE, row.get(COLS["id"]) or url or text, text, gold,
                expert_source=f"{org} rated '{row.get(COLS['verdict'], '')}': {url or ''}".strip(),
                date=(row.get(COLS["date"]) or "")[:10] or None,
                source_label=row.get(COLS["verdict"]) or row.get(COLS["rating"]),
                source_url=url, mapping=kind, flags=flags_for(text),
            )
