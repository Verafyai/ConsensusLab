# G-001 · Budget caps and prices (E00 GATE, spec §11, §14.1, §14.6)

**Status:** OPEN · waiting on Rex
**Blocks:** every paid run (`python -m lab check` exits 2 until this is done)

## What's needed

Fill every `PLACEHOLDER` in:

1. `config/budget.yaml`: per item, per item for the champion, per experiment, per day, per month, social per day and per month, and the Season 0 screening and holdout caps.
2. `config/prices.yaml`: USD per million tokens for each model, plus per-request service prices (search, X API).
3. `config/models.yaml`: `knowledge_cutoff` per model (drives the post-cutoff holdout slice).

## Suggested starting values (please verify)

These are suggestions only. The lab never hardcodes prices.

**Anthropic list prices** (per million tokens, from Anthropic's current model table, 2026-09-25):

| model id | input | output | cache_read |
|---|---|---|---|
| claude-opus-5-5 | 4.00 | 20.00 | 0.20 |
| claude-sonnet-5-5 | 2.00 | 10.00 | 0.20 |
| claude-haiku-4-5 | 1.00 | 5.00 | 0.10 |

**xAI (grok-4.7, grok-4.7-fast):** take these from your xAI console. The xAI client also records `usage.cost_in_usd_ticks` from each response, so metered cost is reconciled against xAI's own number.

**Search:** the evidence retriever uses the Brave Search API (`BRAVE_API_KEY`). Check your plan's per-query price.

**Budget, sized to the Season 0 example in spec §5.3:**

| key | suggestion |
|---|---|
| max_usd_per_item | 0.15 |
| max_usd_per_item_champion | 0.10 |
| max_usd_per_experiment | 25 |
| max_usd_per_day | 40 |
| max_usd_per_month | 600 |
| social.max_usd_per_day | 2 |
| social.max_usd_per_month | 40 |
| season0.max_usd_screening | 80 |
| season0.max_usd_holdout | 200 |

## Related decisions (spec §14)

- **§14.3 Panel models:** the default panel is Opus 5.5, Sonnet 5.5, Haiku 4.5, grok-4.7 and grok-4.7-fast. Confirm the Grok model ids, and say whether to add OpenRouter. Jev has no API on disk, so `jev-aggregate` stays off until you point me at one.
- **§14.6 Season 0 shared tier:** I suggest `claude-sonnet-5-5` plus `grok-4.7-fast` as the mid tier.

## How to close

Edit the three files, run `uv run python -m lab check`, and move this file to `ops/queue/closed/`.
