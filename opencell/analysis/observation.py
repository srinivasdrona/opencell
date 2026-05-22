"""Observation model: maps internal simulation states to experimental assay readouts.

Can't validate against experiments without this. Each assay type
defines how internal quantities (molecule counts, concentrations)
map to what an experimentalist would measure.

Examples:
- OD600 → biomass (Beer-Lambert with extinction coefficient)
- qPCR → mRNA copy number (with amplification efficiency)
- Proteomics → protein abundance (with detection limits)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class AssayDefinition:
    """Definition of an experimental assay and its measurement model."""

    name: str
    description: str
    internal_species: list[str]  # Which species contribute
    transform: Callable[[dict[str, float]], float]  # State → measurement
    unit: str
    noise_model: str = "none"  # "none", "gaussian", "poisson"
    noise_param: float = 0.0  # std for gaussian, lambda for poisson
    detection_limit: float = 0.0


class ObservationModel:
    """Maps internal simulation states to experimental observables."""

    def __init__(self) -> None:
        self._assays: dict[str, AssayDefinition] = {}

    def register_assay(self, assay: AssayDefinition) -> None:
        """Register an assay type."""
        self._assays[assay.name] = assay
        logger.info(f"Registered assay: {assay.name}")

    @property
    def assay_names(self) -> list[str]:
        return list(self._assays.keys())

    def observe(
        self,
        assay_name: str,
        state: dict[str, float],
        add_noise: bool = False,
        rng: np.random.Generator | None = None,
    ) -> float:
        """Compute an observation from internal state.

        Args:
            assay_name: Name of the registered assay
            state: Dict mapping species ID → count/concentration
            add_noise: Whether to add measurement noise
            rng: Random generator for noise (required if add_noise=True)

        Returns:
            Observed measurement value
        """
        if assay_name not in self._assays:
            raise KeyError(f"Unknown assay: {assay_name}")

        assay = self._assays[assay_name]
        value = assay.transform(state)

        # Apply detection limit
        if value < assay.detection_limit:
            value = 0.0

        # Add measurement noise
        if add_noise and rng is not None:
            if assay.noise_model == "gaussian":
                value += rng.normal(0, assay.noise_param)
            elif assay.noise_model == "poisson":
                value = float(rng.poisson(max(0, value)))

        return value

    def observe_all(
        self,
        state: dict[str, float],
        add_noise: bool = False,
        rng: np.random.Generator | None = None,
    ) -> dict[str, float]:
        """Compute all registered observations."""
        return {name: self.observe(name, state, add_noise, rng) for name in self._assays}


# ── Built-in assay definitions ──


def od600_assay(
    extinction_coeff: float = 1.0,
    path_length_cm: float = 1.0,
) -> AssayDefinition:
    """OD600 optical density assay for biomass.

    OD600 = extinction_coeff * path_length * biomass_concentration
    """

    def transform(state: dict[str, float]) -> float:
        biomass = state.get("biomass", 0.0)
        return extinction_coeff * path_length_cm * biomass

    return AssayDefinition(
        name="OD600",
        description="Optical density at 600nm (biomass proxy)",
        internal_species=["biomass"],
        transform=transform,
        unit="AU",
        noise_model="gaussian",
        noise_param=0.01,
    )


def qpcr_assay(gene_id: str, amplification_efficiency: float = 0.95) -> AssayDefinition:
    """qPCR assay for mRNA quantification."""

    def transform(state: dict[str, float]) -> float:
        mrna = state.get(f"mRNA_{gene_id}", 0.0)
        return mrna * amplification_efficiency

    return AssayDefinition(
        name=f"qPCR_{gene_id}",
        description=f"qPCR measurement for {gene_id} mRNA",
        internal_species=[f"mRNA_{gene_id}"],
        transform=transform,
        unit="copies",
        noise_model="poisson",
        detection_limit=1.0,
    )
