# Opus-4.8 critique of L2.2 Metric-by-Process-Character design v1

**Status**: V1 design at `docs/phase_f/L2_2_METRIC_BY_PROCESS_CHARACTER_DESIGN.md`
(commit 8cebfb9, 832 lines) was reviewed by opus-4.8 with reasoning_effort=high.
This document captures the critique that drives the V2 redesign.

**Source**: session 5c51d44b-5a9f-4b23-85ff-0fddaadf2212, Day-40 evening,
2026-06-26.

---

## Bottom line from opus

> The doc materially responds to all four prior blocking issues — it splits W1
> into two named quantities, adds interface-fidelity invariants beyond biology
> aggregates, specifies five concrete mutations, and replaces the single bucket
> with a multi-axis audit. So the originals are addressed *in form*. The
> problems are in whether that form holds under load. It mostly does not, in
> four specific places.

V1's net new gating power (degeneracy audit + invariant suite + mutation
catalogue + verdict label for Metabolism) is buried under documentation of
existing implementations (MF1, MF2, MF3, MF5 are renames of code that already
exists). The 4 blocking issues below mean V1 can't be implemented as written.

---

## Blocking issues (must be fixed in V2)

### B1. D2 matrix and D2 selection rule are not the same function

V1 line 324 (done criterion) and line 433 (pre-registration rule) assert
"the metric family is a pure function of the audit record." But the
**matrix signatures at lines 452–458 are conjunctive over all axes**, while
the **selection rule at lines 460–466 is a sequential if-else that ignores
several axes**. They produce different answers on reachable inputs:

- `observable_sufficiency=requires_aux_invariants` + `solver_type=none` +
  `stochastic` matches *no* matrix row (MF1 requires `raw_output_sufficient`).
  But selection rule falls through to step 6 → MF1 (raw vector W1). The audit
  explicitly flagged that raw outputs *can't* detect the interface bug, and
  the rule hands it raw-vector W1 anyway.
- `trivial_rng` + `degeneracy_sensitivity=lp_degenerate` + `solver_type≠lp`:
  matrix MF3 requires `degeneracy in {none,low}` → no match. Selection rule
  step 5 → MF3, silently dropping the degeneracy flag.
- `observable_sufficiency` has exactly one operative value in the rule
  (`projection_sufficient`, step 4), which merely duplicates
  `solver_type=projection_state`. Values `requires_aux_invariants`,
  `event_window_only`, and `raw_output_sufficient` never change a non-LP
  outcome. **It is a near-phantom axis** dressed as one of the five
  load-bearing dimensions.

**Impact:** Acceptance bar #1 says a reviewer reconstructs the family "by
applying D2's matrix." A different reviewer applying the *rule* gets a
different answer on the cases above. That is precisely the D1 falsifier
("two reviewers classify the same process differently → schema
underspecified"), triggered by the doc's own two artifacts disagreeing.

**V2 fix:** Make the selection rule the single normative artifact. Delete the
matrix-as-spec (demote to illustrative). Add an explicit "no row matched →
error, do not default to MF1" terminal case. Prove rule ≡ matrix with a
truth-table fixture over the axis cross-product.

### B2. `degeneracy_sensitivity` has no objective rubric and the audit requires no review

The entire retroactive-application claim hinges on the audit producing
`degeneracy_sensitivity=lp_degenerate` for Metabolism. V1 cites `cond=6.7e12`,
128 null dims, 8 unbounded reactions — but gives **no threshold** separating
`low` from `lp_degenerate`. A future LP at `cond=1e4` is unclassifiable;
and a critic re-auditing Metabolism with `degeneracy_sensitivity=low` lands
it in MF1 (raw vector W1) with V1's text as written.

Worse: V1 D1 line 419 says "Operator escalation needed? **no**" for the
audit decision. Meanwhile D4 (baseline) and D5 (verdict labels) — *lower-
leverage* decisions — both escalate. The review gate is on the wrong
decision.

**Impact:** V1 was authored *after* Day-40, knowing Metabolism's W1 is red,
and the audit deterministically routes the one red process into the one
family where its red metric is demoted to informational. Without an
objective degeneracy rubric and a review gate on the audit, that is
operationally **indistinguishable from the special pleading V1's own
inversion (line 314) warns about**. The "pure function" defense is empty
if the function's dominant input is a subjective unrubricated label.

**V2 fix:** Pre-register numeric degeneracy thresholds. Concrete proposal:

```
degeneracy_sensitivity = lp_degenerate IF any of:
  - cond(S) > 1e+10                       # numerical near-singularity
  - dim(null(S)) > 0.10 * n_reactions     # > 10% null-space ratio
  - count(unbounded reactions) > 0        # any reaction with lb=-inf, ub=+inf
                                          #  that is not biomass and not closed
                                          #  by Karr's static fbaReactionBounds
ELSE IF any of:
  - cond(S) in [1e+6, 1e+10]
  - dim(null(S)) in [0.01 * n_reactions, 0.10 * n_reactions]
THEN degeneracy_sensitivity = low
ELSE degeneracy_sensitivity = none
```

Thresholds are illustrative; V2 must defend specific numbers or call them
operator-decided in QO with explicit risk.

**V2 fix:** Operator sign-off on the audit record BEFORE any metric run for
any process whose audit yields a non-default (MF4 or MF5) family.

### B3. The mutation suite is provably incomplete against its own falsifier

V1 D6 falsifier (line 574): "A plausible interface corruption outside the
catalogue can pass the suite." Opus constructed one immediately:

- **Magnitude attenuation without sign change** (no V1 M-mutation, no
  invariant): Scale every signed delta by 0.9. Signs preserved (passes
  `key_cofactor_whitelist`, `compartment_specific_exchange_flux_sign_range`,
  M1, M3, M4). If each `|residual| ≤ budget` (budget =
  `q95_baseline_abs_residual[wid]`, V1 line 497),
  `per_wid_signed_delta_residual_budget` passes. A uniform scaling that
  still balances mass passes `elemental_or_mass_conservation`.
  `pathway_level_flux_distributions` shifts every bin proportionally —
  trips only if bin tolerance is tight, and **bin tolerance is undefined**.
  A systematic 10% under-flux — a genuine biological regression — can
  pass the entire suite.
- V1 M1-M5 only flip *signs* (magnitude unchanged); nothing tests biased
  magnitude.
- V1's suite is entirely per-sample-marginal + aggregate-bin. There is no
  joint/cross-WID/cross-tick correlation invariant. Any corruption that
  stays within per-WID budget and preserves bin aggregates and mass is
  invisible.

**Impact:** V1 Claim C4 (line 611) asserts the suite proves "stronger than
W1." W1 is a distributional metric that *would* catch a 10% systematic
shift; the V1 marginal+budget suite may not. This is a **regression in
detection power** for the exact failure class — solver-vertex flux drift —
the design exists to police.

**V2 fix:** Add at minimum:

- `M6_uniform_magnitude_attenuation`: scale all deltas by 0.9 (or another
  sub-budget factor); corresponding `aggregate_signed_flux_magnitude`
  invariant with a *specified* tolerance.
- `M7_temporal_shift`: correct deltas shifted by ±1 tick; corresponding
  `tick_alignment_check` invariant or document why
  `per_wid_signed_delta_residual_budget` already catches this.
- `M8_correlated_noise`: per-sample noise that preserves all aggregate
  statistics; corresponding joint/cross-WID covariance invariant if needed.
- Define specific bin-tolerance thresholds for
  `pathway_level_flux_distributions` (not "loose").
- Add an `aggregate_signed_flux_magnitude` invariant that catches uniform
  scaling.

### B4. Invariant budgets are calibrated FROM the OC-vs-Karr baseline — the Day-40 gap is blessed by construction

This is the honest core. Two self-referential calibrations stack:

1. `per_wid_signed_delta_residual_budget` uses `budget[wid] = max(abs_floor,
   q95_baseline_abs_residual[wid])` (V1 line 497), where
   `q95_baseline_abs_residual` is "measured from the accepted solver-stack
   baseline against Karr." **The budget is sized to accept exactly the
   current divergence.** The 17-WID Day-40 gap fits inside its own budget
   by definition.
2. `metabolism_regression_w1` (V1 line 490) gates against a *pinned OC
   baseline*, not Karr. `trace_vertex_equivalence_w1` vs Karr is demoted to
   informational (V1 line 485). So **after V1, nothing gates Metabolism
   against Karr except invariants whose tolerances are themselves derived
   from the OC-vs-Karr gap.**

V1's entire validity rests on the unproven premise that "the residual gap is
solver-family vertex choice, not a real OC regression." Day-40 is *precisely*
the scenario where an error preserves growth+KS+mean+stddev while corrupting
per-WID writeback (V1 line 323). The mutation suite doesn't rescue this,
because mutations are injected as deltas *on top of* the OC baseline — they
test "can we detect a *new* corruption," not "is the *existing* baseline
biology-correct." A genuine OC bug that contributed to the original 17-WID
gap is laundered into a permanent `CONDITIONAL_PASS` and explicitly excluded
from remediation (V1 Out of scope #3, line 694).

**Impact:** `CONDITIONAL_PASS: biology_invariants_pass /
trace_vertex_divergent` (V1 line 558) *ships as a pass at L2.2* over an
un-diagnosed gap, and the suite that's supposed to justify it is
tolerance-calibrated to that same gap. **This is the relabel-FAIL-as-
conditional-pass risk made concrete.**

**V2 fix:** Require an *independent* confirmation that the residual gap
is vertex-degeneracy and not OC error before MF4 admits CONDITIONAL_PASS.
Concrete proposal: **null-space perturbation test**. For Metabolism at a
representative sample:

1. Compute the null space of S (or a basis of LP-feasible perturbations at
   the current vertex).
2. Perturb the OC flux vector v by `v' = v + α * k` for `k in null(S)` and
   `α` chosen so that all bounds remain satisfied and biomass is preserved.
3. Re-run Karr's writeback on `v'` and observe the per-WID substrate
   distribution at the 17 dominant WIDs.
4. If the per-WID values move freely across a wide range (matching Karr's
   recorded values for some `α`) → the recorded gap IS vertex choice
   (provable, not assumed). MF4 admissible.
5. If perturbations cannot reach Karr's recorded values within the LP-
   feasible region → there is a fixed biased offset → likely OC bug →
   MF4 not admissible until the offset is investigated.

The perturbation test must be passed before any process is admitted to MF4.

---

## Non-blocking issues (V2 should address)

### N1. CONDITIONAL_PASS → L5 handoff is undefined
V1 never states whether a `CONDITIONAL_PASS` Metabolism is admissible input
to L5, and L5 is out of scope (V1 #2, line 693). If L5 whole-cell biology
consumes substrate after-states, it inherits the 17-WID divergence
silently.

**V2 fix:** Add an explicit statement: does CONDITIONAL_PASS gate L5
entry, or pass through? Either is acceptable; the question must be answered,
not deferred.

### N2. Pre-registration has no enforcement mechanism
V1 D1 line 433 mandates the audit precede the run and the family be a pure
function, but no CI gate, no file location, and no test are specified.
Combined with B1, "pure function" is aspirational.

**V2 fix:** Specify (a) the audit record is a committed artifact in a named
location, (b) the selector is a single tested function with a known import
path, (c) the harness *must* call the selector (no inline overrides).

### N3. The "multi-axis" framing is partly cosmetic
Operatively, only ~2 axes are load-bearing for the cases that matter:
`solver_type` + `degeneracy_sensitivity` decide MF4 vs the rest.
`observable_sufficiency` is near-phantom.

**V2 fix:** V2 is a minimal-scope design focused on MF4 only. The multi-
axis framing is dropped; only the degeneracy rubric is normative. Other
"families" are documented as "current behavior, no change" rather than
reified as MF0/MF1/MF2/MF3/MF5.

### N4. QO4 defers a load-bearing decision
V1 QO4 leaves the strength of `elemental_or_mass_conservation` to the
operator — but the suite's claimed ability to catch pathway swaps (M3/M5)
depends on it.

**V2 fix:** Decide the element set (C/N/P or just mass) in V2, don't defer.

### N5. Selection-rule precedence is undocumented
A hypothetical `solver_type=lp` + `event_density=singular_windowed` process
hits step 2 (→ MF5) before step 3 (→ MF4). Probably intended, but
undocumented.

**V2 fix:** State the precedence rationale or remove the conflict by scoping
V2 to MF4 only (which V2 does per N3 fix above).

---

## Suggestions

### S1. The doc is ~2–3× larger than its decision content
V1 lines 1–301 (36%) are verbatim quotations; MF1/MF2/MF3 are renames of
existing implementations. The *net new gating power* is the Metabolism
mutation suite + degeneracy audit; everything else is renaming-plus-
deferral.

**V2 scope:** ~150–200 lines focused on the degeneracy rubric + the
invariant suite + the mutation catalogue + the verdict label + the null-
space perturbation test. Do not reify a six-family taxonomy around four
event-class processes the framework admits it cannot validate (MF5) and
one it can only conditionally pass (MF4).

### S2. State why L2.1 GENUINE survives but L2.2 needs the audit
The implicit answer (L2.1 aggregates fire-rates; L2.2 inspects per-WID
distributions where vertex choice surfaces) is defensible but never written.
One sentence prevents the obvious challenge.

**V2 fix:** Include the one-line rationale.

---

## Acceptance criteria for V2

V2 is admissible only if:

1. **B1**: Selection rule and matrix (if any) provably equivalent on a
   truth-table fixture; no-row-matched → explicit error (not default).
2. **B2**: Objective numeric thresholds for `degeneracy_sensitivity` with
   explicit defense; operator escalation required on the audit decision for
   any non-default family.
3. **B3**: At minimum M6 (magnitude attenuation), M7 (temporal shift),
   M8 (correlated noise) added; bin tolerance for
   `pathway_level_flux_distributions` defined numerically;
   `aggregate_signed_flux_magnitude` invariant present.
4. **B4**: Null-space perturbation test specified concretely (which sample,
   which α range, what counts as "moves freely", what counts as "fixed
   biased offset"). MF4 admission gated on this test passing.
5. **N1**: CONDITIONAL_PASS → L5 handoff stated.
6. **N2**: Enforcement mechanism for pre-registration named (file location,
   selector function path, harness contract).
7. **N3**: V2 is ~150-200 lines, scoped to MF4 only.
8. **N4**: Element set for mass conservation decided in V2.
9. **S1**: No verbatim re-quotation of MF1/MF2/MF3/MF5 status quo. Reference
   V1 for that material; V2 supersedes V1's MF4 section only.
10. **S2**: One-sentence L2.1-vs-L2.2 rationale included.

The combined effect of B1-B4 fixes is that V2 must:
- Be self-consistent (B1)
- Not be game-able by subjective audit labels (B2)
- Provably stronger than current W1 on real failure classes (B3)
- Have an independent confirmation step proving the residual is vertex
  choice (B4)

A V2 that lacks any of those is not admissible.
