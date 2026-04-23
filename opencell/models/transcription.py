"""Transcription / gene-expression sub-model anchored on Vilar et al. 2002.

This is OpenCell's first count-based sub-model. It consumes BIOMD0000000035
("Vilar2002 — Mechanisms of noise resistance in genetic oscillators"): 9
dynamic species (an activator gene + repressor gene with bound/unbound DNA
states, mRNAs, proteins, and an A·R complex), 16 mass-action reactions, 1
boundary species ("EmptySet") representing the extracellular/degraded sink.

Unlike Chassagnole, every species is declared with
``hasOnlySubstanceUnits=true`` — the natural representation for
gene-expression dynamics where state is "molecule count", not
"concentration". Per-species substance-unit handling lives in
:class:`opencell.models.sbml_model.SbmlOdeModel`.

Validation: against ``libroadrunner`` reading the same SBML, OpenCell agrees
to ~1e-3 relative on every species over the oscillation horizon (see
``tests/integration/test_transcription_vilar.py``). Mass-action systems with
no assignment rules are expected to agree even tighter; the looser tolerance
absorbs phase drift on the limit cycle.

Provenance: every loaded instance records the SBML SHA-256, the BioModels
ID, and a reference to the manifest sidecar
(``manifests/vilar2002.draft.yaml``) which carries the eutils-verified
paper-pairing block (DOI 10.1073/pnas.092133899, PMID 11972055).
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
    / "BIOMD0000000035_vilar2002.xml"
)
DEFAULT_MANIFEST_PATH = (
    Path(__file__).resolve().parents[2]
    / "manifests"
    / "vilar2002.draft.yaml"
)
BIOMODELS_ID = "BIOMD0000000035"
PAPER_DOI = "10.1073/pnas.092133899"
PAPER_PMID = "11972055"


@dataclass
class TranscriptionModel:
    """Activator-repressor genetic oscillator (Vilar 2002 / BIOMD0000000035).

    Thin wrapper around :class:`SbmlOdeModel` that:

    1. Pins the SBML source (with SHA-256 check on load),
    2. Records the verified paper-pairing provenance,
    3. Exposes the standard OpenCell sub-model surface (``rhs``, ``initial_y``,
       ``species_index``).

    For the deterministic limit-cycle dynamics, hand the ``rhs`` and
    ``initial_y`` to :func:`opencell.solvers.ode_scipy.solve_ode_scipy`
    (LSODA recommended; the system has fast DNA-binding events alongside
    slower protein turnover). The original paper is about *stochastic*
    robustness; the deterministic ODE used here is the natural mean-field
    limit and exhibits the same limit-cycle topology.

    Notes:
        Vilar's species are absolute molecule counts in units of (transcripts,
        proteins, gene-state occupancies). Time is in hours per the SBML.
        State variables in this model:

        * ``DA``, ``DAp``  — activator gene unbound / activator-bound
        * ``DR``, ``DRp``  — repressor gene unbound / activator-bound
        * ``MA``, ``MR``   — activator and repressor mRNAs
        * ``A``, ``R``     — activator and repressor proteins
        * ``C``            — activator-repressor sequestration complex

        Conservation: ``DA + DAp = 1`` and ``DR + DRp = 1`` (single-copy
        genes) are preserved by the stoichiometry and verified by the
        oracle test.
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
    ) -> TranscriptionModel:
        """Load the curated Vilar SBML and return a configured model.

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
        """Per-reaction fluxes at (t, y) — useful for noise-decomposition."""
        return self.sbml.fluxes(t, y)

    # ---- Provenance ----

    def provenance(self) -> dict[str, Any]:
        """Audit record combining SBML hash with paper-pairing identifiers."""
        out = self.sbml.provenance()
        out.update(
            {
                "biomodels_id": self.biomodels_id,
                "paper_doi": self.paper_doi,
                "paper_pubmed_id": self.paper_pubmed_id,
                "manifest_sidecar": (
                    str(self.manifest_path) if self.manifest_path else None
                ),
            }
        )
        return out
