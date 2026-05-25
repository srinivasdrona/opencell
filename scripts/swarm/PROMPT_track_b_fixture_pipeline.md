# Track-B: Replay Fixture Pipeline (Option B)

## Context

You are working in worktree `E:\opencell-worktrees\track-b-fixtures` on branch
`track-b/replay-fixtures`. Main HEAD is `642d450` plus whatever Track-A merges
(A1..A5) land before this. Your work is INDEPENDENT of Track-A — you touch a new
fixture directory and a small loader extension. Do NOT touch any file in
`opencell/vivarium/karr_*.py`, `opencell/processes/`, or the existing
`data/karr_fixtures/per_process/` directory.

The full diagnosis lives in
`opencell/validation/swarm/fixture_investigation/fixture_pipeline_recommendation.md`
— read it first. The short version:

- Existing replay harness (`opencell/validation/replay.py:120-220`) expects
  tick-indexed channels (`state_before*`, `state_after*`) and a discoverable
  `n_ticks` (manifest key or array shape). It currently can't find them, so
  `tests/integration/test_replay_smoke.py` xfails.
- The current `data/karr_fixtures/per_process/<Process>_flat.mat` files are
  flattened MCOS snapshots — single-tick, no input/output channels.
- BUT: 28 per-tick MATLAB trace `.mat` files (one per process, 100 ticks each)
  ALREADY EXIST on disk at
  `data/m1_sources/karr_native/per_process_traces/<Process>_100ticks.mat`.
  Each contains `states_before` (struct of per-property cell arrays length 100),
  `states_after` (same), and `metadata` (n_ticks, rng_seed, process_name,
  snapshot_properties).

So the only missing work is a **Python converter** that reads those `.mat`
trace files and writes replay-ready companion fixtures the existing harness
can consume.

## Goal

Land ONE branch (`track-b/replay-fixtures`) containing:

1. A Python converter script that produces replay-ready fixtures from the
   existing MATLAB traces.
2. A small extension to the replay loader so it can find and load those
   fixtures.
3. Integration tests for 2-3 representative processes that go from `xfail` to
   `pass`.

Target diff size: ~200 LOC (excluding the generated `.npz`/`.json` artifacts,
which can be checked in or git-ignored — your call, document the choice).

## Authoritative references (read these first)

- `opencell/validation/swarm/fixture_investigation/fixture_pipeline_recommendation.md`
  (the recommendation document, ~50 lines)
- `opencell/validation/replay.py:1-260` — the existing loader contract. Pay
  attention to `_infer_n_ticks` (manifest.n_ticks is honored),
  `_INPUT_HINTS` / `_OUTPUT_HINTS` (`state_before`, `states_before`,
  `_before` are inputs; `state_after`, `states_after`, `_after`, `delta`
  are outputs), and `_ensure_tick_major` (axis-0 should be ticks).
- `scripts/matlab/extract_per_process_traces.m` — the producer. The `.mat`
  layout is `states_before.(prop){tick}` and `states_after.(prop){tick}`
  (cell arrays of length 100 holding numeric arrays).
- `tests/integration/test_replay_smoke.py` — the consumer test. Currently
  xfails for Cytokinesis. Your work should let an equivalent test PASS
  for at least one process.

## Concrete plan (4 commits)

### Commit 1 — converter script

Create `scripts/build_replay_fixtures.py` (~100 LOC). It should:

- Read every `*_100ticks.mat` under
  `data/m1_sources/karr_native/per_process_traces/` (use `scipy.io.loadmat`
  with `simplify_cells=True` and `squeeze_me=True`; MAT v7.3 files need
  `h5py` fallback — check both paths).
- For each process, build two flat dicts of arrays:
  - `state_before__<prop>` → ndarray of shape `(n_ticks, *prop_shape)`
  - `states_after__<prop>` → ndarray of shape `(n_ticks, *prop_shape)`
  Use a double-underscore separator so the existing `_INPUT_HINTS` /
  `_OUTPUT_HINTS` substring match (`state_before`, `states_after`) fires.
- Stack the per-tick cell-array entries into a single tick-major ndarray.
  Properties whose shape varies tick-to-tick (rare but possible) should be
  logged and skipped with a clear warning, NOT crashed on.
- Emit to `data/karr_fixtures/per_process_replay/<Process>.npz` (arrays)
  and `<Process>.json` (manifest), where the JSON contains:
  ```json
  {
    "manifest": {
      "n_ticks": 100,
      "process_name": "<Process>",
      "rng_seed": 0,
      "snapshot_properties": [...],
      "source_mat": "data/m1_sources/karr_native/per_process_traces/<Process>_100ticks.mat",
      "schema_version": 1
    }
  }
  ```
- Provide a CLI: `python scripts/build_replay_fixtures.py --process Cytokinesis`
  (single process) and `--all` (all 28). Default to `--all`.
- Print a per-process summary line: `[ok] <Process>: <n_props> properties,
  n_ticks=100, output=<path>` or `[skip] <Process>: <reason>`.

### Commit 2 — loader extension

Edit `opencell/validation/replay.py`:

- Add a new module constant
  `_REPLAY_FIXTURE_ROOT = Path(...) / "data" / "karr_fixtures" / "per_process_replay"`.
- Extend `load_per_process_fixture` to accept an optional `root` parameter
  (keep backward compat: default to `_REPLAY_FIXTURE_ROOT` IF it exists and
  contains the requested process, ELSE fall back to the existing
  `_DEFAULT_FIXTURE_ROOT` so legacy callers keep working).
- When loading from the new root, read `<Process>.json` + `<Process>.npz`
  directly (no `loadmat` needed). The existing `_infer_n_ticks` already
  honors `manifest.n_ticks` — no change needed there.
- Total diff in `replay.py`: <60 lines. Do NOT refactor the existing
  heuristic split logic; just feed it cleaner inputs.

### Commit 3 — converter unit test + dry-run check

Add `tests/unit/test_build_replay_fixtures.py` (~50 LOC):

- Use a tiny synthetic `.mat` file constructed in-process (via `scipy.io.savemat`)
  with 3 ticks and 2 properties. Confirm the converter:
  - emits `state_before__<prop>` and `states_after__<prop>` with shape `(3, ...)`.
  - writes `manifest.n_ticks=3` in the JSON.
  - tolerates a property whose shape varies tick-to-tick by skipping with a warning.
- Run with `py -3.12 -m pytest tests/unit/test_build_replay_fixtures.py -q`
  and confirm green.

### Commit 4 — integration tests for 2-3 representative processes

After actually running the converter against the real `.mat` files (do this
once during your work; commit the resulting `.npz`/`.json` files IF they
total <5 MB combined; otherwise git-ignore them and document a regenerate
command in the converter docstring + a top-of-file comment in the harness):

- Add `tests/integration/test_replay_fixture_loaded.py` (~80 LOC):
  - One test per representative process: pick **Cytokinesis** (already in
    smoke test, lets us flip an existing xfail), **ChromosomeCondensation**
    (small fixture, good for unit-test-speed), and **Transcription**
    (touches Track-A area, useful sanity).
  - For each: call `load_per_process_fixture(name)`, assert
    `fixture.n_ticks == 100`, assert at least one input key and one output
    key resolved, assert at least one `state_before__<prop>` array has
    leading axis = 100.
  - Do NOT run actual `replay_one_tick` here — that's a separate per-process
    parity gate and out of scope. Just prove the harness sees the channels.
- Update `tests/integration/test_replay_smoke.py:test_replay_smoke_cytokinesis_one_tick`
  ONLY if the xfail trivially flips to pass for Cytokinesis. If it doesn't
  (e.g., key naming mismatch with the process's actual `update()` output),
  document why in a comment and leave it xfailing. Do NOT chase parity
  in this branch.

## Constraints

- Use `py -3.12 -m pytest` for ALL test runs. Default `python` is 3.14
  on this machine and breaks pint/numpy/jax.
- Use `--ignore=tests/gates` in any broad sweep — there's a known
  benchmarks shadowing collision on that path.
- Stay within `~200 LOC` net diff across all 4 commits (the `.npz`/`.json`
  artifacts don't count as LOC even if checked in).
- Do NOT modify any file under `opencell/vivarium/karr_*`,
  `opencell/processes/`, `data/karr_fixtures/per_process/` (legacy
  flat fixtures), or `scripts/matlab/`. Track-B's whole point is to
  add a parallel pathway without disturbing existing artifacts.
- Do NOT attempt to fix or modify replay's heuristic split logic
  (`_split_inputs_outputs`). Your contract is to make its existing
  heuristics succeed by feeding it well-named, well-shaped data.

## Definition of Done

- Branch `track-b/replay-fixtures` has 4 commits as above.
- `py -3.12 -m pytest tests/unit/test_build_replay_fixtures.py tests/integration/test_replay_fixture_loaded.py -q --ignore=tests/gates` is green.
- `py -3.12 -m pytest tests/unit -q --ignore=tests/gates` shows 0 NEW regressions
  vs the pre-branch baseline (target: ≥369 passed, same skipped count as
  baseline ± synthetic test additions).
- `python scripts/build_replay_fixtures.py --process Cytokinesis` (run under
  `py -3.12`) emits `data/karr_fixtures/per_process_replay/Cytokinesis.npz`
  and `.json` files successfully.
- Write a 10-20 line summary at
  `opencell/validation/track_b/b_fixture_pipeline_summary.md` covering:
  what was built, whether the artifacts were checked in or git-ignored
  (and why), the converter usage command, which 2-3 integration tests
  were added, and any per-process pitfalls discovered (e.g., properties
  with variable shape).

## Anti-patterns to avoid

- Do NOT redesign the replay schema. Schema = "namespaced `state_before__<prop>`
  / `states_after__<prop>` keys, tick-major, `manifest.n_ticks` in JSON".
  Anything more elaborate is out of scope.
- Do NOT migrate the legacy `data/karr_fixtures/per_process/` files. Leave
  them in place. The new `per_process_replay/` directory is parallel.
- Do NOT try to handle all 28 processes' edge cases individually. The
  converter should be one uniform code path; per-process oddities get
  logged and skipped, not patched.
- Do NOT scope-creep into replay parity (matching MATLAB outputs to
  Python `process.update()`). That's a follow-up branch with its own
  prompt.

## Hand-off

When done, append a short report to
`opencell/validation/track_b/b_fixture_pipeline_summary.md` as described
above, then exit. The operator will validate under `py -3.12` and merge.
