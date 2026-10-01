# G-006 · Rater rules and hosting for the rating page (E17 GATE, spec §6.4, §14.7)

**Status:** OPEN · waiting on Rex

## Decisions

1. **Eligibility thresholds** (`config/scoring.yaml` → `raters`), currently as the spec says:
   - accounts at least 90 days old
   - at least 50 posts
   - at least 3 calibration cases
   - not automated, not blocklisted

   X's API doesn't expose an "automated" flag reliably, so the code treats `verified_type == "automated"` as automated. Is that enough?
2. **Clout formula:** `1 + 0.25·log10(followers/1000)`, clamped to [0.75, 1.5]. Reliability is Beta(2,2). There's a 5% cap per case, 20 ratings per day per rater, and the score counts only at effective n ≥ 15.
3. **Burst quarantine:** 8 or more raters with accounts under 7 days old on one case within 10 minutes. Is that sensitive enough?
4. **Hosting for the rating page** (`social/ratepage.py`). It needs a public HTTPS URL and an X OAuth 2.0 app client id (`X_CLIENT_ID`), with the callback `<url>/callback`. The page keeps rater identities and weights in `social/private/` (gitignored), so it needs a small server, not GitHub Pages. Options: a small VM or Fly.io, or behind the existing Verafy domain.
5. **Verified domain experts** (reliability floor 0.8): who verifies them, and how? A list maintained in `social/private/`?
