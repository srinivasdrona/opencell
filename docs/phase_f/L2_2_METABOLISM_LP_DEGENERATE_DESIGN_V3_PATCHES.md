> **NOTE**: This V3 patch chain is superseded in full by `docs/phase_f/L2_2_METABOLISM_LP_DEGENERATE_DESIGN_V4.md`; V4 is now the sole normative MF4 design.

# L2.2 Metabolism LP-Degenerate Design — V3 patches

**Status**: V3 PATCH bundle. Canonical contract for MF4 = V2 + V3 patches applied in order. V4 (if needed) supersedes this entirely.

**Driver**: opus-4.8 critique of V2 found 3 BLOCKING issues (BLK-1, BLK-2, BLK-3) and 5 non-blocking. V3 patches the 3 BLK + 3 selected NB (NB-1, NB-2, NB-4, NB-7). Other NBs (NB-3, NB-5, NB-6) deferred to V4 or implementation review; rationale at end.

**Format per patch**: TARGET (V2 location) + REPLACEMENT (new text) + JUSTIFICATION (opus reference) + ACCEPTANCE (how V4 / implementation reviewer verifies the patch held).

---

## P1 — BLK-1 fix: optimal-face equivalence check

**TARGET**: V2 §4 "MF4 is a two-stage contract" (line 120) — extend admission stage. V2 §3 "Single normative selection rule" (lines 104-110) — add admission precondition.

**REPLACEMENT**: Insert before the null-space perturbation test in §4 admission stage:

> **Admission precondition: optimal-face equivalence check.**
> Before the perturbation test runs, verify that OC's vertex `v_OC` and Karr's recorded flux `v_Karr` lie on the same optimal face of the LP:
>
> ```
> |c · v_OC - c · v_Karr| / max(|c · v_Karr|, 1) < 1e-9
> ```
>
> where `c` is the full 36-nonzero Karr objective (biomass coefficient +1000 plus 35 small internal-exchange parsimony penalties, per `opencell/m1/karr_metabolism.py` model.obj).
>
> If the check FAILS: OC's vertex is sub-optimal relative to Karr's, meaning the LP setup differs (objective vector, bounds, or solver semantics). MF4 admission is REFUSED. The failure is `AUDIT_OPTIMAL_FACE_MISMATCH` and triggers re-investigation, not silent degradation to a softer family.
>
> If the check PASSES: OC and Karr both achieved the same optimal objective value, confirming both vertices lie on the LP's optimal face. The remaining residual is then potentially attributable to vertex degeneracy, and the perturbation test runs to confirm reachability.

**JUSTIFICATION**: Opus BLK-1: "The perturbation test passes iff Karr's recorded deltas are REACHABLE from OC's vertex via biomass-fixed feasible motion. That proves Karr and OC's vertex lie in the same connected feasible set — it does NOT prove OC's vertex is itself a legitimate optimum." A feasible-but-sub-optimal vertex would pass the test and bless an OC bug. The optimal-face check is the cheapest discrimination available: same objective value ⟹ same optimal face ⟹ vertex difference is degenerate-optimum choice, not LP-bug.

We already empirically know this holds for Metabolism at sample (0,1): both OC and Karr show growth = 2.119269e-05 (per `docs/phase_f/METABOLISM_GAP_MAP.md`, Day-40 probe). What V2 missed is checking the FULL 36-coef objective, not just biomass.

**ACCEPTANCE**: Implementation must (a) compute `c · v_OC` and `c · v_Karr` at sample (0,1) using the full 36-nonzero `model.obj`, (b) assert the relative difference < 1e-9, (c) error with `AUDIT_OPTIMAL_FACE_MISMATCH` and refuse MF4 admission if the assertion fails. The check is a one-line linear-algebra verification; it cannot be deferred.

---

## P2 — BLK-2 fix: replace per-axis grid with LP-formulation reachability

**TARGET**: V2 §4 lines 144-153 (the 9-step null-space perturbation test procedure).

**REPLACEMENT**: Replace steps 3-9 with:

> 3. **Reachability LP per WID.** For each of the 17 dominant WIDs (per V2 I4 list), solve a feasibility LP:
>    ```
>    find k ∈ R^504 such that:
>      S · k = 0                              (mass balance preserved)
>      c · k = 0                              (optimal face preserved)
>      lb - v ≤ k ≤ ub - v                    (bounds preserved)
>      | writeback_linearized(v + k)[wid] - karr_delta[wid] | < per_wid_reach_tol
>    ```
>    where `writeback_linearized` is the linearization of Karr's 4-step writeback around `v` with RNG seed fixed (so stochastic rounding becomes deterministic) and post-clip inactive at small perturbations. The Jacobian is computable from the writeback fixture's stoichiometry+compartment matrices.
>
>    Per-WID reachability tolerance:
>    ```
>    per_wid_reach_tol = max(1, 3e-4 * max(1, |karr_signed_delta_wid|))
>    ```
>    (Same as V2; defensible because 3e-4 is ~10× the Day-40 algorithm/RNG floor of 40/148K ≈ 2.7e-4 — i.e., we accept reachability within order-of-magnitude RNG noise.)
>
> 4. **Verification step.** For each WID where the LP returned a feasible `k`, evaluate the *actual* (non-linearized) writeback `writeback(v + k)[wid]` and confirm the linearization was accurate within `per_wid_reach_tol`. If linearization error exceeds tolerance, run a small line-search along `k` to find an actually-reachable point.
>
> 5. **"Moves freely" criterion**: ≥80% of the 17 dominant WIDs have a feasible `k` whose actual writeback is within tolerance of Karr's recorded delta.
>
> 6. **"Fixed biased offset" criterion**: >10% of the 17 dominant WIDs have NO feasible `k` (LP infeasible) AND linearization error doesn't explain the gap.
>
> 7. **Pass rule**: MF4 admission requires "moves freely" AND not "fixed biased offset". Any intermediate result is `OPEN_QUESTION_REINVESTIGATE`.

**JUSTIFICATION**: Opus BLK-2: "V2 evaluates `alpha` along each null-space basis vector INDEPENDENTLY. With 128 null dimensions, this explores 128 one-dimensional rays, not the 128-dim feasible cone. Karr's vertex almost certainly requires a COMBINATION. The per-axis sweep may declare WIDs 'unreachable' even when Karr is reachable via combined motion — V2 may fail to achieve its own purpose."

The LP formulation tests the true joint feasible region in one solve per target. Cost: 17 small LPs (each 504 variables, ~876 constraints) — well within seconds via GLPK. The linearization caveat handles the writeback non-linearity honestly.

**ACCEPTANCE**: Implementation must (a) compute the writeback Jacobian from the fixture (analytical, not numerical), (b) formulate and solve 17 feasibility LPs via swiglpk, (c) verify each feasible `k` against the actual writeback, (d) report the 80%/10% reachability/infeasibility split. Implementer should also report the raw counts (e.g., "14/17 reachable, 1/17 infeasible, 2/17 linearization-bounded") for review.

---

## P3 — BLK-3 fix: split I5 into mass-only (I5a) and elemental (I5b)

**TARGET**: V2 §4 I5 row in the invariant table (line 137-138) + V2 §4 "Element set decision" block (lines 139-142) + V2 §6 "single verdict label" (lines 186-190).

**REPLACEMENT**:

V2's I5 row becomes two rows in the invariant table:

> | I5a | `mass_conservation` | per `(seed,tick)` total molecular count across all WIDs and compartments after writeback | `abs(diff) <= max(40, 3e-4 * karr_sample_total)` | M3, M5 |
> | I5b | `elemental_conservation` | per `(seed,tick)` C, N, P mass totals (computed from per-WID elemental composition × delta count) | same tolerance form as I5a, per element | M3, M5 |

V2's "Element set decision" block becomes:

> **Element set decision (V3-revised)**:
> 1. **I5a (mass only)** is implementable with current schema and is REQUIRED for MF4 admission.
> 2. **I5b (C/N/P)** is the stronger biology guard but requires elemental composition per WID, which is currently in `data/m1_sources/WholeCellKB` (Django fixtures) and NOT wired into the L2.2 layer.
> 3. I5b is **DEFERRED** until the dependency is closed. Concrete prerequisite task: extract WID → {C, N, P} composition from WholeCellKB into a TOML or YAML lookup at `data/schemas/per_process/metabolism_elemental_composition.toml`. This is an explicit scoped task, not a residual risk.
> 4. Until I5b is wired, MF4 verdict explicitly notes "I5b deferred" in its telemetry; the verdict label does NOT silently weaken.

V2's verdict label section gains:

> **I5b-pending verdict suffix**: `CONDITIONAL_PASS_LP_DEGENERATE[I5b_deferred]` until elemental composition is wired. Once wired and I5b passes, the suffix drops.

**JUSTIFICATION**: Opus BLK-3: "I5 is unimplementable today. V2 makes I5 a hard pass requirement; without elemental metadata, MF4 cannot ship. V2 calls this a 'residual risk' — it's actually a hard prerequisite. The N4 resolution CREATED this blocker." V3 splits the requirement so the implementable half (mass) gates v1 admission while the elemental half is an explicit scoped follow-up — neither pretending we have it nor silently downgrading the contract.

**ACCEPTANCE**: Implementation must (a) implement I5a immediately (uses existing per-WID counts), (b) emit the `[I5b_deferred]` suffix on verdict until I5b is wired, (c) NOT silently treat MF4 as fully passing without I5b. The elemental composition extraction is a separate task on the project backlog.

---

## P4 — NB-1 fix: bind `DEFER_TO_V1_NON_MF4` to legacy catalog path

**TARGET**: V2 §3 selection rule step 3-4 (lines 107-108) + V2 §6 harness contract (line 200).

**REPLACEMENT**: After V2 §3 line 110, add:

> **DEFER_TO_V1_NON_MF4 binding**: this return token means "the harness must use the legacy catalog-bucket-driven path from V1 (`tests/vivarium/l2_2_design_a_runner.py::run_design_a` direct bucket dispatch)." No current LP process is non-degenerate, so step 4's branch is structurally unreachable today. If a future LP process is added that audits to `(lp, non-degenerate)`, V1's MF1/MF2/MF3 mapping for that bucket must be re-audited (V1 D2 matrix requires `solver_type=none` for MF1, which the new LP process violates).

**JUSTIFICATION**: Opus NB-1: "`DEFER_TO_V1_NON_MF4` is a return token with no defined consumer." V3 binds it to the existing legacy path explicitly, flags the future-LP-non-degenerate seam as a known re-audit trigger.

**ACCEPTANCE**: Implementation must (a) implement the selector to return this token, (b) ensure the runner's dispatch logic interprets the token as "skip MF4-specific code paths, run legacy bucket-driven metric", (c) emit a one-time warning at runner startup if an LP process audits to non-degenerate (currently impossible; warning is defense-in-depth).

---

## P5 — NB-2 fix: field-presence validation in selector step 2

**TARGET**: V2 §3 selection rule step 2 (line 106).

**REPLACEMENT**: Replace step 2 with:

> 2. If no audit record exists, if more than one row matches `process`, if the record hash/commit pin is invalid, OR if any required audit field (`solver_type`, `condition_number`, `nullity_ratio`, `unbounded_non_biomass_reactions`, `observable_surface`, `degeneracy_sensitivity`) is missing from the record OR fails enum validation (specifically: `solver_type ∈ {lp, non_lp}`, `degeneracy_sensitivity ∈ {none, low, lp_degenerate}`, `observable_surface ∈ {substrates_only, other}`), raise `AUDIT_REGISTRATION_ERROR`.

**JUSTIFICATION**: Opus NB-2: "A record that exists and is correctly pinned yet has `solver_type` null/absent hits step 3 (`solver_type != lp` is true) → `DEFER_TO_V1_NON_MF4` silently. The 'no implicit fallthrough' guarantee protects only the lp branch; the defer branch is an unvalidated catch-all." V3 adds field-presence + enum validation at the registration check.

**ACCEPTANCE**: Implementation must (a) validate field presence + enum membership at audit-record load time, (b) error explicitly (not silently defer) on any missing or invalid field, (c) include the offending field name in the error message for debuggability.

---

## P6 — NB-7 fix: I2 scope clarification (all 585 WIDs, focused on Top-27)

**TARGET**: V2 §4 I2 row in invariant table (line 134).

**REPLACEMENT**: I2 row becomes:

> | I2 | `per_wid_signed_delta_residual_budget` | per `(seed,tick,wid)` signed delta vs pinned MF4 baseline. **Evaluated on ALL 585 substrate WIDs**, with mandatory hard-fail threshold on the Top-27 dominant WIDs and a looser failure budget on the tail. | Top-27: `abs(diff) <= max(1, 0.01 * max(1, abs(baseline_delta)))` + sign match when `abs(baseline_delta) > 1`. Tail (≥WID-28): same per-WID tolerance, but pass-condition allows up to 5% (29) of tail WIDs to breach individually. | M1, M2, M4, M7 |

**JUSTIFICATION**: Opus NB-7: "I2 says 'with mandatory focus on Top-27 WIDs.' If 'focus' means *only* Top-27 are checked, a mass-preserving redistribution among the other ~558 WIDs evades I1 (sum preserved), I2 (not checked), I3 (specific family bins), I4 (Top-17), I5 (mass preserved)." V3 closes the tail blind spot explicitly: all 585 WIDs evaluated, Top-27 hard-fail, tail allows budgeted breaches to handle small numerical noise.

**ACCEPTANCE**: Implementation must (a) evaluate per-WID residual for all 585 substrate WIDs, (b) hard-fail on any Top-27 breach, (c) count tail breaches and fail if > 5% of tail (i.e., > 29 of 558).

---

## P7 — NB-4 fix: explicit sub-1% detection-floor documentation + cumulative sign test

**TARGET**: V2 §4 add I6 row + V2 §7 add explicit detection-floor note to "Operator questions remaining" section.

**REPLACEMENT**: Add I6 row to the invariant table:

> | I6 | `cumulative_sign_test` | per `(seed,tick)`, count WIDs where `(candidate - baseline)` is positive vs negative across all 585 WIDs | `|n_positive - n_negative| / n_nonzero < 0.20` (i.e., bias toward one direction may not exceed 60/40 split among WIDs with non-trivial baseline) | M9 |

Add M9 to the mutation catalogue:

> | M9 | Coherent sub-1% bias: scale ALL per-WID signed deltas by 0.995 (0.5% systematic under-flux); residuals are below I1/I2 tolerance individually but coherent across WIDs | I6 |

Add detection-floor disclosure to V2 §7 (immediately after current "Operator questions remaining"):

> **Detection floor disclosure**: MF4's invariant suite has a documented detection floor of ~1% on coherent SYMMETRIC magnitude attenuation (scale-all-deltas without bias). This is intrinsic to a degenerate LP: Karr-vs-Karr seed-pair variation has a ~0.03% RNG floor, and the smallest meaningful invariant tolerance is bounded by FP noise. I6 catches BIASED sub-threshold attacks (where most WIDs move the same direction) via the cumulative sign test, but a truly symmetric ~0.5% scaling can pass. This is an accepted limitation, documented here for downstream operator review.

**JUSTIFICATION**: Opus NB-4: "M6 closes the 10% hole, but I1=1%, I2=1%, I3=5% leave a sub-1% blind spot. A coordinated ~0.9% uniform under-flux passes everything." V3 takes opus's "either accept as detection floor with justification, or add a cumulative sign-test invariant" — V3 does BOTH: adds I6 (catches biased sub-threshold) AND documents the symmetric-attenuation floor as accepted limitation. We don't pretend to detect what we can't.

**ACCEPTANCE**: Implementation must (a) implement I6 as a one-pass count over per-WID residuals, (b) hard-fail on bias > 60/40 among WIDs with non-trivial baseline, (c) emit the detection-floor disclosure in MF4 telemetry so reviewers don't mistake the floor for a regression.

---

## Patches deferred to V4 or implementation review

- **NB-3** (truth-table missing `(non_lp, lp_degenerate)` row): The selector rule already handles this (step 3 → `DEFER_TO_V1_NON_MF4`; degeneracy is ignored for non-LP because we don't have a non-LP-degenerate metric family). NB-3's fix is purely a fixture-completeness concern; implementation reviewer should add the row to the truth-table fixture without needing a design change.
- **NB-5** (M7 detection assumes per-tick dissimilarity): The empirical verification of "Karr's per-tick deltas at sample 1 differ enough from sample 0 deltas for I2 to detect M7" is an implementation/test task. If verification fails, V4 must add an explicit tick-alignment invariant; if it passes, NB-5 is closed by evidence.
- **NB-6** (I4 statistically underpowered): Opus suggested "reassign M8's designated catcher to I2 (or I2∧I4), and don't lean on a 17-point rank correlation as the joint-structure guarantee." V3 implicitly addresses this via P6 (I2 evaluates all 585 WIDs with Top-27 hard-fail), which is the stronger catcher for M8. The I4 underpower stands but is no longer the sole M8 guarantee.

## V3 self-audit against opus BLK + selected NB

- [x] **BLK-1**: P1 adds optimal-face equivalence check; failure → AUDIT_OPTIMAL_FACE_MISMATCH, not silent admission.
- [x] **BLK-2**: P2 replaces per-axis grid with feasibility LP per WID; tests joint feasible cone correctly.
- [x] **BLK-3**: P3 splits I5 into mass-only (gating) + C/N/P (deferred with explicit scoped follow-up); MF4 implementable today.
- [x] **NB-1**: P4 binds `DEFER_TO_V1_NON_MF4` to legacy catalog path; future LP-non-degenerate seam flagged.
- [x] **NB-2**: P5 adds field-presence + enum validation in selector step 2; closes silent-defer hole.
- [x] **NB-4**: P7 adds I6 (cumulative sign test) + documents the symmetric-attenuation detection floor.
- [x] **NB-7**: P6 clarifies I2 evaluates all 585 WIDs (not just Top-27) with tail budget.
- [-] **NB-3, NB-5, NB-6**: explicitly deferred with rationale above.

V3's net new content: ~110 lines (7 patches + this self-audit). V2 (190 lines) + V3 (110 lines) = 300 lines canonical MF4 contract. Below the 350-line warning threshold that would trigger consolidation into a full V4.

**V3 status**: ready for adversarial critique.
