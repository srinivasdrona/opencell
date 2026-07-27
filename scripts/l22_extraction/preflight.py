"""Schema-preflight + loader-compatibility checks, reusing the existing
Design-A oracle loader (`tests/vivarium/_l2_2_design_a_runner_helpers.py`)
rather than re-implementing schema-drift detection or seed-stacking logic.

Two things this module answers, both required by the L2.2 full-extraction
task before any long MATLAB run is allowed to proceed:

1. `schema_preflight(process, seeds)` -- does a freshly generated seed's MAT
   schema (channel key set + per-channel widths) match the canonical seed-0
   schema for this process? Uses the loader's own
   `_seed_schema_preflight`, so "passes preflight" and "loads without the
   generic v2 loader's ValueError" are, by construction, the same check.
2. `loader_report(process)` -- what does the real (unmocked)
   `load_karr_oracle(process)` report for `canonical_seed_count` and
   `warnings`? Used both to confirm specialized Transcription/Translation
   ensembles are healthy (50 seeds, no drift) and, after the full run, to
   confirm every production process reaches `canonical_seed_count == 50`
   with no `KARR_SINGLE_SEED_REUSED` warning.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
_VIVARIUM_TESTS = REPO_ROOT / "tests" / "vivarium"
if str(_VIVARIUM_TESTS) not in sys.path:
    sys.path.insert(0, str(_VIVARIUM_TESTS))

from scripts.l22_extraction.launcher import canonical_seed0_path, seed_mat_path  # noqa: E402


def _helpers():
    import _l2_2_design_a_runner_helpers as helpers  # noqa: PLC0415

    return helpers


def schema_preflight(process: str, seeds: list[int], *, n_ticks: int = 100) -> dict[str, Any]:
    """Compare `process`'s canonical seed-0 schema against every seed in `seeds`.

    Returns `{"ok": True}` on a clean match, or `{"ok": False, "error": ...}`
    naming the exact offending file/channel (as raised by the loader's own
    `_seed_schema_preflight`) on drift. Never raises -- callers (the Phase 2
    preflight report and its tests) need a structured result, not an
    exception, so one process's drift does not abort the whole audit.
    """
    helpers = _helpers()
    seed0 = canonical_seed0_path(process, n_ticks=n_ticks)
    paths = [seed0]
    for seed in seeds:
        if seed == 0:
            continue
        paths.append(seed_mat_path(process, seed, n_ticks=n_ticks))
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        return {"ok": False, "error": f"missing file(s) for schema preflight: {missing}"}
    try:
        helpers._seed_schema_preflight(paths, process_name=process)  # noqa: SLF001
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "paths": [str(p) for p in paths]}
    return {"ok": True, "paths": [str(p) for p in paths]}


def loader_report(process: str) -> dict[str, Any]:
    """Real, unmocked `load_karr_oracle(process)` dispatch summary."""
    helpers = _helpers()
    try:
        oracle = helpers.load_karr_oracle(process)
        return {
            "ok": True,
            "canonical_seed_count": int(oracle.get("canonical_seed_count", 0)),
            "n_ticks_available": int(oracle.get("n_ticks_available", 0)),
            "oracle_path": str(oracle.get("oracle_path")),
            "warnings": list(oracle.get("warnings", ()) or ()),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
