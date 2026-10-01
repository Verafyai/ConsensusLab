# Consensus Lab — Build Spec

> An autonomous experimenter that invents and tests ways for multiple AI models to reach consensus on factual questions and debates, scores every attempt against human expert judgments, shows the evidence process visually, and reports its work publicly through @VerafyAI on X.
>
> **For Claude Code.** Build this as a new GitHub repository, `Verafyai/consensus-lab`, chunk by chunk in the order of the ledger (§12). Each chunk lists deliverables and acceptance criteria. Don't mark a chunk done until every criterion passes. Items marked **GATE** need Rex: stop, write the request to `ops/queue/`, and move to the next unblocked chunk.

_Live chunk status is tracked in [`LEDGER.md`](../LEDGER.md); the table in §12 below is the original plan._

---

## 1. Purpose

Verafy's core bet is that structured disagreement between AI models, grounded in evidence, gets closer to the truth than any single model. Consensus Lab tests that bet continuously and in public:

1. **Generate** consensus protocols: different ways of combining models, evidence and debate.
2. **Measure** each against questions and debates that human experts have already judged.
3. **Show** the evidence process visually so a person can follow it at a glance.
4. **Ask people** whether it's good, on the dashboard and on X.
5. **Learn** from every result, write the lesson down, and use it to design the next experiment.

### What counts as success

- A champion protocol whose accuracy beats the best single model on the hidden holdout, with a confidence interval that excludes zero.
- A visual a stranger on X can understand in five seconds.
- A cost per experiment that stays inside the budget.
- A learning file that makes later experiments measurably smarter than early ones.

---

## 2. Two tracks, kept separate on purpose

The lab runs two kinds of experiments. They must never be merged into one score.

| | **Track A: Consensus** | **Track B: Presentation** |
|---|---|---|
| What changes | Models, prompts, debate rounds, aggregation rules, evidence retrieval | Layout, wording, animation, summary length, video format |
| Scored by | Accuracy, calibration, cost to iterate | Readability and glanceability, human dashboard rating, X poll score, social score |
| Decides | Which protocol produces verdicts | How verdicts are shown |

**Integrity rule (entrenched):** audience signals (thumbs, polls, engagement) may never influence which verdict a protocol reaches. Engagement rewards drama, and a fact-checker that learns to be dramatic is broken. Audience signals tune presentation only. If a poll says a verdict was wrong, that becomes a **review item** for Rex (§7.5), never an automatic label change.

---

## 3. Architecture

```
                 ┌─────────────────────── herdr session ───────────────────────┐
                 │                                                             │
  STEERING.md ──►│  claude (experimenter)      orchestrator (code, the judge)  │
  LEARNINGS.md ─►│   proposes 1 experiment ──►  budget check ─► run dev split  │
                 │                              ─► holdout + bootstrap ─►      │
                 │                              promote / reject ─► learnings  │
                 │                                       │                     │
                 │                       renders replays │ selects a case      │
                 │                                       ▼                     │
                 │  grok (social, @VerafyAI)  ◄── video + poll package         │
                 │   posts, collects poll, metrics, replies ─► feedback.jsonl  │
                 │                                                             │
                 │  dashboard (local server)   monitor (logs, spend, health)   │
                 └─────────────────────────────────────────────────────────────┘
                                    everything committed to GitHub
```

**The same rule as checkworthy:** agents propose, code decides. The Claude agent never scores its own work and never sees the holdout. The orchestrator is plain code that runs the holdout, applies the promotion rule, and writes the result.

### Repository layout

```
consensus-lab/
  README.md  STEERING.md  LEARNINGS.md  CHARTER.md
  config/            models.yaml  prices.yaml  budget.yaml  scoring.yaml
  data/              questions/ (dev only; gitignored raw), SOURCES.md, blocklist.txt
  lab/
    clients/         anthropic.py  xai.py  openrouter.py  jev.py  cache.py  meter.py
    evidence/        retrieve.py  filters.py
    protocols/       engine.py  schema.py  library/*.yaml
    scoring/         accuracy.py  calibration.py  cost.py  readability.py  glance.py
                     human.py  poll.py  social.py  bootstrap.py
    orchestrator/    loop.py  promote.py  holdout.py  learnings.py
  experiments/       E-0001/ {proposal.md, protocol.yaml, results.json, summary.md}
  runs/              <experiment>/<question>.json.gz (transcripts)
  learnings/         learnings.jsonl
  viz/               replay/ (evidence replay app)  dashboard/  render_video.py
  social/            agent.py  CLEARANCE.md  policy.yaml  posts.jsonl  feedback.jsonl
  harness/           herdr config, launch.sh, health.py
  ops/               queue/  STOP  reports/
  tests/
```

The holdout lives **outside the repo**, at `~/.consensus-lab/holdout/` by default, readable only by `lab/orchestrator/holdout.py`.

---

## 4. Data: human-judged questions and debates

### 4.1 Item schema

```json
{
  "id": "q-000123",
  "kind": "claim | question | debate",
  "text": "The claim, question, or debate motion",
  "context": "Optional: speaker, venue, arguments for a debate",
  "date": "2024-03-02",
  "label_set": ["supported", "refuted", "not_enough_evidence", "conflicting"],
  "gold": "refuted",
  "expert_source": "Which expert panel judged it, with link",
  "expert_rationale": "Short summary of the experts' reasoning (paraphrased)",
  "split": "dev | holdout",
  "flags": ["political", "named_person"]
}
```

### 4.2 Sources

Chunk E01 evaluates candidate sources for label quality, license and fit, and writes `data/SOURCES.md` for Rex to approve. Candidates to evaluate:
- **Real-world claim verification sets with human verdicts**, such as AVeriTeC.
- **Professional fact-check archives**, such as LIAR / PolitiFact-derived sets.
- **Encyclopedic claim sets**, such as FEVER, as a sanity baseline only.
- **Human-judged debates**: motions with arguments and a judged outcome. Sources must have a clear license.
- **Rex's own expert panel set**: a small, high-quality set Rex curates, which grows from review items (§7.5).

**GATE:** Rex approves the source list before ingestion.

### 4.3 Splits and contamination (critical)

- **Holdout:** expert-labeled items only, stored outside the repo, never shown to agents.
- **Temporal holdout:** a slice of items dated after the knowledge cutoff of every model in `config/models.yaml`. Models may have memorized older published fact-checks, so accuracy on old items can be inflated. The dashboard reports accuracy on both the full holdout and the post-cutoff slice. The post-cutoff number is the honest one.
- **Leakage guard:** evidence retrieval blocks fact-checking sites and the dataset's own source pages (`data/blocklist.txt`), and only returns evidence published before the item's date, when a date is known.
- **Sizes:** dev ≥ 300 items and holdout ≥ 500 where sources allow, so the bootstrap in §6.2 has power. The lab reports the minimum detectable effect for the current holdout size.

---

## 5. Consensus protocols

A protocol is a YAML file, so the experimenter can create new ones without writing code.

```yaml
id: debate-2x2-judge-opus
description: Two advocates from different model families argue for two rounds; a judge rules.
evidence:
  retrieve: true
  max_sources: 6
  per_agent: shared        # shared | independent
agents:
  - {role: advocate, side: affirm, model: claude-sonnet}
  - {role: advocate, side: deny,   model: grok}
  - {role: judge,                  model: claude-opus}
rounds: 2
aggregation: judge          # judge | majority | weighted | jev | mean_prob
output: {verdict: label_set, confidence: probability, rationale_words: 60}
budget: {max_usd_per_item: 0.08}
```

### 5.1 Baseline library (built in E04)

| Protocol | How it reaches a verdict |
|---|---|
| `single-<model>` | One model, one answer. The baseline every protocol must beat. |
| `self-consistency` | One model sampled N times; majority vote; confidence = agreement. |
| `panel-vote` | K models from different families answer independently; majority or weighted vote. |
| `debate-judge` | Advocates argue assigned sides for R rounds; a judge rules on the evidence. The Court pattern. |
| `evidence-first` | Retrieve evidence, have each model grade each source's stance, aggregate the stances. |
| `jev-aggregate` *(optional)* | Panel outputs become state for Jev, which returns a verdict with a calibrated probability. |

### 5.2 What the experimenter may vary

Models and roles, number of agents, rounds, sampling, prompts, evidence settings, aggregation rule, confidence calibration, and early stopping (stop debating once agents agree). Each change must state a hypothesis drawn from the learnings file or the steering file.

### 5.3 Seed protocols from the Research Library

The lab starts with the eight foundational agent-debate papers already in the Collective's Research Library (`Verafyai/Collective`, `research/library/pdfs/`, hash-verified). Before inventing anything, the lab reproduces what these papers propose, adapted to fact-checking, and tests whether their findings hold up. This first round is **Season 0**.

**Step 1: scan each paper into a protocol card.** For each PDF, the Claude agent writes `library/cards/<paper>.md` covering:
- the setup and the task the paper used
- the roles, rounds, and what the judge can and can't see
- how a verdict is reached, and the baseline the paper compared against
- the paper's headline finding, which becomes the claim to test
- any settings the paper reports, with page references

Each card ends with a **faithfulness note**: what had to change to apply the protocol to fact-checking. Cards are proposals; the orchestrator checks that every page reference exists in the PDF text.

**Step 2: turn each card into a protocol YAML,** tagged with its paper, plus the controls it needs.

| # | Paper | Seed protocol | Claim to test in fact-checking |
|---|---|---|---|
| 1 | Irving et al. 2018, *AI safety via debate* | `irving-debate`: two debaters take opposite sides; the judge sees only the debate. | A judge reaches the truth from adversarial argument alone. |
| 2 | Du et al. 2023, *Improving factuality and reasoning through multiagent debate* | `du-society`: several agents answer, read each other's answers and revise over rounds; majority verdict. | Revising after reading peers beats answering alone. |
| 3 | Liang et al. 2023, *Encouraging divergent thinking through multi-agent debate* | `liang-mad`: affirmative vs. negative debaters with a judge who can end the debate early. | Forced disagreement avoids getting stuck on a first answer. |
| 4 | Chan et al. 2023, *ChatEval* | `chateval-panel`: judges with distinct personas, in its three communication modes (one by one, simultaneous, simultaneous with a summarizer). | Diverse roles beat identical judges. |
| 5 | Michael et al. 2023, *Debate helps supervise unreliable experts* | `michael-asymmetric`: debaters see the evidence; the judge sees only quotes, each verified against its source. Control: consultancy, a single advocate. | Debate beats consultancy when the judge can't see the evidence. |
| 6 | Khan et al. 2024, *Debating with more persuasive LLMs leads to more truthful answers* | `khan-persuasive`: the same asymmetric setup, with the most persuasive of N debater drafts sent each turn. Control: consultancy. | Stronger debaters make judges more accurate, not less. |
| 7 | Kenton et al. 2024, *On scalable oversight with weak LLMs judging strong LLMs* | `kenton-weak-judge`: strong debaters and a cheap, weak judge, compared head to head with consultancy and with the weak judge answering directly. | Debate lets a cheap judge reach strong-model accuracy, and how much depends on the task. |
| 8 | Smit et al. 2024, *Should we be going MAD?* | `smit-controls`: self-consistency and a panel ensemble as required controls, plus an agreement-intensity setting added to `liang-mad` and `du-society`. | Debate doesn't beat cheap baselines unless agreement is tuned. |

The baseline library in §5.1 provides the remaining controls: the best single model, plus `evidence-first`.

**Step 3: run Season 0.** Every seed protocol and control runs on the same items with the same models, so the comparison is fair. The result is a replication scorecard (§8.2): for each paper, did its finding **replicate**, **not replicate**, or come out **unclear** (CI too wide) in fact-checking? That scorecard is the lab's first public output, and Grok's first lab update post.

**Season 0 budget plan (cost control):**
- **Screen cheaply first.** Run all configurations on 100 dev items. Only the top 4 plus the controls go on to the full holdout.
- **Use the same model tier for everyone,** so no protocol wins just by using a bigger model. Start with mid-tier models; upgrade only the finalists.
- **Estimate before running.** The orchestrator prints configurations × items × estimated cost per item, and stops if the total exceeds the Season 0 budget in `budget.yaml`.
- **Example to show the scale, not a quote:** 12 configurations × 100 screening items × about $0.05 per item is about $60. The holdout round for 6 configurations × 500 items is about $150 more. Caching makes later reruns free.

### 5.4 Transcript schema

Every run of a protocol on an item saves a transcript, the raw material for the visual:

```json
{
  "experiment": "E-0042", "protocol": "debate-2x2-judge-opus", "item": "q-000123",
  "evidence": [{"id": "ev1", "url": "...", "title": "...", "published": "...",
                "excerpt": "≤ 40 words", "stance": {"claude-sonnet": "refutes", "grok": "neutral"}}],
  "turns": [{"n": 1, "agent": "advocate-affirm", "model": "claude-sonnet",
             "text": "...", "cites": ["ev1"], "tokens": 812, "usd": 0.004}],
  "verdict": "refuted", "confidence": 0.82, "rationale": "≤ 60 words",
  "usd": 0.031, "latency_s": 14.2
}
```

---

## 6. Scores

Each score has a precise definition in `config/scoring.yaml` and an implementation in `lab/scoring/`. Nothing gets reported as a single blended number. The dashboard shows them side by side.

### 6.1 The six scores

**1. Accuracy (against the human expert panel), Track A**
- Primary: macro-F1 over the label set on the holdout. Also reports plain accuracy and per-label recall.
- Calibration: Brier score and expected calibration error (ECE). A protocol that says 90% should be right about 90% of the time.
- Reported for the full holdout and for the post-cutoff slice.

**2. Cost to iterate, Track A**
- USD per item and per full experiment (dev plus holdout), from metered token counts × `config/prices.yaml`.
- Also tokens and median latency per item.
- Efficiency: macro-F1 gain over the best single model, per dollar.

**3. Human readability and glanceability, Track B**
- *Readability* of the verdict rationale: grade level (target ≤ 9), length within limits, a jargon check, plus a rubric judgment from a cheap judge (Jev or a small model) on clarity, from 1 to 5.
- *Glanceability, the five-second test:* render the evidence card as an image and give a vision model only that image. Ask it for the verdict, the confidence, and the main reason. The score is the fraction it recovers correctly. If a model can't read it from the card alone, a scrolling human won't either.
- Human ratings (6.1.4) calibrate the automated measures. The dashboard shows how well each automated measure agrees with human ratings.

**4. Human dashboard rating, Track B**
- Thumbs up or down on each case's evidence replay, with an optional note, in the local dashboard.
- Score: Wilson lower bound of the thumbs-up share, so a 2-of-2 doesn't outrank a 40-of-50.

**5. X poll score, Track B (also a review signal)**
- Each social post carries a poll: *"Did the AI panel get this right?"* with the options **Yes, and convincing** / **Right, but weak evidence** / **Wrong verdict** / **Can't tell**.
- Presentation score: Wilson lower bound of "Yes, and convincing", with a minimum vote threshold before it counts.
- "Wrong verdict" above a threshold creates a review item for Rex. It never changes labels automatically.
- X poll votes are anonymous; the API returns totals, not voters. So the poll score is reported raw and unweighted, as a secondary signal. The **weighted rater score** in §6.4 is the primary human rating.

**6. Social score, Track B**
- Pulled at 24 and 72 hours: impressions, likes, reposts, replies, quotes and bookmarks.
- Engagement rate = interactions ÷ impressions.
- Social index = the post's engagement rate ÷ the account's trailing 30-day median, so a score of 1.0 is typical.

### 6.2 Promotion rule (Track A)

A protocol becomes the **champion** only when all four of these hold:
1. Holdout macro-F1 beats the current champion, with a paired bootstrap 95% CI on the difference that excludes zero (10,000 resamples).
2. The post-cutoff slice doesn't get worse beyond tolerance.
3. Calibration (ECE) doesn't get worse beyond tolerance.
4. Cost per item stays at or under `budget.yaml: max_usd_per_item_champion`.

Anything else is recorded as **not promoted**, with the reason. Results within noise are labeled "no detectable difference," never "worse" or "better."

### 6.3 Presentation selection (Track B)

A presentation variant becomes the default when it beats the current one on glanceability and human rating, without falling below the readability floor. Poll and social scores are tracked as supporting evidence, weighted cautiously, since X reach varies for reasons unrelated to quality.

### 6.4 Rater quality and weighting

Not every rating counts equally. Raters must clear a quality threshold, and each counted rating is weighted by the rater's derived standing.

**Who can be weighted:** only identified raters.
- **Structured replies on X:** replies to a case post that start with `RIGHT` or `WRONG`, optionally followed by a reason. The collector reads the author, so the rating can be weighted.
- **A hosted rating page** with Sign in with X (OAuth), linked from every post. Votes there carry the rater's identity.
- Anonymous X poll totals are kept as a separate, unweighted signal (§6.1.5).

**Eligibility threshold.** A rater counts only if all of these hold:
- the account is at least 90 days old
- it isn't labeled as automated
- it has posted at least 50 times
- it isn't on the lab's blocklist
- it has rated at least 3 calibration cases (below)

Everyone else's ratings are stored but carry zero weight.

**Weight = reliability × clout, capped.**
- **Reliability (the dominant factor):** how often the rater agrees with the experts on **calibration cases**. These are cases mixed into the rating flow where the human expert verdict is known but not shown. Reliability is a smoothed accuracy score (Beta(2,2) prior, so new raters start near the middle). It ranges from 0 to 1 and updates with every calibration case. Domain experts Rex verifies by hand get a reliability floor of 0.8.
- **Clout (a minor factor):** derived from the account's standing, on a log scale and clamped: `1 + 0.25 × log10(followers / 1000)`, limited to the range 0.75 to 1.5. Clout can never come from engagement with the lab's own posts.
- **Cap:** no single rater may hold more than 5% of the total weight on any case. Each rater is limited to 20 ratings per day.

Reliability dominates because follower count measures reach, not judgment. A 1,000-follower rater who keeps matching the experts should outweigh a 1M-follower account that doesn't.

**Weighted rater score:**
- score = Σ(weight × vote) ÷ Σ(weight), where vote is 1 for RIGHT and 0 for WRONG
- effective sample size = (Σ weight)² ÷ Σ(weight²)
- the Wilson lower bound is computed on the effective sample size, and the score counts only once the effective sample size reaches 15

**Anti-gaming:**
- Bursts of new raters on one case (many arriving within minutes) are quarantined for review.
- Weights are recalculated weekly. Raters never see their own weight.
- Calibration cases are rotated, so they can't be memorized and shared.

**Integrity still applies (§2):** weighted ratings are a Track B signal. A WRONG rating from a high-reliability rater raises a review item's priority for Rex, but labels still change only by Rex's hand.

---

## 7. The experiment loop

### 7.1 One cycle

1. **Read.** The Claude experimenter reads `STEERING.md`, `LEARNINGS.md`, the top of `learnings/learnings.jsonl`, the leaderboard, open review items, and today's remaining budget.
2. **Propose one experiment.** It writes `experiments/E-NNNN/proposal.md` (hypothesis, which learnings it builds on, expected effect, and which track) plus the protocol YAML or presentation change.
3. **Estimate.** The orchestrator dry-runs a cost estimate. If it exceeds the per-experiment or daily cap, the experiment is rejected, and the experimenter is asked to shrink it, for example with fewer items or a cheaper model.
4. **Dev run.** The orchestrator runs it on the dev split. Responses are cached by hash, so reruns cost nothing.
5. **Gate to holdout.** If dev macro-F1 is within striking distance of the champion (configurable margin), the orchestrator runs the holdout and the bootstrap. Otherwise it records "stopped at dev."
6. **Decide and record.** The orchestrator applies §6.2, writes `results.json` and `summary.md`, and updates the leaderboard.
7. **Learn.** The orchestrator appends a structured learning (§7.3). Rejected experiments always produce a learning.
8. **Show.** The orchestrator renders replays for a sample of items, choosing cases that are interesting: disagreements, upsets, high confidence.
9. **Share.** Daily, at most, it hands one case package to the Grok agent (§9).
10. **Listen.** At 24 and 72 hours, the collector pulls poll results, metrics and replies, scores them, and writes feedback and learnings.

### 7.2 Cadence

The loop is event-driven. A new cycle starts when the previous one finishes and budget remains; there's no idle polling. Social collection runs on its own schedule. `ops/STOP` halts everything after the current step.

### 7.3 The learning file

Two forms, both committed:

- **`learnings/learnings.jsonl`** (structured, for agents):
  ```json
  {"id": "L-0031", "date": "2026-10-04", "track": "A",
   "hypothesis": "A second debate round improves accuracy on conflicting claims",
   "experiments": ["E-0040", "E-0041"], "effect": "+0.011 macro-F1",
   "ci": [-0.004, 0.026], "status": "tentative",
   "lesson": "Round 2 helps only when advocates cite different sources; costs 1.7x",
   "next": "Try round 2 only when round-1 citations don't overlap"}
  ```
  `status` is one of `confirmed`, `refuted`, `tentative` or `superseded`.
- **`LEARNINGS.md`** (readable, for Rex and the public): a running narrative regenerated from the JSONL. Confirmed lessons go at the top; refuted ideas are listed so they aren't retried.

**Weekly consolidation:** a cheap step merges duplicate lessons, marks superseded ones, and keeps the active set under about 60 entries, so the experimenter's context stays small and cheap.

**The learning file is the measure of compounding.** The dashboard tracks the hit rate (the share of experiments that produced a promotion or a confirmed lesson) over time. If the learnings are working, the hit rate should rise.

### 7.4 Steering

`STEERING.md` is Rex's lever. It's read every cycle and overrides the experimenter's choices for focus, but it can't unlock budget or the entrenched rules in §11.

### 7.5 Review items

Created when the poll reports "Wrong verdict" above the threshold, when replies dispute a gold label with evidence, or when a champion protocol disagrees with gold at high confidence. Each review item goes to `ops/queue/` with the case, the evidence and the dispute. Rex decides whether to keep the label, fix it, or add the item to his own panel set. **Labels change only by Rex's hand.**

---

## 8. Visuals

### 8.1 Evidence replay (the core visual)

A web view that replays one protocol run on one item as an animated, step-by-step process:

1. **The question** appears.
2. **Evidence cards** arrive: source, date, a 40-word excerpt, and a stance chip per model (supports, refutes, neutral).
3. **The debate** plays turn by turn. Each turn shows the agent, the model family and the cited cards, and lines connect each turn to the cards it cites.
4. **The agreement meter** moves as the agents converge or split.
5. **The verdict** lands with a confidence bar, a 60-word rationale, and, for lab cases, the human experts' verdict revealed next to it.

Requirements:
- Works with `?autoplay=1` for video capture.
- Has a still **evidence card** mode (one image: verdict, confidence, top two reasons, sources count), which is what the glanceability test scores.
- Readable on a phone.
- Never shows more than 40 words from any one source.

### 8.2 Performance dashboard

One dashboard shows the performance of every protocol, paper and experiment. It runs as a local server and exports a read-only static copy for GitHub Pages. Every number links to the result file it came from.

**Headline.** One sentence: the champion, its accuracy against the best single model, and the total spent to get there.

**Replication scorecard (Season 0).** One row per paper:
- the paper's headline finding, as a claim
- the protocol that tests it, and its control
- the measured difference, with its 95% CI
- the verdict: replicated, not replicated, or unclear
- the cost of the test
- a link to the paper card and to example replays

**Protocol leaderboard.** Every protocol, seed and invented alike, in one table:
- holdout macro-F1 with its CI, post-cutoff macro-F1, and calibration (ECE)
- difference against the best single model
- cost per item, median latency, and rounds used
- the paper it came from, if any, and its status (champion, finalist, screened out)

Sortable by any column, with a filter for seed protocols vs. invented ones.

**Accuracy against cost.** A scatter plot of every protocol, with the Pareto frontier drawn and the champion marked. This is the single most useful view: it shows which protocols are worth their price.

**Per-label breakdown.** A heatmap of protocol × label recall (supported, refuted, not enough evidence, conflicting). Debate methods often help on some labels and hurt on others, and this view shows where.

**Where protocols disagree.** A matrix of how often each pair of protocols reaches different verdicts, with links to the cases where they split. Disagreements are where the interesting replays are.

**Trends.** All six scores over time, the experiment hit rate, and cumulative spend.

**Experiments.** Each proposal, its hypothesis, the learnings it cited, its result and its reason, with links to replays.

**Cases.** A replay browser, filterable by protocol, label, outcome (correct or wrong) and disagreement, with thumbs up or down (local only).

**Raters and social.** Each post with its poll totals, its weighted rater score and effective sample size, its social index, and its feedback themes. A rater view shows the distribution of reliability scores without identifying anyone publicly.

**Learnings.** Confirmed, tentative and refuted lessons.

**Budget.** Spend today, this week, this month and for Season 0, against the caps.

### 8.3 Video

`viz/render_video.py` records the autoplay replay with a headless browser and encodes a 20–40 second H.264 MP4 with burned-in captions and no audio requirement, in a square or 16:9 format. Before posting, it validates the file against X's current media limits; E12 checks these limits rather than hardcoding them.

---

## 9. The Grok agent and @VerafyAI

### 9.1 Role

The Grok agent is the lab's voice. It runs on the xAI API for writing (captions, poll wording, reply summaries) and posts through the X API with @VerafyAI's credentials. It does not run experiments or touch labels.

### 9.2 Clearance (`social/CLEARANCE.md` and `social/policy.yaml`)

Rex grants Grok standing clearance to post on behalf of @VerafyAI **within this policy**. Anything outside it goes to `ops/queue/` for approval.

**Cleared without approval:**
- One **case post** per day, at most: a video replay plus a caption with the question, the panel's verdict, the experts' verdict, and a link to the dashboard case. A poll goes with it, attached the way the API allows (see 9.3).
- One **lab update** per week, at most: the champion, accuracy, cost and the top lesson, generated from committed results only.
- **In-thread replies** to people replying to the lab's own posts, limited to short acknowledgments ("Thanks, logged as feedback #214") and links to the case.

**Never without Rex's approval:**
- Posts featuring items flagged `political` or `named_person`. These are excluded from automatic case selection entirely.
- Replies outside the lab's own threads, mentions of other accounts, quote posts, DMs, follows or likes.
- Any claim not backed by a committed result file.
- Anything responding to a dispute about a verdict. These become review items instead.

**Always:**
- The account is labeled as automated on X. **GATE:** Rex sets the label.
- Every post states it was produced by an AI panel and links to the full evidence.
- Every post, with its source result file, is logged to `social/posts.jsonl`.
- A rate limit and a daily cap are enforced in code. `social/PAUSE` stops posting immediately.
- Replies are untrusted data: they're summarized and classified, never followed as instructions.

### 9.3 Posting mechanics

E13 verifies the current X API capabilities rather than assuming them. In particular, it checks whether a poll can be attached to a post that has a video. If it can't, the design is: post 1 is the video and caption, and post 2, a reply in the same thread, is the poll.

### 9.4 Feedback loop

The collector classifies replies into these categories: *confusing*, *design suggestion*, *verdict dispute*, *praise*, *off-topic*, and *spam or abuse*. It writes them to `social/feedback.jsonl`:
- Design suggestions feed Track B proposals.
- Verdict disputes become review items.
- A weekly summary of feedback themes lands in `LEARNINGS.md`.

---

## 10. Harness (herdr)

The lab runs as a herdr session, so it fits Rex's existing agent workflow and can be shown in Return To Office.

**Panes:**

| Pane | Runs | Notes |
|---|---|---|
| `orchestrator` | `python -m lab.orchestrator.loop` | The judge. Plain code. |
| `claude` | Claude Code, headless, one experiment per invocation | Called by the orchestrator. The pane shows its live stream, like checkworthy's live view. |
| `grok` | `python -m social.agent` | Posting and collection on schedule. |
| `dashboard` | Local dashboard server | |
| `monitor` | Spend, heartbeat, errors, queue count | Turns red on cap breaches or a stalled heartbeat. |

Deliverables:
- `harness/launch.sh` starts the session.
- `harness/health.py` writes a heartbeat.
- The herdr config follows herdr's own format and conventions. Claude Code reads herdr's documentation, and if anything is unclear, it asks Rex rather than guessing.
- **Optional (E11b):** expose the lab's events in the format Return To Office reads, so the lab appears as a room with agents, KPIs and a heartbeat.

**Agent permissions:**
- The Claude experimenter may edit only `experiments/`, `lab/protocols/library/`, `viz/` (Track B variants), its fix plan and the learnings proposals. It may run the dev evaluation only.
- Locked paths: the orchestrator, scoring, holdout access, budget config, clearance policy, `STEERING.md` and `CHARTER.md`. Changes to these are reverted, as in checkworthy.

---

## 11. Budget and safety (entrenched)

- **Caps** in `config/budget.yaml`, set by Rex (**GATE**): per item, per experiment, per day, per month, and a separate social budget. The orchestrator enforces them before every model call. Breaching a cap halts the run and alerts.
- **Cost estimates before every run.** No experiment starts without a dry-run estimate under its cap.
- **Response caching.** Identical calls reuse cached responses. Reruns, re-renders and dashboard rebuilds cost nothing.
- **Cheapest tool that works.** Code for rules; Jev or a small model for rubric scoring and reply triage; frontier models only inside protocols where the experiment calls for them.
- **Prices** live in `config/prices.yaml`, maintained by Rex and never hardcoded. If a price is missing, the lab refuses to run.
- **Alerts** at 50% and 80% of the daily and monthly caps.
- **Kill switches:** `ops/STOP` halts everything, and `social/PAUSE` halts posting.
- **Secrets:** Anthropic, xAI, X and optional OpenRouter and Jev keys live in `.env`, which is gitignored. Agents never print, commit or post them.
- **Copyright:** evidence excerpts are capped at 40 words per source, and sources are always linked.

---

## 12. Build plan and ledger

### Phase 0: Foundations

**E00 · Scaffold**
- **Deliverables:** the repo, README, the layout from §3, config files with placeholders, STEERING.md, CHARTER.md (§2 integrity rule, §9.2 clearance and §11 entrenched), and CI running the tests.
- **Acceptance:** the CI is green, and the lab refuses to run while any budget or price is a placeholder.
- **GATE:** Rex fills in the budget and prices.

**E01 · Data**
- **Deliverables:** source evaluation (`data/SOURCES.md`), ingesters, the item schema validator, splits including the post-cutoff slice, holdout storage outside the repo, and the blocklist.
- **Acceptance:** the schema validates; the holdout is unreadable from the agent's permissions (test); the split sizes and the minimum detectable effect are reported.
- **GATE:** Rex approves the sources.

**E02 · Clients and metering**
- **Deliverables:** Anthropic, xAI, and optional OpenRouter and Jev clients, with retries, the response cache, a token and cost meter, and pre-call cap enforcement.
- **Acceptance:** tests show a cached call costs $0; an over-cap call is refused before sending; costs reconcile with each provider's reported usage on a smoke run.

**E03 · Evidence retrieval**
- **Deliverables:** a search and fetch tool with the blocklist, date filtering, the 40-word excerpt limit and a source record.
- **Acceptance:** tests show a blocklisted domain is never returned, evidence after the item's date is dropped when a date exists, and excerpts are capped.

**E04 · Protocol engine**
- **Deliverables:** the protocol YAML schema, the engine, the transcript writer and the baseline library from §5.1.
- **Acceptance:** each baseline runs end to end on 10 dev items within its budget; transcripts validate against the schema.

**E04b · Library scan and Season 0**
- **Deliverables:**
  - Paper cards for all eight Research Library papers, with page references and faithfulness notes (§5.3).
  - The eight seed protocol YAMLs plus the controls.
  - A quote verifier for the asymmetric protocols: a debater's quote counts only if it appears verbatim in the fetched source.
  - The Season 0 run plan with its cost estimate.
- **Acceptance:**
  - Every card's page references resolve in the PDF text (test).
  - Every seed protocol runs on 10 dev items within budget.
  - A fabricated quote is rejected by the verifier (test).
  - The Season 0 estimate is printed and stays under the Season 0 cap.
- **GATE:** Rex approves the Season 0 budget and the cards' faithfulness notes before the full run.

**E05 · Scoring**
- **Deliverables:** accuracy, macro-F1, calibration, cost, the paired bootstrap, the leaderboard and the minimum-detectable-effect report.
- **Acceptance:** each metric has unit tests against hand-computed fixtures; the bootstrap is deterministic given a seed.

**E06 · Orchestrator**
- **Deliverables:** the cycle in §7.1, holdout isolation, the promotion rule, writing results and learnings, STOP handling, locked-path reverts and the heartbeat.
- **Acceptance:** an end-to-end test with a stub experimenter shows a better protocol is promoted, a noise-level one is "no detectable difference," and an over-budget one is refused.

**E07 · Experimenter**
- **Deliverables:** the Claude experimenter's prompt (one experiment per invocation, hypotheses must cite learnings or steering), learning file tooling, weekly consolidation and the hit-rate metric.
- **Acceptance:** 5 live cycles run unattended within budget; every experiment has a proposal, a result and a learning.

### Phase 1: Visuals

**E08 · Evidence replay**
- **Deliverables:** the replay view (§8.1), still card mode, autoplay and phone layout.
- **Acceptance:** replays render from real transcripts; the still card shows the verdict, confidence and top reasons; no excerpt exceeds 40 words.

**E09 · Performance dashboard**
- **Deliverables:** every view in §8.2, including the replication scorecard, local thumbs ratings stored in `ratings.jsonl` and committed, and the static export.
- **Acceptance:** all views render from real data; a thumbs click persists; the static export works with ratings hidden.

**E10 · Readability and glanceability**
- **Deliverables:** the scorers in §6.1.3, and a report of agreement with human ratings.
- **Acceptance:** the five-second test runs on the still cards; scores are written per case and per presentation variant.

### Phase 2: Harness

**E11 · herdr harness**
- **Deliverables:** the panes in §10, the launch script and the health monitor.
- **Acceptance:** `harness/launch.sh` brings up all panes; killing the orchestrator turns the monitor red within one heartbeat interval.
- **E11b (optional):** Return To Office event export.

### Phase 3: Social

**E12 · Video**
- **Deliverables:** the renderer in §8.3, and checks against X's current media limits.
- **Acceptance:** produces a valid MP4 from a replay in under 2 minutes; the captions are legible on a phone.

**E13 · Grok agent**
- **Deliverables:** the clearance policy in code, case selection excluding flagged items, the post and poll flow (§9.3), the posts log, the rate limits, PAUSE and the weekly lab update.
- **Acceptance:** tests show flagged items are never auto-selected, a post without a backing result file is refused, and PAUSE blocks posting. A live smoke test makes one case post with a poll.
- **GATE:** Rex provides the X and xAI credentials and sets the automated label.

**E14 · Collector**
- **Deliverables:** poll results, metrics at 24 and 72 hours, reply classification, `feedback.jsonl`, review items and the poll and social scores.
- **Acceptance:** scores computed for the smoke-test post; injection text in a reply is stored as data and never acted on (test).

**E15 · Track B experiments**
- **Deliverables:** the experimenter can propose presentation variants, scored per §6.3.
- **Acceptance:** one presentation experiment completes with all four Track B scores recorded.

**E17 · Rater registry and weighted ratings**
- **Deliverables:** the structured reply parser; a hosted rating page with Sign in with X; the rater registry (eligibility, reliability, clout, weight history); calibration case injection; the weighted rater score and anti-gaming checks (§6.4).
- **Acceptance:**
  - Tests cover the following: an ineligible rater carries zero weight; one rater can't exceed 5% of a case's weight; reliability rises and falls on calibration fixtures; a burst of new raters is quarantined; the weighted score matches a hand-computed fixture.
  - Raters can't see their own weight.
- **GATE:** Rex approves the eligibility thresholds and the hosting for the rating page.

### Phase 4: Reporting

**E16 · Reports**
- **Deliverables:** a daily digest in `ops/reports/` (champion, experiments run, spend, lessons, review items) and the data for the weekly lab update post.
- **Acceptance:** 3 consecutive daily digests are generated with no missing fields.

### Ledger

| ID | Chunk | Depends on | Status | Done (date · commit) |
|---|---|---|---|---|
| E00 | Scaffold | none | TODO | |
| E01 | Data | E00 | TODO | |
| E02 | Clients and metering | E00 | TODO | |
| E03 | Evidence retrieval | E02 | TODO | |
| E04 | Protocol engine | E02, E03 | TODO | |
| E04b | Library scan and Season 0 | E04 | TODO | |
| E05 | Scoring | E01 | TODO | |
| E06 | Orchestrator | E04, E05 | TODO | |
| E07 | Experimenter | E06 | TODO | |
| E08 | Evidence replay | E04 | TODO | |
| E09 | Performance dashboard | E04b, E05, E08 | TODO | |
| E10 | Readability and glanceability | E08 | TODO | |
| E11 | herdr harness | E06 | TODO | |
| E12 | Video | E08 | TODO | |
| E13 | Grok agent | E12, E06 | TODO | |
| E14 | Collector | E13 | TODO | |
| E15 | Track B experiments | E10, E14 | TODO | |
| E16 | Reports | E07, E14 | TODO | |
| E17 | Rater registry and weighted ratings | E09, E14 | TODO | |

---

## 13. Definition of done

The lab is done when it has run unattended for 14 days, within budget, and:
- the Season 0 replication scorecard is complete and published;
- the champion protocol beats the best single model on the holdout with a CI excluding zero, or the lab has honestly documented that nothing yet does;
- every experiment has a proposal, a result and a learning, and the hit rate is plotted;
- the dashboard shows all six scores over time, with human ratings weighted by rater reliability;
- @VerafyAI has posted case videos with polls, and their scores and feedback are in the learning file;
- no post has violated the clearance policy, and no label changed without Rex.

---

## 14. Decisions Rex needs to make before the build starts

1. **Budget:** per day and per month, plus the social budget.
2. **Datasets:** approve the source list from E01.
3. **Models in the panel:** which Claude and Grok models, and whether to include others through OpenRouter or Jev.
4. **Posting cadence:** case posts per week (the default is at most 1 per day).
5. **Expert panel:** whether to build your own small gold set from the start, or rely on published sets first.
6. **Season 0 budget:** the cap for screening and holdout runs, and which models are the shared tier.
7. **Rater rules:** the eligibility thresholds and the clout formula in §6.4, and where the rating page is hosted.
