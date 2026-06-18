# STATUS: CAUSE_4 remnant diagnosis (Cond + RNAProcessing)

## 1) Verbatim CAUSE_4 definition (D3)

```
CAUSE_4_UPSTREAM_STATE_POLLUTION: process matches in isolated replay
with identical mapped-before state but fails in composition.
```

## 2) Tick-0 forensic table (probe: Condensation -> RNAProcessing)

Source command:
`bin\oc-py.cmd _probe_cause4_cond_rnaproc.py`

| Checkpoint | Evidence |
| --- | --- |
| Composition order used in probe | `['ChromosomeCondensation', 'RNAProcessing']` |
| Owner for shared `substrates` at tick 0 | `ChromosomeCondensation` |
| `H2O` before Condensation | `756718` |
| Condensation `H2O` update delta | `-3` |
| `H2O` after Condensation | `756715` |
| Karr Condensation `H2O` delta (tick 0) | `756718 -> 756715` (`-3`) |
| `H2O` before RNA overlay | `756715` |
| Harness overlays before RNAProcessing? | `Yes` (`overlay_applied_to_substrates=True`) |
| Overlay source for RNA `H2O` | RNA trace-before has `0`, but overlay preserved running value `756715` because `H2O` is in mutated shared indices |
| `H2O` after RNA pre-step overlay | `756715` (unchanged from post-Cond) |
| RNAProcessing `H2O` update delta at tick 0 | `0` |
| `H2O` after RNAProcessing | `756715` |
| Karr RNAProcessing expected `H2O` delta (tick 0) | `0 -> 0` (`0`) |
| Counterfactual RNA `H2O` delta (tick 0) | `0` |

Tick-0 conclusion: no pre-RNA overwrite bug and no RNAProcessing process-level `H2O` delta bug on this tick.

## 3) Verdict classification

Verdict: **(c) classifier issue**.

Why:
- The tick-0 forensic path shows correct Condensation write, correct preserved baseline before RNAProcessing, and correct RNAProcessing delta vs Karr.
- The currently failing DS test case (`bin\oc-pytest.cmd tests/vivarium/test_l25_deterministic_stochastic_pairs.py -v -k "ChromosomeCondensation+RNAProcessing" --tb=long`) emits a CAUSE_4 record at **tick 5** with:
  - `composition_order=["RNAProcessing","ChromosomeCondensation"]`
  - `upstream_processes=[]`
  - `isolated_replay_result="matches_oracle"`

`CAUSE_4_UPSTREAM_STATE_POLLUTION` is logically incompatible with `upstream_processes=[]` for that failing step. This is a classifier emission issue, not the tick-0 Cond->RNA overlay path.

## 4) Why `f55c34a` + `c37fdc7` did not catch this remnant

- `f55c34a` (H5) fixed counterfactual/composition hint-policy equivalence.
- `c37fdc7` (H6) fixed shared-WID pre-step overlay wipeout by preserving upstream-mutated indices.

Those fixes target cases where a downstream step can actually be contaminated by upstream step effects. In the observed remnant failure record, the failing step has `upstream_processes=[]` (RNAProcessing executes first in canonical composition order), so H5/H6 are not the gating defect for that emitted CAUSE_4.

## 5) Specific fix path

1. Tighten CAUSE_4 emission preconditions in `run_integrated_replay_v2`:
   - Only allow `CAUSE_4_UPSTREAM_STATE_POLLUTION` when there is at least one upstream mutator for that observable at that step (`upstream_mutators` non-empty / `compare_mode == "delta"`).
2. If isolated replay matches but no upstream mutator exists, do not emit CAUSE_4:
   - classify as non-CAUSE_4 (e.g., `CAUSE_5`/`CAUSE_UNCLASSIFIED` pending desired taxonomy), with explicit diagnostic note that no upstream mutator exists.
3. Add regression guard:
   - targeted assertion that CAUSE_4 cannot be emitted when `upstream_processes=[]`.

## Verification commands run

- `bin\oc-py.cmd _probe_cause4_cond_rnaproc.py`
- `bin\oc-pytest.cmd tests/vivarium/test_l25_deterministic_stochastic_pairs.py -v -k "ChromosomeCondensation+RNAProcessing" --tb=long`
- `bin\oc-pytest.cmd tests/vivarium/test_karr_rna_processing_l2_replay.py -v`
