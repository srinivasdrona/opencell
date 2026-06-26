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

## 4. LP-degenerate invariant suite and null-space perturbation test

## 5. Mutation catalogue and bin tolerances

## 6. Verdict semantics, L5 handoff, and pre-registration enforcement

## 7. Acceptance bar, self-audit, and risks
