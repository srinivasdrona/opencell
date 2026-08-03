from __future__ import annotations

import random
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

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

TIME_STEP_S = 1.0
RNG_SEED = 0
SHORT_HORIZON_TICKS = 100
LONG_HORIZON_TICKS = 32_400
DNAA_PROTEIN_KEY = "MG_469_MONOMER"


def _build_engine(*, emit_step_s: float = TIME_STEP_S) -> Engine:
    random.seed(RNG_SEED)
    np.random.seed(RNG_SEED)
    composite = build_karr_chassis_v6(time_step_s=TIME_STEP_S, emit_step_s=emit_step_s)
    return Engine(composite=composite, emit_step=emit_step_s, display_info=False)


def _sum_pool_delta(
    before: dict[str, float | int],
    after: dict[str, float | int],
) -> float:
    keys = set(before) | set(after)
    return float(
        sum(float(after.get(wid, 0.0)) - float(before.get(wid, 0.0)) for wid in keys)
    )


def _translation_process(engine: Engine) -> Any:
    for process_key in ("karr_translation", "karr_translation_v3"):
        process = engine.processes.get(process_key)
        if process is not None:
            return process
    raise AssertionError(
        "No translation process found in chassis_v6; expected one of "
        "`karr_translation` or `karr_translation_v3`."
    )


def _seed_protein_processing_inputs(engine: Engine) -> None:
    pp1 = engine.processes["karr_protein_processing_i"]
    pp2 = engine.processes["karr_protein_processing_ii"]

    for wid in set(pp1.enzyme_wids):
        engine.state.set_path(("protein", "counts", wid), 5_000.0)
    for wid in set(pp2.enzyme_wids):
        engine.state.set_path(("protein", "enzyme_counts", wid), 5_000.0)
    for wid in set(pp1.substrate_wids) | set(pp2.substrate_wids):
        engine.state.set_path(("substrates", wid), 50_000.0)

    # Keep one precursor target high so PP flux is observable over a short run.
    source_wid = pp1.unprocessed_monomer_wids[0]
    downstream_wid = pp1.processed_monomer_wids[0]
    engine.state.set_path(("protein", "unprocessed_counts", source_wid), 1_000.0)
    engine.state.set_path(("protein", "processed_counts", downstream_wid), 0.0)
    engine.state.set_path(("protein", "unfolded_counts", downstream_wid), 0.0)


def test_bug5_translation_outputs_precursor_pool() -> None:
    """Bug 5 canary (a,c): translation should grow precursor pool without direct mature writes."""
    engine = _build_engine()
    initial_state = deepcopy(engine.state.get_value())
    translation_update = _translation_process(engine).next_update(TIME_STEP_S, initial_state)

    engine.update(TIME_STEP_S)
    first_tick_state = deepcopy(engine.state.get_value())

    precursor_delta_first_tick = _sum_pool_delta(
        initial_state["protein"]["unprocessed_counts"],
        first_tick_state["protein"]["unprocessed_counts"],
    )
    assert precursor_delta_first_tick > 0.0, (
        "Bug 5 precursor canary failed: total `protein.unprocessed_counts` did not increase "
        f"after the first tick; delta={precursor_delta_first_tick:.6g}."
    )

    protein_update = translation_update.get("protein", {})
    direct_mature_delta = float(
        sum(float(v) for v in protein_update.get("counts", {}).values())
    )
    assert "counts" not in protein_update or np.isclose(direct_mature_delta, 0.0), (
        "Bug 5 precursor canary failed: translation wrote non-zero direct mature deltas to "
        f"`protein.counts`; direct_mature_delta={direct_mature_delta:.6g}."
    )


def test_bug5_pp_pathway_consumes_precursors_and_feeds_mature() -> None:
    """Bug 5 canary (b): PP pathway should consume precursor IDs and increase downstream pools."""
    engine = _build_engine()
    _seed_protein_processing_inputs(engine)
    pp1 = engine.processes["karr_protein_processing_i"]
    pp1_pairs = list(zip(pp1.unprocessed_monomer_wids, pp1.processed_monomer_wids, strict=False))

    initial_state = deepcopy(engine.state.get_value())
    engine.update(float(SHORT_HORIZON_TICKS))
    final_state = deepcopy(engine.state.get_value())

    candidate_hits: list[tuple[str, str, float, float, float]] = []
    for precursor_wid, downstream_wid in pp1_pairs:
        precursor_delta = float(
            final_state["protein"]["unprocessed_counts"].get(precursor_wid, 0.0)
        ) - float(initial_state["protein"]["unprocessed_counts"].get(precursor_wid, 0.0))
        processed_delta = float(
            final_state["protein"]["processed_counts"].get(downstream_wid, 0.0)
        ) - float(initial_state["protein"]["processed_counts"].get(downstream_wid, 0.0))
        unfolded_delta = float(
            final_state["protein"]["unfolded_counts"].get(downstream_wid, 0.0)
        ) - float(initial_state["protein"]["unfolded_counts"].get(downstream_wid, 0.0))

        if precursor_delta < 0.0 and (processed_delta > 0.0 or unfolded_delta > 0.0):
            candidate_hits.append(
                (
                    precursor_wid,
                    downstream_wid,
                    precursor_delta,
                    processed_delta,
                    unfolded_delta,
                )
            )

    assert candidate_hits, (
        "Bug 5 PP canary failed: found no protein where precursor pool decreased while "
        "downstream pool (`processed_counts` or `unfolded_counts`) increased over the short run. "
        f"ticks={SHORT_HORIZON_TICKS}."
    )


@pytest.mark.slow
@pytest.mark.xfail(reason="pending Bug 6a/6b substrate writeback")
def test_bug5_long_horizon_total_protein_not_runaway_and_dnaa_matures() -> None:
    """Bug 5 canary (d,e): long-horizon mature total should stay bounded and DnaA should appear."""
    engine = _build_engine(emit_step_s=float(LONG_HORIZON_TICKS))

    state = engine.state.get_value()
    max_dnaa_mature = float(state["protein"]["counts"].get(DNAA_PROTEIN_KEY, 0.0))
    for tick in range(1, LONG_HORIZON_TICKS + 1):
        engine.update(TIME_STEP_S)
        state = engine.state.get_value()
        atp = float(state["substrates"].get("ATP", 0.0))
        gtp = float(state["substrates"].get("GTP", 0.0))
        if atp < 0.0 or gtp < 0.0:
            pytest.xfail(
                "pending Bug 6a/6b substrate writeback: ATP/GTP dropped negative "
                f"at tick={tick} (ATP={atp:.6g}, GTP={gtp:.6g})"
            )
        max_dnaa_mature = max(max_dnaa_mature, float(state["protein"]["counts"].get(DNAA_PROTEIN_KEY, 0.0)))

    total_protein_final = float(sum(float(v) for v in state["protein"]["counts"].values()))
    assert total_protein_final < 30_000.0, (
        "Bug 5 long-horizon canary failed: mature protein runaway exceeded guard at 32,400 ticks; "
        f"total_protein_final={total_protein_final:.6g}."
    )
    assert max_dnaa_mature > 0.0, (
        "Bug 5 long-horizon canary failed: mature DnaA never appeared by 32,400 ticks; "
        f"max_{DNAA_PROTEIN_KEY}={max_dnaa_mature:.6g}."
    )
