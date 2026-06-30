# STATUS: ProteinModification wiring row

## What I authored

- Added [`data/schemas/per_process_wiring/ProteinModification.yaml`](E:/opencell-worktrees/protein_modification/data/schemas/per_process_wiring/ProteinModification.yaml) as the per-process wiring DB row for `ProteinModification`.
- Captured process identity, method correspondence, allocator mode, request formula, substrate stoichiometry, compartment routing, unit-conversion chain, dependencies, ordering constraints, source anchors, provenance, and deviations.
- Validated the row with the WSL Python parse check: `OK dict 13`.

## What I found

- The current OC port uses `substrates_allocated[self.name]`, so the allocator mode is `allocation` on both sides.
- The OC request path is implemented through the shared `RequestCalculatorProteinPathway` step, not a process-local request method.
- The current OC biology path has a replay-only `trace_hint.unmodifiedMonomers_next` short-circuit, which is absent from the MATLAB process body.
- The raw MATLAB `ProteinModification.m` blob is not present in this checkout, so MATLAB anchors come from repo audit notes and design docs that quote the relevant line ranges.

## Uncertainties

- I could not directly inspect the raw MATLAB file in this worktree, so the MATLAB method split and some line spans are represented through audit notes rather than direct blob citations.
- The `kb_version` string is inferred from the V2 trace / fixture batch naming rather than read from a dedicated per-process KB manifest field.

## Deviations observed

- OC adds replay-only trace-hint gating in `next_update`.
- OC reads substrate allocations from `substrates_allocated` instead of the global `substrates` store.
- OC retains legacy `_n_completed` bookkeeping and a `max_stochastic_iterations` cap for test/replay stability.
