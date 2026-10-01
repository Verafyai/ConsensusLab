"""Human dashboard rating (spec §6.1.4). Track B. Wilson lower bound so a 2-of-2 doesn't
outrank a 40-of-50."""

from __future__ import annotations

import math


def wilson_lower(successes: float, n: float, z: float = 1.96) -> float:
    """Lower bound of the Wilson score interval. Works with fractional (effective) n."""
    if n <= 0:
        return 0.0
    p = successes / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centre - margin) / denom)


def thumbs_score(up: int, down: int, z: float = 1.96) -> dict:
    return {"up": up, "down": down, "n": up + down, "wilson": wilson_lower(up, up + down, z)}
