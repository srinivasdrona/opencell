"""Cell-cycle coordination step for Phase C chassis_v5 integration.

This step runs at tick boundaries and ratchets cross-process state transitions
for replication/segregation/division.
"""

from __future__ import annotations

from typing import Any

from vivarium.core.process import Step


class CellCycleCoordinator(Step):
    """Coordinate cross-process replication and division state transitions."""

    name = "cell_cycle_coordinator"
    defaults: dict[str, Any] = {
        "time_step": 1.0,
        "terc_position_bp": 290_038.0,
        "segregation_complete_threshold": 1.0,
        "division_complete_threshold": 1.0,
    }

    def ports_schema(self) -> dict[str, Any]:
        return {
            "chromosome": {
                "replication_state": {"_default": "idle", "_updater": "set", "_emit": True},
                "fork_position_bp": {
                    "left": {"_default": 0.0, "_updater": "accumulate", "_emit": True},
                    "right": {"_default": 0.0, "_updater": "accumulate", "_emit": True},
                },
                "fork_positions": {
                    # Alias for pc-t6 input contract.
                    "_default": {"left": None, "right": None},
                    "_updater": "set",
                    "_emit": False,
                },
                "forks_passing": {"_default": False, "_updater": "set", "_emit": False},
                "segregation_progress": {
                    "_default": 0.0,
                    "_updater": "accumulate",
                    "_emit": True,
                },
            },
            "cell": {
                "cycle_phase": {"_default": "idle", "_updater": "set", "_emit": True},
                "ftsz_ring_complete": {"_default": False, "_updater": "set", "_emit": True},
                "division_progress": {
                    "_default": 0.0,
                    "_updater": "accumulate",
                    "_emit": True,
                },
                "division_complete": {"_default": False, "_updater": "set", "_emit": True},
                "division_event_count": {
                    "_default": 0.0,
                    "_updater": "accumulate",
                    "_emit": True,
                },
                "gate_allow_cytokinesis": {"_default": False, "_updater": "set", "_emit": True},
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del timestep

        chromosome = states.get("chromosome", {})
        cell = states.get("cell", {})

        replication_state = str(chromosome.get("replication_state", "idle"))
        phase = str(cell.get("cycle_phase", "idle"))

        fork_state = chromosome.get("fork_position_bp", {})
        left_fork = float(fork_state.get("left", 0.0))
        right_fork = float(fork_state.get("right", 0.0))
        forks_at_terc = (
            left_fork >= float(self.parameters["terc_position_bp"])
            and right_fork >= float(self.parameters["terc_position_bp"])
        )

        segregation_progress = float(chromosome.get("segregation_progress", 0.0))
        ftsz_ring_complete = bool(cell.get("ftsz_ring_complete", False))
        division_progress = float(cell.get("division_progress", 0.0))
        division_complete = bool(cell.get("division_complete", False))

        seg_complete_threshold = float(self.parameters["segregation_complete_threshold"])
        div_complete_threshold = float(self.parameters["division_complete_threshold"])

        allow_cytokinesis = bool(
            segregation_progress >= seg_complete_threshold and ftsz_ring_complete
        )

        phase_update: str | None = None
        replication_update: str | None = None

        # idle -> initiating (when pc-t1 has set replication_state to initiating)
        if phase == "idle" and replication_state == "initiating":
            phase_update = "initiating"
        # initiating -> elongating (one tick later)
        elif phase == "initiating" and replication_state == "initiating":
            phase_update = "elongating"
            replication_update = "elongating"
        elif replication_state == "elongating" and phase in {"idle", "initiating"}:
            phase_update = "elongating"

        # elongating -> complete (both forks at terC or replication already complete)
        if phase in {"elongating", "initiating"} and (forks_at_terc or replication_state == "complete"):
            phase_update = "complete"
            replication_update = "complete"

        # complete -> segregating
        if phase in {"complete", "elongating"} and segregation_progress > 0.0:
            phase_update = "segregating"

        # segregating -> dividing
        if phase in {"segregating", "complete"} and allow_cytokinesis:
            phase_update = "dividing"

        # dividing -> divided
        if phase == "dividing" and (
            division_complete or division_progress >= div_complete_threshold
        ):
            phase_update = "divided"

        update: dict[str, Any] = {
            "chromosome": {
                "fork_positions": {
                    "left": float(left_fork),
                    "right": float(right_fork),
                },
                "forks_passing": bool(
                    replication_state == "elongating" and not forks_at_terc
                ),
            },
            "cell": {
                "gate_allow_cytokinesis": allow_cytokinesis,
            },
        }
        if replication_update is not None:
            update["chromosome"]["replication_state"] = replication_update
        if phase_update is not None:
            update["cell"]["cycle_phase"] = phase_update
        if phase == "dividing" and phase_update == "divided":
            update["cell"]["division_event_count"] = 1.0
        return update


__all__ = ["CellCycleCoordinator"]
