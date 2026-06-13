from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


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
import l2_2_design_a_runner as runner  # noqa: E402


_RNA_PRIMARY_PROCESSES = (
    "RNAProcessing",
    "RNAModification",
    "tRNAAminoacylation",
)
_RNA_PRIMARY_CTORS = {
    "RNAProcessing": "_rna_processing_process",
    "RNAModification": "_rna_modification_process",
    "tRNAAminoacylation": "_trna_aminoacylation_process",
}
_RNA_PRIMARY_TICKS = {
    "RNAProcessing": "_run_rna_processing_tick",
    "RNAModification": "_run_rna_modification_tick",
    "tRNAAminoacylation": "_run_trna_aminoacylation_tick",
}


def _fake_rnas_primary_oracle(
    process_name: str,
    *,
    tick_count: int = 4,
    substrate_dim: int = 4,
    enzyme_dim: int = 3,
    rna_dim: int = 6,
) -> dict[str, object]:
    substrate_base = np.arange(tick_count * substrate_dim, dtype=np.float64).reshape(
        1, tick_count, substrate_dim
    )
    rna_base = (
        np.arange(tick_count * rna_dim, dtype=np.float64).reshape(1, tick_count, rna_dim) + 1.0
    )
    return {
        "process": process_name,
        "oracle_path": runner.runner_helpers._METABOLISM_ORACLE_PATH,
        "canonical_seed_count": 1,
        "n_ticks_available": tick_count,
        "before_substrates": substrate_base,
        "before_enzymes": np.ones((1, tick_count, enzyme_dim), dtype=np.float64),
        "before_bound_enzymes": np.zeros((1, tick_count, enzyme_dim), dtype=np.float64),
        "before_rnas": rna_base,
        "after_substrates": substrate_base + 5.0,
        "after_rnas": rna_base + 3.0,
    }


def _fake_rnas_primary_process(
    *,
    substrate_dim: int = 4,
    enzyme_dim: int = 3,
    rna_dim: int = 6,
) -> SimpleNamespace:
    return SimpleNamespace(
        substrate_wids=tuple(f"S{idx}" for idx in range(substrate_dim)),
        enzyme_wids=tuple(f"E{idx}" for idx in range(enzyme_dim)),
        rna_primary_wids=tuple(f"RNA_{idx:03d}" for idx in range(rna_dim)),
    )


@pytest.mark.parametrize("process_name", _RNA_PRIMARY_PROCESSES)
def test_rnas_primary_oracle_laundering_flips_primary_channel(
    process_name: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    oracle = _fake_rnas_primary_oracle(process_name)
    monkeypatch.setattr(runner.runner_helpers, "load_karr_oracle", lambda process: oracle)
    monkeypatch.setattr(
        runner.runner_helpers,
        _RNA_PRIMARY_CTORS[process_name],
        lambda seed: _fake_rnas_primary_process(rna_dim=oracle["after_rnas"].shape[2]),
    )

    def _honest_tick(
        dispatched_process: str,
        seed: int,
        tick: int,
        state: dict[str, object],
    ) -> dict[str, np.ndarray]:
        assert dispatched_process == process_name
        return {
            "substrates": np.asarray(state["oracle_after_substrates"], dtype=np.float64),
            "RNAs": np.zeros_like(np.asarray(state["oracle_after_rnas"], dtype=np.float64)),
        }

    def _cheat_tick(
        dispatched_process: str,
        seed: int,
        tick: int,
        state: dict[str, object],
    ) -> dict[str, np.ndarray]:
        assert dispatched_process == process_name
        return {
            "substrates": np.asarray(state["oracle_after_substrates"], dtype=np.float64),
            "RNAs": np.asarray(state["oracle_after_rnas"], dtype=np.float64),
        }

    monkeypatch.setattr(runner.runner_helpers, "run_oc_tick", _honest_tick)
    honest_payload = runner.run_design_a(
        process=process_name,
        seeds=[0, 1, 2],
        m_ticks=4,
        out_dir=tmp_path / f"{process_name}_honest",
        bootstrap_B=16,
    )

    monkeypatch.setattr(runner.runner_helpers, "run_oc_tick", _cheat_tick)
    cheated_payload = runner.run_design_a(
        process=process_name,
        seeds=[0, 1, 2],
        m_ticks=4,
        out_dir=tmp_path / f"{process_name}_cheated",
        bootstrap_B=16,
    )

    assert honest_payload["result"]["verdict"] == "FAIL"
    assert honest_payload["result"]["channels"]["RNAs"]["verdict"] == "FAIL"
    # Catalog v4 (2026-06-12): tRNAAminoacylation is closed_form_dominant: confirmed,
    # so the runner demotes PRIMARY_CHANNEL_ORACLE_LAUNDERING to informational
    # PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE and does NOT flip the verdict to FAIL.
    # See docs/phase_f/l2_2_design_a/LAUNDERING_VS_CONVERGENCE.md.
    from tests.vivarium.l2_2_design_a_runner import _process_catalog_entry
    closed_form = str(_process_catalog_entry(process_name).get("closed_form_dominant", "false"))
    if closed_form == "confirmed":
        # Cheat path produces an exact-match smoke result on a closed_form_dominant=confirmed
        # process; runner correctly recognizes this as legitimate convergence, not laundering.
        assert any(
            "PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE" in warning
            for warning in cheated_payload["result"]["warnings"]
        ), f"Expected DETERMINISTIC_CONVERGENCE warning for closed_form_dominant=confirmed process {process_name}; got warnings={cheated_payload['result']['warnings']}"
        # No assertion on cheated_payload verdict — it may PASS via convergence.
    else:
        assert cheated_payload["result"]["verdict"] == "FAIL"
        assert cheated_payload["result"]["channels"]["RNAs"]["verdict"] == "FAIL"
        assert any(
            "PRIMARY_CHANNEL_ORACLE_LAUNDERING" in warning
            for warning in cheated_payload["result"]["warnings"]
        )


@pytest.mark.parametrize("process_name", _RNA_PRIMARY_PROCESSES)
def test_rnas_primary_distance_falsifier_rejects_zero_rna_surface(
    process_name: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    oracle = _fake_rnas_primary_oracle(process_name)
    monkeypatch.setattr(runner.runner_helpers, "load_karr_oracle", lambda process: oracle)
    monkeypatch.setattr(
        runner.runner_helpers,
        _RNA_PRIMARY_CTORS[process_name],
        lambda seed: _fake_rnas_primary_process(rna_dim=oracle["after_rnas"].shape[2]),
    )
    monkeypatch.setattr(
        runner.runner_helpers,
        "run_oc_tick",
        lambda dispatched_process, seed, tick, state: {
            "substrates": np.asarray(state["oracle_after_substrates"], dtype=np.float64),
            "RNAs": np.zeros_like(np.asarray(state["oracle_after_rnas"], dtype=np.float64)),
        },
    )

    payload = runner.run_design_a(
        process=process_name,
        seeds=[0, 1, 2],
        m_ticks=4,
        out_dir=tmp_path / f"{process_name}_distance",
        bootstrap_B=16,
    )

    primary = payload["result"]["channels"]["RNAs"]
    assert payload["result"]["verdict"] == "FAIL"
    assert primary["verdict"] == "FAIL"
    assert primary["aggregation"] == "per_tick_vector_w1_mean"
    assert primary["w1_oc_vs_karr"] > 0.0


@pytest.mark.parametrize("process_name", _RNA_PRIMARY_PROCESSES)
def test_rnas_primary_dispatchers_do_not_pass_trace_hint(
    process_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctor = getattr(runner_helpers, _RNA_PRIMARY_CTORS[process_name])
    if hasattr(ctor, "cache_clear"):
        ctor.cache_clear()
    process = ctor(0)
    oracle = runner_helpers.load_karr_oracle(process_name)
    state = {
        "substrate_wids": list(process.substrate_wids),
        "enzyme_wids": list(process.enzyme_wids),
        "rna_wids": list(process.rna_primary_wids),
        "oracle_before_substrates": np.asarray(oracle["before_substrates"], dtype=np.float64)[0, 0],
        "oracle_after_substrates": np.asarray(oracle["after_substrates"], dtype=np.float64)[0, 0],
        "oracle_before_enzymes": np.asarray(oracle["before_enzymes"], dtype=np.float64)[0, 0],
        "oracle_before_bound_enzymes": np.asarray(oracle["before_bound_enzymes"], dtype=np.float64)[0, 0],
        "oracle_before_rnas": np.asarray(oracle["before_rnas"], dtype=np.float64)[0, 0],
        "oracle_after_rnas": np.asarray(oracle["after_rnas"], dtype=np.float64)[0, 0],
    }

    def _raise_on_trace_hint(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"{process_name} dispatcher must not pass trace_hint")

    monkeypatch.setattr(runner_helpers, "overlay_trace_after_hint", _raise_on_trace_hint)
    result = getattr(runner_helpers, _RNA_PRIMARY_TICKS[process_name])(0, 0, state)

    assert "RNAs" in result
    assert np.asarray(result["RNAs"], dtype=np.float64).shape == np.asarray(
        state["oracle_before_rnas"], dtype=np.float64
    ).shape
