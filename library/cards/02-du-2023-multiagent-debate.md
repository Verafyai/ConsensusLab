---
paper: 02-du-2023-multiagent-debate
title: Improving Factuality and Reasoning in Language Models through Multiagent Debate
authors: Du, Li, Torralba, Tenenbaum, Mordatch
year: 2023
arxiv: 2305.14325v1
protocol: du-society
zone: Z3
controls: [self-consistency, single-claude-sonnet]
claim: "Revising after reading peers beats answering alone."
---

## Setup and task
Several copies of one LLM answer a question, then "propose and debate their individual
responses and reasoning processes over multiple rounds"
[p.1: "propose and debate their individual responses and reasoning processes over multiple rounds"].
The tasks are reasoning tasks (arithmetic, GSM8K, chess move prediction) and factuality
tasks (a new computer-scientist biography benchmark, MMLU, chess move validity)
[p.7: "We utilize the existing MMLU dataset [8] to benchmark the accuracy of responses."].
Biographies use ground truth for 524 people
[p.6: "We constructed ground truth bullet point biographies of 524 well-known computer scientists."].
None of the tasks is claim verification against retrieved evidence, and agents use no retrieval.

## Roles, rounds and what the judge sees
There is no judge. All agents are peers with the same role and prompt. Each first answers on
its own. Then "individual responses from other agents are concatenated and given as context to each agent"
[p.4: "Individual responses from other agents are concatenated and given as context to each agent"],
and each agent writes an updated answer. This repeats for several rounds
[p.4: "We iteratively repeat this debate procedure over multiple rounds for improved performance."].
Most results use "three agents with two rounds of debates"
[p.5: "mainly using three agents with two rounds of debates"]. With more agents, the peers'
responses are first summarized by chatGPT to fit in context
[p.7: "we first summarize all agent responses with chatGPT instead of directly concatenating responses"].

## How a verdict is reached
Agents usually converge on one shared answer
[p.4: "language models are able to converge on a single shared answer after multiple rounds of debate"],
and that answer is scored. The baselines are a single agent, single-agent self-reflection, and
multi-agent majority voting
[p.7: "We use the same baselines as in Section 3.1."].
Majority voting is dropped on the factuality tasks
[p.7: "we omit baseline comparison with the majority voting in this setting"]. The majority-vote
baseline uses 3 independent answers, while debate uses 3 agents × 3 generations, so the
two are not matched on cost.

## Headline finding
Debate beats every baseline. With 3 agents and 2 rounds (Table 1): arithmetic 81.8% vs 67.0%
for a single agent and 69.0% for majority vote. GSM8K 85.0% vs 77.0% single and 81.0%
majority [p.6: "Multi-agent results in the table are run with 3 agents and two rounds of debate."].
Factuality (Table 2): biographies 73.8 vs 66.0, MMLU 71.1 vs 63.9
[p.7: "debate gives the best performance in this setting also, and significantly outperforms each baseline"].
The authors note convergence does not guarantee correctness
[p.10: "while debates typically converged into single final answers, these answers were not necessarily correct"].
The claim we test is the paper's core claim: revising after reading peers beats answering alone.
We add the stricter comparison against self-consistency at matched cost.

## Reported settings
- Model: [p.13: "We run all experiments using the gpt-3.5-turbo-0301 model."]. A 20-problem
  GSM8K test mixed chatGPT and Bard (Bard 11, chatGPT 14, debate 17 solved).
- Agents/rounds: 3 agents, 2 debate rounds by default. Gains continue with more agents and
  rounds, but [p.7: "additional debate rounds above four led to a similar final performance to 4 rounds of debate"].
- Sample sizes are small, 100 items per task
  [p.13: "We evaluated models on one hundred selected MMLU questions randomly distributed across each of the subject areas."].
- Prompts: zero-shot chain of thought. The same prompt template is used for every task. The
  "long" debate prompt ("as additional advice") makes agents more stubborn and produces better
  final answers [p.4: "prompts that encouraged models to be more “stubborn’ based on their own solutions led to longer debates and better final solutions"].
- Agreeableness: [p.4: "we observed that language model agents were relatively "agreeable""].
- Temperature is not reported.

## Faithfulness note
(1) Task and labels: Du scores free-form or multiple-choice answers on math, chess, MMLU and
biographies. We ask for one of four fact-check labels. Converging on a single label is easier
than converging on a free-form answer, and converging on a wrong label is a known failure
mode. (2) Evidence: Du's agents use no retrieval. Ours share up to 6 retrieved sources, so
agents may start out agreeing more. With fewer disagreements left to resolve, there is less
room for the revision gain Du reports. (3) What peers see: Du concatenates full peer responses.
Our engine passes each peer's verdict, confidence and short rationale. This is closer to Du's
summarized variant and carries less of the reasoning that let all-wrong agents recover.
(4) Models: three claude-sonnet copies, as in Du's same-model copies. grok-fast is left out so the
comparison with the claude-sonnet self-consistency and single controls stays clean. A mixed-family
variant is a separate experiment, and Du tested that only on 20 problems.
(5) Prompt: Du's default "long" prompt treats peers' answers "as additional advice". We map it to
agreement_intensity 0.5 (weigh peers seriously, change if better supported), not the
consensus-seeking setting, since Du found more stubborn agents did better. (6) Cost control: Du's
majority baseline was not cost-matched. Our society makes 9 calls per item (3 agents × 3
generations), so the self-consistency control should be run at 9 samples for a fair Z3 test.
The library default is 5. (7) Du's results on gpt-3.5 at n=100 per task carry wide error bars,
and the effect may shrink with stronger 2025-era models.

## Proposed protocol
```yaml
id: du-society
description: Three claude-sonnet copies answer independently, read each other's answers and revise for two rounds; majority of final answers (Du et al. 2023).
pattern: society
paper: 02-du-2023-multiagent-debate
controls: [self-consistency, single-claude-sonnet]
tags: [season0, z3]
evidence: {retrieve: true, max_sources: 6, per_agent: shared}
agents:
  - {role: answerer, model: claude-sonnet, name: agent-1}
  - {role: answerer, model: claude-sonnet, name: agent-2}
  - {role: answerer, model: claude-sonnet, name: agent-3}
rounds: 2
communication: simultaneous
agreement_intensity: 0.5
early_stop: {agree: false}
aggregation: majority
```
