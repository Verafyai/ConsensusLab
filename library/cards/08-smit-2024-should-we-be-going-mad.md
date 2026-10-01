---
paper: 08-smit-2024-should-we-be-going-mad
title: "Should we be going MAD? A Look at Multi-Agent Debate Strategies for LLMs"
authors: Smit, Grinsztajn, Duckworth, Barrett, Pretorius
year: 2024
arxiv: 2311.17371v3
protocol: smit-controls
zone: Z3
controls: [smit-self-consistency, smit-ensemble, single-claude-sonnet, du-society, liang-mad]
claim: "Debate doesn't beat cheap baselines unless agreement is tuned."
---

## Setup and task
Smit et al. (InstaDeep, ICML 2024) benchmark multi-agent debate (MAD) protocols against
non-debate prompting strategies on multiple-choice QA. The protocols are Society of Mind (Du),
Multi-Persona (Liang), ChatEval (Chan), Ensemble Refinement, Medprompt, self-consistency and a
single agent. They weigh accuracy against cost and time:
[p.1: "We benchmark a range of debating and prompting strategies to explore the trade-offs between cost, time, and accuracy."]
Datasets:
[p.3: "We evaluate each system using seven datasets: three medical datasets, and three more general datasets requiring reasoning"]
(MedQA, PubMedQA, MMLU-clinical; CosmosQA, CIAR, GPQA; plus Chess state tracking).
Base model: [p.3: "As base agents for the MAD implementations, we utilize GPT-3"] with the
3.5-turbo engine. GPT-4 and Mixtral 8x7B were spot-checked on MedQA only (p.7).

## Roles, rounds and what the judge sees
- **Society of Mind (SoM):** agents answer, read each other's answers, and revise over rounds.
  Answers can optionally be summarized before they go into the shared history (p.2).
- **Multi-Persona:** an affirmative "angel" and a negative "devil" each answer, and a judge
  moderates. [p.2: "The judge has additional agency to end the debate early if it is satisfied with the answers provided."]
- **ChatEval:** one-on-one, simultaneous-talk, or simultaneous-talk with a summarizer (p.2).
- **Self-consistency (control):**
  [p.2: "samples multiple reasoning paths given a fixed prompt and selects the most frequent answer"].
- **Ensemble Refinement / Medprompt (controls):** several sampled reasoning paths are then
  aggregated in a second stage (p.2). Medprompt is run without its kNN few-shot retrieval (p.2).
- No agent sees external evidence. These are closed-book QA tasks, apart from the context
  passages in PubMedQA and CosmosQA.

## How a verdict is reached
Majority or plurality voting for SoM and self-consistency; a judge or moderator for Multi-Persona;
an aggregation step for Ensemble Refinement and Medprompt. Configurations were swept
[p.4: "changing the number of agents, rounds, reasoning and aggregation steps, altering agent prompts"],
and the best one per system per dataset was reported (Table 2, p.5). A K-fold check used the
hyperparameters that did best on held-out datasets of the same category (p.5).

## Headline finding
[p.1: "we find that multi-agent debating systems, in their current form, do not reliably outperform other proposed prompting strategies, such as self-consistency"].
[p.4: "Table 2 indicates that no protocol dominates on all datasets."]
[p.4: "Medprompt seems to perform the best overall."] On MedQA the best runs were
Medprompt 0.65, SoM 0.64, self-consistency 0.60 and Multi-Persona 0.58 (Table 2, p.5).
The authors read this as sensitivity rather than inherent weakness:
[p.5: "It seems that MAD protocols are more sensitive to hyperparameters."]
Cost does not buy accuracy reliably:
[p.4: "beyond a certain threshold, additional computing does not guarantee better results"].

**Agreement intensity, the paper's fix.** They prompt agents with
[p.6: "you should agree with the other agents X% of the time"] and sweep X
[p.6: "as we increase the prompted agreement intensity from zero to 100%"]. Result:
[p.6: "provides a substantial (≈15%) improvement in performance for Multi-Persona, and (≈5%) for SoM on the USMLE dataset"].
[p.6: "ChatEval, on the contrary, is hardly affected by this prompting mechanism"].
The best value depends on the dataset:
[p.6: "while MedQA and PubMedQA directly benefit from a high agreement, CIAR follows a reverse pattern"].
CIAR is built to be counter-intuitive, so strong disagreement helps there. The setting they
carried forward was high: [p.6: "we apply the 90% agreement intensity agent prompts to Multi-Persona on the full MedQA"].
With that setting, [p.9: "it went from being the worst-performing protocol to the best-performing"].
Transfer was mixed: it held for GPT-4, but [p.9: "this transferability does not extend well to Mixtral 8x7B"].

**Claim we test:** at matched call count, du-society and liang-mad do not beat self-consistency or a
cross-model panel unless agreement intensity is tuned. The paper's knob range is 0 to 100%. Its best
value was about 90% on knowledge-recall tasks (MedQA/USMLE, PubMedQA), and low agreement won on
counter-intuitive reasoning (CIAR). Fact-checking real claims is mostly evidence-reading and recall,
so the paper predicts du-society-agree-high > du-society-agree-low. If our results show the reverse,
that is informative too: it would suggest claims behave more like CIAR's traps.

## Reported settings
- Model: gpt-3.5-turbo for all agents; GPT-4 and Mixtral 8x7B spot checks on MedQA (p.7).
- Datasets: MedQA (1273 questions, 4-option version), PubMedQA (500), MMLU clinical (123),
  CosmosQA (500 subsampled), CIAR (50), GPQA (448), Chess Short (p.3–4). The agreement sweep used a
  376-question USMLE subset of MedQA (p.6).
- Agent prompts swept: zero-shot, zero-shot CoT, few-shot, Solo Performance Prompting, few-shot
  CoT (p.2).
- Agreement intensity: prompt-level X% from 0 to 100; best on USMLE was 90% for Multi-Persona
  (p.6), with gains of about 15% (Multi-Persona) and 5% (SoM).
- Best SoM configurations used 3–4 agents and 2–3 rounds (Figure 7, p.8). Debate protocols need
  more calls: [p.9: "MAD typically requires a higher number of API calls"].
- Debate's own contribution varied by system: from first answer to final answer,
  [p.5: "Society of Mind shows a substantial increase, and Multi-Persona, intriguingly, leads to a decrease in performance"].

## Faithfulness note
- **Task and labels.** The paper uses multiple-choice QA (mostly medical) scored on accuracy.
  We use four-label claim verification with retrieved evidence (≤6 sources, before the claim
  date). Agreement may matter differently here: when all agents share the same evidence, high
  agreement may simply copy the first misreading.
- **Controls.** smit-self-consistency is one claude-sonnet answer sampled 9 times. That matches
  du-society's call count, assuming du-society uses 3 agents over 1 initial round plus 2 revision
  rounds = 9 calls; it should be re-sized if du-society's card changes. smit-ensemble is a 3-model
  majority panel. That is *not* the paper's Ensemble Refinement or Medprompt, which add a
  second-stage aggregation and few-shot exemplars. It stands in for "cheap non-debate ensembling"
  and is cheaper (3 calls).
- **Agreement knob rendering.** The paper uses the literal prompt "agree X% of the time". Our engine
  maps `agreement_intensity` onto three instruction tiers: below 0.25 "keep your own view", below 0.6
  "weigh seriously", otherwise "work toward a consensus". So 0.1 and 0.9 test the two ends, but
  finer values within a tier render the same prompt, and the engine cannot reproduce the paper's
  smooth sweep. Matching the paper exactly would need a prompt override with the literal X%.
- **Where the knob acts.** Smit applied it mainly to Multi-Persona (liang-mad's ancestor), by
  changing the devil's system prompt, and secondarily to SoM. Our engine reads
  `agreement_intensity` only in the society pattern's revision prompt. The schema accepts it on a
  debate protocol, but the engine ignores it there. So a "liang-mad-agree-high" YAML would currently
  be a no-op, and we give none. The paper's biggest effect (+15% on Multi-Persona) therefore cannot
  be tested until the debate pattern reads the knob.
- **Models.** Season 0 uses claude-sonnet (and grok-fast) instead of GPT-3.5. The paper itself
  found the tuned value did not transfer to Mixtral (p.9), so the best value may move for our models.
- **Cost.** Each du-society variant is 9 claude-sonnet calls. smit-self-consistency is also 9.
  smit-ensemble is 3 mixed-tier calls. Report results at matched cost, as the zone rules require.

## Proposed protocol
```yaml
id: smit-self-consistency
description: Smit et al. control. One model (claude-sonnet) sampled 9 times on the same retrieved evidence, matching du-society's call count (3 agents x 3 answer rounds); majority vote; confidence = agreement.
pattern: sample_vote
paper: 08-smit-2024-should-we-be-going-mad
controls: [single-claude-sonnet]
tags: [season0, z3]
evidence: {retrieve: true, max_sources: 6, per_agent: shared}
agents:
  - {role: answerer, model: claude-sonnet, samples: 9}
aggregation: majority
```

```yaml
id: smit-ensemble
description: Smit et al. control (cheap non-debate ensembling). Three models from two families answer independently on the same evidence; simple majority vote.
pattern: panel
paper: 08-smit-2024-should-we-be-going-mad
controls: [single-claude-sonnet, smit-self-consistency]
tags: [season0, z3]
evidence: {retrieve: true, max_sources: 6, per_agent: shared}
agents:
  - {role: answerer, model: claude-sonnet, name: sonnet}
  - {role: answerer, model: grok-fast, name: grok}
  - {role: answerer, model: claude-haiku, name: haiku}
aggregation: majority
```

```yaml
id: du-society-agree-low
description: du-society with low agreement intensity (0.1, rendered as keep your own view unless given a decisive reason). Smit et al. found low agreement helps only on counter-intuitive tasks (CIAR).
pattern: society
paper: 08-smit-2024-should-we-be-going-mad
controls: [smit-self-consistency, smit-ensemble, du-society, single-claude-sonnet]
tags: [season0, z3]
evidence: {retrieve: true, max_sources: 6, per_agent: shared}
agents:
  - {role: answerer, model: claude-sonnet, name: agent-1}
  - {role: answerer, model: claude-sonnet, name: agent-2}
  - {role: answerer, model: claude-sonnet, name: agent-3}
rounds: 2
communication: simultaneous
agreement_intensity: 0.1
aggregation: majority
```

```yaml
id: du-society-agree-high
description: du-society with high agreement intensity (0.9, rendered as work toward a consensus). Smit et al. carried 90% agreement forward as their best setting on MedQA/USMLE.
pattern: society
paper: 08-smit-2024-should-we-be-going-mad
controls: [smit-self-consistency, smit-ensemble, du-society, single-claude-sonnet]
tags: [season0, z3]
evidence: {retrieve: true, max_sources: 6, per_agent: shared}
agents:
  - {role: answerer, model: claude-sonnet, name: agent-1}
  - {role: answerer, model: claude-sonnet, name: agent-2}
  - {role: answerer, model: claude-sonnet, name: agent-3}
rounds: 2
communication: simultaneous
agreement_intensity: 0.9
aggregation: majority
```
