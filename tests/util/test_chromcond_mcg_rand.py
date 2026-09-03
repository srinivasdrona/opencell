from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

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

from opencell.util.chromcond_mcg_rand import ChromCondMcgRandStream

# ChromosomeCondensation-only MATLAB RandStream('mcg16807') shim tests.
# Split out from tests/util/test_matlab_rng.py (which stays byte-for-byte
# identical to main) because ChromCondMcgRandStream lives in its own module
# (opencell/util/chromcond_mcg_rand.py) -- see that module's docstring for
# why: opencell/util/matlab_rng.py's file hash is a registered L2.2
# provenance dependency for ProteinTranslocation's accepted evidence, and
# this shim must never touch that file.
#
# Sources for vectors used in this file:
# - Live MATLAB R2026a `RandStream('mcg16807')` probes captured locally for:
#   seed 0 / seed 1 startup, restored state 1279689633, randi, randperm, and the
#   seed1 10000th uniform. These confirm MATLAB's exposed `State` is not the raw
#   Park-Miller state.


def test_mcg16807_seed1_first10_matches_matlab_r2026a() -> None:
    s = ChromCondMcgRandStream(1)
    got = s.rand(10)
    expected = np.array(
        [
            0.5129089357857168,
            0.46048375054285107,
            0.35039537369757673,
            0.09504573517248302,
            0.43367104392204014,
            0.7092351977290754,
            0.11596823256275059,
            0.07808468215078333,
            0.36925290821550965,
            0.03362837807909984,
        ],
        dtype=np.float64,
    )
    np.testing.assert_allclose(got, expected, rtol=0.0, atol=1e-15)
    assert s.get_state()["mcg_state"] == 1_867_023_437


def test_mcg16807_seed0_first5_matches_matlab_r2026a_default_state() -> None:
    s = ChromCondMcgRandStream(0)
    assert s.get_state()["mcg_state"] == 931_316_785
    got = s.rand(5)
    expected = np.array(
        [
            0.21895918632809036,
            0.04704461621448613,
            0.678864716868319,
            0.6792964058366122,
            0.9346928959408276,
        ],
        dtype=np.float64,
    )
    np.testing.assert_allclose(got, expected, rtol=0.0, atol=1e-15)
    assert s.get_state()["mcg_state"] == 72_185_764


def test_mcg16807_restored_state_matches_matlab_r2026a() -> None:
    s = ChromCondMcgRandStream(0)
    s.set_state({"generator": "mcg16807", "seed": 0, "mcg_state": 1_279_689_633})
    got = s.rand(10)
    expected = np.array(
        [
            0.9016734989833432,
            0.4264974130440958,
            0.14202103211638573,
            0.9474867800937441,
            0.4103130355525361,
            0.1311885314673132,
            0.8856483711328581,
            0.0921736299489502,
            0.16219855200601674,
            0.0710635651233902,
        ],
        dtype=np.float64,
    )
    np.testing.assert_allclose(got, expected, rtol=0.0, atol=1e-15)
    assert s.get_state()["mcg_state"] == 476_350_744


def test_mcg16807_seed1_10000th_value_matches_matlab_r2026a() -> None:
    s = ChromCondMcgRandStream(1)
    got = float(s.rand(10000)[-1])
    expected = 0.6958461295328318
    assert got == pytest.approx(expected, rel=0.0, abs=1e-15)


def test_mcg16807_randi_seed1_first10_matches_matlab_r2026a() -> None:
    s = ChromCondMcgRandStream(1)
    got = s.randi(10, 10)
    expected = np.array([6, 5, 4, 1, 5, 8, 2, 1, 4, 1], dtype=np.int64)
    np.testing.assert_array_equal(got, expected)


def test_mcg16807_randperm_seed1_first5_matches_matlab_r2026a() -> None:
    s = ChromCondMcgRandStream(1)
    got = s.randperm(5)
    expected = np.array([4, 3, 5, 2, 1], dtype=np.int64)
    np.testing.assert_array_equal(got, expected)


def test_mcg16807_weighted_randsample_seed1_matches_threshold_mirror() -> None:
    s = ChromCondMcgRandStream(1)
    got = s.randsample(3, 5, True, np.array([1.0, 2.0, 3.0], dtype=np.float64))
    expected = np.array([3, 2, 2, 1, 2], dtype=np.int64)
    np.testing.assert_array_equal(got, expected)


def test_mcg16807_single_weighted_randsample_still_consumes_one_draw() -> None:
    s = ChromCondMcgRandStream(1)
    got = s.randsample(4, 1, False, np.array([0.0, 0.0, 5.0, 0.0], dtype=np.float64))
    np.testing.assert_array_equal(got, np.array([3], dtype=np.int64))
    next_uniform = float(s.rand())
    expected_next_uniform = 0.46048375054285107
    assert next_uniform == pytest.approx(expected_next_uniform, rel=0.0, abs=1e-15)


def test_mcg16807_state_roundtrip_after_rand50_matches_following_rand10() -> None:
    s = ChromCondMcgRandStream(1)
    _ = s.rand(50)
    state = s.get_state()

    s2 = ChromCondMcgRandStream(7)
    s2.set_state(state)

    got1 = s.rand(10)
    got2 = s2.rand(10)
    np.testing.assert_array_equal(got1, got2)
