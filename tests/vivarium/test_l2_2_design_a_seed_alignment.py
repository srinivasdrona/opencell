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


def _synthetic_metabolism_vectors(
    *,
    seed_count: int = 50,
    tick_count: int = 10,
    dim: int = 5,
) -> np.ndarray:
    rng = np.random.default_rng(20260611)
    return np.asarray(rng.random((seed_count, tick_count, dim)) * 0.1, dtype=np.float64)


def _synthetic_metabolism_oracle(karr_vectors: np.ndarray) -> dict[str, object]:
    seed_count, tick_count, _ = karr_vectors.shape
    return {
        "process": "Metabolism",
        "oracle_path": runner.runner_helpers._METABOLISM_ORACLE_PATH,
        "canonical_seed_count": int(seed_count),
        "n_ticks_available": int(tick_count),
        "before_substrates": np.zeros_like(karr_vectors, dtype=np.float64),
        "after_substrates": np.asarray(karr_vectors, dtype=np.float64),
        "before_enzymes": np.ones((seed_count, tick_count, 3), dtype=np.float64),
        "before_bound_enzymes": np.zeros((seed_count, tick_count, 3), dtype=np.float64),
    }


def _fake_metabolism_process(dim: int = 5, enzyme_dim: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        _sub_ids=tuple(f"S{idx}" for idx in range(dim)),
        enzyme_wids=tuple(f"E{idx}" for idx in range(enzyme_dim)),
    )


def _run_synthetic_metabolism_case(
    monkeypatch,
    tmp_path: Path,
    *,
    oc_vectors: np.ndarray,
    karr_vectors: np.ndarray,
) -> dict[str, object]:
    oracle = _synthetic_metabolism_oracle(karr_vectors)
    monkeypatch.setattr(runner.runner_helpers, "load_karr_oracle", lambda process: oracle)
    monkeypatch.setattr(
        runner.runner_helpers,
        "_metabolism_process",
        lambda seed: _fake_metabolism_process(dim=int(karr_vectors.shape[2])),
    )
    monkeypatch.setattr(
        runner.runner_helpers,
        "run_oc_tick",
        lambda process_name, seed, tick, state: {
            "substrates": np.asarray(oc_vectors[int(seed), int(tick)], dtype=np.float64),
        },
    )
    return runner.run_design_a(
        process="Metabolism",
        seeds=list(range(int(karr_vectors.shape[0]))),
        m_ticks=int(karr_vectors.shape[1]),
        out_dir=tmp_path,
        thresholds_path=tmp_path / "thresholds.json",
        bootstrap_B=8,
    )


def test_seed_alignment_diagnostic_does_not_flip_process_verdict(monkeypatch, tmp_path: Path) -> None:
    karr_vectors = _synthetic_metabolism_vectors()
    oc_vectors = np.roll(karr_vectors, shift=-1, axis=0)

    payload = _run_synthetic_metabolism_case(
        monkeypatch,
        tmp_path,
        oc_vectors=oc_vectors,
        karr_vectors=karr_vectors,
    )

    assert payload["result"]["verdict"] == "PASS"
    assert any(
        "SEED_ALIGNMENT_DIAGNOSTIC" in warning for warning in payload["result"]["warnings"]
    )
    assert not any(
        "SEED_ALIGNMENT_MISMATCH" in warning for warning in payload["result"]["warnings"]
    )


def test_seed_alignment_warning_returns_none_when_diagonal_is_best() -> None:
    karr_vectors = _synthetic_metabolism_vectors()

    warning = runner._seed_alignment_warning(
        channel_name="substrates",
        oc_vectors=karr_vectors.copy(),
        karr_vectors=karr_vectors,
    )

    assert warning is None
