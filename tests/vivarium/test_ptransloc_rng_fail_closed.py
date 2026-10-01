"""Tests for ProteinTranslocation RNG fail-closed behavior (Reviewer Finding B4).

A ProteinTranslocation process must reject a non-MatlabRandStream/non-one-based RNG
before mutating state; autonomous/chassis scripts must seed/preserve MatlabRandStream
rather than install NumPy generators.
"""

from __future__ import annotations

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


def test_b4_scripts_do_not_replace_translocation_rng_with_numpy() -> None:
    """B4 static/runtime contract: scripts/l2_4_verify_conservation.py and

    scripts/run_chassis_v6_32400t.py must preserve MatlabRandStream for
    KarrProteinTranslocationProcess, never replace it with np.random.default_rng.
    """
    scripts_to_check = [
        _REPO_ROOT / "scripts" / "l2_4_verify_conservation.py",
        _REPO_ROOT / "scripts" / "run_chassis_v6_32400t.py",
    ]

    violations = []
    for script_path in scripts_to_check:
        src = script_path.read_text(encoding="utf-8")
        if "entity._rng = np.random.default_rng" in src:
            has_protection = (
                "MatlabRandStream" in src
                or "isinstance(entity, KarrProteinTranslocationProcess)" in src
                or 'isinstance(getattr(entity, "_rng", None), MatlabRandStream)' in src
                or 'not isinstance(getattr(entity, "_rng", None), MatlabRandStream)' in src
                or 'entity.name != "karr_protein_translocation"' in src
                or 'hasattr(entity._rng, "randperm")' in src
            )
            if not has_protection:
                violations.append(
                    f"{script_path.name}: blindly replaces entity._rng with np.random.default_rng "
                    "without preserving MatlabRandStream for ProteinTranslocation"
                )

    assert not violations, (
        "Claim B4 violation: autonomous/chassis scripts must seed/preserve MatlabRandStream "
        "rather than install NumPy generators:\n" + "\n".join(violations)
    )
