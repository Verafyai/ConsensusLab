---
paper: 06-khan-2024-persuasive-debaters-truthful
title: Debating with More Persuasive LLMs Leads to More Truthful Answers
authors: Khan, Hughes, Valentine, Ruis, Sachan, Radhakrishnan, Grefenstette, Bowman, Rocktäschel, Perez
year: 2024
arxiv: 2402.06782v4
protocol: khan-persuasive
zone: Z5
controls: [khan-consultancy, khan-persuasive-n1]
claim: "Stronger debaters make judges more accurate, not less."
---

## Setup and task
This paper is the LLM follow-up to Michael et al. (2023). It keeps the same information-asymmetric QuALITY setup. Debaters
read a Project Gutenberg science fiction story. Judges do not:
[p.3: "Judges are not allowed access to the original comprehension text, restricting their ability to answer questions"].
Each question is reduced to [p.3: "the correct answer and the best distractor"], drawn from a stricter
HARD subset. Five LLMs act as debaters and consultants. LLM judges were GPT-4-Turbo, Claude 2.1, GPT-3.5-Turbo and
Mixtral. The paper also ran a large human-judge study. Quoting is checked by a tool:
[p.3: "if the quote directly matches a portion of the text, the tool generates verified"] tags,
and otherwise the tags are unverified.
[p.3: "The judge is instructed to trust only verified quotes"]. The check
is simple: [p.35: "Normalisation involves stripping punctuation and making the text lowercase."]

## Roles, rounds and what the judge sees
**Debate**
- Two experts argue opposing answers for a fixed number of rounds.
  [p.3: "In each round, debaters see the arguments from previous rounds and simultaneously generate their arguments for the next round."]
- The judge reads the finished transcript, including verified and unverified quote tags, and picks an answer. It never sees the story.
- There is also an interactive variant, where the judge comments between rounds.

**Consultancy**
- One expert argues one assigned answer while the judge asks questions.
  [p.3: "In all our evaluations, we run consultancy for both the correct and incorrect answers"].

**Length**
- [p.3: "We run protocols for three rounds."] The transcript is capped at 900 words in total,
  [p.3: "limiting consultants to 300 words per argument and debaters to 150 words"].

**What "stronger" means**
- Debater strength comes from inference-time optimisation:
  [p.4: "a preference model is used to select the most persuasive arguments"].
- The preference model scores each draft the way the judge would:
  [p.36: "the preference model (which does not have access to the the story like the judge)"].

## How a verdict is reached
A non-expert judge picks one of the two answers at the end.
- **Position bias.** To control for it, [p.4: "we run judgements over each debate twice - once with the original transcript and once with the debater order swapped"].
- **Persuasiveness.** Measured without labels, as win rate and Elo from a cross-play tournament.
- **Truthfulness.** Measured as judge accuracy in self-play, with copies of the same debater on both sides.
- **Baselines.** A naive judge (question only) and an expert judge (sees the story) bound performance.

## Headline finding
Debate helps non-expert judges:
[p.1: "debate consistently helps both non-expert models and humans answer questions, achieving 76% and 88% accuracy respectively"]
The naive baselines score 48% and 60%.
[p.2: "Debate also outperforms the single-model baseline consultancy, with which human and LLM judges achieve 78% and 54%, respectively."]

The result we test is about debater strength, and it goes in opposite directions for the two protocols:
- **Debate:** [p.6: "As debaters are optimised against the unsupervised metric of win rate (judge preference), judge accuracy improves"]
- **Consultancy:** [p.2: "By contrast, judge accuracy decreases as consultants are more persuasive."]
- **Why, according to the paper:** stronger debaters gain more when arguing the true side. For QuALITY,
  [p.5: "telling the truth is easier than lying"].

**Claim we test:** stronger debaters make judges more accurate, not less. In consultancy, the same
optimisation should lower accuracy.

## Reported settings
- **Main runs.** [p.5: "using GPT-4-Turbo and best-of-16 sampling for both debaters and consultants"].
- **Strength levels in the tournament.** Twenty debaters, built from four LLMs crossed with best-of-N variants (bo1 to bo32) and critique-and-refinement variants (c2 to c16).
- **Preference model.** Best-of-N drafts were scored with GPT-4-Turbo log-probabilities.
  [p.36: "We found that using the same preference model as the judge model led to the largest gains in aggregate Elo and judge accuracy"].
- **Rounds and length.** 3 rounds, 150 words per debater argument (100-word target) and 300 per consultant.
  Temperature rises with N (0.4 at bo1, 0.8 up to bo16).
- **Judge strength.** The authors advise to [p.34: "use at least GPT-4-Turbo capability for a judging model"].
  [p.5: "Debate outperforms consultancy and, with stronger judges, reduces the gap with the expert judge (75.6% vs 92.5%)"].
- **Interaction.** [p.7: "We find identical judge accuracy between static and interactive debate."]
- **Human judges.** [p.7: "debate outperforms consultancy significantly"] in both the static and interactive settings.

## Faithfulness note
**How "stronger" is operationalized here**
- The main lever is `best_of_n` (4 in khan-persuasive versus 1 in khan-persuasive-n1). The rest of the protocol is identical between the two, so the claim
  becomes a within-protocol comparison: accuracy(N=4) ≥ accuracy(N=1).
- The paper went up to bo16/bo32. Our schema caps N at 8, and N=4 keeps cost manageable, so the strength gap
  we create is much narrower than the paper's.
- A second axis would be model tier (claude-haiku vs claude-sonnet debaters). Season 0 holds the tier fixed, so we leave that
  for later.
- The paper's evidence was a correlation across 20 debaters on an Elo scale. We will have two or three points, with
  no Elo tournament.
- The paper also expects consultancy accuracy to fall as N rises. khan-consultancy uses N=4 and should be
  compared with michael-consultancy, which is the N=1 case.

**Best-of-N mechanics**
- Our selector is the judge model (claude-sonnet). This follows the paper's finding that using the judge as the preference model works best.
- Our selector picks a draft by listwise choice. The paper scored each draft by the log-probability that the judge picks it, using a dummy
  opponent reply.
- Our engine verifies quotes only after selection, so the selector sees raw drafts without VERIFIED or UNVERIFIED tags. In the paper, the
  preference model saw the tags.
- The paper raised temperature with N. Our engine uses the default sampling settings.
- There is no critique-and-refinement.

**Task and labels**
- The task is fact-checking with 4 labels, not a two-option question.
  - Affirm argues "the claim is TRUE" (supported) and deny argues FALSE (refuted). The judge still rules over all four labels.
  - On not_enough_evidence and conflicting items, neither side is correct.
- The paper's mechanism is that truth is easier to argue. It may not hold when the honest answer is "unclear".
  Making both sides more persuasive could then push the judge toward a false supported or refuted verdict.
- Report the supported/refuted subset separately.

**Evidence asymmetry**
- The asymmetry is weaker. Short, real-world web excerpts replace a 7k-token fictional story.
- The judge (claude-sonnet) may know the facts already.
- The advocates are the same tier as the judge, not stronger.

**Turn order, roles and judge**
- **Turn order.** The paper's debate is simultaneous. In our engine, deny reads affirm's turn within each round.
- **Model–side confound.** Affirm is always claude-sonnet and deny is always grok-fast, while the paper used self-play.
  Consider swapping sides, or self-play.
- **Judge.** Our judge rules once over the transcript, which matches the paper's static judge. It does not run twice with the order swapped.
  Our consultancy is not interactive.
- **Word limits.** The engine does not enforce the 150-word limit. The paper enforced it with rejection sampling because LLM judges favour longer arguments.
  Add the limit to the prompts if verbosity confounds best-of-N.

## Proposed protocol
```yaml
id: khan-persuasive
description: >-
  Khan et al. 2024. Information-asymmetric debate with optimised debaters. Each turn the
  advocate drafts 4 arguments and the judge model picks the most persuasive; the judge sees
  only the debate plus verified/unverified quotes. Three fixed rounds.
pattern: debate
paper: 06-khan-2024-persuasive-debaters-truthful
controls: [khan-consultancy, khan-persuasive-n1]
tags: [season0, z5]
evidence: {retrieve: true, max_sources: 6, per_agent: shared, judge_sees: quotes}
quotes: {verify: true, max_words: 30}
best_of_n: 4
agents:
  - {role: advocate, side: affirm, model: claude-sonnet}
  - {role: advocate, side: deny, model: grok-fast}
  - {role: judge, model: claude-sonnet}
rounds: 3
aggregation: judge
budget: {max_usd_per_item: 0.60}
```

```yaml
id: khan-persuasive-n1
description: >-
  Khan et al. 2024 weak-debater variant. Identical to khan-persuasive but best_of_n 1, so
  the strength comparison (N=4 vs N=1) is within one protocol.
pattern: debate
paper: 06-khan-2024-persuasive-debaters-truthful
controls: [khan-persuasive, khan-consultancy]
tags: [season0, z5]
evidence: {retrieve: true, max_sources: 6, per_agent: shared, judge_sees: quotes}
quotes: {verify: true, max_words: 30}
best_of_n: 1
agents:
  - {role: advocate, side: affirm, model: claude-sonnet}
  - {role: advocate, side: deny, model: grok-fast}
  - {role: judge, model: claude-sonnet}
rounds: 3
aggregation: judge
budget: {max_usd_per_item: 0.20}
```

```yaml
id: khan-consultancy
description: >-
  Khan et al. 2024 control. One consultant argues a randomly assigned side with best-of-4
  drafts chosen by the judge model; the judge sees only the consultant's arguments plus
  verified/unverified quotes. Paper predicts accuracy falls as N rises.
pattern: consultancy
paper: 06-khan-2024-persuasive-debaters-truthful
controls: [khan-persuasive, michael-consultancy]
tags: [season0, z5]
evidence: {retrieve: true, max_sources: 6, per_agent: shared, judge_sees: quotes}
quotes: {verify: true, max_words: 30}
best_of_n: 4
agents:
  - {role: consultant, model: claude-sonnet}
  - {role: judge, model: claude-sonnet}
rounds: 3
aggregation: judge
budget: {max_usd_per_item: 0.40}
```
