# Z1 · Single model

One model, one answer. This zone is the floor every other zone must beat. Its best configuration is the reference 'best single model' for every comparison.

**Control:** None. This zone is the floor everyone must beat.

**Papers:** none

## Sub-techniques

- `sub/direct.yaml`: answer from the model's own knowledge (no retrieval)
- `sub/with-evidence.yaml`: answer from retrieved evidence
- `sub/reasoning-first.yaml`: more effort spent reasoning before answering

## Knobs

Ranges live in `knobs.yaml`. A zone refinement run may change only these, and only within range.

- **model** (`agents[*].model`)
- **evidence** (`evidence.retrieve`)
- **max_sources** (`evidence.max_sources`)
- **effort** (`agents[*].effort`)

## Open questions

- How much does retrieval add over closed-book answering on post-cutoff items?
- Does more effort buy calibration, accuracy, or neither?

_Note: The spec lists temperature as a Z1 knob. Current Claude models reject sampling parameters, so effort stands in for it._
