---
paper: 07-kenton-2024-weak-judges-strong-llms
title: On scalable oversight with weak LLMs judging strong LLMs
authors: Kenton, Siegel, Kramár, Brown-Cohen, Albanie, Bulian, Agarwal, Lindner, Tang, Goodman, Shah
year: 2024
arxiv: 2407.04622v2
protocol: kenton-weak-judge
zone: Z5
controls: [kenton-consultancy, kenton-direct-weak, single-claude-haiku, single-claude-sonnet]
claim: "Debate lets a cheap judge reach strong-model accuracy, and how much depends on the task."
---

## Setup and task
Kenton et al. (Google DeepMind) test whether a weaker LLM judge can supervise stronger LLMs
through debate or consultancy, compared with the judge simply answering. All tasks are
binary-choice versions of QA datasets: where a dataset is multiple choice they form a binary
version from the correct answer and a random answer [p.6: "we form a binary choice version by selecting the correct answer and a random answer"].
The scale is large: [p.3: "We perform a large-scale evaluation sweeping over 9 tasks, each sampling 128 questions"].
Tasks fall into three types. In the **extractive** tasks (QuALITY, BoolQ, GPQA-extractive)
[p.6: "a binary-choice question, along with an article, are supplied to consultants/debaters but not to the judge, introducing an information asymmetry"].
In the **closed** tasks (MMLU, GSM8KQA, PrOntoQA, TruthfulQA, GPQA) there is no article, so the
gap is only one of capability; the third type is multimodal (MMMU). Only the extractive type has
the information asymmetry that our setting resembles: debaters hold retrieved evidence, the judge
does not.

## Roles, rounds and what the judge sees
- **Debate:** two debaters argue opposite assigned answers, and the debate runs
  [p.7: "(as a default we use 3 rounds)"]. The main runs used
  [p.8: "simultaneous turns with debaters selecting their responses through Best-of-4"], with the
  debater model (not the judge) picking the most persuasive of the four drafts (p.9, footnote 1).
- **Consultancy:** one consultant argues an assigned answer; the judge may ask probing questions.
  The paper runs both sides for every item: [p.7: "for each question we run two consultancy evaluations: one where the consultant is assigned the correct answer"] and one where it is assigned the incorrect one.
- **Direct QA baselines:** "QA without article" [p.7: "As a baseline, we zero-shot prompt the judge with a question and two answer options."]
  and, on extractive tasks only, "QA with article", where the judge reads the full source.
- **What the judge sees:** debaters reason privately, then
  [p.7: "Only their argument is shown to the judge (the thinking is private)."]
  On extractive tasks the judge never sees the article; quoted passages are checked:
  [p.6: "The debaters and judges have access to a tool which verifies whether the passage is indeed contained in the article"],
  and are tagged verified or unverified in the transcript (Appendix G, p.22).
- **Models:** [p.3: "Our main experiments use Gemini Pro 1.5 as debaters/consultants."] Judges
  were Gemma7B, GPT-3.5, Gemini Pro 1.0 and Pro 1.5, i.e. equal to or weaker than the debaters.

## How a verdict is reached
The judge reads the transcript and picks one of the two answers; judges are zero-shot and do not
use chain of thought by default (p.9). Accuracy is measured against the dataset labels, and protocols
are compared with permutation-test p-values per task type and judge (p.9). The baselines are QA
without article (the judge alone, from its own knowledge) and QA with article (the judge with the
full source). Consultancy is the main protocol control, though the authors note it is an easy one:
[p.4: "it's likely that consultancy is a weak baseline to beat because of the 50/50 chance"].

## Headline finding
[p.1: "We find that debate outperforms consultancy across all tasks when the consultant is randomly assigned"]
to the correct or incorrect answer. Against direct answering, the result depends on the task:
[p.1: "in extractive QA tasks with information asymmetry debate outperforms direct question answering, but in other tasks without information asymmetry the results are mixed"].
On extractive tasks [p.9: "judges attain higher accuracy for debate compared to consultancy and QA without article"],
except for the weakest judge, Gemma7B. But debate never reached the judge reading the source itself:
[p.9: "QA with article is best for all models, indicating that information is best used directly"].
On closed tasks the most informative judges (GPT-3.5, Pro 1.0)
[p.9: "indicate either small or no benefit of debate over QA without article"].
In open-role runs the strong model picked the correct side
[p.11: "The consultant/protagonist chooses the correct answer in 88%, 84%, 71% of questions"]
(extractive, closed, multimodal), and stronger debaters raised judge accuracy only modestly (p.12).
The paper reports these results as figures with confidence intervals; its text gives no single
accuracy number for the headline.

**Claim we test:** a cheap judge (claude-haiku) that cannot see the evidence, reading a debate
between mid-tier models, beats both consultancy and itself answering directly, and closes part of
the gap to claude-sonnet answering with the evidence. Per the paper, expect it *not* to beat
claude-haiku reading the evidence directly (our analogue of QA with article).

## Reported settings
- Debaters/consultants: Gemini Pro 1.5; judges: Gemma7B, GPT-3.5, Pro 1.0, Pro 1.5, all used
  1-shot with default sampling (p.8).
- 9 tasks × 128 questions; binary choice; 3 rounds; simultaneous turns; Best-of-4 for debaters.
- Word limit: [p.22: "consultants and debaters are prompted to follow a word limit of 150 words per turn"].
- Ablations that made little difference: turns (3 vs 1)
  [p.9: "We find no significant effect from the number of turns."]; best-of-N, where 4 vs 1
  showed no substantial drop [p.10: "suggesting our implementation of best-of-N is not helpful"];
  few-shot judging; turn style (simultaneous vs sequential); swapping answer order. Judge chain of
  thought hurt: [p.10: "Surprisingly, we see CoT tends to harm performance or be insignificant"].
- Caveat on the extractive gains: citing Khan et al., the authors note
  [p.21: "the quote verification, rather than the argumentation, is the dominant contribution to judge accuracy"].

## Faithfulness note
- **Task and labels.** The paper uses binary-choice QA with one correct option. We check real claims
  with four labels (supported, refuted, not_enough_evidence, conflicting). Our debate has one
  advocate for TRUE (supported) and one for FALSE (refuted). No one argues for not_enough_evidence or
  conflicting, so the judge has to infer those labels without an advocate. Expect debate to lose
  ground on those two labels compared with the paper's binary setting.
- **The asymmetry.** Our analogue of an extractive task is: advocates see the retrieved evidence
  (≤6 sources), and the judge does not. We use `judge_sees: quotes`, which shows the judge only
  the debate plus quotes marked VERIFIED or UNVERIFIED. This matches Kenton's passage-verification
  tool (p.6, p.22). `none` would be stricter than the paper. The paper itself suggests the verified
  quotes, more than the argument, may drive the gain (p.21). A follow-up arm with `judge_sees: none`
  would separate those two effects.
- **Strength gap.** Kenton's gap was Gemini Pro 1.5 versus much weaker judges. Ours is
  claude-sonnet / grok-fast versus claude-haiku, a smaller gap and across vendors for one
  debater. If claude-haiku already knows many of the claims, kenton-direct-weak will be strong
  (as happened with BoolQ; see p.21). The claims' dates relative to the models' training cutoffs
  will matter.
- **Side–model confound.** claude-sonnet always argues affirm and grok-fast always argues deny.
  The paper used the same model on both sides. Any accuracy difference may partly reflect which
  model argues which side. A swapped-sides arm would fix this, but it doubles the cost.
- **Consultancy.** Kenton runs both sides for every item and lets the judge question the
  consultant. Our engine assigns one side at random per item, which matches in expectation but
  adds variance, and our judge asks no questions. Kenton dropped interactive judging in debate
  (p.8), but consultancy was interactive.
- **Best-of-N.** The paper used Best-of-4, with the debater model choosing the draft. Our engine
  has the judge (claude-haiku) choose, which is a different mechanism. The paper found best-of-N
  barely helped (p.10), so we set `best_of_n: 1`. That saves about 4× on advocate calls.
- **Turn order.** Our debate turns are sequential: the deny advocate sees the affirm turn from the
  same round. Kenton found turn style made no significant difference (p.10).
- **Rounds.** We keep 3 rounds to stay faithful. The paper found 1 round just as good (p.9), so
  `rounds: 1` is the obvious cheap variant if cost is tight.
- **Evidence gaps.** Appendix C finds that some judge errors come from having no evidence at all:
  [p.19: "one is impossible for the judge to adjudicate without access to verified external information"].
  The quotes channel is meant to cover exactly that case.
- **Judge prompt.** No chain of thought for the judge, per p.10. Our judge still writes a short
  rationale, which may act like a light chain of thought.
- **Cost.** One debate at 3 rounds is 6 advocate calls plus 1 judge call. Consultancy is 3 + 1.
  The direct baseline is 1 claude-haiku call with no retrieval. "Strong-model accuracy" is
  single-claude-sonnet with evidence.

## Proposed protocol
```yaml
id: kenton-weak-judge
description: Strong mid-tier advocates (claude-sonnet affirm, grok-fast deny) see the retrieved evidence and debate for 3 rounds; a cheap weak judge (claude-haiku) never sees the evidence, only the debate plus quotes checked word for word against the sources (Kenton et al. 2024, extractive/information-asymmetric setting).
pattern: debate
paper: 07-kenton-2024-weak-judges-strong-llms
controls: [kenton-consultancy, kenton-direct-weak, single-claude-haiku, single-claude-sonnet]
tags: [season0, z5]
evidence: {retrieve: true, max_sources: 6, per_agent: shared, judge_sees: quotes}
agents:
  - {role: advocate, side: affirm, model: claude-sonnet}
  - {role: advocate, side: deny, model: grok-fast}
  - {role: judge, model: claude-haiku}
rounds: 3
best_of_n: 1
quotes: {verify: true, max_words: 30}
aggregation: judge
```

```yaml
id: kenton-consultancy
description: Control for kenton-weak-judge. One strong consultant (claude-sonnet) argues a randomly assigned side for 3 rounds; the same weak judge (claude-haiku) sees only the consultant's arguments and verified quotes, never the evidence.
pattern: consultancy
paper: 07-kenton-2024-weak-judges-strong-llms
controls: [kenton-weak-judge, kenton-direct-weak]
tags: [season0, z5]
evidence: {retrieve: true, max_sources: 6, per_agent: shared, judge_sees: quotes}
agents:
  - {role: consultant, model: claude-sonnet}
  - {role: judge, model: claude-haiku}
rounds: 3
quotes: {verify: true, max_words: 30}
aggregation: judge
```

```yaml
id: kenton-direct-weak
description: Kenton's QA-without-article baseline. The weak judge (claude-haiku) answers the claim directly from its own knowledge, with no retrieval and no help from a stronger model.
pattern: single
paper: 07-kenton-2024-weak-judges-strong-llms
controls: [kenton-weak-judge, single-claude-haiku, single-claude-sonnet]
tags: [season0, z5]
evidence: {retrieve: false}
agents:
  - {role: answerer, model: claude-haiku}
aggregation: majority
output: {rationale_words: 60}
```

