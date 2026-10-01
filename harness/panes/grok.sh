#!/usr/bin/env bash
# @VerafyAI social agent: posting and collection on schedule (social/PAUSE stops posting).
cd "$(dirname "$0")/../.." && exec uv run python -m social.agent "$@"
