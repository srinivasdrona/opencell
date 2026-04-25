"""Karr-native M1 metabolism module.

Loads Karr's fitted FBA snapshot directly:
  - S: 376 x 504 (fbaReactionStoichiometryMatrix)
  - lb, ub: from fbaReactionBounds (504, 2)
  - obj: fbaObjective (504,) -- biomass at col 502 with coefficient +1000
  - RHS: fbaRightHandSide (376,)
  - reaction WCM IDs (645) and per-FBA-column WCM IDs (504, sparse)
  - Karr's stored runtime fluxs[645] (Mode E oracle)

Replaces the iPS189-based opencell.m1.central_carbon for whole-cell
work.  Same ID space as Karr's other 27 processes, so M1 plugs into
the dynamic loop (vivarium chassis) without translation.

Important: snapshot fbaEnzymeBounds are NOT applied by default.  They
are post-step values (free-enzyme count after substrate binding) and
were proven inconsistent with Karr's own stored fluxs (34/504 cols
violate them by up to 100x).  See Session N+8 / commit c5244f2.
The bounds are exposed for inspection but excluded from the LP.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.optimize import linprog

DEFAULT_FIXTURE_JSON = (
    Path(__file__).resolve().parents[2]
    / "data" / "karr_fixtures" / "karr_native_m1.json"
)

# Default flux ceiling used when relaxing infinities for HiGHS.  Set to
# Karr's natural per-cell-per-second range (stored fluxs span [-1e6, 1e6]
# but conversion fluxes typically <= 1e3).  Documented in
# `artifacts/M1_validation.json` (schema_v4 Mode D).
DEFAULT_BIG = 1e3


@dataclass
class KarrMetabolismModel:
    S: np.ndarray
    RHS: np.ndarray
    lb: np.ndarray
    ub: np.ndarray
    obj: np.ndarray
    enz_bounds: np.ndarray
    catalysis: np.ndarray
    fluxs_stored: np.ndarray
    rxn_wcm_ids_645: list[str]
    fba_col_rxn_wcm: list[str | None]
    biomass_col: int
    stored_runtime: dict
    counts: dict
    raw: dict = field(repr=False)

    @property
    def n_reactions(self) -> int:
        return self.S.shape[1]

    @property
    def n_substrates(self) -> int:
        return self.S.shape[0]

    def reaction_wcm_id_to_645_index(self, wcm_id: str) -> int:
        return self.rxn_wcm_ids_645.index(wcm_id)

    def fba_col_for_wcm_id(self, wcm_id: str) -> int | None:
        """Return the 504-space FBA column for a Karr WCM reaction ID, or None
        if that reaction is not in the metabolicConversion subset."""
        for col, name in enumerate(self.fba_col_rxn_wcm):
            if name == wcm_id:
                return col
        return None


def load_default(path: str | Path | None = None) -> KarrMetabolismModel:
    p = Path(path) if path is not None else DEFAULT_FIXTURE_JSON
    meta = json.loads(p.read_text())
    npz_path = p.parent / Path(meta["matrix_npz"]).name
    z = np.load(npz_path)
    return KarrMetabolismModel(
        S=z["S"],
        RHS=z["RHS"],
        lb=z["lb"],
        ub=z["ub"],
        obj=z["obj"],
        enz_bounds=z["enz_bounds"],
        catalysis=z["catalysis"],
        fluxs_stored=z["fluxs_stored"],
        rxn_wcm_ids_645=list(meta["ids"]["reaction_wcm_645"]),
        fba_col_rxn_wcm=list(meta["ids"]["fba_col_to_reaction_wcm"]),
        biomass_col=int(meta["biomass_col"]),
        stored_runtime=dict(meta["stored_runtime"]),
        counts=dict(meta["counts"]),
        raw=meta,
    )


def solve_fba(
    model: KarrMetabolismModel,
    objective_col: int | None = None,
    sense: str = "max",
    big: float = DEFAULT_BIG,
    use_full_objective: bool = True,
    lb_override: np.ndarray | None = None,
    ub_override: np.ndarray | None = None,
) -> tuple[np.ndarray, dict]:
    """Solve Karr's fitted FBA exactly.

    Default is `use_full_objective=True` (Karr's published 36-nonzero
    objective: +1000 on biomass + 35 small parsimony penalties).
    Set `objective_col` to override and maximise / minimise a single
    column instead.  `big` substitutes for +/-inf in bounds.

    ``lb_override`` / ``ub_override`` (each shape ``(R,)``) replace
    ``model.lb`` / ``model.ub`` for this solve only; the model itself
    is never mutated.  Used by the dynamic-bounds chassis loop.
    """
    R = model.n_reactions
    src_lb = model.lb if lb_override is None else lb_override
    src_ub = model.ub if ub_override is None else ub_override
    if src_lb.shape != (R,) or src_ub.shape != (R,):
        raise ValueError(
            f"bound override shape mismatch: lb {src_lb.shape}, ub {src_ub.shape}, R={R}")
    lb = np.where(np.isfinite(src_lb), src_lb, -big).copy()
    ub = np.where(np.isfinite(src_ub), src_ub,  big).copy()
    lb = np.clip(lb, -big, big)
    ub = np.clip(ub, -big, big)

    sign = -1.0 if sense == "max" else 1.0
    if objective_col is None and use_full_objective:
        c = sign * model.obj.copy()
    else:
        c = np.zeros(R)
        col = model.biomass_col if objective_col is None else int(objective_col)
        c[col] = sign

    bounds = list(zip(lb.tolist(), ub.tolist()))

    res = linprog(
        c=c, A_eq=model.S, b_eq=model.RHS,
        bounds=bounds, method="highs",
        options={"presolve": True},
    )
    if not res.success:
        raise RuntimeError(f"Karr FBA infeasible: {res.message}")

    v = np.asarray(res.x, dtype=float)
    biomass_flux = float(v[model.biomass_col])
    return v, {
        "status": "ok",
        "message": res.message,
        "objective_value": -float(res.fun) if sense == "max" else float(res.fun),
        "biomass_flux_per_s": biomass_flux,
        "biomass_flux_per_h": biomass_flux * 3600.0,
        "big": big,
        "use_full_objective": use_full_objective,
        "n_nonzero": int((np.abs(v) > 1e-9).sum()),
    }


def per_reaction_comparison(
    model: KarrMetabolismModel,
    v: np.ndarray,
    nonzero_only: bool = True,
    tol: float = 1e-9,
) -> list[dict]:
    """Compare predicted FBA fluxes (504-space) against Karr's stored
    runtime fluxs (645-space), for every metabolicConversion FBA col
    that has a WCM ID."""
    out = []
    for col, wcm in enumerate(model.fba_col_rxn_wcm):
        if wcm is None:
            continue
        pred = float(v[col])
        idx_645 = model.rxn_wcm_ids_645.index(wcm)
        karr = float(model.fluxs_stored[idx_645])
        if nonzero_only and abs(pred) < tol and abs(karr) < tol:
            continue
        out.append({
            "fba_col": col,
            "wcm_id": wcm,
            "predicted": pred,
            "karr_stored": karr,
        })
    return out
