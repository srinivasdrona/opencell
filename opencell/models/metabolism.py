"""Metabolism sub-model anchored on Chassagnole et al. 2002.

This is the first OpenCell sub-model that consumes a curated BioModels SBML
directly (BIOMD0000000051 — "Chassagnole2002_Carbon_Metabolism", E. coli
central carbon metabolism, 18 dynamic species, 48 reactions).

The model bytes are loaded from
``data/biomodels_reference/BIOMD0000000051_chassagnole2002.xml`` and parsed
via :class:`opencell.models.sbml_model.SbmlOdeModel`, which uses libsbml +
sympy to translate every ``<kineticLaw>`` into a NumPy callable.

Validation: against ``libroadrunner`` reading the same SBML, OpenCell agrees
to ~1e-6 relative on every species over 60s of simulated time (see
``tests/integration/test_metabolism_chassagnole.py``).

Provenance: every loaded instance records the SBML SHA-256, the BioModels
ID, and a reference to the manifest sidecar
(``manifests/chassagnole2002.draft.yaml``) which carries the eutils-verified
paper-pairing block (DOI 10.1002/bit.10288, PMID 17590932).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from opencell.models.sbml_model import SbmlOdeModel

# Canonical location of the curated SBML inside the repo
DEFAULT_SBML_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "biomodels_reference"
    / "BIOMD0000000051_chassagnole2002.xml"
)
DEFAULT_MANIFEST_PATH = (
    Path(__file__).resolve().parents[2] / "manifests" / "chassagnole2002.draft.yaml"
)
BIOMODELS_ID = "BIOMD0000000051"
PAPER_DOI = "10.1002/bit.10288"
PAPER_PMID = "17590932"


@dataclass
class MetabolismModel:
    """E. coli central carbon metabolism (Chassagnole 2002 / BIOMD0000000051).

    Thin wrapper around :class:`SbmlOdeModel` that:

    1. Pins the SBML source (with SHA-256 check on load),
    2. Records the verified paper-pairing provenance,
    3. Exposes the standard OpenCell sub-model surface (``rhs``, ``initial_y``,
       ``species_index``).

    For the full glycolysis dynamics, hand the ``rhs`` and ``initial_y`` to
    :func:`opencell.solvers.ode_scipy.solve_ode_scipy` (LSODA recommended;
    the system mixes fast PTS uptake with slower pentose-phosphate fluxes).

    Notes:
        Cofactor concentrations (catp, cadp, camp, cnadp, cnadph, cnad, cnadh)
        are *not* dynamic in Chassagnole's formulation — they are empirical
        forcing functions of t, encoded as SBML ``<assignmentRule>`` elements
        and applied automatically inside :meth:`rhs`.
    """

    sbml: SbmlOdeModel
    manifest_path: Path | None = None
    biomodels_id: str = BIOMODELS_ID
    paper_doi: str = PAPER_DOI
    paper_pubmed_id: str = PAPER_PMID

    @classmethod
    def load(
        cls,
        sbml_path: str | Path | None = None,
        manifest_path: str | Path | None = None,
    ) -> MetabolismModel:
        """Load the curated Chassagnole SBML and return a configured model.

        Args:
            sbml_path: override the default SBML location (rarely needed)
            manifest_path: override the default manifest sidecar location
        """
        path = Path(sbml_path) if sbml_path is not None else DEFAULT_SBML_PATH
        sbml = SbmlOdeModel.from_file(path)
        return cls(
            sbml=sbml,
            manifest_path=Path(manifest_path) if manifest_path else DEFAULT_MANIFEST_PATH,
        )

    # ---- Pass-through state surface ----

    @property
    def species_ids(self) -> list[str]:
        return self.sbml.species_ids

    @property
    def initial_y(self) -> np.ndarray:
        return self.sbml.initial_y

    @property
    def n_species(self) -> int:
        return self.sbml.n_species

    @property
    def n_reactions(self) -> int:
        return self.sbml.n_reactions

    def species_index(self) -> dict[str, int]:
        return self.sbml.species_index()

    def rhs(self, t: float, y: np.ndarray) -> np.ndarray:
        """Right-hand side dy/dt — drop-in for ``scipy.integrate.solve_ivp``."""
        return self.sbml.rhs(t, y)

    def fluxes(self, t: float, y: np.ndarray) -> np.ndarray:
        """Per-reaction fluxes at (t, y) — useful for FBA-style analyses."""
        return self.sbml.fluxes(t, y)

    # ---- Provenance ----

    def provenance(self) -> dict[str, Any]:
        """Audit record combining SBML hash with paper-pairing identifiers.

        Persist this alongside any simulation output so the run can be traced
        back to the curated SBML bytes AND the verified source paper.
        """
        out = self.sbml.provenance()
        out.update(
            {
                "biomodels_id": self.biomodels_id,
                "paper_doi": self.paper_doi,
                "paper_pubmed_id": self.paper_pubmed_id,
                "manifest_sidecar": (str(self.manifest_path) if self.manifest_path else None),
            }
        )
        return out
