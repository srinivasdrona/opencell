# STATUS_h8_diagnosis

## Beat 1
REJECT: the "double-counting under composition delta arithmetic" hypothesis is not supported by the probe data.

## Beat 2
### (a) Operator empirical finding (VERBATIM)

Day-33 morning canary fixed DNASupercoiling no-hints branch (commit `250b777`). The fix achieved tick-0 bit-identity in **isolated** replay:

```
=== DNASupercoiling tick-0 full-channel deep probe (no-hints isolated) [POST-CANARY] ===
--- substrates  (5 wids) ---
  karr sum:  before=9081531  after=9081591  delta=+60
  oc   sum:  before=9081531  after=9081591    delta=+60  (was 9081587 / +56 pre-canary)
  total |diff| = 0  (was 20 pre-canary)
--- enzymes  (3 wids) ---
  total |diff| = 0  (was 3 pre-canary)
--- boundEnzymes  (3 wids) ---
  total |diff| = 0  (was 3 pre-canary)
```

L2.1 stays green. But L2.5 pair `ChromosomeCondensation+DNASupercoiling` now fails differently:

```
cause=CAUSE_4_UPSTREAM_STATE_POLLUTION
observable=substrates  wid=ATP
oc_compare=-4   karr_compare=-60   diff=+56
compare_mode=delta
upstream_processes=['ChromosomeCondensation']
```

The harness reports OC's "compare delta" as `-4`, oracle's as `-60`. But the **isolated** probe shows OC emits a delta of `-60` (matching Karr exactly). So the `-4` is a composition-mode artifact, not an OC emission bug.

### (b) Harness `compare_mode=delta` arithmetic branch (exact code)

From `tests/vivarium/l2_2_replay_common_v2.py`:

```python
compare_mode = "delta" if upstream_mutators else "absolute"
if compare_mode == "delta":
    oc_compare = oc_after_step - oc_before_step[obs]
    karr_compare = karr_after - before_vectors[name][obs]
else:
    oc_compare = oc_after_step
    karr_compare = karr_after
```

## Beat 3
Created probe script: `scripts/probe_h8_composition_delta.py`.

What it does:
1. Runs the exact failing pair (`ChromosomeCondensation+DNASupercoiling`, `disable_trace_hints=True`) and parses the structured failure record.
2. Verifies the failing observable from the record is `substrates` before continuing.
3. Replays tick-0 composition path with harness primitives, captures:
   - `oc_states_before_step` for DNASupercoiling (post-upstream, pre-step),
   - DNASupercoiling emitted substrate deltas from `update["substrates"]`,
   - `oc_states_after_step`,
   - counterfactual isolated vector and compare vector.
4. Prints the per-WID table for ATP/ADP/PI/H2O/H and a PASS/FAIL hypothesis line plus classification `(a|b|c)`.

## Beat 4 — Pre-mortem (INVERSION)
1. Probe might miss the actual bug if `compare_mode` differs per observable (`substrates` vs `enzymes` vs `boundEnzymes`). I first parse the actual failing record and confirm the failing observable is `substrates` before probing only that surface.
2. Probe might confuse "delta" mode arithmetic with "absolute" mode arithmetic. I read and quote the exact `compare_mode` branch from `run_integrated_replay_v2` before interpreting numbers.
3. Probe might conflate harness arithmetic with OC emit behavior. The probe explicitly checks whether `oc_states_after_step - oc_states_before_step` equals `oc_compare`, and whether emitted DNASupercoiling substrate deltas are `-4/+4` (composition) versus `-60/+60` (counterfactual isolated replay).

## Beat 5 — Verification result
`scripts/probe_h8_composition_delta.py` produced:
- `record_oc_compare_matches_replay=True`
- `record_karr_compare_matches_replay=True`
- `HYPOTHESIS_H8_RESULT=FAIL`
- `VERDICT_CLASSIFICATION=b`

Interpretation:
- Harness arithmetic is exactly what code says (`oc_compare = oc_after_step - oc_before_step`).
- In this pair at tick 0, DNASupercoiling's actual composition-step emit on shared substrates is `-4/+4`, not `-60/+60`.
- Therefore this failure is not explained by "delta arithmetic double-counting"; it is explained by composition-state/allocator-mediated OC behavior for DNASupercoiling under upstream-mutated baseline.

## Probe-finding table
Captured from `scripts/probe_h8_composition_delta.py`:

| wid | karr_states_before | karr_states_after | karr_compare | oc_states_before_tick_start | oc_states_before_step | oc_emitted_delta_dnasc | oc_states_after_step | oc_compare | oc_counterfactual_after | oc_counterfactual_compare |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ATP | 907 | 847 | -60 | 907 | 72 | -4 | 68 | -4 | 847 | -60 |
| ADP | 0 | 60 | 60 | 0 | 3 | 4 | 7 | 4 | 60 | 60 |
| PI | 0 | 60 | 60 | 0 | 3 | 4 | 7 | 4 | 60 | 60 |
| H2O | 9080624 | 9080564 | -60 | 9080624 | 756715 | -4 | 756711 | -4 | 9080564 | -60 |
| H | 0 | 60 | 60 | 0 | 3 | 4 | 7 | 4 | 60 | 60 |

## Verdict
H8 REJECTED.

Exact bug indicated by evidence: DNASupercoiling no-hints behavior under composition (allocator-mediated) is producing a `-4/+4` substrate step delta from the post-upstream pre-step state, while its isolated replay remains `-60/+60`; the harness `compare_mode=delta` arithmetic branch itself is behaving exactly as implemented.

## Spec quote
`docs/phase_f/L2_5_HARNESS_DESIGN.md` exists, but no `compare_mode` delta-vs-absolute arithmetic spec was found there for this case.

Spec doc missing for this arithmetic detail — only code currently defines behavior.

## Fix sketch (≤1 paragraph)
No arithmetic change is justified by this probe: the delta branch in `tests/vivarium/l2_2_replay_common_v2.py:1402-1405` matches observed `oc_compare` exactly. The smallest correction path is to address the composition-specific no-hints DNASupercoiling behavior under upstream-mutated substrate baseline (allocator-mediated step behavior) while preserving isolated canary behavior; after that, re-run this probe and the pair pytest to verify composition step deltas return to oracle-aligned `-60/+60`.
