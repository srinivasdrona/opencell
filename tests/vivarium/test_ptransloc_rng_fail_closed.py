"""Tests for ProteinTranslocation RNG fail-closed behavior (Reviewer Finding B4).

A ProteinTranslocation process must reject a non-MatlabRandStream/non-one-based RNG
before mutating state; autonomous/chassis scripts must seed/preserve MatlabRandStream
rather than install NumPy generators.
"""

from __future__ import annotations

import importlib.util
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

from opencell.util.matlab_rng import MatlabRandStream
from opencell.vivarium.karr_protein_translocation import KarrProteinTranslocationProcess


def test_b4_rejects_non_matlab_rng_before_mutating_state() -> None:
    """B4 contract: A ProteinTranslocation process must reject a non-MatlabRandStream /

    non-one-based RNG (e.g. np.random.Generator) before mutating state.
    Zero-based fallback is corrupt and must fail closed.
    """
    proc = KarrProteinTranslocationProcess({})
    # Install non-MatlabRandStream / numpy generator
    proc._rng = np.random.default_rng(0)

    state: dict[str, Any] = {
        "substrates": {wid: 1000.0 for wid in proc.substrate_wids},
        "complex": {"counts": {wid: 1000.0 for wid in proc.complex_count_wids}},
        "protein": {
            "counts": {"MG_297_MONOMER": 1000.0},
            "compartment_counts": {
                "processed_i": {
                    wid: (
                        {"c": 1.0, "d": 0.0, "e": 0.0, "m": 0.0, "tc": 0.0, "tm": 0.0}
                        if wid == "MG_014_MONOMER"
                        else {"c": 0.0, "d": 0.0, "e": 0.0, "m": 0.0, "tc": 0.0, "tm": 0.0}
                    )
                    for wid in proc.translocatable_wids
                }
            },
        },
        "requests": {proc.name: {wid: 0.0 for wid in proc.request_wids}},
        "substrates_allocated": {
            proc.name: {
                proc.atp_wid: 50.0,
                proc.gtp_wid: 0.0,
                proc.h2o_wid: 50.0,
                proc.adp_wid: 0.0,
                proc.gdp_wid: 0.0,
                proc.pi_wid: 0.0,
                proc.h_wid: 0.0,
            }
        },
    }

    # Must fail closed: raise TypeError or ValueError
    with pytest.raises((TypeError, ValueError), match=r"(?i)matlab|randstream|one-based"):
        proc.next_update(1.0, state)


def test_b4_reviewer_seed0_numpy_draw_demonstrates_corruption() -> None:
    """B4 demonstration: Reproduce reviewer seed-0 draw [2, 0, 1] on the three-WID

    discriminating case and prove that zero-based permutation cannot be accepted by
    1-based searchsorted.
    """
    rng = np.random.default_rng(0)
    perm = rng.permutation(3)
    assert list(perm) == [2, 0, 1], f"Expected reviewer draw [2, 0, 1], got {list(perm)}"

    # Three discriminating WIDs with 1 copy each in fixture order:
    # [MG_014 (pos 0), MG_191 (pos 49), MG_468 (pos 118)]
    # Cumulative counts under fixture order: [1, 2, 3]
    cumulative_counts = np.array([1, 2, 3], dtype=np.int64)

    # In MATLAB: randperm(3) draws from {1, 2, 3}:
    # draw 1 -> searchsorted <= 1 -> index 0 (MG_014)
    # draw 2 -> searchsorted <= 2 -> index 1 (MG_191)
    # draw 3 -> searchsorted <= 3 -> index 2 (MG_468)
    # Each monomer has a unique 1:1 mapping.

    # In NumPy: draw from {0, 1, 2}: [2, 0, 1]
    # draw 2 -> searchsorted <= 1 (2 <= 2) -> index 1 (MG_191)
    # draw 0 -> searchsorted <= 0 (0 <= 1) -> index 0 (MG_014)
    # draw 1 -> searchsorted <= 0 (1 <= 1) -> index 0 (MG_014)
    indices = [int(np.searchsorted(cumulative_counts, int(x), side="left")) for x in perm]
    assert indices == [1, 0, 0], f"Expected corrupted indices [1, 0, 0], got {indices}"

    # Corruption proof:
    # 1. Index 0 (MG_014) is mapped TWICE (for both 0 and 1).
    # 2. Index 2 (MG_468) is NEVER reached (max draw 2 <= cumulative 2).
    # 3. This corrupts copy selection and monomer arrival distributions.
    assert indices.count(0) == 2, "MG_014 was not duplicated"
    assert 2 not in indices, "MG_468 was unexpectedly reached"


class _DummyMatlabEntity(KarrProteinTranslocationProcess):
    """Dummy entity with a real MatlabRandStream for testing seeder behavior."""

    def __init__(self, seed: int = 12345) -> None:
        super().__init__({"rng_seed": seed})


class _DummyOrdinaryEntity:
    """Dummy entity with an ordinary NumPy generator for testing seeder behavior."""

    def __init__(self, seed: int = 54321) -> None:
        self.name = "dummy_ordinary_process"
        self.parameters = {"rng_seed": seed}
        self._rng = np.random.default_rng(seed)


def _verify_collector_preserves_matlab_rng(collector_cls: type) -> None:
    """Behavioral/runtime verifier: assert collector._seed_entities preserves MatlabRandStream

    and does not replace it with np.random.default_rng.
    """
    instance = collector_cls.__new__(collector_cls)
    matlab_entity = _DummyMatlabEntity(seed=12345)
    ordinary_entity = _DummyOrdinaryEntity(seed=54321)
    orig_matlab_rng = matlab_entity._rng
    orig_numpy_rng = ordinary_entity._rng

    instance._entities = {
        "karr_protein_translocation": matlab_entity,
        "dummy_ordinary_process": ordinary_entity,
    }
    instance._seed_entities(seed=42)

    # 1. Ordinary entity must have an appropriate NumPy generator, freshly reseeded
    if not isinstance(ordinary_entity._rng, np.random.Generator):
        raise AssertionError(
            f"Expected ordinary entity _rng to be np.random.Generator, got {type(ordinary_entity._rng)}"
        )
    if ordinary_entity._rng is orig_numpy_rng:
        raise AssertionError("Ordinary entity NumPy generator was not freshly reseeded")

    # 2. Matlab entity must still have a freshly seeded MatlabRandStream, NEVER a NumPy Generator
    if isinstance(matlab_entity._rng, np.random.Generator):
        raise AssertionError(
            "Matlab entity _rng was replaced with a NumPy Generator; must preserve MatlabRandStream"
        )
    if not isinstance(matlab_entity._rng, MatlabRandStream):
        raise AssertionError(
            f"Expected Matlab entity _rng to be MatlabRandStream, got {type(matlab_entity._rng)}"
        )
    reseeded = (matlab_entity._rng is not orig_matlab_rng) or (
        getattr(matlab_entity._rng, "_seed", None) != 12345
    )
    if not reseeded:
        raise AssertionError("Matlab entity MatlabRandStream was not freshly reseeded")


def _load_script_module(script_rel_path: str, module_name: str) -> Any:
    script_path = _REPO_ROOT / script_rel_path
    spec = importlib.util.spec_from_file_location(module_name, str(script_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module spec from {script_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_b4_scripts_do_not_replace_translocation_rng_with_numpy() -> None:
    """B4 behavioral/runtime proof: scripts/l2_4_verify_conservation.py and

    scripts/run_chassis_v6_32400t.py must preserve MatlabRandStream for
    KarrProteinTranslocationProcess, never replace it with np.random.default_rng.
    """
    l2_4_mod = _load_script_module(
        "scripts/l2_4_verify_conservation.py", "scripts_l2_4_verify_conservation"
    )
    conservation_collector_cls = getattr(l2_4_mod, "ConservationCollector")
    _verify_collector_preserves_matlab_rng(conservation_collector_cls)

    chassis_mod = _load_script_module(
        "scripts/run_chassis_v6_32400t.py", "scripts_run_chassis_v6_32400t"
    )
    diagnostic_collector_cls = getattr(chassis_mod, "DiagnosticCollector")
    _verify_collector_preserves_matlab_rng(diagnostic_collector_cls)


class _PlantedBrokenSeederWithUnusedMatlabTokenCollector:
    """Planted broken seeder that contains an unused MatlabRandStream token / import,

    but blindly overwrites every _rng with np.random.default_rng.
    The verifier must reject it despite the token presence.
    """

    _unused_token = MatlabRandStream

    def _seed_entities(self, *, seed: int) -> None:
        names = sorted(self._entities.keys())
        children = np.random.SeedSequence(int(seed)).spawn(len(names))
        for idx, name in enumerate(names):
            entity = self._entities[name]
            child = children[idx]
            entity_seed = int(child.generate_state(1, dtype=np.uint32)[0])
            params = getattr(entity, "parameters", None)
            if isinstance(params, dict) and "rng_seed" in params:
                params["rng_seed"] = entity_seed
            if hasattr(entity, "_rng"):
                entity._rng = np.random.default_rng(entity_seed)


def test_b4_planted_broken_seeder_canary_rejected() -> None:
    """Canary: Prove the verifier rejects a planted broken seeder that blindly overwrites

    _rng with np.random.default_rng, even when an unused MatlabRandStream token is present.
    """
    with pytest.raises(
        AssertionError,
        match=r"(?i)Matlab entity _rng was replaced with a NumPy Generator|must preserve MatlabRandStream",
    ):
        _verify_collector_preserves_matlab_rng(
            _PlantedBrokenSeederWithUnusedMatlabTokenCollector
        )
