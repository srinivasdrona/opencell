# STATUS: Remediate Transcription ROW_WRONG/MISSING

- Status: COMPLETE
- Process row: `data/schemas/per_process_wiring/Transcription.yaml`
- Audit source: `docs/phase_f/audits/Transcription_semantic_audit.md`

## Fixed Priority-1 entries

1. `TRN-S3-02` (`ROW_WRONG`)  
   - Pattern applied: `R1` (structural entry contradicted OC behavior).  
   - Change made: corrected the `produce_stoichiometry` `PPI` entry so it no longer implies OC PPI emission.  
   - Details: replaced misleading OC framing with explicit truth statement that MATLAB emits `PPI` while current OC transcription wrappers do not; added/retained explicit divergence documentation in `deviations.known_deviations`.

2. `TRN-S5-02` (`ROW_WRONG`)  
   - Pattern applied: `R1` (structural routing claim contradicted OC behavior).  
   - Change made: updated `compartment_routing` for `H2O`, `PPI`, and `H` to `mismatch: true`.  
   - Details: notes now explicitly state MATLAB cytosolic consume/produce behavior versus current OC non-consumption/non-emission, with pointer to `known_deviations`.

## Additional deviation documentation added

- Added one explicit `known_deviations` entry documenting that MATLAB writes back `H2O-`, `PPI+`, and `H+` in Transcription substrate stoichiometry, while current OC transcription wrappers update only NTP substrate deltas.

## Unfixed entries

- None.

## Mandatory verification results

1. YAML parse check  
   - Command: `wsl -e bash -lc 'cd /mnt/e/opencell && source .venv-wsl/bin/activate && python -c "import yaml; d = yaml.safe_load(open(\"data/schemas/per_process_wiring/Transcription.yaml\")); print(\"OK dict len=\", len(d))"'`  
   - Result: `OK dict len= 14`

2. L1b structural check (Transcription)  
   - Command: `bin\oc-py scripts/l1b_verify_wiring.py --process Transcription`  
   - Result: `PASS`

3. Row-level/cross-row validation  
   - Command: `bin\oc-py scripts/build_wiring_db.py --validate-only`  
   - Result: `PASS` (no new row-level/cross-row failures)
