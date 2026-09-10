from __future__ import annotations

import sys
from pathlib import Path

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

from tests.vivarium import _l2_2_dnas_runner_helpers as runner_helpers  # noqa: E402


class _FakeDNASProcess:
    def __init__(self, seed: int) -> None:
        self.seed = int(seed)
        self._rng = np.random.default_rng(int(seed))

    def draw(self) -> int:
        return int(self._rng.integers(0, 2**31 - 1))


@pytest.fixture(autouse=True)
def _reset_dna_supercoiling_persistence() -> None:
    runner_helpers.reset_dna_supercoiling_persistent_processes()
    yield
    runner_helpers.reset_dna_supercoiling_persistent_processes()


def _patch_fake_constructor(monkeypatch: pytest.MonkeyPatch) -> dict[int, int]:
    constructions: dict[int, int] = {}

    def _ctor(seed: int) -> _FakeDNASProcess:
        constructions[int(seed)] = constructions.get(int(seed), 0) + 1
        return _FakeDNASProcess(int(seed))

    monkeypatch.setattr(runner_helpers, "_construct_dna_supercoiling_process", _ctor)
    return constructions


def _draw_sequence(seed: int, ticks: list[int]) -> list[int]:
    draws: list[int] = []
    for tick in ticks:
        process = runner_helpers._DNA_SUPERCOILING_PERSISTENT_PROCESSES.get(  # noqa: SLF001
            seed=seed,
            tick=tick,
        )
        draws.append(process.draw())
    return draws


def test_dna_supercoiling_constructs_once_per_seed(monkeypatch: pytest.MonkeyPatch) -> None:
    constructions = _patch_fake_constructor(monkeypatch)

    first = runner_helpers._DNA_SUPERCOILING_PERSISTENT_PROCESSES.get(seed=7, tick=0)  # noqa: SLF001
    second = runner_helpers._DNA_SUPERCOILING_PERSISTENT_PROCESSES.get(seed=7, tick=1)  # noqa: SLF001
    third = runner_helpers._DNA_SUPERCOILING_PERSISTENT_PROCESSES.get(seed=7, tick=2)  # noqa: SLF001
    other = runner_helpers._DNA_SUPERCOILING_PERSISTENT_PROCESSES.get(seed=11, tick=0)  # noqa: SLF001

    assert first is second
    assert second is third
    assert other is not first
    assert constructions == {7: 1, 11: 1}


def test_dna_supercoiling_reruns_are_deterministic_after_tick_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructions = _patch_fake_constructor(monkeypatch)

    first_run = _draw_sequence(seed=13, ticks=[0, 1, 2, 3])
    second_run = _draw_sequence(seed=13, ticks=[0, 1, 2, 3])

    assert first_run == second_run
    assert constructions == {13: 2}


def test_dna_supercoiling_different_seeds_keep_independent_streams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructions = _patch_fake_constructor(monkeypatch)

    seed3_isolated = _draw_sequence(seed=3, ticks=[0, 1, 2])
    runner_helpers.reset_dna_supercoiling_persistent_processes()
    seed4_isolated = _draw_sequence(seed=4, ticks=[0, 1, 2])

    runner_helpers.reset_dna_supercoiling_persistent_processes()
    interleaved_seed3: list[int] = []
    interleaved_seed4: list[int] = []
    for tick in range(3):
        interleaved_seed3.extend(_draw_sequence(seed=3, ticks=[tick]))
        interleaved_seed4.extend(_draw_sequence(seed=4, ticks=[tick]))

    assert seed3_isolated == interleaved_seed3
    assert seed4_isolated == interleaved_seed4
    assert constructions == {3: 2, 4: 2}


def test_dna_supercoiling_tick_order_changes_rng_trajectory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fake_constructor(monkeypatch)

    ordered = _draw_sequence(seed=23, ticks=[0, 1])
    runner_helpers.reset_dna_supercoiling_persistent_processes()
    direct_tick1 = _draw_sequence(seed=23, ticks=[1])

    assert ordered[1] != direct_tick1[0]


def test_dna_supercoiling_interleaved_seeds_do_not_contaminate_one_another(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fake_constructor(monkeypatch)

    isolated = _draw_sequence(seed=31, ticks=[0, 1, 2])

    runner_helpers.reset_dna_supercoiling_persistent_processes()
    interleaved = []
    interleaved.extend(_draw_sequence(seed=31, ticks=[0]))
    _draw_sequence(seed=99, ticks=[0, 1])
    interleaved.extend(_draw_sequence(seed=31, ticks=[1, 2]))

    assert isolated == interleaved
