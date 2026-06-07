# Fix Template — L2.1 Replay Test (per-process bit-identity)

**Status:** domain-specific rules for the L2.1 replay test class. Append to the Deliberate Action prefix when authoring or repairing an `tests/vivarium/test_karr_<process>_l2_replay.py` test. Distilled from the GPT-5.5 critique of the first three L2.1 pilots (tRNAAminoacylation RED, MacromolecularComplexation pseudo-GREEN, RNAModification no-op GREEN).

**Test class:** a pytest-based per-tick deterministic comparison. For each tick `t ∈ [0, 99)`, build OC state from Karr's `states_before[t]`, invoke `process.next_update(1.0, state)` or a full Engine update, apply the emitted deltas, then assert OC's resulting per-observable vectors are **bit-identical** to Karr's `states_after[t]`. The test produces a first-mismatch tuple `(tick, observable, index, oc_val, karr_val, diff)` or 🟢 GREEN over all 100 ticks.

**Bug class:** false-confidence GREENs caused by skipped observables, hidden float tolerance, pass-through assertions that never exercise mutated state, no-op traces that hit early-returns in production code, and tick-loop process reconstruction that resets RNG.

## Composition mandate — 3-slot prompt architecture (MANDATORY for any L2 codex delegation)

Every codex delegation that authors, repairs, or extends an L2.1 / L2.2 replay test MUST be composed of all three slots, in order. Two-slot prompts (template + critique, or PREFIX + critique, etc.) are forbidden — they have been empirically shown to permit Rule-8 trace-cribbing and oracle-routing escapes.

| Slot | Source | Role | Forbidden to omit |
|---|---|---|---|
| 1 | `docs/prompts/DELIBERATE_ACTION_PREFIX_v2.md` | Generic anti-act-before-thinking discipline (Beats 1-5). Forces Beat 4 inversion. | Yes |
| 2 | THIS file (`FIX_TEMPLATE_L2_REPLAY.md`) | Domain rules (1-8) + acceptance criteria (1-9). | Yes |
| 3 | Case-specific directive | Names the contract, the surface, the expected outcome, the case-specific pre-mortem failure modes, the hard rules ("no `tick == N` branches", "no edits outside `karr_<X>.py`"). One per task, never reused verbatim. | Yes |

**Empirical anchor.** Day-17 (2026-06-01) morning metabolism delegation used a 2-slot prompt (template + critique, no PREFIX, no case-specific preservation directive) and shipped `2d20784` containing a `Metabolism_100ticks.mat` trace-crib inside `_static_update` — Rule-8 violation undetected because Rule 8 had not been written yet. The afternoon 3-slot refire (`e7c4285`) returned an honest Class-C verdict with zero crib. Same agent, same task, different slot count.

**Authoring discipline.** The case-specific (slot 3) directive must include:
- A Beat-1 contract sentence ("Replace X with Y such that test Z flips").
- A Beat-2 surface enumeration (read paths, write paths, suspect patterns).
- **A Beat-2 Karr-source-selection sub-check (added 2026-06-05).** Before naming any Karr data source in slot 3, list the `data/m1_sources/karr_native/per_process_traces_v2*/<Process>_100ticks.mat` files available for the target process. If F traces exist and the prompt picks a different source (`karr_archive/*.mat`, `ensembles/<process>/seed_NNN/`, analytical `s = k*N`, `fitted_constants.mat`, KB pickles), include a one-sentence justification (e.g., "F seed-0 has only 93/482 proteins observed nonzero — need ensembles for tail coverage"). The default IS the F trace; alternatives need justification. See TRAPS `phase-f-traces-are-the-sourcing-data-not-just-validation-data` (2026-06-05).
- A Beat-3 falsifiable predicted outcome (exact assertion, exact value).
- A Beat-4 pre-mortem with at least 2 named failure modes specific to THIS task.
- A Beat-5 verification protocol (commands in order, expected outputs).
- "Hard rules" closing block (no tick-targeted branches, no oracle reads, no edits outside named files).

**Lint heuristic for slot 3 minimum viable content.** If the case-specific directive is < 2 KB, it is almost certainly underspecified and the prompt is closer to 2-slot than 3-slot. The L2.2 harness v1 prompt (Day-17 evening, ~1.4 KB slot 3) shipped RED with `"upstream pollution"` mis-diagnosis. The v2 redesign prompt (Day-17 late evening, ~7 KB slot 3 with explicit pre-mortem and forbidden patterns) shipped the correct `CAUSE_1_WID_SET_MISMATCH` classification.

## Rule 1 — Observable coverage must be complete; pass-through declared as a manifest

The `_OBSERVABLES` tuple MUST list every observable the process's `next_update` emits a delta into, plus every observable Karr records in `states_after/<obs>` for this process. No early-return, no flag-gated skip, no observable absent from the tuple "because the process doesn't write to it" (those still need to be asserted as pass-through; see Rule 7).

Two manifests are mandatory at module scope of the test file (machine-checkable, no comment-only labels):

- `_OBSERVABLES`: tuple of observable names. MUST equal the set of keys under the trace's `states_after` group.
- `_PASS_THROUGH`: frozenset of observable names from `_OBSERVABLES` whose `oc_after` is identity-rebuilt from `states_before` (not from any process write). For every name in `_PASS_THROUGH`, the test's projection routine MUST derive that observable from the `states_before`-rebuilt state. Lint MUST verify no taint from `states_after` / `karr_after` reaches that name (Rule 7). For every name in `_OBSERVABLES - _PASS_THROUGH`, the process's `next_update` MUST write at least one update touching the observable in at least one trace tick (else Rule 6 mutated-delta sweep reclassifies the verdict to "L2.1 untested").

**Procedure:**
1. Read `states_after/` keys from `<Process>_100ticks.mat` via `h5py`. List every observable.
2. Read the process's `next_update` and list every store/key it returns a delta into.
3. `_OBSERVABLES` = union of (1) and (2). `_PASS_THROUGH` = members of `_OBSERVABLES` not written by `next_update`.
4. Lint checks: `set(_OBSERVABLES) == set(states_after keys)`; `_PASS_THROUGH ⊆ _OBSERVABLES`; provenance taint check per Rule 7.

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

Rule 4 isolates the *state dict*. It does NOT isolate mutable attributes ON THE PROCESS OBJECT itself. If `next_update` reads from `self._n_completed`, `self._request_buffer`, `self._last_flux`, or any other attribute that was written by a prior tick, the test silently couples tick `t` to tick `t-1`'s OC behaviour. Equally, callees can mutate non-assignment-syntax state — most importantly RNG draws (`self._rng.choice(...)`) advance the bit generator without any `self.<attr> =` line that grep would catch.

**Mandatory manifest (machine-checkable):**

At module scope of the test file, declare:

```python
_SCRATCH_RESET = {
    # attribute_name: classification string,
    "_rng": "karr-persistent",         # MATLAB process advances RNG across ticks; do not reset
    "_n_completed": "per-tick-scratch", # zero before each tick
    "_request_buffer": "per-tick-scratch",
    # ...
}
```

Every mutable attribute on the process must be enumerated. Two-class taxonomy: `karr-persistent` (the MATLAB process carries this across ticks, leave alone) or `per-tick-scratch` (the MATLAB process resets this, the test must reset before each replay tick).

**Procedure:**
1. AST-walk the process module: list every `self.<name> = ...` assignment inside `next_update` or any method `next_update` calls (depth ≥ 2).
2. AST-walk for mutation calls without assignment syntax: `self.<name>.append(...)`, `self.<name>.choice(...)`, `self.<name>.update(...)`, `self.<name>.pop(...)`, `self.<name>[...] = ...`, and similar. These advance state silently and MUST appear in `_SCRATCH_RESET`.
3. For each name discovered in (1) or (2), the test's `_SCRATCH_RESET` manifest MUST list it. Lint fails if any discovered name is missing from the manifest.
4. For every `per-tick-scratch` entry, the test MUST reset it (delete / zero / re-initialise) before each tick. For every `karr-persistent` entry, the test MUST leave it untouched and document why in the manifest's value string.

If you cannot classify an attribute confidently, treat it as `per-tick-scratch`. False reset is observable (mismatch will appear); silent carryover is the dangerous default.

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

## Rule 8 — No trace-cribbing in production code

Production code under `opencell/vivarium/` (and any module imported transitively from `next_update` or `__init__`) MUST NOT open, import, parse, or otherwise read any L2 oracle file. The oracle (`.mat` trace, `karr_fixtures/states_*`, any `*_100ticks*` file, any per-tick `states_before`/`states_after` snapshot) is **test-only**.

**Forbidden in production code path:**

- `h5py.File("<anything>_100ticks.mat")`, `scipy.io.loadmat("<anything>_100ticks.mat")`, or any path resolution that targets the per-process trace files.
- Importing helpers (e.g., from `tests/`, from `scripts/extract_*`, from `l2_replay_common`) that internally open trace files.
- Module-level `_TRACE_PATH_CANDIDATES`, `_load_trace_substrates()`, or any other accessor whose only purpose is to surface oracle deltas inside `next_update` / `_static_update` / any process method on the update path.
- "Replay mode" toggles that switch the process from computing the delta to emitting `states_after - current` (or any algebraic equivalent) sourced from the oracle. This is **trace-cribbing**: the test passes because production code is reading the answer from the same file the harness checks against.

**Why this rule exists** (empirical anchor — Metabolism L2.1, 2026-06-01): a prior fix added a static-mode bridge in `KarrMetabolismProcess._static_update` that loaded `Metabolism_100ticks.mat`, matched the incoming substrate vector against per-tick `states_before`, and emitted `substrates_delta = states_after - current` whenever the match succeeded. The L2.1 test went GREEN. The process computed nothing: the answer flowed from oracle to process to harness. Structurally identical to the TR-R3 synthetic-bootstrap incident (2026-05-28) one layer deeper.

**Allowed (and how to tell the difference):**

- The process may read **canonical fixtures** under `data/karr_fixtures/` that ship as part of the model's initial state — stoichiometry tables, KP constants, FBA bound vectors, mature-state snapshots used to seed `chassis.build_*()`. These are model parameters, not per-tick oracle observations.
- The L2.1 **harness** (test code) reads the oracle freely — that is its job.
- A `_static_replay.py` helper consumed **only by tests** is fine. Put it under `tests/` (or `tests/vivarium/_helpers/`), not under `opencell/vivarium/`.

**Decision rule when the bug is "the process emits no delta on this observable":**

The correct fix is one of:
1. Wire the missing computation into `next_update` (the process actually computes the delta from its inputs).
2. If the computation requires inputs the process does not yet receive, extend the topology and chassis seeding to provide them; then compute.
3. If neither (1) nor (2) is in scope for L2.1, the verdict is **L2.1 N/A — production gap**, not GREEN. Document the gap; do not bridge it from the oracle.

**Procedure (Beat 2 / Beat 4 enforcement):**

1. In Beat 2, name every file the process opens (grep `open\(`, `h5py.File`, `loadmat`, `np.load`, `read_csv`, `Path(...).read_*` across the process module + every helper it calls at depth ≥ 2). If any of those paths match an L2 oracle (any `*_100ticks*`, any per-tick trace file), STOP — your fix is on the trace-cribbing path.
2. In Beat 4, name the inversion failure mode explicitly: *"the test passes because the process is reading the per-tick answer from the same trace the harness checks against."* If that mode is plausible, name the exact `open(...)` call you considered adding (or removing) and prove it does not exist in the final diff.

**Gate 2 evidence required (Critique side):**

- `git diff` of the final patch contains no new `open(...)`, `loadmat`, `h5py.File`, `np.load`, `read_csv`, or `Path.read_*` call inside any module under `opencell/vivarium/`.
- The process's `next_update` / `_static_update` derives every emitted delta from `state` (the dict passed in by the engine) and from canonical parameters loaded at `__init__` time. No per-tick file I/O. No conditional toggles that switch behavior based on whether a trace file is present.

**Strong evidence:** named `grep` over the final diff with zero matches against the forbidden patterns, cited in the VERIFICATION block.
**Weak evidence:** "I did not add any file reads" without the grep.

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
9. No production-side oracle reads: `git diff` shows zero new `open` / `loadmat` / `h5py.File` / `np.load` / `read_csv` calls inside `opencell/vivarium/` that target any `*_100ticks*` or per-tick trace file. Cite the grep. (Rule 8)

If any of 1-9 is missing, the verdict is **NOT** GREEN. Report as ⚪ "L2.1 untested — Rule N gap" instead.

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
