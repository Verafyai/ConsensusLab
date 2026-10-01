# G-004 · Approve the Season 0 budget and faithfulness notes (E04b GATE, spec §5.3, §14.6)

**Status:** OPEN · waiting on Rex
**Blocks:** `python -m lab.season0 screen` and `holdout`, and the replication scorecard

## What to review

1. **The eight paper cards** in `library/cards/`. Each ends with a **Faithfulness note**. Every page reference has been checked word for word against the PDF (`uv run python -m lab.library.cards check`). The biggest adaptation risks the cards report:
   - **Two-sided debate vs. four labels.** No advocate argues "not enough evidence" or "conflicting". Scores are reported for all labels and for the supported/refuted subset.
   - **Model family vs. side.** Debates swap sides per item (`swap_sides: true`) so the two aren't confounded.
   - **Weak information asymmetry.** Short web excerpts replace the papers' long hidden texts, so the judge may already know many claims.
   - **Michael 2023's AI-judge condition was already a null result.** A null from us replicates the paper rather than contradicting it.
   - **Other mechanics** (interactive judges, per-round penalties, temperature 0) aren't reproduced.
2. **The test plan** in `library/season0.yaml`: which protocol is compared against which control for each paper, and the direction expected. `sesoi: 0.02` is the smallest macro-F1 effect that counts.
3. **The shared model tier (§14.6).** It's currently claude-sonnet plus grok-fast, with claude-haiku as the "weak judge".
4. **The budget.** Set `season0.max_usd_screening` and `season0.max_usd_holdout` in `config/budget.yaml`, then run:

   ```bash
   uv run python -m lab.season0 plan
   ```

   It prints configurations × 100 items × $/item and stops if the total is over the cap. The plan has 28 configurations. That's more than the spec's 12-configuration example, because it includes every control the cards asked for. Trim `extra_configs` to cut cost.

## How to close

`touch library/season0.approved`, commit, and move this file to `ops/queue/closed/`.
