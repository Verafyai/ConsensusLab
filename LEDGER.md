# Ledger

Live build status (spec §12). A chunk is DONE only when every acceptance criterion passes. BLOCKED means a GATE is waiting on Rex (see `ops/queue/`). BUILT means the code and offline tests are done, but some acceptance criterion needs a GATE (keys, budget, approval) before it can be checked.

| ID | Chunk | Depends on | Status | Done (date · commit) | Notes |
|---|---|---|---|---|---|
| E00 | Scaffold | none | DONE | 2026-10-01 · a930641 | CI green; `python -m lab check` refuses placeholders. GATE G-001 (budget, prices) open. |
| E01 | Data | E00 | BUILT | 2026-10-01 · fcd3487 | Schema, 8 ingesters, splits + post-cutoff slice, MDE report, holdout outside repo with permission test. Needs G-002 (sources) to produce real splits. |
| E02 | Clients and metering | E00 | BUILT | 2026-10-01 · 2f5bebb | Cache=$0 and pre-call refusal tested. Smoke-run reconciliation needs G-003 (keys). |
| E03 | Evidence retrieval | E02 | DONE | 2026-10-01 · 78a5e5f | Blocklist, date filter, 40-word cap tested. |
| E04 | Protocol engine | E02, E03 | BUILT | 2026-10-01 · efeaad1 | All baselines run on 10 items offline (fake models) within budget; transcripts validate. Live 10-item run needs G-001..G-003. |
| E04b | Library scan and Season 0 | E04 | BUILT | 2026-10-01 · 4731ac2 | 8 cards, all page refs verified in CI; seeds; quote verifier; Season 0 plan. GATE G-004 open. |
| E04c | Testing zones | E04b | BUILT | 2026-10-01 · 587db1b | Knob limits, holdout weekly budget, control/Z1 raw + matched cost tested; 3-iteration refinement offline. Live run needs gates. |
| E05 | Scoring | E01 | DONE | 2026-10-01 · 9b90ccc | Hand-computed fixtures; deterministic bootstrap. |
| E06 | Orchestrator | E04, E05 | DONE | 2026-10-01 · 45a7403 | E2E with stub experimenter: better promoted, noise = no detectable difference, over-budget refused. |
| E07 | Experimenter | E06 | TODO | | |
| E08 | Evidence replay | E04 | TODO | | |
| E09 | Performance dashboard and lab controls | E04c, E05, E08 | TODO | | |
| E10 | Readability and glanceability | E08 | TODO | | |
| E11 | herdr harness | E06 | TODO | | |
| E12 | Video | E08 | TODO | | |
| E13 | Grok agent | E12, E06 | TODO | | |
| E14 | Collector | E13 | TODO | | |
| E15 | Track B experiments | E10, E14 | TODO | | |
| E16 | Reports | E07, E14 | TODO | | |
| E17 | Rater registry and weighted ratings | E09, E14 | TODO | | |
