from __future__ import annotations

import numpy as np
import pytest

from opencell.validation.karr_trajectory import load_karr_trajectory
from opencell.validation.trajectory_compare import compare_trajectories


def _load_or_skip(max_time_s: float = 1000.0) -> dict:
    try:
        return load_karr_trajectory(max_time_s=max_time_s)
    except FileNotFoundError as exc:
        pytest.skip(f"Karr trajectory fixture unavailable: {exc}")


def test_karr_trajectory_loader_smoke() -> None:
    traj = _load_or_skip()
    assert "metadata" in traj
    assert "time_s" in traj
    assert "observables" in traj

    required = {
        "cell_dry_mass_g",
        "replication_state_code",
        "fork_position_norm",
        "mrna_total_count_estimate",
        "protein_total_count_estimate",
        "atp_pool",
        "gtp_pool",
        "dntp_pool_total",
        "division_event_timestamp_s",
    }
    assert required.issubset(set(traj["observables"]))


def test_karr_trajectory_loader_shapes_are_consistent() -> None:
    traj = _load_or_skip()
    n = len(np.asarray(traj["time_s"]))
    assert n > 0
    for values in traj["observables"].values():
        arr = np.asarray(values)
        assert arr.shape[0] == n
        assert np.all(np.isfinite(arr) | np.isnan(arr))


def test_compare_trajectories_returns_expected_keys() -> None:
    traj = _load_or_skip(max_time_s=300.0)
    result = compare_trajectories(traj, traj)

    assert set(result) == {
        "n_timepoints_compared",
        "shared_observables",
        "observable_errors",
        "phenotype_scalar_diff",
        "summary",
    }
    assert result["n_timepoints_compared"] > 0
    assert len(result["shared_observables"]) > 0
    for obs in result["shared_observables"]:
        assert obs in result["observable_errors"]
