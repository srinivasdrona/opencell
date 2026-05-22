"""Module I/O manifests: declare reads, writes, units, timescales.

Each sub-model declares what it reads and writes, with units and
expected timescales. CI checks for undeclared writes and unit mismatches.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class IOManifest:
    """Declares a sub-model's I/O contract."""

    module_id: str
    reads: dict[str, str] = field(default_factory=dict)  # species_id → unit
    writes: dict[str, str] = field(default_factory=dict)  # species_id → unit
    expected_timescale_s: float = 1.0  # characteristic timescale
    conserved_quantities: list[str] = field(default_factory=list)
    description: str = ""


class ManifestRegistry:
    """Registry of module I/O manifests for CI validation."""

    def __init__(self) -> None:
        self._manifests: dict[str, IOManifest] = {}

    def register(self, manifest: IOManifest) -> None:
        self._manifests[manifest.module_id] = manifest

    def get(self, module_id: str) -> IOManifest:
        if module_id not in self._manifests:
            raise KeyError(f"No manifest for module: {module_id}")
        return self._manifests[module_id]

    @property
    def module_ids(self) -> list[str]:
        return list(self._manifests.keys())

    def check_undeclared_writes(
        self,
        module_id: str,
        actual_writes: set[str],
    ) -> list[str]:
        """Check for writes not declared in the manifest."""
        manifest = self.get(module_id)
        declared = set(manifest.writes.keys())
        undeclared = actual_writes - declared
        return [f"{module_id} wrote to undeclared species: {s}" for s in undeclared]

    def check_unit_consistency(
        self,
        module_id: str,
        species_units: dict[str, str],
    ) -> list[str]:
        """Check that module's declared units match registry units."""
        manifest = self.get(module_id)
        errors = []
        for species_id, declared_unit in {**manifest.reads, **manifest.writes}.items():
            if species_id in species_units:
                registry_unit = species_units[species_id]
                if declared_unit != registry_unit:
                    errors.append(
                        f"{module_id}: {species_id} declared as '{declared_unit}' "
                        f"but registry says '{registry_unit}'"
                    )
        return errors
