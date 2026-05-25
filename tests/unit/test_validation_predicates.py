import numpy as np

from opencell.validation.predicates import (
    all_negative,
    all_nonnegative,
    all_nonpositive,
    all_positive,
    monotonically_decreasing,
    monotonically_increasing,
    strictly_decreasing,
    strictly_increasing,
)


def test_strictly_increasing_positive_case():
    assert strictly_increasing(np.array([1, 2, 3, 5]))


def test_strictly_increasing_negative_case():
    assert not strictly_increasing(np.array([1, 2, 2, 3]))


def test_strictly_increasing_edge_cases():
    assert strictly_increasing(np.array([]))
    assert strictly_increasing(np.array([42]))
    assert not strictly_increasing(np.array([7, 7, 7]))


def test_monotonically_increasing_positive_case():
    assert monotonically_increasing(np.array([1, 1, 2, 2, 3]))


def test_monotonically_increasing_negative_case():
    assert not monotonically_increasing(np.array([1, 2, 1]))


def test_monotonically_increasing_edge_cases():
    assert monotonically_increasing(np.array([]))
    assert monotonically_increasing(np.array([9]))
    assert monotonically_increasing(np.array([4, 4, 4]))


def test_strictly_decreasing_positive_case():
    assert strictly_decreasing(np.array([5, 4, 2, 1]))


def test_strictly_decreasing_negative_case():
    assert not strictly_decreasing(np.array([3, 2, 2, 1]))


def test_strictly_decreasing_edge_cases():
    assert strictly_decreasing(np.array([]))
    assert strictly_decreasing(np.array([13]))
    assert not strictly_decreasing(np.array([8, 8, 8]))


def test_monotonically_decreasing_positive_case():
    assert monotonically_decreasing(np.array([3, 3, 2, 1]))


def test_monotonically_decreasing_negative_case():
    assert not monotonically_decreasing(np.array([3, 1, 2]))


def test_monotonically_decreasing_edge_cases():
    assert monotonically_decreasing(np.array([]))
    assert monotonically_decreasing(np.array([2]))
    assert monotonically_decreasing(np.array([6, 6, 6]))


def test_all_nonnegative_positive_case():
    assert all_nonnegative(np.array([0, 1, 2]))


def test_all_nonnegative_negative_case():
    assert not all_nonnegative(np.array([-1, 0, 1]))


def test_all_nonnegative_edge_cases():
    assert all_nonnegative(np.array([]))
    assert all_nonnegative(np.array([0]))
    assert all_nonnegative(np.array([5, 5, 5]))


def test_all_positive_cases():
    assert all_positive(np.array([1, 2, 3]))
    assert not all_positive(np.array([1, 0, 3]))
    assert all_positive(np.array([]))


def test_all_negative_cases():
    assert all_negative(np.array([-1, -2, -3]))
    assert not all_negative(np.array([-1, 0, -3]))
    assert all_negative(np.array([]))


def test_all_nonpositive_cases():
    assert all_nonpositive(np.array([0, -1, -2]))
    assert not all_nonpositive(np.array([-1, 1, -2]))
    assert all_nonpositive(np.array([]))
