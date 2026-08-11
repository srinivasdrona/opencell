# MacromolecularComplexation Active-Window Preregistration

## Scope

This document freezes the active-window extraction contract for
`MacromolecularComplexation` under L2.2 Design-A without editing the shared
catalog or index.

Catalog entry (authoritative spec):

```yaml
name: MacromolecularComplexation
bucket: ALGORITHMIC_SHALLOW
M_ticks: 100
N_seeds: 50
primary_channel: complexs
closed_form_dominant: candidate
karr_artifact: per_process_traces_v2
```

The August 11 checkpoint and `dec-004` establish why the canonical early
100-tick cohort is invalid for closure: its `tick_offset=0` windows never reach
the naturally reachable network-2 competitive branch, while a corrected real
scheduler lifecycle scan shows E1 first nonzero near tick 8264 and both
network-2 pentamers forming later in the same natural run.

## Frozen rule

For each seed `s in [0, 49]`:

1. Run the real Karr scheduler (`sim.evolveState()`) from cell birth with the
   real seeded `Simulation` until the first tick where either network-2 complex
   (`complexs` indices `22` or `23`, 0-based) has a positive delta.
2. Record that first trigger tick and the triggering complex identity or
   identities.
3. Re-run extraction from seed start with
   `extract_per_process_traces_v2(..., n_ticks=100, tick_offset=trigger_tick-1, 'fixed')`.
4. Accept the seed only if the resulting MAT file proves the window begins at
   the trigger tick:
   `metadata.tick_start == metadata.active_window_trigger_tick`, the first
   captured `complexs` delta is positive on the recorded network-2 indices, and
   no non-network-2 index appears in the trigger metadata.

No derived summary tick may be substituted for the real scheduler-discovered
first positive `complexs` delta.

## On-disk contract

Process-local cohort root:

`data/m1_sources/karr_native/macromol_active_window/`

Required layout:

- `per_process_traces_v2/MacromolecularComplexation_100ticks.mat`
- `per_process_traces_v2_s001/MacromolecularComplexation_100ticks.mat`
- ...
- `per_process_traces_v2_s049/MacromolecularComplexation_100ticks.mat`

Required metadata additions on every accepted seed:

- `active_window_rule = "first_network2_formation_tick"`
- `active_window_rule_version = 1`
- `active_window_trigger_tick`
- `active_window_trigger_complex_indices_0b`
- `active_window_search_max_ticks = 33000`
- `active_window_search_stop_reason = "first_network2_positive_delta"`
- `active_window_detection_mechanism`
- optional: `active_window_first_e1_nonzero_tick`

## Design-A consumption

The Design-A loader must consume this cohort only when the
Macromol-specific override is set:

`OPENCELL_L22_PROCESS_ORACLE_ROOT__MACROMOLECULARCOMPLEXATION`

Set it to:

`E:\opencell-worktrees\wave-l22-macromol\data\m1_sources\karr_native\macromol_active_window`

The override is authoritative, not fallback. If it is set, the loader must not
silently fall back to the canonical early-window root.

## Commands

Audit the cohort:

```powershell
bin\oc-py.cmd scripts/l22_extraction/macromol_active_window.py --out artifacts/l22_macromol_active_window_audit.json
```

Run the Macromol-only Design-A sweep against the active cohort:

```powershell
$env:OPENCELL_L22_PROCESS_ORACLE_ROOT__MACROMOLECULARCOMPLEXATION = "E:\opencell-worktrees\wave-l22-macromol\data\m1_sources\karr_native\macromol_active_window"
bin\oc-py.cmd scripts/l22_evidence/sweep.py run --processes MacromolecularComplexation --max-workers 1 --report-out artifacts/l22_macromol_sweep_report.json
bin\oc-py.cmd scripts/l22_evidence/generator.py bundle --source-root artifacts/l2_2_gates
```

## MATLAB slot rule

Long MATLAB work must first acquire the shared lock file by atomically
creating:

`E:\opencell-worktrees\.opencell-matlab-lock`

If the lock is unavailable, do not run the extraction. Finish code/tests and
record `READY_FOR_MATLAB` in `STATUS_L22_MACROMOL.md` instead. Always remove
the lock on exit.
