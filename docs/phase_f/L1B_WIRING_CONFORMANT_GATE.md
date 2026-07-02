# L1b Wiring Conformant Gate

## DAP Intent (Slot 1)
Beat 1 - Pause and name the contract:
- Required behavior from `plan.md` L-ladder + L1b prompt: each per-process wiring row must be statically checked against the referenced OC/MATLAB code and schema TOML so row claims are mechanically verifiable.
- Done means: for every checked row, L1b emits deterministic per-check verdicts and an aggregate PASS/FAIL gate without running chassis/runtime/oracles.

Beat 2 - Point at the surface:
- Read surfaces: `data/schemas/per_process_wiring/_schema.yaml`, `data/schemas/per_process_wiring/*.yaml`, `data/schemas/per_process/*.toml`, referenced `.py`/`.m` source files.
- Write surfaces: `scripts/l1b_verify_wiring.py`, `tests/integration/test_l1b_verify_wiring.py`, first-run report artifacts under `tmp/` and docs under `docs/phase_f/`.
- Suspect patterns called out pre-implementation: placeholder symbols (`NOT_IMPLEMENTED`, `n/a`), conceptual block symbols (not literal defs), and mixed file encodings in MATLAB sources.

Beat 3 - Verbalize expected outcome:
- Distinguishing command: `bin\oc-py scripts/l1b_verify_wiring.py --format md`.
- Expected observable: structured row-by-row verdicts, per-check aggregates, and exit-code gate semantics (`0` only when all rows PASS; `1` otherwise).
- Smallest reachable initial state: static repository checkout with existing wiring YAML + TOML schema files only.

Beat 4 - Invert (pre-mortem):
- Most embarrassing false-pass mode: the checker only verifies path existence and broad symbol text, while row-specific anchor line claims or Python symbol identity are wrong.
- Guardrail selected: hybrid detection for OC anchors (regex + AST line-window validation) and explicit check-level failure attribution.

Beat 5 - Act, then verify:
- Implement checker + tests first, then run required first-run capture and produce faithful L1b verdict docs without remediating row failures.

PM sanity-check sentence:
- This design assumes L1b should fail when row assertions use non-implementing placeholders (`NOT_IMPLEMENTED`, `n/a`) because those are non-conformant row-vs-code claims, even if intentional as roadmap markers.

## Spec Authority Quote Block
> "L1b verifies that the per-process wiring DB rows ... accurately describe what the OC code actually does. It is a static verification gate - no runtime, no oracle, no chassis run."
>
> "Implement these as separate check functions ... Each returns a `CheckResult(verdict: str, details: list[str])` dict."

## 1) Design Contract
Contract:
- Required behavior: provide a static, deterministic row-vs-code conformance gate over all wiring rows (or one targeted row) with seven named checks.
- Why this matters: L1a proves process firing exists, but L1b proves row assertions reflect real code/schema wiring and catches anchor or WID drift before L2.4 (chassis autonomous conservation; renamed from "L1c" on 2026-07-02).
- Done = property statement: any repo state can be evaluated into reproducible per-check/per-row verdicts and aggregate gate verdict, without dynamic simulation execution.

Beat-4 inversion:
- Most plausible "looks right, is wrong" failure mode: checker output is aggregated only, hiding which field in which row failed and making remediation guesswork.
- Falsifier: a failing row must include check name and field-level details containing both row-path label and referenced source/TOML file name.

## 2) Inventory of Existing Artifacts
- [A01] path=data/schemas/per_process_wiring/_schema.yaml | kind=schema | role=contract for row shape and anchor fields consumed by L1b.
- [A02] path=data/schemas/per_process_wiring/Metabolism.yaml | kind=schema | role=gold-standard row used for check-1/check-2 expected pass behavior.
- [A03] path=data/schemas/per_process_wiring/*.yaml | kind=schema | role=28-row verification corpus for gate-wide first run.
- [A04] path=data/schemas/per_process/*.toml | kind=schema | role=authoritative process WID state groups for check-3/check-4.
- [A05] path=scripts/build_wiring_db.py | kind=code | role=existing wiring schema traversal conventions and row discovery patterns.
- [A06] path=scripts/inspect_wiring_db.py | kind=code | role=reporting style and aggregate rendering baseline for wiring artifacts.
- [A07] path=tests/integration/test_build_wiring_db.py | kind=test | role=integration-test style for schema scripts and synthetic-source fixtures.
- [A08] path=docs/prompts/DELIBERATE_ACTION_PREFIX_v2.md | kind=doc | role=Slot-1 mandatory five-beat structure.
- [A09] path=docs/prompts/DESIGN_TEMPLATE.md | kind=doc | role=revision-class minimum and mandatory decision-ledger requirements.

Inventory Beat-4 inversion:
- Missing-artifact risk: per-process TOML filename mapping edge cases (`tRNAAminoacylation` vs `trna_aminoacylation`).
- Risk reduction check: design includes normalized-name TOML resolution plus fallback underscore-case mapping.

## 5) Decision Ledger
Decision D1
- Question: check granularity should be row aggregate only or field-level surfaced?
- Options considered:
1. Aggregate PASS/FAIL only per row.
2. Per-field verdict records for every anchor/WID tuple.
3. Per-check verdict per row with field-level details in `details`.
- Chosen option: 3.
- Rationale: preserves compact gate semantics while retaining actionable failure localization.
- Tradeoffs accepted: details are string-based (not fully typed JSON schema per field).
- Beat-4 inversion: too much detail could become noisy and obscure gate-level status.
- Falsifier: if operators cannot identify failing field+file from one row report, D1 must be reopened.
- Operator escalation needed? no.

Decision D2
- Question: anchor validation strictness model?
- Options considered:
1. Strict always (`lines ± 5` required).
2. Lenient always (symbol anywhere in file).
3. Configurable `--strict-anchors`.
- Chosen option: 3, default lenient.
- Rationale: supports broad repo applicability now while preserving a strict hardening mode for later use.
- Tradeoffs accepted: lenient mode can accept anchors with imprecise line claims.
- Beat-4 inversion: lenient mode may mask stale line spans.
- Falsifier: if strict mode and lenient mode produce materially divergent pass rates on stable rows, default policy must be revisited.
- Operator escalation needed? no.

Decision D3
- Question: missing WIDs in process TOML should fail or warn?
- Options considered:
1. Warn-only for missing WIDs.
2. Fail on missing WIDs; warn when present but outside `substrates`.
3. Fail on any non-substrate placement.
- Chosen option: 2.
- Rationale: missing WID is structural drift; non-substrate placement can be valid (enzyme/monomer/complex/rna).
- Tradeoffs accepted: warnings can accumulate for rows that intentionally reference non-substrate groups.
- Beat-4 inversion: permissive non-substrate warning could hide truly mis-grouped chemistry.
- Falsifier: if remediation repeatedly shows non-substrate warnings are actual bugs, promote to FAIL policy.
- Operator escalation needed? no.

Decision D4
- Question: symbol-in-code detection strategy?
- Options considered:
1. Regex only.
2. AST only.
3. Hybrid: regex for all anchors + AST line-window validation for Python OC anchors.
- Chosen option: 3.
- Rationale: handles MATLAB `.m` and markdown-extracted anchors while enforcing stronger identity checks on OC Python code.
- Tradeoffs accepted: dual-path logic is more complex and may surface encoding edge cases.
- Beat-4 inversion: regex pass + AST mismatch could create confusing mixed signals.
- Falsifier: if repeated false negatives appear on valid Python anchors, adjust AST symbol matching rules.
- Operator escalation needed? no.

Decision D5
- Question: failure attribution should point to row, code, or both?
- Options considered:
1. Code-only attribution.
2. Row-only attribution.
3. Row field label + source file anchor path (both).
- Chosen option: 3.
- Rationale: remediation starts in row YAML but usually resolves in code or anchor maintenance.
- Tradeoffs accepted: longer failure strings.
- Beat-4 inversion: attribution could still be too coarse if multiple anchors share one symbol.
- Falsifier: if triage requires opening script internals to determine failing tuple, attribution schema must be enriched.
- Operator escalation needed? no.

Decision D6 (2026-07-01 post-hoc)
- Question: how should Check 1 handle MATLAB source files that are not UTF-8 decodable?
- Options considered:
1. Fail immediately on Unicode decode error.
2. Fall back to latin-1 only when UTF-8 decode fails.
3. Attempt broad codec guessing.
- Chosen option: 2.
- Rationale: Karr `.m` sources include legacy bytes; latin-1 fallback preserves static anchor checks without masking non-decode errors.
- Tradeoffs accepted: latin-1 decode can admit mojibake in comments, but symbol detection remains reliable.
- Beat-4 inversion: fallback could accidentally hide a genuinely corrupted file.
- Falsifier: if symbol extraction quality regresses after fallback, tighten to extension- and check-scoped decoding rules.
- Operator escalation needed? no.

Decision D7 (2026-07-01 post-hoc)
- Question: how should Check 1 treat `E:/opencell-mirrors/...` anchor paths?
- Options considered:
1. Treat as normal absolute path and fail if mirror is absent.
2. Attempt rewrite to repo-relative when mirror-style prefix is detected.
3. Auto-rewrite rows in-memory without warning.
- Chosen option: 2.
- Rationale: improves environment portability while preserving explicit diagnostics for non-canonical rows.
- Tradeoffs accepted: rewrite logic adds path-policy branching in Check 1.
- Beat-4 inversion: silent rewrites could conceal stale row authorship practices.
- Falsifier: if mirror rewrites appear in stable rows repeatedly, promote row canonicalization to a separate hard gate.
- Operator escalation needed? no.

Decision D8 (2026-07-01 post-hoc)
- Question: should `.md` extract-doc anchors be accepted in Check 1?
- Options considered:
1. Reject non-`.m` anchors for MATLAB-side checks.
2. Allow `.md` anchors with case-insensitive symbol substring checks and warning.
3. Treat `.md` anchors equivalently to MATLAB syntax anchors.
- Chosen option: 2.
- Rationale: derived extract docs can document symbol intent even when MATLAB syntax is absent; warning preserves second-class status.
- Tradeoffs accepted: substring checks are weaker than syntax-aware checks and can false-pass on incidental mentions.
- Beat-4 inversion: permissive matching could become the default authoring path and reduce anchor fidelity.
- Falsifier: if `.md` anchors dominate rows where canonical `.m` anchors exist, tighten policy or block by default.
- Operator escalation needed? no.

## Slot-3 Self-Audit Table
| L1b check | Implemented function | Governing decision(s) | Acceptance criterion | Self-audit |
| --- | --- | --- | --- | --- |
| Check 1 MATLAB anchors | `check_matlab_anchors_resolve` | D2, D4, D5 | Missing file/symbol yields FAIL; strict mode enforces line-window search | [x] |
| Check 2 OC anchors | `check_oc_anchors_resolve` | D2, D4, D5 | Missing file/symbol yields FAIL; Python anchors require AST line-window match | [x] |
| Check 3 consume/produce WIDs | `check_consume_produce_wids_in_schema_toml` | D3, D5 | Any missing WID from TOML state groups yields FAIL; non-substrate presence warns | [x] |
| Check 4 allocator WIDs | `check_allocator_requests_wids_in_schema_toml` | D3, D5 | Requests/bypasses missing from TOML state groups yield FAIL | [x] |
| Check 5 unit chain coherence | `check_unit_conversion_chain_coherent` | D1, D5 | Source/target endpoints and every adjacent step boundary must match | [x] |
| Check 6 ordering references | `check_ordering_constraints_reference_valid_processes` | D1, D5 | Every partner in hard/soft before/after must exist in discovered process roster | [x] |
| Check 7 deviation references | `check_deviations_reference_valid_anchors` | D1, D5 | File references in known deviations warn on missing; check remains PASS-with-warnings | [x] |

## 8) Scope Boundary
In scope:
1. Static wiring-row verification against source anchors, schema TOML WIDs, units chain, ordering references, and deviation file refs.
2. CLI outputs and exit-code semantics for gate integration.
3. Integration tests including real-row smoke and synthetic targeted failures.

Out of scope:
1. Remediation of existing failing rows.
2. Runtime/chassis/L2.4 conservation verification (was called "L1c" before the 2026-07-02 rename).
3. Re-authoring row schema or process TOML content.

Deferred follow-ups:
1. Optional strict-mode promotion policy after first-run triage.
2. Row-data cleanup for placeholder symbols and malformed conversion chains.

## 10) Risks and Residual Unknowns
R1. Non-UTF8 MATLAB sources produce read failures that dominate check-1 outcomes.
- Likelihood: high
- Impact: medium (faithful FAILs, but noisy diagnostics)
- Detection: check-1 details include codec decode errors
- Mitigation: treat as explicit conformance failures; optional future encoding fallback
- Owner: wiring DB maintainers

R2. Placeholder symbols (`NOT_IMPLEMENTED`, `n/a`) intentionally present in rows will fail strict conformance.
- Likelihood: high
- Impact: high (27/28 first-run FAIL outcome likely)
- Detection: check-2 detail strings include placeholder symbol misses
- Mitigation: remediate row intent vs implementation status explicitly, do not suppress in gate
- Owner: per-process row authors

R3. Lenient anchor mode may pass broad symbol existence while line claims drift.
- Likelihood: medium
- Impact: medium
- Detection: compare `--strict-anchors` run against default run
- Mitigation: retain strict mode as opt-in and evaluate promotion after cleanup
- Owner: gate maintainers
