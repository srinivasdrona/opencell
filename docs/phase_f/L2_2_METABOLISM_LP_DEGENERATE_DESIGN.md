# L2.2 Metabolism LP-Degenerate Design

Supersession scope:
- This document supersedes only the MF4 / LP-degenerate section of `docs/phase_f/L2_2_METRIC_BY_PROCESS_CHARACTER_DESIGN.md`.
- V1 remains the current contract for MF0, MF1, MF2, MF3, and MF5.

## DAP Intent

Contract:
- Required behavior: classify Metabolism as an LP-degenerate L2.2 special case by a preregistered numeric audit, then gate it with MF4 interface-fidelity invariants plus an independent null-space perturbation test rather than raw per-tick W1 alone.
- Why this matters: Day-40 shows `W1=161` vs threshold `102` even after the writeback port is correct to the algorithm/RNG floor `40`; the remaining gap sits on a `cond(S)=6.7e+12` LP with `128/504` null-space dimensions and `8` unbounded reactions.
- Done = Metabolism can only enter MF4 if the audit numerically proves `lp_degenerate`, the selector deterministically routes it there, the mutation suite M1-M8 is covered by named invariants with numeric tolerances, and the null-space perturbation test shows the dominant writeback residual is reachable inside the biomass-fixed feasible region.

Beat-4 inversion:
- Most plausible "looks right, is wrong" failure mode: V2 quietly relabels the existing Day-40 FAIL as a conditional pass by deriving all tolerances from the same OC-vs-Karr gap and never proving that the gap is vertex degeneracy rather than an OC bug.
- What would falsify this contract statement: a reviewer can construct a process record that routes differently through the prose rule and the truth-table fixture, or the null-space perturbation test fails to reach Karr on the dominant WIDs while MF4 still admits `CONDITIONAL_PASS`.

## 1. Problem statement and scope

V2 is a minimal MF4-only replacement for V1. It does not redesign MF0/MF1/MF2/MF3/MF5, and it does not change L1, L2.1, L2.event, L2.5, L3, L4, or L5 code paths. Its only job is to replace the old "Metabolism is TRIVIAL_RNG" assumption with a preregistered LP-degenerate contract.

Metabolism is the motivating case and the worked example. The current catalog says `bucket: TRIVIAL_RNG`, `event_density: dense`, and "FBA deterministic"; the empirical record says the opposite for L2.2 purposes: 500-sample audit, `W1=161` vs threshold `102`, per-sample writeback L1 mean `22,412`, Karr-recorded mass mean `109,393`, algorithm/RNG floor `40`, bounds drift `0`, and a residual concentrated in 17 WIDs carrying about 91% of the error.

The design claim is narrow. L2.1 can remain GENUINE for Metabolism because it validates aggregate process behavior, while L2.2 inspects per-WID substrate writeback where LP vertex choice surfaces directly. V2 therefore treats the LP audit as the admission gate for MF4 and treats raw Karr-trace W1 as informational unless the null-space test shows the residual is not feasible vertex motion.

In scope:
1. Numeric `degeneracy_sensitivity` thresholds and a worked Metabolism classification example.
2. A single normative selection rule for MF4 admission, including no-match error behavior.
3. An LP-degenerate invariant suite, M1-M8 mutation catalogue, bin tolerances, and element-conservation set.
4. A concrete null-space perturbation procedure for sample `(seed=0, tick=1)`.
5. One verdict label, explicit L5 handoff semantics, and named pre-registration enforcement surfaces.

Out of scope:
1. Any code implementation, new extraction, or re-run of the Day-40 audit.
2. Any change to non-MF4 families beyond a reference to V1 as the standing contract.
3. Any attempt to "fix" the remaining Metabolism gap inside this design.

## 2. Prior-art quotations

Authoritative quotations:

```text
docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml
- name: Metabolism
  bucket: TRIVIAL_RNG
  output_channels: [substrates]
  primary_channel: substrates
  rationale_M: "FBA deterministic, only stochasticRound is RNG; small M sufficient for confirmation"
```

```text
docs/phase_f/L2_2_DESIGN_OPUS_CRITIQUE.md
1. B1: Selection rule and matrix (if any) provably equivalent on a truth-table fixture; no-row-matched -> explicit error.
4. B4: Null-space perturbation test specified concretely ... MF4 admission gated on this test passing.
7. N3: V2 is ~150-200 lines, scoped to MF4 only.
```

Inventory of existing artifacts:
- [A01] path=docs/phase_f/L2_2_DESIGN_OPUS_CRITIQUE.md | kind=doc | role=primary spec authority defining B1-B4, N1-N4, S1-S2, and the V2 acceptance bar
- [A02] path=docs/phase_f/L2_2_METRIC_BY_PROCESS_CHARACTER_DESIGN.md | kind=doc | role=V1 contract being superseded for MF4 only; source of the specific gaps B1-B4 call out
- [A03] path=docs/phase_f/METABOLISM_POSTMORTEM_DAY40.md | kind=doc | role=records RC3 audit-before-test-design lesson plus LP facts `cond=6.7e+12`, `128` null dims, `8` unbounded reactions
- [A04] path=docs/phase_f/METABOLISM_GAP_MAP.md | kind=doc | role=empirical anchors for `W1=161`, threshold `102`, 500 samples, Top-17/Top-27 WIDs, and variant-family counts
- [A05] path=docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml | kind=schema | role=current machine-loadable routing contract that wrongly keeps Metabolism in `TRIVIAL_RNG`
- [A06] path=data/schemas/per_process/metabolism.toml | kind=schema | role=observable contract proving the L2.2 write surface is `substrates` only, with `585` substrates and `104` enzyme pass-through observables
- [A07] path=tests/vivarium/l2_2_design_a_runner.py | kind=code | role=current harness contract whose direct catalog loading must be replaced by a selector-call enforcement point
- [A08] path=tests/vivarium/_l2_2_design_a_projections.py | kind=code | role=existing invariant-distance style reference for named aggregation contracts and thresholded joint verdicts
- [A09] path=D:/OneDrive - Microsoft/.pm-os/DECISIONS.md | kind=other | role=durable cross-session decision log anchoring the Day-40 RCs as non-optional lessons for future Metabolism work

Inventory Beat-4 inversion:
- Critical artifact still most likely to be missing: the future truth-table fixture file, because it does not yet exist and is specified here only as an implementation target.
- Content check run: each cited artifact was opened and checked for the exact Metabolism facts used in V2; no new MATLAB or Python extraction was run.
- Possible artifact failure: the catalog can be machine-loadable yet semantically stale, which is exactly the Metabolism misclassification V2 is correcting.

## 3. Objective degeneracy rubric and MF4 admission rule

Normative audit fields for any LP candidate:
1. `solver_type in {lp, non_lp}`.
2. `condition_number = cond(S)`.
3. `nullity_ratio = dim(null(S)) / n_reactions`.
4. `unbounded_non_biomass_reactions = count(lb=-inf and ub=+inf after static bound construction, excluding biomass and reactions explicitly closed by Karr bounds)`.
5. `observable_surface = substrates_only | other`.

Numeric rubric:
1. `degeneracy_sensitivity = lp_degenerate` if any of:
   - `condition_number > 1e10`
   - `nullity_ratio > 0.10`
   - `unbounded_non_biomass_reactions > 0`
2. `degeneracy_sensitivity = low` if not `lp_degenerate` and any of:
   - `1e6 < condition_number <= 1e10`
   - `0.01 < nullity_ratio <= 0.10`
3. Else `degeneracy_sensitivity = none`.

Defense of thresholds:
1. They are intentionally decade-scale, not finely tuned, because the Metabolism audit sits far beyond the cutoff on all three axes.
2. They separate numerically ordinary LPs from solver-family-sensitive LPs using the three failure modes Day-40 actually exposed: ill-conditioning, large feasible null motion, and explicitly unbounded cycle directions.
3. Any audit that lands in `lp_degenerate` or `low` requires operator sign-off before the harness runs; MF4 is never a silent default.

Worked Metabolism example:
1. `condition_number = 6.7e+12 > 1e10` -> `lp_degenerate`.
2. `nullity_ratio = 128 / 504 = 0.254 > 0.10` -> `lp_degenerate`.
3. `unbounded_non_biomass_reactions = 8 > 0` -> `lp_degenerate`.
4. Therefore Metabolism is objectively `lp_degenerate` even before considering the 17-WID residual structure, and its current `TRIVIAL_RNG` catalog bucket is non-admissible for L2.2 metric selection.

Single normative selection rule:
1. Load the preregistered audit record for `process`.
2. If no audit record exists, if more than one row matches `process`, or if the record hash/commit pin is invalid, raise `AUDIT_REGISTRATION_ERROR`.
3. If `solver_type != lp`, return `DEFER_TO_V1_NON_MF4`.
4. If `solver_type == lp` and `degeneracy_sensitivity in {none, low}`, return `DEFER_TO_V1_NON_MF4`.
5. If `solver_type == lp` and `degeneracy_sensitivity == lp_degenerate`, return `MF4_LP_DEGENERATE_INTERFACE_FIDELITY_V2`.
6. Else raise `AUDIT_SELECTION_ERROR`; there is no implicit fallthrough to MF1 or any bucket label.

Truth-table equivalence requirement:
1. The selector above is the only normative artifact; any table is illustrative only.
2. A checked fixture must enumerate the reachable cross-product for current LP and non-LP audit states and assert exact equality between fixture outcome and selector outcome.
3. Required rows are at minimum: `(non_lp, none)`, `(non_lp, low)`, `(lp, none)`, `(lp, low)`, `(lp, lp_degenerate)`.
4. The fixture must also assert the negative case: no matching preregistered row -> explicit error, not `DEFER_TO_V1_NON_MF4`.

## 4. LP-degenerate invariant suite and null-space perturbation test

MF4 is a two-stage contract:
1. Admission stage: prove the existing Karr-facing residual is feasible LP vertex motion, not a fixed OC bias.
2. Regression stage: once admitted, detect future interface regressions against a pinned MF4 baseline using invariants that are stronger than raw W1 on the mutation catalogue.

Pinned baseline rule:
1. The first admissible MF4 baseline is the exact committed solver stack that passes the null-space perturbation test.
2. No candidate run may define its own tolerances from its own residuals.
3. `trace_vertex_equivalence_w1` vs Karr remains informational only; it never upgrades a failing invariant suite to pass.

Invariant suite for regression stage:

| ID | Invariant | Contract unit | Tolerance | Must fail |
|---|---|---|---|---|
| I1 | `aggregate_signed_flux_magnitude` | per `(seed,tick)`, `sum_w abs(delta_w)` over all 585 substrate WIDs vs pinned MF4 baseline | `abs(diff) <= max(0.01 * baseline_total, 40)` | M6 |
| I2 | `per_wid_signed_delta_residual_budget` | per `(seed,tick,wid)` signed delta vs pinned MF4 baseline, with mandatory focus on Top-27 WIDs | `abs(diff) <= max(1, 0.01 * max(1, abs(baseline_delta)))`; sign must match when `abs(baseline_delta) > 1` | M1, M2, M4, M7 |
| I3 | `pathway_level_flux_distributions` | per `(seed,tick,family,bin)` for `LIPASE x27`, `TX x12`, `Pyk x7`, `Adk x3`, `PfkA x5`, `Gmk x2` | `bin_tolerance = max(0.05 * abs(karr_bin_flux), 10)` | M3, M5, M6 |
| I4 | `dominant_wid_joint_structure` | per `(seed,tick)` Top-17 signed-delta vector over `OCDCEA,H2O2,O2,TRP,TRIOLEIN,TYR,GL,AC,PHE,TrpTrp,H2O,TyrTyr,GLC,ACAL,AEPP,CAP,PhePhe` vs pinned MF4 baseline | Spearman `rho >= 0.95` and sign agreement on at least `15/17` WIDs | M5, M8 |
| I5 | `elemental_and_mass_conservation` | per `(seed,tick)` mass + elemental totals after writeback | choose `mass + C/N/P`; pass if deviation `<= max(40, 3e-4 * karr_sample_total)` for each total | M3, M5 |

Element set decision:
1. V2 chooses `mass + C/N/P`, not mass-only.
2. Reason: mass-only misses pathway swaps that preserve total count but move carbon, nitrogen, or phosphate burden across WIDs.
3. Implementation dependency: if the current observable schema lacks elemental composition, MF4 cannot be enabled until the composition lookup is wired from the metabolism model metadata.

Null-space perturbation admissibility test:
1. Mandatory sample: `(seed=0, tick=1)`, because Day-40 already anchored the algorithm/RNG floor there and verified bounds drift `0`.
2. Flux input: start from the pinned OC flux vector `v` at that sample after static bounds and biomass optimum are fixed.
3. Basis: compute a basis `K` for the biomass-fixed feasible null space, i.e. vectors `k` such that `S k = 0`, biomass-column objective remains fixed, and active bound constraints are respected to first order.
4. Cone projection and `alpha` normalization: for each basis vector, intersect the bound-feasible interval implied by `lb <= v + alpha * k <= ub`; normalize `k` so the nearest feasible bound occurs at `|alpha| = 1`; then evaluate `alpha in {-1.0, -0.9, ..., 0.9, 1.0}`.
5. Readout: re-run Karr's writeback on each feasible `v + alpha * k` and inspect the 17 dominant Day-40 WIDs listed in I4.
6. Reachability tolerance: a WID is "reachable" if some feasible perturbation lands within `max(1, 3e-4 * max(1, abs(karr_signed_delta_wid)))` molecules of Karr's recorded signed delta at that sample.
7. "Moves freely": at least `80%` of the 17 dominant WIDs are reachable.
8. "Fixed biased offset": more than `10%` of the 17 dominant WIDs are unreachable by every feasible perturbation.
9. Pass rule: MF4 admission requires "moves freely" and not "fixed biased offset". Any intermediate result is `OPEN_QUESTION_REINVESTIGATE`, not silent admission.

Expected falsifier:
1. If the perturbation search cannot reach Karr on the dominant WIDs while staying biomass-fixed and bound-feasible, the residual is not established as vertex degeneracy and MF4 is not admissible.
2. If M6-M8 can pass I1-I5 on the admitted baseline, the suite is weaker than claimed and V2 must be reopened before implementation.

## 5. Mutation catalogue and bin tolerances

The mutation catalogue is the admission test for I1-I5. MF4 is not implementation-ready until each mutation below is shown to fail at least one named invariant on the pinned baseline.

| ID | Construction | Required failing invariant |
|---|---|---|
| M1 | Sign flip on one dominant WID delta after writeback, e.g. `OCDCEA`, `TRP`, or `H2O2` | I2 |
| M2 | Compartment or paired-writeback permutation that preserves total magnitude but assigns the signed delta to the wrong substrate slot | I2 |
| M3 | Cofactor or pathway-family swap that preserves rough mass but moves flux between variant families or cofactor-coupled products | I3 or I5 |
| M4 | Exchange-direction flip on an external or internal exchange writeback component while keeping magnitude unchanged | I2 and usually I5 |
| M5 | Growth-only preserved redistribution: keep biomass-compatible totals but reshuffle signed deltas across the Top-17 WIDs | I3 or I4 |
| M6 | Uniform magnitude attenuation: multiply every per-WID signed delta by `0.9` | I1 and usually I3 |
| M7 | Temporal shift: apply the correct signed deltas at tick `t+1` or `t-1` instead of tick `t` | I2 |
| M8 | Correlated-noise forgery: inject zero-mean per-sample noise with Karr-matched variance, then re-normalize to preserve total absolute magnitude and family-bin aggregates | I4 |

Mutation notes:
1. M6 is the direct B3 fix for the "10% under-flux but same signs" hole. I1's `1%` tolerance is intentionally an order of magnitude tighter than the attack.
2. M7 is caught because I2 is keyed by exact `(seed,tick,wid)`, not by pooled histograms. No extra tick-alignment invariant is needed for MF4.
3. M8 is the direct joint-structure test. If a future implementation can make M8 pass while preserving I1-I3, I4 is underspecified and must be strengthened before MF4 ships.

Bin-tolerance decision:
1. For every variant family bin in `LIPASE`, `TX`, `Pyk`, `Adk`, `PfkA`, and `Gmk`, use `bin_tolerance = max(0.05 * abs(karr_bin_flux), 10)`.
2. Defense: `5%` is tight enough that M6's `10%` attenuation must fail, while the absolute floor `10` prevents tiny bins from failing on stochastic rounding dust.
3. The tolerance is anchored to Karr's recorded family-bin flux, not to the candidate run, so the candidate cannot widen its own pass band.

## 6. Verdict semantics, L5 handoff, and pre-registration enforcement

## 7. Acceptance bar, self-audit, and risks
