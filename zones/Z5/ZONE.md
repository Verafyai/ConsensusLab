# Z5 · Information-asymmetric debate

Debaters see the evidence; the judge doesn't, and sees only arguments and verified quotes (Michael 2023, Khan 2024, Kenton 2024).

**Control:** `michael-consultancy`.

**Papers:** [05](../../library/cards/05-michael-2023-debate-supervise-unreliable-experts.md), [06](../../library/cards/06-khan-2024-persuasive-debaters-truthful.md), [07](../../library/cards/07-kenton-2024-weak-judges-strong-llms.md)

## Sub-techniques

- `sub/judge-without-evidence.yaml`: judge sees arguments only
- `sub/verified-quotes.yaml`: judge sees arguments plus verified quotes
- `sub/best-of-n.yaml`: most persuasive of N drafts each turn
- `sub/weak-judge.yaml`: cheap judge, strong debaters

## Knobs

Ranges live in `knobs.yaml`. A zone refinement run may change only these, and only within range.

- **judge_model** (`agents[role=judge].model`)
- **quote_words** (`quotes.max_words`)
- **best_of_n** (`best_of_n`)
- **rounds** (`rounds`)
- **judge_sees** (`evidence.judge_sees`)
- **side_assignment** (`swap_sides`)
- **advocate_models** (`agents[role=advocate].model`)

## Open questions

- Does quote verification, rather than argument, carry the gain (Kenton p.21)?
