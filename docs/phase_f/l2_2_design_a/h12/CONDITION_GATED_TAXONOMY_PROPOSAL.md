# Proposal: `CONDITION_GATED` H12 taxonomy value for structurally-Monte-Carlo units

Status: **PROPOSAL ONLY — NOT IMPLEMENTED ON THIS BRANCH.**
This document does not modify `scripts/l22_evidence/verdict.py`,
`scripts/l22_evidence/generator.py`,
`docs/phase_f/l2_2_design_a/h12/h12_evidence_index.json`, or
`docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml`. It is a narrowly-scoped
design note for a future, separately-reviewed change, submitted alongside
the evidence artifact this proposal cites:
`docs/phase_f/l2_2_design_a/h12/condition_gated/
MacromolecularComplexation_h12_condition_gated.json`.

Author: Sonnet (implementation/evidence owner, this worktree). Reviewers:
GPT-5.6 Sol (adjudication), Opus 5 (independent review/test).

## 1. Problem this closes

`scripts/l22_evidence/h12.py`'s `REQUIRED_BRANCHES["MacromolecularComplexation"]`
includes `"network_ge2_fires"`. This branch can **never** be
`H12_CONFIRMED` for a structural reason documented in
`predict_macromolecular_complexation`'s own docstring (h12.py:437-470):
network >= 2 complex formation is a genuine Karr Monte Carlo competition
(`buildProteinComplexs_montecarlokinetic`, `MacromolecularComplexation.m`
lines 334-357, one `randStream.rand()` draw per while-loop iteration —
no closed form). H12's own predictor design requires `regime_valid=True`
samples for network>=2 to be exactly the all-`ub==0` (trivial) case, so
`nontrivial=True` and `regime_valid=True` can never co-occur for this
branch. This is not a temporary sampling gap; it is permanent by
construction.

As a result, `MacromolecularComplexation_h12.json` is capped at
`H12_OBSERVED_REGIME` forever, regardless of how many additional natural
seeds are sampled. There is currently no taxonomy value that distinguishes
this "permanently non-`H12_CONFIRMED`-eligible, but with independently
verified structural/conditional evidence" case from an ordinary,
potentially-closeable `H12_OBSERVED_REGIME` gap (e.g. a process merely
under-sampled so far).

## 2. What is NOT being proposed

- No change to `H12_CONFIRMED`'s existing meaning or gate strictness
  (`_has_valid_h12_support` in `verdict.py`, `EVALUATOR_SCHEMA_VERSION = 4`
  semantics, unchanged).
- No relaxation of any threshold, catalog entry, or required-branch list.
- No claim that `MacromolecularComplexation`'s overall process verdict
  changes as a result of this proposal — H12 support is one evidence
  channel among several consumed by `rederive_process`
  (`verdict.py:771-918`); a `CONDITION_GATED` H12 status would remain, at
  most, equivalent in strength to the current `H12_OBSERVED_REGIME`
  w.r.t. `_has_valid_h12_support` (still not `H12_CONFIRMED`, so still not
  independently sufficient to gate a channel green).
- No change to any other process's H12 artifact or required-branch list.

## 3. Proposed taxonomy addition

Add a new H12 top-level `verdict` value, `H12_CONDITION_GATED`, alongside
the existing `H12_CONFIRMED` / `H12_FAIL` / `H12_OBSERVED_REGIME`
(`h12.py:1118-1165`, `decide_verdict`). Semantics:

> `H12_CONDITION_GATED`: every required branch is either `H12_CONFIRMED`-
> eligible in the observed natural population, OR has an accepted,
> hash-bound, non-gating **conditional** artifact
> (`h12_condition_gated_evidence`, see
> `scripts/l22_evidence/h12_condition_gated.py`) demonstrating ALL THREE of:
> (a) the branch is unobserved in the accepted natural population, with a
> documented, source-cited reason for the non-firing AND an explicit,
> honestly-recorded `lifecycle_reachability_status` (whether the branch
> could ever fire naturally at a different lifecycle stage/tick window is
> stated as resolved-true, resolved-false, or `UNRESOLVED` — "unobserved in
> the sampled window" is recorded as an observed fact, never silently
> treated as a resolution of this question, and is NOT by itself
> sufficient for (a) without a documented reason); (b) the branch is
> demonstrably reachable under an explicit, narrowly-scoped, source-
> faithful state conditioning that changes NO stoichiometry/constants; and
> (c) the branch's own underlying mechanism is independently shown to be
> non-closed-form (Monte Carlo), making `H12_CONFIRMED` inapplicable to it
> by construction, not merely by insufficient sampling. Conditions (a),
> (b), and (c) are independently necessary — none of the three alone is
> sufficient, and in particular an unresolved `lifecycle_reachability_status`
> under (a) must never be conflated with a resolved unreachability claim.

This is **weaker** than `H12_CONFIRMED` and **stronger** than a bare,
uninvestigated `H12_OBSERVED_REGIME` gap: it certifies that the missing
branch has been actively investigated and cannot regress into "someone
eventually just needs to sample more" territory, while still refusing to
claim exact-match evidence that does not exist.

### 3.1 Where it would be wired (future change, not this branch)

- `scripts/l22_evidence/h12.py`: `decide_verdict` would need a new
  parameter/lookup (e.g. `condition_gated_refs: dict[str, Path]`) mapping
  process name -> accepted `h12_condition_gated_evidence` artifact path,
  consulted only when `missing_required_branches` is non-empty. This
  changes `EVALUATOR_SCHEMA_VERSION` (a semantic verdict change) and MUST
  follow the same re-derivation/staleness discipline
  `_has_valid_h12_support` already applies to `H12_CONFIRMED` (fresh
  re-hash of every referenced source, not soft-trust).
- `scripts/l22_evidence/verdict.py`: `h12_support_reason` /
  `_has_valid_h12_support` would need an explicit policy decision on
  whether `H12_CONDITION_GATED` support is treated identically to
  `H12_OBSERVED_REGIME` (i.e., still never independently sufficient to
  gate a channel green) or given a distinct, still-non-`H12_CONFIRMED`
  tier. This proposal recommends the former (no gating-strength change)
  to keep the risk surface minimal; a future change could revisit this
  only with fresh Opus/Sol sign-off.
- `docs/phase_f/l2_2_design_a/h12/h12_evidence_index.json`: would gain a
  new field (e.g. `condition_gated_artifact_path`) per process entry,
  populated only for processes with an accepted
  `h12_condition_gated_evidence` artifact.
- `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml`: no change is
  currently believed necessary — `H12_CONDITION_GATED` is an H12-internal
  verdict refinement, not a new top-level process disposition. This
  should be re-confirmed by whoever implements the change.

### 3.2 Acceptance criteria for enacting this (future PR)

1. `scripts/l22_evidence/h12_condition_gated.py`'s
   `validate_condition_gated_artifact` (already implemented, tested in
   `tests/scripts/test_h12_condition_gated.py`) becomes a REQUIRED,
   non-bypassable check inside `decide_verdict`/`_has_valid_h12_support`
   — never soft-trusted.
2. A process may only receive `H12_CONDITION_GATED` if EVERY currently
   missing required branch has its own accepted condition-gated artifact
   — partial coverage must remain `H12_OBSERVED_REGIME`.
3. `EVALUATOR_SCHEMA_VERSION` bump + full re-derivation of any
   dependent stored verdicts, per existing v3/v4 precedent
   (`verdict.py:52-124`).
4. New tests mirroring `test_h12_evidence_wiring.py`'s existing
   cross-process substitution / stale-hash / forged-field battery, scoped
   to the new `H12_CONDITION_GATED` path.
5. Explicit reviewer sign-off from Opus 5 and adjudication by GPT-5.6 Sol
   before merge — this is a genuine (if narrow) semantic change to the
   evidence gate, not a pure refactor.

## 4. Evidence this proposal is grounded in (already committed, this branch)

- `docs/phase_f/l2_2_design_a/h12/MacromolecularComplexation_h12.json` —
  accepted `H12_OBSERVED_REGIME`, 814/814 nontrivial exact-match,
  `network_ge2_fires` missing.
- `docs/phase_f/l2_2_design_a/h12/perturbation/
  MacromolecularComplexation_h12_perturbation.json` — accepted, non-gating
  `H12_PERTURBATION_OBSERVED_STOCHASTIC`; network 2 fires for real (ub=[17,15],
  6 distinct outcomes across 50 seeds) once only `MG_429_MONOMER`
  (PTS system E1) is conditioned from 0 to 40; all structural invariants hold.
- `docs/phase_f/l2_2_design_a/h12/
  MACROMOLECULARCOMPLEXATION_NETWORK2_E1_PROVENANCE.md` — E1 provenance
  investigation: E1 is fixture-constant zero across all 5000 accepted
  natural (seed, tick) samples; whether this reflects a genuine biological
  ceiling or a sampling-window artifact (the extractor's own
  `tick_offset` mechanism for late-activating species) is explicitly
  left unresolved, not papered over.
- `docs/phase_f/l2_2_design_a/h12/condition_gated/
  MacromolecularComplexation_h12_condition_gated.json` — this branch's new
  artifact mechanically binding all of the above, self-validating via
  `validate_condition_gated_artifact`, classification
  `CONDITION_GATED_CANDIDATE` (proposal-stage, not enacted).

## 5. Non-goals restated

No production biology, threshold, or catalog change is proposed or made
by this document or its companion artifact. No new MATLAB/Octave
execution occurred to produce this proposal. This document proposes a
taxonomy addition for future review; it does not itself change what
`H12_CONFIRMED` means or how strictly it is checked.
