# Z3 · Iterative revision

Agents answer, read each other, and revise over rounds (Du et al. 2023). Smit et al. found the agreement level matters.

**Control:** `z2-self-consistency` at matched cost.

**Papers:** [02](../../library/cards/02-du-2023-multiagent-debate.md), [08](../../library/cards/08-smit-2024-should-we-be-going-mad.md)

## Sub-techniques

- `sub/society.yaml`: revise after peers' rationales
- `sub/revise-after-summary.yaml`: revise after a summary of the panel
- `sub/revise-after-full.yaml`: revise after peers' full answers

## Knobs

Ranges live in `knobs.yaml`. A zone refinement run may change only these, and only within range.

- **agents** (`agents`)
- **rounds** (`rounds`)
- **peer_view** (`peer_view`)
- **communication** (`communication`)
- **agreement_intensity** (`agreement_intensity`)
- **early_stop** (`early_stop.agree`)

## Open questions

- Does revision help on 'conflicting' claims, where a single answer is most brittle?
