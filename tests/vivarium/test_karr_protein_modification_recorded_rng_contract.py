"""Recorded MATLAB private-MCG vectors and the exact PM weighted-call contract.

Companion to, not an edit/waiver of, the original 19 frozen RNG checks.
Small test fixtures preserve exact historic primary bytes plus hashes/origins.
Generic builtin reset(seed) observations are NOT a PM-private-prefix capture.

ProteinModification.m:374 calls util.RandStream.randsample(n,1,true,weights).
The wrapper delegates that branch directly. The as-inspected local toolbox
randsample.m:53-57,75-88 normalizes weights and draws k uniforms for histogram
bins: k=1 means ONE uniform, with no extra burns. No proprietary source body
is copied here. Boundary expectations below are independent unit inputs.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import opencell
from opencell.util import mcg16807_state_codec as codec
from opencell.vivarium import karr_protein_modification as pm

assert _ROOT in Path(opencell.__file__).resolve().parents, opencell.__file__
assert Path(pm.__file__).resolve() == _ROOT / "opencell/vivarium/karr_protein_modification.py"
assert Path(codec.__file__).resolve() == _ROOT / "opencell/util/mcg16807_state_codec.py"

_FIXTURES = Path(__file__).parent / "fixtures" / "pm_rng_recorded"
_AUTHORITY = json.loads((_FIXTURES / "authority.json").read_bytes())
_STATE_PROBE = json.loads(
    (_FIXTURES / "chromosome_randstream_state_probe.json").read_bytes()
)
_ZERO_PROBE = json.loads(
    (_FIXTURES / "probe_txreg_mcg_randsample_result.json").read_bytes()
)
_ROWS = _STATE_PROBE["rows"]
_RAW_ZERO = np.asarray(_ZERO_PROBE["case_c_seed0_rand8"])
_MODULUS = 2_147_483_647
_MULTIPLIER = 16807


def _recurrence(state: int, count: int) -> np.ndarray:
    """Test-only arithmetic check against recorded doubles, not an OC RNG."""
    out = []
    for _ in range(count):
        state = _MULTIPLIER * state % _MODULUS
        out.append(state / _MODULUS)
    return np.asarray(out)


def test_unit_recorded_primary_bytes_and_failed_old_formula_flags_are_preserved() -> None:
    for source in _AUTHORITY["sources"]:
        raw = (_FIXTURES / source["filename"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == source["sha256"]
        generator = source["generator"]
        assert generator["sha256"] != generator["current_pm_copy_sha256"]
    assert _STATE_PROBE["matlab_release"] == "2026a"
    assert _STATE_PROBE["all_formula_matches"] is False
    assert _STATE_PROBE["all_state_after_reset_matches_formula"] is False
    assert _STATE_PROBE["all_reconstruction_ok"] is True
    assert all(row["formula_matches_v1"] is False for row in _ROWS)
    assert all(row["formula_matches_v2"] is False for row in _ROWS)


def test_unit_seed_zero_kernel_mapping_uses_raw_uniforms_and_separate_holdouts() -> None:
    x1 = round(float(_RAW_ZERO[0]) * _MODULUS)
    x0 = x1 * pow(_MULTIPLIER, -1, _MODULUS) % _MODULUS
    assert x0 == 1_144_108_930
    np.testing.assert_array_equal(_recurrence(x0, 8), _RAW_ZERO)
    zero_row = next(row for row in _ROWS if row["seed"] == 0)
    np.testing.assert_array_equal(
        _RAW_ZERO[[0, 1, 7]], [zero_row["v1"], zero_row["v2"], zero_row["v3"]]
    )
    assert zero_row["state_after_reset"] == 931_316_785
    assert x0 != zero_row["state_after_reset"]


@pytest.mark.parametrize(
    "row", [row for row in _ROWS if row["seed"] > 0],
    ids=[f"seed{int(row['seed'])}" for row in _ROWS if row["seed"] > 0],
)
def test_unit_positive_seed_recurrence_matches_recorded_anchors(row: dict[str, Any]) -> None:
    vector = _recurrence(int(row["seed"]) * 65536 % _MODULUS, 8)
    np.testing.assert_array_equal(vector[[0, 1, 7]], [row["v1"], row["v2"], row["v3"]])


@pytest.mark.parametrize("row", _ROWS, ids=[f"seed{int(row['seed'])}" for row in _ROWS])
def test_pm_real_private_owner_matches_recorded_matlab_anchor_vector(
    row: dict[str, Any],
) -> None:
    """Precise primitive boundary: real constructor/owner, no substitute RNG."""
    process = pm.KarrProteinModificationProcess({"rng_seed": int(row["seed"])})
    owner = process._rng
    first_two = owner.random(2)
    owner.random(5)
    eighth = owner.random(1)
    observed = np.concatenate([first_two, eighth])
    assert process._rng is owner
    np.testing.assert_array_equal(
        observed,
        [row["v1"], row["v2"], row["v3"]],
        err_msg=(
            "Actual PM private owner must match recorded builtin reset(seed) "
            "uniform positions 1,2,8; v3 was recorded after randperm(5), not "
            "as the third contiguous uniform. This is not a PM-prefix oracle."
        ),
    )


@pytest.mark.parametrize("chunks", [(8,), (3, 5), (1,) * 8], ids=["vector", "split", "scalar"])
def test_pm_real_private_owner_seed_zero_matches_separate_direct_rand8(
    chunks: tuple[int, ...],
) -> None:
    process = pm.KarrProteinModificationProcess({"rng_seed": 0})
    owner = process._rng
    actual = np.concatenate([owner.random(n) for n in chunks])
    assert process._rng is owner
    np.testing.assert_array_equal(
        actual, _RAW_ZERO, err_msg="Recorded MATLAB reset(0); rand(8,1), exact doubles"
    )


class _UnitUniforms:
    """Sampler-unit input only; never used by real-owner vector cases."""

    def __init__(self, first: float) -> None:
        self.values = [first, 0.61, 0.89, 0.02, 0.51, 0.77, 0.33, 0.44]
        self.count = 0

    def random(self, size: Any = None) -> Any:
        count = 1 if size is None else int(np.prod(size))
        start = self.count
        self.count += count
        assert self.count <= len(self.values), "Unexpected extra sampler draws"
        values = np.asarray(self.values[start : self.count])
        return float(values[0]) if size is None else values.reshape(size, order="F")


@pytest.mark.parametrize(
    ("weights", "uniform", "expected_index"),
    [
        pytest.param([1.0, 2.0, 3.0], float(_RAW_ZERO[0]), 1, id="recorded-first-uniform"),
        pytest.param([0.0, 1.0, 0.0, 3.0, 0.0], 0.0, 1, id="left-edge-zero-bin"),
        pytest.param(
            [0.0, 1.0, 0.0, 3.0, 0.0], np.nextafter(0.25, 0.0), 1,
            id="below-interior-edge",
        ),
        pytest.param([0.0, 1.0, 0.0, 3.0, 0.0], 0.25, 3, id="on-interior-edge"),
        pytest.param(
            [0.0, 1.0, 0.0, 3.0, 0.0], np.nextafter(0.25, 1.0), 3,
            id="above-interior-edge",
        ),
        pytest.param(
            [0.0, 1.0, 0.0, 3.0, 0.0], np.nextafter(1.0, 0.0), 3,
            id="last-positive-bin",
        ),
    ],
)
def test_unit_pm_weighted_replacement_uses_one_first_uniform_without_burns(
    weights: list[float], uniform: float, expected_index: int
) -> None:
    """Source k=1 law: one draw regardless of engine/seed/chosen protein."""
    process = pm.KarrProteinModificationProcess({"rng_seed": 17})
    scripted = _UnitUniforms(uniform)
    process._rng = scripted
    vector = np.asarray(weights)
    selected = process._weighted_index_sample(vector, float(np.sum(vector)))
    assert scripted.count == 1, (
        "PM source calls weighted randsample(n,1,true,w); installed source "
        f"randsample.m:88 draws k=1 uniform, not {scripted.count}. "
        "Deleting source-absent burns is the contract, not calibrating a burn."
    )
    assert selected == expected_index
    assert process._rng is scripted


def test_pm_real_owner_weighted_draw_keeps_recorded_seed_zero_continuation() -> None:
    """Real-owner primitive boundary, not a substitute for public replay."""
    process = pm.KarrProteinModificationProcess({"rng_seed": 0})
    owner = process._rng
    selected = process._weighted_index_sample(np.array([1.0, 2.0, 3.0]), 6.0)
    continuation = owner.random(3)
    assert process._rng is owner
    assert selected == 1, "First recorded u=.218959... lies in normalized bin2 (OC index1)"
    np.testing.assert_array_equal(
        continuation, _RAW_ZERO[1:4], err_msg="Exactly one weighted draw, then raw uniforms2..4"
    )


@pytest.mark.parametrize("row", _ROWS, ids=[f"seed{int(row['seed'])}" for row in _ROWS])
def test_unit_neutral_codec_matches_recorded_uniforms_and_matlab_exposed_states(
    row: dict[str, Any],
) -> None:
    """Reuse authority: compare actual codec to raw records, not to itself."""
    seed = int(row["seed"])
    encoded = codec.seed_state(seed)
    assert encoded == int(row["state_after_reset"])
    assert encoded == int(row["op_states_before"][0])
    expected_kernel = (
        1_144_108_930 if seed == 0 else seed * 65536 % _MODULUS
    )
    assert codec.decode_state(encoded) == expected_kernel
    observed = []
    for position in range(8):
        value, encoded = codec.draw_and_advance(encoded)
        observed.append(value)
        if position < 2:
            assert encoded == int(row["op_states_after"][position])
        if position == 6:
            assert encoded == int(row["state_before_op4"])
            assert encoded == int(row["op_states_after"][2])
    assert encoded == int(row["state_after_op4"])
    np.testing.assert_array_equal(
        np.asarray(observed)[[0, 1, 7]], [row["v1"], row["v2"], row["v3"]]
    )


def test_unit_neutral_codec_seed_zero_matches_independent_direct_rand8_record() -> None:
    encoded = codec.seed_state(0)
    assert encoded == 931_316_785
    assert codec.decode_state(encoded) == 1_144_108_930
    observed = []
    for _ in range(8):
        value, encoded = codec.draw_and_advance(encoded)
        observed.append(value)
    np.testing.assert_array_equal(observed, _RAW_ZERO)
