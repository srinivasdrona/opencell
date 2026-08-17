# MacromolecularComplexation Active-Window Preregistration

## Scope

This document freezes the process-local active-window contract for
`MacromolecularComplexation` under L2.2 Design-A without editing the shared
catalog, shared evidence index, or shared runner helpers.

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

The canonical early 100-tick cohort is not admissible for this closeout
because it never reaches the naturally reachable network-2 branch. This
prereg instead binds a process-local active-window cohort under:

`data/m1_sources/karr_native/macromol_active_window/`

## Frozen rule

For each seed `s in [0, 49]`:

1. Start from cell birth with the real seeded `Simulation`.
2. Advance one tick at a time with the tapped allocator-correct scheduler
   semantics used by `extract_per_process_traces_v2`'s per-tick capture path.
3. Detect the first tick where either network-2 complex (`complexs` indices
   `22` or `23`, 0-based) has a positive delta on that tick's own
   `states_after.complexs - states_before.complexs`.
4. Treat that same tick as tick 1 of the active window, and continue
   capturing the next 99 ticks from that same trajectory.

No second replay pass is allowed. The trigger source and the captured first
tick must come from one identical trajectory.

## Required metadata

Every accepted seed file must contain the ordinary fixed-window metadata plus
the following process-local fields:

- `active_window_rule = "first_network2_formation_tick"`
- `active_window_rule_version = 2`
- `active_window_trigger_tick`
- `active_window_trigger_complex_indices_0b`
- `active_window_search_max_ticks = 33000`
- `active_window_search_stop_reason = "first_network2_positive_delta"`
- `active_window_detection_mechanism`
- `active_window_capture_mode = "same_pass_tapped_scheduler_trigger_and_capture"`
- optional: `active_window_first_e1_nonzero_tick`

Every accepted seed must also bind:

- genuine-provider metadata (`mnrnd_provider_*`,
  `statistics_rng_provider_identity_json`)
- extractor driver path/hash
- fixture path/hash
- vendored MATLAB source path/hash

## Acceptance checks

A seed is accepted only if all of the following are true:

- `metadata.tick_start == metadata.active_window_trigger_tick`
- `metadata.tick_offset == metadata.active_window_trigger_tick - 1`
- `metadata.tick_end - metadata.tick_start + 1 == 100`
- the first captured `complexs` delta is positive on the recorded
  network-2 index or indices
- no non-network-2 index appears in
  `active_window_trigger_complex_indices_0b`
- the seed validates under
  `scripts/l22_extraction/macromol_active_window.py`

## On-disk layout

Required cohort layout:

- `per_process_traces_v2/MacromolecularComplexation_100ticks.mat`
- `per_process_traces_v2_s001/MacromolecularComplexation_100ticks.mat`
- ...
- `per_process_traces_v2_s049/MacromolecularComplexation_100ticks.mat`

All paths are rooted at:

`data/m1_sources/karr_native/macromol_active_window/`

## Design-A consumption

The shared runner helpers are intentionally not edited for this closeout.
Instead, `scripts/l22_evidence/macromol_active_windows.py` temporarily routes
only `MacromolecularComplexation`'s oracle lookup to the active-window root in
process, runs the ordinary shared Design-A runner, and emits a separate
portable process-local artifact.

This process-local artifact is not consumed by the shared evidence index or
generator without an explicit promotion step.

## Commands

Audit the cohort:

```powershell
bin\oc-py.cmd scripts/l22_extraction/macromol_active_window.py --out artifacts/l22_macromol_active_window_audit.json
```

Produce the process-local ordinary Design-A artifact:

```powershell
bin\oc-py.cmd scripts/l22_evidence/macromol_active_windows.py --out docs/phase_f/l2_2_design_a/active_windows/MacromolecularComplexation_genuine_provider_design_a.json
```
