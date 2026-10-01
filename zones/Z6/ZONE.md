# Z6 · Persona panels

Judges with distinct perspectives discuss before ruling (Chan et al. 2023).

**Control:** `chateval-panel-same-persona`.

**Papers:** [04](../../library/cards/04-chan-2023-chateval.md)

## Sub-techniques

- `sub/diverse-personas.yaml`: one by one
- `sub/simultaneous.yaml`: everyone at once
- `sub/with-summarizer.yaml`: simultaneous with a summarizer

## Knobs

Ranges live in `knobs.yaml`. A zone refinement run may change only these, and only within range.

- **personas** (`agents[role=judge].persona`)
- **panel** (`agents`)
- **mode** (`communication`)
- **rounds** (`rounds`)

## Open questions

- Which persona set helps most on 'not enough evidence' claims?
