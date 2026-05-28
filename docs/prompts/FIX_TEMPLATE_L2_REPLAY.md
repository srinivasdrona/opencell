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
4. **Delta-integrality (anti-rounding):** every count-valued delta emitted by `next_update` MUST be integral before the harness applies it. Assert `np.array_equal(np.rint(delta), delta)` per emitted delta vector. The harness MUST NOT round, cast, floor, clip, or otherwise coerce `state_before + delta` before comparison. Without this, a non-integral 0.49-magnitude delta is silently rounded to zero by `np.rint(state_before + delta)` and the integrality assert on `oc_after` then passes vacuously.

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

### Rule 4b — Per-tick process scratch reset

Rule 4 isolates the *state dict*. It does NOT isolate mutable attributes ON THE PROCESS OBJECT itself. If `next_update` reads from `self._n_completed`, `self._request_buffer`, `self._last_flux`, or any other attribute that was written by a prior tick, the test silently couples tick `t` to tick `t-1`'s OC behaviour.

**Procedure:**
1. Grep the process module for `self\.[_a-zA-Z]+ = ` assignments inside `next_update` or any method `next_update` calls.
2. Classify each: **Karr-persistent** (the MATLAB process also carries this across ticks — keep) or **per-tick scratch** (the MATLAB process resets this — must be reset before each replay tick).
3. For per-tick scratch attributes, the test MUST reset them before each tick, either by deleting/zeroing them or by classifying them in a comment block.

If you cannot classify an attribute confidently, treat it as per-tick scratch. False reset is observable (mismatch will appear); silent carryover is the dangerous default.

## Rule 5 — Construct process once, outside tick loop (with stateless-exception)

Stateful or stochastic processes MUST be instantiated once before the tick loop and reused across all 100 ticks. The Karr `_100ticks.mat` is a single contiguous run; the process's internal RNG and any persistent counters (`_n_completed`, `_lp_solver`, cached arrays, solver warm-starts) must advance sequentially.

**Forbidden:** `process = Karr<X>Process(...)` inside `for tick in range(100):` for any process with RNG, mutable counters, or solver warm-start state. That resets internal state every tick, masking any sequence-dependent bug.

**Stateless exception:** per-tick reconstruction is allowed only if a source review of `next_update` + Rule 4b's grep + an A/B replay (run with both placements, verify identical results) prove no RNG, cache, counter, solver warm-start, or mutable attribute affects the output. The exception MUST be documented in a comment block citing the proof. Default is to construct once; the exception requires justification.

## Rule 6 — Adversarial-trace probe (non-triviality)

The test MUST verify at least one tick exercises the non-trivial path of `next_update`. If the production code has guard early-returns like `if x.sum() <= 0: return {}`, the trace MUST trigger the body at least once.

**Procedure:**
1. Inspect `next_update` AND every helper it calls on the update path. For every guard that can return `{}`, `None`, unchanged state, zero flux, or an all-zero delta vector, derive a trace predicate. Pure `grep "return {}"` on `next_update` alone is insufficient — guard returns frequently live in callees like `_compute_flux` (e.g., `if enzymes.sum() == 0: return np.zeros(...)`).
2. Sweep all 100 ticks of `states_before` and report how many ticks satisfy each predicate.
3. Additionally, assert that each **mutated** observable class (per Rule 7's split) has at least one tick with a nonzero emitted delta. If every emitted delta is identically zero across all 100 ticks, the verdict is N/A not GREEN.
4. If no tick triggers any non-trivial path, the test must be marked `pytest.skip("L2.1 no-op replay: trace does not exercise <process> non-trivial path")` and the result reported separately as "L2.1 N/A: no-op trace" — not as GREEN.

This rule exists because RNAModification's first pilot returned GREEN on a trace where `unmodifiedRNAs` was all zero, the production code hit `return {}` at line 225-226, and the test never exercised the flux machinery. The callee-graph requirement exists because a future process can hide the same early-return one frame deeper.

## Rule 7 — Real code path; pass-through provenance; no private helpers in the delta path

The test MUST invoke `process.next_update(1.0, state)` directly OR run a full Vivarium Engine update (`engine.update(1.0)`).

**Forbidden in the delta path:**
- Calling a private helper that computes deltas, mutates process state, or bypasses the public `next_update` / Engine path (e.g., `process._compute_flux(...)` returning a substrate delta the test then applies directly, skipping the LP writeback).

**Allowed:**
- Read-only **post-update** projection helpers — e.g., `process._enzyme_vector_from_split_stores(state["protein"]["counts"], state["complex"]["counts"])` to reconstruct a Karr observable vector from the post-`next_update` state. These do not compute deltas, do not mutate process state, do not bypass `next_update`. They are projections from already-updated OC state into Karr's observable order, and are permitted.

**Pass-through provenance (anti-tautology):**
- For a pass-through observable (Karr has it, `next_update` writes no delta into it), `oc_after` for that observable MUST be derived from `states_before[t]` (via the rebuilt state tree) — NEVER from `states_after[t]` or `karr_after`. A test that assigns `oc_after = karr_after.copy()` for pass-through observables and then asserts equality is a tautology, not a check. Critique Gate 1 will fail this.
- The corresponding labelling in `_OBSERVABLES` (or an adjacent `_PASS_THROUGH` set) MUST be explicit. The verdict block in the pilot/summary doc MUST split observables into two columns: "Mutated" (process writes a delta) and "Pass-through" (process declares no write; assertion is identity-check only).

**Acceptance:** a test that is GREEN only on pass-through columns is reported as ⚪ "L2.1 untested" — not GREEN.

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

## Known coverage gaps (not yet a Rule)

These bug classes can produce a false-GREEN L2.1 verdict that the current 7 rules + 5 gates do NOT mechanically catch. Tracked as known limitations; promoted to a Rule when a concrete empirical hit forces the issue.

- **K1 — Manual updater vs Vivarium deep-merge mismatch.** Rule 7 allows direct `next_update` + manual delta application. The test's `_apply_update` can quietly diverge from Vivarium's deep-merge semantics (e.g., manual code creates missing nested keys that the Engine would drop). Mitigation: prefer Engine-driven update path where practical; flag any test that uses both patterns.
- **K2 — Oracle provenance drift.** The `.mat` file's WID order, extractor commit, and MATLAB source commit are not pinned in metadata. If `extract_per_process_traces_fix.m` is updated between extractions, the trace can silently desync from the process's fixture without any test failing. Mitigation: when a trace is re-extracted, run the full L2.1 sweep and compare verdicts to the prior commit; investigate any flip.
- **K3 — `states_before` itself wrong.** If the MATLAB dumper extracted `states_before` with the wrong WID order, both input and oracle are self-consistently wrong and the test goes GREEN on a tautology. Same mitigation as K2.
- **K4 — Port-update-order sensitivity.** Direct delta application imposes an order Karr did not have. No rule validates the atomic update semantics. Mitigation: cross-check with an Engine-driven variant where applicable.
- **K5 — BLAS/NumPy environment non-determinism.** Floating-point order can differ between BLAS implementations on solver-heavy processes (LP, ODE). Mitigation: pin via `requirements.txt` + WSL `.venv-wsl` canonical environment; document in the pilot doc.
- **K6 — WID content drift inside the alignment guard.** Rule 3's length check passes when `len(process.<obs>_wids) == karr_after.shape[0]` even if the two lists are reorderings of each other with equal `states_before` values (e.g., `[A, B]` vs `[B, A]` both reading `[5, 5]`). Mitigation: when the trace exposes a WID-list dataset, assert byte-equality against `process.<obs>_wids`; absent that, treat any tick-0 mismatch on a paired/symmetric observable with suspicion.
