#!/usr/bin/env bash
cd "$(dirname "$0")/../.." && exec uv run python -m viz.dashboard.server --port "${CL_DASHBOARD_PORT:-8770}"
