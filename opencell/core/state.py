"""Cell state container for OpenCell.

The CellState holds all dynamic simulation state as numpy arrays.
It is backed by the IR (species registry) and compartment model.
Design principle: data-oriented (flat arrays), not Python object graphs.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from opencell.core.compartments import CellGeometry
from opencell.core.ir import IRSpeciesRegistry, MoleculeType


@dataclass
class CellState:
    """Complete simulation state at a point in time.

    All species amounts are stored in a single flat array indexed
    by the species registry. This makes the state efficient for
    vectorized numpy operations.

    Attributes:
        time_s: Current simulation time in seconds
        counts: Array of molecule counts (shape: [n_species])
        registry: Species registry for ID ↔ index mapping
        geometry: Cell geometry (volumes, surface areas)
        rng_key: numpy Generator for stochastic processes
    """

    time_s: float
    counts: np.ndarray  # shape: (n_species,), dtype: float64
    registry: IRSpeciesRegistry
    geometry: CellGeometry
    rng_key: np.random.Generator

    @classmethod
    def initialize(
        cls,
        registry: IRSpeciesRegistry,
        initial_counts: dict[str, float],
        geometry: CellGeometry | None = None,
        rng_seed: int = 0,
    ) -> CellState:
        """Create initial cell state.

        Args:
            registry: Frozen species registry
            initial_counts: Dict of species_id → initial count
            geometry: Cell geometry (defaults to M. genitalium-like)
            rng_seed: Seed for the numpy Generator
        """
        if not registry._frozen:
            registry.freeze()

        counts_array = np.zeros(registry.size, dtype=np.float64)
        for species_id, count in initial_counts.items():
            idx = registry.index(species_id)
            counts_array[idx] = count

        return cls(
            time_s=0.0,
            counts=counts_array,
            registry=registry,
            geometry=geometry or CellGeometry.default_mycoplasma(),
            rng_key=np.random.default_rng(rng_seed),
        )

    def get_count(self, species_id: str) -> float:
        """Get current count for a species."""
        idx = self.registry.index(species_id)
        return float(self.counts[idx])

    def get_concentration_mM(self, species_id: str) -> float:
        """Get concentration in mM (converts from counts via cell volume)."""
        count = self.get_count(species_id)
        compartment = self.registry.get(species_id).compartment
        comp_state = self.geometry.compartments[compartment]
        return comp_state.counts_to_concentration_mM(count)

    def get_counts_by_type(self, mol_type: MoleculeType) -> dict[str, float]:
        """Get counts for all species of a given type."""
        species_ids = self.registry.species_by_type(mol_type)
        return {sid: self.get_count(sid) for sid in species_ids}

    def total_mass_da(self) -> float:
        """Total mass in Daltons (for conservation checking).

        Returns NaN if any species is missing molar mass data.
        """
        total = 0.0
        for i in range(self.registry.size):
            sp_id = self.registry.id_at(i)
            sp_info = self.registry.get(sp_id)
            if sp_info.molar_mass_da is None:
                return float("nan")
            total += float(self.counts[i]) * sp_info.molar_mass_da
        return total

    def total_atoms(self) -> dict[str, float]:
        """Total atom counts by element (for atom balance audit — Gate G1.4)."""
        totals: dict[str, float] = {}
        for i in range(self.registry.size):
            sp_id = self.registry.id_at(i)
            sp_info = self.registry.get(sp_id)
            count = float(self.counts[i])
            for element, n_atoms in sp_info.atom_counts.items():
                totals[element] = totals.get(element, 0.0) + count * n_atoms
        return totals

    def validate_positivity(self) -> list[str]:
        """Check that all counts are non-negative. Returns list of violations."""
        violations = []
        negative_mask = self.counts < 0
        if np.any(negative_mask):
            for i in range(self.registry.size):
                if float(self.counts[i]) < 0:
                    sp_id = self.registry.id_at(i)
                    violations.append(f"{sp_id}: count = {float(self.counts[i]):.6e}")
        return violations

    def split_rng(self) -> tuple[np.random.Generator, np.random.Generator]:
        """Spawn two independent child Generators (new_state_gen, use_gen).

        Uses ``numpy.random.Generator.spawn`` (SeedSequence-based), which the
        project's RNG-discipline rule endorses for independent streams. The
        first child advances the state generator; the second is for immediate
        use.
        """
        new_gen, use_gen = self.rng_key.spawn(2)
        self.rng_key = new_gen
        return new_gen, use_gen
