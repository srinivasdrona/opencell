# Fix Template — L2.1 Replay Test (per-process bit-identity)

**Status:** domain-specific rules for the L2.1 replay test class. Append to the Deliberate Action prefix when authoring or repairing an `tests/vivarium/test_karr_<process>_l2_replay.py` test. Distilled from the GPT-5.5 critique of the first three L2.1 pilots (tRNAAminoacylation RED, MacromolecularComplexation pseudo-GREEN, RNAModification no-op GREEN).

**Test class:** a pytest-based per-tick deterministic comparison. For each tick `t ∈ [0, 99)`, build OC state from Karr's `states_before[t]`, invoke `process.next_update(1.0, state)` or a full Engine update, apply the emitted deltas, then assert OC's resulting per-observable vectors are **bit-identical** to Karr's `states_after[t]`. The test produces a first-mismatch tuple `(tick, observable, index, oc_val, karr_val, diff)` or 🟢 GREEN over all 100 ticks.

**Bug class:** false-confidence GREENs caused by skipped observables, hidden float tolerance, pass-through assertions that never exercise mutated state, no-op traces that hit early-returns in production code, and tick-loop process reconstruction that resets RNG.

## Rule 1 — Observable coverage must be complete

The `_OBSERVABLES` tuple MUST list every observable the process's `next_update` emits a delta into, plus every observable Karr records in `states_after/<obs>` for this process. No early-return, no flag-gated skip, no observable absent from the tuple "because the process doesn't write to it" (those still need to be asserted as pass-through; see Rule 7).

**Procedure:**
1. Read `states_after/` keys from `<Process>_100ticks.mat` via `h5py`. List every observable.
2. Read the process's `next_update` and list every store/key it returns a delta into.
3. The union of the two lists is `_OBSERVABLES`. Anything in Karr's set but not OC's is a pass-through observable (assert it remains equal to `states_before/<obs>` for the same tick).

## Rule 2 — Integer-exact compare on count observables

Molecule counts are integer-valued in the Karr oracle. The test MUST:

1. Assert each Karr `states_after` vector is integral (`np.array_equal(np.rint(x), x)`). If non-integral, fail loud with "L2a oracle non-integral".
2. Assert each OC `oc_after` vector is integral. Same loud failure.
3. Compare with exact `np.not_equal` — no `atol`, no `rtol`, no `np.isclose`, no `pytest.approx`, no `1e-6 * max(1, abs(karr))` tolerance.

The float-tolerance pattern silently hides ~100-300 molecule diffs on large metabolite pools. The dimer-port equivalent is "silent darkness on default-zero reads"; L2.1's equivalent is "silent agreement on default-1e-6 tolerance."

Concentrations, rates, and other non-count quantities are out of scope for Rule 2 — but if they appear in `states_after`, you're probably reading the wrong field. Verify.

## Rule 3 — WID-length alignment guard

For each observable, at runtime the test MUST assert:

```python
expected_len = len(getattr(process, _OBSERVABLE_TO_WIDS_ATTR[observable]))
assert karr_after.shape[0] == expected_len, f"L2a wid-length drift: ..."
```

This catches drift between the fixture's WID order/cardinality and the trace's vector dimensionality. The trace metadata typically does NOT carry WID lists, so length-equality is the strongest cheap guard. If the fixture and oracle ever desync, the positional `oc_after[i]` vs `karr_after[i]` compare becomes silently wrong; this guard turns that into a loud failure.

## Rule 4 — Per-tick state isolation

State for tick `t` MUST be rebuilt from `states_before[t]`, NOT from OC's tick-`t-1` output. Cumulative Python drift is a separate (and harder) question than per-tick bit-identity. L2.1 measures the latter only.

**Forbidden patterns:**
- Mutating a long-lived state dict tick-over-tick and only resetting partial fields from `states_before`.
- Using `states_before[t+1]` as a surrogate for `states_after[t]` — that's a composite delta across all 28 processes, not this process's delta.

## Rule 5 — Construct process once, outside tick loop

The process MUST be instantiated once before the tick loop and reused across all 100 ticks. The Karr `_100ticks.mat` is a single contiguous run; the process's internal RNG and any persistent counters (`_n_completed`, `_lp_solver`, cached arrays) must advance sequentially.

**Forbidden:** `process = Karr<X>Process(...)` inside `for tick in range(100):`. That resets RNG and internal state every tick, masking any sequence-dependent bug.

## Rule 6 — Adversarial-trace probe (non-triviality)

The test MUST verify at least one tick exercises the non-trivial path of `next_update`. If the production code has guard early-returns like `if x.sum() <= 0: return {}`, the trace MUST trigger the body at least once.

**Procedure:**
1. Identify every early-return in `process.next_update` (grep for `return {}`, `return None`, `return state`).
2. For each, derive a "non-triviality predicate" on `states_before` (e.g., `unmodifiedRNAs.sum() > 0`).
3. Before the assertion loop, sweep all 100 ticks and assert at least one tick satisfies the predicate. If none do, the test must be marked `pytest.skip("L2.1 no-op replay: trace does not exercise <process> non-trivial path")` and the result reported separately as "L2.1 N/A: no-op trace" — not as GREEN.

This rule exists because RNAModification's first pilot returned GREEN on a trace where `unmodifiedRNAs` was all zero, the production code hit `return {}` at line 225-226, and the test never exercised the flux machinery.

## Rule 7 — Real code path; no private helpers, no pass-through inflation

The test MUST invoke `process.next_update(1.0, state)` directly OR run a full Vivarium Engine update (`engine.update(1.0)`). Forbidden:

- Calling a private helper like `process._compute_flux(...)` that bypasses the LP writeback or the public delta path.
- Constructing `oc_after` from `states_before` unchanged for an observable the test then labels GREEN. Pass-through observables must be **labeled** as such in the `_OBSERVABLES` tuple comment AND reported separately in the verdict block, because they prove nothing about the process.

**Acceptance:** the verdict in the pilot/summary doc MUST split observables into two columns: "Mutated" (process writes a delta) and "Pass-through" (process declares no write; assertion is identity-check only). A test that is GREEN only on pass-through columns is reported as ⚪ "L2.1 untested" — not GREEN.

## Acceptance criteria for "L2.1 GREEN"

Before declaring a process L2.1 GREEN:

1. `_OBSERVABLES` covers every observable in `states_after/` for this `.mat`. Cite the h5py list.
2. Tolerance is integer-exact on all count observables. Cite the assertion line.
3. WID-length guard fires on every (observable, tick). Cite the assertion.
4. State is rebuilt from `states_before` per tick. No tick-over-tick mutation.
5. Process constructed once outside the loop. Cite the line.
6. Non-triviality predicate identified, swept, and at least one tick triggers. Cite line + tick count that triggers.
7. `next_update` or Engine `update` is the entry point. Cite the line.
8. Mutated and pass-through observables split in the verdict block.

If any of 1-8 is missing, the verdict is **NOT** GREEN. Report as ⚪ "L2.1 untested — Rule N gap" instead.

## How this template grows

When a new false-confidence pattern surfaces (the way Rule 6 surfaced from the RNAModification pilot), add a Rule N here, cite the empirical anchor in one line, and reference it from the corresponding `CRITIQUE_L2_REPLAY.md` gate. Same closed-loop discipline as the dimer-port template family (`docs/prompts/FIX_TEMPLATE_DIMER_PORT.md` Rules 1-7).
