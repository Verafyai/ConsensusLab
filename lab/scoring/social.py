"""Social score (spec §6.1.6). Track B. Engagement rate and a social index relative to the
account's trailing 30-day median (1.0 = typical)."""

from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median

INTERACTIONS = ["likes", "reposts", "replies", "quotes", "bookmarks"]


def engagement_rate(metrics: dict) -> float | None:
    imp = metrics.get("impressions") or 0
    if imp <= 0:
        return None
    return sum(metrics.get(k, 0) or 0 for k in INTERACTIONS) / imp


def social_index(rate: float | None, history: list[tuple[datetime, float]], at: datetime,
                 days: int = 30) -> float | None:
    """history: (post time, engagement rate) for the account's earlier posts."""
    window = [r for t, r in history if at - timedelta(days=days) <= t < at and r is not None]
    if rate is None or not window:
        return None
    m = median(window)
    return rate / m if m > 0 else None
