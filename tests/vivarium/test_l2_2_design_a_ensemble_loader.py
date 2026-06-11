from __future__ import annotations

import sys
from pathlib import Path

import h5py
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

import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402


def _write_mat_trace(
    path: Path,
    *,
    states_before: dict[str, list[np.ndarray]],
    states_after: dict[str, list[np.ndarray]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as handle:
        refs = handle.create_group("#refs#")
        before_group = handle.create_group("states_before")
        after_group = handle.create_group("states_after")
        handle.create_group("metadata")

        for section_name, section_group, section_values in (
            ("states_before", before_group, states_before),
            ("states_after", after_group, states_after),
        ):
            for channel, tick_vectors in section_values.items():
                dataset = section_group.create_dataset(
                    channel,
                    (1, len(tick_vectors)),
                    dtype=h5py.ref_dtype,
                )
                for tick, vector in enumerate(tick_vectors):
                    ref_ds = refs.create_dataset(
                        f"{section_name}_{channel}_{tick}",
                        data=np.asarray(vector, dtype=np.float64).reshape(1, -1),
                    )
                    dataset[0, tick] = ref_ds.ref


def _metabolism_tick_vectors(seed: int, n_ticks: int = 2) -> tuple[dict[str, list[np.ndarray]], dict[str, list[np.ndarray]]]:
    before = {
        "substrates": [],
        "enzymes": [],
        "boundEnzymes": [],
    }
    after = {"substrates": []}
    for tick in range(n_ticks):
        before["substrates"].append(np.asarray([100 * seed + tick, 100 * seed + tick + 1], dtype=np.float64))
        before["enzymes"].append(np.asarray([10 * seed + tick], dtype=np.float64))
        before["boundEnzymes"].append(np.asarray([seed + tick], dtype=np.float64))
        after["substrates"].append(np.asarray([200 * seed + tick, 200 * seed + tick + 1], dtype=np.float64))
    return before, after


def test_load_v2_ensemble_returns_none_when_no_seeds_present(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runner_helpers, "_REPO_ROOT", tmp_path)

    assert runner_helpers._load_v2_ensemble("Metabolism", max_seeds=3) is None


def test_load_v2_ensemble_loads_single_seed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runner_helpers, "_REPO_ROOT", tmp_path)
    before, after = _metabolism_tick_vectors(seed=0)
    _write_mat_trace(
        tmp_path
        / "data"
        / "m1_sources"
        / "karr_native"
        / "per_process_traces_v2_s000"
        / "Metabolism_100ticks.mat",
        states_before=before,
        states_after=after,
    )

    oracle = runner_helpers._load_v2_ensemble("Metabolism", max_seeds=3)

    assert oracle is not None
    assert oracle["canonical_seed_count"] == 1
    assert oracle["n_ticks_available"] == 2
    assert np.asarray(oracle["before_substrates"]).shape == (1, 2, 2)
    assert np.asarray(oracle["before_enzymes"]).shape == (1, 2, 1)
    assert np.asarray(oracle["before_bound_enzymes"]).shape == (1, 2, 1)
    assert np.asarray(oracle["after_substrates"]).shape == (1, 2, 2)
    assert np.array_equal(np.asarray(oracle["before_substrates"])[0, 1], np.asarray([1.0, 2.0]))
    assert np.array_equal(np.asarray(oracle["after_substrates"])[0, 1], np.asarray([1.0, 2.0]))


def test_load_v2_ensemble_stacks_multiple_present_seeds_in_order(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runner_helpers, "_REPO_ROOT", tmp_path)
    for seed in range(3):
        before, after = _metabolism_tick_vectors(seed=seed)
        _write_mat_trace(
            tmp_path
            / "data"
            / "m1_sources"
            / "karr_native"
            / f"per_process_traces_v2_s{seed:03d}"
            / "Metabolism_100ticks.mat",
            states_before=before,
            states_after=after,
        )

    oracle = runner_helpers._load_v2_ensemble("Metabolism", max_seeds=3)

    assert oracle is not None
    assert oracle["canonical_seed_count"] == 3
    assert np.asarray(oracle["before_substrates"]).shape == (3, 2, 2)
    assert np.asarray(oracle["after_substrates"]).shape == (3, 2, 2)
    assert np.array_equal(np.asarray(oracle["before_substrates"])[0, 0], np.asarray([0.0, 1.0]))
    assert np.array_equal(np.asarray(oracle["before_substrates"])[1, 0], np.asarray([100.0, 101.0]))
    assert np.array_equal(np.asarray(oracle["before_substrates"])[2, 0], np.asarray([200.0, 201.0]))
    assert np.array_equal(np.asarray(oracle["after_substrates"])[2, 1], np.asarray([401.0, 402.0]))


def test_load_ensembles_layout_reads_real_translation_ensemble() -> None:
    oracle = runner_helpers._load_ensembles_layout("Translation", max_seeds=50)

    assert oracle is not None
    assert oracle["canonical_seed_count"] == 50
    assert oracle["oracle_path"] == runner_helpers._ensembles_manifest_path("Translation")
    assert np.asarray(oracle["before_substrates"]).shape[0] == 50
    assert np.asarray(oracle["before_substrates"]).shape[1] == 100
    assert np.asarray(oracle["after_monomers"]).shape[0] == 50
    assert np.asarray(oracle["after_bound_enzymes"]).shape[0] == 50
    assert np.asarray(oracle["before_mrnas"]).shape[0] == 50
    assert "mRNAs" in oracle["ensemble_missing_before_channels"]


def test_load_karr_oracle_uses_v2_loader_when_no_specialized_ensemble_exists(monkeypatch) -> None:
    sentinel = {"process": "Metabolism", "canonical_seed_count": 7}
    monkeypatch.setattr(runner_helpers, "_load_v2_ensemble", lambda process_name, max_seeds=50: sentinel)
    monkeypatch.setattr(runner_helpers, "_load_ensembles_layout", lambda process_name, max_seeds=50: None)

    oracle = runner_helpers.load_karr_oracle("Metabolism")

    assert oracle is sentinel


def test_load_karr_oracle_returns_v2_macromol_without_touching_legacy_loader(monkeypatch) -> None:
    sentinel = {"process": "MacromolecularComplexation", "canonical_seed_count": 50}
    monkeypatch.setattr(runner_helpers, "_load_v2_ensemble", lambda process_name, max_seeds=50: sentinel)
    monkeypatch.setattr(runner_helpers, "_load_ensembles_layout", lambda process_name, max_seeds=50: None)

    oracle = runner_helpers.load_karr_oracle("MacromolecularComplexation")

    assert oracle is sentinel


def test_load_karr_oracle_prefers_richer_specialized_ensemble_over_partial_v2(monkeypatch) -> None:
    partial_v2 = {"process": "Translation", "canonical_seed_count": 1}
    specialized = {"process": "Translation", "canonical_seed_count": 50}
    monkeypatch.setattr(runner_helpers, "_load_v2_ensemble", lambda process_name, max_seeds=50: partial_v2)
    monkeypatch.setattr(runner_helpers, "_load_ensembles_layout", lambda process_name, max_seeds=50: specialized)

    oracle = runner_helpers.load_karr_oracle("Translation")

    assert oracle is specialized


def test_load_karr_oracle_falls_back_to_legacy_with_warning(monkeypatch) -> None:
    monkeypatch.setattr(runner_helpers, "_load_v2_ensemble", lambda process_name, max_seeds=50: None)
    monkeypatch.setattr(runner_helpers, "_load_ensembles_layout", lambda process_name, max_seeds=50: None)

    oracle = runner_helpers.load_karr_oracle("Metabolism")

    assert oracle["canonical_seed_count"] == 1
    assert any("KARR_LEGACY_SINGLE_SEED_FALLBACK" in warning for warning in oracle["warnings"])
