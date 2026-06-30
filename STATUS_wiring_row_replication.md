# STATUS: wiring row for Replication

Authored `data/schemas/per_process_wiring/Replication.yaml` for the Karr `Replication` process.

What was recorded:
- Process identity and file mappings for Karr `Replication` and `opencell/vivarium/karr_replication.py`
- Method correspondence for `calcResourceRequirements_Current`, `evolveState`, and `calcFluxBounds`
- Allocator mode, request formula, request/bypass WIDs, stoichiometry, compartment routing, unit conversion, dependencies, ordering, source anchors, provenance, and deviations

Uncertainties:
- The raw MATLAB `Replication.m` file was not present in this worktree or the sibling checkout I inspected, so MATLAB anchors use the checked-in Karr extract docs instead of a direct `.m` read.
- `calcFluxBounds` appears to be absent for `Replication` in the current OC port, so that row entry is marked `not_implemented`.
- The dependency block is limited to shared-substrate coupling; chromosome-state coupling is handled elsewhere in the model.

Observed divergences:
- OC request logic is embedded inside `KarrReplicationProcess.next_update` instead of a separate request-calculator class.
- The current OC port is intentionally lighter than Karr's full 8-stage replication mechanism and defers SSB release/binding and RNAP collision details.

Audit metadata:
- `last_audited`: `2026-06-29`
- `audited_by`: `gpt-5.4-mini (codex; row authored Day-43 EOD)`
- `oc_commit_sha`: `61a5a06e8031af3159dffa436655ade330be1fd9`
