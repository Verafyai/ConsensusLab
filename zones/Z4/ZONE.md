# Z4 · Adversarial debate

Advocates argue assigned sides; a judge rules (Irving et al. 2018; Liang et al. 2023).

**Control:** The best configuration in Z2 at matched cost.

**Papers:** [01](../../library/cards/01-irving-2018-ai-safety-via-debate.md), [03](../../library/cards/03-liang-2023-divergent-thinking-mad.md)

## Sub-techniques

- `sub/fixed-side-debate.yaml`: two rounds, judge sees the evidence
- `sub/aff-neg-early-stop.yaml`: affirmative vs negative, judge may end early

## Knobs

Ranges live in `knobs.yaml`. A zone refinement run may change only these, and only within range.

- **rounds** (`rounds`)
- **judge_model** (`agents[role=judge].model`)
- **advocate_models** (`agents[role=advocate].model`)
- **early_stop** (`early_stop.judge_can_end`)
- **min_rounds** (`early_stop.min_rounds`)
- **side_assignment** (`swap_sides`)
- **judge_sees** (`evidence.judge_sees`)
- **agreement_intensity** (`agreement_intensity`)

## Open questions

- Is any debate gain explained by the judge simply reading more tokens?
