#!/usr/bin/env bash
# The judge: plain code. Runs cycles until budget or ops/STOP, then waits for dashboard jobs.
cd "$(dirname "$0")/../.." && exec uv run python -m lab.orchestrator.loop "$@"
