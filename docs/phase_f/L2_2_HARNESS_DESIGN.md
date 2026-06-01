# L2_2_HARNESS_DESIGN

Status: first dogfood of `docs/prompts/DESIGN_TEMPLATE.md` for multi-file design-doc authoring.

## DAP Intent

Contract (Beat 1):

- Required behavior: given any selected composition of `k` under-test Karr processes sharing per-tick state, L2.2 must validate each process's owned observables against that process's `states_after[t]` with L2.1-level fidelity and produce a named, evidence-backed mismatch cause.
- Done means: a mismatch message is attributable to a concrete design cause (WID mapping, order semantics, oracle overlay, upstream pollution, intrinsic replay, harness bug, oracle defect), not just "RED".

Expected observable (Beat 3):

- For a known failing pair (Translation + RNAProcessing), harness-v2 should flag WID-space miscomposition explicitly instead of mislabeling it as generic upstream pollution.

Beat-4 inversion:

- The document could still preserve the same flawed hidden assumption ("shared observable index positions mean shared chemicals"), now with cleaner formatting.

PM sanity-check sentence:

- This design assumes L2.2 is a composition-fidelity layer (small-k integration with explicit attribution), not a full 28-process chassis replay replacement; if that scope is wrong, several decisions below should be revisited.

## 1) Design contract

Contract:

- Required behavior: L2.2 harness composes `k` processes on shared state without silently aliasing incompatible observable spaces, and validates post-step/post-tick outputs for owned observables against per-process traces.
- Why this matters: L2.1 GREEN only proves isolated process replay. It does not prove cross-process composition correctness.
- Done = property statement: every mismatch emitted by L2.2 must carry a cause category from a defined taxonomy and a reproducible diagnostic path.

Beat-4 inversion:

- Most plausible "looks right, is wrong" failure mode: index-based overlays still map different chemicals together, so attribution logic appears sophisticated while root state is corrupted.
- What would falsify this contract statement: if we can produce a mismatch where the stated cause cannot be reproduced by the documented diagnostic procedure.

## 2) Inventory of existing artifacts

- [A01] path=`SESSION_CONTEXT.md` | kind=doc | role=non-negotiable interpreter/fidelity/scope rules; establishes Karr-fidelity and no-guessing constraints.
- [A02] path=`docs/phase_f/PROTEIN_DECAY_PROJECTION.md` | kind=doc | role=closest recent successful pre-implementation design precedent in Phase F.
- [A03] path=`docs/prompts/DELIBERATE_ACTION_PREFIX_v2.md` | kind=doc | role=slot-1 five-beat discipline adapted here for design authoring.
- [A04] path=`docs/prompts/FIX_TEMPLATE_L2_REPLAY.md` | kind=doc | role=slot-2 sibling pattern showing machine-checkable rule/checklist structure.
- [A05] path=`tests/vivarium/l2_2_replay_common.py` | kind=code | role=current harness-v1 behavior, including composition order and first-process oracle injection policy.
- [A06] path=`E:/opencell-worktrees/l2-2-harness/STATUS_l2_2_harness.md` | kind=status | role=records shipped RED plus misdiagnosed "upstream pollution" finding.
- [A07] path=`phase-f-schema-extract:data/schemas/per_process/translation.toml` | kind=schema | role=declares Translation substrate WID set/order (`count=26`) used to expose mismatch root cause.
- [A08] path=`phase-f-schema-extract:data/schemas/per_process/rna_processing.toml` | kind=schema | role=declares RNAProcessing substrate WID set/order (`count=7`) proving non-aligned spaces.
- [A09] path=`phase-f-schema-extract:data/schemas/per_process/transcription.toml` | kind=schema | role=extra evidence that substrate WID sets vary by process and are not globally positional.
- [A10] path=`phase-f-schema-extract:data/schemas/per_process/metabolism.toml` | kind=schema | role=shows extractor-diagnostic complexity and schema heterogeneity that harness design must tolerate.
- [A11] path=`docs/karr_extracts/architecture/01_simulation_loop.md` | kind=doc | role=verbatim extract of `@Simulation/evolveState.m` establishing process execution-order semantics.
- [A12] path=`plan.md` | kind=doc | role=current hypothesis framing context; informs recommendation to add explicit cross-process composition risk tracking.

Inventory Beat-4 inversion:

- Possible missing critical artifact: a branch-local harness experiment not in this worktree that changed semantics after `d2421ac`.
- Check run: read the paired harness STATUS artifact and current `l2_2_replay_common.py` together to reconcile intended vs implemented behavior before deciding.

## 3) Interaction-surface map

| Surface ID | Producer | Consumer | Contract unit | Failure if mismatched | Evidence anchor |
|---|---|---|---|---|---|
| S1 | Per-process schema TOMLs | L2.2 state composer | substrate WID identity/order | Wrong chemical mapped to same index | [A07], [A08] |
| S2 | L2.2 shared state overlay | Process `next_update` | observable vector semantics | False upstream/intrinsic diagnosis | [A05], [A06] |
| S3 | Karr scheduler semantics | L2.2 composition runner | intra-tick process order | Apparent replay divergence caused by wrong order model | [A11] |
| S4 | Oracle injection policy | Shared-state initializer | source-of-truth for each observable | Hidden cross-process taint at tick start | [A05], [A07], [A08] |
| S5 | L2.1 helper projection utilities | L2.2 verification assertions | owned observable compare surface | Pass/Fail reflects projection artifact, not biology | [A04], [A05] |
| S6 | Failure-attribution taxonomy | Test operator triage | named cause -> diagnostic proof | Time lost on wrong repair path | [A06], Section 5/D3 |
| S7 | Existing harness-v1 commits | Harness-v2 migration | change-management path | Diff noise and regression ambiguity | [A05], Section 9 |

Interaction Beat-4 inversion:

- Most likely false assumption: "observable name equality implies shared semantic space".
- Fast exposure signal: dump WID names for each process at first mismatch index and show names differ.

## 4) Baseline facts and constraints

1. This task is docs-only; no production code changes under `opencell/vivarium/`.
2. L2.2 harness-v1 composes Translation then RNAProcessing with `_ORACLE_INJECTION_POLICY = first-process-with-observable` and a single shared state vector per observable name.
3. The known RED (`tick=5`, RNAProcessing `substrates`, index `5`) was labeled "upstream pollution" via counterfactual isolated replay.
4. F-schema evidence shows the shared-index assumption is invalid:
   - `data/schemas/per_process/translation.toml`:
     - `[substrates] wids = ["ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE", "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL", "FMET", "GTP", "GDP", "PI", "H2O", "H"]`
     - `count = 26`
   - `data/schemas/per_process/rna_processing.toml`:
     - `[substrates] wids = ["ATP", "GTP", "ADP", "GDP", "PI", "H2O", "H"]`
     - `count = 7`
   - Therefore index `5` (0-based) corresponds to `GLN` in Translation but `H2O` in RNAProcessing.
5. Karr execution semantics from `docs/karr_extracts/architecture/01_simulation_loop.md` (verbatim from `@Simulation/evolveState.m`):
   - Per tick, process evaluation order is randomized (`randperm`) with a specific ordering constraint (tRNAAminoacylation before Translation).
   - Processes are executed sequentially in that order (`mod.copyFromState(); mod.evolveState(); mod.copyToState();` loop).
   - Allocation is precomputed for all processes before execution, then each process runs with its allocation.
6. `plan.md` currently tracks many within-path hypotheses; explicit cross-process composition-risk framing should be first-class in future hypothesis matrices.

Baseline Beat-4 inversion:

- Inferred-not-proven baseline risk: per-process schema extraction could itself contain extractor errors for some processes (e.g., Metabolism diagnostics show failures).
- Invalidator: if schema WID lists disagree with process runtime `*_wids` attributes for a process, schema cannot be treated as authoritative without reconciliation.

## 5) Decision ledger

Decision D1 (Q1): WID-set unification across composed processes

- Question: how should shared observables be represented when per-process WID sets differ in content/length/order?
- Options considered:
  1) Union master list with per-process WID->master index maps.
  2) Per-process state shards with no direct shared substrate pool.
  3) Per-observable owner-only model plus projected read views.
  4) Keep first-process positional overlay.
- Chosen option: Option 1 (union master list + explicit mappings), with owner manifest for overlap semantics.
- Rationale:
  - Preserves true shared-resource interactions where WIDs overlap.
  - Prevents positional aliasing (`GLN` vs `H2O`) by mapping on identity, not index.
  - Scales to `k > 2` while keeping one composable store per observable family.
- Tradeoffs accepted:
  - Additional mapping complexity per process/observable.
  - Need a canonical union ordering policy.
- Beat-4 inversion:
  - Could still be wrong if canonical ordering is unstable across runs/branches, causing nondeterministic failures.
- Falsifier:
  - If two identical harness runs produce different mismatch indices without code changes, union-order policy is unstable.
- Operator escalation needed? Yes (QO1: canonical union order policy).

Decision D2 (Q2): Composition-order semantics

- Question: should L2.2 run tick-sequential, tick-parallel, or configurable order?
- Options considered:
  1) Tick-sequential fixed order.
  2) Tick-parallel read-same-before then reduce deltas.
  3) Configurable policy (deterministic fixed, or Karr-like randomized sequential).
- Chosen option: Option 3 with sequential semantics only; no parallel mode in v2 baseline.
- Rationale:
  - Karr source indicates sequential process execution within tick, not parallel delta summation.
  - Deterministic fixed-order mode improves reproducibility/debuggability for tests.
  - Karr-like random-per-tick sequential mode can be added for fidelity experiments while retaining deterministic test mode.
- Tradeoffs accepted:
  - Deterministic order is not identical to Karr's randomized ordering by default.
  - Additional mode surface may increase harness complexity.
- Beat-4 inversion:
  - A deterministic order could hide order-sensitive defects that appear under Karr randperm.
- Falsifier:
  - If deterministic mode passes but randomized-sequential mode consistently fails on same pair, order sensitivity is real and must be surfaced.
- Operator escalation needed? Yes (QO2: require randperm mode in v2 baseline or defer).

Decision D3 (Q3): Failure-attribution semantics and taxonomy

- Question: what causes should L2.2 distinguish and how should each be diagnosed?
- Options considered:
  1) Binary attribution (upstream vs intrinsic) via isolated counterfactual only.
  2) Multi-cause taxonomy with targeted diagnostics.
- Chosen option: Option 2.
- Rationale:
  - Binary model misdiagnosed the current RED because it lacked a WID-space mismatch category.
  - Actionable repairs require cause-specific proofs.
- Taxonomy and diagnostic proof structure:
  - `CAUSE_1_WID_SET_MISMATCH`: compare per-process WID names for mismatched index; if names differ, classify immediately.
  - `CAUSE_2_ORACLE_INJECTION_MISALIGNMENT`: rerun with explicit owner manifest; mismatch disappears => injection policy bug.
  - `CAUSE_3_COMPOSITION_ORDER_ERROR`: run deterministic order A->B vs B->A (or randomized sequential); order-dependent outcomes implicate order semantics.
  - `CAUSE_4_UPSTREAM_STATE_POLLUTION`: process matches in isolated replay with identical mapped-before state but fails in composition.
  - `CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE`: process fails in isolated replay against own trace.
  - `CAUSE_6_HARNESS_BUG`: contradiction between two equivalent projection paths in harness.
  - `CAUSE_7_ORACLE_TRACE_DEFECT`: Karr `states_before/after` or metadata violate internal consistency checks (shape/integrality/known invariants).
- Tradeoffs accepted:
  - More diagnostic runs per mismatch.
  - Slightly longer test runtime.
- Beat-4 inversion:
  - Taxonomy labels could become cosmetic if diagnostics are not mechanized.
- Falsifier:
  - If two investigators running the documented diagnostics disagree on category for the same mismatch, taxonomy is underspecified.
- Operator escalation needed? Yes (QO3: strict fail on unknown cause vs soft "UNCLASSIFIED").

Decision D4 (Q4): Oracle injection policy

- Question: should "first-process-with-observable" remain the initializer for shared observables?
- Options considered:
  1) Keep first-process policy.
  2) Last-process policy.
  3) Explicit per-observable owner manifest with fallback rules.
  4) Union-merge from all processes each tick.
- Chosen option: Option 3.
- Rationale:
  - First-process policy caused hidden assumptions; ownership must be explicit and auditable.
  - Owner manifest aligns with design intent: one source-of-truth initialization per observable for comparison.
- Tradeoffs accepted:
  - Manual manifest maintenance or generator complexity.
- Beat-4 inversion:
  - Owner manifest can drift from actual process responsibilities, creating stale correctness assumptions.
- Falsifier:
  - If owner manifest contradicts per-process schema/write paths, fail harness setup before tick loop.
- Operator escalation needed? Yes (QO4: owner manifest source and governance).

Decision D5 (Q5): Validation surface (step/final, owned/all)

- Question: what should be validated and when?
- Options considered:
  1) Final-cell only.
  2) Step-level only.
  3) Step-level + final-cell, owned observables as hard assertions, non-owned as diagnostics.
- Chosen option: Option 3.
- Rationale:
  - Step-level localizes where divergence first appears.
  - Final-cell catches downstream pollution after a process's local success.
  - Owned-only hard assertions avoid tautological comparison of unrelated surfaces.
- Tradeoffs accepted:
  - Additional bookkeeping for before/after snapshots and ownership.
- Beat-4 inversion:
  - Owned-only hard assertions could miss important non-owned regressions.
- Falsifier:
  - If a known regression appears only in non-owned observables and is not surfaced by diagnostics, policy must be tightened.
- Operator escalation needed? Yes (QO5: should selected non-owned observables be hard-fail).

Decision D6 (Q6): Scope of `k` for L2.2

- Question: does L2.2 target only pairs or general small-k compositions?
- Options considered:
  1) k=2 only.
  2) unrestricted k up to 28.
  3) small-k tier (`2 <= k <= 4`) with explicit handoff to L3 for large-k/full-chassis.
- Chosen option: Option 3.
- Rationale:
  - Pair-only is too narrow to test interaction chains.
  - Unrestricted k conflates L2.2 with full integration and explodes diagnostic complexity.
  - Small-k tier provides meaningful composition coverage while preserving attribution quality.
- Tradeoffs accepted:
  - Some multi-process emergent failures will remain outside L2.2.
- Beat-4 inversion:
  - k<=4 boundary could be arbitrary and miss practical failure modes at k=5+.
- Falsifier:
  - If repeated defects only surface at k>4, L2.2 boundary needs expansion or explicit L3 precursor tests.
- Operator escalation needed? Yes (QO6: exact k upper bound for this project phase).

Decision D7 (Q7): Relationship to L2.1 guarantees

- Question: what does L2.1 GREEN imply for L2.2, and what does it not imply?
- Options considered:
  1) Treat L2.1 GREEN as near-sufficient precondition.
  2) Treat L2.1 GREEN as necessary but strictly insufficient.
- Chosen option: Option 2.
- Rationale:
  - L2.1 proves isolated per-process replay fidelity.
  - L2.2 introduces new failure surfaces: cross-process WID mapping, order semantics, shared-state initialization, ownership policy.
- Tradeoffs accepted:
  - Additional design and runtime checks beyond existing L2.1 machinery.
- Beat-4 inversion:
  - Team may still over-trust L2.1 and under-invest in composition checks.
- Falsifier:
  - If documented L2.2-specific checks are skipped and REDs recur in composition-only contexts, governance failed.
- Operator escalation needed? No.

Decision D8 (Q8): Migration path from harness-v1

- Question: how should existing `l2_2_replay_common.py` be migrated?
- Options considered:
  1) Revert v1 commits first, then build v2.
  2) Keep v1, build v2 in parallel, cut over when green, then retire v1.
  3) Refactor v1 in place.
- Chosen option: Option 2.
- Rationale:
  - Keeps an auditable baseline for regression comparison.
  - Reduces risk of losing useful diagnostics while redesigning core mapping/order logic.
  - Enables side-by-side cause-quality comparison (old vs new attribution).
- Tradeoffs accepted:
  - Temporary duplication and extra maintenance during overlap window.
- Beat-4 inversion:
  - Parallel paths may diverge and cause confusion about source-of-truth.
- Falsifier:
  - If team cannot state which harness is authoritative for a test module, migration protocol is failing.
- Operator escalation needed? No.

## 6) Expected outcomes and verification claims

Claim C1 (WID mapping correctness):

- If design is correct, per-mismatch diagnostics will show chemical-name mismatches instead of raw index-only diffs when mapped WIDs differ.
- Measurement: mismatch report includes `{index, process_wid, compared_wid}` pairs.
- Distinguishes alternatives: positional-overlay design cannot emit semantic-name mismatch proof.

Claim C2 (current RED reclassification):

- For Translation + RNAProcessing failing case, harness-v2 should classify first failure as `CAUSE_1_WID_SET_MISMATCH` or downstream effect of that category, not generic upstream pollution.
- Measurement: run same pair and compare first failure category between v1 and v2.
- Threshold: category string must be in taxonomy and supported by diagnostic data dump.

Claim C3 (order semantics alignment):

- Sequential deterministic mode should be default, with optional randomized-sequential mode yielding reproducible failures given fixed seed.
- Measurement: run same case with fixed seed in both modes; deterministic should be stable across runs.

Claim C4 (attribution completeness):

- Every failure must map to one of seven cause classes or explicit `UNCLASSIFIED` (if operator-approved).
- Measurement: assertion that failure records always include `cause_code`.

Claim C5 (owner-injection transparency):

- Initial shared state construction log should identify owner source per observable.
- Measurement: harness emits owner manifest used for tick initialization and validates against process/schema metadata.

Claim C6 (migration confidence):

- During overlap period, v1 and v2 harnesses should run side-by-side on at least one pair and report where attribution differs.
- Measurement: migration report artifact compares first mismatch tuple and cause for same test input.

Expected-outcome Beat-4 inversion:

- These claims could pass while still wrong if diagnostic data itself is derived from corrupted mappings.
- Guardrail: include independent cross-check that raw vector lengths + WID lists align before any comparison is performed.

## 7) Open questions for operator

QO1. What canonical ordering should union master WID lists use?

- Why unresolved: deterministic order affects reproducibility and diff stability.
- Options:
  1) Lexicographic order of union WIDs.
  2) Stable first-seen order by composition order.
  3) External canonical list per observable family.
- Recommended default (if no response): option 2 for local explainability.
- Risk if wrong: unstable indices or harder cross-run comparison.

QO2. Must harness-v2 include Karr-style random-per-tick sequential order in the first implementation?

- Why unresolved: fidelity vs complexity tradeoff in initial rewrite.
- Options:
  1) Ship deterministic sequential first, add randperm mode later.
  2) Ship both modes in v2 baseline.
- Recommended default: option 1.
- Risk if wrong: order-sensitive defects may be delayed.

QO3. Should unknown/unclassified causes be allowed?

- Why unresolved: strictness affects CI behavior and developer velocity.
- Options:
  1) Hard-fail if cause not in taxonomy.
  2) Allow `UNCLASSIFIED` with required diagnostic payload.
- Recommended default: option 2 initially, with a timebox to eliminate unclassified cases.
- Risk if wrong: either brittle CI or ambiguous failures.

QO4. How should observable ownership manifests be sourced?

- Why unresolved: manual manifests drift; auto-generated manifests may overfit extractor artifacts.
- Options:
  1) Hand-maintained manifest in test module.
  2) Generated from per-process schema + process write-path metadata.
  3) Hybrid (generated baseline + manual overrides).
- Recommended default: option 3.
- Risk if wrong: injection policy silently diverges from real ownership.

QO5. Should selected non-owned observables be hard-fail assertions?

- Why unresolved: owned-only hard checks improve signal, but non-owned can expose severe coupling issues.
- Options:
  1) Non-owned always diagnostic-only.
  2) Promote configured high-risk non-owned observables to hard-fail.
- Recommended default: option 2 for substrate pools.
- Risk if wrong: either missed regressions or noisy false failures.

QO6. Confirm L2.2 scope boundary: is `k<=4` acceptable as Phase-F target?

- Why unresolved: project might want broader integration pressure sooner.
- Options:
  1) Keep `2<=k<=4` for L2.2, escalate larger compositions to L3.
  2) Expand L2.2 up to `k=8`.
- Recommended default: option 1.
- Risk if wrong: either insufficient coverage or diluted attribution quality.

## 8) Scope boundary

In scope:

1. Define harness-v2 composition semantics and attribution taxonomy.
2. Define WID-unification strategy for shared observables.
3. Define migration strategy from current harness-v1.
4. Establish operator decision surface for unresolved design forks.

Out of scope:

1. Implementing harness-v2 code changes.
2. Modifying production process code under `opencell/vivarium/`.
3. Editing `plan.md` directly.
4. Redesigning full L3 full-chassis integration framework.

Deferred follow-ups:

1. Add a cross-process composition-risk row in project hypothesis matrices.
2. Automate manifest generation from schema extraction pipeline.
3. Add randomized-order stress mode once deterministic v2 is stabilized.

Scope Beat-4 inversion:

- Likely scope-creep vector: implementing "just one helper change" in harness code while authoring design.
- Prevention: docs-only commits in this task; implementation is a separate follow-on delegation.

## 9) Migration and rollout path

Strategy: option (b), keep v1, build v2 in parallel, retire v1 after v2 acceptance.

Proposed sequence:

1. Freeze v1 behavior in a baseline note (first mismatch tuple + cause on current pair).
2. Introduce `l2_2_replay_common_v2.py` with union-WID mapping + owner manifest + cause taxonomy.
3. Port first pair test to v2 while leaving v1 test intact.
4. Compare v1 vs v2 outputs on same case; verify cause-quality improvement.
5. Expand to second and third pairs.
6. Once v2 demonstrates stable attribution and expected behavior, deprecate v1 module and update references.

Backout trigger:

- If v2 cannot classify failures better than v1 on known case, freeze rollout and reopen D1/D3.

Backout method:

- Keep v1 as authoritative until D1/D3 issues are resolved; do not delete v1 during investigation.

Migration Beat-4 inversion:

- Parallel migration could create two conflicting failure narratives in active PRs.
- Detection guard: require each L2.2 test module to state explicitly whether it uses v1 or v2 helper.

## 10) Risks and residual unknowns

R1. Schema extraction fidelity risk

- Likelihood: medium
- Impact: high
- Detection: compare schema WID lists to runtime process WID attributes during harness setup.
- Mitigation: fail fast on mismatches; permit per-process override.
- Owner: harness implementer

R2. Order-sensitive stochastic behavior risk

- Likelihood: medium
- Impact: medium/high
- Detection: deterministic vs randomized-sequential comparison runs.
- Mitigation: keep deterministic baseline plus optional stochastic stress mode.
- Owner: harness implementer + reviewer

R3. Ownership-manifest drift risk

- Likelihood: medium
- Impact: high
- Detection: manifest consistency checks against process write-path metadata.
- Mitigation: generator + explicit overrides + lint.
- Owner: harness implementer

R4. Attribution runtime cost risk

- Likelihood: low/medium
- Impact: medium
- Detection: measure diagnostic rerun cost on representative pairs.
- Mitigation: lazy diagnostics (only on mismatch) and capped reruns.
- Owner: harness implementer

R5. Scope confusion between L2.2 and L3

- Likelihood: medium
- Impact: medium
- Detection: ambiguous requests to push k upward without revisiting goals.
- Mitigation: enforce documented `k` boundary and escalation path.
- Owner: PM/operator

## 11) Operator review checklist

1. Does D1 explicitly fix the WID aliasing issue shown by translation/rna_processing schema evidence?
2. Does D2 align with Karr's sequential-with-random-order semantics rather than an invented parallel model?
3. Does D3 taxonomy provide actionable diagnostics beyond binary upstream/intrinsic labels?
4. Are unresolved decisions surfaced in QO1-QO6 with defaults and risks?
5. Is migration strategy clear enough to avoid destructive rewrites and preserve auditability?

