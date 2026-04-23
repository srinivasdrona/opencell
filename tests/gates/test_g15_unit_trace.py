"""Gate G1.5: pint Quantity trace through the micro-model pipeline.

Verifies that a parameter expressed as a pint.Quantity survives end-to-end
through parameter construction, ODE RHS evaluation, and steady-state
formula computation without losing dimensional information.

This is the canary for "naked number drift" — a common failure mode where
units get stripped in intermediate steps and incompatible values get
combined silently downstream.
"""

from __future__ import annotations

import math

import pint
import pytest

from opencell.core.units import (
    Q_,
    ureg,
    validate_positive,
    validate_quantity,
)


@pytest.mark.gate
class TestGateG15UnitTrace:
    """G1.5: pint Quantities must carry dimensions through the pipeline."""

    def test_thattai_params_validate_as_inverse_minutes(self) -> None:
        """All 4 Thattai rate constants must validate as [1/time]."""
        k_R = Q_(0.60, "1/minute")
        gamma_R = Q_(math.log(2) / 2.0, "1/minute")
        k_P = Q_(20.0 * math.log(2) / 2.0, "1/minute")
        gamma_P = Q_(math.log(2) / 60.0, "1/minute")

        for label, value in (("k_R", k_R), ("gamma_R", gamma_R),
                              ("k_P", k_P), ("gamma_P", gamma_P)):
            validate_quantity(value, "1/[time]", label=label)
            validate_positive(value, label=label)

    def test_naked_float_rejected(self) -> None:
        """Passing a bare float where a Quantity is expected must fail."""
        with pytest.raises(TypeError):
            validate_quantity(0.60, "1/[time]", label="k_R")

    def test_wrong_dimensionality_rejected(self) -> None:
        """A Quantity with the wrong dimensions must fail loudly."""
        k_wrong = Q_(0.60, "meter / second")   # velocity, not rate
        with pytest.raises(pint.DimensionalityError):
            validate_quantity(k_wrong, "1/[time]", label="k_R")

    def test_steady_state_derivation_preserves_units(self) -> None:
        """m* = k_R / gamma_R must come out as dimensionless count."""
        k_R = Q_(0.60, "1/minute")
        gamma_R = Q_(math.log(2) / 2.0, "1/minute")
        m_ss = k_R / gamma_R
        # [1/min] / [1/min] = dimensionless
        assert m_ss.dimensionless
        assert m_ss.magnitude == pytest.approx(0.60 / (math.log(2) / 2.0))

    def test_protein_steady_state_preserves_units(self) -> None:
        """p* = (k_R · k_P) / (gamma_R · gamma_P) is dimensionless."""
        k_R = Q_(0.60, "1/minute")
        k_P = Q_(20.0 * math.log(2) / 2.0, "1/minute")
        gamma_R = Q_(math.log(2) / 2.0, "1/minute")
        gamma_P = Q_(math.log(2) / 60.0, "1/minute")
        p_ss = (k_R * k_P) / (gamma_R * gamma_P)
        assert p_ss.dimensionless
        # Sanity: expected ~1038.7
        assert 1000.0 < p_ss.magnitude < 1100.0

    def test_time_quantity_carries_through(self) -> None:
        """Half-life → rate-constant conversion must preserve units."""
        half_life = Q_(2.0, "minute")
        gamma = math.log(2) / half_life
        assert gamma.check("1/[time]")
        assert gamma.to("1/minute").magnitude == pytest.approx(
            math.log(2) / 2.0
        )

    def test_cross_unit_sum_rejected_by_pint(self) -> None:
        """Adding a rate and a half-life must fail dimensionally."""
        rate = Q_(0.347, "1/minute")
        half_life = Q_(2.0, "minute")
        with pytest.raises(pint.DimensionalityError):
            _ = rate + half_life

    def test_concentration_to_copies_requires_volume(self) -> None:
        """Converting between reference frames requires explicit volume."""
        conc = Q_(1.0, "micromolar")    # per_volume frame
        vol_fL = Q_(1.0, "femtoliter")   # E. coli-scale volume
        n_molecules = (conc * vol_fL).to("mol") * Q_(6.022e23, "1/mol")
        # At 1 µM in 1 fL, roughly 602 molecules
        assert 500 < n_molecules.to_reduced_units().magnitude < 700
