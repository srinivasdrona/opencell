from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from opencell.validation.replay import load_per_process_fixture, replay_one_tick


def _write_replay_fixture(root: Path) -> None:
    payload = {
        "manifest": {
            "n_ticks": 2,
            "process_name": "DemoProcess",
            "snapshot_properties": ["substrates", "enzymes"],
        }
    }
    (root / "DemoProcess.json").write_text(json.dumps(payload), encoding="utf-8")
    np.savez(
        root / "DemoProcess.npz",
        state_before__substrates=np.asarray([[1.0, 2.0], [3.0, 4.0]]),
        state_before__enzymes=np.asarray([[10.0], [20.0]]),
        states_after__substrates=np.asarray([[1.5, 2.5], [3.5, 4.5]]),
        states_after__enzymes=np.asarray([[11.0], [21.0]]),
    )


class _EchoProcess:
    parameters: dict[str, float] = {"time_step": 1.0}

    def __init__(self) -> None:
        self.last_state: dict[str, Any] | None = None

    def next_update(self, timestep: float, state: dict[str, Any]) -> dict[str, Any]:
        self.last_state = state
        return {"substrates": np.asarray(state["substrates"]) + float(timestep)}


def test_replay_loader_strips_state_before_and_states_after_prefixes(tmp_path: Path) -> None:
    _write_replay_fixture(tmp_path)

    fixture = load_per_process_fixture("DemoProcess", root=tmp_path)

    assert fixture.process_name == "DemoProcess"
    assert fixture.n_ticks == 2
    assert sorted(fixture.inputs) == ["enzymes", "substrates"]
    assert sorted(fixture.outputs) == ["enzymes", "substrates"]
    assert fixture.inputs["substrates"].shape == (2, 2)
    assert fixture.outputs["substrates"].shape == (2, 2)


def test_replay_one_tick_uses_prefix_stripped_keys_for_process_ports(tmp_path: Path) -> None:
    _write_replay_fixture(tmp_path)
    fixture = load_per_process_fixture("DemoProcess", root=tmp_path)
    process = _EchoProcess()

    update = replay_one_tick(process, fixture, tick_index=1)

    assert process.last_state is not None
    assert sorted(process.last_state) == ["enzymes", "substrates"]
    np.testing.assert_allclose(process.last_state["substrates"], np.asarray([3.0, 4.0]))
    np.testing.assert_allclose(update["substrates"], np.asarray([4.0, 5.0]))
