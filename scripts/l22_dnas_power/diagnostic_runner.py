"""Runs the existing, unmodified Design-A `run_design_a` metric for
DNASupercoiling across explicit seed configurations (N=50 baseline, N=100
combined, seed half-splits), for the N=100 power diagnostic described in
`docs/phase_f/l2_2_design_a/L22_DNAS_POWER_PREREG.md`.

This module never edits `tests/vivarium/l2_2_design_a_runner.py` or
`tests/vivarium/_l2_2_design_a_runner_helpers.py`. It only overrides, for the
duration of one call, the shared oracle loader's default `max_seeds=50` cap
(a sample-size/load-time parameter, not a metric/threshold/biology change)
so seeds 50-99 become visible to the unmodified `run_design_a` entry point.
`_l2_2_design_a_runner_helpers._load_v2_ensemble(process, max_seeds=N)`
already accepts this parameter; this module substitutes the value passed
for one process only, restoring the original function afterwards.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
_VIVARIUM_TESTS = REPO_ROOT / "tests" / "vivarium"
if str(_VIVARIUM_TESTS) not in sys.path:
    sys.path.insert(0, str(_VIVARIUM_TESTS))

PROCESS = "DNASupercoiling"


@contextmanager
def seed_count_override(helpers_module: Any, process: str, max_seeds: int):
    """Temporarily widen `load_karr_oracle`'s seed search for one process.

    Restores the original `load_karr_oracle` attribute on exit regardless of
    success/failure, so no other process/test observes the override.
    """
    original = helpers_module.load_karr_oracle

    def _patched(requested_process: str):
        if requested_process == process:
            widened = helpers_module._load_v2_ensemble(requested_process, max_seeds=max_seeds)  # noqa: SLF001
            if widened is not None:
                return widened
        return original(requested_process)

    helpers_module.load_karr_oracle = _patched
    try:
        yield
    finally:
        helpers_module.load_karr_oracle = original


def run_seed_config(
    *,
    seeds: list[int],
    out_dir: Path,
    max_seeds_override: int,
    m_ticks: int = 100,
    bootstrap_B: int = 1000,
) -> dict[str, Any]:
    """Run the unmodified `run_design_a(process="DNASupercoiling", ...)` for
    an explicit `seeds` list, with the oracle loader's seed-search widened to
    `max_seeds_override` (must be > max(seeds)) for this call only. Writes
    the harness's normal artifact set (result.json, SUMMARY.json, etc.) into
    `out_dir`, which callers must point at a `diagnostic_n100/` subpath, never
    the canonical `latest/`.
    """
    if max_seeds_override <= max(seeds):
        raise ValueError(
            f"max_seeds_override={max_seeds_override} must be > max(seeds)={max(seeds)}"
        )
    import _l2_2_design_a_runner_helpers as helpers_module  # noqa: PLC0415
    import l2_2_design_a_runner as design_a_runner  # noqa: PLC0415

    out_dir.mkdir(parents=True, exist_ok=True)
    with seed_count_override(helpers_module, PROCESS, max_seeds_override):
        return design_a_runner.run_design_a(
            process=PROCESS,
            seeds=list(seeds),
            m_ticks=m_ticks,
            out_dir=out_dir,
            bootstrap_B=bootstrap_B,
        )


def extract_primary_components(payload: dict[str, Any]) -> dict[str, Any]:
    """Pull the `chromosome` primary-channel per-component block out of a
    `run_seed_config` return payload's `result`, for report-building.
    """
    return payload["result"]["channels"]["chromosome"]["per_component"]
