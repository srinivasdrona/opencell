"""Tests for ProteinTranslocation full-vector (2892 positions) Design-A replay contract.

Prevents compartment-sum collapse from laundering cytosol-to-membrane/extracellular
translocation movement in L2.2 evidence runs.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

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

from tests.vivarium._l2_2_design_a_runner_helpers import (
    _load_v2_ensemble,
    _project_protein_translocation_monomer_cube,
    _protein_translocation_process,
    _run_protein_translocation_tick,
)
from tests.vivarium.l2_2_design_a_runner import (
    _observable_wids,
    run_design_a,
)


def _verify_translocation_monomer_adapter(adapter_fn: Any) -> None:
    """Verifier: assert that a ProteinTranslocation monomer cube adapter preserves full 2892

    positions and does not collapse or sum across compartments.
    """
    n_ticks = 2
    n_comps = 6
    n_wids = 482
    flat_len = n_comps * n_wids

    trace_cytosol = np.zeros((n_ticks, flat_len), dtype=np.float64)
    trace_membrane = np.zeros((n_ticks, flat_len), dtype=np.float64)

    wid_idx = 10
    comp_c = 0
    comp_m = 3

    trace_cytosol[0, comp_c * n_wids + wid_idx] = 1.0
    trace_membrane[0, comp_m * n_wids + wid_idx] = 1.0

    # Ensure preconditions: per-WID summed totals are identical
    totals_c = trace_cytosol.reshape(n_ticks, n_comps, n_wids).sum(axis=1)
    totals_m = trace_membrane.reshape(n_ticks, n_comps, n_wids).sum(axis=1)
    if not np.array_equal(totals_c, totals_m):
        raise ValueError("Precondition failed: summed totals must be identical")

    out_c = np.asarray(adapter_fn(trace_cytosol), dtype=np.float64)
    out_m = np.asarray(adapter_fn(trace_membrane), dtype=np.float64)

    if out_c.shape[-1] != 2892:
        raise AssertionError(
            f"Adapter output width must be 2892, got {out_c.shape[-1]} (collapsed projection detected)"
        )

    if np.array_equal(out_c, out_m):
        raise AssertionError(
            "Adapter output is identical for cytosol vs membrane positions; compartment movement was laundered"
        )

    if out_c[0, comp_c * n_wids + wid_idx] != 1.0 or out_c[0, comp_m * n_wids + wid_idx] != 0.0:
        raise AssertionError("Adapter corrupted cytosol compartment position")
    if out_m[0, comp_c * n_wids + wid_idx] != 0.0 or out_m[0, comp_m * n_wids + wid_idx] != 1.0:
        raise AssertionError("Adapter corrupted membrane compartment position")


def _planted_collapsed_sum_adapter(values: np.ndarray) -> np.ndarray:
    """Planted mutation: mimics the buggy (ticks, 6, 482).sum(axis=1) adapter."""
    arr = np.asarray(values, dtype=np.float64)
    if arr.ndim == 2 and arr.shape[-1] == 2892:
        arr = arr.reshape(arr.shape[0], 6, 482)
    return arr.sum(axis=1, dtype=np.float64)


def test_contract_1_translocation_adapter_preserves_2892_compartment_positions() -> None:
    """Contract 1: A synthetic six-compartment vector with one copy moving from cytosol

    to membrane for the same WID has identical 482-WID summed totals but MUST remain
    observably different after the ProteinTranslocation oracle adapter.
    Adapter output width must be exactly 2892 and preserve compartment position/order.
    """
    _verify_translocation_monomer_adapter(_project_protein_translocation_monomer_cube)


def test_contract_2_load_v2_ensemble_returns_2892_monomer_vectors() -> None:
    """Contract 2: _load_v2_ensemble('ProteinTranslocation', max_seeds=1) must return

    before_monomers and after_monomers with last dimension 2892, not 482.
    """
    ens = _load_v2_ensemble("ProteinTranslocation", max_seeds=1)
    assert ens is not None, "Failed to load ProteinTranslocation v2 ensemble"
    before_m = ens.get("before_monomers")
    after_m = ens.get("after_monomers")

    assert before_m is not None, "Missing before_monomers in ensemble dict"
    assert after_m is not None, "Missing after_monomers in ensemble dict"

    assert before_m.shape[-1] == 2892, (
        f"before_monomers last dimension must be 2892, got {before_m.shape[-1]}"
    )
    assert after_m.shape[-1] == 2892, (
        f"after_monomers last dimension must be 2892, got {after_m.shape[-1]}"
    )


def test_contract_3_run_protein_translocation_tick_preserves_non_authority_monomers() -> None:
    """Contract 3: _run_protein_translocation_tick given a full 2892 oracle_before_monomers

    vector must return a 2892 monomers vector and preserve all non-authority positions
    while applying the real authority movement.
    """
    proc = _protein_translocation_process(0)
    wids = _observable_wids("ProteinTranslocation", proc)
    m_wids = list(proc.monomer_wids)
    assert len(m_wids) == 482

    # Choose an authority WID (e.g. MG_014_MONOMER)
    auth_wid = "MG_014_MONOMER"
    assert auth_wid in proc.translocatable_wids
    auth_idx = m_wids.index(auth_wid)

    # Choose non-authority WIDs (not translocatable by ProteinTranslocation)
    non_auth_wids = [w for w in m_wids if w not in proc.translocatable_wids]
    assert len(non_auth_wids) >= 2
    non_auth_idx_1 = m_wids.index(non_auth_wids[0])
    non_auth_idx_2 = m_wids.index(non_auth_wids[1])

    # 6 compartments in Karr order: 0: c, 1: d, 2: e, 3: m, 4: tc, 5: tm
    comp_c = 0
    comp_m = 3

    # Build full 2892 vector
    before_monomers = np.zeros(6 * 482, dtype=np.float64)
    # 1 copy of translocatable monomer in cytosol
    before_monomers[comp_c * 482 + auth_idx] = 1.0
    # Plant non-authority monomers with distinct counts in cytosol and membrane
    before_monomers[comp_c * 482 + non_auth_idx_1] = 7.0
    before_monomers[comp_m * 482 + non_auth_idx_2] = 13.0

    state = {
        "substrate_wids": wids["substrates"],
        "enzyme_wids": wids["enzymes"],
        "monomer_wids": wids["monomers"],
        "oracle_before_substrates": np.full(len(wids["substrates"]), 1000.0, dtype=np.float64),
        "oracle_before_enzymes": np.full(len(wids["enzymes"]), 1000.0, dtype=np.float64),
        "oracle_before_monomers": before_monomers,
    }

    result = _run_protein_translocation_tick(seed=0, tick=0, state=state)
    result_monomers = result.get("monomers")
    assert result_monomers is not None, "Missing monomers in tick result"
    assert result_monomers.shape == (2892,), (
        f"Result monomers must have shape (2892,), got {result_monomers.shape}"
    )

    # Non-authority positions must be strictly preserved
    assert result_monomers[comp_c * 482 + non_auth_idx_1] == 7.0, (
        f"Non-authority cytosol monomer at index {comp_c * 482 + non_auth_idx_1} was not preserved: "
        f"expected 7.0, got {result_monomers[comp_c * 482 + non_auth_idx_1]}"
    )
    assert result_monomers[comp_m * 482 + non_auth_idx_2] == 13.0, (
        f"Non-authority membrane monomer at index {comp_m * 482 + non_auth_idx_2} was not preserved: "
        f"expected 13.0, got {result_monomers[comp_m * 482 + non_auth_idx_2]}"
    )

    # Authority movement: MG_014 translocated out of cytosol into target compartment
    assert result_monomers[comp_c * 482 + auth_idx] == 0.0, (
        f"Expected authority monomer to translocate out of cytosol, got {result_monomers[comp_c * 482 + auth_idx]}"
    )
    total_auth_after = sum(result_monomers[c * 482 + auth_idx] for c in range(6))
    assert total_auth_after == 1.0, (
        f"Expected total count across compartments for authority monomer to remain 1.0, got {total_auth_after}"
    )


def test_contract_4_planted_collapsed_sum_mutation_canary() -> None:
    """Contract 4: Planted collapsed-sum mutation canary.

    The verifier must reject a (ticks, 6, 482).sum(axis=1) adapter even though
    per-WID totals are identical.
    """
    with pytest.raises(AssertionError, match=r"(?i)width must be 2892|collapsed|laundered"):
        _verify_translocation_monomer_adapter(_planted_collapsed_sum_adapter)


def test_contract_5_design_a_integration_fails_on_broadcast_without_shape_coercion(
    tmp_path: Path,
) -> None:
    """Contract 5: Minimal 1-seed / 1-tick run_design_a integration must complete

    without shape coercion. Currently reproduces the 2892->482 broadcast failure:
    ValueError: could not broadcast input array from shape (2892,) into shape (482,).
    """
    out_dir = tmp_path / "design_a_ptransloc"
    out_dir.mkdir(parents=True, exist_ok=True)

    result = run_design_a(
        process="ProteinTranslocation",
        seeds=[0],
        m_ticks=1,
        out_dir=out_dir,
        bootstrap_B=2,
    )
    assert result is not None, "run_design_a returned None"
    assert "verdict" in result, "run_design_a output missing 'verdict'"
