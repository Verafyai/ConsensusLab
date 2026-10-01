---
paper: 03-liang-2023-divergent-thinking-mad
title: Encouraging Divergent Thinking in Large Language Models through Multi-Agent Debate
authors: Liang, He, Jiao, Wang, Wang, Wang, Yang, Shi, Tu
year: 2023
arxiv: 2305.19118v4
protocol: liang-mad
zone: Z4
controls: [self-consistency, single-claude-sonnet]
claim: "Forced disagreement avoids getting stuck on a first answer."
---

## Setup and task
The paper names a failure of self-reflection, Degeneration-of-Thought (DoT): "once the LLM
has established confidence in its solutions, it is unable to generate novel thoughts later
through reflection" [p.1: "once the LLM has established confidence in its solutions, it is unable to generate novel thoughts later"].
As a fix it proposes MAD [p.1: "we propose a Multi-Agent Debate (MAD) framework, in which multiple agents express their arguments"].
It is tested on two tasks where the intuitive answer is usually wrong: Chinese-to-English
commonsense machine translation (Common MT) and a new counter-intuitive arithmetic set
(CIAR) [p.4: "Our Counter-Intuitive AR dataset contains 200 questions collected from elicitation questions"].
Neither task is fact-checking, and neither uses retrieved evidence. The model works only
from its own knowledge.

## Roles, rounds and what the judge sees
There are three agents: two debaters and a judge [p.4: "including two debaters (i.e., affirmative and negative) and a judge"].
The debaters take turns and see the whole debate history [p.3: "speak one by one in a fixed order and express their arguments based on the previous debate history"].
The affirmative side states an answer. The negative side is told to oppose it
[p.3: "You disagree with the affirmative side’s points. Provide your reasons and answer."].
The sides are therefore defined relative to the first answer, not as fixed true or false
positions. A meta prompt sets a moderate "tit for tat" tone
[p.2: "It’s not necessary to fully agree with each other’s perspectives, as our objective is to find the correct answer"].
The judge sees the full debate transcript. After each round, in discriminative mode, it
decides whether to stop [p.3: "decides whether the correct solution can be obtained after all the debaters finish their arguments in the current iteration"].
Debates are capped at three rounds, and the judge can stop them early
[p.8: "setting the maximum debate iteration to 3. In other words, the judge can take an adaptive break"].

## How a verdict is reached
If the judge never stops the debate, it switches to extractive mode at the cap and picks
the answer [p.3: "the judge J needs to extract the final solution based on the whole debate history"].
There is no vote. The judge's ruling is the answer. Baselines were the plain model, CoT,
Self-Reflect and Self-Consistency (on CIAR), plus Rerank and MAPS (on Common MT)
[p.4: "This method samples multiple responses and determines the final answer through a majority vote."].
Self-Consistency, the paper's majority-vote baseline, is the cheap control we keep.

## Headline finding
On CIAR, GPT-3.5-Turbo with MAD scores 37.0% accuracy. That beats the plain model (26.0),
CoT (28.0), Self-Consistency (29.5) and Self-Reflect (27.5), but stays below GPT-4 (51.0)
[p.5: "Table 3: Accuracy on Counter-Intuitive AR."]
[p.5: "outperforms all the other compared methods based on GPT-3.5-Turbo"].
On Common MT, Turbo with MAD reaches GPT-4 level on automatic metrics and beats it on human
ratings [p.2: "GPT-3.5-Turbo with MAD can surpass the performance of GPT-4 on Common MT"].
For example, Lexical HUMAN is 3.78 against 3.41 [p.5: "Table 1: Translation performance on Common MT."].
The ablations support stopping debates early: forcing extra rounds hurts
[p.8: "Forcing the debate to continue will harm the translation results"].
Maximum disagreement also does not give the best result
[p.7: "(with a disagreement of 0.988) does not lead to the best performance"].
The judge favoured the negative side, which the authors credit for the gains
[p.7: "negative side, which is believed to contribute to the performance improvement in MAD"].
The claim we test: forced disagreement, refereed by a judge who can stop early, avoids
locking onto a first answer, compared with self-consistency and a single model at matched cost.

## Reported settings
- Models: vicuna-7b/13b-v1.5-16k, GPT-3.5-Turbo-0301 and GPT-4-0314. MAD was run on Turbo and
  Vicuna [p.4: "Here, we implement the methods on top of GPT-3.5-Turbo and Vicuna models."].
- Zero-shot prompts at temperature 0 [p.4: "Our experiments are performed in zero-shot instructions (setting temperature to 0)"].
- Two debaters by default. Adding more made results worse
  [p.7: "an increase in the number of debaters has resulted in varying degrees of performance reduction"].
- Judge strength matters less than debater strength
  [p.6: "Strong debaters with a weak judge work better than the reverse."].
- When the debaters use different models, the judge is biased toward its own model
  [p.7: "the judge shows a preference to the side with the same LLM as the backbone"].
- At most 3 rounds, with the judge able to stop early (see above).

## Faithfulness note
- **Task and labels.** We switch from translation and arithmetic, which have open answers,
  to real-claim fact-checking with four labels (supported, refuted, not_enough_evidence,
  conflicting). In our engine the debaters argue fixed sides: "the claim is TRUE" and "the
  claim is FALSE". In the paper, the negative side's job is to attack whatever the
  affirmative side said first. The anti-DoT mechanism comes from that relative opposition,
  and fixed sides only approximate it. Neither side argues for not_enough_evidence or
  conflicting, so the judge has to infer those two labels with no advocate pressing them.
  We expect this to cost accuracy on those two classes.
- **Evidence.** The paper has no retrieval. We give all agents and the judge
  (`judge_sees: full`) up to 6 pre-claim-date web sources. Shared evidence may anchor both
  sides on the same first reading, which could weaken the divergence the paper relies on.
- **Models.** The paper used the same model for all agents and found judge self-preference
  when the debaters' models differed. Season 0 pairs claude-sonnet (affirm) against grok-fast
  (deny) with a claude-sonnet judge. That setup is the one the paper flagged as biased, so a
  family effect may be confounded with a side effect. A side-swap or all-claude-sonnet rerun
  would separate the two.
- **Rounds and early stop.** We keep 3 rounds and `judge_can_end` with `min_rounds: 1`.
  This matches the adaptive break.
- **Tit-for-tat intensity.** The paper's best setting is moderate disagreement. Smit et al.
  2024 (card 08) later add an `agreement_intensity` knob to this protocol. In our engine that
  knob is currently only rendered into society revision prompts, not into debate advocate
  prompts, so we leave it unset here. Setting it on a debate would currently do nothing.
- **Temperature.** The paper used temperature 0. Ours follows the model defaults.

## Proposed protocol
```yaml
id: liang-mad
description: Liang et al. MAD. Affirmative vs. negative debaters argue for up to three rounds; a judge who sees the full debate may end it early once the answer is settled, else rules at the cap.
pattern: debate
paper: 03-liang-2023-divergent-thinking-mad
controls: [self-consistency, single-claude-sonnet]
tags: [season0, z4]
evidence: {retrieve: true, max_sources: 6, per_agent: shared, judge_sees: full}
agents:
  - {role: advocate, side: affirm, model: claude-sonnet, name: affirmative}
  - {role: advocate, side: deny, model: grok-fast, name: negative}
  - {role: judge, model: claude-sonnet, name: moderator}
rounds: 3
early_stop: {judge_can_end: true, min_rounds: 1}
aggregation: judge
```
