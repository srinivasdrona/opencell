# DESIGN_TEMPLATE

Status: reusable slot-2 template for multi-file design-doc authoring (parallel to `FIX_TEMPLATE_*` artifacts).

**Composition mandate.** This template is **slot 2** in the 3-slot codex prompt architecture. Before composing a design-doc delegation, read `docs/prompts/COMPOSITION_MANDATE_v2.md` — it defines slot roles, slot-3 size heuristics (floor and ceiling), the spec-authority rule, and the slot-to-patch routing rules for diagnosing failures.

## Trigger guardrail (apply template only when needed)

Use this template when any of the following is true:

1. Task touches more than 2 files.
2. Task introduces a new test/build category (new harness layer, schema family, framework, integration surface).
3. Task is an architectural fork (multiple durable options; choice affects future work).

Do not use this template for:

1. Single-file bug fixes.
2. One-function repairs.
3. Incremental refactors with no durable architecture decision.

Goal: enforce decision quality where ambiguity and cross-surface risk are real, without adding ceremony to trivial work.

## Revision-class minimum (added 2026-06-27 after Day-40 V1→V4 trajectory)

For REVISION-class work (patching an existing design after critique), use a
lighter shape than the full template:

- **MANDATORY**: §1 design contract, §5 decision ledger (one card per BLK/NB
  fix), §10 risks. Plus the slot-3 spec-authority quote block and a self-audit
  checkbox table mapping each critique item to a §5 decision.
- **OPTIONAL**: §2 inventory, §6 verification claims, §7 operator questions.
- **SKIP**: §3 interaction-surface map, §9 migration path, §11 review
  checklist. These add ceremony without changing decision quality for
  revisions.
- **Target**: 80-200 lines instead of 250-400.

The decision-card format (options/chosen/rationale/Beat-4 inversion/falsifier)
is the load-bearing element of this template; the rest is right-sized for
genuine multi-fork architectural authoring, not revisions. See
`D:\OneDrive - Microsoft\.pm-os\DECISIONS.md` entry
`2026-06-27 | cross-cutting | empirical-probe-before-design-iteration` for
the empirical anchor (Day-40 L2.2 Metabolism MF4 V1=832L→V4=357L iteration).

Companion rule: **before commissioning a full design iteration, check whether
the design's core assumption can be probed empirically in <1h. If yes, run the
probe first.** Day-40 V4-probe falsified V4's core assumption in 27 minutes;
the V2/V3/V4 design rounds could have been skipped had the probe run after V1.

## Acceptance bar (author must check before requesting review)

The design doc is not review-ready until every item is checked:

1. [ ] Design contract is stated as a system property (not "test passes").
2. [ ] Inventory manifest is present, machine-checkable, and has at least `N_inventory` entries (`N_inventory >= 8` by default).
3. [ ] Interaction-surface map explicitly names cross-component/process/schema/store boundaries.
4. [ ] Every major decision has options considered, chosen option, rationale, and Beat-4 inversion.
5. [ ] Falsifiable expected outcomes are stated for the chosen design before implementation.
6. [ ] Open questions for operator section has at least `N_questions` entries (`N_questions = 5` default).
7. [ ] Scope boundary section clearly states in-scope and out-of-scope.
8. [ ] Migration/backout path is documented for existing code/artifacts.
9. [ ] Risks and residual unknowns are explicit (no silent assumptions).

## Slot-1 carryover (Deliberate Action Prefix for design work)

At the top of the design doc, include:

1. Contract (Beat 1): what system behavior must hold when this design is implemented.
2. Surface inventory intent (Beat 2): where evidence will come from.
3. Falsifiable expectation (Beat 3): what observable claims should hold if design is correct.
4. Inversion (Beat 4): most embarrassing way this design could look right while being wrong.
5. PM/operator sanity-check sentence.

Empty inversion is allowed. Missing inversion is not.

## Required section order

All sections below are mandatory unless explicitly marked optional.

### 1) Design contract (mandatory)

Template:

```
Contract:
- Required behavior:
- Why this matters:
- Done = (property statement, not command success):

Beat-4 inversion:
- Most plausible "looks right, is wrong" failure mode:
- What would falsify this contract statement:
```

### 2) Inventory of existing artifacts (mandatory, machine-checkable)

Purpose: force a grep-and-list pass so relevant prior artifacts are surfaced before design choices harden.

Default minimum: `N_inventory = 8`.

Use this exact list-item schema:

```
- [A01] path=<repo-path or branch:path> | kind=<code|doc|trace|schema|status|commit|other> | role=<one-line design relevance>
- [A02] path=<...> | kind=<...> | role=<...>
...
```

Rules:

1. Path must be concrete (no "relevant docs").
2. Role must be specific ("defines substrate WID order", "contains current failure attribution behavior", etc.).
3. At least one artifact must be a prior failed attempt/status when such artifact exists.
4. At least one artifact must be a primary source/spec when available.
5. For any artifact claimed as a data source, fixture, or evidence anchor (kind=data, trace, schema, fixture): verify at least one field/record loads correctly via code before claiming it contains usable content. File existence ≠ content correctness — placeholder strings, flatten-errors, and empty arrays are common in extracted MATLAB artifacts.

Beat-4 inversion for inventory:

```
- What critical artifact could still be missing from this list?
- What check did you run to reduce that risk?
- What could be WRONG in the artifacts we listed? (Presence ≠ correctness.
  A fixture file can exist and contain placeholder strings instead of data.
  A schema can list a column that is never populated. A trace can have the
  right keys but wrong shapes. For each data-source artifact, state what
  content check was run — or flag "content not verified" explicitly.)
```

### 3) Interaction-surface map (mandatory)

Name every cross-surface touched by the design.

Use this table shape:

| Surface ID | Producer | Consumer | Contract unit | Failure if mismatched | Evidence anchor |
|---|---|---|---|---|---|
| S1 | ... | ... | ... | ... | ... |

Include at minimum:

1. Data-shape boundaries (length/order/schema/version).
2. Execution-order boundaries (scheduler/order semantics).
3. Ownership boundaries (who writes, who reads, who validates).
4. External contract boundaries (trace/oracle/spec/config).

Beat-4 inversion:

```
- Which cross-surface assumption is most likely false?
- What observation would expose that quickly?
```

### 4) Baseline facts and constraints (mandatory)

> **Boundary rule (added 2026-06-01 after first dogfood):** if a fact is *single-component* (lives inside one process / one schema / one file), it belongs here. If it is *multi-component* (touched by ≥2 processes, shared across schemas, or describes alignment between components), it belongs in section 3 (Interaction-surface map). When uncertain, prefer section 3 — cross-surface evidence is the section more likely to be skimmed thin, and was the slot the L2.2.k miss happened in.

Capture non-negotiables before options:

1. Hard constraints from project/session context.
2. Fidelity constraints from primary source.
3. Existing implementation facts (what already exists, **single-component only**).
4. Known failures and anti-patterns.

Keep this as facts only; do not present preferred design yet.

Beat-4 inversion:

```
- Which baseline "fact" is inferred rather than proven?
- What would invalidate it?
```

### 5) Decision ledger (mandatory)

Each major decision must use a decision card:

```
Decision D#
- Question:
- Options considered:
  1) ...
  2) ...
  3) ...
- Chosen option:
- Rationale:
- Tradeoffs accepted:
- Beat-4 inversion (how chosen option could be wrong):
- Falsifier (what evidence would force reopening D#):
- Operator escalation needed? <yes/no + question id if yes>
```

Minimum: 3 decision cards for medium complexity; 5+ for architectural forks.

### 6) Expected outcomes and verification claims (mandatory)

State falsifiable claims before implementation:

```
Claim C1:
- If design is correct, we should observe:
- Measurement method / command / assertion:
- Threshold or exact value:
- Why this distinguishes from alternatives:
```

Include at least one claim that can fail even if basic tests pass.

Beat-4 inversion:

```
- How could these claims pass while design is still wrong?
- Additional guardrail to close that hole:
```

### 7) Open questions for operator (mandatory, non-empty)

Default minimum: `N_questions = 5`.

Rationale for `N_questions = 5`:

1. Fewer than 3 usually hides unresolved forks.
2. 5 is enough to expose material decision surfaces without turning review into an interrogation.
3. Forces explicit escalation instead of silent assumptions.

Format:

```
QO1. <question>
- Why unresolved:
- Options:
  1) ...
  2) ...
- Recommended default (if no response):
- Risk if wrong:
```

No empty section allowed. If truly no questions, state why and include a self-audit proving all forks were decided by source constraints.

### 8) Scope boundary (mandatory)

Use explicit lists:

```
In scope:
1. ...
2. ...

Out of scope:
1. ...
2. ...

Deferred follow-ups:
1. ...
```

Beat-4 inversion:

```
- Most likely scope-creep vector:
- How this doc prevents it:
```

### 9) Migration and rollout path (mandatory when replacing existing implementation)

Document how to move from current state to designed state:

1. Strategy (revert, parallel-v2, in-place refactor, or hybrid).
2. Sequence of steps.
3. Backout trigger and backout method.
4. Compatibility period (if dual paths coexist).

Beat-4 inversion:

```
- How migration could strand partially-updated code:
- Checkpoint or guard to detect that state:
```

### 10) Risks and residual unknowns (mandatory)

List unresolved technical risks after design choices.

Format:

```
R1. <risk>
- Likelihood:
- Impact:
- Detection:
- Mitigation:
- Owner:
```

### 11) Operator review checklist (mandatory)

Provide a short checklist the operator can run while reviewing:

1. Did inventory list concrete artifacts and include at least one branch-only or non-obvious source where applicable?
2. Are cross-surfaces explicit and testable?
3. Does each major decision include inversion and falsifier?
4. Are operator decisions clearly separated from implementer assumptions?
5. Is scope boundary tight enough to prevent ad-hoc expansion?

## Authoring notes (non-binding guidance)

1. Prefer primary sources over second-hand summaries.
2. Cite exact paths for each claim-critical anchor.
3. If the design includes numeric/vector semantics, quote concrete examples.
4. If a prior STATUS misdiagnosed a failure, include that as an anti-pattern anchor.
5. Keep decisions auditable: future implementers should be able to regenerate why a choice was made.

## Quick-start skeleton

```
# <CASE_NAME>_DESIGN

## DAP Intent
...

## 1) Design contract
...

## 2) Inventory of existing artifacts
- [A01] path=...

## 3) Interaction-surface map
| Surface ID | Producer | Consumer | Contract unit | Failure if mismatched | Evidence anchor |

## 4) Baseline facts and constraints
...

## 5) Decision ledger
Decision D1...

## 6) Expected outcomes and verification claims
Claim C1...

## 7) Open questions for operator
QO1...

## 8) Scope boundary
...

## 9) Migration and rollout path
...

## 10) Risks and residual unknowns
...

## 11) Operator review checklist
...
```

