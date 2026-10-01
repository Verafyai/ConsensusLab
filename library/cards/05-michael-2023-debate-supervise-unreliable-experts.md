---
paper: 05-michael-2023-debate-supervise-unreliable-experts
title: Debate Helps Supervise Unreliable Experts
authors: Michael, Mahdi, Rein, Petty, Dirani, Padmakumar, Bowman
year: 2023
arxiv: 2311.08702v1
protocol: michael-asymmetric
zone: Z5
controls: [michael-consultancy]
claim: "Debate beats consultancy when the judge can't see the evidence."
---

## Setup and task
The paper asks whether two adversarial experts help a non-expert judge find the truth better
than one unreliable expert does. The task is hard reading comprehension, and
the judge never sees the source text: the judge sees only arguments and [p.1: "short quotes
selectively revealed by ‘expert’ debaters who have access to the passage"]. Questions come
from QuALITY-hard over Project Gutenberg science fiction, so the judge cannot fall back on
prior knowledge. Each four-option question is reduced to two answers:
[p.6: "we use the correct answer and the incorrect option that was labeled as the best distractor"].
The paper's design point is the information asymmetry: it lets the debaters, but not the judge, read the passage
[p.3: "allow the debaters—but not the judge—to read the story the question is about"].
Most experiments use human debaters drawn from the NYU debate team. There is also an AI condition in which GPT-4 debates, and
[p.6: "We use human judges in all experiments."]

## Roles, rounds and what the judge sees
- **Debate.** Two debaters are assigned opposite answers, and one of the two is correct. [p.4: "Then, both debaters
  write opening statements simultaneously (without seeing the other debater’s statement)."]
  After the openings, the judge, debater A and debater B take turns in sequence until the judge ends the debate.
- **Quotes.** Each speech is capped at 750 characters, and up to 250 of those characters can be quotes [p.6: "meaning that on average up
  to 1.8% of the story could be revealed in each round"]. Quotes are checked by the system:
  [p.4: "Certified quotes are highlighted in yellow so the judge knows they are verbatim"].
- **Judge.** The judge sees the question, the transcript and the certified quotes, but not the passage. The judge is
  interactive: after each round the judge writes feedback, reports a credence, and [p.4: "the judge has the
  option of continuing the debate for another round or ending it"]. Every extra round costs the judge
  a small score penalty, so the judge chooses how long to keep going.
- **Consultancy (baseline).** A single consultant argues one answer.
  [p.5: "The consultant is assigned to argue for one of these answers, with a 50% chance of each."]
  To keep the amount of text per round equal across the two protocols,
  [p.5: "Argument and quote length limits are doubled for the consultant"].
- **Length.** [p.8: "Human debates finish in 2.7 rounds on average, whereas consultancies finish in 4 rounds on average."]

## How a verdict is reached
The judge's final credence decides the outcome. The judge is scored with a log scoring rule minus a penalty for each extra
round. Accuracy is the share of sessions where the judge's final answer is correct. The control is
consultancy with the same judge view, where the prior is 50/50 because the consultant is honest half
the time. There are four conditions in total: human debate, human consultancy, AI debate and AI consultancy
[p.7: "We collect 413 debates and consultancies across our four experimental conditions."].

## Headline finding
With human debaters, debate beats consultancy:
[p.1: "debate performs significantly better, with 84% judge accuracy compared to consultancy’s 74%"]
(p = 0.04). Much of the consultancy gap comes from deception that goes uncaught:
[p.8: "dishonest human consultants successfully deceive judges 40% of the time"], and
[p.9: "In consultancies, 52% of mistakes involve judges not getting key evidence from a dishonest consultant."]
The result does not replicate with GPT-4 as the debater:
[p.8: "In the AI case, judge accuracies on debate (78%) and consultancy (80%) are similar"], and
[p.3: "In this setting, we find no difference between debate and consultancy."] The paper reads
this as a skill effect:
[p.1: "with more skilled (in this case, human) debaters, the performance of debate goes up but the performance of consultancy goes down"].
**Claim we test:** debate beats consultancy when the judge cannot see the evidence. Our setup is
an AI-debater setup. The paper's own AI result was a null, so a null from us would replicate the
paper's AI condition. It would not contradict the paper.

## Reported settings
- **Debaters.** In the human conditions, the debaters were NYU debate-team members and researchers. In the AI condition, [p.6: "we use the version of GPT-4 with a
  32,000-token context window"].
- **Judges.** All judges were human.
- **Limits.** 750 characters per turn, of which up to 250 can be quotes. Consultants get double both limits.
- **Rounds.** The judge decides when to stop, with a 0.05 penalty for each continuation. Human debates averaged 2.7 rounds and consultancies about 4.
- **Errors in debates.** Judges often stopped too early. The authors' proposed fix is a minimum round count: [p.10: "Both of these errors could be easily remedied by requiring judges to wait at least one extra round"].
- **Limitation.** The authors note that their judges start without opinions on the question: [p.11: "we do not test the robustness of debate in the presence of
  strong preexisting views"].

## Faithfulness note
- **Task and labels.** Our task is fact-checking a real claim with four labels (supported, refuted,
  not_enough_evidence, conflicting). The paper used a two-option question where exactly one option is correct.
  - The affirm advocate argues "the claim is TRUE" (supported) and the deny advocate argues "the claim is FALSE"
    (refuted). The judge still rules over all four labels.
  - For not_enough_evidence and conflicting items, no advocate holds the correct answer. Both sides
    are then "dishonest" in the paper's sense. The judge has to infer those labels from a stalemate or from
    verified quotes pulling in both directions. This tests a condition the paper never ran.
  - Accuracy should be reported separately for the supported/refuted subset (closest to the paper) and the other two labels.
- **Information asymmetry.** It is weaker in our setup.
  - The paper's stories are about 27.7k characters of fiction that the judge cannot know.
  - Our evidence is at most 6 short pre-claim-date web excerpts about real-world events. The judge model
    may already know the answer from pretraining, which is the contamination worry the paper raises in footnote 6.
  - Debaters can reveal a large share of a short excerpt in a single round, which shrinks the gap that debate is supposed to bridge.
  - The single-claude-sonnet-closed baseline can be used to measure what the judge knows with no evidence at all.
- **Judge.**
  - We use a model judge (claude-sonnet), not a human one.
  - The judge is not interactive: it does not ask questions or set burdens. It rules once, or ends early through `early_stop.judge_can_end`.
  - The paper's judge reported credences under a proper scoring rule. Our judge reports a confidence with no
    penalty per round. The paper's 2.7 average rounds come from that penalty; we approximate it with
    rounds: 3 plus judge early stop, with min_rounds 2 to follow the paper's own fix for judges who stop too early.
- **Quotes.**
  - The paper capped quotes at 250 characters per turn. Our `quotes.max_words: 40` is a cap per quote, not per turn.
  - A quote is VERIFIED only if it appears verbatim in the fetched page text (or the excerpt), so a page that fails to fetch makes honest quotes UNVERIFIED.
- **Turn order.** In the paper, openings are simultaneous and later rounds are sequential. In our engine, deny reads affirm's speech within
  each round, in every round.
- **Models.**
  - Affirm is claude-sonnet and deny is grok-fast, so model family is confounded with side.
  - The paper's debaters were equally skilled, often the same people.
  - Consider a second run with the sides swapped, or self-play on a single model.
- **Consultancy.** The consultant is claude-sonnet, assigned affirm or deny by a seeded coin flip, which matches the paper. The
  judge does not question the consultant, and the paper found that questioning was how judges caught dishonest consultants.
  The consultant also gets the same rounds and quote cap as the debaters, not double. Its total speaking volume is therefore half
  of a debate's, not equal to it.

## Proposed protocol
```yaml
id: michael-asymmetric
description: >-
  Michael et al. 2023. Information-asymmetric debate. Advocates read the retrieved evidence;
  the judge sees only the debate plus cited quotes, each checked verbatim against its source
  and marked VERIFIED or UNVERIFIED. The judge may end the debate after round 2.
pattern: debate
paper: 05-michael-2023-debate-supervise-unreliable-experts
controls: [michael-consultancy]
tags: [season0, z5]
evidence: {retrieve: true, max_sources: 6, per_agent: shared, judge_sees: quotes}
quotes: {verify: true, max_words: 40}
agents:
  - {role: advocate, side: affirm, model: claude-sonnet}
  - {role: advocate, side: deny, model: grok-fast}
  - {role: judge, model: claude-sonnet}
rounds: 3
early_stop: {judge_can_end: true, min_rounds: 2}
aggregation: judge
budget: {max_usd_per_item: 0.20}
```

```yaml
id: michael-consultancy
description: >-
  Michael et al. 2023 control. One consultant reads the evidence and argues a randomly
  assigned side (affirm or deny); the judge sees only the consultant's arguments plus
  verified/unverified quotes, never the evidence itself.
pattern: consultancy
paper: 05-michael-2023-debate-supervise-unreliable-experts
controls: [michael-asymmetric]
tags: [season0, z5]
evidence: {retrieve: true, max_sources: 6, per_agent: shared, judge_sees: quotes}
quotes: {verify: true, max_words: 40}
agents:
  - {role: consultant, model: claude-sonnet}
  - {role: judge, model: claude-sonnet}
rounds: 3
aggregation: judge
budget: {max_usd_per_item: 0.15}
```
