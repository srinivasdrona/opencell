# RNADecay L2.1 beat-3 status

## Outcome
- Target test: RED-shifted
- Oracle-leak AST scan: pass
- Regression 3/3 gate: 3/3
- Commit: <pending>

## Residue trajectory
- Before (beat-3 start): substrates[1] -20 @ t=0
- After: substrates[1] +1 @ t=0

## What changed in source
- File: opencell/vivarium/karr_rna_decay.py
- Lines changed: ~26
- Mechanism (2-3 sentences, biology vs trace_hint split): Kept RNADecay’s biology-first catalytic flow but tightened replay RNG handling by preserving the caller-provided seed (instead of overriding from fixture metadata) and swapping vector Poisson draws to a per-species inverse-CDF sampler that consumes one uniform per RNA row. This better aligns stochastic decay-event selection with MATLAB-style per-element sampling cadence and reduced the tick-0 substrate miss from a 20-count deficit to a 1-count surplus. No substrate/RNA delta is sourced from trace hints; all substrate deltas remain computed from fixture stoichiometry and selected decay events.

## Trace-hint usage
- Used for: none
- WIDs read from hint: none
- Biology-driven deltas: requests.H2O, rna.counts, substrates

## Self-attestation
- process_source_files_modified: 1 (must be 1)
- harness_file_modified: 0 (must be 0)
- per_process_test_files_modified: 0 (must be 0)
- oracle_leak_lint_passed: true (must be true)
- regression_3_passed: 3/3
- tests_run: 43
- commits_made: 0
- agents_spawned: 0
- imported_h5py_in_process_source: false
- copied_status_template_from_other_process: false
