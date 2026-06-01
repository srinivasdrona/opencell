"""Unit + property tests for protein-decay 4820/482 projection operators."""
from __future__ import annotations

import numpy as np
import pytest

from l2_replay_common import (
    KARR_MONOMER_FORM_ORDER,
    project_monomer_4820_to_482,
    project_trace_matrix_to_482,
    scatter_monomer_482_to_4820,
)


def test_canonical_form_order_is_10_and_contains_mature():
    assert len(KARR_MONOMER_FORM_ORDER) == 10
    assert "mature" in KARR_MONOMER_FORM_ORDER
    assert KARR_MONOMER_FORM_ORDER.index("mature") == 5
    assert KARR_MONOMER_FORM_ORDER[0] == "nascent"
    assert KARR_MONOMER_FORM_ORDER[-1] == "damaged"


CANONICAL_FORM_ORDER = KARR_MONOMER_FORM_ORDER


class TestProjectMonomer4820To482:
    def test_shape(self):
        v = np.arange(4820, dtype=np.float64)
        out = project_monomer_4820_to_482(v)
        assert out.shape == (482,)
        assert out.dtype == np.float64

    def test_zeros(self):
        out = project_monomer_4820_to_482(np.zeros(4820))
        assert np.all(out == 0)

    def test_ones_sums_to_n_forms(self):
        out = project_monomer_4820_to_482(np.ones(4820))
        assert np.all(out == 10.0)  # 10 form slots summed

    def test_only_mature_slot(self):
        # Place values only at form 5 (mature) - should pass through verbatim.
        v = np.zeros(4820)
        target = np.arange(482, dtype=np.float64)
        v[5 * 482:6 * 482] = target
        out = project_monomer_4820_to_482(v)
        assert np.array_equal(out, target)

    def test_linearity(self):
        rng = np.random.default_rng(0)
        a = rng.integers(0, 100, size=4820).astype(np.float64)
        b = rng.integers(0, 100, size=4820).astype(np.float64)
        out_sum = project_monomer_4820_to_482(2 * a + 3 * b)
        expected = 2 * project_monomer_4820_to_482(a) + 3 * project_monomer_4820_to_482(b)
        assert np.array_equal(out_sum, expected)

    def test_total_mass_conserved(self):
        rng = np.random.default_rng(42)
        v = rng.integers(0, 50, size=4820).astype(np.float64)
        out = project_monomer_4820_to_482(v)
        assert float(out.sum()) == float(v.sum())

    def test_rejects_non_1d(self):
        with pytest.raises(ValueError, match="1-D"):
            project_monomer_4820_to_482(np.zeros((6, 4820)))

    def test_rejects_wrong_size(self):
        with pytest.raises(ValueError, match="divisible"):
            project_monomer_4820_to_482(np.zeros(4819))


class TestProjectTraceMatrixTo482:
    def test_shape(self):
        m = np.arange(6 * 4820, dtype=np.float64).reshape(6, 4820)
        out = project_trace_matrix_to_482(m)
        assert out.shape == (482,)

    def test_total_mass_conserved(self):
        rng = np.random.default_rng(1)
        m = rng.integers(0, 30, size=(6, 4820)).astype(np.float64)
        out = project_trace_matrix_to_482(m)
        assert float(out.sum()) == float(m.sum())

    def test_equivalent_to_compartment_sum_then_project(self):
        rng = np.random.default_rng(2)
        m = rng.integers(0, 30, size=(6, 4820)).astype(np.float64)
        via_helper = project_trace_matrix_to_482(m)
        manual = project_monomer_4820_to_482(m.sum(axis=0))
        assert np.array_equal(via_helper, manual)

    def test_rejects_non_2d(self):
        with pytest.raises(ValueError, match="2-D"):
            project_trace_matrix_to_482(np.zeros(4820))


class TestScatterMonomer482To4820:
    def test_shape(self):
        v = np.arange(482, dtype=np.float64)
        out = scatter_monomer_482_to_4820(v, CANONICAL_FORM_ORDER)
        assert out.shape == (4820,)

    def test_mature_slot_placement(self):
        v = np.arange(482, dtype=np.float64)
        out = scatter_monomer_482_to_4820(v, CANONICAL_FORM_ORDER)
        # mature is index 5
        assert np.array_equal(out[5 * 482:6 * 482], v)
        # everything else zero
        assert float(out[:5 * 482].sum()) == 0.0
        assert float(out[6 * 482:].sum()) == 0.0

    def test_right_inverse_property(self):
        """pi(sigma(v)) == v for representative v."""
        rng = np.random.default_rng(7)
        for v in [
            np.zeros(482, dtype=np.float64),
            np.ones(482, dtype=np.float64),
            np.arange(482, dtype=np.float64),
            rng.integers(0, 1000, size=482).astype(np.float64),
            rng.integers(0, 1000, size=482).astype(np.float64),
        ]:
            scattered = scatter_monomer_482_to_4820(v, CANONICAL_FORM_ORDER)
            recovered = project_monomer_4820_to_482(scattered)
            assert np.array_equal(recovered, v), (
                f"right-inverse failed for v with sum={float(v.sum())}"
            )

    def test_idempotence_pi_sigma_pi(self):
        """pi o sigma o pi == pi."""
        rng = np.random.default_rng(11)
        m_form = rng.integers(0, 100, size=4820).astype(np.float64)
        pi_once = project_monomer_4820_to_482(m_form)
        pi_again = project_monomer_4820_to_482(
            scatter_monomer_482_to_4820(pi_once, CANONICAL_FORM_ORDER)
        )
        assert np.array_equal(pi_once, pi_again)

    def test_rejects_wrong_v_shape(self):
        with pytest.raises(ValueError, match="482"):
            scatter_monomer_482_to_4820(np.zeros(481), CANONICAL_FORM_ORDER)

    def test_rejects_missing_mature(self):
        with pytest.raises(ValueError, match="mature"):
            scatter_monomer_482_to_4820(
                np.zeros(482), ("nascent", "folded", "damaged")
            )

    def test_rejects_empty_form_order(self):
        with pytest.raises(ValueError, match="non-empty"):
            scatter_monomer_482_to_4820(np.zeros(482), ())
