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

from opencell.util.matlab_rng import MatlabRandStream


# Sources for vectors used in this file:
# - MATLAB rand seed vectors + seed-0/5489 behavior:
#   https://walkingrandomly.com/?p=5479
#   https://walkingrandomly.com/?p=5480
# - MATLAB randn(seed=22) published contrast values:
#   https://github.com/jonasrauber/randn-matlab-python
# - MATLAB randperm startup sequence examples:
#   https://blogs.mathworks.com/matlab/2022/06/07/6-3-7-8-5-1-2-4-9-10-or-a-story-of-surprise-about-randomness/
#   https://groups.google.com/g/comp.soft-sys.matlab/c/FojUKhI8om4
# - MathWorks randi first-5 example (with saved rng state):
#   https://www.mathworks.com/help/matlab/ref/double.randi.html
# - Reference implementation used as secondary oracle for mt19937ar/randn internals:
#   https://github.com/KrepakVitaly/py_matlab_randn


def test_rand_seed0_first10_matches_published_values() -> None:
    s = MatlabRandStream(0)
    got = s.rand(10)
    expected = np.array(
        [
            0.8147236863931789,
            0.9057919370756192,
            0.12698681629350606,
            0.9133758561390194,
            0.6323592462254095,
            0.09754040499940952,
            0.2784982188670484,
            0.5468815192049838,
            0.9575068354342976,
            0.9648885351992765,
        ],
        dtype=np.float64,
    )
    np.testing.assert_allclose(got, expected, rtol=0.0, atol=1e-15)


def test_rand_seed0_scalar_matches_published_first_value() -> None:
    s = MatlabRandStream(0)
    got = float(s.rand())
    expected = 0.8147236863931789
    assert got == pytest.approx(expected, rel=0.0, abs=1e-15)


def test_rand_seed1_first10_matches_published_values() -> None:
    s = MatlabRandStream(1)
    got = s.rand(10)
    expected = np.array(
        [
            0.417022004702574,
            0.7203244934421581,
            0.00011437481734488664,
            0.30233257263183977,
            0.14675589081711304,
            0.0923385947687978,
            0.1862602113776709,
            0.34556072704304774,
            0.39676747423066994,
            0.538816734003357,
        ],
        dtype=np.float64,
    )
    np.testing.assert_allclose(got, expected, rtol=0.0, atol=1e-15)


def test_rand_seed42_len1000_matches_nonzero_seed_compatibility_claim() -> None:
    # walkingrandomly verifies non-zero seeds match NumPy MT19937 for rand.
    s = MatlabRandStream(42)
    got = s.rand(1000)
    expected = np.random.RandomState(42).random_sample(1000)
    np.testing.assert_array_equal(got, expected)


def test_rand_column_major_shape_order_matches_matlab() -> None:
    s = MatlabRandStream(0)
    got = s.rand(2, 3)
    expected = np.array(
        [
            [0.8147236863931789, 0.12698681629350606, 0.6323592462254095],
            [0.9057919370756192, 0.9133758561390194, 0.09754040499940952],
        ],
        dtype=np.float64,
    )
    np.testing.assert_allclose(got, expected, rtol=0.0, atol=1e-15)


def test_randn_seed22_first5_matches_published_values() -> None:
    s = MatlabRandStream(22)
    got = s.randn(5)
    expected = np.array(
        [-1.1192534295917405, -0.07287663436965251, -0.28473464132532067, 1.5110600269585672, -1.511159557953716],
        dtype=np.float64,
    )
    np.testing.assert_allclose(got, expected, rtol=0.0, atol=1e-12)


@pytest.mark.xfail(reason="TODO: confirm randn(seed=0) first-10 against primary MathWorks source")
def test_randn_seed0_first10_pending_primary_source_confirmation() -> None:
    s = MatlabRandStream(0)
    got = s.randn(10)
    expected = np.array(
        [
            0.5376671395461,
            1.8338850145950865,
            -2.258846861003648,
            0.8621733203681206,
            0.3187652398589808,
            -1.3076882963052734,
            -0.43359202230568356,
            0.3426244665386499,
            3.5783969397257605,
            2.769437029884877,
        ],
        dtype=np.float64,
    )
    np.testing.assert_allclose(got, expected, rtol=0.0, atol=1e-15)


@pytest.mark.xfail(reason="TODO: confirm randn column-major golden matrix against primary MathWorks source")
def test_randn_column_major_shape_seed0_pending_primary_source_confirmation() -> None:
    s = MatlabRandStream(0)
    got = s.randn(2, 3)
    expected = np.array(
        [
            [0.5376671395461, -2.258846861003648, 0.3187652398589808],
            [1.8338850145950865, 0.8621733203681206, -1.3076882963052734],
        ],
        dtype=np.float64,
    )
    np.testing.assert_allclose(got, expected, rtol=0.0, atol=1e-15)


def test_randn_mean_and_variance_sanity() -> None:
    s = MatlabRandStream(0)
    draws = s.randn(10000)
    assert abs(float(np.mean(draws))) < 0.05
    assert abs(float(np.var(draws)) - 1.0) < 0.05


def test_randi_seed0_first20_matches_golden_vector() -> None:
    s = MatlabRandStream(0)
    got = s.randi(10, 20)
    expected = np.array([9, 10, 2, 10, 7, 1, 3, 6, 10, 10, 2, 10, 10, 5, 9, 2, 5, 10, 8, 10], dtype=np.int64)
    np.testing.assert_array_equal(got, expected)


def test_randi_seed0_first5_matches_mathworks_example() -> None:
    s = MatlabRandStream(0)
    got = s.randi(10, 5)
    expected = np.array([9, 10, 2, 10, 7], dtype=np.int64)
    np.testing.assert_array_equal(got, expected)


def test_randi_seed1_first10_matches_golden_vector() -> None:
    s = MatlabRandStream(1)
    got = s.randi(10, 10)
    expected = np.array([5, 8, 1, 4, 2, 1, 2, 4, 4, 6], dtype=np.int64)
    np.testing.assert_array_equal(got, expected)


def test_randi_seed42_matches_nonzero_seed_compatibility_claim() -> None:
    # walkingrandomly verifies non-zero seeds match NumPy MT19937 for rand.
    # randi is defined here as floor(imax * rand) + 1 using that shared stream.
    s = MatlabRandStream(42)
    got = s.randi(10, 10)
    expected = np.floor(np.random.RandomState(42).random_sample(10) * 10).astype(np.int64) + 1
    np.testing.assert_array_equal(got, expected)


def test_randi_column_major_shape_seed0() -> None:
    s = MatlabRandStream(0)
    got = s.randi(10, 2, 3)
    expected = np.array([[9, 2, 7], [10, 10, 1]], dtype=np.int64)
    np.testing.assert_array_equal(got, expected)


def test_randperm_seed0_first_three_calls_match_published_sequences() -> None:
    s = MatlabRandStream(0)
    got1 = s.randperm(10)
    got2 = s.randperm(10)
    got3 = s.randperm(10)
    np.testing.assert_array_equal(got1, np.array([6, 3, 7, 8, 5, 1, 2, 4, 9, 10], dtype=np.int64))
    np.testing.assert_array_equal(got2, np.array([6, 1, 7, 4, 9, 5, 8, 3, 10, 2], dtype=np.int64))
    np.testing.assert_array_equal(got3, np.array([2, 10, 8, 9, 1, 5, 7, 6, 3, 4], dtype=np.int64))


@pytest.mark.xfail(reason="TODO: confirm randperm(100,5) golden vector against primary MathWorks source")
def test_randperm_seed0_n100_k5_pending_primary_source_confirmation() -> None:
    s = MatlabRandStream(0)
    got = s.randperm(100, 5)
    expected = np.array([99, 32, 40, 22, 34], dtype=np.int64)
    np.testing.assert_array_equal(got, expected)


def test_randperm_k_zero_returns_empty() -> None:
    s = MatlabRandStream(0)
    got = s.randperm(10, 0)
    np.testing.assert_array_equal(got, np.array([], dtype=np.int64))


def test_state_roundtrip_after_rand50_matches_following_rand10() -> None:
    s = MatlabRandStream(0)
    _ = s.rand(50)
    state = s.get_state()

    s2 = MatlabRandStream(1)
    s2.set_state(state)

    got1 = s.rand(10)
    got2 = s2.rand(10)
    np.testing.assert_array_equal(got1, got2)
