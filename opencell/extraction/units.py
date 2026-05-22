"""Pint-based unit normalization with an explicit transformation trail.

The point of recording the transformation as a human-readable string
(rather than just a multiplicative factor) is so that the reviewer can
audit the conversion path without re-running pint.
"""

from __future__ import annotations

from dataclasses import dataclass

import pint

# Single shared registry — building one is expensive.
_UREG: pint.UnitRegistry | None = None


def ureg() -> pint.UnitRegistry:
    global _UREG
    if _UREG is None:
        _UREG = pint.UnitRegistry()
    return _UREG


@dataclass
class ConversionResult:
    converted_value: float
    converted_unit: str
    transformation: str  # e.g. "0.01 s^-1 × 60 s/min = 0.60 min^-1"
    success: bool
    error: str = ""


def _normalize_unit_for_pint(u: str) -> str:
    """Map common biology unit shorthand into pint-friendly syntax."""
    u = u.strip()
    # "s^-1" → "1/s" pint accepts both; keep as-is, pint handles ^-1
    # Greek letters → ascii
    u = u.replace("μ", "u").replace("µ", "u")
    return u


def convert(raw_value: float, from_unit: str, to_unit: str) -> ConversionResult:
    """Convert raw_value from from_unit to to_unit using pint.

    Returns a ConversionResult with the converted value, the converted
    unit string, and a human-readable transformation trail.  Never raises;
    on failure returns success=False with an error message.
    """
    if not from_unit or not to_unit:
        return ConversionResult(raw_value, to_unit, "", False, "missing unit")
    try:
        u = ureg()
        from_u = _normalize_unit_for_pint(from_unit)
        to_u = _normalize_unit_for_pint(to_unit)
        q = raw_value * u(from_u)
        converted = q.to(to_u)
        ratio = float(converted.magnitude) / raw_value if raw_value != 0 else float("nan")
        trans = f"{raw_value} {from_unit} × {ratio:g} = {float(converted.magnitude):g} {to_unit}"
        return ConversionResult(
            converted_value=float(converted.magnitude),
            converted_unit=to_unit,
            transformation=trans,
            success=True,
        )
    except Exception as e:
        return ConversionResult(raw_value, to_unit, "", False, str(e))


def units_compatible(a: str, b: str) -> bool:
    """True iff units a and b have the same dimensionality."""
    if not a or not b:
        return False
    try:
        u = ureg()
        return (
            u(_normalize_unit_for_pint(a)).dimensionality
            == u(_normalize_unit_for_pint(b)).dimensionality
        )
    except Exception:
        return False
