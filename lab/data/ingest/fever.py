"""FEVER (Thorne et al. 2018): Wikipedia-derived claims. Sanity baseline only, dev split only.

Raw format: JSONL with id, label (SUPPORTS/REFUTES/NOT ENOUGH INFO), claim.
Labels are crowd annotations against Wikipedia, not expert fact-checks, so items carry the
crowd_labeled flag and lab.data.splits never places them in the holdout.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from lab.data.ingest import base_item, flags_for

SOURCE = "fever"
LABEL_SET = ["supported", "refuted", "not_enough_evidence"]
LABEL_MAP = {"SUPPORTS": "supported", "REFUTES": "refuted",
             "NOT ENOUGH INFO": "not_enough_evidence"}


def ingest(path: Path) -> Iterator[dict]:
    with Path(path).open() as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            gold = LABEL_MAP.get(row.get("label", ""))
            if not gold:
                continue
            yield base_item(
                SOURCE, str(row["id"]), row["claim"], gold, label_set=list(LABEL_SET),
                expert_source="FEVER crowd annotators against Wikipedia (2017 snapshot)",
                source_label=row["label"], mapping="exact",
                flags=flags_for(row["claim"], extra=["crowd_labeled"]),
            )
