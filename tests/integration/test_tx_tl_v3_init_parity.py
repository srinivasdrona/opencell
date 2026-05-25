from __future__ import annotations

from pathlib import Path
import sys

import numpy as np

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

from opencell.validation.replay import load_per_process_fixture
from opencell.vivarium.karr_composite import build_karr_chassis_v6

_TRANSLATION_MONOMERS_KEY = "fixture__monomers"


def _load_translation_fixture_monomers() -> np.ndarray:
    fixture = load_per_process_fixture("Translation")
    npz_path = fixture.fixture_path.with_name("Translation.npz")
    with np.load(npz_path, allow_pickle=False) as payload:
        if _TRANSLATION_MONOMERS_KEY not in payload:
            raise KeyError(f"Missing '{_TRANSLATION_MONOMERS_KEY}' in {npz_path}")
        return np.asarray(payload[_TRANSLATION_MONOMERS_KEY], dtype=float).reshape(-1)


def test_translation_fixture_tick0_monomers_are_zero() -> None:
    monomers = _load_translation_fixture_monomers()
    assert monomers.shape == (482,)
    assert np.count_nonzero(monomers) == 0


def test_v6_translation_t0_matches_fixture_when_seeded_from_fixture() -> None:
    fixture_monomers = _load_translation_fixture_monomers()
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0, seed_from_fixture=True)

    translation = composite["processes"]["karr_translation"]
    unprocessed = composite["state"]["protein"]["unprocessed_counts"]
    chassis_monomers = np.asarray(
        [float(unprocessed.get(pid, 0.0)) for pid in translation.protein_ids], dtype=float
    )

    assert chassis_monomers.shape == fixture_monomers.shape
    np.testing.assert_array_equal(chassis_monomers, fixture_monomers)


def test_v6_translation_t0_can_opt_out_of_fixture_seeding() -> None:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0, seed_from_fixture=False)

    translation = composite["processes"]["karr_translation"]
    unprocessed = composite["state"]["protein"]["unprocessed_counts"]
    chassis_monomers = np.asarray(
        [float(unprocessed.get(pid, 0.0)) for pid in translation.protein_ids], dtype=float
    )

    assert np.count_nonzero(chassis_monomers) > 0
    assert float(chassis_monomers.sum()) > 0.0
