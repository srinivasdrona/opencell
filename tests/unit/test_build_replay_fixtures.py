from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.io import savemat

from scripts.build_replay_fixtures import build_replay_fixture


def _cell(values: list[np.ndarray]) -> np.ndarray:
    out = np.empty((len(values), 1), dtype=object)
    for idx, value in enumerate(values):
        out[idx, 0] = np.asarray(value)
    return out


def test_build_replay_fixture_stacks_ticks_and_skips_variable_shapes(
    tmp_path: Path,
    capsys,
) -> None:
    mat_path = tmp_path / "Demo_100ticks.mat"
    before_a = [np.array([1.0, 2.0]), np.array([3.0, 4.0]), np.array([5.0, 6.0])]
    after_a = [np.array([10.0, 20.0]), np.array([30.0, 40.0]), np.array([50.0, 60.0])]
    varying = [np.array([1.0]), np.array([2.0, 3.0]), np.array([4.0])]

    savemat(
        mat_path,
        {
            "states_before": {"good": _cell(before_a), "varying": _cell(varying)},
            "states_after": {"good": _cell(after_a), "varying": _cell(varying)},
            "metadata": {
                "n_ticks": 3,
                "process_name": "Demo",
                "rng_seed": 0,
                "snapshot_properties": ["good", "varying"],
            },
        },
        do_compression=True,
    )

    process_name, n_props, n_ticks, npz_path = build_replay_fixture(mat_path, output_root=tmp_path)

    assert process_name == "Demo"
    assert n_ticks == 3
    assert n_props == 2
    assert npz_path.exists()
    assert (tmp_path / "Demo.json").exists()

    with np.load(npz_path, allow_pickle=False) as data:
        assert "state_before__good" in data.files
        assert "states_after__good" in data.files
        assert "state_before__varying" not in data.files
        assert "states_after__varying" not in data.files
        assert data["state_before__good"].shape == (3, 2)
        assert data["states_after__good"].shape == (3, 2)

    payload = json.loads((tmp_path / "Demo.json").read_text(encoding="utf-8"))
    assert payload["manifest"]["n_ticks"] == 3

    output = capsys.readouterr().out
    assert "variable tick shapes" in output
