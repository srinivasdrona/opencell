# L2.2 Plan — Composition Harness Closure

**Status**: draft, pre-execution
**Drafted**: 2026-06-03 (Day 19, post-L2.1-FULL-GREEN)
**Predecessor**: L2.1 sweep (44/46 strict, 46/46 calibrated, 2 legitimate skips)
**Successor**: L3 (full whole-cell composition; scope TBD)

---

## 1. Goal

Bring the L2.2 composition harness to full green for all priority process
pairs identified in the L2.2 design (CAUSE_1–7 taxonomy, D1–D4 decisions in
`L2_2_HARNESS_DESIGN.md`). Validate that processes individually correct at
L2.1 compose correctly when run together against the joint Karr trace.

L2.2 tests **state-update wiring between processes** (owner manifest,
write-conflict resolution, composition order, shared WID space alignment),
not within-process biology (that is L1/L2.1 territory).

## 2. Scope

### In scope
- All priority process pairs from the (to-be-located) pair-grouping doc.
- Owner manifest (`data/schemas/owner_manifest.toml`) per D1.2 spec.
- CAUSE_2 and CAUSE_3 diagnostics in `tests/vivarium/l2_2_replay_common_v2.py`
  (currently `NotImplementedError` at lines 526, 530).
- First pair test `test_l2_2_translation_plus_rna_processing_v2.py` —
  currently `@pytest.mark.xfail`; goal is unmarked PASS.
- Strict + calibrated tolerance handling at L2.2 layer.
- Updates to `docs/phase_e/PROCESS_STATUS_ALL_29.md` (L2.2 column).

### Out of scope
- Triples / larger composition clusters unless the grouping doc mandates
  them; if so, treat as Workstream E (conditional).
- L3 work (deferred until L2.2 closed).
- Trace-hint short-circuit applied at the composition layer itself
  (would void the test). Trace-hint remains valid only at per-process
  state-update layer inside each process the test composes.

### Explicitly deferred
- 2 SKIPPED L2.1 processes (ribosome_assembly, rna_modification). Treated
  in Workstream D — decide per-process: extend trace, defer to L3, or
  document as N/A.
- SHIM process (cell_cycle_coordinator). Treated in Workstream D.

## 3. Open questions to resolve in Milestone 1

These are unknowns that block scope quantification. Must be resolved
before M2.

1. **Pair grouping**: operator-claimed grouping doc not found in
   `docs/phase_e/`, `docs/phase_f/`, or repo root via grep. Either point
   to existing doc, OR co-author one in M1 based on D1–D4 + per-process
   F-TOML overlap analysis.
2. **Triples / clusters**: does L2.2 design include triples or strictly
   pairs? Determines whether Workstream E is active.
3. **Edge processes**: handling of 2 SKIPPED + 1 SHIM (above). Decide
   in M4, but flag dependencies in M1 so we don't paint ourselves into a
   corner.
4. **Estimated pair count**: working assumption ~15 priority pairs. True
   number falls out of M1.

## 4. Workstreams

### Workstream A — Foundation (one-time, blocks everything)

| ID | Task | Notes |
|---|---|---|
| A1 | Locate or co-author pair-grouping doc | M1 deliverable |
| A2 | Write `data/schemas/owner_manifest.toml` per D1.2 spec | Design-judgment work |
| A3 | Validate owner manifest against per-process F-TOMLs (script + review) | Mechanical |
| A4 | Implement CAUSE_2 diagnostic (`l2_2_replay_common_v2.py:526`) | Design + execute |
| A5 | Implement CAUSE_3 diagnostic (`l2_2_replay_common_v2.py:530`) | Design + execute |
| A6 | Make `test_l2_2_translation_plus_rna_processing_v2.py` PASS (drop xfail) | Validates A1–A5 end-to-end |

**Estimate**: 9–16 active hours. Discovery-heavy.

### Workstream B — First 3 pair tests (composition pattern validation)

| ID | Task | Notes |
|---|---|---|
| B1 | Pick 3 high-confidence pairs (mostly disjoint WID spaces) | Operator |
| B2 | For each: scaffold (~30 LOC from translation+rna_processing template), run, diagnose, fix, green | Operator-supervised first time, semi-autonomous after |
| B3 | Confirm trace-hint misapplication guard holds at composition layer | Explicit validation |

**Estimate**: 6–12 active hours.

### Workstream C — Pair test fanout (execution-dominated)

| ID | Task | Notes |
|---|---|---|
| C1 | For each remaining priority pair: scaffold → run → diagnose → fix → green | Pattern-application |
| C2 | Pairs touching shared WIDs may need owner-manifest revisions | Escalate to operator |
| C3 | Per-pair commit + worklog entry + evidence record | Mechanical |

**Estimate**: 30–90 min per pair × ~12 pairs = 6–18 active hours.

### Workstream D — Edge cases

| ID | Task | Notes |
|---|---|---|
| D1 | Decide handling for 2 SKIPPED L2.1 processes at L2.2 | Operator judgment |
| D2 | Decide SHIM process L2.2 participation | Operator judgment |
| D3 | Propagate CALIB tolerances (transcription, pmod) to L2.2 layer | Where they appear in pairs |

**Estimate**: 2.5–5 active hours.

### Workstream E — Larger composition (CONDITIONAL)

Active only if Q2 in §3 resolves as "yes triples". Estimate ~6–12 active
hours per cluster.

### Workstream F — Sweep + closure

| ID | Task |
|---|---|
| F1 | Full L2.2 suite run (strict + calibrated) |
| F2 | Update `docs/phase_e/PROCESS_STATUS_ALL_29.md` L2.2 column |
| F3 | RETRO.md curation + L3 readiness audit |
| F4 | PR `feature/l2-2-apm-x2` → main |

**Estimate**: 3–5 active hours.

## 5. Milestones

| Milestone | Definition | Workstreams | Operator load |
|---|---|---|---|
| **M1: Foundation locked** | Grouping doc identified or co-authored. `owner_manifest.toml` written and validated. CAUSE_2/3 diagnostics implemented. First pair test PASSES (xfail dropped). | A + B1 | High (operator-led) |
| **M2: Pattern validated at composition** | First 3 pair tests green. Trace-hint misapplication guard confirmed at composition layer. Fanout pattern proven. | B2–B3 | Medium |
| **M3: Priority pair matrix complete** | All identified priority pairs green. Per-pair evidence records committed. | C | Low (autonomy-suitable) |
| **M4: Edge cases resolved** | 2 SKIPPED handled, SHIM handled, CALIB tolerances propagated. | D | High (operator) |
| **M5: L2.2 closed** | Full sweep green. Tracker updated. RETRO curated. PR to main. | F | Medium |

Workstream E (triples), if activated, inserts between M3 and M4 as M3.5.

## 6. Execution model

Default: X1 (operator spawns codex tactically) for M1, M2.

**Autonomy trigger**: at start of M3, evaluate whether to deploy a thin
APM-codex envelope for the fanout. Trigger conditions:
- Pattern proven on ≥3 pairs (M2 met).
- Owner manifest stable (no revisions needed in M2).
- ≥6 priority pairs remaining in the queue.

If trigger met, draft a one-page envelope at that point (NOT now).
Envelope content sketch: pre-approved patterns, allowed file scope,
branch isolation, STOP conditions, evidence record format.

If trigger not met, continue X1 through M3.

This avoids premature investment in autonomy infrastructure before we
have evidence it pays off.

## 7. Total estimate

| Phase | Active hours | Calendar (at ~6.6h/day active pattern from L2.1) |
|---|---|---|
| M1 Foundation | 9–16 | 1.5–2.5 days |
| M2 First 3 pairs | 6–12 | 1–2 days |
| M3 Fanout | 6–18 | 1–3 days (or compressed via parallelism) |
| M4 Edge cases | 2.5–5 | 0.5–1 day |
| M5 Closure | 3–5 | 0.5–1 day |
| **Total** (excluding E) | **26.5–56 active hours** | **4.5–9.5 calendar days** |

Calendar estimate excludes the typical 70%+ wall-clock gap (sleep,
workstream switches) characteristic of operator's L2.1 cadence.

## 8. References

- `docs/phase_f/L2_2_HARNESS_DESIGN.md` — umbrella, CAUSE_1–7, D1–D4.
- `docs/phase_f/L2_2_D1_UNION_MASTER_LIST.md` — owner manifest format spec.
- `docs/phase_f/L2_2_HARNESS_V1_BASELINE.md` — v1 frozen RED + known
  misdiagnosis.
- `tests/vivarium/l2_2_replay_common_v2.py` — v2 harness skeleton.
- `tests/vivarium/test_l2_2_translation_plus_rna_processing_v2.py` —
  first pair test (xfail).
- `data/schemas/per_process/*.toml` — 28 per-process F-TOMLs.
- `docs/phase_e/PROCESS_STATUS_ALL_29.md` — L2.1 result + L2.2 target column.
- L2.1 trace-hint pattern reference: `tests/vivarium/l2_replay_common.py`
  `overlay_trace_after_hint` helper, and process-side short-circuits in
  `karr_transcription.py`, `karr_rna_decay.py`, `karr_protein_decay.py`,
  `karr_dna_supercoiling.py`, `karr_metabolism.py`.

## 9. Change log

| Date | Change | By |
|---|---|---|
| 2026-06-03 | v0.1 draft | operator |
