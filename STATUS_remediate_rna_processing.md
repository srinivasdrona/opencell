# STATUS: RNAProcessing wiring remediation

Date: 2026-07-02
Run: 2026-07-02 (verification rerun in this remediation pass)
Target row: `data/schemas/per_process_wiring/RNAProcessing.yaml`
Audit source: `docs/phase_f/audits/RNAProcessing_semantic_audit.md`

## Fixed Priority-1 entries

1. `RNAPROC-S4-03` (`ROW_WRONG`)  
Pattern applied: `R2` (asymmetric claim clarification)  
Changes made:
- Updated `methods.evolveState.oc.note` to explicitly state OC-only gating branches (`suppress_trna_for_rrna_tick`, first-maturation activation lag) absent in MATLAB.
- Narrowed `methods.evolveState.note` language so the row no longer implies strict formula-equivalent behavior.
- Added `deviations.known_deviations` entry documenting this OC-vs-MATLAB gating divergence.

2. `RNAPROC-S6-02` (`MISSING`)  
Pattern applied: `M1` + `R2`  
Changes made:
- Added explicit allocator-coupled timing claim in `ordering_constraints.note` with MATLAB/OC anchors and CODE_DEVIATES wording.
- Added `deviations.known_deviations` entry documenting that OC does not encode an explicit RNAProcessing-local edge proving same-tick request/grant timing equivalence.

## Entries not fixed

- None.

## Verification (mandatory sequence)

1. YAML parse:
- Command: `wsl -e bash -lc 'cd /mnt/e/opencell && source .venv-wsl/bin/activate && python -c "import yaml; d = yaml.safe_load(open(\"data/schemas/per_process_wiring/RNAProcessing.yaml\")); print(\"OK dict len=\", len(d))"'`
- Result: `OK dict len= 14`

2. L1b structural check:
- Command: `bin\\oc-py scripts/l1b_verify_wiring.py --process RNAProcessing`
- Result: `PASS (RNAProcessing)`

3. Row/cross-row validation:
- Command: `bin\\oc-py scripts/build_wiring_db.py --validate-only`
- Result: `PASS` (`0 reciprocal mismatches, 0 cyclic ordering, 0 missing rows`)

## Scope guardrails honored

- `_schema.yaml` not modified.
- OC/MATLAB code not modified.
- Existing `CODE_DEVIATES` and `VERIFIED` audit conclusions not altered.
