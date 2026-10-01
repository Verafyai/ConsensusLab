"""Quote verification for information-asymmetric protocols (spec §5.3, Michael et al.).

A debater's quote counts only if it appears verbatim in the fetched source text, after
normalizing whitespace, quote marks and dashes. Fabricated or altered quotes are rejected.
"""

from __future__ import annotations

import re

_TRANS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                        "–": "-", "—": "-", " ": " ", "…": "..."})


def normalize(s: str) -> str:
    s = s.translate(_TRANS)
    s = re.sub(r"\s+", " ", s).strip().strip('"\'').strip()
    return s.lower()


def verify(quote: str, source_text: str | None, max_words: int = 40) -> tuple[bool, str]:
    """(ok, reason)."""
    q = normalize(quote)
    if not q:
        return False, "empty"
    if len(q.split()) > max_words:
        return False, f"over {max_words} words"
    if len(q.split()) < 3:
        return False, "too short to verify"
    if not source_text:
        return False, "source text unavailable"
    if q.rstrip(".") in normalize(source_text):
        return True, "verbatim"
    return False, "not found in source"
