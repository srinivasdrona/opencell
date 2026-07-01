# Task: Semantic Wiring Audit for {PROCESS_NAME}

You are codex (gpt-5.3-codex). Work directly on `main` in `E:\opencell`.

Audit objective:
- Execute a semantic per-process wiring audit for `{PROCESS_NAME}`.
- Compare row claims against MATLAB behavior and OC behavior.
- Do not do structural-only checks; this is semantic validation.

Process metadata:
- Process slug: `{PROCESS_SLUG}`

## Python interpreter - MANDATORY

Use:
- `bin\oc-py <script.py>`

Do not use:
- `python ...`
- `pytest ...` (unless explicitly requested by this task)

## Slot 1: DELIBERATE_ACTION_PREFIX_v2

Apply all five beats from:
- `docs/prompts/DELIBERATE_ACTION_PREFIX_v2.md`

Constraint:
- Empty Beat 4 is allowed.
- Missing Beat 4 is not allowed.

## Slot 2: Revision-Class Minimum (audit is not a design task)

Use the revision-class minimum discipline from:
- `docs/prompts/DESIGN_TEMPLATE.md`

Required minimum for this audit run:
- design contract sentence (what semantic truth is being checked)
- decision ledger for non-obvious attribution calls
- risks section for unresolved ambiguity

Do not author a full design document.

## Slot 3: Process-specific semantic audit instructions

### Inputs to read (mandatory)

1. Row file:
- `data/schemas/per_process_wiring/{PROCESS_NAME}.yaml`

2. MATLAB file(s):
- `{MATLAB_FILE}`
{MATLAB_SUPPORT_FILES}

3. OC file(s):
{OC_FILES}

4. Methodology template:
- `docs/prompts/SEMANTIC_AUDIT_TEMPLATE.md`

### Deliverable path (mandatory)

Write exactly one audit file:
- `docs/phase_f/audits/{PROCESS_NAME}_semantic_audit.md`

### Claims to check (all required)

Audit all six semantic categories:

1. `S1 (Consume completeness)`
- Every substrate MATLAB consumes appears in row `consume_stoichiometry` (within declared row scope policy).

2. `S2 (Consume fabrication)`
- Every row consume entry has a real OC consume path.

3. `S3 (Produce completeness + fabrication)`
- Produce side equivalent of S1 and S2.

4. `S4 (Formula match)`
- MATLAB and OC formulas are mathematically equivalent modulo syntax.
- Include concrete formula families (for example uptake, hydrolysis, clipping, bounds transforms).

5. `S5 (Compartment routing match)`
- MATLAB and OC target the same `(substrate, compartment)` tuples.
- Explicitly test for compartment projection/merge behavior.

6. `S6 (Allocator engagement match)`
- MATLAB allocator participation mode vs OC request/grant or bypass mode.
- Include allocator-coupled ordering claims when relevant.

### Required verdict vocabulary

Use only:
- `VERIFIED`
- `ROW_WRONG`
- `CODE_DEVIATES`
- `MISSING`

Rules:
- Prefer `ROW_WRONG` when row statement is false or ambiguous.
- Use `CODE_DEVIATES` only when row correctly describes MATLAB-vs-OC divergence.
- For discretionary judgment, keep verdict but append `judgment=required` in Note.

### Required output format

The audit file must contain:

1. Header block:
- process name
- audited files list
- scope policy (strict completeness vs exemplar-scoped completeness)

2. Claim table with exact columns:

`Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note`

3. Aggregate counts:
- `VERIFIED: <n>`
- `ROW_WRONG: <n>`
- `CODE_DEVIATES: <n>`
- `MISSING: <n>`

4. Priority-1 fixes:
- list all `ROW_WRONG` and `MISSING` claims that need immediate row remediation
- if none, write `Priority-1 fixes: none`

5. Optional but recommended:
- known-deviation mapping (for example A1-A4)
- auditor discretion list (`judgment=required` claims)

### Mechanical execution rules

- Do not silently guess.
- If a claim needs interpretation, mark it with `judgment=required` in Note.
- Do not mutate row/code while auditing unless explicitly asked.
- Keep claim IDs stable and deterministic.

### Budget

- Soft: 15-20 minutes
- Hard: 30 minutes

If hard budget is exceeded:
- finish current evidence capture
- write partial audit with explicit `PARTIAL` marker in the header note

### Commit requirements

Single commit expected for this process audit:
- Commit message: `audit(l1b-semantic): {PROCESS_NAME} per-process semantic audit`
- Required trailer:
  - `Catalog-Entry: N/A (justification: audit-only docs, no L2-catalog impact)`

Do not push.

### Final checklist

- [ ] All six categories S1-S6 covered by at least one claim row
- [ ] Verdict vocabulary constrained to allowed set
- [ ] Aggregate counts included
- [ ] Priority-1 list included
- [ ] File saved at `docs/phase_f/audits/{PROCESS_NAME}_semantic_audit.md`
- [ ] Commit created with required trailer
