"""Predicate library ported from CovertLab/vEcoli ecoli/library/data_predicates.py at 2026-05-25. Used by per-process biology-firing tests in opencell.validation."""

from collections import Counter

import numpy as np
from scipy.stats import chisquare, poisson


def strictly_increasing(arr: np.ndarray) -> bool:
    return all(a < b for a, b in zip(arr, arr[1:], strict=False))


def strictly_decreasing(arr: np.ndarray) -> bool:
    return all(a > b for a, b in zip(arr, arr[1:], strict=False))


def monotonically_increasing(arr: np.ndarray) -> bool:
    return all(a <= b for a, b in zip(arr, arr[1:], strict=False))


def monotonically_decreasing(arr: np.ndarray) -> bool:
    return all(a >= b for a, b in zip(arr, arr[1:], strict=False))


def all_positive(arr: np.ndarray) -> bool:
    return np.all(arr > 0)


def all_negative(arr: np.ndarray) -> bool:
    return np.all(arr < 0)


def all_nonnegative(arr: np.ndarray) -> bool:
    return np.all(arr >= 0)


def all_nonpositive(arr: np.ndarray) -> bool:
    return np.all(arr <= 0)


def approx_poisson(
    arr: np.ndarray, rate: float | None = None, significance: float = 0.05, verbose: bool = False
) -> bool:
    """
    Test whether data appears to follow Poisson distribution, using Chi-sq goodness of fit.
    Does not do particularly well comparing poisson data of rate r_1 vs. poisson distribution of rate r_2.
    Args:
        arr: 1D array where index i corresponds the number of events observed in interval i.
        rate: rate (lambda) of the Poisson distribution against which to compare. If None, rate is estimated from the data.
        significance: for p > significance, fail to reject that the data is not Poisson-distributed.
        verbose: if True, prints estimated rate, and results (chi-sq, p-value) of the goodness-of-fit test.
    """

    if rate is None:
        rate = np.mean(arr)

    counts = Counter(list(arr))
    counts = [counts.get(i, 0) for i in range(max(arr) + 1)]

    res = chisquare(
        np.array(counts) / sum(counts),
        poisson(rate).pmf(range(len(counts)))
        / sum(poisson(rate).pmf(range(len(counts)))),
    )

    if verbose:
        print(f"Estimated rate (lambda): {rate}")
        print(f"Chi-sq: {res[0]}")
        print(f"p: {res[1]}")

    return res[1] > significance


def test_data_predicates() -> None:
    assert strictly_increasing(np.array([1, 2, 3])) and not strictly_increasing(
        np.array([1, 1, 2])
    )
    assert strictly_decreasing(np.array([3, 2, 1])) and not strictly_decreasing(
        np.array([3, 3, 2])
    )
    assert monotonically_increasing(
        np.array([1, 1, 2])
    ) and not monotonically_increasing(np.array([1, 0, 1]))
    assert monotonically_decreasing(
        np.array([2, 2, 1])
    ) and not monotonically_decreasing(np.array([1, 2, 1]))
    assert all_positive(np.array([1, 2, 3])) and not all_positive(np.array([1, 1, 0]))
    assert all_negative(np.array([-1, -2, -3])) and not all_negative(np.array([-1, -1, 0]))
    assert all_nonnegative(np.array([0, 1, 2])) and not all_nonnegative(np.array([-1, 0, 1]))
    assert all_nonpositive(np.array([0, -1, -2])) and not all_nonpositive(np.array([-1, 0, 1]))

    poisson_data = np.random.poisson(lam=2, size=1000)
    geom_data = np.random.geometric(p=0.1, size=1000)
    assert approx_poisson(poisson_data) and not approx_poisson(geom_data)

    print("Passed all tests.")


if __name__ == "__main__":
    test_data_predicates()
