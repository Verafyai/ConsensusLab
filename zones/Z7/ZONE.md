# Z7 · Evidence-first aggregation

Grade each source's stance, then aggregate in code. The lab's own family; the optional calibrated aggregator (Jev) waits on a Jev endpoint.

**Control:** `z1-with-evidence`.

**Papers:** none

## Sub-techniques

- `sub/stance-grading.yaml`: two graders
- `sub/weighted-stance.yaml`: three graders, two families

## Knobs

Ranges live in `knobs.yaml`. A zone refinement run may change only these, and only within range.

- **graders** (`agents`)
- **max_sources** (`evidence.max_sources`)

## Open questions

- Does stance aggregation hold up when sources are few or one-sided?
