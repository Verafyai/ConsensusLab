"""X poll score (spec §6.1.5). Track B, also a review signal. Votes are anonymous totals,
so this is reported raw and unweighted, as a secondary signal."""

from __future__ import annotations

from lab.scoring.human import wilson_lower

OPTIONS = ["Yes, and convincing", "Right, but weak evidence", "Wrong verdict", "Can't tell"]


def poll_score(counts: dict[str, int], min_votes: int = 20,
               wrong_threshold: float = 0.35, z: float = 1.96) -> dict:
    n = sum(counts.get(o, 0) for o in OPTIONS)
    yes = counts.get(OPTIONS[0], 0)
    wrong = counts.get(OPTIONS[2], 0)
    counted = n >= min_votes
    return {"n": n, "counts": {o: counts.get(o, 0) for o in OPTIONS},
            "counted": counted,
            "score": wilson_lower(yes, n, z) if counted else None,
            "wrong_share": wrong / n if n else 0.0,
            # Creates a review item for Rex; never changes a label (spec §2, §7.5).
            "review": counted and n > 0 and wrong / n > wrong_threshold}
