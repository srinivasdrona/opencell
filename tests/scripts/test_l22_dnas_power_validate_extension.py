"""Targeted tests for scripts/l22_dnas_power/validate_extension.py.

Structural/schema-drift checks are exercised against real synthetic MAT
fixtures (`write_synthetic_trace`, same as the rest of the L2.2 extraction
test suite). The chromosome non-vacuity step depends on the real sparse-
triple HDF5 chromosome layout, which is not reproduced by
`write_synthetic_trace`; it is instead exercised by monkeypatching
`_l2_2_design_a_runner_helpers.load_chromosome_oracle_for_process` /
`chromosome_projection_matrix` at the point of use inside
`validate_extension` (same monkeypatch-at-point-of-use convention as
`tests/scripts/test_l22_report_final.py`), so the counting/blocker logic is
verified without needing to fake the full HDF5 chromosome format.

Run via `bin\\oc-pytest tests/scripts/test_l22_dnas_power_validate_extension.py -v`.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
_VIVARIUM_TESTS = REPO_ROOT / "tests" / "vivarium"
if str(_VIVARIUM_TESTS) not in sys.path:
    sys.path.insert(0, str(_VIVARIUM_TESTS))

import scripts.l22_dnas_power.validate_extension as validate_extension  # noqa: E402
from scripts.l22_extraction.launcher import seed_mat_path  # noqa: E402
from tests.scripts._l22_fixtures import write_synthetic_trace  # noqa: E402


def _install_fake_chromosome_helpers(monkeypatch, *, projection_matrix: np.ndarray):
    """Install a fake `_l2_2_design_a_runner_helpers` module (with just the
    two functions `validate_extension_seeds` calls) into `sys.modules`, so
    the `import _l2_2_design_a_runner_helpers as helpers` inside
    `validate_extension_seeds` resolves to this fake instead of the real
    module (which would otherwise require real chromosome HDF5 data)."""
    fake = types.ModuleType("_l2_2_design_a_runner_helpers")
    fake.load_chromosome_oracle_for_process = lambda process, seeds, n_ticks: {
        "process": process,
        "before_stores": [[None] * n_ticks for _ in seeds],
        "after_stores": [[None] * n_ticks for _ in seeds],
    }
    fake.chromosome_projection_matrix = lambda **kwargs: projection_matrix
    # `scripts.l22_extraction.preflight._helpers()` does its own
    # `import _l2_2_design_a_runner_helpers as helpers` and will resolve to
    # this same sys.modules entry; give it a trivial always-passes
    # `_seed_schema_preflight` since schema-drift logic itself is out of
    # scope for this test file (this test only covers
    # `validate_extension_seeds`'s own blocker-aggregation wiring).
    fake._seed_schema_preflight = lambda paths, process_name: None
    monkeypatch.setitem(sys.modules, "_l2_2_design_a_runner_helpers", fake)


def test_validate_extension_seeds_passes_for_well_formed_traces(tmp_path, monkeypatch):
    seeds = [50, 51]
    for seed in seeds:
        write_synthetic_trace(
            seed_mat_path(validate_extension.PROCESS, seed, karr_native_root=tmp_path),
            process_name=validate_extension.PROCESS,
            seed=seed,
            n_ticks=100,
        )
    write_synthetic_trace(
        (tmp_path / "per_process_traces_v2" / f"{validate_extension.PROCESS}_100ticks.mat"),
        process_name=validate_extension.PROCESS,
        seed=0,
        n_ticks=100,
    )
    # Two components, non-zero on every (seed, tick) -> non-vacuous on both.
    projection_matrix = np.ones((len(seeds), 100, 2), dtype=np.float64)
    _install_fake_chromosome_helpers(monkeypatch, projection_matrix=projection_matrix)

    report = validate_extension.validate_extension_seeds(seeds, karr_native_root=tmp_path)

    assert report["result"] == "PASS", report["blockers"]
    assert report["blockers"] == []
    assert report["schema_preflight"]["ok"] is True


def test_validate_extension_seeds_flags_missing_file(tmp_path, monkeypatch):
    seeds = [50, 51]
    write_synthetic_trace(
        seed_mat_path(validate_extension.PROCESS, 50, karr_native_root=tmp_path),
        process_name=validate_extension.PROCESS,
        seed=50,
        n_ticks=100,
    )
    # Seed 51 deliberately never written.
    write_synthetic_trace(
        (tmp_path / "per_process_traces_v2" / f"{validate_extension.PROCESS}_100ticks.mat"),
        process_name=validate_extension.PROCESS,
        seed=0,
        n_ticks=100,
    )
    _install_fake_chromosome_helpers(monkeypatch, projection_matrix=np.ones((len(seeds), 100, 2)))

    report = validate_extension.validate_extension_seeds(seeds, karr_native_root=tmp_path)

    assert report["result"] == "BLOCKED"
    assert any("structural validation failed" in b for b in report["blockers"])
    assert report["structural"]["51"]["ok"] is False


def test_validate_extension_seeds_flags_all_zero_component_as_vacuous(tmp_path, monkeypatch):
    seeds = [50, 51]
    for seed in seeds:
        write_synthetic_trace(
            seed_mat_path(validate_extension.PROCESS, seed, karr_native_root=tmp_path),
            process_name=validate_extension.PROCESS,
            seed=seed,
            n_ticks=100,
        )
    write_synthetic_trace(
        (tmp_path / "per_process_traces_v2" / f"{validate_extension.PROCESS}_100ticks.mat"),
        process_name=validate_extension.PROCESS,
        seed=0,
        n_ticks=100,
    )
    # component 0 all-zero across every seed/tick -> vacuous; component 1 fine.
    projection_matrix = np.ones((len(seeds), 100, 2), dtype=np.float64)
    projection_matrix[:, :, 0] = 0.0
    _install_fake_chromosome_helpers(monkeypatch, projection_matrix=projection_matrix)

    report = validate_extension.validate_extension_seeds(seeds, karr_native_root=tmp_path)

    assert report["result"] == "BLOCKED"
    assert any("all-zero across every requested seed" in b for b in report["blockers"])
    component_0 = validate_extension.PRIMARY_PROJECTION[0]
    assert report["non_vacuity"][component_0]["all_zero_seeds"] == seeds
