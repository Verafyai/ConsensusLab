# Z2 · Sampling and ensembles

Many independent answers, combined by a vote. Cheap, strong baselines that debate must beat (Smit et al. 2024).

**Control:** The best configuration in Z1.

**Papers:** [08](../../library/cards/08-smit-2024-should-we-be-going-mad.md)

## Sub-techniques

- `sub/self-consistency.yaml`: one model sampled N times, majority
- `sub/multi-model-vote.yaml`: models from different families, majority
- `sub/confidence-weighted-vote.yaml`: votes weighted by stated confidence

## Knobs

Ranges live in `knobs.yaml`. A zone refinement run may change only these, and only within range.

- **samples** (`agents[*].samples`)
- **panel** (`agents`)
- **vote_rule** (`aggregation`)
- **model** (`agents[*].model`)

## Open questions

- Is model diversity worth more than more samples of the best model at equal cost?
