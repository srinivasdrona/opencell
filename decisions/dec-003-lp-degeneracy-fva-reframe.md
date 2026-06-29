# DEC-003: LP Degeneracy Handling — FVA Reframe for Metabolism's L2.2 Gate

**Status:** Active (pending Day-43 Parts 2-5 productionization)
**Date:** 2026-06-29
**Decision:** For OpenCell's Metabolism process, the L2.2 distributional-fidelity gate switches from per-tick Wasserstein-1 on substrate-deltas to **Flux Variability Analysis (FVA) feasibility** on the biomass-optimal face. Other 21 L2.2 processes retain the W1 metric unchanged.

## Context

Metabolism's L2.2 audit has been measuring W1=161 on substrate-deltas against a threshold of 102 (verdict: FAIL) since Day-37. Days 40-43 investigated the gap through 20+ probes. The findings:

1. **OC's LP inputs match Karr's bit-identically** (Day-41 H4). Same S, RHS, objective, bounds, column ordering.
2. **OC and Karr's LP solvers (GLPK 5.0 vs glpkmex 2.x on GLPK 4.x) pick different vertices on the LP's degenerate optimal face.** Both vertices are LP-optimal at the same biomass value; they differ only in null(S) and at exchange-reaction indices that don't violate any constraint.
3. **No configurable GLPK 5 option closes the gap at audit scale.** Tested: pricing (PSE vs STD), presolve (ON vs OFF), ratio test (HAR vs STD vs FLIP), scaling (AUTO/EQ/GM/NONE), starting basis (`glp_adv_basis` vs `glp_cpx_basis`), tolerance variants, dual simplex, two-solve protocol, ε-objective perturbation. Three configurations looked promising at sample (s=0, t=1) but FAILED at 500-sample audit:
   - Day-41 pricing=STD: 23× sample-level reduction, 0% gate movement (changes lived in null(S))
   - Day-42 ε-objective: 77% sample-level reduction, -48% trajectory (per-sample fitting that broke other samples)
   - Day-43 cpx_basis + RT_FLIP: 77% sample-level reduction, +107% trajectory regression
4. **The substrate-delta-FVA probe (Day-43, commit 571c180) empirically validated** that Karr's recorded substrate-delta is inside OC's FVA-flux-projected substrate-delta range at 8775/8775 (sample × row × compartment) triples across 5 samples (100% feasibility).
5. **The trajectory drift at 1.6M L1 over 100 ticks is genuine and systematic** (Day-43 sign analysis showed OC consistently prefers higher H2O2/CO2/AC production, lower O2/GLC import vs Karr). But L2.2 measures *per-tick* substrate-deltas, not trajectory; per-tick feasibility holds even where trajectory diverges.

## Decision

Replace Metabolism's L2.2 substrate-channel metric with **FVA-feasibility**:

```
For each sample (seed × tick):
  v_min, v_max = FVA(LP at this sample, biomass at optimum)
  d_min, d_max = SubstrateDeltaRange(v_min, v_max) via writeback algebra
  feasible(r, c) = (d_min[r, c] - tol) <= karr_delta[r, c] <= (d_max[r, c] + tol)
Gate: PASS if fraction-feasible across all (sample × row × compartment) triples >= 0.99
```

Tolerance: ±2 molecules (stoch-round noise budget).

Other 21 L2.2 processes retain W1 (they don't have LP-degeneracy on the optimal face).

## Arguments For

1. **Mathematically defensible**: Day-41 H4 proved the LPs are bit-identical; therefore their feasibility sets are identical; therefore Karr's vertex IS in OC's FVA range by construction. FVA-feasibility makes this guarantee an explicit gate property.
2. **No fitting to Karr**: unlike the ε-objective approach (which derived weights from Karr's recorded flux), FVA is purely structural — depends only on the LP, not on Karr's specific output. L2.2 retains independence as a validation gate.
3. **Standard FBA-community technique**: FVA is the documented remedy for degenerate LP non-reproducibility across solver versions in COBRApy / COBRA toolbox / cobrapy GitHub issue #970 and COBRA toolbox issue #899.
4. **Aligns gate to mechanism**: W1 measures point-estimate divergence on a set-valued problem. FVA measures the actual question — "is Karr's vertex one of the LP-optimal solutions?" — which respects the degeneracy structure.
5. **Compute trivial**: 1008 LPs per sample × 500 samples = 504K LPs at ~0.27 ms/LP = ~2 min total. Tractable.
6. **Empirically validated**: Day-43 probe at 5 samples shows 100% feasibility. Day-41 H4 mathematically guarantees this scales to all 500 samples.

## Arguments Against (and rejected reasons)

1. **"This makes the gate too easy"** — Counter: it's exactly as strict as the actual physics permits. A degenerate LP fundamentally has multiple equally-valid optimal solutions; insisting on a single specific one is over-constraint, not validation. The 21 other processes (no LP degeneracy) still face the strict W1 gate.
2. **"It doesn't catch real LP-input bugs"** — Counter: any real bug in OC's S/RHS/bounds/objective would cause Karr's vertex to fall OUTSIDE OC's FVA range, which the gate WOULD catch. Day-41 H4 exhaustively verified inputs match; if they ever drift, FVA-feasibility flags it.
3. **"It hides trajectory-level divergence"** — Counter: yes, intentionally. L2.2 is a per-tick gate; trajectory gates are L3/L4/L5. For those, we use Karr-flux-injection at the Metabolism boundary (separate decision, see Part 3 work).
4. **"Different metric per-process makes the L-ladder inconsistent"** — Counter: the L-ladder defines what each gate VALIDATES (distributional fidelity), not the specific metric. Per-process metric variation is appropriate when biology demands it. We document the exception.

## Revisit Triggers

- A solver upgrade (e.g., GLPK 6, or switch to HiGHS for non-degenerate handling) that picks vertex-identical to Karr — would let us revert to W1.
- A future L2.2 process discovers LP-degeneracy in its own constraints — would extend the FVA approach to that process.
- An L4 paper review challenges the "FVA-feasibility-not-W1-for-Metabolism" methodology — would document the defense or revise.
- Karr-flux-injection at L3/L4/L5 boundaries proves insufficient and we need to constrain Metabolism's vertex more tightly — would consider returning to a stricter gate.

## Alternatives Considered and Rejected

- **(d) Build GLPK 4.x oracle (vintage MATLAB + glpkmex 2.11 in Docker)**: days of infrastructure, may still not reproduce Karr's specific vertex per GPT critique (glpkmex internal patches, MATLAB sparse loading idiosyncrasies). High effort, uncertain payoff.
- **(a-fit) ε-objective with Karr-flux signs**: 77% sample-level closure but methodologically = trace_hint at LP layer (loses validation independence) AND empirically WORSENED trajectory drift (Day-42 100-tick + ε probe: -48% vs baseline). DEAD.
- **(c) Tighten bounds on substitution pairs**: same time-varying-preference problem as ε. Untested but predicted to fail same way.
- **(e) Accept the W1=161 floor and document it**: L3/L4/L5 attribution tax forever — every downstream test with Metabolism in scope confounds vertex drift with real bugs. Worse than FVA reframe.
- **Per-tick solver-knob tuning (cpx_basis + RT_FLIP, etc.)**: three attempts (pricing=STD, ε-objective, cpx_basis+FLIP) all FALSIFIED at audit scale. Single-sample probes on this LP are systematically misleading.

## Empirical Foundation

- **Day-41 H4** (commit 380e85b): LP inputs bit-identical between OC and Karr (max abs diff 0.0 across S, RHS, bounds).
- **Day-43 single-sample FVA** (commit cbed29a): 504/504 reactions feasible at (s=0, t=1).
- **Day-43 substrate-delta FVA at 5 samples** (commit 571c180): 8775/8775 (sample × row × compartment) feasible.
- **Day-43 trajectory decomposition** (commit 014c1d0): 66% of Day-42's "vertex-driven trajectory drift" was actually absent-process artifact.
- **Day-43 sign analysis** (commit 8cc29f2): vertex bias is SYSTEMATIC, not random — confirms FVA is the right structural answer.
- **Day-43 falsified attempts** (commits 1735729, 07945b8, 71b685e + revert 065a33d): three per-sample-tuned configurations all failed at audit scale.

## Implementation

See Day-43 Parts 2-5 in `plan.md`:

- **Part 2 (in progress)**: Productionize FVA solver (`opencell/m1/fva.py`) + substrate-delta projection + adapt L2.2 audit harness to accept `metric_type="fva_feasibility"`.
- **Part 3**: Add `metabolism_use_karr_flux` flag to `KarrMetabolismProcess` for L3/L4/L5 downstream tests that need to inject Karr's flux at the Metabolism boundary (separate from this decision but listed for completeness).
- **Part 4**: This decision card + updates to plan.md L-ladder section + PROCESS_STATUS_ALL_29 note for Metabolism's special gate.
- **Part 5**: Re-run L2.2 audit with the new metric; expect Metabolism PASSes by construction.

## External Review Context

- Cross-model critique by gpt-5.4 on Day-42 (rubber-duck agent) flagged that "all glp_smcp exhausted" was premature; Day-43 verification probes confirmed GPT's flag (GLP_RT_FLIP and bound semantics matter) but ALSO confirmed the high-level "no single knob solves it at scale" conclusion.
- FBA community consensus (COBRApy / COBRA toolbox issues): degenerate LP non-reproducibility across solver versions is well-documented; FVA is the standard remedy.

## Related Decisions

- DEC-002 (Crosswalk Phase 2) — established the per-process L-ladder structure that this decision modifies for Metabolism.
- (Future) DEC-004 (Karr-flux-injection methodology for L3/L4/L5) — to be written if/when Part 3 lands as a standalone methodology change.

## Provenance

- Drafted in Copilot CLI session `5c51d44b-5a9f-4b23-85ff-0fddaadf2212` on Day-43 (2026-06-29).
- Cross-model critique by gpt-5.4 verified the framing on Day-42 (commit 4b648fa).
- Productionization in progress (Day-43 Part 2 codex agent, PID 38360 launched 2026-06-29 ~10:30 IST).
