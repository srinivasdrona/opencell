"""Read-only capture of the real DNASupercoiling Design-A projection tensors.

This mirrors the proven zero-edit capture pattern used in the earlier
DNAS N=100 power diagnostic, but is kept process-local so no shared
Design-A runner or evidence-index source files need to change.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
_VIVARIUM_TESTS = REPO_ROOT / "tests" / "vivarium"
if str(_VIVARIUM_TESTS) not in sys.path:
    sys.path.insert(0, str(_VIVARIUM_TESTS))

from scripts.l22_dnas_power import diagnostic_runner  # noqa: E402


@contextmanager
def capture_projection_tensors(runner_module: Any):
    """Capture one `per_component_scaled_distance` call by rebinding it."""
    original = runner_module.per_component_scaled_distance
    captured: dict[str, Any] = {}

    def _spy(oc_projection_vectors, karr_projection_vectors, component_scales):
        captured["oc"] = np.array(oc_projection_vectors, dtype=np.float64, copy=True)
        captured["karr"] = np.array(karr_projection_vectors, dtype=np.float64, copy=True)
        captured["component_scales"] = dict(component_scales)
        return original(oc_projection_vectors, karr_projection_vectors, component_scales)

    runner_module.per_component_scaled_distance = _spy
    try:
        yield captured
    finally:
        runner_module.per_component_scaled_distance = original


def run_and_capture(
    *,
    seeds: list[int],
    out_dir: Path,
    max_seeds_override: int,
    m_ticks: int = 100,
    bootstrap_B: int = 1000,
) -> dict[str, Any]:
    """Run the unmodified DNASupercoiling Design-A harness and capture tensors."""
    import l2_2_design_a_runner as design_a_runner  # noqa: PLC0415

    with capture_projection_tensors(design_a_runner) as captured:
        payload = diagnostic_runner.run_seed_config(
            seeds=seeds,
            out_dir=out_dir,
            max_seeds_override=max_seeds_override,
            m_ticks=m_ticks,
            bootstrap_B=bootstrap_B,
        )
    if "oc" not in captured or "karr" not in captured:
        raise RuntimeError(
            "capture_projection_tensors did not observe a "
            "per_component_scaled_distance call."
        )
    return {
        "payload": payload,
        "oc_tensor": captured["oc"],
        "karr_tensor": captured["karr"],
        "component_scales": captured["component_scales"],
    }


__all__ = ["capture_projection_tensors", "run_and_capture"]

