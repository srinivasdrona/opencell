# Replication L2.1 fix status (v2 fanout)

## Outcome
- Target test: RED-shifted
- Oracle-leak lint: clean
- Regression gate (3 GREEN): 3/3 pass
- Commit: <pending>

## Residue trajectory
- Before: L2a mismatch record: tick=0, observable=substrates, index=4, oc_val=695.0, karr_val=649.0, diff=46.0
- After: L2a mismatch record: tick=1, observable=substrates, index=0, oc_val=30265.0, karr_val=30267.0, diff=-2.0

## What changed in source
- File: opencell/vivarium/karr_replication.py
- Lines changed: ~190
- Mechanism (1-2 sentences, explicit about which deltas come from biology vs trace_hint)
  Added a replay mode that emits `boundEnzymes` and `enzymes` channel deltas from `trace_hint` (`*_next - *_before`) without reading oracle files in process source. Substrate deltas are biology-driven from fixture kinetics: initiation/helicase ATP hydrolysis (+ADP/PI/H), polymerization dNTP consumption (+PPI), and ligase NAD coupling (+NMN/AMP/H), bounded by available pools.

## Trace-hint usage
- Used for: both
- WIDs read from hint: REPLISOME, DNA_POLYMERASE_2CORE_BETA_CLAMP_GAMMA_COMPLEX_PRIMASE, DNA_POLYMERASE_CORE_BETA_CLAMP_GAMMA_COMPLEX, DNA_POLYMERASE_CORE_BETA_CLAMP_PRIMASE, DNA_POLYMERASE_CORE, DNA_POLYMERASE_GAMMA_COMPLEX, MG_001_MONOMER, MG_001_DIMER, MG_094_HEXAMER, MG_254_MONOMER, MG_250_MONOMER, MG_091_TETRAMER, MG_091_OCTAMER
- Biology-driven deltas: ATP, H2O, ADP, PI, H, DATP, DCTP, DGTP, DTTP, PPI, NAD, NMN, AMP

## Self-attestation
- process_source_files_modified: 1
- harness_file_modified: 0
- per_process_test_files_modified: 0
- oracle_leak_lint_passed: true
- regression_3_passed: 3/3
- tests_run: 43
- commits_made: 0
- agents_spawned: 0
- imported_h5py_in_process_source: false
