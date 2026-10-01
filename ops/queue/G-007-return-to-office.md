# G-007 · Show the lab in Return To Office (E11b, optional)

**Status:** OPEN · optional

The lab now publishes an RTO-compatible feed in `ops/rto/`. It uses the same schema and SHA-256 hash chain as the Collective's `agents/bin/eventlog.py`:

- `events.ndjson`: cycles, decisions, budget alerts, a heartbeat per component, and KPI updates. Check the chain with `uv run python -m harness.rto verify`.
- `roster.json`: the lab's agents, all in room `consensus-lab`.
- `room.json`: the room's name, a one-line description and its KPIs (champion, holdout macro-F1, experiments, spend today, queue size).

The orchestrator syncs the feed at the end of every cycle.

**What's needed:** the RTO floor (`Collective/dashboard/server.py`) needs to read a second event source and roster. That's a change to the Collective, which goes through its own governance, so I didn't touch it. Decide whether to propose it there. The simplest approach: on load, the floor merges `<lab>/ops/rto/events.ndjson` and `<lab>/ops/rto/roster.json`, configured by a path in its config.
