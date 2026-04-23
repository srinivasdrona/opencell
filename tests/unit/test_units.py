"""Tests for core/units.py — Unit registry and validation."""

import pytest
import pint

from opencell.core.units import (
    Q_,
    StandardUnits,
    convert_reference_frame,
    ureg,
    validate_positive,
    validate_quantity,
)


class TestUnitRegistry:
    def test_millimolar(self) -> None:
        km = 0.5 * ureg.mM
        assert km.magnitude == 0.5

    def test_micromolar(self) -> None:
        conc = 100 * ureg.uM
        converted = conc.to(ureg.mM)
        assert abs(converted.magnitude - 0.1) < 1e-10

    def test_dalton(self) -> None:
        mass = 507.18 * ureg.Da
        assert mass.magnitude == 507.18

    def test_flux_units(self) -> None:
        flux = 10.0 * ureg.mmol / ureg.gDW / ureg.hour
        assert flux.magnitude == 10.0

    def test_copy_per_cell(self) -> None:
        copies = 100 * ureg.copies
        assert copies.magnitude == 100


class TestValidateQuantity:
    def test_valid_concentration(self) -> None:
        q = 0.5 * ureg.mM
        result = validate_quantity(q, "[substance] / [length] ** 3", "Km")
        assert result is q

    def test_raw_number_raises(self) -> None:
        with pytest.raises(TypeError, match="expected pint Quantity"):
            validate_quantity(0.5, "[substance] / [length] ** 3", "Km")

    def test_wrong_dimensionality_raises(self) -> None:
        q = 0.5 * ureg.second
        with pytest.raises(pint.DimensionalityError):
            validate_quantity(q, "[substance] / [length] ** 3", "time_as_conc")


class TestValidatePositive:
    def test_positive_ok(self) -> None:
        q = 0.5 * ureg.mM
        assert validate_positive(q) is q

    def test_zero_ok(self) -> None:
        q = 0.0 * ureg.mM
        assert validate_positive(q) is q

    def test_negative_raises(self) -> None:
        q = -0.5 * ureg.mM
        with pytest.raises(ValueError, match="non-negative"):
            validate_positive(q, "concentration")


class TestReferenceFrameConversion:
    def test_per_cell_to_per_volume(self) -> None:
        # 1000 molecules in 1e-15 L → concentration
        count = Q_(1000, "copies")
        result = convert_reference_frame(
            count, "per_cell", "per_volume",
            cell_volume_L=1e-15, dry_weight_g=1e-14,
        )
        # Should be count / volume
        assert result.magnitude > 0

    def test_same_frame_noop(self) -> None:
        q = Q_(100, "copies")
        result = convert_reference_frame(
            q, "per_cell", "per_cell",
            cell_volume_L=1e-15, dry_weight_g=1e-14,
        )
        assert result.magnitude == 100

    def test_roundtrip(self) -> None:
        original = Q_(500, "copies")
        vol_L = 1e-15
        dw_g = 1e-14

        per_vol = convert_reference_frame(
            original, "per_cell", "per_volume", vol_L, dw_g
        )
        back = convert_reference_frame(
            per_vol, "per_volume", "per_cell", vol_L, dw_g
        )
        assert abs(back.magnitude - original.magnitude) < 1e-6
