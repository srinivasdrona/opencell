# Task: 3-slot diagnostic on CAUSE_5 — is it a real bug or oracle artifact?

## SLOT 1 — DELIBERATE ACTION PREFIX

You are operating under the Deliberate Action discipline defined in
`docs/prompts/DELIBERATE_ACTION_PREFIX_v2.md`. Apply Beats 1–5 as a
structural constraint, not as a checklist:

**Beat 1 (contract)**: state in one sentence what success looks like, in
terms of an observation an outside party could verify (e.g., "the next
turn will show a screen where X is true"). No verb-only sentences ("I
will investigate"); they are not contracts.

**Beat 2 (surface)**: enumerate the read paths, the write paths, and the
"suspect patterns" you need to confirm or refute. For each suspect
pattern, list the file:line you will read to confirm/refute.

**Beat 3 (falsifiable prediction)**: state the assertion you expect to
prove, with an exact value if possible (e.g., "Metabolism's ADP delta in
isolation tick 0 = +X; in composition tick 0 after Condensation runs =
+X + 3 because Condensation produced 3 ADP upstream"). If the prediction
fails, the hypothesis is wrong and a different root cause is at play —
say what.

**Beat 4 (pre-mortem)**: name at least 3 plausible "looks right, is wrong"
failure modes specific to THIS task. Examples for this delegation:
- "Hypothesis confirms but only because of a coincidence at tick 0; the
  pattern doesn't hold at tick 5, 10, etc."
- "The classifier is right; CAUSE_5 truly is a process intrinsic bug for
  THIS pair (and other pairs that look CAUSE_5 are different issues)"
- "The classifier is right for THIS pair but wrong for a different pair
  reported as CAUSE_5; one-pair investigation doesn't generalize"
- "The harness state-isolation is broken in a different way than the
  hypothesis posits"

**Beat 5 (verification protocol)**: list the exact commands and expected
outputs that prove or disprove the contract. Include the file paths and
the script structure for any probe script you author.

The output must show all 5 beats in order before any code is touched.

---

## SLOT 2 — DOMAIN TEMPLATE (L2.5 COMPOSITION INVESTIGATION)

This delegation is a DIAGNOSIS, not a fix. Domain rules:

**Authoritative spec doc:** `docs/phase_f/L2_5_ACCEPTANCE_RUBRIC.md` and
`docs/phase_f/L2_5_HARNESS_DESIGN.md` (CAUSE_1-7 taxonomy definitions).
Quote the relevant CAUSE_5 definition verbatim in your slot-3 output
before any analysis (per COMPOSITION_MANDATE v2 spec-authority rule).

**Karr-fidelity rule:** for any claim about what a process "should" do at
tick N, anchor to the actual Karr trace at
`data/m1_sources/karr_native/per_process_traces_v2_s000/<Process>_100ticks.mat`
(`states_before`, `states_after`). Do NOT compute "should" from your own
reading of the algorithm without checking the trace.

**Multi-trace rule (added for this task):** at L2.5, the comparison
baseline is ambiguous. Both processes have L2.1 traces recorded in
isolation. A diverged value in composition could be:
- (a) The composed process is wrong — real bug
- (b) The composed process is right; the L2.1 trace is the wrong baseline
  because composition changes the inputs
- (c) The harness is classifying the wrong type of mismatch
For each finding, distinguish (a), (b), (c) explicitly.

**Read-set discipline:** maximum 5 files in your read-set for this task.
If you need a 6th, document why in STATUS and proceed; do not silently
expand.

**Write-set discipline:** READ ONLY for opencell/, tests/, data/. Only
write to:
- `docs/phase_f/STATUS_cause5_diagnosis.md`
- A temporary probe script `_probe_cause5_<pair>.py` (delete before final
  commit, but it MAY exist during the session)

**Acceptance criteria:** STATUS doc must contain:
1. Verbatim quotation of CAUSE_5 definition from the harness design doc
2. Tick-0 forensic table: per shared substrate WID, list (Karr value in
   Condensation's L2.1, Karr value in Metabolism's L2.1, value seen by
   Metabolism in composition, what the test asserted vs)
3. Verdict: (a) real bug, (b) wrong baseline, or (c) classifier issue
4. If (a): the specific fix path (which process file, which line, what
   change)
5. If (b) or (c): the specific harness-level fix proposal (which file,
   which classifier function, what change)
6. Generalizability: does this verdict hold for the other 15 CAUSE_5
   pairs, or is this case-specific? Justify based on the WID pattern
   (all CAUSE_5 first-WID are ATP/ADP/AMP/GTP — energy currency)

---

## SLOT 3 — CASE-SPECIFIC DIRECTIVE

### Catalog entry (authoritative spec) — CAUSE_5 definition

From `docs/phase_f/L2_5_HARNESS_DESIGN.md` section 5 (D3):

```
CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE: process fails in isolated
replay against own trace.
```

The diagnostic procedure (per D3): isolated counterfactual replay should
match the process's own L2.1 oracle. If it does NOT match, the process
has an intrinsic bug. If it DOES match but composition diverges, the
classifier should NOT have emitted CAUSE_5.

### Beat-1 contract (sample, refine in your output)

"Determine whether the CAUSE_5 emitted for `ChromosomeCondensation +
Metabolism` at tick 0 (first WID = ADP) is (a) Metabolism has a real
intrinsic bug exposed only in composition, (b) Metabolism is computing
correctly but the L2.1 oracle is the wrong baseline because upstream
Condensation legitimately modified shared substrates, or (c) the harness
is misclassifying a CAUSE_4-style harness bug as CAUSE_5."

### Beat-2 surface

**Read-set (5 files maximum):**
- `tests/vivarium/l2_2_replay_common_v2.py` — the harness, look at how
  CAUSE_5 is emitted (search for `CAUSE_5_INTRINSIC` references) and the
  counterfactual diagnostic path (`_build_counterfactual_step_vector`)
- `data/m1_sources/karr_native/per_process_traces_v2_s000/ChromosomeCondensation_100ticks.mat`
  — Condensation's L2.1 oracle
- `data/m1_sources/karr_native/per_process_traces_v2_s000/Metabolism_100ticks.mat`
  — Metabolism's L2.1 oracle
- `opencell/vivarium/karr_chromosome_condensation.py` — the deterministic
  process (check what it actually writes to ADP)
- `opencell/vivarium/karr_metabolism.py` — the stochastic process under
  test (check what it does with ADP input)

### Beat-2 probe script structure

Author `_probe_cause5_cond_metab.py` that does the following:

1. Load both processes' tick-0 `states_before` and `states_after` for ADP
   from the L2.1 traces
2. Print:
   - `Condensation_L1: states_before[ADP] = ?, states_after[ADP] = ?, delta = ?`
   - `Metabolism_L1: states_before[ADP] = ?, states_after[ADP] = ?, delta = ?`
3. Now simulate the COMPOSITION as the harness does:
   - Reset shared state to Condensation's `states_before` at tick 0
   - Run Condensation's `next_update`
   - Capture the post-Condensation ADP value
   - Now run Metabolism's `next_update` against this post-Condensation state
   - Print: `Metabolism_composed: states_after[ADP] = ?`
4. Compute and print:
   - What the harness ASSERTED Metabolism's ADP should equal
   - What Metabolism actually produced
   - The difference

### Beat-3 falsifiable prediction (the hypothesis to test)

If hypothesis (b) is correct:
- Metabolism's L2.1 trace shows `states_before[ADP] = X1, states_after[ADP] = X2`
- Condensation's L2.1 trace at tick 0 shows ADP delta = +3
- In composition, Metabolism sees `states_before[ADP] = X1 + 3` (because
  Condensation produced 3 ADP upstream)
- Metabolism then produces `states_after[ADP] = (X1+3) + (X2-X1) = X2 + 3`
- Harness asserts Metabolism's after = X2 (from its isolated trace)
- Divergence = +3, matching exactly what Condensation produced
- VERDICT: hypothesis (b) — Metabolism is right, oracle is the wrong baseline

If hypothesis (a) is correct:
- The divergence in composition is unrelated to Condensation's upstream
  consumption — there's a separate offset that can't be explained by
  upstream delta
- Probe shows Metabolism's composition behavior doesn't match L2.1 even
  when shared state is set to Metabolism's own L2.1 `states_before`

If hypothesis (c) is correct:
- The counterfactual diagnostic in `_build_counterfactual_step_vector`
  passes (matches Metabolism's L2.1 in isolation) but composition fails
  — meaning the bug is in the composition harness path, not Metabolism

### Beat-4 pre-mortem failure modes

1. **Tick-0 coincidence.** The hypothesis confirms at tick 0 but doesn't
   hold at tick 5 or tick 10. Mitigation: probe should also check tick 5
   and tick 10 if tick 0 confirms (b).

2. **Selective WID confirmation.** ADP confirms (b), but ATP shows (a) for
   the same pair. Probe should check ATP and AMP too (all 3 listed in the
   CAUSE_5 first-WID rotation).

3. **Generalization failure.** This pair is one specific case; other
   CAUSE_5 pairs might be (a) for different reasons. Mitigation: STATUS
   must include a section "Does this verdict generalize? Evidence."

4. **Counterfactual path artifact.** The CAUSE_4 fix earlier today
   threaded `disable_trace_hints` into the counterfactual. Maybe the
   counterfactual is now correctly matching Metabolism's L2.1 (no hints),
   and the CAUSE_5 emission is downstream of that. Probe should verify
   the counterfactual path output.

### Beat-5 verification protocol

```powershell
# Step 1: run the probe
bin\oc-py.cmd _probe_cause5_cond_metab.py

# Step 2: re-run the failing test with verbose
bin\oc-pytest.cmd tests/vivarium/test_l25_deterministic_stochastic_pairs.py \
    -v -k "ChromosomeCondensation+Metabolism" --tb=long

# Step 3: compare probe output with structured failure record
# Expected: probe's composed Metabolism delta == failure record's diff
# If they match: verdict (b) confirmed
```

### Hard rules

- DO NOT modify any process file
- DO NOT modify any test file
- DO NOT modify the harness — only PROPOSE harness changes in STATUS
- DO NOT run the full 43-pair DS suite (slow; we already have its output)
- DO NOT generalize beyond what the probe data supports
- If probe data is inconclusive, say so; do not pick a verdict to satisfy
  the form
- If you exceed 60k tokens, stop and write STATUS with partial evidence
- The probe script may be deleted before final commit, but its output
  must be quoted verbatim in STATUS
