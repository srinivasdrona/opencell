# Phase E Master Design (2026-05-23)

Defines the four closing milestones — `pe-1` (already shipped scaffold), `pe-2`
(phenotype scorecard), `pe-3` (discrepancy analysis), `pe-final` (v1.0 release
gate). Builds on the pe-1 trajectory scaffold + chassis_v6 (landing today).

Scope: this is the orchestrator-owned spec. Each milestone gets one Codex
implementation turn; this doc is what those turns read first.

## E.1 — Karr trajectory match (chassis_v6 vs cell_cycle_trajectory.mat)

**Status**: scaffold shipped (pe-1). Real run blocks on pd-final-integration (chassis_v6).

### Goal
Run chassis_v6 for 32400 ticks (`dt=1s`, one full Karr cell cycle), extract
the 9 observables already defined in pe-1's scaffold contract, compare against
Karr's reference trajectory, and emit a bucket-classified PASS/FAIL report.

### Inputs
- `opencell.vivarium.karr_composite.build_karr_chassis_v6()` (from pd-final-integration)
- `opencell.validation.karr_trajectory.load_karr_trajectory()` (shipped in pe-1)
- `opencell.validation.trajectory_compare.compare_trajectories(...)` (shipped in pe-1)
- 9 observables already mapped (see `docs/design/pe-1-trajectory-scaffold.md` §State-port mapping)

### Acceptance criteria

Per-observable bucket classification using the existing v1-trajectory-buckets
decision (see `D:\OneDrive - Microsoft\.pm-os\DECISIONS.md`):

| Bucket | Acceptance for pe-1-match |
|---|---|
| `opencell-tooling` | strict: rel_err ≤ 0.1% (wiring/invariants only) |
| `validation-and-organism-scaling` | medium: rel_err ≤ 30% |
| `karr-known-incomplete` | xfail-allowed: bounded drift 0.4×–2.5× |
| `biology-beyond-Karr` | qualitative only (no numeric gate in v1) |

The 9 scaffold observables map to buckets as:

| Observable | Bucket | Notes |
|---|---|---|
| `cell_dry_mass_g` | validation-and-organism-scaling | mass-balance closes ⇒ should PASS |
| `replication_state_code` | opencell-tooling | discrete enum, strict |
| `fork_position_norm` | karr-known-incomplete | bulk counter, light-scope |
| `mrna_total_count_estimate` | validation-and-organism-scaling | proxy comparison |
| `protein_total_count_estimate` | validation-and-organism-scaling | proxy comparison |
| `atp_pool` | opencell-tooling | direct comparison |
| `gtp_pool` | opencell-tooling | direct comparison |
| `dntp_pool_total` | opencell-tooling | direct comparison |
| `division_event_timestamp_s` | karr-known-incomplete | bulk-counter cytokinesis, light-scope |

**Acceptance**: 100% of `opencell-tooling` bucket PASS, ≥50% of
`validation-and-organism-scaling` PASS. `karr-known-incomplete` may xfail but
must be measured & reported. Below this gates the v1.0 release.

### Output artifact
`docs/phase_e/E1_match_report.md` — markdown report with per-observable rows
(observable, bucket, opencell_value, karr_value, rel_err, status, disposition).
Plus a one-line summary header for blog/release-notes consumption.

### Test plan
- `tests/validation/test_e1_full_cycle_match.py`:
  - `test_e1_match_runs` — chassis_v6 32400 ticks completes, observables extracted, comparator returns dict. Mark `pytest.mark.slow`.
  - `test_e1_tooling_bucket_strict` — all opencell-tooling observables PASS strict.
  - `test_e1_validation_bucket_medium` — ≥50% PASS at medium tolerance.
  - `test_e1_report_emitted` — `docs/phase_e/E1_match_report.md` exists and has all 9 rows.

### Codex turn brief (when ready to fire)
- Branch: `agent/pe-1-real-match`
- Prereq: chassis_v6 on main (from pd-final-integration)
- Wall-time budget: 20-30 min (mostly the 32400-tick simulation, ≈18 min @ 30 ticks/s)
- Deferred-to-v2: real comparison against full Karr 28-phenotype panel (that's E.2)

---

## E.2 — 28-phenotype scorecard (KP01–KP28)

**Status**: design only (this doc). Implementation blocks on E.1 PASS.

### Goal
Extract Karr's 28 published quantitative phenotypes (`KP01..KP28`) from a
single full-cycle chassis_v6 run, compare against Karr 2012 paper +
supplementary table S1, emit scorecard.

### KP registry
Adopt the table from `docs/design/pd_final_chassis_v6.md` lines 144-173 as
canonical. Codify in code as
`opencell/validation/phenotype_registry.py`:

```python
PHENOTYPES: dict[str, PhenotypeDef] = {
    "KP01": PhenotypeDef(
        label="Growth rate",
        bucket="opencell-tooling",
        extractor=lambda state: state["metabolic_reaction"]["growth_per_s"],
        karr_value=0.060,  # placeholder; populate from paper
        rel_tol=0.05,
    ),
    # ... KP02..KP28
}
```

### Acceptance criteria
- ≥10 of 28 PASS within bucket tolerance (per `pe-2-phenotype-match` todo from yesterday)
- Every KP either PASS, FAIL with disposition (xfail/qual/blocked), or BLOCKED-on-missing-extractor (a known v1 limitation; document, don't fail)

### Output artifact
`docs/phase_e/E2_scorecard.md` — scorecard table + summary header.

### Test plan
- `tests/validation/test_e2_phenotype_scorecard.py`:
  - `test_e2_all_kps_registered` — all 28 IDs present in registry
  - `test_e2_extractors_run` — each extractor returns a numeric value or NaN (no exceptions) on a chassis_v6 fixture
  - `test_e2_scorecard_pass_count` — ≥10/28 PASS

### Codex turn brief (when ready)
- Branch: `agent/pe-2-phenotype-scorecard`
- Prereq: E.1 PASS (so we know chassis_v6 runs to completion)
- Wall-time: 30-45 min (registry implementation + per-KP extractor + Karr-value sourcing from paper)
- Out-of-scope: chassis biology changes to chase failing KPs (that's E.3 dispositioning + v1.1)

---

## E.3 — Discrepancy analysis & disposition

**Status**: design only. Implementation blocks on E.2.

### Goal
For every E.1 observable or E.2 phenotype that FAILS, document:
1. **What diverged**: actual numeric gap (opencell value vs Karr value, ratio, rel_err)
2. **Hypothesis why**: one of:
   - Karr-light scope (defer to v1.1)
   - missing biology (e.g., process not modeled — defer to v1.1+)
   - parameter drift (calibration task for v1.1)
   - allocation timing artifact (chassis wiring bug — fix now)
   - extraction bug (extractor wrong — fix now)
   - genuinely biology-beyond-Karr (qualitative, no numeric gate)
3. **Disposition for v1.0 release**:
   - ACCEPT (xfail/qual)
   - FIX-NOW (small surgical fix this turn)
   - DEFER-TO-V1.1 (logged as todo, won't gate release)
   - BLOCK-RELEASE (rare, but possible)

### Acceptance criteria
- 100% of E.1/E.2 fails have an explicit disposition
- 0 BLOCK-RELEASE entries (else loop back to fix before E-final)
- All DEFER-TO-V1.1 entries logged as todos in `opencell_tasks.db` with v1.1 milestone tag

### Output artifact
`docs/phase_e/E3_discrepancy_log.md` — one row per discrepancy with
disposition, plus a roll-up summary by hypothesis category (useful for blog).

### Codex turn brief (when ready)
- Branch: `agent/pe-3-discrepancy-analysis`
- Prereq: E.1 + E.2 reports both committed
- Mostly classification/writing work; ~20-30 min wall-time
- ALSO updates `opencell_tasks.db` with v1.1 todos

---

## E-final — v1.0 release gate

**Status**: design only. The terminal milestone of M4.

### Hard gates (all must pass)
1. **Code completeness**: 28/28 Karr processes present, no `NotImplementedError` in production paths.
2. **Test suite**: ≥900 tests, 0 failures, 0 unexplained xfails (each xfail has a documented v1.1 todo).
3. **Full-cycle test**: `test_full_cell_cycle_completes` (32400 ticks) PASS or `xfail("perf-budget v2")` with measured wall-time.
4. **E.1**: 100% opencell-tooling bucket PASS, ≥50% validation-and-organism-scaling PASS.
5. **E.2**: ≥10/28 phenotypes PASS within bucket tolerance.
6. **E.3**: All discrepancies dispositioned; 0 BLOCK-RELEASE entries.
7. **CI**: GitHub Actions strict-lint + full-suite green on main.

### Soft gates (recommended but not blocking)
- `CHANGELOG.md` + `RELEASE_NOTES_v1.0.md` drafted
- README updated with installation + quickstart for v1.0 API
- Blog post / Day-N narrative published
- L4 methods paper draft (separate todo `l4-methods-paper`; deferred to post-v1.0)
- PyPI `llm-interaction-log` extraction (separate todo; deferred to post-v1.0)

### Release artifacts
- Git tag `v1.0.0`
- GitHub Release page with notes
- Optional: PyPI publish of `opencell` itself (defer to v1.1 if extraction work is large)

### Codex turn brief (when ready)
- Branch: `agent/pe-final-v1-release`
- Prereq: E.1 + E.2 + E.3 all committed and PASS
- Tasks: assemble CHANGELOG from `git log v0.x..HEAD`, draft RELEASE_NOTES from
  E.1+E.2+E.3 summaries, run `gh release create`, update README, push v1.0.0 tag
- Wall-time: 30-60 min

---

## Critical-path ordering after today's integration sessions land

```
pd-final-integration completes
    ↓
audit-cross-process-keys merge (may patch process modules)
    ↓
fix-set-accumulate-warnings merge (cleans warnings)
    ↓
[optional pause: run full suite, push to main, confirm baseline]
    ↓
pe-1-real-match Codex turn (E.1)
    ↓
pe-2-phenotype-scorecard Codex turn (E.2)
    ↓
pe-3-discrepancy-analysis Codex turn (E.3)
    ↓
pe-final-v1-release Codex turn (E-final)
    ↓
v1.0.0 tagged, release page published, blog post
```

Estimated total wall-time after chassis_v6 lands: **4-6 hours** for all four
Phase E turns serial. They can NOT meaningfully parallelize (each depends on
prior turn's output: E.2 needs E.1's run-completion confirmation; E.3 reads
E.1+E.2; E-final reads everything).

## Out-of-scope decisions for today (deferred to v1.1+)

- Tighten Karr-light scopes for any process where E.3 traces drift to "light-scope" hypothesis
- Per-nucleotide replication mechanics (SSB / Okazaki / ligase)
- Per-loop chromosome condensation topology
- Full DNA-binding occupancy per-region accounting (KP15 detail)
- `host_adhesion_gates_division` feature flag activation (currently off-by-default per v6 design)
- Performance optimization for 32400-tick run (<10 min target)
- PyPI extraction of `llm-interaction-log` package
- L4 methods paper draft

These all get logged as v1.1 todos in `opencell_tasks.db` during the E.3 turn.
