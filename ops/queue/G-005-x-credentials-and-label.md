# G-005 · X and xAI credentials, and the automated label (E13 GATE, spec §9.2, §14.4)

**Status:** OPEN · waiting on Rex
**Blocks:** the live smoke test (one real case post with a poll), the collector on real posts, and the Grok captions

## What's needed

1. **Credentials in `.env`:**
   - `XAI_API_KEY`
   - `X_API_KEY`, `X_API_SECRET`
   - `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET` (OAuth 1.0a user context for @VerafyAI, with read and write)
   - The X app's tier must allow `GET /2/tweets/search/recent`, which reading replies needs.
2. **The "Automated" label** on @VerafyAI. Set it by hand in X: Settings → Your account → Account information → Automation.
3. **Confirm the public dashboard URL** used in every post. It's `https://verafyai.github.io/ConsensusLab` in `social/policy.yaml`: GitHub Pages on this repo, built by `python -m viz.dashboard.export`.
4. **Posting cadence (§14.4):** the default is at most 1 case post per day, posted 15:00–18:00 UTC. Lab updates go out Mondays.

## What the first post will verify

X's docs don't say whether a poll can be attached to a post that carries a video. The agent tries it once:

- If X accepts, it records `poll_with_media: true` in `social/x_capabilities.yaml`.
- If X rejects it, it records `false` and posts the poll as a reply in the same thread, as the spec designs.

## How to close

```bash
uv run python -m social.agent --dry-run --force case_post    # compose and check, no posting
uv run python -m social.agent --force case_post              # the live smoke test
```
