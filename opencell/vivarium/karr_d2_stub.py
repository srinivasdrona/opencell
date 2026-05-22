"""Vivarium Process seeding complex counts from Karr per-process fixtures.

Evidence provenance:
- `data/karr_fixtures/per_process/MacromolecularComplexation_flat.mat`:
  `data.fixture.complexWholeCellModelIDs` (D.2 complex IDs, part 1)
- `data/karr_fixtures/per_process/RibosomeAssembly_flat.mat`:
  `data.fixture.complexWholeCellModelIDs` (D.2 complex IDs, part 2)
- `data/karr_fixtures/per_process/ProteinComplex_flat.mat`:
  `data.fixture.{wholeCellModelIDs,matureIndexs,compartments,counts}`
  (mature snapshot count per complex WID)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_LOGGER = logging.getLogger(__name__)
_FIXTURE_DIR = (
    Path(__file__).resolve().parents[2] / "data" / "karr_fixtures" / "per_process"
)
_PROTEIN_COMPLEX_FLAT = _FIXTURE_DIR / "ProteinComplex_flat.mat"
_MACROMOLECULAR_COMPLEXATION_FLAT = _FIXTURE_DIR / "MacromolecularComplexation_flat.mat"
_RIBOSOME_ASSEMBLY_FLAT = _FIXTURE_DIR / "RibosomeAssembly_flat.mat"


def _load_flat_fixture(path: Path) -> object:  # noqa: ANN401 - matlab struct dynamic
    return loadmat(str(path), squeeze_me=True, struct_as_record=False)["data"].fixture


def _fixture_wids(values: object) -> list[str]:
    return np.asarray(values, dtype=object).ravel().astype(str).tolist()


def _derive_d2_owned_wids(
    macromolecular_complexation_path: Path,
    ribosome_assembly_path: Path,
) -> tuple[str, ...]:
    mc = _load_flat_fixture(macromolecular_complexation_path)
    ra = _load_flat_fixture(ribosome_assembly_path)
    wids = set(_fixture_wids(mc.complexWholeCellModelIDs))
    wids.update(_fixture_wids(ra.complexWholeCellModelIDs))
    return tuple(sorted(wids))


def _mature_count_by_wid(protein_complex_path: Path) -> dict[str, float]:
    fixture = _load_flat_fixture(protein_complex_path)
    form_wids = np.asarray(fixture.wholeCellModelIDs, dtype=object).ravel().astype(str)
    mature_rows = np.asarray(fixture.matureIndexs, dtype=np.int64).ravel() - 1
    compartments = np.asarray(fixture.compartments, dtype=np.int64).ravel() - 1
    counts = np.asarray(fixture.counts, dtype=np.float64)

    out: dict[str, float] = {}
    for row in mature_rows:
        if row < 0 or row >= form_wids.size:
            continue
        col = int(compartments[row])
        if col < 0 or col >= counts.shape[1]:
            continue
        out[form_wids[row]] = float(counts[row, col])
    return out


class KarrD2StubProcess(Process):
    """Seed `complex.counts` defaults from Karr snapshot fixtures."""

    name = "karr_d2_stub"
    defaults: dict[str, Any] = {
        "protein_complex_path": str(_PROTEIN_COMPLEX_FLAT),
        "macromolecular_complexation_path": str(_MACROMOLECULAR_COMPLEXATION_FLAT),
        "ribosome_assembly_path": str(_RIBOSOME_ASSEMBLY_FLAT),
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        protein_complex_path = Path(self.parameters["protein_complex_path"])
        macromolecular_complexation_path = Path(
            self.parameters["macromolecular_complexation_path"]
        )
        ribosome_assembly_path = Path(self.parameters["ribosome_assembly_path"])

        self.d2_owned_wids = _derive_d2_owned_wids(
            macromolecular_complexation_path=macromolecular_complexation_path,
            ribosome_assembly_path=ribosome_assembly_path,
        )
        mature_counts = _mature_count_by_wid(protein_complex_path)

        missing_wids: list[str] = []
        self._complex_counts_schema: dict[str, dict[str, Any]] = {}
        for wid in self.d2_owned_wids:
            if wid not in mature_counts:
                missing_wids.append(wid)
            self._complex_counts_schema[wid] = {
                "_default": float(mature_counts.get(wid, 0.0)),
                "_updater": "accumulate",
                "_emit": True,
            }

        if missing_wids:
            _LOGGER.warning(
                "KarrD2StubProcess: %d D.2-owned WIDs missing mature snapshot "
                "counts; defaulting to 0 (%s)",
                len(missing_wids),
                ",".join(sorted(missing_wids)),
            )

    def ports_schema(self) -> dict[str, Any]:
        return {
            "complex": {
                "counts": {
                    wid: dict(schema)
                    for wid, schema in self._complex_counts_schema.items()
                }
            }
        }

    def next_update(self, timestep: float, states: dict) -> dict:
        del timestep, states
        return {}


__all__ = [
    "KarrD2StubProcess",
]

