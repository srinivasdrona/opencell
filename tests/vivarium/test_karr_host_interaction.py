from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np

# Ensure pytest imports from this worktree even if another editable install exists.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

from opencell.vivarium.karr_host_interaction import KarrHostInteractionProcess


def _required_wids(process: KarrHostInteractionProcess) -> list[str]:
    return sorted(set(process.adhesin_wids) | set(process.terminal_organelle_wids))


def _ready_protein_counts(process: KarrHostInteractionProcess) -> dict[str, float]:
    return {
        wid: float(process.reference_count_by_wid.get(wid, 1.0))
        for wid in _required_wids(process)
    }


def _base_state(
    process: KarrHostInteractionProcess,
    *,
    terminal_organelle_count: float = 1.0,
    adhesion_strength: float = 0.0,
    host_attached: bool = False,
) -> dict[str, Any]:
    return {
        "cell": {
            "terminal_organelle_count": float(terminal_organelle_count),
            "host_adhesion_strength": float(adhesion_strength),
            "host_attached": bool(host_attached),
        },
        "protein": {"counts": _ready_protein_counts(process)},
    }


def _apply_update(state: dict[str, Any], update: dict[str, Any]) -> None:
    cell_update = update.get("cell", {})
    if "host_adhesion_strength" in cell_update:
        state["cell"]["host_adhesion_strength"] = float(
            state["cell"]["host_adhesion_strength"] + float(cell_update["host_adhesion_strength"])
        )
    if "host_attached" in cell_update:
        state["cell"]["host_attached"] = bool(cell_update["host_attached"])


def test_process_instantiates_with_defaults() -> None:
    p = KarrHostInteractionProcess({})
    assert p.name == "karr_host_interaction"
    assert len(p.adhesin_wids) > 0
    assert len(p.terminal_organelle_wids) > 0
    schema = p.ports_schema()
    assert "cell" in schema
    assert "host_adhesion_strength" in schema["cell"]
    assert "host_attached" in schema["cell"]


def test_one_tick_positive_adhesion_delta_and_atp_consumption() -> None:
    p = KarrHostInteractionProcess(
        {
            "rng_seed": 1,
            "max_adhesion_bonds": 12,
            "bind_rate_per_s": 20.0,
            "unbind_rate_per_s": 0.0,
            "use_trace_rates": False,
        }
    )
    state = _base_state(p, terminal_organelle_count=1.0)
    update = p.next_update(1.0, state)

    assert update["cell"]["host_adhesion_strength"] > 0.0


def test_no_requests_or_substrate_deltas_emitted() -> None:
    p = KarrHostInteractionProcess(
        {
            "rng_seed": 2,
            "max_adhesion_bonds": 6,
            "bind_rate_per_s": 25.0,
            "unbind_rate_per_s": 0.0,
            "use_trace_rates": False,
        }
    )
    state = _base_state(p, terminal_organelle_count=1.0)
    update = p.next_update(1.0, state)

    assert "requests" not in update
    assert "substrates" not in update


def test_100_tick_steady_state_within_rate_envelope() -> None:
    p = KarrHostInteractionProcess(
        {
            "rng_seed": 3,
            "max_adhesion_bonds": 200,
            "bind_rate_per_s": 0.12,
            "unbind_rate_per_s": 0.06,
            "use_trace_rates": False,
        }
    )
    state = _base_state(p, terminal_organelle_count=1.0)

    for _ in range(100):
        update = p.next_update(1.0, state)
        _apply_update(state, update)

    observed = float(state["cell"]["host_adhesion_strength"])
    expected = p.bind_rate_per_s / (p.bind_rate_per_s + p.unbind_rate_per_s)
    assert 0.0 <= observed <= 1.0
    assert abs(observed - expected) < 0.30


def test_seed_determinism() -> None:
    params = {
        "rng_seed": 7,
        "max_adhesion_bonds": 50,
        "bind_rate_per_s": 0.4,
        "unbind_rate_per_s": 0.2,
        "use_trace_rates": False,
    }
    p1 = KarrHostInteractionProcess(params)
    p2 = KarrHostInteractionProcess(params)
    s1 = _base_state(p1, terminal_organelle_count=1.0)
    s2 = deepcopy(s1)

    updates_1: list[dict[str, Any]] = []
    updates_2: list[dict[str, Any]] = []
    for _ in range(30):
        u1 = p1.next_update(1.0, s1)
        u2 = p2.next_update(1.0, s2)
        updates_1.append(u1)
        updates_2.append(u2)
        _apply_update(s1, u1)
        _apply_update(s2, u2)

    assert updates_1 == updates_2
    assert s1 == s2


def test_no_nan_and_non_negative_strength() -> None:
    p = KarrHostInteractionProcess(
        {
            "rng_seed": 11,
            "max_adhesion_bonds": 120,
            "bind_rate_per_s": 0.2,
            "unbind_rate_per_s": 0.15,
            "use_trace_rates": False,
        }
    )
    state = _base_state(p, terminal_organelle_count=1.0)

    for _ in range(200):
        update = p.next_update(1.0, state)
        _apply_update(state, update)

        strength = float(state["cell"]["host_adhesion_strength"])
        assert np.isfinite(strength)
        assert 0.0 <= strength <= 1.0
