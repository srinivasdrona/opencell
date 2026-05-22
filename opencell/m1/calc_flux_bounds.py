"""Python port of Karr's Metabolism.calcFluxBounds().

Reference: data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/
+process/Metabolism.m, lines 1318-1402.

Computes per-FBA-reaction (504,2) [lower, upper] bounds at each tick from
the current substrate counts (585, 3) and enzyme counts (104,) plus
static fixture data.  Implements rules 1-5; rule 6 (protein bounds) is
deferred to Phase C and raises NotImplementedError if requested.

Bound rules (all evaluated when the corresponding flag is True; default
all on):

  1. Enzyme kinetic:  lo/hi = kcat_lo/hi * (catalysis @ enzymes)
  2. Enzyme presence: catalysed reactions with rxnEnzymes <= 0  ->  [0, 0]
  3. Directionality:  clamp metabolicConversion + biomassExchange +
     biomassProduction + internalExchange to static fbaReactionBounds
  4. External metabolite availability:
       upper[external] = min(upper, substrate[ext_idx, extracellular] / dt)
       lower[external] = max(lower, fbaRxnBnds[ext, 0] * cellDryMass)
       upper[external] = min(upper, fbaRxnBnds[ext, 1] * cellDryMass)
  5. Internal metabolite availability:
       lower[int_lim] = max(lower, -substrate[int_lim_idx, *] / dt)
     where the [*] follows MATLAB linear-indexing of (585, 3) and lands
     on the cytosol slice for the substrateIndexs_internalExchangedLimited
     vector by construction (Metabolism.m:1383-1387).

Validation oracle: data/karr_fixtures/karr_native_m1_dynamics.{json,npz}
contains the MATLAB-computed bounds_dynamic_no_protein at the snapshot
inputs; tests/m1/test_calc_flux_bounds.py asserts Python output matches.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

DEFAULT_FIXTURE_JSON = (
    Path(__file__).resolve().parents[2] / "data" / "karr_fixtures" / "karr_native_m1_dynamics.json"
)


@dataclass
class M1DynamicsInputs:
    """Static + snapshot data needed to recompute M1 flux bounds each tick."""

    substrates_snapshot: np.ndarray  # (585, 3) snapshot counts
    enzymes_snapshot: np.ndarray  # (104,) snapshot enzyme counts
    cell_dry_mass: float
    step_size_sec: float
    compartment_extracellular_0based: int

    # Linear-index breakouts of substrateIndexs_fba (368-len each)
    substrate_idx_fba_sub0: np.ndarray  # (368,) -> 585
    substrate_idx_fba_cmp0: np.ndarray  # (368,) -> 3

    # Substrate-only index lists used by rules 4/5
    substrate_idx_external_exch_0: np.ndarray  # (k,) -> 585
    substrate_idx_internal_lim_0: np.ndarray  # (m,) -> 585

    # FBA-reaction selector arrays (504-space)
    fba_rxn_idx_metab_conv: np.ndarray
    fba_rxn_idx_external_exch: np.ndarray
    fba_rxn_idx_internal_exch: np.ndarray
    fba_rxn_idx_internal_lim_exch: np.ndarray
    fba_rxn_idx_internal_unlim_exch: np.ndarray
    fba_rxn_idx_biomass_production: np.ndarray
    fba_rxn_idx_biomass_exchange: np.ndarray

    # MATLAB oracles for tests
    bounds_dynamic_no_protein_oracle: np.ndarray  # (504, 2)
    bounds_dynamic_with_protein_oracle: np.ndarray  # (504, 2)

    raw: dict = field(repr=False)


def load_default_dynamics(path: str | Path | None = None) -> M1DynamicsInputs:
    p = Path(path) if path is not None else DEFAULT_FIXTURE_JSON
    meta = json.loads(p.read_text())
    z = np.load(p.parent / Path(meta["matrix_npz"]).name)
    sc = meta["scalars"]
    return M1DynamicsInputs(
        substrates_snapshot=z["substrates_snapshot"].astype(float),
        enzymes_snapshot=z["enzymes_snapshot"].astype(float),
        cell_dry_mass=float(sc["cell_dry_mass"]),
        step_size_sec=float(sc["step_size_sec"]),
        compartment_extracellular_0based=int(sc["compartment_extracellular_0based"]),
        substrate_idx_fba_sub0=z["substrate_idx_fba_sub0"].astype(np.int64),
        substrate_idx_fba_cmp0=z["substrate_idx_fba_cmp0"].astype(np.int64),
        substrate_idx_external_exch_0=z["substrate_idx_external_exch_0"].astype(np.int64),
        substrate_idx_internal_lim_0=z["substrate_idx_internal_lim_0"].astype(np.int64),
        fba_rxn_idx_metab_conv=z["fba_rxn_idx_metab_conv"].astype(np.int64),
        fba_rxn_idx_external_exch=z["fba_rxn_idx_external_exch"].astype(np.int64),
        fba_rxn_idx_internal_exch=z["fba_rxn_idx_internal_exch"].astype(np.int64),
        fba_rxn_idx_internal_lim_exch=z["fba_rxn_idx_internal_lim_exch"].astype(np.int64),
        fba_rxn_idx_internal_unlim_exch=z["fba_rxn_idx_internal_unlim_exch"].astype(np.int64),
        fba_rxn_idx_biomass_production=z["fba_rxn_idx_biomass_production"].astype(np.int64),
        fba_rxn_idx_biomass_exchange=z["fba_rxn_idx_biomass_exchange"].astype(np.int64),
        bounds_dynamic_no_protein_oracle=z["bounds_dynamic_no_protein"].astype(float),
        bounds_dynamic_with_protein_oracle=z["bounds_dynamic_with_protein"].astype(float),
        raw=meta,
    )


def compute_bounds(
    *,
    substrates: np.ndarray,  # (585, 3)
    enzymes: np.ndarray,  # (104,)
    cell_dry_mass: float,
    step_size_sec: float,
    catalysis: np.ndarray,  # (504, 104)  fbaReactionCatalysisMatrix
    enz_bounds: np.ndarray,  # (504, 2)    fbaEnzymeBounds (kcat * dt)
    fba_reaction_bounds: np.ndarray,  # (504, 2)    static fbaReactionBounds
    dyn: M1DynamicsInputs,
    apply_enzyme_kinetic: bool = True,
    apply_enzyme_presence: bool = True,
    apply_directionality: bool = True,
    apply_external_metabolite: bool = True,
    apply_internal_metabolite: bool = True,
    apply_protein_bounds: bool = False,
) -> np.ndarray:
    """Return (504, 2) [lower, upper] bound matrix.

    Mirrors Metabolism.calcFluxBounds().  ``apply_protein_bounds=True``
    raises NotImplementedError (Phase C).
    """
    if apply_protein_bounds:
        raise NotImplementedError("rule 6 (protein bounds) deferred to Phase C")

    n_rxn = catalysis.shape[0]
    if catalysis.shape != (n_rxn, enzymes.size):
        raise ValueError(f"catalysis {catalysis.shape} vs enzymes {enzymes.size}")
    if substrates.shape[0] < 1 or substrates.shape[1] < 1:
        raise ValueError(f"substrates shape {substrates.shape}")

    lower = np.full(n_rxn, -np.inf, dtype=float)
    upper = np.full(n_rxn, np.inf, dtype=float)

    # rxnEnzymes = catalysis @ enzymes  (504,)
    rxn_enz = catalysis.astype(float) @ enzymes.astype(float)

    # ---- Rule 1: enzyme kinetic ---------------------------------------
    if apply_enzyme_kinetic:
        # inf*0 -> NaN warning is benign: fmax/fmin treat NaN as missing,
        # so kinetic constraint is dropped exactly where it should be.
        with np.errstate(invalid="ignore"):
            kin_lo = enz_bounds[:, 0] * rxn_enz
            kin_hi = enz_bounds[:, 1] * rxn_enz
        lower = np.fmax(lower, kin_lo)
        upper = np.fmin(upper, kin_hi)

    # ---- Rule 2: enzyme presence (catalysed but no enzymes -> [0,0]) --
    if apply_enzyme_presence:
        any_cat = np.any(catalysis != 0, axis=1)
        no_enz = rxn_enz <= 0.0
        zero_mask = any_cat & no_enz
        lower[zero_mask] = 0.0
        upper[zero_mask] = 0.0

    # ---- Rule 3: directionality / static bounds -----------------------
    if apply_directionality:
        for sel in (
            dyn.fba_rxn_idx_metab_conv,
            dyn.fba_rxn_idx_internal_exch,
            dyn.fba_rxn_idx_biomass_exchange,
            dyn.fba_rxn_idx_biomass_production,
        ):
            lower[sel] = np.fmax(lower[sel], fba_reaction_bounds[sel, 0])
            upper[sel] = np.fmin(upper[sel], fba_reaction_bounds[sel, 1])

    # ---- Rule 4: external metabolite availability ---------------------
    if apply_external_metabolite:
        ext_rxn = dyn.fba_rxn_idx_external_exch
        ext_sub = dyn.substrate_idx_external_exch_0
        cmp_ext = dyn.compartment_extracellular_0based
        if ext_rxn.size != ext_sub.size:
            raise ValueError(
                f"external rxn count {ext_rxn.size} != external sub count {ext_sub.size}"
            )
        avail = substrates[ext_sub, cmp_ext] / step_size_sec
        upper[ext_rxn] = np.fmin(upper[ext_rxn], avail)
        lower[ext_rxn] = np.fmax(lower[ext_rxn], fba_reaction_bounds[ext_rxn, 0] * cell_dry_mass)
        upper[ext_rxn] = np.fmin(upper[ext_rxn], fba_reaction_bounds[ext_rxn, 1] * cell_dry_mass)

    # ---- Rule 5: internal metabolite availability ---------------------
    if apply_internal_metabolite:
        int_rxn = dyn.fba_rxn_idx_internal_lim_exch
        int_sub = dyn.substrate_idx_internal_lim_0
        if int_rxn.size != int_sub.size:
            raise ValueError(f"internal-lim rxn count {int_rxn.size} != sub count {int_sub.size}")
        # MATLAB linear indexing into (585, 3) with a substrate-only index
        # vector lands on the cytosol slice (indices < 585 are column 1).
        # We use cytosol explicitly (compartment 0).
        cytosol_counts = substrates[int_sub, 0]
        lower[int_rxn] = np.fmax(lower[int_rxn], -cytosol_counts / step_size_sec)

    return np.column_stack([lower, upper])
