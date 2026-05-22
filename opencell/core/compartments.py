"""Dynamic compartment model for OpenCell.

Handles cell geometry, volume dynamics, and counts↔concentration conversions.
M. genitalium is roughly spherical with volume ~0.07 fL.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from opencell.core.ir import Compartment


@dataclass
class CompartmentState:
    """Dynamic state of a single compartment.

    Attributes:
        compartment: Which compartment
        volume_fL: Volume in femtoliters (1 fL = 1e-15 L)
        surface_area_um2: Surface area in µm² (for membrane transport)
    """

    compartment: Compartment
    volume_fL: float
    surface_area_um2: float = 0.0

    @property
    def volume_L(self) -> float:
        """Volume in liters (for concentration calculations)."""
        return self.volume_fL * 1e-15

    def counts_to_concentration_mM(self, counts: float) -> float:
        """Convert molecule counts to millimolar concentration.

        concentration (mM) = counts / (Avogadro * volume_L) * 1e3
        """
        avogadro = 6.022e23
        return counts / (avogadro * self.volume_L) * 1e3

    def concentration_mM_to_counts(self, conc_mM: float) -> float:
        """Convert millimolar concentration to molecule counts.

        counts = conc_mM * 1e-3 * Avogadro * volume_L
        """
        avogadro = 6.022e23
        return conc_mM * 1e-3 * avogadro * self.volume_L


@dataclass
class CellGeometry:
    """Cell geometry model.

    Assumes roughly spherical geometry (appropriate for M. genitalium).
    Volume and surface area are dynamically updated during growth.
    """

    compartments: dict[Compartment, CompartmentState]

    @classmethod
    def default_mycoplasma(cls) -> CellGeometry:
        """Default geometry for M. genitalium-like cell.

        Volume ~0.07 fL, diameter ~0.3-0.8 µm (spherical approximation).
        """
        cytoplasm_volume_fL = 0.07
        # Sphere: V = (4/3)πr³, SA = 4πr²
        radius_um = (3 * cytoplasm_volume_fL * 1e-15 / (4 * np.pi)) ** (1 / 3) * 1e6
        surface_area_um2 = 4 * np.pi * radius_um**2

        return cls(
            compartments={
                Compartment.CYTOPLASM: CompartmentState(
                    compartment=Compartment.CYTOPLASM,
                    volume_fL=cytoplasm_volume_fL,
                ),
                Compartment.MEMBRANE: CompartmentState(
                    compartment=Compartment.MEMBRANE,
                    volume_fL=0.0,  # membrane is 2D
                    surface_area_um2=surface_area_um2,
                ),
                Compartment.EXTRACELLULAR: CompartmentState(
                    compartment=Compartment.EXTRACELLULAR,
                    volume_fL=1e9,  # effectively infinite
                ),
            }
        )

    def get_volume_fL(self, compartment: Compartment) -> float:
        """Get current volume of a compartment in femtoliters."""
        return self.compartments[compartment].volume_fL

    def grow(self, compartment: Compartment, factor: float) -> None:
        """Scale compartment volume by a growth factor.

        Also updates surface area assuming spherical geometry.
        """
        state = self.compartments[compartment]
        state.volume_fL *= factor
        if compartment == Compartment.CYTOPLASM:
            radius_um = (3 * state.volume_fL * 1e-15 / (4 * np.pi)) ** (1 / 3) * 1e6
            membrane = self.compartments.get(Compartment.MEMBRANE)
            if membrane is not None:
                membrane.surface_area_um2 = 4 * np.pi * radius_um**2

    @property
    def dry_weight_g(self) -> float:
        """Estimated dry weight in grams.

        For M. genitalium: ~2e-14 g (rough estimate).
        This is needed for per-gDW ↔ per-cell reference frame conversion.
        """
        # Rough: dry weight ≈ 0.3 * wet weight; wet weight ≈ density * volume
        # density ≈ 1.1 g/mL for bacteria
        volume_mL = self.compartments[Compartment.CYTOPLASM].volume_fL * 1e-12
        wet_weight_g = 1.1 * volume_mL
        return 0.3 * wet_weight_g
