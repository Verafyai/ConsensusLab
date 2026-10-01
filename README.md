# Consensus Lab

An autonomous experimenter that invents and tests ways for multiple AI models to reach consensus on fact-checking questions and debates. It scores every attempt against human expert judgments, replays the evidence process visually, and reports its work publicly through [@VerafyAI](https://x.com/VerafyAI).

**Agents propose, code decides.** A headless Claude experimenter proposes one experiment at a time. A plain-code orchestrator runs it on the dev split, runs the hidden holdout when the result is promising, applies the promotion rule and writes the learning. The experimenter never scores its own work and never sees the holdout.

- Full spec: [`docs/SPEC.md`](docs/SPEC.md)
- Build status, chunk by chunk: [`LEDGER.md`](LEDGER.md)
- Entrenched rules: [`CHARTER.md`](CHARTER.md)
- Rex's steering: [`STEERING.md`](STEERING.md)
- What the lab has learned: [`LEARNINGS.md`](LEARNINGS.md)
- Requests waiting on Rex: [`ops/queue/`](ops/queue/)

## Quick start

```bash
uv sync                      # Python 3.12+
cp .env.example .env         # add keys; never commit .env
uv run python -m lab check   # refuses to run until budget and prices are set
uv run pytest -q
```

## Running it

```bash
harness/launch.sh                       # the herdr workspace: orchestrator, claude, grok, dashboard, monitor
uv run python -m viz.dashboard.server   # dashboard only: http://127.0.0.1:8770
uv run python -m lab.orchestrator.loop --once        # one experiment cycle
uv run python -m lab.zones refine Z4 --iterations 3 --budget 10
uv run python -m lab.season0 plan       # Season 0 cost estimate vs its cap
uv run python -m lab.reports daily      # today's digest → ops/reports/
uv run python -m social.agent --dry-run --force case_post
uv run python -m viz.dashboard.demo /tmp/cl-demo     # offline demo data (no spend)
```

| Piece | Where |
|---|---|
| Data, splits, holdout (outside the repo) | `lab/data/`, `lab/orchestrator/holdout.py`, `data/SOURCES.md` |
| Model gateway: cache, metering, caps | `lab/clients/` |
| Evidence with the leakage guard | `lab/evidence/` |
| Protocol engine and library | `lab/protocols/`, `lab/protocols/library/` (seed protocols in `seed/`) |
| Season 0 paper cards (page refs verified) | `library/cards/`, `library/season0.yaml`, `lab/season0.py` |
| Testing zones Z1–Z7 | `zones/`, `lab/zones.py` |
| Scoring (Track A and B) | `lab/scoring/`, `lab/trackb.py` |
| Orchestrator, learnings, jobs | `lab/orchestrator/` |
| Experimenter (headless Claude Code, sandboxed) | `lab/experimenter/`, `harness/experimenter-settings.json` |
| Replay, dashboard, video | `viz/replay/`, `viz/dashboard/`, `viz/render_video.py` |
| @VerafyAI agent, collector, raters | `social/` |
| Harness, monitor, Return To Office feed | `harness/` |

Nothing paid runs until Rex closes the gates in `ops/queue/` (budget, prices, sources, keys).

## Two tracks, never blended

| Track A: Consensus | Track B: Presentation |
|---|---|
| models, prompts, rounds, aggregation, evidence | layout, wording, animation, video |
| scored by accuracy (macro-F1), calibration, cost | scored by readability, glanceability, human ratings, polls, social |
| decides **which verdict** | decides **how it's shown** |

Audience signals never touch verdicts. A disputed verdict becomes a review item for Rex. Labels change only by his hand.

## Kill switches

- `touch ops/STOP` halts everything after the current step.
- `touch social/PAUSE` halts posting immediately.
