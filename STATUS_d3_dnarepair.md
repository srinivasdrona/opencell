# STATUS_d3_dnarepair

**Branch:** `exec/l22-d3_dnarepair`  
**Process:** DNARepair (`KarrDNARepairProcess`)  
**Author of Beat 1:** operator (manual, after 3 codex deaths on auto-Beat-1)  
**Author of Beats 2-5:** codex (delegated with stripped prompt)

---

## Provenance note

This branch's Beat 1 was authored by the operator after three consecutive codex deaths attempting auto-Beat-1 (5-way fanout, 3-way fanout, 1-way decomposed-phase-1; all died at 85-97k tokens with zero commits). Root cause identified as slot-3 over-historicization — the original PROMPT.md recited i2/i3/i4 fix histories and listed 7 probe templates, triggering codex into a study-everything-first mode that exceeded the budget cap before any commit landed. See `docs/prompts/COMPOSITION_MANDATE_v1.md` for the ceiling rule added from this incident (commit `470e661`).

Beat 1 was completed in three operator probes (`scripts/probe_d3_dnarepair_inspect.py`, `probe_d3_dnarepair_writesurface.py`, `probe_d3_wid_overlap.py`) in ~10 minutes. Findings are below.

---

## Beat 1 — SUT inspection + wiring design

### SUT facts (from `opencell/vivarium/karr_dna_repair.py:299-360`)

- **`_maybe_replay_from_hint`:** does NOT exist. (i2 clean.)
- **`trace_hint` branch:** does NOT exist. (i2 clean.)
- **`next_update` ALWAYS writes:** `requests.DNARepair.<wid in tracked_substrates>` (5 WIDs).
- **`next_update` CONDITIONALLY writes:** `substrates.<wid in tracked_substrates>` when `consumption > 0`; `+ AMET/AHCYS/H` on rare `rm_methylation` event; `chromosome.repair_events_cumulative` + counts when `consumed_total > 0`.
- **`next_update` NEVER writes:** `enzymes`, `boundEnzymes`, `protein.counts`, `complex.counts` (all read-only inputs).

### Channel inventory

| channel | written_by_SUT? | in_trace_npz? | n_wids | n_unique_wids | classification |
|---|---|---|---|---|---|
| `substrates` (full 277-vector) | partial (5 of 277 are SUT-tracked) | yes — `state_before__substrates` (100,1,277), `states_after__substrates` (100,1,277) | 277 | 277 | full-width misclassifies SUT silence as failure on 272 unwritten WIDs |
| `substrates` projected to 5 tracked WIDs (ATP, DATP, DCTP, DGTP, DTTP) | yes | yes (positions 5, 42, 54, 58, 83 in the 277-vector) | 5 | 5 | **PRIMARY candidate** |
| `enzymes` | no (SUT reads, never writes) | yes — (100,1,15), 1500 nonzero entries | 15 | 15 | `expected_sut_gap` (i4-class; do not gate) |
| `boundEnzymes` | no (SUT reads, never writes) | yes — (100,1,15), all-zero in trace | 15 | 15 | `expected_sut_gap` (i4-class; do not gate) |

### Replay trace character (probe: `scripts/probe_d3_dnarepair_inspect.py`)

- The DNARepair.npz replay export is a **pure no-op trace** on all three channels:
  - `substrates`: ticks_with_diff = 0/100. Per-tick before == after for every position.
  - `enzymes`: ticks_with_diff = 0/100. 1500 nonzero entries flat across 100 ticks.
  - `boundEnzymes`: ticks_with_diff = 0/100. All-zero throughout.
- For the 5 SUT-tracked WIDs specifically (probe: `scripts/probe_d3_wid_overlap.py`):
  - ATP (pos 5): flat at 36234, delta_nonzero_ticks = 0/100
  - DATP (pos 42): flat at 30264, delta_nonzero_ticks = 0/100
  - DCTP (pos 54): flat at 14039, delta_nonzero_ticks = 0/100
  - DGTP (pos 58): flat at 14040, delta_nonzero_ticks = 0/100
  - DTTP (pos 83): flat at 30265, delta_nonzero_ticks = 0/100

This matches the pattern observed for d1 ReplicationInitiation, d2 Replication, and d5 Cytokinesis: seed-0 replay traces for event-driven repair/initiation processes show no within-window activity.

### Honest-path probe (probe: `scripts/probe_d3_dnarepair_honest_path.py`)

With both zero-substrates state AND populated state (enzymes=5, substrates=100, allocated=100, planted damage event), SUT's `next_update` returned ONLY `{"requests": ...}` on all 5 tested ticks. No `substrates` write, no `chromosome` write. The allocator-mediated substrate consumption path requires conditions (damage_sites format match + non-zero allocated + repair throughput > 0) that the simple planted damage event did not satisfy.

### Duplicate-WID check (i3)

- substrate WIDs: 277 total, 277 unique (no duplicates)
- enzyme WIDs: 15 total, 15 unique (no duplicates)
- **No positional shadow store needed.** Dict overlay is sufficient.

### Design decisions

- **PRIMARY channel:** `substrates` projected to the 5 SUT-tracked WIDs (ATP, DATP, DCTP, DGTP, DTTP), positions [5, 42, 54, 58, 83] of the npz 277-vector. Same projection pattern as d2 Replication (which also projects to 5 substrate WIDs).
- **SECONDARY / expected_sut_gap:** `enzymes` and `boundEnzymes` are read-only inputs in `next_update`; they appear in the trace but SUT never writes them. Do NOT wire as gateable; document as `expected_sut_gap`.
- **Bucket:** `ALGORITHMIC_DEEP`. The SUT uses two RNG instances (`_rng` for repair sampling, `_rm_rng` for methylation), iterates over per-tick damage sites, computes pathway-weighted rates from enzyme counts × reaction bounds, and depends on allocator-mediated substrate availability. State depth is real (chromosome damage queue + cumulative repair events).
- **Positional shadow store:** NOT needed (no duplicate WIDs on any wired channel).
- **After-hint overlay on PRIMARY:** NOT applied. Standard i2-laundering avoidance, even though SUT has no `_maybe_replay_from_hint` to bypass — the rule is uniformly applied.
- **Oracle source:** `data/karr_fixtures/per_process_replay/DNARepair.npz` (canonical). Manifest's `source_mat` points to `DNARepair_100ticks.mat` which is present. Schema matches the d2 Replication pattern (state_before__/states_after__ with mixed singular/plural prefix bug, which is widespread in the export pipeline).

### Beat 2 handoff

- **Primary channel name:** `substrates`
- **Primary channel WID projection:** positions [5, 42, 54, 58, 83] → ATP/DATP/DCTP/DGTP/DTTP
- **Bucket:** `ALGORITHMIC_DEEP`
- **Positional shadow store needed:** NO
- **`_maybe_replay_from_hint` exists:** NO (no after-hint overlay code branch needed; defensive guard not required)
- **Reference implementation to mirror:** `_run_replication_tick` in `tests/vivarium/_l2_2_design_a_runner_helpers.py` (d2's tick dispatcher) — DNARepair is structurally the closest analog (event-driven, substrate-consuming, no-op replay window, same primary-projection pattern).
- **Expected smoke gate verdict:** `PASS_PRIMARY_WITH_DOCUMENTED_GAPS` with primary substrates = `SEED_NOISE@0.000000` and `PRIMARY_CHANNEL_ORACLE_DETERMINISM_LEGITIMATE` warning (same as d2 Replication, d4 Macromol — the trace is a legitimate no-op, the helper reproduces it without laundering).

## Beat 2 — tick dispatcher

- Diff stat: `tests/vivarium/_l2_2_design_a_runner_helpers.py | 126 insertions(+)`
- Added `_DNAREPAIR_ORACLE_PATH`, a dynamic 5-WID substrate projection loader for `ATP/DATP/DCTP/DGTP/DTTP`, `_dnarepair_process({"rng_seed": seed})`, and `_run_dnarepair_tick`.
- Dispatcher mirrors Replication's structure: it overlays the clean `oracle_before_*` snapshot for substrates/enzymes/boundEnzymes/protein/complex, keeps `trace_hint = {}` defensively, and never applies `oracle_after_*` onto the primary substrates channel.

## Beat 3 — runner wiring + anticheat tests

- Wired `DNARepair` through `tests/vivarium/l2_2_design_a_runner.py`: supported-process tables, primary/output channel metadata, sample-process dispatch, 5-WID observable projection, and the DNARepair-specific sample-state handoff for protein/complex inputs.
- Added `tests/vivarium/test_l2_2_design_a_runner_anticheat_dnarepair.py` with:
  - `test_dnarepair_primary_fixture_is_legitimate_noop`
  - `test_dnarepair_constant_zero_primary_channel_fails`
  - `test_dnarepair_primary_exact_match_is_legitimate_noop`
- Omitted the Replication trace-hint bypass test on purpose; DNARepair has no `_maybe_replay_from_hint` / `trace_hint` replay branch.
- Verification: `bin/oc-pytest.cmd tests/vivarium/test_l2_2_design_a_runner_anticheat*.py -q` -> `26 passed in 58.57s`
