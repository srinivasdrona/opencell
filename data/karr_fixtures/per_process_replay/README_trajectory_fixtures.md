# Trajectory-Derived Replay Fixtures (`*_from_trajectory.npz`)

## What these fixtures are

These fixtures are built from:

- `data/m1_sources/karr_native/cell_cycle_trajectory.mat` (or fallback `E:/opencell/...`)
- Per-process mapping metadata in `data/karr_fixtures/per_process/<Process>_flat.mat`

for the five MATLAB-truncated processes:

- `Transcription`
- `Translation`
- `RNADecay`
- `Replication`
- `ReplicationInitiation`

Each output file is:

- `data/karr_fixtures/per_process_replay/<Process>_from_trajectory.npz`
- with keys `state_before__<prop>` and `states_after__<prop>`
- shaped `(n_pairs, 1, N)` where `n_pairs = n_snapshots - 1`.

## Critical validation framing

These fixtures are **not** the same validation target as the MATLAB `_100ticks.mat` isolated traces.

- MATLAB `_100ticks.mat` traces validate:
  `Python.process.evolveState(isolated state)` vs MATLAB isolated process behavior.
- Trajectory-derived fixtures validate:
  whether a process replay is consistent with observed whole-sim deltas between `(state_t, state_t+1)`.

So trajectory fixtures are:

- integration-coupled (all 28 processes + allocator effects are mixed into deltas),
- biologically richer context,
- but harder and less isolating as a process oracle.

They **complement** isolated fixtures; they do not replace them.

## Tolerance regime guidance

Use these fixtures with explicit, documented tolerances and expectations:

- Prefer consistency checks on direction/magnitude bands over bit-exact equality.
- Require non-trivial deltas (especially substrates) to avoid degenerate no-op channels.
- Use per-channel tolerances that acknowledge coupling noise from other processes.

When MATLAB access is restored, regenerate isolated traces via:

- `scripts/matlab/extract_per_process_traces_fix.m`

then cross-compare isolated and trajectory-derived evidence channels.

## Known limitations

The trajectory export only contains selected numeric state properties (`numel(v) < 10000` and numeric-typed). In this dataset:

- Metabolite and ProteinComplex count channels are available and used dynamically.
- RNA/ProteinMonomer count channels required for some enzyme vectors are absent.

For missing channels, extractor falls back to flat-fixture baseline values and documents this in script output notes.

## Build command

```powershell
py -3.12 scripts/build_replay_fixtures_from_trajectory.py --all-truncated
```

or per process:

```powershell
py -3.12 scripts/build_replay_fixtures_from_trajectory.py --process Transcription
```
