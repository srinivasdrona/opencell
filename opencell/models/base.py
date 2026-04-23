"""Abstract sub-model interface for OpenCell.

All sub-models (metabolism, transcription, translation, etc.) implement
this interface. Sub-models declare what they CONSUME and PRODUCE via
SubModelContract; the engine + resource ledger handle allocation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import jax.numpy as jnp
import numpy as np

from opencell.core.ir import ReferenceFrame, SubModelContract
from opencell.core.state import CellState


class SubModel(ABC):
    """Abstract base class for all sub-models.

    Each sub-model:
    1. Declares its I/O contract (reads, writes, reference frame)
    2. Initializes from parameters
    3. Evolves state for a given time step
    4. Validates its output
    """

    @property
    @abstractmethod
    def id(self) -> str:
        """Unique identifier for this sub-model."""
        ...

    @property
    @abstractmethod
    def contract(self) -> SubModelContract:
        """I/O manifest: what this sub-model reads and writes."""
        ...

    @abstractmethod
    def initialize(self, state: CellState) -> None:
        """Initialize sub-model from initial cell state."""
        ...

    @abstractmethod
    def compute_derivatives(
        self,
        t: float,
        state: CellState,
    ) -> dict[str, float]:
        """Compute rate of change for each species this sub-model writes.

        Returns dict of species_id → d(count)/dt.
        Only species declared in contract.writes should be returned.
        """
        ...

    def validate_output(self, state: CellState) -> list[str]:
        """Validate sub-model output. Returns list of violation messages."""
        violations = []
        for species_id in self.contract.writes:
            count = state.get_count(species_id)
            if count < 0:
                violations.append(
                    f"[{self.id}] {species_id}: negative count {count:.6e}"
                )
        return violations


class DummyProducer(SubModel):
    """Test sub-model that produces a species at a constant rate."""

    def __init__(self, species_id: str, rate: float) -> None:
        self._species_id = species_id
        self._rate = rate

    @property
    def id(self) -> str:
        return "dummy_producer"

    @property
    def contract(self) -> SubModelContract:
        return SubModelContract(
            sub_model_id=self.id,
            reads=set(),
            writes={self._species_id},
            reference_frame=ReferenceFrame.PER_CELL,
        )

    def initialize(self, state: CellState) -> None:
        pass

    def compute_derivatives(self, t: float, state: CellState) -> dict[str, float]:
        return {self._species_id: self._rate}


class DummyConsumer(SubModel):
    """Test sub-model that consumes a species at a rate proportional to its amount."""

    def __init__(self, species_id: str, rate_constant: float) -> None:
        self._species_id = species_id
        self._k = rate_constant

    @property
    def id(self) -> str:
        return "dummy_consumer"

    @property
    def contract(self) -> SubModelContract:
        return SubModelContract(
            sub_model_id=self.id,
            reads={self._species_id},
            writes={self._species_id},
            reference_frame=ReferenceFrame.PER_CELL,
        )

    def initialize(self, state: CellState) -> None:
        pass

    def compute_derivatives(self, t: float, state: CellState) -> dict[str, float]:
        current = state.get_count(self._species_id)
        return {self._species_id: -self._k * current}
