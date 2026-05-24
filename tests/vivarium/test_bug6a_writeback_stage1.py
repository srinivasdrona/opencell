from __future__ import annotations

import numpy as np
import pytest

from opencell.vivarium.karr_metabolism import _KARR_DEMAND_KEYS, KarrMetabolismProcess, build_karr_m1_engine


def _default_shared_substrates(proc: KarrMetabolismProcess) -> dict[str, float]:
    return {sid: 1.0 for sid in proc._sub_ids}


def test_dynamic_update_returns_signed_mapped_cytosol_writeback() -> None:
    proc = KarrMetabolismProcess({"dynamic_bounds": True})
    assert proc._fba_row_cmp is not None
    assert proc._cytosol_rows.size == int(np.count_nonzero(proc._fba_row_cmp == 0))
    assert proc._cytosol_rows.size > len(_KARR_DEMAND_KEYS)
    assert any(sid not in _KARR_DEMAND_KEYS for sid in proc._cyt_row_to_sid.values())

    out = proc.next_update(
        timestep=1.0,
        states={"substrates": _default_shared_substrates(proc), "metabolic_reaction": {}},
    )

    assert "substrates" in out
    substrate_delta = out["substrates"]
    assert isinstance(substrate_delta, dict)
    assert substrate_delta, "expected at least one non-zero LP-derived writeback"
    assert all(k in proc._sub_ids for k in substrate_delta)
    assert any(v > 0.0 for v in substrate_delta.values())
    assert any(v < 0.0 for v in substrate_delta.values())

    total_pos = float(sum(v for v in substrate_delta.values() if v > 0.0))
    total_neg = float(sum(v for v in substrate_delta.values() if v < 0.0))
    diag = out["m1_dynamic_diagnostics"]
    assert diag["bug6a_writeback_total_positive"] == pytest.approx(total_pos)
    assert diag["bug6a_s2_total_pos_writeback"] == pytest.approx(total_pos)
    assert diag["bug6a_s2_total_neg_writeback"] == pytest.approx(total_neg)
    assert diag["bug6a_s2_atp_lp_delta"] == pytest.approx(
        float(substrate_delta.get("ATP", 0.0))
    )
    assert set(diag["bug6a_writeback_keys"]) == set(substrate_delta)


def test_engine_accumulates_writeback_into_shared_substrates() -> None:
    eng = build_karr_m1_engine(dynamic_bounds=True)
    before = dict(eng.state.get_value()["substrates"])

    eng.update(1.0)
    state = eng.state.get_value()
    after = state["substrates"]
    diag = state["m1_dynamic_diagnostics"]

    deltas = {sid: float(after[sid] - before[sid]) for sid in before if after[sid] != before[sid]}

    assert deltas, "engine state showed no accumulated LP writeback"
    assert any(delta > 0.0 for delta in deltas.values())
    assert any(delta < 0.0 for delta in deltas.values())
    total_pos = float(sum(v for v in deltas.values() if v > 0.0))
    total_neg = float(sum(v for v in deltas.values() if v < 0.0))
    assert float(diag["bug6a_writeback_total_positive"]) == pytest.approx(total_pos, rel=1e-9, abs=1e-9)
    assert float(diag["bug6a_s2_total_pos_writeback"]) == pytest.approx(total_pos, rel=1e-9, abs=1e-9)
    assert float(diag["bug6a_s2_total_neg_writeback"]) == pytest.approx(total_neg, rel=1e-9, abs=1e-9)
    assert float(diag["bug6a_s2_atp_lp_delta"]) == pytest.approx(
        float(deltas.get("ATP", 0.0)),
        rel=1e-9,
        abs=1e-9,
    )
    assert set(deltas).issubset(set(diag["bug6a_writeback_keys"]))
