# STATUS_gap_s1

## Scope
- Task: S1 (L1b structural port) for DNASupercoiling `calcRNAPolymeraseBindingProbFoldChange` and wiring into shared `tx_rate_fold_change`.

## Changes Made
- Implemented dedicated method:
  - `opencell/vivarium/karr_dna_supercoiling.py`
  - `KarrDNASupercoilingProcess.calc_rna_polymerase_binding_prob_fold_change`
  - Faithful structural port of Karr `DNASupercoiling.m:510-543`:
    - computes per-region sigma from linking numbers
    - clamps sigma to fixture limits
    - applies linear fit via fixture slopes/intercepts
    - maps TU coordinates into ds regions and chromosome columns
- Loaded required supercoiling fold-change fixture constants (no hardcoded biology constants):
  - `foldChangeSlopes`, `foldChangeIntercepts`, `foldChangeLowerSigmaLimit`, `foldChangeUpperSigmaLimit`, `numTranscriptionUnits`, `tuIndexs`, `tuCoordinates`.
- Routed fold-change into runtime update path:
  - `next_update` now computes `tx_rate_fold_change` from current linking-number/supercoiling state each tick.
- Added DNASupercoiling output port schema for supercoiling-target TU keys under `tx_rate_fold_change`.
- Added minimal composite topology route:
  - `opencell/vivarium/karr_composite.py`
  - `karr_dna_supercoiling` now maps `tx_rate_fold_change` to shared store.
- Updated method map entry:
  - `data/karr_method_inventory/oc_method_map.yaml`
  - `processes.DNASupercoiling.runtime_methods.calcRNAPolymeraseBindingProbFoldChange`
  - `status: confirmed`
  - `oc: opencell/vivarium/karr_dna_supercoiling.py:KarrDNASupercoilingProcess.calc_rna_polymerase_binding_prob_fold_change:703`
- Also fixed shifted line anchors for existing DNASupercoiling `next_update` map entries so the completeness gate resolves this file after code insertions.
- Ancillary fix: removed broad global substrate reads in DNASupercoiling substrate delta assembly to satisfy strict-zero guard behavior.

## Verification
1. Import check (required):
- Command: `wsl -e bash -lc "cd /mnt/e/opencell && source .venv-wsl/bin/activate && python -c 'import opencell.vivarium.karr_dna_supercoiling'"`
- Result: PASS

2. L1b completeness gate (required):
- Command: `bin\oc-py scripts/l1b_method_completeness.py`
- Result: PASS
- Summary: `L1b METHOD-COMPLETENESS: PASS (115/115 runtime methods resolved)`
- DNASupercoiling row: `run 3, conf 2, inln 1, gap 0, err 0`

3. DNASupercoiling-focused tests (required command):
- Command: `bin\oc-pytest tests -q -k "supercoil or dna_supercoiling"`
- Result: PARTIAL (17 passed, 3 failed)
- Failing tests:
  - `tests/vivarium/test_karr_dna_supercoiling.py::test_100tick_steady_state_near_karr_sigma`
  - `tests/vivarium/test_l25_deterministic_stochastic_pairs.py::test_l25_deterministic_stochastic_pair_no_hints[ChromosomeCondensation+DNASupercoiling-rng_seed_0]`
  - `tests/vivarium/test_l25_deterministic_stochastic_pairs.py::test_l25_deterministic_stochastic_pair_no_hints[ChromosomeSegregation+DNASupercoiling-rng_seed_0]`
- Note: strict-zero test now passes after substrate-read guard fix.

## Success Criteria Check
- [x] `calcRNAPolymeraseBindingProbFoldChange` implemented in `karr_dna_supercoiling.py` faithful to `DNASupercoiling.m:510-543`.
- [x] `tx_rate_fold_change` produced from supercoiling state and routed to shared store.
- [x] map entry flipped `gap` -> `confirmed` with resolving anchor.
- [x] `scripts/l1b_method_completeness.py` prints PASS.
- [ ] DNASupercoiling tests pass (`-k "supercoil or dna_supercoiling"` has 3 failures listed above).
- [ ] committed (pending commit step).
