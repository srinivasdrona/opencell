"""One-way coupling: metabolism (Chassagnole 2002) drives transcription (Vilar 2002).

Composite ODE on concatenated state ``y = [y_met (mM, t in s), y_gene (counts, t in h)]``.
The metabolism sub-model is unchanged; the gene sub-model has its **6 synthesis
fluxes** scaled by a dimensionless modulation factor ``f_met(t, y_met) in [0, 1]``
derived from the external glucose pool. All other gene fluxes (degradation,
DNA binding/unbinding, complex formation) run untouched.

Design notes (after rubber-duck + GPT-5 critiques):

* This is a **demo** of architectural coupling, NOT a biologically validated
  claim. ``cglcex`` is *external glucose availability*, not energy state. We
  use it only because it is the most legible substrate-availability signal in
  Chassagnole's model.
* We modulate **fluxes**, not whole RHS. Scaling the whole Vilar RHS would
  also scale degradation, which is wrong (a starving cell does not stop
  degrading mRNA).
* The 6 synthesis reactions are curated by index here, with a runtime
  stoichiometry assertion that confirms each is product-only with
  +1 stoichiometry on the expected species. If the SBML changes, we crash
  loudly instead of silently coupling the wrong reactions.
* Time-scale conversion is explicit: composite time is in **seconds**.
  Vilar's SBML uses **hours**, so for any t_s we evaluate
  ``gene.fluxes(t_s/3600, y_gene)`` and divide the resulting dy_gene/dt
  by 3600 to convert h^-1 -> s^-1.
* Validation: at ``f_met=1`` the composite RHS must equal
  ``concat([met.rhs, gene.rhs/3600])`` to floating-point precision.

Example:
    from opencell.models.coupled import CoupledMetabolismTranscription
    coupled = CoupledMetabolismTranscription.build()
    y0 = coupled.initial_y
    # integrate with scipy LSODA, t in seconds; run >= 5 hours of cellular time
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from opencell.models.metabolism import MetabolismModel
from opencell.models.transcription import TranscriptionModel


# Vilar 2002 / BIOMD0000000035: indices of the 6 synthesis reactions in the
# stoichiometry matrix as exposed by SbmlOdeModel. Curated once, asserted at
# build time. (Order: MA basal, MA activated, A translation, MR basal,
# MR activated, R translation.)
SYNTHESIS_REACTION_INDICES: tuple[int, ...] = (6, 7, 9, 12, 13, 15)
SYNTHESIS_PRODUCT_SPECIES: tuple[str, ...] = ("MA", "MA", "A", "MR", "MR", "R")

SECONDS_PER_HOUR = 3600.0
EXTERNAL_GLUCOSE_SPECIES = "cglcex"
# Chassagnole 2002 / BIOMD0000000051: PTS reaction (sugar phosphotransferase
# system) is the glucose uptake step. Stoichiometry: cglcex + 65*cpep ->
# cg6p + 65*cpyr (the 65 multiplier is Chassagnole's accounting for total
# PEP turnover per glucose entering glycolysis). Flux units are mM/s.
PTS_REACTION_INDEX: int = 0
PTS_EXPECTED_PRODUCT: str = "cg6p"


def default_f_met(cglcex: float, cglcex0: float) -> float:
    """Concentration-based modulation: clamp(cglcex/cglcex0, 0, 1).

    Simple and legible but only sees external glucose pool size. Drops
    to zero only when the cell has actually starved.
    """
    if cglcex0 <= 0.0:
        return 1.0
    return float(np.clip(cglcex / cglcex0, 0.0, 1.0))


def f_met_from_uptake_flux(v_pts: float, v_pts0: float) -> float:
    """Flux-based modulation: clamp(vPTS / vPTS_init, 0, 1).

    More biologically meaningful than concentration: reflects the rate
    at which carbon is actually entering glycolysis. Drops when:
      * external glucose depletes (substrate term in PTS rate law)
      * PEP becomes scarce (cofactor for PTS)
      * the network is stalled for any reason
    Initial value is 1.0 (vPTS at t=0 / vPTS at t=0).
    """
    if v_pts0 <= 0.0:
        return 1.0
    return float(np.clip(v_pts / v_pts0, 0.0, 1.0))


@dataclass
class CoupledMetabolismTranscription:
    """Composite ODE coupling Chassagnole metabolism -> Vilar gene expression.

    State layout: ``y = concat([y_met, y_gene])``.
    Composite time is in seconds. Vilar's hour-based RHS is rescaled inside.

    Two coupling signals are supported:

    * ``signal="concentration"`` (default): f_met = clamp(cglcex/cglcex0, 0, 1)
    * ``signal="uptake_flux"``:           f_met = clamp(vPTS/vPTS0, 0, 1)

    The flux signal is more biologically meaningful — it reflects the rate
    at which carbon is actually entering the cell, which integrates substrate
    availability AND network state (PEP cofactor depletion stalls PTS even
    if glucose is available).
    """

    met: MetabolismModel
    gene: TranscriptionModel
    n_met: int
    n_gene: int
    cglcex_index: int
    cglcex_init: float
    v_pts_init: float
    signal: str = "concentration"
    synthesis_indices: tuple[int, ...] = SYNTHESIS_REACTION_INDICES
    f_met_fn: Callable[[float, float], float] = field(default=default_f_met)

    # ----- construction -----

    @classmethod
    def build(
        cls,
        met: MetabolismModel | None = None,
        gene: TranscriptionModel | None = None,
        signal: str = "concentration",
        f_met_fn: Callable[[float, float], float] | None = None,
    ) -> "CoupledMetabolismTranscription":
        met = met if met is not None else MetabolismModel.load()
        gene = gene if gene is not None else TranscriptionModel.load()

        met_idx = met.species_index()
        if EXTERNAL_GLUCOSE_SPECIES not in met_idx:
            raise ValueError(
                f"metabolism model lacks expected species {EXTERNAL_GLUCOSE_SPECIES!r}"
            )
        cglcex_idx = met_idx[EXTERNAL_GLUCOSE_SPECIES]
        cglcex0 = float(met.initial_y[cglcex_idx])

        # Stoichiometry assertions: each curated reaction must be a single
        # product-only synthesis with stoichiometry +1 on the expected species.
        S = gene.sbml.stoich
        sp = gene.species_ids
        for j, expected_product in zip(SYNTHESIS_REACTION_INDICES, SYNTHESIS_PRODUCT_SPECIES):
            col = S[:, j]
            nonzero = [(sp[i], int(col[i])) for i in range(len(sp)) if col[i] != 0]
            if nonzero != [(expected_product, 1)]:
                raise AssertionError(
                    f"reaction index {j} expected product-only +1 for {expected_product!r}, "
                    f"got stoichiometry {nonzero}. Vilar SBML changed; recurate "
                    f"SYNTHESIS_REACTION_INDICES in opencell/models/coupled.py."
                )

        # PTS reaction sanity check: confirm r0 is glucose uptake.
        met_S = met.sbml.stoich
        met_sp = met.species_ids
        pts_col = met_S[:, PTS_REACTION_INDEX]
        produces_g6p = pts_col[met_sp.index(PTS_EXPECTED_PRODUCT)] > 0
        consumes_glc = pts_col[cglcex_idx] < 0
        if not (produces_g6p and consumes_glc):
            raise AssertionError(
                f"PTS reaction index {PTS_REACTION_INDEX} did not pass the "
                f"'consumes cglcex, produces cg6p' sanity check. Chassagnole "
                f"SBML changed; re-curate PTS_REACTION_INDEX in coupled.py."
            )
        v_pts0 = float(met.sbml.fluxes(0.0, met.initial_y)[PTS_REACTION_INDEX])

        if signal not in ("concentration", "uptake_flux"):
            raise ValueError(
                f"signal must be 'concentration' or 'uptake_flux', got {signal!r}"
            )
        if f_met_fn is None:
            f_met_fn = default_f_met if signal == "concentration" else f_met_from_uptake_flux

        return cls(
            met=met,
            gene=gene,
            n_met=met.n_species,
            n_gene=gene.n_species,
            cglcex_index=cglcex_idx,
            cglcex_init=cglcex0,
            v_pts_init=v_pts0,
            signal=signal,
            f_met_fn=f_met_fn,
        )

    # ----- state surface -----

    @property
    def initial_y(self) -> np.ndarray:
        return np.concatenate([self.met.initial_y, self.gene.initial_y])

    def split(self, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return y[: self.n_met], y[self.n_met :]

    def species_layout(self) -> dict[str, list[str]]:
        return {"metabolism": list(self.met.species_ids), "gene": list(self.gene.species_ids)}

    def vector_atols(
        self, met_atol: float = 1e-9, gene_atol: float = 1e-3
    ) -> np.ndarray:
        """Per-state atol vector for stiff solvers.

        Mixed-magnitude state: metabolism is mM (~1e-3 to ~1e0), gene is
        molecule counts (DA ~ 1, R ~ 1e3). Per GPT-5 critique.
        """
        return np.concatenate(
            [np.full(self.n_met, met_atol), np.full(self.n_gene, gene_atol)]
        )

    # ----- composite RHS -----

    def f_met(self, t_s: float, y: np.ndarray) -> float:
        y_met, _ = self.split(y)
        if self.signal == "uptake_flux":
            v_pts = float(self.met.sbml.fluxes(t_s, y_met)[PTS_REACTION_INDEX])
            return self.f_met_fn(v_pts, self.v_pts_init)
        return self.f_met_fn(float(y_met[self.cglcex_index]), self.cglcex_init)

    def rhs(self, t_s: float, y: np.ndarray) -> np.ndarray:
        """Composite dy/dt with t in seconds."""
        y_met, y_gene = self.split(y)

        if self.signal == "uptake_flux":
            # Compute met fluxes once and reuse for both met-RHS and f_met.
            # Chassagnole species are concentration-mode in unit-volume
            # compartments, so dy/dt = S @ v matches met.rhs() exactly.
            # (Verified by RHS-equality test in tests/integration.)
            met_fluxes = self.met.sbml.fluxes(t_s, y_met)
            dy_met = self.met.sbml.stoich @ met_fluxes
            f = self.f_met_fn(float(met_fluxes[PTS_REACTION_INDEX]), self.v_pts_init)
        else:
            dy_met = self.met.rhs(t_s, y_met)
            f = self.f_met_fn(float(y_met[self.cglcex_index]), self.cglcex_init)

        t_h = t_s / SECONDS_PER_HOUR
        gene_fluxes_h = self.gene.fluxes(t_h, y_gene).copy()
        for j in self.synthesis_indices:
            gene_fluxes_h[j] *= f
        # Vilar species are hasOnlySubstanceUnits=True -> dy = S @ v (no /V).
        dy_gene_h = self.gene.sbml.stoich @ gene_fluxes_h
        dy_gene_s = dy_gene_h / SECONDS_PER_HOUR

        return np.concatenate([dy_met, dy_gene_s])
