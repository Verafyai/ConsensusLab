"""Data Commons ClaimReview feed (schema.org DataFeed, CC BY compilation). Post-cutoff source.

Raw format: {"dataFeedElement": [{"item": [ClaimReview, ...]}, ...]} where each ClaimReview has
claimReviewed, url, datePublished, author{name,url}, reviewRating{alternateName},
itemReviewed{datePublished, author{name}}, sdLicense. Ratings are mapped with the ClaimReview
normalizer; ambiguous ratings ("no evidence") are dropped pending manual review.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from lab.data.ingest import base_item, flags_for
from lab.data.ingest.claimreview import map_rating, normalize_rating

SOURCE = "datacommons"
MANUAL = {"no evidence"}
LOSSY = {"mostly true", "mostly false"}


def _reviews(feed: dict) -> Iterator[dict]:
    for el in feed.get("dataFeedElement", []):
        items = el.get("item", [])
        yield from (items if isinstance(items, list) else [items])


def ingest(path: Path) -> Iterator[dict]:
    for r in _reviews(json.loads(Path(path).read_text())):
        rating = (r.get("reviewRating") or {}).get("alternateName") or ""
        norm = normalize_rating(rating)
        gold = map_rating(rating)
        text = (r.get("claimReviewed") or "").strip()
        if not gold or norm in MANUAL or len(text) < 3 or not r.get("url"):
            continue
        reviewed = r.get("itemReviewed") or {}
        claimant = ((reviewed.get("author") or {}).get("name")) or None
        date = (reviewed.get("datePublished") or r.get("datePublished") or "")[:10] or None
        site = (r.get("author") or {}).get("name") or "fact-checker"
        yield base_item(
            SOURCE, r["url"], text, gold,
            expert_source=f"{site} rated '{rating}': {r['url']}",
            context=f"Claimant: {claimant}" if claimant else None, date=date,
            source_label=rating, source_url=r["url"],
            mapping="lossy" if norm in LOSSY else "exact",
            license=r.get("sdLicense") or None,
            flags=flags_for(text, claimant),
        )
