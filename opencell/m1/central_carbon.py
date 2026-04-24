"""Central carbon + adenylate FBA module for M1.

All numeric values are loaded from a sourced JSON fixture; nothing is
synthesised in this module.

The fixture (`data/karr_fixtures/iPS189_m1.json`) is produced by
`scripts/karr_a4f_ingest_m1.py` from:
  - Suthers 2009 iPS189 SBML (PLoS Comput Biol s005) — stoichiometry,
    reversibility, biomass equation
  - Karr WholeCellKB Reactions sheet — Keq + kinetic forms
  - Karr parameters.json (A4F path) — exchange-rate upper bounds, NGAM,
    GAM

This module exposes:
  - CentralCarbonModel: holds S matrix, lb/ub vectors, provenance
  - pfba(model, ...): two-stage parsimonious FBA via scipy.optimize.linprog
  - load_default(): factory loading the default fixture

Design notes:
  - Default flux bound magnitude follows the COBRA convention (1000
    mmol/(gDW*h)), used for any reaction not explicitly bounded by a
    Karr-sourced value. This is documented in the fixture under
    `default_flux_bound_convention`.
  - Reversibility is taken verbatim from the iPS189 SBML.
  - Adenylate / nucleotide-balance sanity is a separate test concern;
    the model itself does not enforce conservation explicitly because
    the SBML stoichiometry already does (mass-balanced rows in S).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np
from scipy.optimize import linprog

DEFAULT_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "data" / "karr_fixtures" / "iPS189_m1.json"
)


@dataclass
class CentralCarbonModel:
    """A small FBA model loaded from a sourced JSON fixture."""
    species: list[str]
    reactions: list[str]
    reaction_names: list[str]
    reversibility: np.ndarray
    S: np.ndarray
    lb: np.ndarray
    ub: np.ndarray
    karr_bounds: dict
    sources: dict
    default_bound_magnitude: float
    raw: dict = field(repr=False)
    boundary_species: list[str] = field(default_factory=list)

    @property
    def n_species(self) -> int:
        return self.S.shape[0]

    @property
    def n_reactions(self) -> int:
        return self.S.shape[1]

    @property
    def balanced_species_mask(self) -> np.ndarray:
        """Boolean mask: True for species under quasi-steady-state, False for
        boundary species (suffix `_b` in iPS189 / COBRA SBML convention)."""
        return np.array([s not in set(self.boundary_species)
                         for s in self.species])

    def species_index(self, sid: str) -> int:
        return self.species.index(sid)

    def reaction_index(self, rid: str) -> int:
        return self.reactions.index(rid)

    def stoich(self, species_id: str, reaction_id: str) -> float:
        return float(self.S[self.species_index(species_id),
                            self.reaction_index(reaction_id)])

    def atp_balance_coefficients(self) -> np.ndarray:
        """Row of S corresponding to cytosolic ATP (M_atp_c)."""
        return self.S[self.species_index("M_atp_c")].copy()


def _build_from_fixture(data: dict) -> CentralCarbonModel:
    rxs = data["reactions"]
    reactions = [r["id"] for r in rxs]
    reaction_names = [r["name"] for r in rxs]

    species_order: list[str] = []
    seen: set[str] = set()
    for r in rxs:
        for s in r["reactants"] + r["products"]:
            sid = s["species"]
            if sid not in seen:
                species_order.append(sid)
                seen.add(sid)

    M = len(species_order)
    R = len(reactions)
    S = np.zeros((M, R), dtype=float)
    sp_index = {s: i for i, s in enumerate(species_order)}
    for j, r in enumerate(rxs):
        for s in r["reactants"]:
            S[sp_index[s["species"]], j] -= float(s["stoichiometry"])
        for s in r["products"]:
            S[sp_index[s["species"]], j] += float(s["stoichiometry"])

    reversibility = np.array([bool(r["reversible"]) for r in rxs])

    B = float(data["default_flux_bound_magnitude"])
    lb = np.where(reversibility, -B, 0.0).astype(float)
    ub = np.full(R, B, dtype=float)

    karr = data["karr_sourced_bounds"]
    rid_to_idx = {r: i for i, r in enumerate(reactions)}

    glc_bound = karr["exchangeRateUpperBound_carbon"]["value"]
    if "R_EX_glc_D_e_" in rid_to_idx:
        lb[rid_to_idx["R_EX_glc_D_e_"]] = -float(glc_bound)
        ub[rid_to_idx["R_EX_glc_D_e_"]] = float(glc_bound)

    nc_bound = karr["exchangeRateUpperBound_noncarbon"]["value"]
    for rid in karr["exchangeRateUpperBound_noncarbon"]["applies_to"]:
        if rid in rid_to_idx:
            lb[rid_to_idx[rid]] = -float(nc_bound)
            ub[rid_to_idx[rid]] = float(nc_bound)

    ngam = karr["nonGrowthAssociatedMaintenance"]["value"]
    if "R_ATPM" in rid_to_idx:
        lb[rid_to_idx["R_ATPM"]] = float(ngam)

    return CentralCarbonModel(
        species=species_order,
        reactions=reactions,
        reaction_names=reaction_names,
        reversibility=reversibility,
        S=S,
        lb=lb,
        ub=ub,
        karr_bounds=karr,
        sources=data["sources"],
        default_bound_magnitude=B,
        raw=data,
        boundary_species=[s for s in species_order if s.endswith("_b")],
    )


def load_default(path: Path | str | None = None) -> CentralCarbonModel:
    p = Path(path) if path is not None else DEFAULT_FIXTURE_PATH
    data = json.loads(Path(p).read_text())
    return _build_from_fixture(data)


def pfba(
    model: CentralCarbonModel,
    objective_reaction: str,
    sense: str = "max",
    pfba_fraction: float = 1.0,
) -> tuple[np.ndarray, dict]:
    """Two-stage parsimonious FBA.

    LP1: optimise the chosen objective reaction subject to S v = 0,
         lb <= v <= ub.
    LP2: minimise total absolute flux Sigma|v| subject to the LP1 optimum.
    """
    R = model.n_reactions
    obj_idx = model.reaction_index(objective_reaction)
    sign = -1.0 if sense == "max" else 1.0
    c = np.zeros(R)
    c[obj_idx] = sign

    bounds = list(zip(model.lb.tolist(), model.ub.tolist()))

    # Only impose S v = 0 on quasi-steady (non-boundary) species.
    # Boundary species (suffix _b) are system sinks/sources by COBRA
    # convention; their rows must be excluded.
    bal_mask = model.balanced_species_mask
    A_eq = model.S[bal_mask]
    b_eq = np.zeros(int(bal_mask.sum()))

    res1 = linprog(
        c=c, A_eq=A_eq, b_eq=b_eq,
        bounds=bounds, method="highs",
        options={"presolve": True},
    )
    if not res1.success:
        raise RuntimeError(f"pFBA LP1 infeasible: {res1.message}")

    obj_value = -res1.fun if sense == "max" else res1.fun

    A_eq2_top = np.hstack([A_eq, -A_eq])
    A_eq2_bot = np.zeros((1, 2 * R))
    A_eq2_bot[0, obj_idx] = 1.0
    A_eq2_bot[0, R + obj_idx] = -1.0
    A_eq2 = np.vstack([A_eq2_top, A_eq2_bot])
    b_eq2 = np.concatenate([b_eq, [pfba_fraction * obj_value]])

    A_ub2 = np.vstack([
        np.hstack([np.eye(R), -np.eye(R)]),
        np.hstack([-np.eye(R), np.eye(R)]),
    ])
    b_ub2 = np.concatenate([model.ub, -model.lb])

    c2 = np.ones(2 * R)
    bounds2 = [(0.0, None)] * (2 * R)

    res2 = linprog(
        c=c2, A_eq=A_eq2, b_eq=b_eq2,
        A_ub=A_ub2, b_ub=b_ub2,
        bounds=bounds2, method="highs",
        options={"presolve": True},
    )
    if not res2.success:
        return res1.x, {
            "objective_value": obj_value,
            "objective_reaction": objective_reaction,
            "pfba_status": "lp2_failed_returning_lp1",
            "lp1_message": res1.message,
            "lp2_message": res2.message,
            "total_flux_l1": float(np.sum(np.abs(res1.x))),
        }

    v = res2.x[:R] - res2.x[R:]
    return v, {
        "objective_value": obj_value,
        "objective_reaction": objective_reaction,
        "pfba_status": "ok",
        "total_flux_l1": float(res2.fun),
    }


def reaction_summary(model: CentralCarbonModel,
                     v: np.ndarray,
                     reactions: Iterable[str] | None = None,
                     tol: float = 1e-9) -> list[tuple[str, float]]:
    """Return [(rid, flux), ...] for non-zero or selected reactions."""
    if reactions is None:
        return [(rid, float(v[i])) for i, rid in enumerate(model.reactions)
                if abs(v[i]) > tol]
    return [(rid, float(v[model.reaction_index(rid)])) for rid in reactions]
