"""Source-derived PM RNG regressions, not a replacement for persistent replay.

WholeCell/src/+edu/+stanford/+covert/+cell/+sim/Process.m:282-290
constructs a PRIVATE util.RandStream('mcg16807') and resets it with this.seed.
WholeCell/src/+edu/+stanford/+covert/+util/RandStream.m:235-239
draws rand(this.randStream, size(value)) for EVERY entry, then compares
u < mod(value, 1). In particular, floor(value + u) is not that algorithm.

The family exclusion below is a necessary, intentionally RED condition:
NumPy RandomState is MT19937, not the source factory's mcg16807. It does not
invent a MATLAB seed-to-state mapping or an unrecorded tick53 uniform. Passing
it alone cannot certify an arbitrary replacement RNG or close the unchanged
100-tick replay. Remaining checks are explicitly primitive-unit controls or
public-owner continuity controls; none reads the output oracle.
"""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import opencell
from opencell.vivarium import karr_protein_modification as pm
from opencell.vivarium.protein_state import MIGRATED_WIDS

assert _ROOT in Path(opencell.__file__).resolve().parents, opencell.__file__
assert Path(pm.__file__).resolve() == _ROOT / "opencell/vivarium/karr_protein_modification.py"


class _ScriptedUniforms:
    """Unit-only primitive input, never installed in the public-owner tests."""

    def __init__(self, uniforms: list[float]) -> None:
        self.uniforms = np.asarray(uniforms, dtype=float)
        self.position = 0
        self.shapes: list[tuple[int, ...]] = []

    def random(self, size: tuple[int, ...]) -> np.ndarray:
        shape = tuple(size)
        count = int(np.prod(shape))
        start = self.position
        self.position += count
        assert self.position <= self.uniforms.size, "Unexpected extra RNG consumption"
        self.shapes.append(shape)
        # PM's actual call is an n-by-1 MATLAB vector, represented as (n,).
        # There is no 2-D production operand here to justify a matrix-order test.
        return self.uniforms[start : self.position].reshape(shape, order="F")


class _ObservedUniforms:
    """Forward exactly, recording real draws without changing the RNG stream."""

    def __init__(self, owner: Any) -> None:
        self.owner = owner
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any], np.ndarray]] = []

    def random(self, *args: Any, **kwargs: Any) -> Any:
        result = self.owner.random(*args, **kwargs)
        self.calls.append((args, kwargs, np.asarray(result).copy()))
        return result

    def get_state(self) -> Any:
        return self.owner.get_state()


def _assert_same_state(left: Any, right: Any) -> None:
    np.testing.assert_equal(left, right)


def _zero_capacity_state(process: pm.KarrProteinModificationProcess) -> dict[str, Any]:
    """One canonical folded precursor, zero free enzymes and zero allocation.

    This is a public-path consumption control, not an oracle replay state.
    The precursor WID and enzyme routes come from the actual constructor.
    """
    wid = next(w for w in process.unmodified_monomer_wids if w not in MIGRATED_WIDS)
    return {
        "protein": {
            "counts": dict.fromkeys(process.monomer_enzyme_wids, 0.0),
            "unmodified_counts": {wid: 1.0},
            "modified_counts": {},
        },
        "complex": {"counts": dict.fromkeys(process.complex_enzyme_wids, 0.0)},
        "substrates_allocated": {process.name: dict.fromkeys(process.substrate_wids, 0.0)},
    }


def test_public_update_private_owner_is_not_mt19937() -> None:
    """Source-family counterexample on the actual constructor/public path.

    No RNG replacement, oracle, synthetic draws, or expected output flux.
    Burns, seed changes/resets and rounding orientation cannot change the
    engine family. This condition excludes the demonstrated wrong family;
    it is deliberately not a numerical specification of an unknown prefix.
    """
    process = pm.KarrProteinModificationProcess({"rng_seed": 17})
    owner = process._rng
    process.next_update(1.0, _zero_capacity_state(process))
    assert process._rng is owner, "A public update must retain its private RNG owner"
    bit_generator = getattr(owner, "bit_generator", None)
    uses_mt19937 = isinstance(owner, np.random.RandomState) or isinstance(
        bit_generator, np.random.MT19937
    )
    assert not uses_mt19937, (
        "PM private RNG family mismatch: Process.m:282-290 constructs "
        "util.RandStream('mcg16807') and reset(this.seed), but the actual "
        f"public-update owner is {type(owner).__module__}.{type(owner).__name__} "
        "(MT19937). No draw burn, orientation change, or per-tick reset repairs "
        "this source-factory mismatch. Exact MATLAB prefix/seed mapping is "
        "not asserted by this necessary family-exclusion regression."
    )


@pytest.mark.parametrize(
    ("value", "uniform", "expected"),
    [
        pytest.param(
            0.48355554474724666, 0.7532401195921768, 0.0, id="measured-pair-rounds-down"
        ),
        pytest.param(0.25, 0.1, 1.0, id="below-fraction-rounds-up"),
        pytest.param(0.25, 0.25, 0.0, id="equality-is-not-less-than"),
        pytest.param(0.25, np.nextafter(0.25, 0.0), 1.0, id="just-below-fraction"),
        pytest.param(0.25, np.nextafter(0.25, 1.0), 0.0, id="just-above-fraction"),
        pytest.param(-1.25, 0.5, -1.0, id="negative-mod-positive"),
        pytest.param(-1.25, 0.75, -2.0, id="negative-equality-rounds-down"),
        pytest.param(0.0, 0.0, 0.0, id="zero-still-draws"),
        pytest.param(2.0, 0.0, 2.0, id="integer-still-draws"),
        pytest.param(-2.0, 0.9, -2.0, id="negative-integer-still-draws"),
        pytest.param(np.inf, 0.2, np.inf, id="infinity-still-draws"),
        pytest.param(-np.inf, 0.4, -np.inf, id="negative-infinity-still-draws"),
        pytest.param(np.nan, 0.6, np.nan, id="nan-still-draws"),
    ],
)
def test_unit_stochastic_round_uses_source_comparison_and_draws_every_entry(
    value: float, uniform: float, expected: float
) -> None:
    process = pm.KarrProteinModificationProcess({"rng_seed": 17})
    scripted = _ScriptedUniforms([uniform])
    process._rng = scripted
    values = np.array([value])
    before = values.copy()
    with np.errstate(invalid="ignore"):
        actual = process._stochastic_round_vector(values)
    np.testing.assert_equal(actual, np.array([expected]))
    np.testing.assert_equal(values, before)
    assert scripted.shapes == [(1,)]
    assert scripted.position == 1


def test_unit_vector_order_and_continuation_include_zero_integer_and_nonfinite_slots() -> None:
    """Column-vector linear order: no fractional-only compaction or reset."""
    process = pm.KarrProteinModificationProcess({"rng_seed": 17})
    scripted = _ScriptedUniforms([0.1, 0.9, 0.2, 0.3, 0.1, 0.8, 0.1, 0.7])
    process._rng = scripted
    # The fractional slots distinguish this order from reversed/compacted draws.
    first = np.array([0.0, 0.5, 2.0, np.inf, 0.25, -1.25])
    with np.errstate(invalid="ignore"):
        actual_first = process._stochastic_round_vector(first)
        actual_second = process._stochastic_round_vector(np.array([0.5, 0.5]))
    np.testing.assert_equal(actual_first, np.array([0.0, 0.0, 2.0, np.inf, 1.0, -2.0]))
    np.testing.assert_array_equal(actual_second, [1.0, 0.0])
    assert scripted.shapes == [(6,), (2,)]
    assert scripted.position == 8


def test_public_updates_keep_one_owner_and_full_zero_capacity_vectors() -> None:
    """Real public-path guard; not a stand-in for the persistent trace replay."""
    process = pm.KarrProteinModificationProcess({"rng_seed": 17})
    control = pm.KarrProteinModificationProcess({"rng_seed": 17})
    owner = process._rng
    observer = _ObservedUniforms(owner)
    process._rng = observer
    state = _zero_capacity_state(process)
    pristine_state = deepcopy(state)
    n_active = len(process.unmodified_monomer_wids)
    initial_state = deepcopy(owner.get_state())
    for tick in range(3):
        before = deepcopy(owner.get_state())
        actual = process.next_update(1.0, state)
        expected = control.next_update(1.0, deepcopy(pristine_state))
        assert actual == expected == {}, (tick, "zero capacity must not create chemistry")
        assert process._rng is observer
        assert observer.owner is owner
        assert len(observer.calls) == tick + 1, "One vector round, no weighted selection"
        args, kwargs, draws = observer.calls[-1]
        assert args == ((n_active,),) and kwargs == {}
        assert draws.shape == (n_active,)
        _assert_same_state(owner.get_state(), control._rng.get_state())
        # A full vector must be consumed even though every capacity rounds to zero.
        assert repr(before) != repr(owner.get_state()), "Public update reset/elided RNG draws"
        assert state == pristine_state
    assert repr(initial_state) != repr(owner.get_state())


@pytest.mark.parametrize("seed", [0, 1, 17])
def test_unit_private_seed_reproducibility_chunking_and_global_rng_isolation(seed: int) -> None:
    """Seed/isolation guard only; no invented MATLAB seed-to-state mapping."""
    global_before = deepcopy(np.random.get_state())
    first = pm.KarrProteinModificationProcess({"rng_seed": seed})
    second = pm.KarrProteinModificationProcess({"rng_seed": seed})
    interloper = pm.KarrProteinModificationProcess({"rng_seed": seed + 1})
    assert first._rng is not second._rng and first._rng is not interloper._rng
    first_initial = deepcopy(first._rng.get_state())
    assert repr(first_initial) != repr(interloper._rng.get_state())
    prefix = first._rng.random(3)
    interloper._rng.random(19)
    suffix = first._rng.random(5)
    np.testing.assert_array_equal(np.concatenate([prefix, suffix]), second._rng.random(8))
    _assert_same_state(first._rng.get_state(), second._rng.get_state())
    _assert_same_state(global_before, np.random.get_state())
