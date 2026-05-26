# STATUS_repl_regression.md

1. **Verdict**: COMPLETE (root cause found; strip commits are not the causative mechanism for replication non-initiation).

2. **Pre vs post replication state comparison**

| Artifact | Horizon | First non-idle replication tick | Max `replication_state_code` | Max `fork_position_norm` | Replication events (`idle` only?) |
|---|---:|---|---:|---:|---|
| `data/phase_e/v6_trajectory_32400s.pkl` | 32,400 s (325 snapshots) | none | 0.0 | 0.0 | n/a (pkl only) |
| `data/phase_e/v6_trajectory_32400s_post_strip.pkl` | 32,400 s (325 snapshots) | none | 0 | 0.0 | n/a (pkl only) |
| `artifacts/canary_post_strip_20260526_153956/replication_events.csv` | 32,400 ticks | none | n/a | n/a (`fork_max_abs_bp` max=0) | yes (`idle` on all 32,401 rows) |

Notes:
- The local "pre-strip" pkl in this worktree does **not** show replication progression either (no non-idle state, no fork motion).
- This behavior also matches the same pkl in `E:\opencell-worktrees\p2-karr-divergence-audit\data\phase_e\`.

3. **ATP pool comparison (early ticks)**

| Artifact | ATP first 5 | ATP ticks 26-30 | ATP last 5 | Min/Max ATP |
|---|---|---|---|---|
| `v6_trajectory_32400s.pkl` | `[1.0, -43750.0, -87500.0, -131250.0, -175000.0]` | `[-1066700.0, -1107950.0, -1149200.0, -1190450.0, -1231700.0]` | `[-10106500.0, -10132750.0, -10159000.0, -10185250.0, -10211500.0]` | `-10211500.0 / 1.0` |
| `v6_trajectory_32400s_post_strip.pkl` | `[36234.0, 36149.0, 36149.0, 36149.0, 36149.0]` | `[36149.0, 36149.0, 36149.0, 36149.0, 36149.0]` | `[36149.0, 36149.0, 36149.0, 36149.0, 36149.0]` | `36149.0 / 36234.0` |

Post-strip canary CSV corroboration:
- `key_substrates.csv` ATP remains essentially flat at `36149` after tick 1.

4. **Suspect commits (with diff hunks)**

- `8abaf63` (`karr_parity_mode: single global flag gates all 4 NGAM enforcement sites`)
  - Added parity gating to NGAM floor paths:
    - `RequestCalculatorMetabolism`: ATP floor clamp applied only when `not karr_parity_mode`.
    - `RequestCalculatorTRNA`: ATP request floor conditional on parity.
    - `KarrMetabolismProcess`: ATPM lb floor injection conditional on parity.
  - No replication-initiation logic changes in `karr_replication_initiation.py`/`karr_replication.py`.

- `6cfb1e3` (`strip-track-n: remove Sites 2/3/4 NGAM floor code`)
  - Removed Sites 2/3/4 floor code:
    - `karr_request_calculators.py`: TRNA ATP floor removed.
    - `karr_metabolism.py`: ATPM LP floor helpers and lb override removed.
    - `karr_allocation_step.py` and `karr_composite.py`: allocator NGAM plumbing removed.
  - **Site 1 floor remains** in `RequestCalculatorMetabolism` under `not karr_parity_mode`.
  - No direct edits to replication process files.

- `94a6b8c`, `d34887e`
  - Test-only changes in `tests/integration/test_chassis_v6_biology_firing.py`; no production replication/metabolism path edits.

- Earlier evidence of pre-existing replication-init issue:
  - `93b96d9` marks D1 replication gate check as xfail with reason:
    - `"Requires DnaA expression + activation; tracked separately"` (dated 2026-05-24, before strip commits).

5. **Root cause statement**

Smoking gun mechanism is **DnaA gate starvation, not ATP floor stripping**: `karr_replication_initiation` can only request ATP proportional to free DnaA-ADP (`requests[self.atp_wid] = max(0, self._free_dnaa_adp)`). In runtime probes, `MG_469_MONOMER` (DnaA) starts at `0.0` and stays `0.0`, so replication-init ATP request is `0.0` for all observed ticks, allocation is `0.0`, oriC occupancy (R1-R5) stays `0`, and `chromosome.replication_state` never leaves `idle`. This reproduces identically for both `karr_parity_mode=True` and `False`, which rules out the Site 2/3/4 strip as the initiating cause. As a control, manually seeding DnaA to 100 at t=0 causes replication initiation by tick ~74 in both parity modes, confirming the gate is otherwise functional once DnaA exists.

6. **Proposed fix**

Add a biologically valid DnaA availability path before initiation gating: either seed a non-zero initial DnaA pool (`MG_469_MONOMER`) consistent with Karr fixtures, or ensure transcription/translation produce DnaA quickly enough (integer-realizable counts) prior to initiation checks. Keep NGAM/parity work separate; the fix should target DnaA expression/initialization and add an integration assertion that `MG_469_MONOMER > 0` by an early tick budget.

7. **Confidence**: HIGH  
Why: direct runtime instrumentation shows zero DnaA -> zero replication-init ATP request/allocation in both parity modes; forcing DnaA non-zero immediately restores initiation behavior.

8. **Regression test added**: no  
Reason: the supplied "pre-strip" pkl in this workspace does not exhibit replication progression either, so a pkl-based assertion would encode an inconsistent baseline.

9. **Branch push status**

Pushed in this session with `git push -u origin fix/nan-replication-timing`.

10. **Anything weird**

- WSL `git` cannot operate on this Windows worktree metadata path (`not a git repository ... E:/opencell/.git/worktrees/...`), so git inspection was done via native Windows git.
- In `canary_post_strip_20260526_153956/process_traces/`, most process trace files are header-only; only a few (notably `karr_metabolism.csv`) contain rows.
- The local `v6_trajectory_32400s.pkl` timestamp/content does not match the described "May-23 pre-strip with replication progressing"; it already shows no replication progression.
