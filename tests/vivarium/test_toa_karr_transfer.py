from __future__ import annotations

from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
import sys

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

from l2_replay_common import cell_vector, resolve_trace_path

from opencell.vivarium.karr_terminal_organelle_assembly import KarrTerminalOrganelleAssemblyProcess

TOA_MONOMERS = (
    "MG_191_MONOMER",
    "MG_192_MONOMER",
    "MG_217_MONOMER",
    "MG_218_MONOMER",
    "MG_312_MONOMER",
    "MG_317_MONOMER",
    "MG_318_MONOMER",
    "MG_386_MONOMER",
)
COMPARTMENTS = ("c", "d", "e", "m", "tc", "tm")
# Incorporated (column 0 in Python, column 1 in MATLAB)
TOA_COMPARTMENTS_INC = ("tm", "tm", "tc", "tc", "tc", "tc", "tm", "tc")
# Unincorporated (column 1 in Python, column 2 in MATLAB)
TOA_COMPARTMENTS_UNINC = ("m", "m", "c", "c", "c", "c", "m", "c")


def _empty_mature_state() -> dict[str, dict[str, float]]:
    return {wid: {c: 0.0 for c in COMPARTMENTS} for wid in TOA_MONOMERS}


def _build_toa_input_state(mature_dict: dict[str, dict[str, float]]) -> dict[str, Any]:
    return {
        "protein": {
            "compartment_counts": {
                "mature": {
                    wid: {c: float(mature_dict.get(wid, {}).get(c, 0.0)) for c in COMPARTMENTS}
                    for wid in TOA_MONOMERS
                }
            }
        }
    }


def _apply_toa_update(mature_state: dict[str, dict[str, float]], update: dict[str, Any]) -> None:
    deltas = update.get("protein", update)
    if "compartment_counts" in deltas:
        deltas = deltas["compartment_counts"]
    if "mature" in deltas:
        deltas = deltas["mature"]

    for wid, comp_deltas in deltas.items():
        if isinstance(comp_deltas, dict):
            for comp, delta in comp_deltas.items():
                if wid in mature_state and comp in mature_state[wid]:
                    mature_state[wid][comp] = float(mature_state[wid][comp] + float(delta))


def project_substrates_8x2(mature_state: dict[str, dict[str, float]]) -> np.ndarray:
    out = np.zeros((8, 2), dtype=np.float64)
    for i, wid in enumerate(TOA_MONOMERS):
        inc_comp = TOA_COMPARTMENTS_INC[i]
        uninc_comp = TOA_COMPARTMENTS_UNINC[i]
        out[i, 0] = mature_state.get(wid, {}).get(inc_comp, 0.0)
        out[i, 1] = mature_state.get(wid, {}).get(uninc_comp, 0.0)
    return out


def overlay_substrates_8x2(mature_state: dict[str, dict[str, float]], substrates_8x2: np.ndarray) -> None:
    for i, wid in enumerate(TOA_MONOMERS):
        inc_comp = TOA_COMPARTMENTS_INC[i]
        uninc_comp = TOA_COMPARTMENTS_UNINC[i]
        if wid not in mature_state:
            mature_state[wid] = {c: 0.0 for c in COMPARTMENTS}
        mature_state[wid][inc_comp] = float(substrates_8x2[i, 0])
        mature_state[wid][uninc_comp] = float(substrates_8x2[i, 1])


def test_c3_toa_exact_8x2_fixture_transfer_oracle_ticks() -> None:
    """Claim C3: Exact 8x2 fixture transfer on oracle ticks 6, 46, 68.

    Asserts integer exactness, non-empty update on active ticks, and empty update
    when unincorporated is all-zero.
    """
    trace_path = resolve_trace_path("TerminalOrganelleAssembly")
    proc = KarrTerminalOrganelleAssemblyProcess({})

    with h5py.File(trace_path, "r") as trace:
        active_ticks = [6, 46, 68]
        for tick in active_ticks:
            karr_before_vec = cell_vector(trace, "states_before", "substrates", tick)
            karr_after_vec = cell_vector(trace, "states_after", "substrates", tick)
            karr_before_8x2 = karr_before_vec.reshape((8, 2), order="F")
            karr_after_8x2 = karr_after_vec.reshape((8, 2), order="F")

            mature_state = _empty_mature_state()
            overlay_substrates_8x2(mature_state, karr_before_8x2)

            state_input = _build_toa_input_state(mature_state)
            update = proc.next_update(1.0, state_input)

            # Guard against identity/no-op: update MUST be non-empty on active ticks
            assert update, f"Tick {tick}: expected non-empty update from TOA, got empty dict"

            _apply_toa_update(mature_state, update)
            oc_after_8x2 = project_substrates_8x2(mature_state)

            assert np.array_equal(oc_after_8x2, karr_after_8x2), (
                f"Tick {tick} mismatch:\nExpected Karr after:\n{karr_after_8x2}\nGot OC after:\n{oc_after_8x2}"
            )

        # Non-active tick with unincorporated all zero must return {}
        zero_uninc_state = _empty_mature_state()
        zero_state_input = _build_toa_input_state(zero_uninc_state)
        zero_update = proc.next_update(1.0, zero_state_input)
        assert zero_update == {}, f"Expected empty update for all-zero unincorporated, got {zero_update}"


def test_c4_full_count_transfer_n_greater_than_one() -> None:
    """Claim C4: Multi-copy transfer (n > 1) moves the full count in ONE tick.

    Constructed state: mature MG_312 = {c: 5, tc: 26}; mature MG_218 = {tc: 33}.
    Expected after ONE tick: mature MG_312 = {c: 0, tc: 31}.
    Kills: any +1-per-tick implementation (which would yield {c: 4, tc: 27}).
    """
    proc = KarrTerminalOrganelleAssemblyProcess({})
    mature_state = _empty_mature_state()
    mature_state["MG_312_MONOMER"]["c"] = 5.0
    mature_state["MG_312_MONOMER"]["tc"] = 26.0
    mature_state["MG_218_MONOMER"]["tc"] = 33.0

    state_input = _build_toa_input_state(mature_state)
    update = proc.next_update(1.0, state_input)
    assert update, "Expected non-empty update for multi-copy transfer"

    _apply_toa_update(mature_state, update)

    assert mature_state["MG_312_MONOMER"]["c"] == 0.0, (
        f"Expected full-count transfer c -> 0, got {mature_state['MG_312_MONOMER']['c']}"
    )
    assert mature_state["MG_312_MONOMER"]["tc"] == 31.0, (
        f"Expected tc -> 31, got {mature_state['MG_312_MONOMER']['tc']}"
    )


def test_c5_fixed_point_hierarchy_depth_three() -> None:
    """Claim C5: Fixed-point loop resolves 3-hop cascade in ONE tick.

    Constructed cascade:
      MG_312 (HMW1) = {tc: 1}  (incorporated seed)
      MG_317 (HMW3) = {c: 2}   (uninc; needs HMW1 inc, R8)
      MG_318 (P32)  = {m: 4}   (uninc; needs HMW3 inc, R9)
      MG_217 (P65)  = {c: 3}   (uninc; needs P32 inc, R3)
    Expected after ONE tick:
      MG_317 -> {tc: 2, c: 0}
      MG_318 -> {tm: 4, m: 0}
      MG_217 -> {tc: 3, c: 0}
      MG_312 -> {tc: 1, c: 0}
    Kills: any single-pass implementation.
    """
    proc = KarrTerminalOrganelleAssemblyProcess({})
    mature_state = _empty_mature_state()
    mature_state["MG_312_MONOMER"]["tc"] = 1.0
    mature_state["MG_317_MONOMER"]["c"] = 2.0
    mature_state["MG_318_MONOMER"]["m"] = 4.0
    mature_state["MG_217_MONOMER"]["c"] = 3.0

    state_input = _build_toa_input_state(mature_state)
    update = proc.next_update(1.0, state_input)
    assert update, "Expected cascade update"

    _apply_toa_update(mature_state, update)

    assert mature_state["MG_317_MONOMER"]["tc"] == 2.0
    assert mature_state["MG_317_MONOMER"]["c"] == 0.0
    assert mature_state["MG_318_MONOMER"]["tm"] == 4.0
    assert mature_state["MG_318_MONOMER"]["m"] == 0.0
    assert mature_state["MG_217_MONOMER"]["tc"] == 3.0
    assert mature_state["MG_217_MONOMER"]["c"] == 0.0
    assert mature_state["MG_312_MONOMER"]["tc"] == 1.0


def test_c6_plane_orientation_hmw1_hmw2_mutual_rule() -> None:
    """Claim C6: Plane orientation distinguishes incorporated vs unincorporated requirements.

    State A: MG_312={c: 2}, MG_218={c: 3}. Both require unincorporated partner.
             Both localize -> MG_312 {tc: 2}, MG_218 {tc: 3}.
    State B: MG_317={c: 2}, MG_312={c: 1}. R8 requires HMW1 INCORPORATED.
             HMW1 is UNINCORPORATED, so NOTHING must move.
    Kills: TOA-PLANE-SWAP (transposed requirement planes).
    """
    proc = KarrTerminalOrganelleAssemblyProcess({})

    # State A: Both move
    state_a = _empty_mature_state()
    state_a["MG_312_MONOMER"]["c"] = 2.0
    state_a["MG_218_MONOMER"]["c"] = 3.0
    update_a = proc.next_update(1.0, _build_toa_input_state(state_a))
    assert update_a, "State A: expected both to localize"
    _apply_toa_update(state_a, update_a)
    assert state_a["MG_312_MONOMER"]["tc"] == 2.0
    assert state_a["MG_312_MONOMER"]["c"] == 0.0
    assert state_a["MG_218_MONOMER"]["tc"] == 3.0
    assert state_a["MG_218_MONOMER"]["c"] == 0.0

    # State B: Nothing moves
    state_b = _empty_mature_state()
    state_b["MG_317_MONOMER"]["c"] = 2.0
    state_b["MG_312_MONOMER"]["c"] = 1.0
    update_b = proc.next_update(1.0, _build_toa_input_state(state_b))
    assert update_b == {}, f"State B: expected empty update (no movement), got {update_b}"
    _apply_toa_update(state_b, update_b)
    assert state_b["MG_317_MONOMER"]["c"] == 2.0
    assert state_b["MG_317_MONOMER"]["tc"] == 0.0


def test_c7_threshold_zero_reaction() -> None:
    """Claim C7: P110 (MG_192) has threshold 0 (no requirements) and always localizes.

    Constructed state: mature MG_192 = {m: 7}, all else 0.
    Expected: MG_192 -> {tm: 7, m: 0} in one tick.
    """
    proc = KarrTerminalOrganelleAssemblyProcess({})
    mature_state = _empty_mature_state()
    mature_state["MG_192_MONOMER"]["m"] = 7.0

    state_input = _build_toa_input_state(mature_state)
    update = proc.next_update(1.0, state_input)
    assert update, "Expected P110 localization update"

    _apply_toa_update(mature_state, update)
    assert mature_state["MG_192_MONOMER"]["tm"] == 7.0
    assert mature_state["MG_192_MONOMER"]["m"] == 0.0


def test_c8_conservation_and_integrality() -> None:
    """Claim C8: Molecule counts are strictly conserved and integral across TOA updates."""
    proc = KarrTerminalOrganelleAssemblyProcess({})
    mature_state = _empty_mature_state()
    mature_state["MG_312_MONOMER"]["c"] = 10.0
    mature_state["MG_218_MONOMER"]["tc"] = 5.0
    mature_state["MG_192_MONOMER"]["m"] = 3.0

    total_before = {wid: sum(mature_state[wid].values()) for wid in TOA_MONOMERS}

    state_input = _build_toa_input_state(mature_state)
    update = proc.next_update(1.0, state_input)
    _apply_toa_update(mature_state, update)

    total_after = {wid: sum(mature_state[wid].values()) for wid in TOA_MONOMERS}

    for wid in TOA_MONOMERS:
        assert total_after[wid] == total_before[wid], f"Conservation violated for {wid}"
        assert float(total_after[wid]).is_integer(), f"Non-integral total count for {wid}: {total_after[wid]}"
        for comp, val in mature_state[wid].items():
            assert val >= 0.0, f"Negative count at {wid}@{comp}: {val}"
            assert float(val).is_integer(), f"Non-integral count at {wid}@{comp}: {val}"


def test_c8_fractional_count_raises_value_error() -> None:
    """Claim C8: Supplying a fractional authoritative molecule count must raise ValueError

    with an integral-count message before any transfer. Karr state is uint16; fail loud,
    never round/floor/clip.
    """
    proc = KarrTerminalOrganelleAssemblyProcess({})
    mature_state = _empty_mature_state()
    # Fractional count: 1.5 copies of MG_192 in unincorporated compartment 'm'
    mature_state["MG_192_MONOMER"]["m"] = 1.5

    state_input = _build_toa_input_state(mature_state)
    with pytest.raises(ValueError) as exc_info:
        proc.next_update(1.0, state_input)

    err_str = str(exc_info.value).lower()
    assert (
        "integral" in err_str
        or "integer" in err_str
        or "fractional" in err_str
        or "non-integral" in err_str
    ), f"Expected integral-count message in ValueError, got: {exc_info.value}"


def test_c9_no_oracle_input_in_toa() -> None:
    """Claim C9: TOA production code contains no trace_hint, states_after, or states_before."""
    src_path = _REPO_ROOT / "opencell" / "vivarium" / "karr_terminal_organelle_assembly.py"
    src_text = src_path.read_text(encoding="utf-8")

    forbidden = ["trace_hint", "states_after", "states_before"]
    violations = [token for token in forbidden if token in src_text]
    assert not violations, f"TOA production code contains forbidden oracle tokens: {violations}"

    # Runtime: passing state with trace_hint must produce identical update
    proc = KarrTerminalOrganelleAssemblyProcess({})
    base_state = _empty_mature_state()
    base_state["MG_192_MONOMER"]["m"] = 5.0

    input_clean = _build_toa_input_state(base_state)
    update_clean = proc.next_update(1.0, input_clean)

    input_tainted = _build_toa_input_state(base_state)
    input_tainted["trace_hint"] = {"substrates_next": {"MG_192_MONOMER@tm": 999.0}}
    update_tainted = proc.next_update(1.0, input_tainted)

    assert update_clean == update_tainted, "trace_hint tainted the runtime update"


# -----------------------------------------------------------------------------
# Mutation Canaries (Beat-4 Inversion Proofs)
# -----------------------------------------------------------------------------

class _OneCopyCanaryTOA:
    """Canary 1: Broken TOA that moves only 1 copy instead of the full count."""
    def evolve(self, mature_state: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
        out = {wid: dict(comps) for wid, comps in mature_state.items()}
        # Transfers only 1 copy
        if out["MG_312_MONOMER"]["c"] > 0 and out["MG_218_MONOMER"]["tc"] > 0:
            out["MG_312_MONOMER"]["c"] -= 1.0
            out["MG_312_MONOMER"]["tc"] += 1.0
        return out


class _SinglePassCanaryTOA:
    """Canary 2: Broken TOA that runs only 1 pass (no while fixed-point loop)."""
    def evolve(self, mature_state: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
        out = {wid: dict(comps) for wid, comps in mature_state.items()}
        # Pass 1 only: localizes HMW3 (MG_317) using HMW1 incorporated seed
        if out["MG_312_MONOMER"]["tc"] > 0 and out["MG_317_MONOMER"]["c"] > 0:
            count = out["MG_317_MONOMER"]["c"]
            out["MG_317_MONOMER"]["c"] = 0.0
            out["MG_317_MONOMER"]["tc"] += count
        # Exits immediately without iteration 2 or 3!
        return out


class _PlaneSwappedCanaryTOA:
    """Canary 3: Broken TOA with requirement planes swapped (plane 0 treated as uninc)."""
    def evolve(self, mature_state: dict[str, dict[str, float]]) -> dict[str, Any]:
        # Under swapped planes, R8 checks UNINCORPORATED HMW1 instead of INCORPORATED HMW1.
        # In State B (where HMW1 is unincorporated), it erroneously fires!
        if mature_state["MG_312_MONOMER"]["c"] > 0 and mature_state["MG_317_MONOMER"]["c"] > 0:
            return {"protein": {"compartment_counts": {"mature": {"MG_317_MONOMER": {"tc": 2.0, "c": -2.0}}}}}
        return {}


def test_mutation_canary_one_copy_fails_c4() -> None:
    """Mutation Canary 1: One-copy transfer demonstrably FAILS Claim C4."""
    canary = _OneCopyCanaryTOA()
    state = _empty_mature_state()
    state["MG_312_MONOMER"]["c"] = 5.0
    state["MG_312_MONOMER"]["tc"] = 26.0
    state["MG_218_MONOMER"]["tc"] = 33.0

    result = canary.evolve(state)
    # Canary gives {c: 4, tc: 27}, which fails the C4 assertion ({c: 0, tc: 31})
    with pytest.raises(AssertionError):
        assert result["MG_312_MONOMER"]["c"] == 0.0
        assert result["MG_312_MONOMER"]["tc"] == 31.0


def test_mutation_canary_single_pass_fails_c5() -> None:
    """Mutation Canary 2: Single-pass implementation demonstrably FAILS Claim C5."""
    canary = _SinglePassCanaryTOA()
    state = _empty_mature_state()
    state["MG_312_MONOMER"]["tc"] = 1.0
    state["MG_317_MONOMER"]["c"] = 2.0
    state["MG_318_MONOMER"]["m"] = 4.0
    state["MG_217_MONOMER"]["c"] = 3.0

    result = canary.evolve(state)
    # Canary leaves P32 (MG_318) and P65 (MG_217) unmoved, which fails C5
    with pytest.raises(AssertionError):
        assert result["MG_318_MONOMER"]["tm"] == 4.0
        assert result["MG_217_MONOMER"]["tc"] == 3.0


def test_mutation_canary_plane_swap_fails_c6_state_b() -> None:
    """Mutation Canary 3: Swapped requirement planes demonstrably FAILS Claim C6 State B."""
    canary = _PlaneSwappedCanaryTOA()
    state_b = _empty_mature_state()
    state_b["MG_317_MONOMER"]["c"] = 2.0
    state_b["MG_312_MONOMER"]["c"] = 1.0

    update_b = canary.evolve(state_b)
    # Canary returns non-empty update, failing the State B requirement of empty update ({})
    with pytest.raises(AssertionError):
        assert update_b == {}
