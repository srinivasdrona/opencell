from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

import l2_2_design_a_runner as runner  # noqa: E402


def _fake_metabolism_oracle(*, seed_count: int = 3, tick_count: int = 4, dim: int = 8) -> dict[str, object]:
    base = np.arange(seed_count * tick_count * dim, dtype=np.float64).reshape(seed_count, tick_count, dim)
    return {
        "process": "Metabolism",
        "oracle_path": runner.runner_helpers._METABOLISM_ORACLE_PATH,
        "canonical_seed_count": seed_count,
        "n_ticks_available": tick_count,
        "before_substrates": base,
        "after_substrates": base + 5.0,
        "before_enzymes": np.ones((seed_count, tick_count, 3), dtype=np.float64),
        "before_bound_enzymes": np.zeros((seed_count, tick_count, 3), dtype=np.float64),
    }


def _fake_metabolism_process(dim: int = 8, enzyme_dim: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        _sub_ids=tuple(f"S{idx}" for idx in range(dim)),
        enzyme_wids=tuple(f"E{idx}" for idx in range(enzyme_dim)),
    )


def test_metabolism_oracle_replay_cheat_fails_primary_channel(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runner.runner_helpers, "load_karr_oracle", lambda process: _fake_metabolism_oracle())
    monkeypatch.setattr(runner.runner_helpers, "_metabolism_process", lambda seed: _fake_metabolism_process())
    monkeypatch.setattr(
        runner.runner_helpers,
        "run_oc_tick",
        lambda process_name, seed, tick, state: {
            "substrates": np.asarray(state["oracle_after_substrates"], dtype=np.float64)
        },
    )

    payload = runner.run_design_a(
        process="Metabolism",
        seeds=[0, 1, 2],
        m_ticks=4,
        out_dir=tmp_path / "metabolism_oracle_laundering",
        thresholds_path=tmp_path / "metabolism_oracle_laundering_thresholds.json",
        bootstrap_B=16,
    )

    result = payload["result"]
    assert result["verdict"] == "FAIL"
    assert result["channels"]["substrates"]["verdict"] == "FAIL"
    assert result["channels"]["substrates"]["w1_oc_vs_karr"] == 0.0
    assert any(
        "PRIMARY_CHANNEL_ORACLE_LAUNDERING" in warning
        for warning in result["warnings"]
    )


def test_metabolism_zero_substrates_cheat_fails_primary_channel(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runner.runner_helpers, "load_karr_oracle", lambda process: _fake_metabolism_oracle())
    monkeypatch.setattr(runner.runner_helpers, "_metabolism_process", lambda seed: _fake_metabolism_process())
    monkeypatch.setattr(
        runner.runner_helpers,
        "run_oc_tick",
        lambda process_name, seed, tick, state: {
            "substrates": np.zeros_like(np.asarray(state["oracle_after_substrates"], dtype=np.float64))
        },
    )

    payload = runner.run_design_a(
        process="Metabolism",
        seeds=[0, 1, 2],
        m_ticks=4,
        out_dir=tmp_path / "metabolism_zero_substrates",
        thresholds_path=tmp_path / "metabolism_zero_substrates_thresholds.json",
        bootstrap_B=16,
    )

    result = payload["result"]
    primary = result["channels"]["substrates"]
    assert result["verdict"] == "FAIL"
    assert primary["verdict"] == "FAIL"
    # NOTE: synthetic _fake_metabolism_oracle uses wide-range Karr values so the
    # null-bootstrap threshold is permissive (~90 on this fixture). The cheat's
    # raw W1 (~52) is still flagged FAIL because n_nonzero_oc==0 < n_nonzero_karr
    # triggers the SUT-produced-nothing-but-Karr-did rejection. Keep the
    # n_nonzero assertions; do not assert W1 > threshold (which would couple this
    # test to the specific synthetic distribution's null spread).
    assert primary["w1_oc_vs_karr"] > 0.0
    assert primary["n_nonzero_oc"] == 0
    assert primary["n_nonzero_karr"] > 0
