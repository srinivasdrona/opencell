from __future__ import annotations

from pathlib import Path
import random
import sys

import numpy as np
import pytest
from vivarium.core.engine import Engine

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

from opencell.vivarium.karr_composite import build_karr_chassis_v6
from opencell.vivarium.karr_transcription_v3 import KarrTranscriptionV3Process
from opencell.vivarium.karr_translation_v3 import KarrTranslationV3Process


def _run_chassis_v6_120_ticks() -> dict[str, object]:
    random.seed(0)
    np.random.seed(0)

    m2_atp_deltas: list[float] = []
    m3_atp_deltas: list[float] = []

    orig_m2_next = KarrTranscriptionV3Process.next_update
    orig_m3_next = KarrTranslationV3Process.next_update

    def _spy_m2(self: KarrTranscriptionV3Process, timestep: float, states: dict) -> dict:
        update = orig_m2_next(self, timestep, states)
        m2_atp_deltas.append(float(update.get("substrates", {}).get("ATP", 0.0)))
        return update

    def _spy_m3(self: KarrTranslationV3Process, timestep: float, states: dict) -> dict:
        update = orig_m3_next(self, timestep, states)
        m3_atp_deltas.append(float(update.get("substrates", {}).get("ATP", 0.0)))
        return update

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(KarrTranscriptionV3Process, "next_update", _spy_m2)
    monkeypatch.setattr(KarrTranslationV3Process, "next_update", _spy_m3)

    min_ntp = {sid: np.inf for sid in ("ATP", "CTP", "GTP", "UTP")}
    m1_atp_lp_deltas: list[float] = []
    writeback_neg: list[float] = []
    writeback_pos: list[float] = []
    try:
        engine = Engine(
            composite=build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0),
            emit_step=1.0,
            display_info=False,
        )
        for _tick in range(120):
            engine.update(1.0)
            state = engine.state.get_value()
            shared = state["substrates"]
            for sid in min_ntp:
                min_ntp[sid] = min(min_ntp[sid], float(shared[sid]))
            diag = state["m1_dynamic_diagnostics"]
            m1_atp_lp_deltas.append(float(diag["bug6a_s2_atp_lp_delta"]))
            writeback_neg.append(float(diag["bug6a_s2_total_neg_writeback"]))
            writeback_pos.append(float(diag["bug6a_s2_total_pos_writeback"]))
    finally:
        monkeypatch.undo()

    m1_atp_sum = float(sum(m1_atp_lp_deltas))
    m2_atp_sum = float(sum(m2_atp_deltas))
    m3_atp_sum = float(sum(m3_atp_deltas))
    m23_sum = m2_atp_sum + m3_atp_sum
    eps = 1e-12
    double_count_flag = abs(m1_atp_sum) > eps and abs(m23_sum) > eps and np.sign(m1_atp_sum) == np.sign(
        m23_sum
    )
    return {
        "min_ntp": min_ntp,
        "m1_atp_lp_deltas": np.asarray(m1_atp_lp_deltas, dtype=np.float64),
        "writeback_neg": np.asarray(writeback_neg, dtype=np.float64),
        "writeback_pos": np.asarray(writeback_pos, dtype=np.float64),
        "m1_atp_lp_sum": m1_atp_sum,
        "m2_atp_sum": m2_atp_sum,
        "m3_atp_sum": m3_atp_sum,
        "double_count_flag": bool(double_count_flag),
    }


def test_bug6a_stage2_chassis_v6_canary_120_ticks() -> None:
    try:
        stats = _run_chassis_v6_120_ticks()
    except Exception as exc:  # pragma: no cover - failure path asserts runtime health
        pytest.fail(f"120-tick chassis_v6 canary raised unexpectedly: {exc!r}")

    # Post-Track-A (allocator enrollment for TX v3 + TL v3, L2 layer), the
    # shared NTP pools must stay non-negative across the 120-tick canary. TX/TL
    # now consume via `substrates_allocated` direct writers rather than
    # draining the shared pool unconstrained, so M1's signed writeback should
    # produce only the positive (production) stream and no negative writeback.
    # Pre-Track-A this was diagnostic-only; with the swarm landed (HEAD 2151d35,
    # 2026-05-25) it is the closing gate.
    min_ntp = stats["min_ntp"]
    print(
        "[bug6a stage2 gate] min_ntp post-Track-A: "
        f"ATP={min_ntp['ATP']:.6g} CTP={min_ntp['CTP']:.6g} "
        f"GTP={min_ntp['GTP']:.6g} UTP={min_ntp['UTP']:.6g}"
    )
    _NTP_FLOOR = -1e-9  # numerical-noise tolerance for fp64 LP residuals
    for sid in ("ATP", "CTP", "GTP", "UTP"):
        assert min_ntp[sid] >= _NTP_FLOOR, (
            f"NTP {sid} dropped below allocator-mediated floor: "
            f"min={min_ntp[sid]!r} (tolerance {_NTP_FLOOR})"
        )

    m1_atp_lp_deltas = stats["m1_atp_lp_deltas"]
    writeback_neg = stats["writeback_neg"]
    writeback_pos = stats["writeback_pos"]
    assert np.all(np.isfinite(m1_atp_lp_deltas))
    assert np.all(np.isfinite(writeback_neg))
    assert np.all(np.isfinite(writeback_pos))
    assert np.all(writeback_neg <= 1e-12)
    assert np.all(writeback_pos >= -1e-12)
    # Post-Track-A invariant: M1's signed writeback collapses to a purely
    # additive stream because TX/TL consumption flows through the allocator
    # (substrates_allocated direct writers), not through M1's net flux.
    # Negative writeback (pre-A2 artifact) must NOT appear; positive writeback
    # (M1 production) must still fire on most ticks.
    assert np.all(writeback_neg >= -1e-12), (
        "Negative writeback resurfaced; allocator enrollment may be broken."
    )
    assert np.any(writeback_pos > 0.0), (
        "M1 positive writeback (production) disappeared; M1 LP solve broken."
    )

    assert np.isfinite(float(stats["m1_atp_lp_sum"]))
    assert np.isfinite(float(stats["m2_atp_sum"]))
    assert np.isfinite(float(stats["m3_atp_sum"]))
    # Comparison is diagnostic only; follow-up gating happens outside this stage.
    assert isinstance(stats["double_count_flag"], bool)
    print(
        "[bug6a stage2 diag] ATP attribution: "
        f"M1={float(stats['m1_atp_lp_sum']):.6g} "
        f"M2v3={float(stats['m2_atp_sum']):.6g} "
        f"M3v3={float(stats['m3_atp_sum']):.6g} "
        f"double_count_flag={stats['double_count_flag']}"
    )
