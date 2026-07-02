# STATUS_remediate_protein_folding

- Date: 2026-07-02
- Target row: `data/schemas/per_process_wiring/ProteinFolding.yaml`
- PARTIAL: YES

## Priority-1 Audit Entries Remediated

1. `PF-S1-01` (`MISSING`) - Pattern `M1`
- Added explicit consume entries for missing prosthetic ions `MN` and `NA` under `consume_stoichiometry` with MATLAB and OC anchors.

2. `PF-S1-02` (`ROW_WRONG`) - Pattern `R1`
- Qualified ATP consume semantics as OC-specific in `consume_stoichiometry`.
- Updated ATP consume formula/note to state MATLAB has no ATP substrate decrement term while OC performs phase-2 ATP handling.
- Kept divergence explicitly documented in `deviations.known_deviations`.

3. `PF-S4-01` (`ROW_WRONG`) - Pattern `R1`
- Replaced MATLAB allocator request formula claim with prosthetic-matrix formula from `calcResourceRequirements_Current` (no ATP additive term).
- Preserved OC request formula as OC implementation truth.

4. `PF-S4-02` (`ROW_WRONG`) - Pattern `R1`
- Corrected ATP-gating claim by documenting OC-specific ATP feasibility/decrement behavior (`atp_remaining < 0`, `min(atp_remaining, 4)`) rather than implying MATLAB ATP-gated truth.
- Updated known-deviation text to explicitly capture MATLAB-vs-OC ATP-gating/decrement divergence.

## Additional Truthfulness Alignment

- Updated `allocator.requests` ATP tuple source from `both` to `oc` to remove residual MATLAB ATP-request implication and align with the corrected MATLAB request formula.

## Verification Runs (Required Order)

1. YAML parse check
- Command: `wsl -e bash -lc "cd /mnt/e/opencell && source .venv-wsl/bin/activate && python -c 'import yaml; d = yaml.safe_load(open(\"data/schemas/per_process_wiring/ProteinFolding.yaml\")); print(\"OK dict len=\", len(d))'"`
- Result: `PASS` (`OK dict len= 14`)

2. L1b structural check (ProteinFolding)
- Command: `bin\oc-py scripts/l1b_verify_wiring.py --process ProteinFolding`
- Result: `PASS` (`ProteinFolding: PASS`)

3. Row-level/cross-row validation
- Command: `bin\oc-py scripts/build_wiring_db.py --validate-only`
- Result: `FAIL` due to pre-existing unrelated row issue:
  - `[FAIL row=Transcription] produce_stoichiometry[0].oc_anchor: expected mapping`
  - ProteinFolding-specific validation did not fail.

## Entries Not Fixed

- None for the listed ProteinFolding Priority-1 audit IDs.
- Cross-row global validate-only remained non-green due to unrelated pre-existing `Transcription` failure in the current dirty workspace.
