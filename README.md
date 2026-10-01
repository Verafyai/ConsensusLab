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
