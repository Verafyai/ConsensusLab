"""Cost to iterate (spec §6.1.2). Track A."""

from __future__ import annotations

from statistics import median


def summarize(transcripts: list[dict]) -> dict:
    n = len(transcripts)
    if not n:
        return {"n": 0, "usd_total": 0.0, "usd_per_item": 0.0, "usd_per_item_uncached": 0.0,
                "tokens_per_item": 0.0, "median_latency_s": 0.0, "calls_per_item": 0.0}
    usd = sum(t["usd"] for t in transcripts)
    # What the run would cost without the cache: sum of per-turn costs as first metered.
    uncached = sum(_uncached(t) for t in transcripts)
    tokens = sum(x.get("tokens", 0) for t in transcripts for x in t["turns"])
    return {"n": n, "usd_total": round(usd, 6), "usd_per_item": usd / n,
            "usd_per_item_uncached": uncached / n, "tokens_per_item": tokens / n,
            "median_latency_s": median(t["latency_s"] for t in transcripts),
            "calls_per_item": sum(len(t["turns"]) for t in transcripts) / n}


def _uncached(t: dict) -> float:
    """Cached turns carry usd 0; their original cost is recorded in `usd_list` when known."""
    return t.get("usd_uncached", t["usd"])


def efficiency(f1_gain: float, usd_per_item: float) -> float | None:
    """Macro-F1 gain over the best single model per dollar per item."""
    return f1_gain / usd_per_item if usd_per_item > 0 else None
