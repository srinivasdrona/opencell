"""Unit registry and validation for OpenCell.

All values entering the IR must pass through unit validation.
This catches unit errors at the boundary, not deep in the solver.

Uses pint for dimensional analysis. The registry is a singleton
shared across the entire simulation.
"""

from __future__ import annotations

import pint

# Singleton unit registry — all OpenCell code must use this instance
ureg = pint.UnitRegistry()
Q_ = ureg.Quantity

# Define custom units common in systems biology
ureg.define("molar = mol / liter = M")
ureg.define("millimolar = 1e-3 molar = mM")
ureg.define("micromolar = 1e-6 molar = uM")
ureg.define("nanomolar = 1e-9 molar = nM")
ureg.define("dalton = 1.66054e-27 kg = Da")
ureg.define("kilodalton = 1e3 dalton = kDa")
ureg.define("copy_per_cell = [] = copies")  # dimensionless count per cell
ureg.define("nt = [] = nucleotide")  # nucleotide (for polymerization rates)
ureg.define("aa = [] = amino_acid")  # amino acid (for translation rates)
ureg.define("gDW = gram")  # gram dry weight (alias for flux units)


# Standard units used across OpenCell
class StandardUnits:
    """Standard unit conventions. Sub-models should convert to these."""

    # Concentrations
    CONCENTRATION = ureg.mM  # millimolar
    LOW_COPY_COUNT = ureg.copies  # molecules per cell (for stochastic species)

    # Rates
    METABOLIC_FLUX = ureg.mmol / ureg.gDW / ureg.hour  # FBA convention
    TRANSCRIPTION_RATE = ureg.nt / ureg.second  # polymerization
    TRANSLATION_RATE = ureg.aa / ureg.second  # ribosome elongation

    # Time
    TIME = ureg.second

    # Mass
    MOLAR_MASS = ureg.Da

    # Volume
    VOLUME = ureg.liter  # cell volume (will be femtoliters in practice)


def validate_quantity(
    value: object,
    expected_dimensionality: str,
    label: str = "value",
) -> pint.Quantity:
    """Validate that a value has the expected dimensional units.

    Args:
        value: A pint Quantity or raw number
        expected_dimensionality: Dimensionality string (e.g., "[concentration]", "[time]")
        label: Human-readable label for error messages

    Returns:
        The validated pint Quantity

    Raises:
        pint.DimensionalityError: If units don't match
        TypeError: If value is not a pint Quantity
    """
    if not isinstance(value, pint.Quantity):
        raise TypeError(
            f"{label}: expected pint Quantity, got {type(value).__name__}. "
            f"Wrap with Q_({value}, 'unit') or value * ureg.unit"
        )
    if not value.check(expected_dimensionality):
        raise pint.DimensionalityError(
            value.units,
            expected_dimensionality,
            extra_msg=f" for {label}",
        )
    return value


def validate_positive(value: pint.Quantity, label: str = "value") -> pint.Quantity:
    """Validate that a quantity is non-negative."""
    if value.magnitude < 0:
        raise ValueError(f"{label}: expected non-negative, got {value}")
    return value


def convert_reference_frame(
    value: pint.Quantity,
    from_frame: str,
    to_frame: str,
    cell_volume_L: float,
    dry_weight_g: float,
) -> pint.Quantity:
    """Convert a value between reference frames.

    This is the explicit conversion required by Gate G1.6.
    No sub-model may read state from a different reference frame
    without calling this function.

    Args:
        value: The quantity to convert
        from_frame: Source reference frame ("per_cell", "per_volume", "per_gDW")
        to_frame: Target reference frame
        cell_volume_L: Cell volume in liters
        dry_weight_g: Cell dry weight in grams

    Returns:
        Converted quantity in the target frame
    """
    if from_frame == to_frame:
        return value

    # Convert to per_cell as intermediate
    if from_frame == "per_volume":
        per_cell = value * Q_(cell_volume_L, "liter")
    elif from_frame == "per_gDW":
        per_cell = value * Q_(dry_weight_g, "gram")
    elif from_frame == "per_cell":
        per_cell = value
    else:
        raise ValueError(f"Unknown reference frame: {from_frame}")

    # Convert from per_cell to target
    if to_frame == "per_cell":
        return per_cell
    elif to_frame == "per_volume":
        return per_cell / Q_(cell_volume_L, "liter")
    elif to_frame == "per_gDW":
        return per_cell / Q_(dry_weight_g, "gram")
    else:
        raise ValueError(f"Unknown reference frame: {to_frame}")
