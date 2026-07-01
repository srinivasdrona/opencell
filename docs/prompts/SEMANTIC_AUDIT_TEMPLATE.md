# Per-Process Semantic Wiring Audit Template (L1b Semantic Tier)

Status: canonical method for turning L1b structural PASS into semantic truth checks.
Use for: one process at a time (`data/schemas/per_process_wiring/<Process>.yaml`).
Do not use for: structural-only anchor checks (L1b Checks 1-7).

## Slot-1 carryover (DELIBERATE_ACTION_PREFIX_v2)

Apply all five beats in each audit run:
1. Beat 1 contract: prove/falsify row semantics against MATLAB + OC behavior.
2. Beat 2 surface: name exact row, MATLAB, OC, and (if needed) scheduler files.
3. Beat 3 expected outcome: claim table with strict verdict vocabulary + totals.
4. Beat 4 inversion: name how audit could "look complete" while still wrong. Empty Beat 4 allowed; missing Beat 4 not allowed.
5. Beat 5 verify: cite concrete branch/formula evidence per claim.

Required PM sanity-check sentence in each run: "PM: I am assuming row scope (full vs exemplar) is explicit; if not, completeness verdicts may be mis-attributed."

## DT §1 Design Contract (mandatory)

Contract:
- Required behavior: classify each audited claim as `VERIFIED`, `ROW_WRONG`, `CODE_DEVIATES`, or `MISSING`.
- Why this matters: structural PASS only proves anchors exist; it does not prove row truthfulness.
- Done = property statement: independent auditors can reproduce the same claim-level verdicts from the same sources.

Beat-4 inversion:
- Failure mode: claims pass because comments and anchors are read, but executed branches differ.
- Falsifier: each claim cites executable logic (condition, formula, route), not prose alone.

## DT §2 Inventory of Existing Artifacts (mandatory)

Minimum inventory for this methodology:
- [A01] path=docs/prompts/DELIBERATE_ACTION_PREFIX_v2.md | kind=doc | role=Beat discipline.
- [A02] path=docs/prompts/DESIGN_TEMPLATE.md | kind=doc | role=decision/verification/risk scaffolding.
- [A03] path=scripts/l1b_verify_wiring.py | kind=code | role=structural baseline this semantic tier extends.
- [A04] path=data/schemas/per_process_wiring/Metabolism.yaml | kind=schema | role=Day-43 hand-audited exemplar with known deviations.
- [A05] path=data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Metabolism.m | kind=code | role=MATLAB process behavior source.
- [A06] path=data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m | kind=code | role=MATLAB allocation + order semantics.
- [A07] path=opencell/vivarium/karr_metabolism.py | kind=code | role=OC runtime behavior and allocator bypass gates.
- [A08] path=opencell/vivarium/karr_request_calculators.py | kind=code | role=OC request emission path.
- [A09] path=opencell/vivarium/karr_allocation_step.py | kind=code | role=OC grant algorithm.
- [A10] path=opencell/m1/karr_metabolism_writeback.py | kind=code | role=OC writeback + projection (A4 surface).
- [A11] path=opencell/m1/calc_flux_bounds.py | kind=code | role=OC bounds source (A3 surface).
- [A12] path=opencell/m1/compartmented.py | kind=code | role=unit conversion evidence.

Inventory Beat-4 inversion:
- Missing artifact risk: scheduler/composition file omitted when auditing ordering claims.
- Reduction check: if ordering is audited, include concrete flow/scheduler source file.

## 1. Purpose

This audit checks whether a row semantically describes actual code behavior.

Why structural PASS is insufficient:
- Structural PASS confirms path/anchor existence.
- Structural PASS cannot detect false formulas, wrong routing, wrong allocator mode, or ordering drift.

Day-43 anchor:
- Metabolism had 4 semantic wiring bugs (A1-A4) that structural checks could not catch.
- These bugs are the target class:
  - A1 request/allocator participation mismatch.
  - A2 ordering semantics mismatch.
  - A3 LP-bound source mismatch.
  - A4 compartment projection mismatch.

Goal:
- Make semantic audits mechanical and repeatable.
- Separate row defects from implementation deviations.
- Produce immediate row-remediation priorities.

## 2. Scope Per Process (L1b Semantic Checks 8-13)

### S1 (Consume completeness)
- Definition: every MATLAB-consumed substrate appears in row `consume_stoichiometry` within declared row scope.
- Mechanical actions:
  1. Extract MATLAB consume set from executed consume lines.
  2. Extract row consume set.
  3. Compare set inclusion using chosen scope policy.
- Output: one or more claim rows.

### S2 (Consume fabrication)
- Definition: each row consume entry maps to a real OC consume path.
- Mechanical actions:
  1. For each row consume claim, inspect OC anchor branch.
  2. Confirm consume path exists for claimed substrate.
  3. If sign-dependent, keep verdict + add `judgment=required`.
- Output: claim rows by consume family.

### S3 (Produce completeness + fabrication)
- Definition: S1+S2 equivalent for `produce_stoichiometry`.
- Mechanical actions:
  1. MATLAB produce set vs row produce set (completeness).
  2. Row produce entries vs OC emit path (fabrication).
- Output: claim rows by produce family.

### S4 (Formula match)
- Definition: MATLAB and OC formulas are mathematically equivalent modulo syntax.
- Mechanical actions:
  1. Normalize formulas to operation skeletons.
  2. Compare operation order, factors, signs, and rounding placement.
  3. Flag mismatches with exact branch references.
- Output: claim rows by formula family.

### S5 (Compartment routing match)
- Definition: MATLAB and OC target the same `(substrate, compartment)` tuples.
- Mechanical actions:
  1. Extract tuple targets from MATLAB writes.
  2. Extract tuple targets from OC internal writes and emitted outputs.
  3. Explicitly detect projection/merge loss at output.
- Output: at least one agreement claim + one mismatch claim if projection exists.

### S6 (Allocator engagement match)
- Definition: MATLAB participation mode (`calcResourceRequirements`/allocation path) matches OC (`RequestCalculatorX` + grant use or bypass).
- Mechanical actions:
  1. Verify request formula source and grant application path.
  2. Verify bypass gates.
  3. Verify bound/consume path uses allocated vs internal/shared pools.
  4. If ordering affects allocator semantics, include ordering claim under S6.
- Output: claim rows for request formula, grant use, bypass, and order-coupled behavior.

## 3. Verdict Vocabulary Per Claim

Allowed values only:
- `VERIFIED`: row, MATLAB, and OC consistent for this claim.
- `ROW_WRONG`: row misstates behavior (or is too ambiguous to test).
- `CODE_DEVIATES`: row correctly describes MATLAB-vs-OC divergence.
- `MISSING`: MATLAB behavior exists but row omits claim.

Precedence:
1. If row is inaccurate/ambiguous, use `ROW_WRONG` first.
2. Use `CODE_DEVIATES` only when row is accurate about both sides.
3. Use `MISSING` for omission, not uncertainty.
4. For discretionary cases, keep verdict and append `judgment=required` in Note.

## 4. Output Shape Per Process

One markdown file per process:
- `docs/phase_f/audits/{PROCESS_NAME}_semantic_audit.md`

Required table columns:
- `Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note`

Column rules:
- `Claim ID`: stable, process-scoped ID (`PROC-S4-03` style).
- `Category`: exactly one of `S1..S6`.
- `Row Says/MATLAB Says/OC Says`: concise factual statement with path:line references.
- `Verdict`: one of the four allowed labels.
- `Note`: include `judgment=required` where applicable.

Required aggregate footer:
- `VERIFIED: <n>`
- `ROW_WRONG: <n>`
- `CODE_DEVIATES: <n>`
- `MISSING: <n>`

Required Priority-1 list:
- Include all `ROW_WRONG` and `MISSING` claims needing immediate row remediation.
- If none: write `Priority-1 fixes: none`.

## 5. Attribution Rules For Edge Cases

A. Intentional reimplementation in OC:
- If row accurately states MATLAB vs OC difference and intent is explicit -> `CODE_DEVIATES` with note `intentional reimplementation`.

B. Ambiguous row claim:
- If claim is not mechanically testable -> `ROW_WRONG` with note `ambiguity`.

C. Anchor drift after OC refactor:
- If semantics still exist but row line range is stale -> `ROW_WRONG` with note `anchor rot`.
- Structural anchor checks remain complementary.

D. Exemplar row scope:
- If row explicitly says non-exhaustive, operator policy controls completeness attribution:
  - strict policy: omissions -> `MISSING`.
  - exemplar policy: assess declared exemplars only + `judgment=required`.
- Auditor must state chosen policy; never assume silently.

E. Sign-dependent consume/produce:
- Do not force binary direction if formula is signed.
- Keep verdict and mark `judgment=required: sign-dependent`.

## 6. Mechanical Criteria (No-Judgment Checks)

Mechanical checks:
1. File path exists.
2. Anchor symbol/range exists.
3. Substrate token appears where claimed.
4. Formula tokens/operators appear where claimed (`stochasticRound`, `max`, `fix/floor`, sign vector, `/stepSizeSec`).
5. Required stores/ports exist (`requests`, `substrates_allocated`, `substrates`).
6. Bypass guard branch exists or not (`use_allocator_budget`, similar).
7. Compartment projection is explicit (`sum(axis=1)`, flatten, map merge).
8. Allocator rule shape exists (request matrix, scaling, floor).
9. Scheduler primitive exists/absent (`randperm` or equivalent).
10. Known-deviation IDs are encoded in row and traceable to source anchors.

### Auditor discretion required

Must be flagged:
1. Sign-dependent net consume/produce interpretation.
2. Exemplar-scope completeness policy choice.
3. Algebraic equivalence with reordered operations.
4. Intentional-vs-accidental implementation drift.
5. Ordering semantics split across multiple runtime files.

Policy:
- If judgment is required, do not guess silently.
- Keep best-supported verdict and append `judgment=required` in Note.

## DT §5 Decision Ledger (mandatory)

Decision D1:
- Question: claim granularity?
- Options: (1) per-substrate exhaustive, (2) grouped by formula family, (3) one global verdict.
- Chosen: (2).
- Rationale: balances reproducibility with 15-30 minute run budget.
- Tradeoff: less per-substrate detail per pass.
- Beat-4 inversion: grouped claims can hide one substrate error.
- Falsifier: require explicit claims for all known deviations + each formula family.
- Escalation needed: no.

Decision D2:
- Question: mismatch taxonomy?
- Options: (1) single mismatch label, (2) split row vs code attribution, (3) many labels.
- Chosen: (2) `ROW_WRONG` vs `CODE_DEVIATES`.
- Rationale: remediation owner differs.
- Tradeoff: stricter attribution burden.
- Beat-4 inversion: overuse `CODE_DEVIATES` to avoid row edits.
- Falsifier: enforce precedence (`ROW_WRONG` first when row inaccurate).
- Escalation needed: no.

Decision D3:
- Question: ambiguous row prose handling?
- Options: (1) interpret best-effort, (2) mark wrong, (3) defer unresolved.
- Chosen: (2).
- Rationale: ambiguity breaks mechanical reproducibility.
- Tradeoff: harsher labeling on legacy prose.
- Beat-4 inversion: terse but valid claims may be flagged unfairly.
- Falsifier: require explicit ambiguity reason in Note.
- Escalation needed: no.

Decision D4:
- Question: ordering claim placement?
- Options: (1) ignore ordering, (2) include under S6, (3) add S7 now.
- Chosen: (2) for this version.
- Rationale: ordering can change allocator-coupled semantics.
- Tradeoff: S6 scope broadens.
- Beat-4 inversion: ordering-only bugs under-emphasized.
- Falsifier: require explicit ordering claim when known deviations cite it.
- Escalation needed: no.

Decision D5:
- Question: exemplar completeness policy default?
- Options: (1) strict omissions -> `MISSING`, (2) exemplar-scoped with `judgment=required`, (3) skip completeness checks.
- Chosen: (2) initial rollout default.
- Rationale: avoids immediate false-failure flood while still surfacing policy dependence.
- Tradeoff: cross-process comparability depends on operator policy lock.
- Beat-4 inversion: overuse of exemplar exception.
- Falsifier: require explicit row text proving non-exhaustive scope.
- Escalation needed: yes (operator policy lock).

## DT §6 Verification Claims (mandatory)

Claim C1:
- If template is correct, two independent auditors produce identical verdict labels for the same claim IDs on one process.
- Measurement: dual-run audit using same sources.
- Threshold: claim-level label match.
- Why load-bearing: detects under-specified attribution rules.

Claim C2:
- If template is correct, Metabolism A1-A4 appear as `CODE_DEVIATES`.
- Measurement: run worked example using this template.
- Threshold: exactly 4 A1-A4 `CODE_DEVIATES` entries.
- Why load-bearing: proves semantic tier catches known structural-PASS misses.

Claim C3:
- If template is correct, discretion-heavy claims are not silent.
- Measurement: inspect Note column.
- Threshold: every discretion-needed claim includes `judgment=required`.
- Why load-bearing: prevents silent guesswork.

Verification Beat-4 inversion:
- Possible false pass: auditor copies prior verdicts without re-reading sources.
- Guardrail: each claim requires path:line evidence.

## DT §7 Open Questions For Operator (mandatory)

QO1. Exemplar rows policy lock?
- Why unresolved: rows differ in completeness intent.
- Options: strict vs exemplar-scoped.
- Recommended default: exemplar-scoped now, strict later.
- Risk if wrong: skewed `MISSING` rates.

QO2. Should ordering become explicit S7?
- Why unresolved: currently embedded in S6.
- Options: keep S6-only or promote to S7 in next revision.
- Recommended default: keep in S6 for first fleet run.
- Risk if wrong: ordering bugs undercounted.

QO3. Formula-match depth level?
- Why unresolved: token skeleton vs symbolic equivalence.
- Options: skeleton+order vs full symbolic proofs.
- Recommended default: skeleton+order.
- Risk if wrong: subtle formula drift escapes.

QO4. Discretion cap per process?
- Why unresolved: too many discretionary claims hurt comparability.
- Options: no cap vs capped + operator review.
- Recommended default: cap and escalate above cap.
- Risk if wrong: inconsistent fleet outputs.

QO5. Immediate remediation policy for `MISSING`?
- Why unresolved: some omissions are known temporary gaps.
- Options: always remediate rows vs defer with tracker.
- Recommended default: remediate row truth immediately.
- Risk if wrong: stale misleading rows persist.

## DT §10 Risks and Residual Unknowns (mandatory)

R1. Exemplar-policy drift across auditors.
- Likelihood: medium
- Impact: high
- Detection: high variance in S1/S3 counts.
- Mitigation: lock operator policy before fleet pass.
- Owner: operator

R2. Ordering evidence omitted.
- Likelihood: medium
- Impact: medium
- Detection: A2-like claims marked verified without scheduler source.
- Mitigation: require scheduler file in Beat-2 surface when ordering is audited.
- Owner: auditor

R3. Token-level formula checks miss deep algebraic drift.
- Likelihood: medium
- Impact: medium
- Detection: replay mismatch despite S4 verified.
- Mitigation: escalate high-impact formulas to deeper symbolic review.
- Owner: auditor + operator

R4. Over-attribution to `CODE_DEVIATES`.
- Likelihood: medium
- Impact: high
- Detection: many `CODE_DEVIATES` with weak row statements.
- Mitigation: strict verdict precedence (`ROW_WRONG` first if row inaccurate).
- Owner: auditor
