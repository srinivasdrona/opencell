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

import l2_2_design_a_runner as runner


def _fake_oracle(*, seed_count: int = 3, tick_count: int = 4, dim: int = 8) -> dict[str, object]:
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


def _fake_process(dim: int = 8, enzyme_dim: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        _sub_ids=tuple(f"S{idx}" for idx in range(dim)),
        enzyme_wids=tuple(f"E{idx}" for idx in range(enzyme_dim)),
    )


def test_constant_zero_oc_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runner.runner_helpers, "load_karr_oracle", lambda process: _fake_oracle())
    monkeypatch.setattr(runner.runner_helpers, "_metabolism_process", lambda seed: _fake_process())
    monkeypatch.setattr(
        runner.runner_helpers,
        "run_oc_tick",
        lambda seed, tick, state: {"substrates": np.zeros_like(state["oracle_after_substrates"])},
    )

    payload = runner.run_design_a(
        process="Metabolism",
        seeds=[0, 1, 2],
        m_ticks=4,
        out_dir=tmp_path,
        thresholds_path=tmp_path / "thresholds.json",
        bootstrap_B=16,
    )

    assert payload["result"]["verdict"] == "FAIL"
    assert payload["result"]["channels"]["substrates"]["verdict"] == "FAIL"


def test_oracle_laundering_warns(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runner.runner_helpers, "load_karr_oracle", lambda process: _fake_oracle())
    monkeypatch.setattr(runner.runner_helpers, "_metabolism_process", lambda seed: _fake_process())
    monkeypatch.setattr(
        runner.runner_helpers,
        "run_oc_tick",
        lambda seed, tick, state: {"substrates": np.asarray(state["oracle_after_substrates"], dtype=np.float64)},
    )

    payload = runner.run_design_a(
        process="Metabolism",
        seeds=[0, 1, 2],
        m_ticks=4,
        out_dir=tmp_path,
        thresholds_path=tmp_path / "thresholds.json",
        bootstrap_B=16,
    )

    assert any("TRIVIAL_RNG_LEAK" in warning for warning in payload["result"]["warnings"])


def test_off_by_one_seed_caught(monkeypatch, tmp_path: Path) -> None:
    oracle = _fake_oracle(seed_count=4)
    monkeypatch.setattr(runner.runner_helpers, "load_karr_oracle", lambda process: oracle)
    monkeypatch.setattr(runner.runner_helpers, "_metabolism_process", lambda seed: _fake_process())

    def _shifted_seed(seed: int, tick: int, state: dict[str, object]) -> dict[str, np.ndarray]:
        next_seed = (int(seed) + 1) % state["oracle_after_all"].shape[0]
        return {
            "substrates": np.asarray(state["oracle_after_all"][next_seed, tick], dtype=np.float64),
        }

    monkeypatch.setattr(runner.runner_helpers, "run_oc_tick", _shifted_seed)

    payload = runner.run_design_a(
        process="Metabolism",
        seeds=[0, 1, 2],
        m_ticks=4,
        out_dir=tmp_path,
        thresholds_path=tmp_path / "thresholds.json",
        bootstrap_B=16,
    )

    assert payload["result"]["verdict"] == "FAIL" or any(
        "SEED_ALIGNMENT_MISMATCH" in warning for warning in payload["result"]["warnings"]
    )
