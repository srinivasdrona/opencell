"""First-class environment/media model for OpenCell.

The environment is a runtime object, not a config parameter.
It models the growth medium surrounding the cell: nutrient concentrations,
pH, temperature, and other conditions that affect cellular behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GrowthMedium:
    """Growth medium composition.

    Nutrient concentrations are in mM (millimolar).
    This is a simplified model — real media have dozens of components.
    """

    nutrients_mM: dict[str, float] = field(default_factory=dict)
    ph: float = 7.4
    temperature_C: float = 37.0
    name: str = "minimal"

    @classmethod
    def sp4_medium(cls) -> GrowthMedium:
        """SP4 medium — standard for Mycoplasma genitalium culture.

        Concentrations are approximate and UNVERIFIED.
        """
        return cls(
            name="SP4",
            ph=7.4,
            temperature_C=37.0,
            nutrients_mM={
                "glucose": 25.0,
                "glutamine": 2.0,
                "serine": 0.5,
                "threonine": 0.5,
            },
        )

    @classmethod
    def minimal_toy(cls) -> GrowthMedium:
        """Minimal medium for toy cell benchmark."""
        return cls(
            name="minimal_toy",
            ph=7.0,
            temperature_C=37.0,
            nutrients_mM={
                "glucose": 10.0,
            },
        )


@dataclass
class Environment:
    """Runtime environment model.

    Tracks medium composition over time. Nutrients are consumed by the cell
    and can be replenished (batch vs chemostat mode).
    """

    medium: GrowthMedium
    mode: str = "batch"  # "batch" or "chemostat"
    dilution_rate_per_hr: float = 0.0  # for chemostat mode only
    _initial_nutrients_mM: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._initial_nutrients_mM = dict(self.medium.nutrients_mM)

    def get_nutrient_mM(self, nutrient: str) -> float:
        """Get current concentration of a nutrient."""
        return self.medium.nutrients_mM.get(nutrient, 0.0)

    def consume_nutrient(self, nutrient: str, amount_mM: float) -> float:
        """Consume a nutrient from the medium.

        Returns the actual amount consumed (may be less if depleted).
        """
        available = self.medium.nutrients_mM.get(nutrient, 0.0)
        consumed = min(available, amount_mM)
        self.medium.nutrients_mM[nutrient] = available - consumed
        return consumed

    def is_nutrient_depleted(self, nutrient: str, threshold_mM: float = 0.001) -> bool:
        """Check if a nutrient is effectively depleted."""
        return self.get_nutrient_mM(nutrient) < threshold_mM

    def step_chemostat(self, dt_hr: float) -> None:
        """Update medium for chemostat mode: dilute and replenish."""
        if self.mode != "chemostat":
            return
        d = self.dilution_rate_per_hr * dt_hr
        for nutrient, initial_conc in self._initial_nutrients_mM.items():
            current = self.medium.nutrients_mM.get(nutrient, 0.0)
            # chemostat: dS/dt = D * (S_in - S)
            self.medium.nutrients_mM[nutrient] = current + d * (initial_conc - current)
