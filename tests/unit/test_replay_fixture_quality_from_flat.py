from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_ROOT = _REPO_ROOT / "data" / "karr_fixtures" / "per_process_replay"
_PROCESSES = (
    "Replication",
    "ReplicationInitiation",
    "ChromosomeCondensation",
    "DnaSupercoiling",
)
_EXPECTED_PARAM_KEY = {
    "Replication": "dnaPolymeraseElongationRate",
    "ReplicationInitiation": "kb1ATP",
    "ChromosomeCondensation": "smcSepNt",
    "DnaSupercoiling": "gyraseActivityRate",
}


@pytest.mark.parametrize("process_name", _PROCESSES)
def test_flat_fixture_exists_and_has_snapshot_schema(process_name: str) -> None:
    path = _FIXTURE_ROOT / f"{process_name}_from_flat.npz"
    assert path.exists(), f"Missing flat-derived fixture: {path}"

    with np.load(path, allow_pickle=True) as payload:
        assert "metadata" in payload.files, "Expected metadata payload."
        metadata = payload["metadata"].item()
        assert metadata["source"] == "flat"
        assert metadata["oracle_kind"] == "snapshot_state"
        assert metadata["process_name"] == process_name

        assert "initial__substrates" in payload.files
        substrates = np.asarray(payload["initial__substrates"])
        assert substrates.size > 0, "Expected non-empty substrate snapshot."

        assert "initial__enzymes" in payload.files
        enzymes = np.asarray(payload["initial__enzymes"])
        assert enzymes.size > 0, "Expected non-empty enzyme snapshot."

        has_chromosome_struct = "initial__chromosome" in payload.files
        has_chromosome_prefix = any(
            key.startswith("initial__chromosome__") for key in payload.files
        )
        assert has_chromosome_struct or has_chromosome_prefix, "Missing chromosome snapshot payload."

        assert "params" in payload.files, "Expected params payload."
        params = payload["params"].item()
        assert isinstance(params, dict), "Expected params to deserialize as dict."
        expected_key = _EXPECTED_PARAM_KEY[process_name]
        assert expected_key in params, f"Expected process-specific param '{expected_key}' in params."
