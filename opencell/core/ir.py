"""Internal Runtime Representation (IR) for OpenCell.

The IR is the canonical data structure for all simulation state. Every sub-model
reads from and writes to the IR through declared contracts. The IR is designed
for JAX compatibility (pytrees/arrays), extensibility (promoter states, complexes,
events), and correctness (resource allocation via partition-merge, not write-exclusion).

Key design decisions:
- Species are identified by string IDs, mapped to integer indices for array ops
- Compartments are enum-based with dynamic volumes
- Stoichiometry is stored as a sparse matrix
- Multiple sub-models CAN write to the same species (ATP, ribosomes, tRNAs)
  via resource ledger allocation, NOT write-exclusion
- All values carry units (validated at IR boundary via pint)
- Reference frame (per-cell, per-volume, per-gDW) is declared per species
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

import jax.numpy as jnp
import numpy as np
from jax.typing import ArrayLike


class Compartment(Enum):
    """Cell compartments. Extensible for eukaryotic models."""

    CYTOPLASM = auto()
    MEMBRANE = auto()
    EXTRACELLULAR = auto()


class ReferenceFrame(Enum):
    """Reference frame for concentration/count values.

    Every species MUST declare its reference frame. The coupler performs
    explicit conversions at sync points — no implicit mixing allowed.
    Gate G1.6 enforces this via CI.
    """

    PER_CELL = auto()
    PER_VOLUME = auto()  # concentration (mM, µM, etc.)
    PER_GRAM_DRY_WEIGHT = auto()  # flux units (mmol/gDW/hr)


class MoleculeType(Enum):
    """Classification of molecular species."""

    METABOLITE = auto()
    MRNA = auto()
    PROTEIN = auto()
    TRNA = auto()
    RRNA = auto()
    DNA = auto()
    COMPLEX = auto()
    OTHER = auto()


@dataclass(frozen=True)
class SpeciesInfo:
    """Metadata for a single molecular species in the simulation.

    Attributes:
        id: Unique string identifier (e.g., "atp_c", "gene_001_mrna")
        name: Human-readable name
        compartment: Which compartment this species resides in
        molecule_type: Classification (metabolite, mRNA, protein, etc.)
        reference_frame: Declared reference frame for this species' values
        molar_mass_da: Molar mass in Daltons (for mass conservation checks)
        atom_counts: Dict of element symbol → count (for atom balance audit)
        is_shared: Whether multiple sub-models can write to this species
    """

    id: str
    name: str
    compartment: Compartment
    molecule_type: MoleculeType
    reference_frame: ReferenceFrame
    molar_mass_da: float | None = None
    atom_counts: dict[str, int] = field(default_factory=dict)
    is_shared: bool = False


@dataclass(frozen=True)
class ReactionInfo:
    """Metadata for a single reaction.

    Attributes:
        id: Unique string identifier
        name: Human-readable name
        stoichiometry: Dict of species_id → stoichiometric coefficient
                       (negative = consumed, positive = produced)
        reversible: Whether reaction can run in both directions
        compartment: Primary compartment where reaction occurs
        sub_model: Which sub-model owns this reaction
    """

    id: str
    name: str
    stoichiometry: dict[str, float]
    reversible: bool = False
    compartment: Compartment = Compartment.CYTOPLASM
    sub_model: str = ""


@dataclass
class IRSpeciesRegistry:
    """Registry mapping species IDs to array indices and metadata.

    This is the bridge between human-readable species IDs and
    JAX-compatible integer-indexed arrays.
    """

    _species: dict[str, SpeciesInfo] = field(default_factory=dict)
    _id_to_index: dict[str, int] = field(default_factory=dict)
    _index_to_id: dict[int, str] = field(default_factory=dict)
    _frozen: bool = False

    def register(self, species: SpeciesInfo) -> int:
        """Register a species and return its array index."""
        if self._frozen:
            raise RuntimeError("Registry is frozen — cannot add species after simulation starts")
        if species.id in self._species:
            raise ValueError(f"Species '{species.id}' already registered")
        idx = len(self._species)
        self._species[species.id] = species
        self._id_to_index[species.id] = idx
        self._index_to_id[idx] = species.id
        return idx

    def freeze(self) -> None:
        """Freeze the registry. No more species can be added."""
        self._frozen = True

    def get(self, species_id: str) -> SpeciesInfo:
        """Get species metadata by ID."""
        return self._species[species_id]

    def index(self, species_id: str) -> int:
        """Get array index for a species ID."""
        return self._id_to_index[species_id]

    def id_at(self, index: int) -> str:
        """Get species ID for an array index."""
        return self._index_to_id[index]

    @property
    def size(self) -> int:
        """Number of registered species."""
        return len(self._species)

    @property
    def ids(self) -> list[str]:
        """All species IDs in index order."""
        return [self._index_to_id[i] for i in range(self.size)]

    def shared_species(self) -> list[str]:
        """Species IDs that are written by multiple sub-models."""
        return [sid for sid, info in self._species.items() if info.is_shared]

    def species_by_compartment(self, compartment: Compartment) -> list[str]:
        """Species IDs in a given compartment."""
        return [
            sid for sid, info in self._species.items() if info.compartment == compartment
        ]

    def species_by_type(self, mol_type: MoleculeType) -> list[str]:
        """Species IDs of a given molecule type."""
        return [
            sid for sid, info in self._species.items() if info.molecule_type == mol_type
        ]


@dataclass
class StoichiometryMatrix:
    """Sparse stoichiometry matrix: species × reactions.

    Stored as a dense NumPy array for now (toy cell is small enough).
    Will switch to sparse representation for M. genitalium scale.

    Convention: S[species_idx, reaction_idx]
    - Negative values = consumed
    - Positive values = produced
    """

    _matrix: np.ndarray  # shape: (n_species, n_reactions)
    _reaction_ids: list[str] = field(default_factory=list)
    _reaction_to_index: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_reactions(
        cls,
        reactions: list[ReactionInfo],
        registry: IRSpeciesRegistry,
    ) -> StoichiometryMatrix:
        """Build stoichiometry matrix from reaction definitions."""
        n_species = registry.size
        n_reactions = len(reactions)
        matrix = np.zeros((n_species, n_reactions), dtype=np.float64)
        reaction_ids = []
        reaction_to_index: dict[str, int] = {}

        for rxn_idx, rxn in enumerate(reactions):
            reaction_ids.append(rxn.id)
            reaction_to_index[rxn.id] = rxn_idx
            for species_id, coeff in rxn.stoichiometry.items():
                sp_idx = registry.index(species_id)
                matrix[sp_idx, rxn_idx] = coeff

        return cls(
            _matrix=matrix,
            _reaction_ids=reaction_ids,
            _reaction_to_index=reaction_to_index,
        )

    @property
    def matrix(self) -> np.ndarray:
        """Raw stoichiometry matrix (n_species × n_reactions)."""
        return self._matrix

    @property
    def as_jax(self) -> ArrayLike:
        """JAX-compatible array for use in solvers."""
        return jnp.array(self._matrix)

    @property
    def n_species(self) -> int:
        return self._matrix.shape[0]

    @property
    def n_reactions(self) -> int:
        return self._matrix.shape[1]

    def mass_balance_check(self, registry: IRSpeciesRegistry) -> dict[str, float]:
        """Check mass balance for each reaction.

        Returns dict of reaction_id → net mass change.
        For a balanced reaction, this should be ~0.
        """
        residuals: dict[str, float] = {}
        for rxn_idx, rxn_id in enumerate(self._reaction_ids):
            net_mass = 0.0
            for sp_idx in range(self.n_species):
                coeff = self._matrix[sp_idx, rxn_idx]
                if coeff != 0.0:
                    sp_id = registry.id_at(sp_idx)
                    sp_info = registry.get(sp_id)
                    if sp_info.molar_mass_da is not None:
                        net_mass += coeff * sp_info.molar_mass_da
                    else:
                        residuals[rxn_id] = float("nan")
                        break
            else:
                residuals[rxn_id] = net_mass
        return residuals


@dataclass
class SubModelContract:
    """Declares what a sub-model reads and writes.

    This is the I/O manifest for each sub-model (task 1.40).
    The engine and resource ledger use these contracts to:
    - Validate no undeclared writes
    - Detect read/write unit mismatches
    - Allocate shared resources proportionally
    """

    sub_model_id: str
    reads: set[str] = field(default_factory=set)  # species IDs
    writes: set[str] = field(default_factory=set)  # species IDs
    reference_frame: ReferenceFrame = ReferenceFrame.PER_CELL
    timescale_s: float = 1.0  # characteristic timescale in seconds

    def validate_against_registry(self, registry: IRSpeciesRegistry) -> list[str]:
        """Check that all declared species exist and frames match."""
        errors: list[str] = []
        for species_id in self.reads | self.writes:
            if species_id not in registry._species:
                errors.append(f"Species '{species_id}' not in registry")
                continue
            sp_info = registry.get(species_id)
            if sp_info.reference_frame != self.reference_frame:
                errors.append(
                    f"Species '{species_id}' is {sp_info.reference_frame.name} "
                    f"but sub-model '{self.sub_model_id}' declares {self.reference_frame.name}. "
                    f"Explicit conversion required."
                )
        return errors


def validate_contracts(contracts: list[SubModelContract]) -> list[str]:
    """Check for write conflicts and overlap between sub-model contracts.

    Shared species (is_shared=True) are allowed to be written by multiple
    sub-models — they go through the resource ledger. Non-shared species
    written by multiple sub-models are flagged as errors.
    """
    write_map: dict[str, list[str]] = {}  # species_id → [sub_model_ids]
    for contract in contracts:
        for species_id in contract.writes:
            write_map.setdefault(species_id, []).append(contract.sub_model_id)

    errors: list[str] = []
    for species_id, writers in write_map.items():
        if len(writers) > 1:
            errors.append(
                f"Species '{species_id}' written by {writers}. "
                f"Must be declared is_shared=True and allocated via resource ledger."
            )
    return errors
