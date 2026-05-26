# Canary Tracer Fix Status

## Scope
- Worktree: `/mnt/e/opencell-worktrees/canary-tracer-fix`
- Branch: `fix/canary-tracer-ports-v2`
- Base reference provided: `trackA/wave2-base` @ `cd2e775`

## Diff Summary
Updated `scripts/run_chassis_v6_32400t.py` to remove the hard-coded `"substrates"` tracer filter and capture writes across all routed update ports.

### DiagnosticCollector changes
1. Added helpers:
- `_topology_path_tuple(...)` to normalize topology port paths
- `_iter_numeric_leaf_writes(...)` to collect numeric leaf updates (including nested dict leaves)
- `_nested_get(...)` for baseline lookup on nested state paths

2. Refactored `DiagnosticCollector._patch_entities(...)`:
- Builds `shared_ports` from topology per entity (all routed ports with non-empty topology paths)
- Builds per-port updater maps via `_collect_leaf_updaters(schema.get(port_name, {}))` for every declared schema port
- In `wrapped_next_update(...)`, iterates `update.items()` and processes each shared port instead of `update.get("substrates", {})`
- Preserves set-vs-accumulate delta behavior per leaf key using per-port updater maps
- Keeps `per_tick_process_sums` conservation accounting limited to substrate-root writes to avoid conservation regression while still writing all-port process traces

3. Small robustness fix in same file:
- Moved `diagnostics.close()` to run before `build_e2_payload(...)` so trace CSV headers are flushed before header inspection.

## New Tests
Added `tests/scripts/test_canary_tracer_ports.py` with two tests:
1. `test_diagnostic_collector_records_writes_from_multiple_ports`
- Verifies one entity writing to both `substrates` and `rna` is traced from both ports
- Verifies `set` updater delta baseline logic on substrate leaf and nested-port capture for RNA leaf

2. `test_diagnostic_collector_skips_non_shared_ports_without_crashing`
- Verifies writes to a non-routed port are skipped silently (no crash)
- Verifies routed substrate write still appears in process trace

## Test Results
Command run:
```bash
timeout 600 pytest tests/scripts/test_canary_tracer_ports.py tests/unit/ -q --tb=short
```
(Executed via required WSL wrapper: `wsl bash -lc "source /mnt/e/opencell/.venv-wsl/bin/activate && cd /mnt/e/opencell-worktrees/canary-tracer-fix && ..."`.)

Result:
- `379 passed, 11 skipped in 155.74s (0:02:35)`

## 200-Tick Smoke Validation
Command run:
```bash
timeout 900 python scripts/run_chassis_v6_32400t.py --seed 42 --biological-seconds 200 --out-dir /tmp/canary_test_portfix --fresh
```
(Executed via required WSL wrapper.)

Observed runtime:
- Simulation advanced through `tick=200/200`
- Post-run failed at manifest git SHA capture (`git rev-parse HEAD`) due WSL worktree git path resolution (`CalledProcessError` / exit 128)

Trace artifact validation from `/tmp/canary_test_portfix/process_traces/`:
- `karr_transcription.csv`: `510480` bytes, `10541` lines
- `karr_translation.csv`: `113322` bytes, `2327` lines

Conclusion:
- Non-substrates process traces are now populated (no longer header-only / 21B-style empty outputs for these files).

## emit_step_s Decision
Left unchanged (`emit_step_s=float(ticks)` and engine `emit_step=float(ticks)`) in this patch.

Rationale:
- This tracer fix is independent of vivarium emitter cadence.
- Changing emit cadence in this hotfix would alter memory/performance behavior for long runs and is better handled as a separate follow-up.
