# fix-set-accumulate-warnings

## Problem

`build_karr_chassis_v4` and related integrations emit many Vivarium warnings:
`Incompatible schema assignment` on
`substrates_allocated.<process>.<substrate>`.

Root symptom:
- consumers declare `substrates_allocated` leaves with `_updater: "accumulate"`
- `KarrAllocationStep` declares the same leaves with `_updater: "set"`
- Vivarium warns when the second declaration conflicts with the first

This is a schema ownership issue, not a numeric update bug in allocation math.

## Options considered

1. Keep `set` for allocation step and remove consumer declarations.
2. Change allocation step to `accumulate` to match consumers.
3. Move allocation step output to a new store and retopologize consumers.

## Decision

Choose **Option 1**.

Rationale:
- `substrates_allocated` is produced by exactly one writer:
  `KarrAllocationStep`.
- Its values are absolute per tick allocations, not deltas, so `set` is the
  correct updater for the producing step.
- Consumers only read the allocated values; they do not need to declare updater
  ownership for these leaves.
- This is the smallest, least risky change and preserves existing chassis
  wiring as requested.

## Implementation plan

1. Keep `KarrAllocationStep` as sole schema owner for
   `substrates_allocated.<process>.<substrate>`.
2. Remove `substrates_allocated` blocks from `ports_schema()` of all consuming
   processes that currently re-declare those leaves.
3. Preserve all consumer read paths:
   `states.get("substrates_allocated", {}).get(self.name, {})`.
4. Update tests that asserted consumer-side schema updater on
   `substrates_allocated` (now intentionally absent from consumer schema).

## Non-goals

- No changes to chassis assembly/wiring (`build_karr_chassis_v4` topology).
- No changes to request-generation logic.
- No changes to allocation algorithm.

## Validation

- Targeted reproduction test with `-W error::UserWarning` must pass.
- Full suite with `-W error::UserWarning` should show zero UserWarning failures.
- Full suite without `-W` should remain green at baseline level.
