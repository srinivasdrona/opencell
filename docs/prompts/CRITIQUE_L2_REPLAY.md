# CRITIQUE_L2_REPLAY — canonical 5-gate critique rubric for L2.1 replay tests

This file is the canonical template for the **external critique** step on any L2.1 per-process bit-identity replay test (`tests/vivarium/test_karr_<process>_l2_replay.py`). Pair it with `FIX_TEMPLATE_L2_REPLAY.md` (which constrains the *test*) — this file constrains the *critique that gates the test before its verdict is published*.

Default model: `gpt-5.5`. Mini-tier models tend to gloss the multi-hop reasoning in Gates 3 and 5; reserve mini for first-pass triage in large fanouts only.

## Inputs to the critique agent

The launching shell must supply:
- **Process name** (e.g., `karr_trna_aminoacylation`)
- **Worktree path** (e.g., `E:\opencell-worktrees\l2-trna-aminoacylation`)
- **Test path** (e.g., `<worktree>\tests\vivarium\test_karr_trna_aminoacylation_l2_replay.py`)
- **Production process module** (`<worktree>\opencell\vivarium\karr_<process>.py` plus `E:\opencell\opencell\vivarium\karr_<process>.py` for diff baseline)
- **Karr trace** (`E:\opencell\data\m1_sources\karr_native\per_process_traces\<Process>_100ticks.mat`)
- **Pre-run verdict** (the GREEN/RED/ERROR claim being audited, with the first-mismatch tuple if RED)

## Reference miss — what Gate 1/Gate 5 failure looks like (pilot-1 findings)

On the first three L2.1 pilots, GPT-5.5 critique caught three real misses the test-author verdict missed:

- **tRNAAminoacylation (RED)**: `_OBSERVABLES` skipped `freeRNAs` and `aminoacylatedRNAs` even though the process mutates both via `rna/counts` and `rna/aminoacylated_counts`. Gate 1 FAIL on coverage; the AMP-37 finding is real but additional RNA-side mismatches could be hiding.
- **MacromolecularComplexation (GREEN)**: `enzymes` and `boundEnzymes` were asserted as pass-through (production never touches them in the schema/topology). Those assertions never could fail and inflated apparent coverage. Gate 5 WEAK.
- **RNAModification (GREEN)**: trace had `unmodifiedRNAs` all zero, production hit early-return `if x.sum() <= 0: return {}`, so the test never exercised the flux machinery. Process was also reconstructed inside the tick loop, resetting RNG every tick. Gate 5 FAIL — verdict is "no-op replay," not GREEN.

Every critique on a new L2.1 replay test must explicitly probe for these three shapes.

## The 5 gates

### Gate 1 — Observable coverage (Rule 1)

For the process under test:

1. List every key in `states_after/` of the `.mat` file via `h5py`. Cite the python snippet.
2. List every store/key the process's `next_update` writes a delta into. Cite the line range.
3. Cross-check `_OBSERVABLES` in the test against the union. List any **missing** observables.
4. For any pass-through observable (Karr has it, OC `next_update` doesn't write it), verify the test ASSERTS it as identity-check, not silently ignores it.

**Output:**
- `states_after_keys`: [...]
- `next_update_writes`: [...]
- `_OBSERVABLES`: [...]
- `missing`: [...] (count; non-empty → Gate 1 FAIL)
- `pass_through_handled`: [...] (must be labelled in test; absent labelling → Gate 5 WEAK)

### Gate 2 — Tolerance discipline (Rule 2)

Locate the comparison assertion. Report:

- Exact code of the mismatch detection (e.g., `mismatch = diff > tol` vs `mismatch = oc != karr`).
- The tolerance expression if any (e.g., `1.0e-6 * np.maximum(1.0, np.abs(karr))`).
- The largest count value seen in this trace's `states_after` (from `h5py`-driven probe). Estimate the masked-difference upper bound at that value.

**Verdict:**
- Tolerance present AND comparison is on count observables → Gate 2 FAIL. Specify masked-difference upper bound.
- Integer-exact compare AND oracle-integrality + oc-integrality asserts present → Gate 2 PASS.
- Integer-exact compare WITHOUT integrality asserts → Gate 2 WEAK (a smuggled concentration silently passes as a 0.0-diff integer cast).

### Gate 3 — State-build vs schema (Rules 4, 7)

1. Read `process.ports_schema()` and list declared ports + sub-keys.
2. Read `_build_state` (or equivalent) in the test and list keys it populates.
3. Cross-reference. Report:
   - Ports declared but NOT populated → potential silent-zero feed.
   - Ports populated but NOT declared → wasted (test thinks it's exercising production code that's actually skipped).
4. Verify per-tick state isolation: does the test rebuild from `states_before[t]` or reuse the previous output? Cite the loop body line range.

**Verdict:**
- Any port declared-but-not-populated where production reads it → Gate 3 FAIL.
- Cumulative state across ticks (no per-tick reset from `states_before`) → Gate 3 FAIL.
- Else Gate 3 PASS.

### Gate 4 — Oracle dereference + WID order (Rule 3)

1. Locate `_cell_vector` (or equivalent HDF5 deref). Verify it handles `(100, 1)` ref arrays, dereferences once, flattens correctly. Cite lines.
2. Locate the WID-length alignment guard. If absent → Gate 4 FAIL (add per-observable runtime check against `len(process.<obs>_wids)`).
3. Note that the trace metadata typically does NOT carry WID lists, so length is the strongest cheap guard. Content alignment is asserted by Rule 1's coverage + the integer-exact match across all 100 ticks (if any indexed mismatch is consistent, content drift will surface).

**Verdict:**
- Deref correct AND length guard present → Gate 4 PASS.
- Length guard absent → Gate 4 FAIL.

### Gate 5 — Non-triviality (Rule 6) + RNG persistence (Rule 5)

1. **Early-return probe.** Grep `process.next_update` for `return {}`, `return None`, `return state` patterns. For each, identify the gate predicate. Cite line.
2. For each predicate, derive the corresponding `states_before` field. Sweep all 100 ticks of `states_before/<field>` and report how many ticks satisfy the predicate (trigger the non-trivial path).
3. If 0/100 → verdict is "no-op replay." Gate 5 FAIL. The test result is NOT GREEN; it is "L2.1 N/A — adversarial trace required."
4. **RNG persistence probe.** Locate the `KarrXProcess(...)` constructor call. Is it inside the tick loop or outside? If inside → Gate 5 FAIL (RNG reset every tick masks sequence-dependent bugs).

**Verdict:**
- ≥1 tick triggers non-trivial path AND process constructed outside loop → Gate 5 PASS.
- 0 ticks trigger → Gate 5 FAIL with "no-op verdict" classification.
- Process constructed inside loop → Gate 5 FAIL with "RNG reset per tick" classification.

## Combined verdict

The critique outputs ONE of:

- **VALID** — all 5 gates PASS. Published verdict (GREEN/RED) stands at HIGH confidence.
- **WEAK-VERDICT** — 1-2 gates WEAK, none FAIL. Verdict stands at MEDIUM confidence. List the WEAK gates and the masked-difference upper bound where relevant.
- **FALSE-GREEN-RISK** — published GREEN, ≥1 gate FAIL. The GREEN is rejected. Specify which gate(s) and what to fix per FIX_TEMPLATE_L2_REPLAY.md.
- **FALSE-RED-RISK** — published RED, the mismatch tuple is suspect (harness bug: wrong state-build, oracle deref off, WID order drift). Specify which gate(s) and what to fix.
- **BOTH** — multiple processes audited, mixed failure modes.

## Output structure

```
# L2.1 Replay Critique — <process>

## Headline verdict
VALID / WEAK-VERDICT / FALSE-GREEN-RISK / FALSE-RED-RISK

## Per-gate findings
Gate 1 (coverage): PASS / WEAK / FAIL + evidence (line-cited)
Gate 2 (tolerance): PASS / WEAK / FAIL + masked-diff upper bound
Gate 3 (state-build vs schema): PASS / WEAK / FAIL + diff
Gate 4 (oracle deref + WID guard): PASS / WEAK / FAIL
Gate 5 (non-triviality + RNG): PASS / WEAK / FAIL + trigger-tick count

## Recommended fixes
Numbered, line-cited, mapped to FIX_TEMPLATE_L2_REPLAY rule numbers.

## Confidence
HIGH / MEDIUM / LOW that the published verdict is the real verdict.
```

## How this template grows

Same closed-loop discipline as the dimer-port critique template. New false-confidence shape → add a sub-probe under the relevant gate → reference the empirical anchor (which process/pilot surfaced it) in one line. The reference-miss section above must be kept current with the latest pilot evidence.
