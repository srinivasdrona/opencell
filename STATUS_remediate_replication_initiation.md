# STATUS: ReplicationInitiation Wiring Remediation

- Task: Remediate Priority-1 `ROW_WRONG` / `MISSING` findings for `data/schemas/per_process_wiring/ReplicationInitiation.yaml`
- Process: `ReplicationInitiation`
- Source audit: `docs/phase_f/audits/ReplicationInitiation_semantic_audit.md`
- PARTIAL: YES (global validate-only check has pre-existing unrelated failure in `ChromosomeCondensation`)

## Fixed Audit Entries

1. `RI-S3-02` (`ROW_WRONG`) — **Pattern R1**
- Changed `produce_stoichiometry` `ADP` MATLAB attribution from hydrolysis to reactivation.
- Updated MATLAB anchor to `ReplicationInitiation.m:865-883` with ATP->ADP reactivation note.
- Kept OC hydrolysis anchor (`karr_replication_initiation.py:774-777`) and added explicit asymmetry note.
- Added corresponding `known_deviations` entry documenting MATLAB reactivation vs OC hydrolysis coupling.

2. `RI-S4-02` (`ROW_WRONG`) — **Pattern R1**
- Updated `consume_stoichiometry` `H2O` formula text to explicitly represent MATLAB polymer-indexed demand vs OC free-pool event-sampling family.
- Added explicit entry note marking asymmetry (`CODE_DEVIATES`) and corresponding `known_deviations` line.

3. `RI-S4-03` (`MISSING`) — **Pattern M1**
- Added missing explicit reactivation substrate consume claim as a dedicated `consume_stoichiometry` `ATP` entry:
  - MATLAB anchor `ReplicationInitiation.m:865-883`
  - OC anchor `karr_replication_initiation.py:923-938` with explicit "no ATP substrate decrement" note.
- Added/updated notes so row now states MATLAB reactivation `ATP -> ADP` substrate transform and OC divergence.

## Verification

1. YAML parse
- Command: `wsl -e bash -lc "cd /mnt/e/opencell && source .venv-wsl/bin/activate && python ..."`
- Result: `OK dict len= 14`

2. L1b row verification
- Command: `bin\oc-py scripts/l1b_verify_wiring.py --process ReplicationInitiation`
- Result: `PASS` for `ReplicationInitiation`

3. Cross-row validate-only
- Command: `bin\oc-py scripts/build_wiring_db.py --validate-only`
- Result: `FAIL` due pre-existing unrelated row:
  - `ChromosomeCondensation: source_anchors.matlab_blocks.simulation_ordering: lines must match start-end`
- `ReplicationInitiation` no longer appears in validate-only failures.

## Unfixed Priority-1 Entries

- None.
