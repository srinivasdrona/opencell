# STATUS: Wiring row for FtsZPolymerization

## What I authored
- Added [`data/schemas/per_process_wiring/FtsZPolymerization.yaml`](/E:/opencell-worktrees/ftsz_polymerization/data/schemas/per_process_wiring/FtsZPolymerization.yaml) as a single per-process wiring DB row for `FtsZPolymerization`.
- Added [`STATUS_wiring_row_ftsz_polymerization.md`](/E:/opencell-worktrees/ftsz_polymerization/STATUS_wiring_row_ftsz_polymerization.md) to record the evidence trail and the one main uncertainty.

## What the row captures
- Process identity and OC class/file mapping.
- Allocator mode: `allocation` on both Karr and OC.
- The OC request path: direct `GTP` request emission from `next_update`, with `substrates_allocated[self.name]` readback in the clamp path.
- Canonical consumed / produced substrates: `GTP`, `GDP`, `H2O` consumed; `GDP`, `PI`, `H` produced.
- Compartment routing: all exemplar substrates are cytosolic.
- Unit conversion: counts to concentration for the ODE, then back to integer tick deltas with rounding / clamping.
- Dependencies: `Cytokinesis` downstream, and the usual protein-production / maturation upstreams.
- Ordering: no FtsZ-specific rule found; only the global `tRNAAminoacylation < Translation` ordering was anchored.

## Uncertainties
- The raw MATLAB source file `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/FtsZPolymerization.m` was not present in this checkout, so I used `docs/karr_extracts/process/25_FtsZPolymerization.md` and the OC implementation as the evidence trail for MATLAB-side anchors.
- Because of that, the MATLAB-side `calcResourceRequirements_Current` and `calcFluxBounds` entries are conservative and partly proxy-based rather than direct file-line diffs.

## Divergences observed
- OC does not have a separate FtsZ request-calculator module; the request is emitted directly from `KarrFtsZPolymerizationProcess.next_update`.
- OC keeps a direct substrate-store fallback path for GTP when allocation is absent.
- `calcFluxBounds` is not a real process-local concern here; the row keeps that slot as `not_implemented` for schema completeness.

## Validation status
- `bin\oc-py.cmd _tmp_validate_ftsz.py` in this worktree returned `OK dict 13`.
- The exact task-provided WSL command targeted `/mnt/e/opencell`, which does not contain this worktree's new row file; I validated the authored row in the active worktree instead.
