# Ledger

Live build status (spec §12). A chunk is DONE only when every acceptance criterion passes. BLOCKED means a GATE is waiting on Rex (see `ops/queue/`). BUILT means the code and offline tests are done, but some acceptance criterion needs a GATE (keys, budget, approval) before it can be checked.

| ID | Chunk | Depends on | Status | Done (date · commit) | Notes |
|---|---|---|---|---|---|
| E00 | Scaffold | none | TODO | | |
| E01 | Data | E00 | TODO | | |
| E02 | Clients and metering | E00 | TODO | | |
| E03 | Evidence retrieval | E02 | TODO | | |
| E04 | Protocol engine | E02, E03 | TODO | | |
| E04b | Library scan and Season 0 | E04 | TODO | | |
| E04c | Testing zones | E04b | TODO | | |
| E05 | Scoring | E01 | TODO | | |
| E06 | Orchestrator | E04, E05 | TODO | | |
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
