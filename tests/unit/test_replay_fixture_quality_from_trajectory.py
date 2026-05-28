from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_ROOT = _REPO_ROOT / "data" / "karr_fixtures" / "per_process_replay"
_PROCESSES = (
    "Transcription",
    "Translation",
    "RNADecay",
    "Replication",
    "ReplicationInitiation",
)


@pytest.mark.trajectory_derived
@pytest.mark.parametrize("process_name", _PROCESSES)
def test_trajectory_fixture_exists_and_has_valid_shapes(process_name: str) -> None:
    path = _FIXTURE_ROOT / f"{process_name}_from_trajectory.npz"
    assert path.exists(), f"Missing trajectory-derived fixture: {path}"

    with np.load(path, allow_pickle=True) as payload:
        before_keys = sorted(key for key in payload.files if key.startswith("state_before__"))
        assert before_keys, "Expected at least one state_before__<prop> array."

        first_shape: tuple[int, ...] | None = None
        for before_key in before_keys:
            prop = before_key.removeprefix("state_before__")
            after_key = f"states_after__{prop}"
            assert after_key in payload.files, f"Missing paired output key: {after_key}"

            before = np.asarray(payload[before_key])
            after = np.asarray(payload[after_key])
            assert before.shape == after.shape, f"Shape mismatch for property {prop}"
            assert before.ndim == 3, f"Expected 3D tick-series for {before_key}, got {before.shape}"
            assert before.shape[1] == 1, f"Expected singleton middle axis for {before_key}"
            assert before.shape[0] > 0, f"Expected at least one replay pair for {before_key}"
            assert np.issubdtype(before.dtype, np.number), f"Non-numeric dtype for {before_key}"
            assert np.issubdtype(after.dtype, np.number), f"Non-numeric dtype for {after_key}"
            assert np.all(np.isfinite(before)), f"Non-finite values in {before_key}"
            assert np.all(np.isfinite(after)), f"Non-finite values in {after_key}"

            if first_shape is None:
                first_shape = before.shape
            else:
                assert before.shape[0] == first_shape[0], "All channels must share n_pairs."

        substrate_before = np.asarray(payload["state_before__substrates"])
        substrate_after = np.asarray(payload["states_after__substrates"])
        max_abs_diff = float(np.max(np.abs(substrate_after - substrate_before)))
        assert max_abs_diff > 0.0, "Expected non-trivial substrate delta in trajectory-derived replay."

        assert "metadata" in payload.files, "Expected metadata payload."
        metadata = payload["metadata"].item()
        assert metadata["source"] == "trajectory"
        assert metadata["process_name"] == process_name
        n_snapshots = int(metadata["n_snapshots"])
        effective_dt_sec = list(metadata["effective_dt_sec"])
        assert n_snapshots >= 2
        assert len(effective_dt_sec) == n_snapshots - 1
        assert substrate_before.shape[0] == n_snapshots - 1
