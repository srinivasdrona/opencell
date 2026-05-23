# Phase C Turn 10 — TerminalOrganelleAssembly

**Status**: design ready · **Estimated wall**: 35 min · **Karr process**: `Process_TerminalOrganelleAssembly`

## Primary-source references

- Karr extract: `docs/karr_extracts/process/28_TerminalOrganelleAssembly.md`
- OpenCell fixture: `data/karr_fixtures/per_process/TerminalOrganelleAssembly_flat.mat`

Notes on source availability in this worktree:
- The prompt references `docs/karr_extracts/process/11_TerminalOrganelleAssembly.md`; the available extract is `28_TerminalOrganelleAssembly.md`.
- The prompt references `data/m1_sources/karr_native/per_process_traces/TerminalOrganelleAssembly_100ticks.mat`; no `*_100ticks.mat` files are present in this worktree.
- The MATLAB source file path cited by the extract is not present under `data/m1_sources/WholeCell/...` in this worktree snapshot, so implementation is constrained to extract + fixture evidence.

## Why this is Phase C Turn 10

Terminal organelle assembly is a key *M. genitalium* cell-cycle morphology process tied to:
- polar adhesion (motility/host interaction coupling),
- duplication during replication,
- daughter-pole migration during division.

In this turn we deliver a Karr-light v1 that preserves the fixture-defined hierarchical assembly logic while representing the structure as coarse component counters instead of compartmentalized per-protein localization arrays.

## Karr algorithm (mapped to light-scope implementation)

Docstring simulation outline:
1. Determine which localization reactions can proceed.
2. Determine which proteins can localize.
3. Incorporate localizable proteins.
4. Repeat until no more localization is possible.

Fixture-derived hierarchy used directly:
- Proteins (8): `MG_191_MONOMER`, `MG_192_MONOMER`, `MG_217_MONOMER`, `MG_218_MONOMER`, `MG_312_MONOMER`, `MG_317_MONOMER`, `MG_318_MONOMER`, `MG_386_MONOMER`.
- Reactions (10) from `localizationReactions` + `localizationSubstrates` + `localizationThreshold`.
- Special HMW1/HMW2 mutual dependency behavior is represented by paired reactions requiring the partner in either "unincorporated" or "incorporated" context (captured via thresholded dependency checks).

Karr-light per-tick behavior:
- Evaluate reaction eligibility from current assembled counters and protein activity gates.
- Assemble at most one component step per reaction per tick (bulk counter increment).
- Update organelle-level count as the minimum assembled count across all 8 required proteins.
- Clamp to `target_terminal_organelle_count` (default 1 in single-cycle mode; can be 2 during duplication/division scenarios).

## Scope

### In scope (v1 / light)

- New process: `opencell/vivarium/karr_terminal_organelle_assembly.py`.
- New cell-level state:
  - `cell.terminal_organelle_count` (integer-like count emitted as accumulate delta)
  - `cell.terminal_organelle_components_assembled` (per-protein integer-like counters)
- Hierarchical, component-by-component assembly using fixture reaction dependency matrices.
- Activity-gated assembly input from `protein.activity` (per-protein boolean/0-1 gates).
- Deterministic per-tick updates; no stochastic kinetics introduced (consistent with "no kinetic information reported").

### Deferred to v2

- Full compartment-level substrate representation (`unincorporated` vs `terminal organelle`) as in Karr state.
- Explicit migration/duplication pole dynamics across a full cell cycle.
- Direct calibration against native `TerminalOrganelleAssembly_100ticks.mat` trace (artifact absent in this worktree).
- Tight coupling with HostInteraction process signals.

## State ports and store additions

```python
"protein": {
    "activity": {
        # Required gates for 8 terminal-organelle proteins
        wid: {"_default": 0.0, "_updater": "set", "_emit": False}
    }
},
"cell": {
    "terminal_organelle_count": {
        "_default": 0.0,
        "_updater": "accumulate",
        "_emit": True,
    },
    "terminal_organelle_components_assembled": {
        wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
        for wid in terminal_organelle_component_wids
    },
},
```

Rationale:
- Per-tick writers are accumulate deltas.
- `protein.activity` is read-only input and uses set semantics upstream.

## Substrate consumption and allocation contract

- No ATP/GTP/H2O or other shared substrate stoichiometry is defined for this process in the fixture/docstring.
- Therefore this process does **not** participate in `KarrAllocationStep` and does not write `requests`/`substrates_allocated`.

## Expected dynamics and 100-tick validation target

Because native per-process trace artifact is not present locally, validation target for this turn is fixture-derived:
- Monotonic non-decreasing assembly counters per component.
- Hierarchy-respecting ordering (downstream components do not assemble before prerequisites).
- Saturation at `target_terminal_organelle_count`.
- Stable plateau over 100 ticks once assembly completes.

This provides a deterministic proxy trajectory for regression tests until native trace files are available.

## Test plan

1. `test_fixture_loads_terminal_organelle_hierarchy`
   - Process instantiates with defaults.
   - Confirms 8 substrates and 10 localization reactions loaded.
2. `test_one_tick_delta_sign_is_positive_for_first_component`
   - With all activities enabled and zero initial assembly, one tick yields non-negative deltas and at least one positive assembly delta.
3. `test_activity_gate_blocks_component_assembly`
   - If a required protein activity gate is off, dependent component(s) do not assemble.
4. `test_hierarchy_order_enforced`
   - Components with unmet prerequisites remain zero until prerequisite counters rise.
5. `test_100_tick_progression_reaches_expected_plateau`
   - Over 100 ticks under full activity, component counters approach and hold at target count and organelle count reaches expected target.
6. `test_no_nan_or_negative_regressions`
   - Across repeated ticks with mixed activity, all outputs remain finite and non-negative.

## Open questions

1. Confirm canonical mapping of MG IDs to labels (P1/P30/HMW1/2/3/etc.) for final naming consistency in docs and emits.
2. Confirm intended source for `protein.activity` gating of these 8 proteins; existing `karr_protein_activation` currently regulates a different protein subset.
3. Confirm expected `target_terminal_organelle_count` schedule across cell-cycle stages (1 in vegetative, 2 near division).
