# STATUS: TranscriptionalRegulation Wiring Row Remediation

Date: 2026-07-02
Process: `TranscriptionalRegulation`
Row file: `data/schemas/per_process_wiring/TranscriptionalRegulation.yaml`
Audit source: `docs/phase_f/audits/TranscriptionalRegulation_semantic_audit.md`
Status: COMPLETE

## Fixed Priority-1 audit entries

1. `TR-S4-02` (`MISSING`) - **Pattern M1**
- Added explicit MATLAB accessibility-gating claim (`isRegionPolymerized`) in the `evolveState` semantic note.
- Documented OC non-implementation in-row and in `deviations.known_deviations`.

2. `TR-S5-02` (`ROW_WRONG`) - **Pattern R1**
- Remediated projection/merge semantics by setting `deviations.shared_pool_projection_merges_compartments: true`.
- Added explicit known deviation that MATLAB keeps `tx_rate_fold_change` as `nTU x 2` (strand axis) while OC emits scalar per TU.

3. `TR-S6-01` (`ROW_WRONG`) - **Pattern R2**
- Corrected allocator attribution to MATLAB engaged-zero-request vs OC bypass in `allocator.mode` and `allocator.request_formula`.
- Removed prior "no method found" implication by anchoring MATLAB `calcResourceRequirements_Current` directly to `.m` method lines and updating notes.
- Added explicit allocator divergence line under `deviations.known_deviations`.

## Entries not fixed

- None. All Priority-1 entries listed in the audit were remediated in the row.

## Mandatory verification results

1. YAML parse:
- Command: `wsl -e bash -lc 'cd /mnt/e/opencell && source .venv-wsl/bin/activate && python -c "import yaml; d = yaml.safe_load(open(\"data/schemas/per_process_wiring/TranscriptionalRegulation.yaml\")); print(\"OK dict len=\", len(d))"'`
- Result: `OK dict len= 14`

2. L1b per-row structural verification:
- Command: `bin\oc-py scripts/l1b_verify_wiring.py --process TranscriptionalRegulation`
- Result: `PASS` for `TranscriptionalRegulation`

3. Row-level cross-row validation:
- Command: `bin\oc-py scripts/build_wiring_db.py --validate-only`
- Result: `PASS` with `0` reciprocal mismatches, `0` cyclic ordering, `0` missing rows
