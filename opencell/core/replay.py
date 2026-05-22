"""Single-step replay / delta ledger debug mode.

Replay exactly one step from checkpoint, print each module/reaction
contribution to Δstate for any species. Shows:
  starting value → contributions by term/module → ending value → conservation residuals

Fastest path to answering "which module injected nonsense?"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DeltaEntry:
    """Contribution of one module to one species' change."""

    module_id: str
    species_id: str
    delta: float
    description: str = ""


@dataclass
class StepReplay:
    """Complete delta ledger for a single simulation step."""

    step_index: int
    t_start: float
    dt: float
    species_start: dict[str, float] = field(default_factory=dict)
    species_end: dict[str, float] = field(default_factory=dict)
    deltas: list[DeltaEntry] = field(default_factory=list)
    conservation_residuals: dict[str, float] = field(default_factory=dict)

    def contributions_for(self, species_id: str) -> list[DeltaEntry]:
        """Get all module contributions for a specific species."""
        return [d for d in self.deltas if d.species_id == species_id]

    def report(self, species_id: str) -> str:
        """Human-readable report for one species through this step."""
        lines = [
            f"Step {self.step_index} (t={self.t_start:.4f}, dt={self.dt:.4e})",
            f"  {species_id}: {self.species_start.get(species_id, '?'):.6f}",
        ]
        contribs = self.contributions_for(species_id)
        for d in contribs:
            sign = "+" if d.delta >= 0 else ""
            lines.append(f"    {sign}{d.delta:.6e}  ← {d.module_id} {d.description}")
        total_delta = sum(d.delta for d in contribs)
        lines.append("    ----------")
        lines.append(f"    Δ = {total_delta:.6e}")
        lines.append(f"  → {self.species_end.get(species_id, '?'):.6f}")
        if species_id in self.conservation_residuals:
            lines.append(f"  Conservation residual: {self.conservation_residuals[species_id]:.2e}")
        return "\n".join(lines)


class DeltaLedger:
    """Records per-module, per-species deltas for debugging.

    Attach to engine in debug mode to trace exactly where
    state changes originate.
    """

    def __init__(self) -> None:
        self._steps: list[StepReplay] = []
        self._current: StepReplay | None = None

    def begin_step(self, step_index: int, t: float, dt: float, state: dict[str, float]) -> None:
        """Start recording a new step."""
        self._current = StepReplay(
            step_index=step_index,
            t_start=t,
            dt=dt,
            species_start=dict(state),
        )

    def record_delta(
        self,
        module_id: str,
        species_id: str,
        delta: float,
        description: str = "",
    ) -> None:
        """Record a single module's contribution to a species."""
        if self._current is None:
            raise RuntimeError("No step in progress — call begin_step first")
        self._current.deltas.append(
            DeltaEntry(
                module_id=module_id,
                species_id=species_id,
                delta=delta,
                description=description,
            )
        )

    def end_step(
        self, state: dict[str, float], residuals: dict[str, float] | None = None
    ) -> StepReplay:
        """Finalize the current step."""
        if self._current is None:
            raise RuntimeError("No step in progress")
        self._current.species_end = dict(state)
        self._current.conservation_residuals = residuals or {}
        step = self._current
        self._steps.append(step)
        self._current = None
        return step

    @property
    def steps(self) -> list[StepReplay]:
        return list(self._steps)

    def find_first_bad_step(self, species_id: str, threshold: float = 0.0) -> StepReplay | None:
        """Find the first step where a species goes below threshold."""
        for step in self._steps:
            end_val = step.species_end.get(species_id, threshold + 1)
            if end_val < threshold:
                return step
        return None
