# Cytokinesis Wiring Row Status

## Authored

- `data/schemas/per_process_wiring/Cytokinesis.yaml`

## What It Captures

- Process identity for `Cytokinesis` and the matching OC class `KarrCytokinesisProcess`.
- MATLAB method correspondence for:
  - `calcResourceRequirements_Current`
  - `calcResourceRequirements_LifeCycle`
  - `evolveState`
  - `calcFluxBounds` placeholder
- Allocator mode and request logic:
  - Karr mode: `allocation`
  - OC current mode: `allocation`
  - Current request comparison points at `KarrCytokinesisProcess.next_update` and `_water_request`
- Per-tick substrate wiring:
  - consume: `H2O`
  - produce: `PI`, `H`
- Compartment routing, dependencies, ordering notes, source anchors, provenance, and deviations.

## Validation

- Equivalent YAML load check: `OK dict 13`
- The exact validation command from the task points at `/mnt/e/opencell`, which does not contain this worktree row file, so I validated the authored file at `/mnt/e/opencell-worktrees/cytokinesis` instead.

## Uncertainties

- `calcFluxBounds` is marked `not_implemented` because the MATLAB Cytokinesis source does not define a local override and the OC port does not expose a flux-bounds path.
- The task requested provenance fields such as `last_audited`, `audited_by`, `oc_commit_sha`, `matlab_files_referenced`, and `oc_files_referenced`, but the current schema only allows `fixture_files`, `kb_version`, `extraction_date_utc`, and `notes`. I recorded the extra audit metadata in `provenance.notes`.
- I treated `Metabolism` as the only clear substrate-level dependency in the local source set; enzyme/filament interactions were not modeled as dependency edges.

## Observed Deviations

- OC embeds the allocator request in `next_update` and uses a geometry/gating-aware water request, while MATLAB requests water from the current FtsZ-GTP polymer pool.
- OC keeps a zero-valued GTP request slot for compatibility, but the MATLAB source only requests water.
- The OC port does not expose a separate lifecycle resource calculator.
