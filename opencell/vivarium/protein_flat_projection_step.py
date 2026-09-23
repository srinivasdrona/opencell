"""Vivarium Step: derive the flat `protein.counts` compatibility view from
the compartmental `protein.compartment_counts` authority.

Primary source: `docs/design/compartmental_protein_state_migration.md`
decisions D3 (mechanism) and D5 (scheduler placement). This is a
**production Step, never a Process**: a Process would compute its update
from the pre-tick snapshot, lagging the flat view by one tick (design D5
rationale). Two instances of this same class are registered per composite --
`protein_flat_projection_pre` (layer 0, consumes this tick's just-applied
Process writes, feeds the flat-reading request-calculator Steps) and
`protein_flat_projection_post` (runs after every authority-writing Step,
feeds downstream observability/derived readers). See `karr_composite.py`.

Stage 1a (this commit): `protein_state.MIGRATED_WIDS` is the empty tuple, so
`next_update` always returns `{}` and this Step changes no state -- it is
wired into the Step graph (satisfying the structural test C12) but is fully
behavior-neutral.
"""

from __future__ import annotations

from typing import Any

from vivarium.core.process import Step

from opencell.vivarium.protein_state import (
    COMPARTMENTS,
    MIGRATED_WIDS,
    flat_counts_schema,
    make_privileged_projection_write,
    project_mature_row,
)


class ProteinFlatProjectionStep(Step):
    """Recompute `protein.counts[wid] = Pi(protein.compartment_counts.mature[wid])`
    for every WID in `protein_state.MIGRATED_WIDS`, overwriting the full flat
    map on every run (design D3: overwrite-on-every-run, not just on change,
    so a write that sneaks past the rejecting updater cannot persist beyond
    one Step layer).
    """

    name = "protein_flat_projection"
    defaults: dict[str, Any] = {}

    def ports_schema(self) -> dict[str, Any]:
        migrated = tuple(MIGRATED_WIDS)
        return {
            "protein": {
                "compartment_counts": {
                    "mature": {
                        wid: {comp: {"_default": 0.0} for comp in COMPARTMENTS}
                        for wid in migrated
                    }
                },
                "counts": flat_counts_schema(migrated),
            }
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del timestep
        migrated = tuple(MIGRATED_WIDS)
        if not migrated:
            return {}
        mature = states.get("protein", {}).get("compartment_counts", {}).get("mature", {})
        counts_update = {
            wid: make_privileged_projection_write(project_mature_row(mature.get(wid, {})))
            for wid in migrated
        }
        return {"protein": {"counts": counts_update}}


__all__ = ["ProteinFlatProjectionStep"]
