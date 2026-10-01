---
paper: 01-irving-2018-ai-safety-via-debate
title: AI safety via debate
authors: Irving, Christiano, Amodei
year: 2018
arxiv: 1805.00899v2
protocol: irving-debate
zone: Z4
controls: [irving-consultancy, single-claude-sonnet-closed]
claim: "A judge reaches the truth from adversarial argument alone."
---

## Setup and task
A mostly theoretical proposal: train agents "via self play on a zero sum debate game"
[p.1: "we propose training agents via self play on a zero sum debate game"], so that a judge
can supervise tasks too hard to judge directly. The central bet is stated as a claim
[p.3: "In the debate game, it is harder to lie than to refute a lie."]. The only experiment
run is a toy image task: MNIST digits, where "agents compete to convince a sparse classifier"
[p.1: "an initial MNIST experiment where agents compete to convince a sparse classifier"].
A human cat-vs-dog version with natural language was built as a website but only played
informally [p.11: "We leave formal experiments testing whether honesty wins in single pixel debate to future work."].
There is no natural-language, LLM or fact-checking experiment in the paper.

## Roles, rounds and what the judge sees
Two debaters and one judge. Both agents see the question, state answers, then alternate
statements, and the judge sees only the transcript
[p.3: "The judge sees the debate (q, a, s) and decides which agent wins."].
The information gap is the point: the image is shown to the debaters but not the judge
[p.8: "A random MNIST image is shown to the two debating agents but not the judge."], which
the authors frame as replacing "thinks better" with "knows more"
[p.7: "we can give the agents access to a source of information that the judge cannot see"].
Sides are fixed in advance, one honest and one liar
[p.7: "we prespecify one agent as honest and one as liar"]. Each turn reveals one true pixel;
for 6 pixels "each player reveals 3 pixels" [p.9: "In the 6 pixel case, this means each player reveals 3 pixels."].
Revealed context cannot be faked, and the paper says debate depends on that
[p.7: "Debate only works if this revealed context cannot be a lie"].

## How a verdict is reached
The judge is a fixed CNN trained beforehand to classify digits from a few random nonzero
pixels. The winner is "the player whose claimed class has higher logit"
[p.9: "The winner is the player whose claimed class has higher logit when the sparse mask is shown to the judge"].
In the precommit variant the liar must state the lie up front and cannot change it
[p.8: "the liar states their claim in advance of making moves and cannot change their story"].
The baseline is the same judge looking at random pixels with no debate. Debaters are not
trained: they play by pure Monte Carlo tree search against the fixed judge
[p.9: "We use 10k rollouts per move, where each rollout descends to a leaf for evaluation using the judge."].
There is no consultancy (single-advocate) control.

## Headline finding
Debate raises the sparse judge's accuracy a lot. With 6 pixels, "debate with precommit
turns a 59.4% accurate judge into a 88.9% accurate debate"
[p.10: "debate with precommit turns a 59.4% accurate judge into a 88.9% accurate debate"],
and with 4 pixels "a 48.2% accurate judge becomes an 85.2% accurate debate"
[p.10: "With 4 pixels, a 48.2% accurate judge becomes an 85.2% accurate debate."].
Precommit matters [p.10: "For both 4 and 6 pixels precommit is crucial"]. The claim we test,
"a judge reaches the truth from adversarial argument alone", is our reading of the paper's
hypothesis, not something it showed for language
[p.2: "Our hypothesis is that optimal play in this game produces honest, aligned information far beyond the capabilities of the human judge."].

## Reported settings
- Judge: TensorFlow MNIST tutorial CNN, Adam lr 1e-4, trained to 59.4% (6 px) / 48.2% (4 px)
  [p.9: "We train the judges using Adam with a learning rate of 10−4 for 30k (resp. 50k) batches of 128 samples"].
- Debate length: 4 or 6 revealed pixels in total, alternating turns, one honest and one liar player.
- Debaters: MCTS with 10k rollouts per move, c_puct = 1, no learned heuristic.
- Precommit modeled by playing all 9 possible lies, mean over 3 seeds per lie.
- Evaluated on the MNIST test set; the debaters have full access to the judge, so the result
  models "debate agents with no generalization error" [p.10: "we are modeling the limit of debate agents with no generalization error"].

## Faithfulness note
Almost everything changes. (1) Task: Irving's only result is MNIST with a CNN judge and MCTS
debaters; we run LLM advocates and an LLM judge on real-world claims. No result in the paper
speaks to natural-language debate between LLMs. (2) Unforgeable evidence: in the paper every
move is a true pixel, and the paper says debate needs that. Our seed setting `judge_sees: none`
means the judge sees only the advocates' prose, so a quote or source can be invented and the
judge cannot check it. That makes our test harder for the honest side than the MNIST game was.
A setup closer to Irving's mechanics would show the judge verified quotes (`judge_sees: quotes`),
but that is the Michael et al. protocol (Z5). We keep `none` as the spec asks, and the
`michael-asymmetric` run should be read alongside this one. (3) Optimal play: MCTS debaters
search against the exact judge they face. LLM advocates are prompted, not optimized, so the
"liar" is weaker than in the paper. (4) Labels: the paper's judge picks between two claimed
classes. Our debate fixes an affirm side and a deny side, so neither advocate argues
not_enough_evidence or conflicting, and a judge with no evidence has little basis for those
labels. Expect our 4-way accuracy to be lower than binary accuracy. (5) Honest vs. liar: the paper fixes one honest debater. Here which advocate is
"lying" depends on the gold label, and on not_enough_evidence or conflicting items both
advocates overstate. (6) Models and rounds: 3 rounds mirrors 3 pixels each in the 6-pixel game.
Advocates are claude-sonnet (affirm) and grok-fast (deny). Irving uses copies of the same agent,
so model family is confounded with side here. A side-swapped rerun would remove that confound.
The judge is claude-sonnet. The paper's judge is weak because it lacks information, not
because it is a smaller model, so we do not use claude-haiku.

## Proposed protocol
```yaml
id: irving-debate
description: Two advocates with fixed opposite sides argue for three rounds over retrieved evidence; the judge sees only the debate transcript, never the evidence (Irving et al. 2018).
pattern: debate
paper: 01-irving-2018-ai-safety-via-debate
controls: [irving-consultancy, single-claude-sonnet-closed]
tags: [season0, z4]
evidence: {retrieve: true, max_sources: 6, per_agent: shared, judge_sees: none}
agents:
  - {role: advocate, side: affirm, model: claude-sonnet}
  - {role: advocate, side: deny, model: grok-fast}
  - {role: judge, model: claude-sonnet}
rounds: 3
aggregation: judge
early_stop: {judge_can_end: false}
```
