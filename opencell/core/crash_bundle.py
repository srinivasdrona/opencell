"""Crash bundle: diagnostic capture on first NaN/Inf/assertion failure.

When the simulation produces its first bad value, this module captures
everything needed to diagnose the bug class:
- Exploding solver stats → numerical bug
- Invariant breaks but solver normal → biology/model logic bug
- Abrupt jump in one module → software bug
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CrashBundle:
    """Diagnostic bundle captured on first simulation failure.

    Attributes:
        timestamp: When the crash occurred
        step: Step index
        time_s: Simulation time
        dt: Time step size
        rng_seed: RNG seed (for reproducibility)
        state_norm: L2 norm of state vector
        derivative_norm: L2 norm of derivative vector
        top_changed: Top N species with largest absolute change
        violated_invariant: Which invariant was violated
        last_module: Last sub-model that executed
        solver_stats: Solver diagnostics (steps accepted/rejected)
        error_message: The actual error
    """

    timestamp: str = ""
    step: int = -1
    time_s: float = 0.0
    dt: float = 0.0
    rng_seed: int = 0
    state_norm: float = 0.0
    derivative_norm: float = 0.0
    top_changed: list[dict[str, Any]] = field(default_factory=list)
    violated_invariant: str = ""
    last_module: str = ""
    solver_stats: dict[str, Any] = field(default_factory=dict)
    error_message: str = ""

    def classify_bug(self) -> str:
        """Heuristic bug classification based on diagnostics.

        Returns one of: "numerical", "biology", "software", "unknown"
        """
        if np.isnan(self.state_norm) or np.isinf(self.state_norm):
            return "numerical"
        if np.isnan(self.derivative_norm) or np.isinf(self.derivative_norm):
            return "numerical"
        if self.violated_invariant and self.solver_stats.get("rejected_steps", 0) == 0:
            return "biology"
        if self.top_changed and len(self.top_changed) <= 2:
            return "software"
        return "unknown"

    def save(self, output_dir: str | Path = ".") -> Path:
        """Save crash bundle to JSON file."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"crash_bundle_{self.step}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
        filepath = output_dir / filename

        data = {
            "timestamp": self.timestamp or datetime.now(UTC).isoformat(),
            "step": self.step,
            "time_s": self.time_s,
            "dt": self.dt,
            "rng_seed": self.rng_seed,
            "state_norm": self.state_norm if np.isfinite(self.state_norm) else str(self.state_norm),
            "derivative_norm": self.derivative_norm
            if np.isfinite(self.derivative_norm)
            else str(self.derivative_norm),
            "top_changed": self.top_changed,
            "violated_invariant": self.violated_invariant,
            "last_module": self.last_module,
            "solver_stats": self.solver_stats,
            "error_message": self.error_message,
            "bug_class": self.classify_bug(),
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        logger.error(f"Crash bundle saved to {filepath}")
        return filepath


def capture_crash_bundle(
    step: int,
    time_s: float,
    dt: float,
    state_array: np.ndarray,
    derivative_array: np.ndarray | None,
    species_ids: list[str],
    error_message: str,
    last_module: str = "",
    rng_seed: int = 0,
    solver_stats: dict[str, Any] | None = None,
    violated_invariant: str = "",
    top_n: int = 5,
) -> CrashBundle:
    """Capture a crash bundle from current simulation state."""

    state_norm = float(np.linalg.norm(state_array))
    deriv_norm = float(np.linalg.norm(derivative_array)) if derivative_array is not None else 0.0

    # Find top changed species (by absolute derivative)
    top_changed = []
    if derivative_array is not None:
        abs_derivs = np.abs(derivative_array)
        top_indices = np.argsort(abs_derivs)[-top_n:][::-1]
        for idx in top_indices:
            if idx < len(species_ids):
                top_changed.append(
                    {
                        "species": species_ids[idx],
                        "value": float(state_array[idx]),
                        "derivative": float(derivative_array[idx]),
                    }
                )

    bundle = CrashBundle(
        timestamp=datetime.now(UTC).isoformat(),
        step=step,
        time_s=time_s,
        dt=dt,
        rng_seed=rng_seed,
        state_norm=state_norm,
        derivative_norm=deriv_norm,
        top_changed=top_changed,
        violated_invariant=violated_invariant,
        last_module=last_module,
        solver_stats=solver_stats or {},
        error_message=error_message,
    )

    logger.error(
        f"CRASH at step {step}, t={time_s:.4f}s: {error_message} "
        f"[bug_class={bundle.classify_bug()}]"
    )

    return bundle
