# G-002 · Approve data sources (E01 GATE, spec §4.2, §14.2, §14.5)

**Status:** OPEN · waiting on Rex
**Blocks:** ingestion, and with it every dev/holdout run (E04 acceptance, E04b, E06 live, E07)

## What's needed

Read `data/SOURCES.md` and answer its section 9 decisions. The short version:

- **Recommended default, Option A (license-clean):**
  - Dev: SciFact (CC BY 4.0) + FACTors (CC BY 4.0) + 50 FEVER items (CC BY-SA).
  - Holdout: post-cutoff ClaimReview items from the Data Commons feed, plus FACTors 2025.
- **AVeriTeC** is the best schema fit, but it's CC BY-NC 4.0. Should I email the authors for commercial-evaluation permission?
- **PolitiFact-derived sets** (LIAR and its variants): exclude, as recommended?
- **Post-cutoff holdout:** needs about 36 hours of human annotation for 300 items. Who annotates?
- **Your own expert panel set (§14.5):** start now or later? Ingester `panel` is ready; format in `lab/data/ingest/panel.py`.

## How to close

Write the approved source keys, one per line, to `data/approved_sources.txt`. Available keys: `scifact factors fever datacommons averitec liar claimreview panel`. Put the raw files in `data/questions/raw/<key>/`, then run:

```bash
uv run python -m lab.data.build
```

That writes `data/SPLITS.md` with the split sizes and the minimum detectable effect.
