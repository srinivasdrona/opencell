# STATUS: CAUSE_4 classifier guard fix (require upstream mutator)

Date: 2026-06-18

## 1) Verbatim CAUSE_4 definition (authoritative spec)

From `docs/phase_f/L2_5_HARNESS_DESIGN.md` section 5 / D3:

`CAUSE_4_UPSTREAM_STATE_POLLUTION: process matches in isolated replay with identical mapped-before state but fails in composition.`

## 2) Exact lines changed (before/after)

File changed: `tests/vivarium/l2_2_replay_common_v2.py`

- Before (old behavior), at `tests/vivarium/l2_2_replay_common_v2.py:1498-1502`:
  - `isolated_matches == True` always emitted `CAUSE_4_UPSTREAM_STATE_POLLUTION`
  - `isolated_matches == False` emitted `CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE`

- After (new behavior), at `tests/vivarium/l2_2_replay_common_v2.py:1498-1508`:
  - `if isolated_matches and upstream_mutators:` emit `CAUSE_4_UPSTREAM_STATE_POLLUTION`
  - `elif isolated_matches:` emit `CAUSE_UNCLASSIFIED` and attach:
    - `reclassification.reclassified_from = "CAUSE_4_UPSTREAM_STATE_POLLUTION"`
    - `reclassification.reason = "upstream_mutators_empty"`
  - `else:` emit `CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE`

No other harness logic was refactored.

## 3) Verification runs

### Run 1 (must improve classification honesty)

Command:

`bin\oc-pytest.cmd tests/vivarium/test_l25_deterministic_stochastic_pairs.py -v -k "ChromosomeCondensation+RNAProcessing" --tb=long`

Observed:

- Test still fails (expected remnant behavior).
- Failure record now emits `cause_code: "CAUSE_UNCLASSIFIED"` (not `CAUSE_4`).
- Structured marker present:
  - `reclassification.reclassified_from = "CAUSE_4_UPSTREAM_STATE_POLLUTION"`
  - `reclassification.reason = "upstream_mutators_empty"`
- Record confirms `upstream_processes: []`.

### Run 2 (regression check)

Command:

`bin\oc-pytest.cmd tests/vivarium/test_l25_chromosome_condensation_plus_segregation.py -v`

Observed: `1 passed`.

### Run 3 (regression check)

Command:

`bin\oc-pytest.cmd tests/vivarium/test_l25_host_interaction_plus_terminal_organelle.py -v`

Observed: `1 passed`.

### Run 4 (regression check)

Command:

`bin\oc-pytest.cmd tests/vivarium/test_l2_2_translation_plus_rna_processing_v2.py -v`

Observed: `2 passed` (both subtests pass).

## 4) Reclassification result for the remnant case

For `ChromosomeCondensation+RNAProcessing` (the diagnosed remnant), the emitted code changed:

- From: `CAUSE_4_UPSTREAM_STATE_POLLUTION`
- To: `CAUSE_UNCLASSIFIED`

Reason: isolated replay matched but there were no upstream mutators for the failing observable at that step, so CAUSE_4 precondition is not satisfied by D3 definition.

## 5) Additional sweep (informational)

Command run:

`bin\oc-pytest.cmd tests/vivarium/test_l25_deterministic_stochastic_pairs.py -v --tb=no`

Observed high-level totals: `30 failed, 7 passed, 6 skipped`.

Note: `--tb=no` does not emit per-failure structured cause payloads, so CAUSE bucket totals cannot be counted from this run output alone.
