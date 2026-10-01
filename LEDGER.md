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
| E07 | Experimenter | E06 | BUILT | 2026-10-01 · ddb4cfe | Prompt, sandboxed headless runner (holdout canary test passed with real claude), dev-only tools, consolidation, hit rate; 5 cycles offline. 5 live cycles need G-001..G-003. |
| E08 | Evidence replay | E04 | BUILT | 2026-10-01 · 9c39222 | Replay, card mode, autoplay, captions, phone layout; browser-tested on 3 samples. 'Renders from real transcripts' needs a live run (G-001..G-003). |
| E09 | Performance dashboard and lab controls | E04c, E05, E08 | BUILT | 2026-10-01 · 7bb62c0 | Snapshot, server, controls, job queue, Record, static export; UI tested on demo data. Real data needs a live run. |
| E10 | Readability and glanceability | E08 | BUILT | 2026-10-01 · 7bb62c0 | Readability + five-second glance + human agreement report; live card read needs keys. |
| E11 | herdr harness | E06 | BUILT | 2026-10-01 · 7bb62c0 | launch.sh (herdr-plus template, tmux fallback), panes, monitor red on dead/stale/cap tested. Live herdr launch not yet run. E11b Return To Office feed built (ops/rto, G-007). |
| E12 | Video | E08 | DONE | 2026-10-01 · 9c39222 | 720x720 MP4 in ~32 s, 29.7 s long, passes X limits (checked from docs); captions verified legible on frames. |
| E13 | Grok agent | E12, E06 | BUILT | 2026-10-01 · c46ca73 | Policy in code, flagged exclusion, committed-file rule, PAUSE tested. Live smoke post needs G-005. |
| E14 | Collector | E13 | BUILT | 2026-10-01 · c46ca73 | 24/72h scores, injection-as-data test. Real post needs G-005. |
| E15 | Track B experiments | E10, E14 | BUILT | 2026-10-01 · 7bb62c0 | Variant scoring + §6.3 selection rule tested. A live presentation experiment needs data + keys. |
| E16 | Reports | E07, E14 | DONE | 2026-10-01 · 06234a3 | 3 consecutive digests with no missing fields (test). |
| E17 | Rater registry and weighted ratings | E09, E14 | BUILT | 2026-10-01 · c46ca73 | All listed tests pass; rating page OAuth tested with a mock. GATE G-006 (rules, hosting). |
