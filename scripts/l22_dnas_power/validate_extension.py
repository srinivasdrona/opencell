"""Structural/schema/non-vacuity validation for the seeds 50-99
DNASupercoiling trace extension, reusing existing, unmodified validators:

  - `scripts/l22_extraction/trace_validation.validate_structural` (schema/hash/tick-count)
  - `scripts/l22_extraction/preflight.schema_preflight` (drift vs canonical seed 0)

plus one new check specific to this diagnostic: non-vacuity of the
`chromosome` primary projection (`linkingNumbers.delta_nnz` /
`linkingNumbers.delta_value_sum`) for each new seed, using the existing
`load_chromosome_oracle_for_process` / `chromosome_projection_matrix`
helpers (unmodified) from `_l2_2_design_a_runner_helpers.py`.
"""

from __future__ import annotations

import functools
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

from scripts.l22_extraction import preflight as preflight_module  # noqa: E402
from scripts.l22_extraction.launcher import canonical_seed0_path, seed_mat_path  # noqa: E402
from scripts.l22_extraction.preflight import schema_preflight  # noqa: E402
from scripts.l22_extraction.trace_validation import validate_structural  # noqa: E402


@contextmanager
def _schema_preflight_root_override(karr_native_root: Path | None):
    """`preflight.schema_preflight` itself has no `karr_native_root`
    parameter (it always resolves seed paths against the production
    default root). To keep that existing, unmodified tooling untouched
    while still allowing this diagnostic's tests to point it at a
    `tmp_path` fixture root, temporarily rebind the two path-helper
    functions it calls (`canonical_seed0_path`, `seed_mat_path`) to
    partials pinned to `karr_native_root`, for the duration of one call
    only; restores the originals afterwards regardless of outcome. A no-op
    when `karr_native_root` is None (the real, production call path).
    """
    if karr_native_root is None:
        yield
        return
    original_seed0 = preflight_module.canonical_seed0_path
    original_seed_mat = preflight_module.seed_mat_path
    preflight_module.canonical_seed0_path = functools.partial(canonical_seed0_path, karr_native_root=karr_native_root)
    preflight_module.seed_mat_path = functools.partial(seed_mat_path, karr_native_root=karr_native_root)
    try:
        yield
    finally:
        preflight_module.canonical_seed0_path = original_seed0
        preflight_module.seed_mat_path = original_seed_mat


PROCESS = "DNASupercoiling"
PRIMARY_PROJECTION = ("linkingNumbers.delta_value_sum", "linkingNumbers.delta_nnz")


def validate_extension_seeds(
    seeds: list[int],
    *,
    n_ticks: int = 100,
    karr_native_root: Path | None = None,
) -> dict[str, Any]:
    """Validate every extension seed's trace file structurally, for schema
    drift against canonical seed 0, and for non-vacuity of the primary
    chromosome projection. Never raises for a single bad seed; collects
    every problem into `blockers` so the caller sees the full picture.
    """
    kwargs = {"karr_native_root": karr_native_root} if karr_native_root is not None else {}
    report: dict[str, Any] = {
        "process": PROCESS,
        "seeds": list(seeds),
        "n_ticks": n_ticks,
        "structural": {},
        "schema_preflight": None,
        "non_vacuity": {},
        "blockers": [],
    }

    for seed in seeds:
        path = seed_mat_path(PROCESS, seed, n_ticks=n_ticks, **kwargs)
        result = validate_structural(path, expected_process=PROCESS, expected_seed=seed, expected_n_ticks=n_ticks)
        report["structural"][str(seed)] = result.to_dict()
        if not result.ok:
            report["blockers"].append(f"seed {seed}: structural validation failed: {result.errors}")

    with _schema_preflight_root_override(karr_native_root):
        drift = schema_preflight(PROCESS, seeds, n_ticks=n_ticks)
    report["schema_preflight"] = drift
    if not drift.get("ok"):
        report["blockers"].append(f"schema drift vs seed0: {drift.get('error')}")

    try:
        import _l2_2_design_a_runner_helpers as helpers  # noqa: PLC0415

        oracle = helpers.load_chromosome_oracle_for_process(PROCESS, list(seeds), n_ticks)
        matrix = helpers.chromosome_projection_matrix(
            before_stores=oracle["before_stores"],
            after_stores=oracle["after_stores"],
            projection_spec=PRIMARY_PROJECTION,
        )
        for idx, component in enumerate(PRIMARY_PROJECTION):
            per_seed_nonzero = [int((matrix[seed_idx, :, idx] != 0).sum()) for seed_idx in range(len(seeds))]
            all_zero_seeds = [seeds[i] for i, count in enumerate(per_seed_nonzero) if count == 0]
            report["non_vacuity"][component] = {
                "per_seed_nonzero_ticks": dict(zip((str(s) for s in seeds), per_seed_nonzero)),
                "total_nonzero_ticks": int(sum(per_seed_nonzero)),
                "all_zero_seeds": all_zero_seeds,
            }
            if len(all_zero_seeds) == len(seeds):
                report["blockers"].append(
                    f"non-vacuity: component {component!r} is all-zero across every requested seed"
                )
    except Exception as exc:  # noqa: BLE001
        report["blockers"].append(f"non-vacuity check raised: {exc}")

    report["result"] = "PASS" if not report["blockers"] else "BLOCKED"
    return report
