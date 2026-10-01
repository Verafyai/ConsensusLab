"""SciFact (Wadden et al. 2020): expert-written scientific claims. Claims CC BY 4.0.

Raw format: claims_*.jsonl with id, claim, evidence {doc_id: [{sentences, label}]},
cited_doc_ids. Label is derived at claim level across all evidence documents.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from lab.data.ingest import base_item, flags_for

SOURCE = "scifact"
LABEL_MAP = {"SUPPORT": "supported", "CONTRADICT": "refuted"}


def claim_label(evidence: dict) -> tuple[str, str]:
    """(our label, mapping kind). Mixed SUPPORT/CONTRADICT is conflicting, flagged manual."""
    labels = {e["label"] for docs in evidence.values() for e in docs}
    if not labels:
        return "not_enough_evidence", "exact"
    if len(labels) > 1:
        return "conflicting", "manual"
    return LABEL_MAP[labels.pop()], "exact"


def ingest(path: Path) -> Iterator[dict]:
    with Path(path).open() as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if "evidence" not in row:      # unlabeled test split
                continue
            gold, kind = claim_label(row["evidence"])
            yield base_item(
                SOURCE, str(row["id"]), row["claim"], gold,
                expert_source="SciFact expert annotators against cited abstracts "
                              "(https://github.com/allenai/scifact)",
                source_label=",".join(sorted({e["label"] for d in row["evidence"].values()
                                              for e in d})) or "NEI",
                mapping=kind, flags=flags_for(row["claim"], extra=["health"]),
            )
