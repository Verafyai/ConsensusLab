---
paper: 02-du-2023-multiagent-debate          # file stem from library/MANIFEST
title: Improving Factuality and Reasoning in Language Models through Multiagent Debate
authors: Du, Li, Torralba, Tenenbaum, Mordatch
year: 2023
arxiv: 2305.14325v1
protocol: du-society                          # seed protocol id (spec §5.3 table)
zone: Z3                                      # testing zone (spec §5.4)
controls: [self-consistency, single-claude-sonnet]   # protocol ids it must be compared with
claim: "Revising after reading peers beats answering alone."   # the finding we test
---

## Setup and task
What the paper did and on which tasks, with page references.

## Roles, rounds and what the judge sees
Agents, roles, number of rounds, who sees what (evidence, other agents, the debate).

## How a verdict is reached
Aggregation or judging rule, and the baseline(s) the paper compared against.

## Headline finding
The paper's main result in its own terms, with numbers, and the claim we will test.

## Reported settings
Concrete settings: models, agents, rounds, temperatures, prompt features, sample sizes.

## Faithfulness note
What had to change to apply this to fact-checking with our engine, and what that may
cost in faithfulness. Be specific: task change, label set, evidence, models, rounds.

## Proposed protocol
```yaml
# a protocol that validates with lab.protocols.schema.validate_protocol
```

Page references: [p.N: "verbatim snippet of 4-25 words copied from physical PDF page N"].
Every factual statement about the paper should carry one. At least 5 per card.
