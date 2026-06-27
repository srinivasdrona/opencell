# L2.2 Metabolism LP-Degenerate Design — V4

Supersession scope:
- This document supersedes `docs/phase_f/L2_2_METABOLISM_LP_DEGENERATE_DESIGN.md` (V2) and `docs/phase_f/L2_2_METABOLISM_LP_DEGENERATE_DESIGN_V3_PATCHES.md` (V3) for MF4 only.
- `docs/phase_f/L2_2_METRIC_BY_PROCESS_CHARACTER_DESIGN.md` remains the current contract for MF0, MF1, MF2, MF3, and MF5.

## Catalog Entry (Authoritative Spec)

```text
docs/phase_f/L2_2_DESIGN_V3_CRITIQUE.md (V4 spec authority)

Bottom line: V3 is better than V2 but not implementation-ready. 5 BLK
issues, 6 NB issues. V4 must close all 5 BLK + all 6 NB.

V4 acceptance criteria (lines 184-210):
1. BLK-V3-1: Joint reachability LP specified concretely
2. BLK-V3-2: Linearization choice specified (pre-round / MILP / verify-only)
3. BLK-V3-3: e_biomass · k = 0 enforced separately from c · k = 0
4. BLK-V3-4: I5a renamed to total_count_conservation; M3/M5 reassigned
5. BLK-V3-5: Audit stores numerics only; selector computes label
6. NB-V3-1: P1 failure wording broadened; Karr-flux feasibility precheck
7. NB-V3-2: Re-audit trigger has named CI assertion
8. NB-V3-3: Tail residual has aggregate + family-concentration caps
9. NB-V3-4: I6 redesigned as directional magnitude test
10. NB-V3-5: Verdict = enum + deferred_invariants structured field
11. NB-V3-6: M7 promoted from deferred to admission gate
```

## DAP Intent

1. Summary: replace V3's patch chain with one implementation-ready MF4 design that proves or falsifies joint Karr reachability from OC's biomass-fixed optimal face, stores only numeric audit inputs, and admits Metabolism only through a verified structured MF4 gate.
2. Contract: per `docs/phase_f/L2_2_DESIGN_V3_CRITIQUE.md` and the standing V2 MF4 scope, V4 must close all 5 BLK and all 6 NB such that a junior implementer can write the reachability module and the MF4 admission tests from this document alone.
3. Expected observable change: after implementation, `tests/vivarium/test_l2_2_metabolism_mf4_admission.py` should be able to assert that sample `(seed=0, tick=1)` either produces a jointly verified `k` with Top-17 actual-writeback agreement on at least `14/17` WIDs inside tolerance or returns a structured infeasibility object naming the blocking WIDs / active bounds, while `tests/vivarium/l2_2_metric_selector.py::select_metric_family` derives `degeneracy_sensitivity` from numerics on every call.
4. Beat-4 inversion: V4 could still look "complete" while being wrong if the LP is specified against a pre-round surrogate and the implementation treats LP feasibility as admission without running the real writeback verification; or if a cached `degeneracy_label` is smuggled back into the audit schema and silently bypasses the numeric rubric.
5. PM sanity-check: I am assuming the authoritative behavior for MF4 is "prove joint reachability or fail closed," not "approximate V3's per-WID evidence more carefully"; if MF4 is supposed to admit on partial joint evidence, this design is too strict.

## 1) Design Contract

Contract:
- Required behavior: classify Metabolism as `lp_degenerate` from stored numeric audit inputs, then gate MF4 admission on one jointly feasible biomass-fixed perturbation problem plus a verified invariant / mutation suite rather than on per-WID marginal LPs or stored labels.
- Why this matters: the Day-40 postmortem and the V3 critique agree that the remaining metabolism gap sits on a highly degenerate LP where solver-family vertex choice is real, but V3 still failed to prove the Karr residual is jointly reachable from OC's vertex.
- Done = a system property: the implemented MF4 path can only emit `CONDITIONAL_PASS_LP_DEGENERATE` when the selector recomputes `degeneracy_sensitivity` from numeric inputs, the sample `(0,1)` joint LP plus actual-writeback verification succeeds on the Top-17 residual simultaneously, invariants `I1/I2/I3/I4/I5a/I6` all pass on the candidate, and mutations `M1-M9` each trip exactly their designated invariant on the pinned baseline.

Beat-4 inversion:
- Most plausible "looks right, is wrong" failure mode: the implementation satisfies the literal acceptance text by solving a relaxed LP with slack, sees a small objective, and treats that as admission even though no actual `v + alpha*k` passed the real writeback verification.
- What would falsify this contract statement: any implementation that can emit `CONDITIONAL_PASS_LP_DEGENERATE` while the selector accepts a stored derived label, while the actual writeback misses the Top-17 tolerance budget, or while one of the designated mutation fixtures does not fire its assigned invariant.

## 2) Inventory Of Existing Artifacts

- [A01] path=docs/phase_f/L2_2_DESIGN_V3_CRITIQUE.md | kind=doc | role=primary V4 spec authority; content check: opened critique and verified the 11 acceptance criteria block plus BLK-V3-1..5 and NB-V3-1..6 details are present.
- [A02] path=docs/phase_f/L2_2_METABOLISM_LP_DEGENERATE_DESIGN.md | kind=doc | role=V2 baseline contract being revised, including original MF4 scope and worked Metabolism example; content check: opened V2 and verified it currently defines the MF4 admission rule, invariant suite, and null-space perturbation narrative.
- [A03] path=docs/phase_f/L2_2_METABOLISM_LP_DEGENERATE_DESIGN_V3_PATCHES.md | kind=doc | role=prior failed attempt / patch chain; content check: opened V3 and verified P1-P7 still rely on per-WID LPs, deferred I5b, and enum validation rather than runtime-derived labels.
- [A04] path=docs/phase_f/L2_2_METRIC_BY_PROCESS_CHARACTER_DESIGN.md | kind=doc | role=standing V1 contract for MF0/MF1/MF2/MF3/MF5; content check: verified the existing top note already limits supersession to MF4.
- [A05] path=docs/phase_f/METABOLISM_POSTMORTEM_DAY40.md | kind=doc | role=records the five RCs and the solver / degeneracy facts motivating MF4; content check: verified `cond=6.7e+12`, `8` unbounded reactions, variant-family facts, and the "port the full FBA discipline" lesson.
- [A06] path=docs/phase_f/METABOLISM_GAP_MAP.md | kind=doc | role=empirical anchor for the 500-sample gap, Top-17 / Top-27 WIDs, and cluster concentration; content check: verified mean writeback error `22409`, algorithm floor `40`, and the Top-17 WID set used by V4.
- [A07] path=opencell/m1/karr_metabolism.py | kind=code | role=current FBA solve surface and objective semantics; content check: verified `solve_fba` supports `highs` and `glpk`, uses the full `model.obj` by default, and documents biomass at FBA column `502` (0-based).
- [A08] path=opencell/m1/karr_metabolism_writeback.py | kind=code | role=current actual writeback algorithm used for verification; content check: verified the code implements Step 1 external uptake, Step 2 internal exchange, Step 3 biomass production, Step 4 unaccounted energy, and Step 5 metabolite clipping.
- [A09] path=data/karr_fixtures/per_process/Metabolism_flat.mat | kind=fixture | role=fixture authority for the LP and writeback matrices; content check: loaded `data.fixture` and verified `fbaReactionStoichiometryMatrix (376,504)`, `fbaObjective (504,)`, `fbaReactionBounds (504,2)`, `metabolismNewProduction (585,3)`, `reactionNames (645,)`, and `substrateNames (585,)`.
- [A10] path=data/karr_fixtures/matlab_ground_truth/metab_flux_allocated_state_s000_tick1.mat | kind=fixture | role=single-sample ground truth for `(seed=0,tick=1)`; content check: opened the v7.3 HDF5 file and verified datasets `flux (1,504)`, `bounds (2,504)`, `delta (3,585)`, `growth (1,1)`, `pre_sub (3,585)`, and `post_sub (3,585)`.
- [A11] path=data/schemas/per_process/metabolism.toml | kind=schema | role=observable surface anchor for substrates / enzymes and the trace fixture path; content check: verified `observables.substrates shape=[3,585]`, `pass_through=["boundEnzymes","enzymes"]`, and `trace_file=.../Metabolism_100ticks.mat`.
- [A12] path=tests/vivarium/l2_2_design_a_runner.py | kind=code | role=current L2.2 runner boundary that will consume the future selector verdict; content check: verified it still computes scalar W1 / threshold channel verdicts and currently has no MF4-specific selector hook.

Inventory Beat-4 inversion:
- What critical artifact could still be missing from this list? A pre-existing selector contract file if one exists outside `tests/vivarium`; `rg --files tests/vivarium | rg 'l2_2_metric_selector'` returned no current selector file, so V4 treats that as a new implementation target rather than a missed source.
- What check did you run to reduce that risk? I verified the named local sources from the prompt, loaded both MATLAB artifacts far enough to confirm non-placeholder contents, and checked the current test tree for an existing selector surface.
- What could be wrong in the artifacts we listed? The fixture and ground-truth files can still be semantically stale relative to newer extractions even when they load cleanly; V4 therefore treats them as the pinned local contract for this design pass and forbids new MATLAB extraction during this task.

## 3) Interaction-Surface Map

| Surface ID | Producer | Consumer | Contract unit | Failure if mismatched | Evidence anchor |
|---|---|---|---|---|---|
| S1 | `data/l2_2_audits/metabolism.yaml` numeric audit record | `tests/vivarium/l2_2_metric_selector.py::select_metric_family` | scalar numeric fields only; process identity comes from filename / registry, no derived labels in payload | stale / manual family routing bypasses the rubric | A01, A12 |
| S2 | selector verdict payload | `tests/vivarium/l2_2_design_a_runner.py` | stable verdict enum plus structured telemetry | runner silently falls back to V1 or string-parses suffixes | A01, A12 |
| S3 | `opencell/m1/karr_metabolism.py::solve_fba` output `(v,obj)` | future `opencell/m1/metabolism_mf4_reachability.py` | `v` length `504`, full objective `c`, bounds `lb/ub`, biomass column index | reachability LP tests a different feasible region than the solver actually uses | A07, A09 |
| S4 | `data/karr_fixtures/per_process/Metabolism_flat.mat` fixture matrices | reachability linearization builder and actual writeback verifier | matrix shapes / index order for LP rows, reaction columns, substrate rows | Jacobian / affine map is built against wrong order or wrong compartment convention | A08, A09 |
| S5 | sample ground truth `metab_flux_allocated_state_s000_tick1.mat` | precheck, LP target builder, verification test | Karr `flux`, `bounds`, `delta`, `growth`, `pre_sub`, `post_sub` for sample `(0,1)` | the admission probe compares OC against the wrong target state or wrong sample | A10 |
| S6 | mutation constructors | invariant evaluators `I1/I2/I3/I4/I5a/I6` | pinned baseline deltas and family-group bins | a mutation is said to prove a catcher but actually fires none or the wrong invariant | A01, A06 |
| S7 | `data/schemas/per_process/metabolism.toml` | selector and MF4 harness | output surface name / tensor shape / pass-through observables | MF4 evaluates the wrong channel or mis-shapes the baseline tensors | A11 |
| S8 | reviewed LP-nondegenerate mapping in CI | selector tests / audit review | explicit allowlist keyed by process name | a future `lp + {none,low}` record slips in without re-audit | A01 |
| S9 | structured MF4 verdict | downstream report / status emission | `verdict`, `deferred_invariants`, `telemetry`, optional failure object | string suffix parsing reintroduces schema drift and hides deferred invariants | A01, A12 |

Interaction Beat-4 inversion:
- Which cross-surface assumption is most likely false? The assumption that the LP row / column order in `solve_fba` and the `Metabolism_flat.mat` fixture can be joined without an explicit mapping step.
- What observation would expose that quickly? A first implementation that reproduces Karr flux feasibility but yields obviously wrong Top-17 writeback targets or shape mismatches should be treated as a row/column-order bug before any LP reasoning is trusted.

## 4) Baseline Facts And Constraints

1. Hard constraints from this task:
   1. No code, fixture, or test modifications in this turn; only design docs and redirect notes may change.
   2. No external fetches, no new MATLAB extraction, and no re-run of the L2.2 audit.
   3. V4 must be a consolidated design, not another patch-against-V3.
2. Spec hierarchy:
   1. `docs/phase_f/L2_2_DESIGN_V3_CRITIQUE.md` is authoritative for V4.
   2. V2 remains the baseline MF4 contract except where V4 replaces it.
   3. V3 is fully superseded rather than partially inherited.
   4. V1 remains authoritative for MF0 / MF1 / MF2 / MF3 / MF5.
3. Existing implementation facts:
   1. `solve_fba` already exposes the full `model.obj`, `lb`, `ub`, and a GLPK backend suitable for the same solver family as Karr.
   2. `apply_karr_substrate_writeback` already provides the normative actual writeback path V4 wants the admission probe to verify against.
   3. `Metabolism_flat.mat` already contains the stoichiometry, bounds, objective, substrate indices, and biomass-production matrices needed to build an affine pre-round surrogate.
   4. The sample ground-truth file already pins a single reference flux / bounds / delta tuple for `(seed=0,tick=1)`.
4. Known failures and anti-patterns that V4 must remove:
   1. Per-WID marginal LPs are not evidence of joint reachability.
   2. A Jacobian that passes through `stochastic_round` and clipping without stating the surrogate is undefined.
   3. `c · k = 0` alone does not keep biomass fixed when small parsimony coefficients are present.
   4. "Mass-only" in V3 actually means total molecule count; that wording was overstated.
   5. Stored degeneracy labels and suffix verdict strings are schema traps because they can go stale silently.
   6. A prose-only re-audit trigger and a deferred M7 proof are not enforceable gates.

Baseline Beat-4 inversion:
- Which baseline "fact" is inferred rather than proven? That sample `(0,1)` remains the right single-sample admission probe after V4, rather than only a historical convenience.
- What would invalidate it? If an implementation shows `(0,1)` is uniquely clip-dominated or otherwise non-representative relative to the rest of the 50x100 trace, V4 would need one confirmatory sample rather than changing the LP design itself.

## 5) Decision Ledger

Decision D1
- Question: How should V4 test whether Karr's Top-17 residual is jointly reachable from OC's flux vertex?
- Options considered:
  1) Keep V3's per-WID LPs and interpret the count heuristically.
  2) Solve one joint LP with shared `k` and zero-slack pass criterion, then demote per-WID LPs to diagnostics.
  3) Skip LP structure and rely on null-space random search.
- Chosen option: 2.
- Rationale: one perturbation vector `k` must explain the full 17-WID target simultaneously or MF4 has not proved "vertex choice" at all. V4 uses one shared decision vector `k in R^504` and per-WID nonnegative slack variables `s_j` on the Top-17 set:
  `min sum_j (s_j / tau_j)` subject to `S k = 0`, `e_biomass·k = 0`, `c·k = 0`, `lb-v <= k <= ub-v`, and `-tau_j - s_j <= (a_j + J_j k) - target_j <= tau_j + s_j` for each Top-17 WID `j`.
  Pass = objective exactly `0`, meaning every Top-17 WID is simultaneously inside tolerance with one `k`.
  Fail = objective `> 0` or solver infeasible; in either case the returned failure object must include `per_wid_slack`, `active_bounds`, and the Top-17 WIDs sorted by normalized miss. Per-WID LPs may run only after joint fail as diagnostics.
- Tradeoffs accepted: this is stricter than V3 and may reject some cases V3 would have described as "mostly reachable," but that strictness is the point of BLK-V3-1.
- Beat-4 inversion (how chosen option could be wrong): the implementation could accidentally solve the relaxed slack LP and treat "small objective" as success, which recreates a softer heuristic in disguise.
- Falsifier (what evidence would force reopening D1): a verified implementation that cannot get objective `0` on `(0,1)` but a stronger exact formulation proves joint reachability anyway.
- Operator escalation needed? no

Decision D2
- Question: Which linearization choice should define the LP target map through writeback?
- Options considered:
  1) Pre-round continuous surrogate only, with no mandatory verification.
  2) MILP that models rounding exactly.
  3) Pre-round continuous surrogate for candidate generation, with the actual writeback as the normative verifier.
- Chosen option: 3, implemented with the pre-round surrogate from option 1.
- Rationale: the actual writeback in `karr_metabolism_writeback.py` is affine in `v` before stochastic rounding and clipping. Under `e_biomass·k = 0`, Steps 3 and 4 are constant offsets because growth stays fixed; only Steps 1 and 2 vary with `k`. V4 therefore linearizes only the pre-round, pre-clip map to generate a candidate `k`, then requires the real `apply_karr_substrate_writeback` path to validate it. Verification is non-optional and uses fixed line-search alphas `1.0, 0.75, 0.5, 0.25, 0.10, 0.05, 0.01` along the LP direction. Admission accepts the best `alpha` only if the actual writeback at `v + alpha*k` keeps all Top-17 WIDs inside `tau_j` simultaneously; otherwise the LP result is rejected as an unverifiable surrogate artifact.
- Tradeoffs accepted: V4 declines the mathematical neatness of a MILP in exchange for an auditable surrogate plus a mandatory reality check.
- Beat-4 inversion (how chosen option could be wrong): a junior implementer may read "pre-round surrogate" and silently drop the actual-writeback verification because the LP already returned a `k`.
- Falsifier (what evidence would force reopening D2): repeated verification failures on candidate `k` where a bounded MILP or exact-search prototype succeeds, indicating the surrogate is too weak to serve even as candidate generation.
- Operator escalation needed? no

Decision D3
- Question: How should V4 preserve the intended "same biomass-fixed optimal face" claim?
- Options considered:
  1) Keep only `c · k = 0`.
  2) Keep only `e_biomass · k = 0`.
  3) Enforce both `e_biomass · k = 0` and `c · k = 0`.
- Chosen option: 3.
- Rationale: `e_biomass · k = 0` prevents growth drift directly, while `c · k = 0` preserves the full 36-nonzero objective semantics already used by `solve_fba`. V4 therefore treats biomass preservation and objective-face preservation as distinct constraints and requires both in the LP. Precheck and reporting must use the same post-bound conventions as the solver, with objective equivalence measured as `|c·v_oc - c·v_karr| / max(|c·v_karr|, 1) < 1e-9`.
- Tradeoffs accepted: the feasible region is narrower than a generic optimal-face motion, but it matches the actual claim V2 was trying to make.
- Beat-4 inversion (how chosen option could be wrong): an implementation could enforce both equalities in the LP builder but verify only one of them in the returned telemetry, hiding an accidental drop of the other in refactors.
- Falsifier (what evidence would force reopening D3): proof that Karr's recorded residual requires biomass drift while preserving the full objective, which would mean the original MF4 explanation itself was misstated.
- Operator escalation needed? no

Decision D4
- Question: How should the admission precheck talk about `v_oc` versus `v_karr` before the joint LP runs?
- Options considered:
  1) Keep V3's "OC is sub-optimal" wording on failure.
  2) Broaden failure into model mismatch / feasibility / tolerance categories and add Karr-flux feasibility first.
  3) Drop the precheck entirely and let the joint LP sort it out.
- Chosen option: 2.
- Rationale: V4 requires two prechecks in order. First, verify `v_karr` itself is feasible under the same `S`, `RHS`, `lb`, and `ub` used for `v_oc`; failure returns `AUDIT_LP_MODEL_MISMATCH`. Second, only if feasible, compare the full objective values and return `AUDIT_OPTIMAL_FACE_MISMATCH` when the relative difference exceeds `1e-9`. This wording is broader and honest: failure means objective, bounds, solver semantics, or numerical tolerance differ, not automatically that OC is "sub-optimal."
- Tradeoffs accepted: more failure categories mean slightly more implementation work up front, but they prevent false stories about what went wrong.
- Beat-4 inversion (how chosen option could be wrong): implementers may reuse the old message text in one call path, making the design look updated while the error taxonomy remains misleading.
- Falsifier (what evidence would force reopening D4): a future source audit showing Karr's stored flux intentionally violates the extracted bounds in a way that should still count as admissible.
- Operator escalation needed? no

Decision D5
- Question: What is the authoritative audit schema and label-derivation rule for MF4 routing?
- Options considered:
  1) Keep storing `degeneracy_sensitivity` and validate only enum membership.
  2) Store numeric inputs plus metadata only, compute `degeneracy_sensitivity` at load time, and fail closed if any derived-label field is present.
  3) Store both numeric inputs and cached labels, but compare them.
- Chosen option: 2.
- Rationale: the audit payload in `data/l2_2_audits/metabolism.yaml` must contain only the numeric rubric inputs `condition_number`, `nullity_ratio`, `unbounded_non_biomass_reactions`, `objective_value_oc`, and `objective_value_karr`. Process identity comes from the file name / reviewed registry, and solver-family review state comes from the selector-side registry rather than the numeric payload. Forbidden fields are `degeneracy_sensitivity`, `degeneracy_label`, `metric_family`, and any other derived routing label. `select_metric_family` must recompute `degeneracy_sensitivity` on every load and raise `AUDIT_DERIVED_LABEL_FORBIDDEN` if any forbidden field is present. There is no cache path.
- Tradeoffs accepted: selector calls do a tiny amount of repeated math, but the design removes an entire class of stale-routing errors.
- Beat-4 inversion (how chosen option could be wrong): someone may add a hidden debug field like `derived_family_debug` and later another caller starts trusting it.
- Falsifier (what evidence would force reopening D5): a demonstrated need for offline audit interchange where derived labels are required and cannot be reconstructed from the numeric fields.
- Operator escalation needed? no

Decision D6
- Question: How should V4 redesign the invariant suite around BLK-V3-4, NB-V3-3, and NB-V3-4?
- Options considered:
  1) Keep V3's naming and tail budget, with a sign test for I6.
  2) Rename I5a honestly, reassign M3/M5 to I3/I4, add aggregate tail caps, and replace I6 with a directional magnitude test.
  3) Make I5b mandatory now and postpone V4 until elemental metadata exists.
- Chosen option: 2.
- Rationale: V4 defines six gating invariants:
  `I1 aggregate_signed_flux_magnitude`,
  `I2 per_wid_signed_delta_residual_budget`,
  `I3 pathway_level_flux_distributions`,
  `I4 dominant_wid_joint_structure`,
  `I5a total_count_conservation`,
  `I6 directional_magnitude_bias`.
  `I5a` is explicitly total-count only and is no longer claimed to catch M3/M5. `M3` is assigned to `I3`; `M5` is assigned to `I4`; empirical proof is mandatory. `I2` keeps the Top-27 hard-fail but now adds three tail caps: tail breach count `<= 29`, tail absolute residual sum `<= max(40, 0.01 * baseline_tail_total)`, and no one family bin may contribute more than `50%` of tail breaches or tail residual mass. `I6` computes `d_w = (candidate_delta_w - baseline_delta_w) * sign(baseline_delta_w)` on eligible WIDs with `|baseline_delta_w| > 1`; it fails if at least `80%` of eligible WIDs have `d_w < 0` (coherent under-flux) or at least `80%` have `d_w > 0` (coherent over-flux).
- Tradeoffs accepted: `I5b` remains deferred, so V4 relies on pathway and joint-structure invariants rather than claiming elemental coverage it cannot yet implement.
- Beat-4 inversion (how chosen option could be wrong): the mutation constructors could be sloppy enough that M3 or M5 also trip unrelated invariants, letting the suite "pass" without really proving the intended reassignment.
- Falsifier (what evidence would force reopening D6): a pinned-baseline mutation study where M3 cannot be isolated to I3 or M5 cannot be isolated to I4 despite careful construction.
- Operator escalation needed? no

Decision D7
- Question: What mutation-to-invariant matrix should MF4 admission require?
- Options considered:
  1) Keep V3's loose "at least one fails" rule.
  2) Require exact designated catcher(s) with M7 promoted from deferred to admission gate.
  3) Drop the mutation suite from admission and treat it as post-admission regression only.
- Chosen option: 2.
- Rationale: V4 names one designated catcher per mutation and requires the pinned-baseline fixture to show exactly that invariant fires and the non-designated invariants stay within tolerance for the constructed mutation. The matrix is:
  `M1 -> I2`, `M2 -> I2`, `M3 -> I3`, `M4 -> I2`, `M5 -> I4`, `M6 -> I1`, `M7 -> I2`, `M8 -> I4`, `M9 -> I6`.
  `M7` is no longer deferred; admission is blocked until the exact tick-shift mutation provably fails `I2`.
- Tradeoffs accepted: mutation construction becomes more disciplined because "good enough to fail something" is no longer acceptable.
- Beat-4 inversion (how chosen option could be wrong): reviewers may check only that the mutation file exists and not that each mutation isolates its intended catcher.
- Falsifier (what evidence would force reopening D7): a reproducible case where a mutation cannot be constructed to isolate its designated catcher without violating the biological meaning of the mutation.
- Operator escalation needed? no

Decision D8
- Question: How should the MF4 verdict be encoded for downstream consumers?
- Options considered:
  1) Keep a string suffix such as `CONDITIONAL_PASS_LP_DEGENERATE[I5b_deferred]`.
  2) Use a stable enum plus structured `deferred_invariants` and `telemetry`.
  3) Return only booleans and let the runner invent labels.
- Chosen option: 2.
- Rationale: success verdict payload shape is:
  `{ "verdict": "CONDITIONAL_PASS_LP_DEGENERATE", "deferred_invariants": ["I5b"], "telemetry": { "joint_lp_objective": 0.0, "verified_alpha": <float>, "top17_pass_count": <int>, "audit_metrics": {...}, "mutation_matrix_version": "v4" } }`.
  Failure payloads must keep the same top-level shape but use a rejecting enum and include a structured `failure` object rather than string suffixes. This stays parseable and makes deferred invariants explicit without rewriting enum consumers.
- Tradeoffs accepted: downstream code must read a small structured payload instead of a single string.
- Beat-4 inversion (how chosen option could be wrong): a caller might still parse the old suffix pattern out of habit and ignore `deferred_invariants`.
- Falsifier (what evidence would force reopening D8): an unavoidable downstream contract that can only accept a single flat string and cannot be changed.
- Operator escalation needed? no

Decision D9
- Question: How should V4 make the future re-audit trigger enforceable?
- Options considered:
  1) Keep a prose note that future `lp + {none,low}` cases require review.
  2) Add a named CI assertion with an explicit reviewed allowlist.
  3) Ignore the edge until another LP process appears.
- Chosen option: 2.
- Rationale: V4 requires `tests/vivarium/test_l2_2_metric_selector.py::test_lp_none_or_low_requires_reviewed_mapping`. The test must fail whenever any process whose reviewed solver family is LP computes `degeneracy_sensitivity in {"none","low"}` from its numeric audit payload unless the process name appears in a checked-in allowlist such as `REVIEWED_LP_NONDEGENERATE_PROCESSES`. This turns NB-V3-2 into an enforceable gate instead of review folklore.
- Tradeoffs accepted: adding a new LP process now requires touching both the audit file and the allowlist / test expectation.
- Beat-4 inversion (how chosen option could be wrong): a team member could add the process to the allowlist without actually performing the review.
- Falsifier (what evidence would force reopening D9): a later harness design that replaces process-name allowlists with a stronger machine-reviewed audit registry.
- Operator escalation needed? yes + QO5

## 6) Expected Outcomes And Verification Claims

Claim C1:
- If design is correct, we should observe: `select_metric_family("Metabolism")` cannot consume any stored degeneracy label because the audit file schema forbids it and the selector recomputes from numerics every time.
- Measurement method / command / assertion: a selector test injects an audit record containing `degeneracy_sensitivity: lp_degenerate` and asserts `AUDIT_DERIVED_LABEL_FORBIDDEN`.
- Threshold or exact value: hard failure whenever any forbidden field is present.
- Why this distinguishes from alternatives: V3-style enum validation would let the same record load and silently route MF4.

Claim C2:
- If design is correct, we should observe: sample `(0,1)` passes the precheck only when `v_karr` is feasible under the extracted LP and the full-objective relative mismatch is below `1e-9`; otherwise the failure taxonomy names `AUDIT_LP_MODEL_MISMATCH` or `AUDIT_OPTIMAL_FACE_MISMATCH`.
- Measurement method / command / assertion: `pytest tests/vivarium/test_l2_2_metabolism_mf4_admission.py::test_sample_0_1_precheck`.
- Threshold or exact value: `|c·v_oc - c·v_karr| / max(|c·v_karr|, 1) < 1e-9`, with a separate boolean feasibility assertion on `v_karr`.
- Why this distinguishes from alternatives: a simple "OC is sub-optimal" assertion cannot tell model mismatch from objective mismatch.

Claim C3:
- If design is correct, we should observe: the joint LP on `(0,1)` returns either objective `0` and a verified `alpha*k` whose actual writeback matches Karr on at least `14/17` Top-17 WIDs within tolerance, or a failure object with non-zero `per_wid_slack` and the sorted bottleneck WIDs.
- Measurement method / command / assertion: `pytest tests/vivarium/test_l2_2_metabolism_mf4_admission.py::test_joint_lp_reachability_sample_0_1`.
- Threshold or exact value: success requires LP objective `0.0` and actual-writeback Top-17 pass count `>= 14`; failure requires a non-empty structured diagnostic object.
- Why this distinguishes from alternatives: a per-WID LP implementation can pass the old V3-style diagnostics while still failing the simultaneous Top-17 target.

Claim C4:
- If design is correct, we should observe: the mutation suite on the pinned baseline yields exactly one designated invariant failure per mutation `M1-M9`.
- Measurement method / command / assertion: `pytest tests/vivarium/test_l2_2_metabolism_mf4_admission.py::test_mutation_assignment_matrix`.
- Threshold or exact value: for each mutation, one and only one designated invariant failure; zero false negatives and zero off-target failures.
- Why this distinguishes from alternatives: a basic "some invariant failed" suite would still let the M3/M5 reassignment hole ship unnoticed.

Claim C5:
- If design is correct, we should observe: CI fails the first time any process whose reviewed solver family is LP computes sensitivity `none` or `low` unless a reviewed mapping is added deliberately.
- Measurement method / command / assertion: `pytest tests/vivarium/test_l2_2_metric_selector.py::test_lp_none_or_low_requires_reviewed_mapping`.
- Threshold or exact value: hard fail on any unmapped process with reviewed LP solver family and computed sensitivity in `{none, low}`.
- Why this distinguishes from alternatives: prose-only warnings cannot stop schema drift.

Expected-outcomes Beat-4 inversion:
- How could these claims pass while design is still wrong? A shallow implementation could hard-code the sample `(0,1)` outcome or overfit the mutation fixtures while leaving the real runner / selector wiring inconsistent.
- Additional guardrail to close that hole: require the selector tests to load the real audit file path, require the admission tests to build targets from the real fixture / ground-truth artifacts, and require the mutation matrix test to use the same invariant evaluator entry points the runner will call.

## 7) Open Questions For Operator

QO1. Should the admission implementation expose a diagnostic secondary backend (for example HiGHS) alongside the normative GLPK path?
- Why unresolved: V4 only needs a normative contract, but implementers may want a side-by-side diagnostic backend while debugging the joint LP.
- Options:
  1) GLPK only in admission code.
  2) GLPK normative plus optional diagnostic backend.
- Recommended default (if no response): 2, but diagnostics must never change the admission verdict.
- Risk if wrong: a single-backend implementation may be harder to debug, while a multi-backend implementation may tempt people to treat backend disagreement as admissible ambiguity.

QO2. Should the Top-17 set be frozen exactly to the current Day-40 list or recomputed from the pinned baseline when implementation lands?
- Why unresolved: the critique and gap map anchor the current set, but a pinned-baseline implementation could want a mechanically regenerated list.
- Options:
  1) Freeze the Day-40 Top-17 list in code.
  2) Recompute Top-17 from the pinned baseline with the Day-40 list as the initial expected result.
- Recommended default (if no response): 2, with a test that `(0,1)` still regenerates the same list before any generalization is accepted.
- Risk if wrong: freezing could fossilize a stale target set; recomputing without a pin could make the target drift silently.

QO3. Is the line-search budget of seven fixed alphas enough, or should implementation escalate to a bounded local search when all seven fail?
- Why unresolved: seven points are easy to audit, but a bounded local search could recover some candidates rejected only by rounding thresholds.
- Options:
  1) Fixed seven-alpha grid only.
  2) Seven-alpha grid, then one bounded local search fallback before final rejection.
- Recommended default (if no response): 1 for the first implementation; reopen only if the fixed grid fails often on honest candidates.
- Risk if wrong: too small a budget may reject reachable cases, while too much search may turn admission into a tuning exercise.

QO4. Should the tail family-concentration cap be enforced by breach count, residual mass, or both?
- Why unresolved: the critique asked for family-concentration caps but did not force one exact formulation.
- Options:
  1) Count cap only.
  2) Residual-mass cap only.
  3) Both count and residual-mass caps.
- Recommended default (if no response): 3, because it closes both sparse-concentrated and heavy-concentrated failure patterns.
- Risk if wrong: a single-cap design can miss biologically concentrated but numerically sparse tail failures.

QO5. Where should the reviewed LP-nondegenerate allowlist live?
- Why unresolved: V4 requires the assertion, but not the exact storage module.
- Options:
  1) Keep it as a constant inside `tests/vivarium/test_l2_2_metric_selector.py`.
  2) Store it in a small checked-in registry file that the selector tests read.
- Recommended default (if no response): 2, because review metadata is easier to audit when it is not buried in one test module.
- Risk if wrong: hiding the allowlist in test code makes future review weaker and easier to bypass.

## 8) Scope Boundary

In scope:
1. The consolidated MF4 design contract for Metabolism LP degeneracy.
2. The joint reachability LP formulation, linearization choice, and mandatory actual-writeback verification.
3. The numerics-only audit schema, selector behavior, and CI re-audit assertion.
4. The invariant suite, mutation-to-invariant assignment matrix, and structured verdict schema.
5. Redirect notes that mark V2 and V3 historical rather than normative.

Out of scope:
1. Any changes to MF0, MF1, MF2, MF3, or MF5.
2. Any code implementation, new fixtures, MATLAB extraction, or audit rerun during this task.
3. Any redesign of the underlying metabolism solver or writeback algorithm beyond specifying how MF4 will consume them.
4. Any new non-Metabolism process mapping.

Deferred follow-ups:
1. Wiring `I5b` elemental composition data into the L2.2 layer.
2. Generalizing the admission proof beyond sample `(0,1)` after the single-sample gate works.
3. Reconsidering MILP / stronger candidate generation only if the surrogate-plus-verification path proves insufficient.

Scope Beat-4 inversion:
- Most likely scope-creep vector: trying to fix solver behavior or rewrite writeback code while authoring V4, because those are the tempting concrete pieces.
- How this doc prevents it: V4 specifies the future implementation surfaces and gate conditions, but it does not edit or bless any immediate code changes.

## 9) Migration And Rollout Path

1. Strategy: hybrid replacement. The docs switch immediately to V4 as the normative MF4 contract, while implementation rolls out in parallel and the current runner continues to use V1 behavior for all processes until the MF4 gate is actually implemented.
2. Sequence of steps:
   1. Land V4 plus the redirect notes on V2 and V3.
   2. Implement `opencell/m1/metabolism_mf4_reachability.py` and `tests/vivarium/test_l2_2_metabolism_mf4_admission.py`.
   3. Implement `tests/vivarium/l2_2_metric_selector.py` plus `tests/vivarium/test_l2_2_metric_selector.py`.
   4. Add the sample `(0,1)` precheck, joint LP, line-search verification, and structured failure object.
   5. Add the invariant evaluator and exact mutation-assignment matrix.
   6. Only after all gates pass, create `data/l2_2_audits/metabolism.yaml` with numerics only and enable the runner to emit the MF4 verdict for Metabolism.
3. Backout trigger and backout method:
   1. Trigger: any of `C1-C5` fails, especially failed actual-writeback verification, mutation misassignment, or selector schema drift.
   2. Method: keep the selector returning `DEFER_TO_V1_NON_MF4` for Metabolism and leave the audit file absent rather than widening tolerances or caching labels.
4. Compatibility period:
   1. V1 remains active for all non-MF4 families without change.
   2. V2 and V3 remain on disk only as historical references once this document lands.

Migration Beat-4 inversion:
- How migration could strand partially-updated code: the selector could be introduced before the joint LP / invariant gate exists, causing a new route token with no trustworthy admission logic behind it.
- Checkpoint or guard to detect that state: Metabolism must not receive an audit file or selector entry until the admission tests and mutation matrix tests exist and pass together.

## 10) Risks And Residual Unknowns

R1. The pre-round surrogate may still be too optimistic near clip boundaries.
- Likelihood: medium
- Impact: high, because it could create false LP optimism.
- Detection: candidate `k` repeatedly fails actual-writeback verification even when LP objective is `0`.
- Mitigation: treat verification failure as hard rejection; reopen D2 only with evidence.
- Owner: implementer + reviewer

R2. Sample `(0,1)` may be unusually favorable or unfavorable for the admission proof.
- Likelihood: medium
- Impact: medium
- Detection: future cross-sample spot checks disagree sharply with the `(0,1)` conclusion.
- Mitigation: add one confirmatory sample without weakening the `(0,1)` gate.
- Owner: operator

R3. Exact mutation isolation may be harder than the design expects.
- Likelihood: medium
- Impact: high, because BLK-V3-4 and NB-V3-6 rely on empirical proof.
- Detection: one mutation keeps tripping off-target invariants in the pinned-baseline fixture.
- Mitigation: refine the mutation constructor; if isolation is impossible, reopen D6/D7 instead of hand-waving.
- Owner: implementer

R4. The future audit registry could drift if someone adds convenience fields.
- Likelihood: medium
- Impact: medium
- Detection: selector forbidden-field tests start failing.
- Mitigation: keep the schema small and fail closed on any derived-label field.
- Owner: selector maintainer

R5. `I5b` remains deferred, so V4 still relies on pathway and joint-structure evidence rather than elemental totals.
- Likelihood: certain
- Impact: medium
- Detection: mutation studies find a biologically wrong redistribution that slips past `I3/I4/I5a/I6`.
- Mitigation: keep `I5b` in `deferred_invariants` and do not claim full elemental coverage.
- Owner: operator + future implementation task

## 11) Operator Review Checklist

1. Confirm the authoritative V3-critique quote appears before any Beat content and that V4 is clearly a consolidated replacement, not another patch series.
2. Confirm the inventory names concrete artifacts, includes content checks for both MATLAB files, and records V3 as the prior failed attempt.
3. Confirm each major decision card includes options, chosen option, rationale, Beat-4 inversion, and a falsifier.
4. Confirm BLK-V3-1..5 and NB-V3-1..6 each have an explicit home in sections 5 or 6.
5. Confirm the scope stays MF4-only and does not redefine MF0 / MF1 / MF2 / MF3 / MF5.
6. Confirm the migration section prevents partial rollout by withholding the audit file / selector entry until the admission gate exists.
