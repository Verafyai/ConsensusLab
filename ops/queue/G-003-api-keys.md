# G-003 · API keys in .env (E02 smoke run, E03 search, every live run)

**Status:** OPEN · waiting on Rex
**Blocks:**
- The E02 acceptance criterion "costs reconcile with each provider's reported usage on a smoke run".
- Live evidence retrieval.
- Every live experiment.

## What's needed

Copy `.env.example` to `.env` (it's gitignored) and fill in at least:

- `ANTHROPIC_API_KEY`
- `XAI_API_KEY`
- `BRAVE_API_KEY`: evidence search (the Brave Search API). If you'd rather use a different search provider, tell me which one and I'll add a backend.

Optional:

- `OPENROUTER_API_KEY`
- `JEV_BASE_URL` and `JEV_API_KEY`: Jev must be an OpenAI-compatible endpoint. No Jev API was found on disk, so `jev-aggregate` stays off.

The X keys belong to G-005 (E13).

## How to close

```bash
uv run python -m lab check                   # budgets and prices (G-001) must be set first
CL_LIVE=1 uv run pytest -q -m live           # smoke run: one tiny call per provider,
uv run python -m lab.clients.smoke           #   metered $ next to provider-reported $
```
