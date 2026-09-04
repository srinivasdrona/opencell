"""Regression tests for ``opencell/util/mcg16807_state_codec.py``.

Encodes, as literal hard-coded fixtures, the live-MATLAB transcript captured
2026-09-05 in this worktree (``tmp/probe_mcg16807_state_live2.m`` via
``scripts/tools/run_matlab_slot.ps1``, real ``RandStream('mcg16807')``,
R2026a-class MATLAB statistics toolbox) -- so this codec's correctness is
verifiable offline/in CI without a live MATLAB dependency, while still being
traceable back to a genuine MATLAB run rather than an assumed formula.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure pytest imports from this worktree even if another editable install exists.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    _loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in _loaded.parents:
        for _mod_name in list(sys.modules):
            if _mod_name == "opencell" or _mod_name.startswith("opencell."):
                del sys.modules[_mod_name]

from opencell.util.mcg16807_state_codec import (
    DEFAULT_STATE_FOR_ZERO_SEED,
    MCG_MOD,
    decode_state,
    draw_and_advance,
    encode_state,
    parse_captured_state,
    seed_state,
    step_raw,
    steps_between,
)

# Live MATLAB transcript: RandStream('mcg16807','Seed',uint32(36)), 60
# consecutive rand(rs) draws, State captured after each draw.
_SEED = 36
_STATES_AFTER_EACH = [
    1194876, 1010878952, 866668191, 49001976, 771444315, 1642972199, 831559265,
    1886021584, 1952785796, 639736565, 1314583917, 854653958, 1781373901,
    1050504137, 1823729965, 297223695, 693110612, 1190274660, 1301250413,
    1745113042, 126647979, 961318524, 872554089, 2129071317, 1984304254,
    2016213638, 1334588175, 176468527, 2044317486, 1043076373, 1166321060,
    1886020771, 1925457449, 896461613, 2142963170, 1359075631, 1181078082,
    991174127, 761709839, 653658177, 1689644388, 1596881635, 67724670,
    518861883, 1952781675, 501203366, 1025876422, 1500905131, 1363919953,
    905435011, 402950175, 851857973, 257204888, 1703595497, 1862055644,
    2122834637, 62833153, 1355575664, 994280648, 774444670,
]
_RAND_VALS = [
    0.46472168828580607, 0.57741501954263774, 0.61423345311276312,
    0.42164646620938856, 0.61215758119344599, 0.53246711824669835,
    0.1748563722590247, 0.81104855742820003, 0.2931046957583654,
    0.21062161084759123, 0.91741351546599226, 0.96895443693220351,
    0.21722151954528945, 0.84207899768002281, 0.82171400814396978,
    0.54733487570068562, 0.05725590142293642, 0.2999352152924683,
    0.011163420514745368, 0.62360859132539881, 0.98959440597779791,
    0.11318126884902886, 0.23758554562813861, 0.10026537212555547,
    0.16010931421076383, 0.95724394030740667, 0.39890474658408426,
    0.3920758387036975, 0.61862109304341539, 0.16471078068237321,
    0.29409092864677822, 0.78623776640102161, 0.29813990197057832,
    0.83733241950968862, 0.045974699336092315, 0.69677174170351208,
    0.64266281092663424, 0.2338632439420853, 0.53954093462766195,
    0.064488287113834308, 0.85464152221318401, 0.96006383698436615,
    0.79290819624108644, 0.40805422393980167, 0.16734175624667749,
    0.51289723790851294, 0.26387752837682027, 0.98961942921840562,
    0.53374687374278296, 0.68370699495249754, 0.063464166626084673,
    0.64224848460510764, 0.27028075804481316, 0.60870045917513804,
    0.428617356544648, 0.77191144589889393, 0.51567122271082888,
    0.88624010090075434, 0.037375838978856726, 0.17572571764501077,
]


def test_seed_state_matches_live_matlab() -> None:
    """RandStream('mcg16807','Seed',uint32(36)).State == 36 immediately
    after construction (live-verified) -- the seed passes through
    verbatim, no encode transform applied at seed time."""
    assert seed_state(36) == 36


def test_seed_state_zero_seed_matches_live_matlab() -> None:
    assert seed_state(0) == DEFAULT_STATE_FOR_ZERO_SEED == 931_316_785


def test_seed_state_one_matches_live_matlab() -> None:
    assert seed_state(1) == 1


def test_full_60_draw_sequence_matches_live_matlab() -> None:
    """Replays all 60 draws via decode -> raw step -> encode and checks
    both the resulting State and the uniform value against the real
    MATLAB transcript, exactly (0 mismatches required)."""
    state = seed_state(_SEED)
    for i in range(60):
        val, state = draw_and_advance(state)
        assert state == _STATES_AFTER_EACH[i], f"draw {i + 1}: state mismatch"
        assert val == pytest.approx(_RAND_VALS[i], abs=1e-12), f"draw {i + 1}: value mismatch"


def test_tick894_ledger_transition_reachable_in_49_steps() -> None:
    """The exact failure this codec fixes: task step 894's entry/exit pair
    (36 -> 1363919953) is unreachable under a raw (undecoded) recurrence
    within 1e6 steps, but reachable in exactly 49 real Lehmer steps once
    both endpoints are decoded first."""
    assert steps_between(36, 1_363_919_953) == 49


def test_tick895_ledger_transition_reachable_in_8_steps() -> None:
    assert steps_between(1_363_919_953, 62_833_153) == 8


def test_steps_between_zero_when_states_equal() -> None:
    assert steps_between(36, 36) == 0


def test_steps_between_raises_when_unreachable() -> None:
    # decode(1) -> raw 1; decode(2) -> raw... whatever it is, it's
    # exceedingly unlikely 1 forward-steps into 2's raw value within a
    # tiny bound; use a deliberately too-small max_steps to force failure
    # deterministically without depending on the actual orbit length.
    with pytest.raises(ValueError, match="not reached"):
        steps_between(36, 1_363_919_953, max_steps=5)


def test_encode_decode_round_trip() -> None:
    for raw in (1, 2, 36, 2359296, 997982226, MCG_MOD - 1, 1_146_212_683):
        assert decode_state(encode_state(raw)) == raw


def test_decode_encode_round_trip_on_captured_values() -> None:
    for encoded in (36, 1_363_919_953, 62_833_153, 1, MCG_MOD - 1):
        assert encode_state(decode_state(encoded)) == encoded


def test_step_raw_matches_lehmer_recurrence() -> None:
    assert step_raw(1) == 16807
    assert step_raw(2359296) == 997982226


@pytest.mark.parametrize("bad_value", [0, MCG_MOD, -1, MCG_MOD + 1])
def test_decode_state_rejects_out_of_range(bad_value: int) -> None:
    with pytest.raises(ValueError, match="must be in"):
        decode_state(bad_value)


@pytest.mark.parametrize("bad_value", [0, MCG_MOD, -1, MCG_MOD + 1])
def test_encode_state_rejects_out_of_range(bad_value: int) -> None:
    with pytest.raises(ValueError, match="must be in"):
        encode_state(bad_value)


def test_parse_captured_state_accepts_plain_scalar() -> None:
    assert parse_captured_state(36) == 36
    assert parse_captured_state(36.0) == 36


def test_parse_captured_state_accepts_single_element_array() -> None:
    import numpy as np

    assert parse_captured_state(np.array([[36.0]])) == 36
    assert parse_captured_state([36.0]) == 36


def test_parse_captured_state_rejects_multi_element_first_word_only_risk() -> None:
    with pytest.raises(ValueError, match="expected exactly 1"):
        parse_captured_state([36.0, 5.0])


def test_parse_captured_state_rejects_empty() -> None:
    with pytest.raises(ValueError, match="empty"):
        parse_captured_state([])


def test_parse_captured_state_rejects_non_finite() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        parse_captured_state(float("nan"))
    with pytest.raises(ValueError, match="non-finite"):
        parse_captured_state(float("inf"))


def test_parse_captured_state_rejects_non_integer_valued() -> None:
    with pytest.raises(ValueError, match="not integer-valued"):
        parse_captured_state(36.5)


def test_parse_captured_state_rejects_out_of_range() -> None:
    with pytest.raises(ValueError, match="out of range"):
        parse_captured_state(0)
    with pytest.raises(ValueError, match="out of range"):
        parse_captured_state(MCG_MOD)
