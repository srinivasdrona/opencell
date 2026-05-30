# ChromosomeCondensation L2.1 fix status (v2 fanout)

## Outcome
- Target test: GREEN
- Oracle-leak lint: clean
- Regression gate (3 GREEN): 3/3 pass
- Commit: <pending>

## Residue trajectory
- Before: L2a mismatch record: tick=0, observable=enzymes, index=1, oc_val=3.0, karr_val=0.0, diff=3.0
- After: GREEN (no mismatch)

## What changed in source
- File: opencell/vivarium/karr_chromosome_condensation.py
- Lines changed: ~85
- Mechanism (1-2 sentences, explicit about which deltas come from biology vs trace_hint)
  Replaced the aggregate replay path in `next_update` with Karr-style per-tick count bookkeeping: free `SMC_ADP` is deterministically dissociated each tick, ATP/H2O hydrolysis and PI/H production are emitted from the resulting binding event count, and free-enzyme deltas are computed from those biology rules. The stochastic binding/release component is sourced from `state["trace_hint"]["boundEnzymes_next"]` and emitted only on `boundEnzymes`.

## Trace-hint usage
- Used for: boundEnzymes_next
- WIDs read from hint: MG_213_214_298_6MER, MG_213_214_298_6MER_ADP
- Biology-driven deltas: enzymes (MG_213_214_298_6MER, MG_213_214_298_6MER_ADP), substrates (ATP, H2O, ADP, PI, H)

## Self-attestation
- process_source_files_modified: 1
- harness_file_modified: 0
- per_process_test_files_modified: 0
- oracle_leak_lint_passed: true
- regression_3_passed: 3/3
- tests_run: 41
- commits_made: 0
- agents_spawned: 0
- imported_h5py_in_process_source: true   # legacy allowlisted init-time trace anchor read
