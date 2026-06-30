# ChromosomeCondensation Wiring Row Status

Authored `data/schemas/per_process_wiring/ChromosomeCondensation.yaml` for the `ChromosomeCondensation` Karr process and grounded it in:

- MATLAB source: `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ChromosomeCondensation.m`
- Simulation ordering source: `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m`
- OC port: `opencell/vivarium/karr_chromosome_condensation.py`
- Chassis wiring: `opencell/vivarium/karr_composite.py`

What I captured:

- Class identity and the OC process/class mapping.
- `calcResourceRequirements_Current`, `evolveState`, `initializeState`, `calcResourceRequirements_LifeCycle`, `calcNewRegions`, and the schema-required `calcFluxBounds` slot.
- Allocator mode as `allocation` on the Karr side and `mixed` on the OC side because OC reads `substrates_allocated` first and still has a zero-grant fallback to global `substrates`.
- Canonical ATP/H2O request tuples and ATP/H2O/ADP/PI/H substrate traffic.
- The only explicit global ordering rule I found: `tRNAAminoacylation < Translation`.
- Fixture provenance from the OC constructor defaults.

Uncertainties and deviations:

- The schema only has `fixture_files`, `kb_version`, `extraction_date_utc`, and `notes` under `provenance`, so the requested audit metadata (`last_audited`, `audited_by`, `oc_commit_sha`, referenced file lists) is encoded in `provenance.notes` instead of separate fields.
- `kb_version` was not explicit in the fixture JSON, so I recorded it as `unknown` and noted the v2 trace manifest hint in the notes.
- `calcFluxBounds` is not present for this process in either source tree, so that row entry is marked `not_implemented`.
- The OC port is intentionally Karr-light and does not preserve the full per-position chromosome topology.

Validation passed: the row parsed as `OK dict 13` under the project WSL Python environment.
