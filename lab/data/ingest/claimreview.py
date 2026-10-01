"""ClaimReview records (e.g. from the Google Fact Check Tools API), the post-cutoff source.

Raw format: JSON with a top-level "claims" list as returned by
`claims:search`: each claim has text, claimant, claimDate and claimReview[] with
publisher.site, url, title, reviewDate, textualRating.
Free-text ratings are normalized and mapped; anything unmapped is dropped, never guessed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path

from lab.data.ingest import base_item, flags_for

SOURCE = "claimreview"
LABEL_MAP = {
    "true": "supported", "correct": "supported", "accurate": "supported",
    "mostly true": "supported", "verified": "supported",
    "false": "refuted", "pants on fire": "refuted", "mostly false": "refuted",
    "fake": "refuted", "incorrect": "refuted", "inaccurate": "refuted",
    "fabricated": "refuted", "baseless": "refuted", "four pinocchios": "refuted",
    "half true": "conflicting", "mixture": "conflicting", "half-true": "conflicting",
    "mixed": "conflicting", "partly false": "conflicting", "partly true": "conflicting",
    "missing context": "conflicting", "misleading": "conflicting", "cherry picks": "conflicting",
    "unproven": "not_enough_evidence", "unsupported": "not_enough_evidence",
    "unverified": "not_enough_evidence", "no evidence": "not_enough_evidence",
    "lacks evidence": "not_enough_evidence", "research in progress": None,
    "satire": None, "outdated": None,
}


def normalize_rating(s: str) -> str:
    s = re.sub(r"[^a-z\- ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip(" -")


def map_rating(s: str) -> str | None:
    return LABEL_MAP.get(normalize_rating(s))


def ingest(path: Path) -> Iterator[dict]:
    data = json.loads(Path(path).read_text())
    for c in data.get("claims", []):
        reviews = [r for r in c.get("claimReview", []) if map_rating(r.get("textualRating", ""))]
        if not reviews or not c.get("text"):
            continue
        golds = {map_rating(r["textualRating"]) for r in reviews}
        if len(golds) > 1:  # fact-checkers disagree: not a clean gold label
            continue
        r = reviews[0]
        date = (c.get("claimDate") or r.get("reviewDate") or "")[:10] or None
        site = r.get("publisher", {}).get("site") or r.get("publisher", {}).get("name", "")
        yield base_item(
            SOURCE, r["url"], c["text"], golds.pop(),
            expert_source=f"{site} rated '{r['textualRating']}': {r['url']}",
            context=f"Claimant: {c['claimant']}" if c.get("claimant") else None,
            date=date, source_label=r["textualRating"], source_url=r["url"],
            expert_rationale=r.get("title") or None,
            flags=flags_for(c["text"], c.get("claimant")),
        )
