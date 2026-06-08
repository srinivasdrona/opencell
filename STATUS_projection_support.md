# STATUS projection_support

## INTENT

Summary: replace the runner's hardcoded L2.2 process wiring with catalog-derived wiring, add projection-based primary-distance infrastructure, keep all existing Design-A anticheat behavior green, and stage the work in five committed beats.

Contract: `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml` is the authoritative wiring contract, and the runner changes are scoped to `tests/vivarium/**` only. Done means `tests/vivarium/l2_2_design_a_runner.py` reads in-scope process configuration from the catalog at startup, preserves the existing behavior for the current five processes, and can optionally score a primary channel via projection-based distance blocks without regressing current tests.

Expected observable: after Beat 4, `bin/oc-pytest.cmd tests/vivarium/test_l2_2_design_a*.py -q` stays green while `result.json` / `SUMMARY.json` can carry optional `per_component` or `hurdle` diagnostics for catalog entries that request non-default `primary_distance`.

Inversion: the embarrassing failure mode is that I keep the old five-process behavior by silently preserving the hardcoded tables and only layering a catalog reader beside them, so tests pass while new processes and out-of-scope rejection still follow stale code paths. A second risk is wiring projection support against already-projected channel vectors instead of the chromosome state snapshot, which would satisfy the new function signatures while making `primary_projection` useless for the intended follow-up processes.

PM sanity-check: I am assuming the new projection paths are infrastructure-only in this task, so it is acceptable to wire them end-to-end without yet introducing any current catalog entry that uses them in production runner flow.

## Beat 1 - Audit current runner + hook design

Status: completed

Read set:
- `docs/prompts/DELIBERATE_ACTION_PREFIX_v2.md`
- `docs/prompts/FIX_TEMPLATE_L2_REPLAY.md`
- `docs/prompts/COMPOSITION_MANDATE_v2.md`
- `tests/vivarium/l2_2_design_a_runner.py`
- `tests/vivarium/_l2_2_design_a_runner_helpers.py`
- `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml`
- Existing anticheat tests under `tests/vivarium/test_l2_2_design_a_runner*.py`

Current hardcoded process tables in runner:
- `SUPPORTED_PROCESSES` in `tests/vivarium/l2_2_design_a_runner.py:36`
- `_PROCESS_BUCKET` in `tests/vivarium/l2_2_design_a_runner.py:38`
- `_PROCESS_K_ENG` in `tests/vivarium/l2_2_design_a_runner.py:45`
- `_PROCESS_OUTPUT_CHANNELS` in `tests/vivarium/l2_2_design_a_runner.py:50`
- `_PROCESS_PRIMARY_CHANNEL` in `tests/vivarium/l2_2_design_a_runner.py:57`
- `_PROCESS_ANALYTICAL_CHECK_REASON` in `tests/vivarium/l2_2_design_a_runner.py:64`
- Supporting channel-key tables that stay structural rather than catalog-derived:
  - `_ORACLE_BEFORE_KEY` in `tests/vivarium/l2_2_design_a_runner.py:71`
  - `_ORACLE_AFTER_KEY` in `tests/vivarium/l2_2_design_a_runner.py:80`

Current catalog-field consumption audit:
- `name`
  - Current behavior: implicitly consumed by `SUPPORTED_PROCESSES`, `_process_sample_process`, and the helper dispatch tables rather than by the catalog.
  - Hook plan: `_load_catalog()` becomes the source for the supported/in-scope process set and for all per-process accessors.
- `bucket`
  - Current behavior: consumed from `_PROCESS_BUCKET` in `run_design_a()` at `tests/vivarium/l2_2_design_a_runner.py:493`; also fed into summary/result payloads and threshold math through `_PROCESS_K_ENG`.
  - Hook plan: derive per-process bucket from catalog entry, keep `_PROCESS_K_ENG` as the bucket-to-threshold constant map.
- `in_scope_L2_2`
  - Current behavior: not read explicitly; enforced indirectly because only the current five in-scope processes appear in `SUPPORTED_PROCESSES`.
  - Hook plan: `_load_catalog()` filters to in-scope entries; startup validation distinguishes unknown process from known-but-out-of-scope process and names the catalog bucket plus rationale.
- `primary_channel`
  - Current behavior: consumed through `_PROCESS_PRIMARY_CHANNEL` in `run_design_a()` at `tests/vivarium/l2_2_design_a_runner.py:496`; also used by `_warning_strings()` at line 265 and by allocator-input bookkeeping at lines 593-596.
  - Hook plan: catalog-backed accessor, same downstream use sites.
- `output_channels`
  - Current behavior: consumed through `_PROCESS_OUTPUT_CHANNELS` in `run_design_a()` at `tests/vivarium/l2_2_design_a_runner.py:495`; controls `after_vectors`, `oc_vectors`, per-channel scoring loop, and output payload structure.
  - Hook plan: catalog-backed accessor, same downstream use sites.
- `M_ticks`
  - Current behavior: not enforced from spec; caller supplies `--ticks`, and `_normalize_seed_axis()` only checks oracle width against the requested tick count at `tests/vivarium/l2_2_design_a_runner.py:157-170`.
  - Hook plan: keep explicit `m_ticks` argument behavior for tests, but add catalog accessors so future callers can compare requested ticks against catalog defaults and so STATUS can state the current mismatch honestly.
- `N_seeds`
  - Current behavior: not enforced from spec; caller supplies `--seeds`, and the runner uses the resolved list length.
  - Hook plan: expose via catalog accessor for future validation / reporting, without changing current tests.
- `karr_artifact`
  - Current behavior: not consumed in the runner; helper loaders currently hardcode legacy `per_process_replay/*.npz` fixtures for the five existing processes.
  - Hook plan: catalog-derived accessors will surface the field, but actual helper oracle routing remains unchanged in this task unless a test-safe path is needed.
- `event_channels`
  - Current behavior: not consumed; every channel is emitted as `is_event_channel: False` at `tests/vivarium/l2_2_design_a_runner.py:649`.
  - Hook plan: catalog-backed event-channel set will mark channel payloads and feed deferred-gating behavior in the runner wiring.
- `seed_window`
  - Current behavior: not consumed.
  - Hook plan: carry through catalog accessors only; no active seed-window execution logic in this task.
- `joint_check`
  - Current behavior: not consumed; result and summary payloads hardcode `joint_check: None`.
  - Hook plan: carry through catalog accessors only; the actual cross-channel diagnostic remains future work.
- `primary_projection`
  - Current behavior: not consumed.
  - Hook plan: projection extractor runs after `runner_helpers.run_oc_tick(...)` has produced the SUT tick result and before the channel-level W1 aggregation currently written at `tests/vivarium/l2_2_design_a_runner.py:578-584` / `618-655`.
- `primary_distance`
  - Current behavior: not consumed; all channels hardcode `aggregation: "per_tick_vector_w1_mean"` at `tests/vivarium/l2_2_design_a_runner.py:650`.
  - Hook plan: replace the single-implementation primary-channel distance path with a dispatcher that keeps `_per_sample_w1`-style behavior for the default and routes to projection-based implementations for `per_component_scaled` and `hurdle_event_rate_plus_conditional_scaled_distance`.

Hook design:
- Projection extractor insertion point:
  - The new extractor should run in `run_design_a()` after each tick's SUT execution and before the per-channel W1 rollup.
  - Concretely: after `oc_result = runner_helpers.run_oc_tick(...)` at `tests/vivarium/l2_2_design_a_runner.py:578` and before `per_sample_w1[channel][seed_index, tick] = ...` at lines 579-584.
  - Practical implication: helper tick runners need to return enough state context for projection resolution, not only the existing observable vectors.
- Distance-dispatch insertion point:
  - The current single aggregation path lives in the per-channel loop at `tests/vivarium/l2_2_design_a_runner.py:613-655`.
  - For default `per_tick_vector_w1_mean`, preserve the existing channel payload and verdict math.
  - For non-default `primary_distance`, compute the specialized diagnostic for the primary channel, emit `per_component` or `hurdle` blocks on that channel payload, and derive the primary verdict from component-level thresholds while leaving secondary channels on the current W1 path.
- Warning / summary touch points:
  - Primary-channel warning helpers currently assume raw channel vectors (`_warning_strings`, `_primary_channel_oracle_laundering_warning`, `_primary_channel_oracle_determinism_legitimate_warning`, `_seed_alignment_warning`).
  - The specialized distance work should preserve those warnings for legacy/default flows and avoid silently bypassing them when a process later opts into projection mode.

Files expected to change:
- `tests/vivarium/l2_2_design_a_runner.py`
- `tests/vivarium/_l2_2_design_a_runner_helpers.py`
- `tests/vivarium/_l2_2_design_a_projections.py` (new)
- `tests/vivarium/test_l2_2_design_a_projections.py` (new)
- Existing Design-A anticheat tests under `tests/vivarium/test_l2_2_design_a_runner*.py` as needed for catalog-backed behavior
- `scripts/probe_l22_projection_smoke.py` (new)
- `STATUS_projection_support.md`

Beat 1 verdict: PASS

## Beat 2 - Catalog loader + table replacement

Status: completed

Changes:
- Added `_load_catalog(path: Path | None = None)` in `tests/vivarium/l2_2_design_a_runner.py`, backed by `yaml.safe_load` and `@lru_cache(maxsize=1)`.
- Added a full-catalog companion loader so the runner can distinguish:
  - unknown process
  - known but out-of-scope catalog process
  - in-scope catalog process not yet implemented by the current helper/oracle layer
- Replaced the current module-level process tables with catalog-derived equivalents while keeping the existing names:
  - `SUPPORTED_PROCESSES`
  - `_PROCESS_BUCKET`
  - `_PROCESS_OUTPUT_CHANNELS`
  - `_PROCESS_PRIMARY_CHANNEL`
  - `_PROCESS_ANALYTICAL_CHECK_REASON`
- Normalized catalog channel spellings into the runner's existing internal spellings (notably `rnas -> RNAs`, `mrnas -> mRNAs`) so current helper/oracle code remains unchanged.
- Added runner-startup conformance errors:
  - out-of-scope process names now fail with `bucket=<...>; rationale=<...>`
  - in-scope catalog names that the current runner does not yet implement now fail before helper dispatch
- Added `tests/vivarium/test_l2_2_design_a_runner_catalog.py` to lock in catalog filtering, normalization, table derivation, and the new error messages.

Verification:
- Command: `bin\oc-pytest.cmd tests/vivarium/test_l2_2_design_a*.py -q`
- Actual: `17 passed in 97.44s`

Beat 2 verdict: PASS

## Beat 3 - Projection extractor + distance functions

Status: completed

Changes:
- Added `tests/vivarium/_l2_2_design_a_projections.py` with:
  - `extract_projection(...)`
  - `per_component_scaled_distance(...)`
  - `hurdle_event_rate_plus_conditional_distance(...)`
  - alias `hurdle_event_rate_plus_conditional_scaled_distance(...)` for the catalog string variant
- `extract_projection(...)` now supports:
  - ordinary dotted chromosome paths
  - `delta_*` scalar deltas between per-tick before/after snapshots
  - `replication_state` categorical encoding
  - `replication_complete_fired_this_tick`
  - `repair_event_present`
  - `repair_count_by_pathway.<pathway>_delta`
- Added synthetic unit tests in `tests/vivarium/test_l2_2_design_a_projections.py` covering:
  - dotted path and derived-component resolution
  - missing-path error reporting
  - per-component scaling semantics
  - hurdle all-zero behavior
  - hurdle conditional-nonzero behavior

Verification:
- Command: `bin\oc-pytest.cmd tests/vivarium/test_l2_2_design_a_projections.py -q`
- Actual: `5 passed in 17.79s`

Beat 3 verdict: PASS

## Beat 4 - Wire runner to use primary_distance

Status: completed

Changes:
- Updated `tests/vivarium/l2_2_design_a_runner.py` to read and expose the catalog-backed fields needed for projection wiring:
  - `event_channels`
  - `joint_check`
  - `primary_projection`
  - `primary_distance` with default `per_tick_vector_w1_mean`
- Preserved the existing per-channel W1 bookkeeping for all channels and all current processes.
- Added a primary-channel projection-distance dispatcher:
  - default path: unchanged `per_tick_vector_w1_mean`
  - `per_component_scaled`: emits `channel_payloads[primary_channel]["per_component"]`
  - `hurdle_event_rate_plus_conditional_scaled_distance`: emits `channel_payloads[primary_channel]["hurdle"]`
- Marked catalog event channels as `is_event_channel: true` and deferred their normal gating via `EVENT_CHANNEL_DEFERRED`.
- Bumped `SUMMARY_SCHEMA_VERSION` from `1.3` to `1.4` with an inline comment documenting the optional primary-channel diagnostic additions.
- Extended `tests/vivarium/test_l2_2_design_a_runner_catalog.py` to cover:
  - `per_component` primary payload emission
  - `hurdle` primary payload emission
  - event-channel deferral accounting

Verification:
- Command: `bin\oc-pytest.cmd tests/vivarium/test_l2_2_design_a*.py -q`
- Actual: `25 passed in 62.63s`

Beat 4 verdict: PASS

## Beat 5 - Synthetic smoke

Status: completed

Changes:
- Added `scripts/probe_l22_projection_smoke.py`.
- The probe constructs:
  - a synthetic 3-component `per_component_scaled` catalog entry
  - a synthetic 5-component hurdle catalog entry
- The probe exercises the new distance functions directly and asserts that the returned structures contain the expected component blocks.

Smoke stdout:
```text
per_component joint_verdict=PASS components=3
hurdle joint_verdict=PASS event_rate_diff=0.000000 conditionals=4
PASS
```

Final verification:
- Command: `bin\oc-pytest.cmd tests/vivarium/test_l2_2_design_a*.py -q`
- Actual: `25 passed in 77.31s`

Beat 5 verdict: PASS

verdict: PASS
