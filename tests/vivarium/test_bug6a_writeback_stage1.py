from __future__ import annotations

import pytest

from opencell.vivarium.karr_metabolism import _KARR_DEMAND_KEYS, KarrMetabolismProcess, build_karr_m1_engine


def _default_shared_substrates(proc: KarrMetabolismProcess) -> dict[str, float]:
    return {sid: 1.0 for sid in proc._sub_ids}


def test_dynamic_update_returns_positive_demand_writeback() -> None:
    proc = KarrMetabolismProcess({"dynamic_bounds": True})
    out = proc.next_update(
        timestep=1.0,
        states={"substrates": _default_shared_substrates(proc), "metabolic_reaction": {}},
    )

    assert "substrates" in out
    substrate_delta = out["substrates"]
    assert isinstance(substrate_delta, dict)
    assert substrate_delta, "expected at least one positive LP-derived demand-key writeback"
    assert all(v >= 0.0 for v in substrate_delta.values())
    assert all(k in _KARR_DEMAND_KEYS for k in substrate_delta)
    assert out["m1_dynamic_diagnostics"]["bug6a_writeback_total_positive"] == pytest.approx(
        float(sum(substrate_delta.values()))
    )
    assert set(out["m1_dynamic_diagnostics"]["bug6a_writeback_keys"]) == set(substrate_delta)


def test_engine_accumulates_writeback_into_shared_substrates() -> None:
    eng = build_karr_m1_engine(dynamic_bounds=True)
    before = dict(eng.state.get_value()["substrates"])

    eng.update(1.0)
    state = eng.state.get_value()
    after = state["substrates"]
    diag = state["m1_dynamic_diagnostics"]

    deltas = {sid: float(after[sid] - before[sid]) for sid in before}
    positive = {sid: delta for sid, delta in deltas.items() if delta > 0.0}

    assert positive, "engine state showed no accumulated LP writeback"
    assert all(delta >= 0.0 for delta in deltas.values())
    assert all(sid in _KARR_DEMAND_KEYS for sid in positive)
    assert float(diag["bug6a_writeback_total_positive"]) == pytest.approx(
        float(sum(positive.values())),
        rel=1e-9,
        abs=1e-9,
    )
    assert set(diag["bug6a_writeback_keys"]) == set(positive)

    ntp = {sid: positive.get(sid, 0.0) for sid in ("ATP", "CTP", "GTP", "UTP")}
    assert all(v >= 0.0 for v in ntp.values())
    assert sum(ntp.values()) > 0.0
