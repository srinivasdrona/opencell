# GPT-5.5 critique of V3 patches

**Status**: V3 patch bundle at
`docs/phase_f/L2_2_METABOLISM_LP_DEGENERATE_DESIGN_V3_PATCHES.md` (118 lines,
7 patches: P1-P7 addressing opus BLK-1/2/3 + NB-1/2/4/7) was reviewed by
gpt-5.5 with reasoning_effort=high.

GPT-5.5 found **5 BLOCKING issues** in V3. Convergence broke. V3 is NOT
implementation-ready. V4 must close these.

**Source**: session 5c51d44b-5a9f-4b23-85ff-0fddaadf2212, Day-40 evening
2026-06-27.

---

## Bottom line

> V3 is better than V2, but not implementation-ready. It needs a V4 /
> consolidated spec before a junior implementer starts. The main remaining
> risk is that P2 can still "prove" degeneracy using tests that do not
> actually establish that Karr's full 17-WID residual vector is jointly
> reachable from OC on the biomass-fixed optimal face.

Three of the five blocking issues are in P2 (the reachability test) — that's
not clerical, it's structural. The reachability question is mathematically
harder than V3 formalized.

GPT empirically confirmed P1 (optimal-face check) actually works at sample
(0,1): `|c · v_OC - c · v_Karr|` differs by about 1.3e-13, well within the
1e-9 threshold. So P1 is real.

---

## Blocking issues (must be fixed in V4)

### BLK-V3-1. P2 proves per-WID marginal reachability, not joint reachability

V3 solves 17 INDEPENDENT LPs, one per WID. That can show each WID is
individually adjustable by some k_i, but not that there exists ONE flux
perturbation k that reaches Karr's 17-WID residual pattern simultaneously.

**Impact:** MF4 could admit a case where every WID is separately reachable
but no single LP vertex corresponds to Karr. That does not prove "the gap
is vertex choice."

**V4 fix:** Require a JOINT reachability LP first: one k with all 17 WID
constraints, or an optimization minimizing normalized 17-WID residual with
a weighted pass criterion. Per-WID LPs should be diagnostics only.

Concrete proposal:

```
minimize  sum over wid in Top17 of:
              max(0, |writeback_linearized(v+k)[wid] - karr_delta[wid]|
                     / per_wid_reach_tol[wid] - 1)
subject to:
  S · k = 0
  e_biomass · k = 0           # biomass-fixed (NEW per BLK-V3-3)
  c · k = 0                   # full optimal face preserved
  lb - v <= k <= ub - v
```

Pass: objective value = 0 (every WID within tolerance simultaneously).
Per-WID LPs run AFTER joint LP, only as diagnostics for failed WIDs.

### BLK-V3-2. P2's writeback "Jacobian" is not well-defined

The writeback includes stochastic rounding (`stochasticRound`) and
post-clipping (`v.clip(lb, ub)`). With fixed RNG, stochastic rounding is
deterministic but still piecewise-constant with zero derivative almost
everywhere and jumps at integer boundaries. "The Jacobian is computable"
is not mathematically true as V3 wrote it.

**Impact:** A junior implementer may either produce a zero Jacobian,
ignore rounding, or implement an unjustified continuous surrogate. The
LP result would then have unclear meaning.

**V4 fix:** Define exactly what is linearized. Options to choose ONE:

(a) **Pre-round continuous surrogate**: linearize the pre-rounding map
   `delta_continuous(v) = step1_stoichiometric(v) + step3_compartment(v)`
   skipping step 2 (stochasticRound) and step 5 (clipping). The Jacobian
   is then the well-defined product of constant matrices. Use the LP
   result as a CANDIDATE; verify by running the actual non-linearized
   writeback and accepting if `|writeback(v+k)[wid] - karr_delta[wid]|
   < per_wid_reach_tol[wid]`.

(b) **MILP formulation**: model stochasticRound as integer variables;
   computationally heavier but mathematically clean.

(c) **Verification-as-normative**: demote the LP to candidate generation
   ONLY; the actual writeback (with rounding + clipping) is the normative
   test; the LP just provides a starting k for line search.

V4 should pick (a) or (c) and define the verification + line-search
acceptance criteria. (b) is likely over-engineering for this gate.

### BLK-V3-3. P2 preserves c·k = 0 but not biomass separately

V2's original intent was biomass-fixed feasible motion. P2 only requires
`c·k = 0` using the full objective. Because the objective includes 35 small
parsimony penalties (each ~5e-9), a perturbation can trade biomass against
parsimony while keeping total objective constant.

**Impact:** The reachability test may bless flux motion that changes growth
or biomass writeback terms, which is not the claimed "same-growth LP vertex"
explanation.

**V4 fix:** Add an explicit biomass constraint, e.g. `e_biomass · k = 0`
(unit vector at the biomass column), IN ADDITION to `c · k = 0`. Also
specify objective and biomass tolerances using the same post-clipping/bound
conventions as the solver.

### BLK-V3-4. P3 weakens elemental conservation while still claiming M3/M5 coverage

I5a is described as "mass-only" but actually uses total molecular count.
Count conservation will not reliably catch cofactor/pathway swaps. ATP↔GTP
swaps can preserve count and may preserve rough mass while still being
biologically wrong.

**Impact:** V3 claims I5a gates M3/M5, but that claim is not supported.
Deferring I5b may leave the exact pathway/cofactor-swap hole V2 tried to
close.

**V4 fix:** Rename I5a to `total_count_conservation` and DO NOT claim it
catches M3/M5. Reassign M3/M5 detection responsibility to I3
(pathway_level_flux_distributions) and I4 (dominant_wid_joint_structure)
— which are sensitive to family-bin imbalance and rank-structure
respectively. Require concrete M3/M5 mutation fixtures to fail via I3 or
I4 before MF4 admission. I5b (when wired) becomes the rigorous catch but
is not the only catch.

### BLK-V3-5. P5 validates enum presence but not numeric-rubric consistency

The selector can still accept an audit record where `condition_number=6.7e+12`
but `degeneracy_sensitivity=none`, because P5 only validates enum membership.

**Impact:** This reopens silent misclassification risk: the numeric rubric
says MF4, the stored label says defer, and the selector may trust the
stale/manual label.

**V4 fix:** The selector should compute `degeneracy_sensitivity` from
numeric fields directly and either (a) ignore the stored value entirely
(canonical: derived label), or (b) fail with `AUDIT_RUBRIC_INCONSISTENCY`
if the stored value disagrees with the computed value. V4 should pick (a)
or (b) and require the audit record to store ONLY the numeric inputs;
the label is computed at load time.

---

## Non-blocking issues (V4 should address)

### NB-V3-1. P1 wording — failure ≠ "OC is suboptimal"
P1 says failure means "OC's vertex is sub-optimal." Other interpretations:
(a) the LP setup differs (different objective coefs, different bounds,
different solver semantics), (b) numerical tolerance failure (rare but
possible).

V4 fix: state failure as "objective/bounds/solver-semantics mismatch or
numerical tolerance failure" and require Karr-flux feasibility check under
the SAME S/RHS/lb/ub before claiming "same optimal face." If Karr's flux
is infeasible under our bounds, the LP setup itself differs and the check
is moot.

### NB-V3-2. P4's future re-audit trigger is not enforceable
The runner path exists, but "future LP-non-degenerate process requires
re-audit" needs a CI/audit fixture, not just prose.

V4 fix: Add a test that fails on any `(solver_type=lp,
degeneracy_sensitivity in {none, low})` record unless an explicit reviewed
mapping exists. State the file location and assertion form.

### NB-V3-3. P6 tail budget is arbitrary and pattern-blind
Allowing 29 tail WIDs to breach could hide concentrated failures in a
biologically meaningful family.

V4 fix: Add a tail aggregate cap and/or family concentration cap, not only
a count cap. Concrete: tail-region L1 residual must also satisfy
`tail_residual <= max(40, 0.01 * baseline_tail_total)`, AND no single
family bin (Lipid, NucleotidePool, etc.) may carry >50% of tail breaches.

### NB-V3-4. P7's I6 sign test does not catch the stated M9 reliably
For scaling all signed deltas by 0.995, residual signs depend on the
baseline delta signs. If baseline production/consumption signs are
balanced, the 60/40 positive-vs-negative test may not fire.

V4 fix: Replace I6 with a directional magnitude test: count or sign-test
`(candidate_delta - baseline_delta) * sign(baseline_delta)` per WID with
non-trivial baseline. A coherent under-flux makes this consistently
negative; a coherent over-flux consistently positive. Threshold: ≥80% of
WIDs must agree in sign for I6 to fire.

OR: aggregate-magnitude test `sum(|candidate_delta|) / sum(|baseline_delta|)`
must be in `[1 - tol, 1 + tol]` with `tol = max(0.01, 40 / baseline_total)`.

### NB-V3-5. Verdict suffix may break downstream enum consumers
`CONDITIONAL_PASS_LP_DEGENERATE[I5b_deferred]` may not parse wherever V2
expects the single exact label.

V4 fix: Prefer stable verdict enum plus structured telemetry:
`verdict = CONDITIONAL_PASS_LP_DEGENERATE`, separate field
`deferred_invariants = ["I5b"]`. Single enum stays parseable; structured
field carries the nuance.

### NB-V3-6. NB-5 was deferred but should be admission-gated
GPT noted: "NB-5 should be an implementation acceptance gate, not a vague
deferral: if M7 temporal shift is in the mutation catalogue, the
implementation must empirically prove I2 catches it before MF4 can pass."

V4 fix: Promote M7 empirical verification from V3 "deferred" to V4
"admission gate." Implementation must run M7 against I2 on the pinned
baseline and confirm I2 fires. If it doesn't, V4 adds an explicit
tick-alignment invariant.

---

## Acceptance criteria for V4

V4 is admissible only if:

1. (BLK-V3-1) Joint reachability LP specified concretely; per-WID LPs
   demoted to diagnostics; pass criterion is "joint LP objective = 0".
2. (BLK-V3-2) Linearization choice specified (pre-round surrogate,
   MILP, or verification-as-normative); Jacobian construction either
   well-defined or explicitly demoted.
3. (BLK-V3-3) Biomass constraint `e_biomass · k = 0` separately enforced
   in addition to `c · k = 0`.
4. (BLK-V3-4) I5a renamed to `total_count_conservation`; M3/M5 detection
   reassigned to I3/I4; concrete mutation fixtures required before MF4
   admission.
5. (BLK-V3-5) Audit record stores numeric inputs only; selector computes
   `degeneracy_sensitivity` from numerics; stale labels rejected.
6. (NB-V3-1) P1 failure wording broadened; Karr-flux feasibility
   precheck added.
7. (NB-V3-2) Re-audit trigger has a named CI assertion.
8. (NB-V3-3) Tail residual has aggregate cap + family-concentration cap,
   not just count cap.
9. (NB-V3-4) I6 redesigned as directional magnitude test or
   aggregate-magnitude test.
10. (NB-V3-5) Verdict label uses stable enum + structured deferred_invariants
    field.
11. (NB-V3-6) M7 promoted from "deferred" to "admission gate".

The combined effect: V4 must make the reachability test mathematically
correct (BLK-V3-1, BLK-V3-2, BLK-V3-3), close the elemental-conservation
gap honestly (BLK-V3-4), enforce the rubric at runtime (BLK-V3-5), and
patch the smaller holes (NB-V3-1 through NB-V3-6).

A V4 that lacks any of these is not admissible.

---

## Convergence note

| Version | BLK by reviewer | Lines |
|---|---:|---:|
| V1 | 4 (opus) | 832 |
| V2 | 3 (opus) | 190 |
| **V3** | **5 (gpt-5.5)** | **118 patches** |

Convergence broke at V3. The reachability formulation in P2 was structurally
under-specified; three of the five new BLK issues are in P2 alone. V4 must
get the joint reachability LP right OR pivot to a different mathematical
primitive entirely.

If V4 also accumulates 3+ BLK issues, the design problem may not be
tractable via iteration. At that point the operator should consider:
- (i) Empirical pivot: build the joint reachability probe FIRST,
   let the result drive the design (the audit RC3 demanded).
- (ii) Warm-start pivot: extract Karr's flux at all 500 samples via
   MATLAB, use as GLPK basis seed, sidestepping the degeneracy
   characterization problem entirely.
- (iii) Accept FAIL with documented residual analysis; return after L5
   work begins on the other 21 processes.
