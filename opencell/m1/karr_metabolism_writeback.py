"""Karr-faithful Metabolism substrate writeback (post-FBA evolveState steps).

Implements Karr's 4-step substrate writeback + metabolite clipping from
`data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Metabolism.m`
lines 1200-1258, isolated for unit-testing independent of the Vivarium process.

Algorithm (per Karr `evolveState`):

  Step 1 (line 1213-1215): nutrient uptake
    substrates[ext_idx, extracellular_col] -= stochRound(v[fba_ext_idx] * stepSize)

  Step 2 (line 1218-1220): recycled metabolites (cytosol via single-arg linear idx)
    substrates[int_idx, cytosol_col] += stochRound(v[fba_int_idx])

  Step 3 (line 1223-1225): new biomass (full 585x3 matrix add)
    substrates += stochRound(metabolismNewProduction * growth * stepSize)

  Step 4 (line 1228-1231): unaccounted energy on 5 ATP-hydrolysis substrates
    substrates[atp_idx, cytosol_col] += [-1,-1,1,1,1] * stochRound(unaccounted * growth * stepSize)

  Step 5 (line 1235-1253): clip metabolites
    substrates[metabolite_rows, :] = max(0, substrates[metabolite_rows, :])

Architectural decisions (see docs/phase_f/METABOLISM_FIX_DESIGN.md):
  - Returns a per-WID flat delta (sum across compartments) for OC's shared port.
  - Uses _Mcg16807 RNG per-instance, seeded by caller (no global state).
  - Step 5 clip is applied on the post-state and translates to a clamped delta.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat

# Compartment column indices (0-based; Karr MATLAB uses 1-based)
CYTOSOL = 0
EXTRACELLULAR = 1
MEMBRANE = 2

# ATP-hydrolysis sign pattern (Metabolism.m:1230 [-1; -1; 1; 1; 1])
ATP_HYDROLYSIS_SIGNS = np.array([-1, -1, 1, 1, 1], dtype=np.int64)


@dataclass
class KarrWritebackFixture:
    """Indices and constants required for Karr's substrate writeback.

    All indices are 0-based (converted from MATLAB 1-based on load).
    """

    sub_idx_external: np.ndarray  # (124,) substrate rows for external exchange
    sub_idx_internal: np.ndarray  # (42,)  substrate rows for internal exchange (cytosol)
    sub_idx_atp_hydrolysis: np.ndarray  # (5,) ATP hydrolysis substrate rows
    fba_idx_external: np.ndarray  # (124,) FBA col indices for external exchange reactions
    fba_idx_internal: np.ndarray  # (42,)  FBA col indices for internal exchange reactions
    metabolism_new_production: np.ndarray  # (585, 3) precomputed biomass production per tick per unit growth
    unaccounted_energy_consumption: float  # scalar
    metabolite_row_idx: np.ndarray  # (567,) substrate rows that are metabolites (subject to max-0 clip)
    step_size_sec: float = 1.0

    @classmethod
    def from_mat(cls, path: str | Path) -> "KarrWritebackFixture":
        """Load all required indices/constants from Metabolism_flat.mat."""
        mat = loadmat(str(path), squeeze_me=True, struct_as_record=False)
        fix = mat["data"].fixture

        def to_0based(arr: np.ndarray) -> np.ndarray:
            return np.asarray(arr, dtype=np.int64) - 1

        return cls(
            sub_idx_external=to_0based(fix.substrateIndexs_externalExchangedMetabolites),
            sub_idx_internal=to_0based(fix.substrateIndexs_internalExchangedMetabolites),
            sub_idx_atp_hydrolysis=to_0based(fix.substrateIndexs_atpHydrolysis),
            fba_idx_external=to_0based(fix.fbaReactionIndexs_metaboliteExternalExchange),
            fba_idx_internal=to_0based(fix.fbaReactionIndexs_metaboliteInternalExchange),
            metabolism_new_production=np.asarray(fix.metabolismNewProduction, dtype=np.float64),
            unaccounted_energy_consumption=float(fix.unaccountedEnergyConsumption),
            # substrateMetaboliteLocalIndexs is (567, 1) — first column = global substrate row
            metabolite_row_idx=to_0based(np.asarray(fix.substrateMetaboliteLocalIndexs)[:, 0]
                                         if np.asarray(fix.substrateMetaboliteLocalIndexs).ndim == 2
                                         else np.asarray(fix.substrateMetaboliteLocalIndexs)),
            step_size_sec=float(fix.stepSizeSec),
        )


def apply_karr_substrate_writeback(
    *,
    pre_state_585x3: np.ndarray,
    v_504: np.ndarray,
    growth_per_s: float,
    fixture: KarrWritebackFixture,
    rng: Any,  # _Mcg16807 instance with .stochastic_round(np.ndarray) -> np.ndarray[int64]
    step_size_sec: float | None = None,
) -> np.ndarray:
    """Compute Karr's 4-step substrate delta + clip, return (585, 3) delta.

    Parameters
    ----------
    pre_state_585x3 : (585, 3) float array
        Substrate counts before FBA — used for Step 5 clipping. Caller's
        responsibility to provide cytosol values from shared state and
        non-cytosol values from internal tracking or fixture defaults.
    v_504 : (504,) float array
        FBA reaction flux vector (output of solve_fba).
    growth_per_s : float
        Biomass flux per second (FBA objective value).
    fixture : KarrWritebackFixture
        Index arrays loaded from Metabolism_flat.mat.
    rng : _Mcg16807
        MATLAB-compatible RNG instance providing stochastic_round().
    step_size_sec : float, optional
        Time step in seconds. Defaults to fixture.step_size_sec.

    Returns
    -------
    delta_585x3 : (585, 3) int64 array
        Substrate delta to apply. Already clipped: post_state + delta will
        never drive a metabolite below zero.
    """
    step = float(step_size_sec) if step_size_sec is not None else fixture.step_size_sec
    delta = np.zeros((585, 3), dtype=np.int64)

    # Step 1: nutrient uptake (Metabolism.m:1213-1215)
    # substrates[ext, extracellular] -= stochRound(v[fba_ext] * step)
    ext_flow = v_504[fixture.fba_idx_external] * step
    delta[fixture.sub_idx_external, EXTRACELLULAR] -= rng.stochastic_round(ext_flow)

    # Step 2: recycled metabolites (Metabolism.m:1218-1220)
    # Single-arg MATLAB linear index on (585, 3) with values <= 585 → cytosol col 0
    # substrates[int, cytosol] += stochRound(v[fba_int])
    int_flow = v_504[fixture.fba_idx_internal]  # NOTE: no step multiplier per Karr line 1220
    delta[fixture.sub_idx_internal, CYTOSOL] += rng.stochastic_round(int_flow)

    # Step 3: new biomass (Metabolism.m:1223-1225)
    # substrates += stochRound(metabolismNewProduction * growth * step)
    biomass_flow = fixture.metabolism_new_production * growth_per_s * step
    delta += rng.stochastic_round(biomass_flow)

    # Step 4: unaccounted energy (Metabolism.m:1228-1231)
    # substrates[atp_hydrolysis, cytosol] += [-1,-1,1,1,1] * stochRound(unaccounted * growth * step)
    unaccounted_qty = fixture.unaccounted_energy_consumption * growth_per_s * step
    # Karr applies one scalar stochRound, then broadcasts the sign vector
    unaccounted_rounded = rng.stochastic_round(np.asarray([unaccounted_qty], dtype=np.float64))
    delta[fixture.sub_idx_atp_hydrolysis, CYTOSOL] += (
        ATP_HYDROLYSIS_SIGNS * int(unaccounted_rounded[0])
    )

    # Step 5: clip metabolites (Metabolism.m:1235-1253)
    # post = pre + delta; clip metabolite rows to >= 0; recompute delta
    post = pre_state_585x3 + delta.astype(np.float64)
    met_idx = fixture.metabolite_row_idx
    clipped_post = post.copy()
    clipped_post[met_idx, :] = np.maximum(0.0, clipped_post[met_idx, :])
    # Final delta is integer-valued because pre + delta was integer (assuming pre is integer)
    # but we keep float in case caller passes non-integer pre.
    clipped_delta = (clipped_post - pre_state_585x3).astype(np.int64)
    return clipped_delta


def project_to_flat_per_wid(
    delta_585x3: np.ndarray,
    sub_wids_585: list[str],
) -> dict[str, float]:
    """Project (585, 3) compartmented delta to a flat per-WID dict (sum across compartments).

    Skips zero entries to keep the emitted dict small (Vivarium accumulator
    skips missing keys = treats as zero delta).
    """
    totals = delta_585x3.sum(axis=1)  # (585,)
    return {
        sub_wids_585[i]: float(totals[i])
        for i in range(len(sub_wids_585))
        if totals[i] != 0
    }
