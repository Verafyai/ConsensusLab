#!/usr/bin/env bash
# Live stream of the headless Claude experimenter (the orchestrator invokes it).
cd "$(dirname "$0")/../.." && mkdir -p ops/experimenter && exec uv run python -m harness.live --follow ops/experimenter/live.jsonl
