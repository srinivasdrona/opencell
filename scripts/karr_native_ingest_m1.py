"""Extract Karr's fitted FBA matrices into a committable fixture.

Reads `data/m1_sources/karr_flat/sim_fitted_targeted.mat` (gitignored)
and writes:
  - data/karr_fixtures/karr_native_m1.json  (metadata + ID strings)
  - data/karr_fixtures/karr_native_m1.npz   (numeric matrices)

The fixture is the sole runtime dependency of
`opencell.m1.karr_metabolism`; no MAT access at runtime.

Run via .venv-wsl:
  wsl bash -lc 'source /mnt/e/opencell/.venv-wsl/bin/activate && \
                python /mnt/e/opencell/scripts/karr_native_ingest_m1.py'
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

REPO = Path(__file__).resolve().parents[1]
MAT = REPO / "data" / "m1_sources" / "karr_flat" / "sim_fitted_targeted.mat"
OUT_DIR = REPO / "data" / "karr_fixtures"
JSON_OUT = OUT_DIR / "karr_native_m1.json"
NPZ_OUT = OUT_DIR / "karr_native_m1.npz"

SCHEMA_VERSION = "karr_native_m1__v1"


def _to_str_list(arr) -> list[str]:
    a = np.asarray(arr).reshape(-1)
    return [str(x) for x in a.tolist()]


def _to_int_idx(arr) -> np.ndarray:
    """MATLAB 1-based -> Python 0-based int64."""
    return np.asarray(arr).reshape(-1).astype(np.int64) - 1


def main() -> None:
    if not MAT.exists():
        raise SystemExit(f"missing {MAT} - run extract_karr_targeted.m first")

    m = loadmat(str(MAT), struct_as_record=False, squeeze_me=True)
    met = m["data"].metabolism
    mr = m["data"].states.State_MetabolicReaction

    # Numeric matrices (committed to .npz)
    S = np.asarray(met.fbaReactionStoichiometryMatrix, dtype=float)
    RHS = np.asarray(met.fbaRightHandSide, dtype=float).reshape(-1)
    bounds = np.asarray(met.fbaReactionBounds, dtype=float)
    lb = bounds[:, 0].copy()
    ub = bounds[:, 1].copy()
    obj = np.asarray(met.fbaObjective, dtype=float).reshape(-1)
    enz_bounds = np.asarray(met.fbaEnzymeBounds, dtype=float)
    catalysis = np.asarray(met.fbaReactionCatalysisMatrix, dtype=np.uint8)

    # Stored runtime values (the Mode E oracle baseline)
    fluxs_stored = np.asarray(mr.dump.fluxs, dtype=float).reshape(-1)
    growth_stored = float(np.asarray(mr.dump.growth).item())
    growth0_stored = float(np.asarray(mr.dump.growth0).item())
    mean_init_growth = float(np.asarray(mr.dump.meanInitialGrowthRate).item())
    doubling_time = float(np.asarray(mr.dump.doublingTime).item())

    # Index maps (0-based)
    fba_idx_metab_conv = _to_int_idx(met.fbaReactionIndexs_metabolicConversion)
    fba_idx_ext_exch = _to_int_idx(met.fbaReactionIndexs_metaboliteExternalExchange)
    fba_idx_int_exch = _to_int_idx(met.fbaReactionIndexs_metaboliteInternalExchange)
    fba_idx_int_lim = _to_int_idx(met.fbaReactionIndexs_metaboliteInternalLimitedExchange)
    fba_idx_int_unlim = _to_int_idx(met.fbaReactionIndexs_metaboliteInternalUnlimitedExchange)

    fba_sub_idx_substrates = _to_int_idx(met.fbaSubstrateIndexs_substrates)
    fba_sub_idx_int_exch_constraints = _to_int_idx(
        met.fbaSubstrateIndexs_metaboliteInternalExchangeConstraints
    )

    rxn_idx_fba = _to_int_idx(met.reactionIndexs_fba)        # (336,) -> 645 space

    # Names (645 reactions, 585 substrates, 104 enzymes)
    rxn_wcm_ids = _to_str_list(met.reactionWholeCellModelIDs)
    rxn_names = _to_str_list(met.reactionNames)
    rxn_types = _to_str_list(met.reactionTypes)
    sub_wcm_ids = _to_str_list(met.substrateWholeCellModelIDs)
    sub_names = _to_str_list(met.substrateNames)
    enz_wcm_ids = _to_str_list(met.enzymeWholeCellModelIDs)

    n_fba_rxn = S.shape[1]
    n_fba_sub = S.shape[0]
    n_metab_conv = fba_idx_metab_conv.size

    # Per-FBA-column WCM reaction ID (only the metabolicConversion cols
    # have a 1:1 named reaction; exchange cols have substrate-scoped names).
    fba_col_rxn_wcm_id: list[str | None] = [None] * n_fba_rxn
    for fba_col, rxn645 in enumerate(rxn_idx_fba):
        # rxn_idx_fba is the 336-len map: it gives the 645-space index
        # of each metabolicConversion FBA col (in order).
        fba_metab_conv_col = int(fba_idx_metab_conv[fba_col])
        fba_col_rxn_wcm_id[fba_metab_conv_col] = rxn_wcm_ids[int(rxn645)]

    # Locate biomass column: fbaObjective has +1000 on biomass, ~0 elsewhere.
    biomass_candidates = list(np.where(obj > 1.0)[0])
    if len(biomass_candidates) != 1:
        raise RuntimeError(
            f"expected exactly one large positive obj entry, got {biomass_candidates}"
        )
    biomass_col = int(biomass_candidates[0])

    # Sanity: confirm Karr's stored fluxs are consistent with rxn_wcm_ids count
    assert fluxs_stored.size == len(rxn_wcm_ids), (
        f"fluxs[{fluxs_stored.size}] != reactionWholeCellModelIDs[{len(rxn_wcm_ids)}]"
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        NPZ_OUT,
        S=S, RHS=RHS, lb=lb, ub=ub, obj=obj,
        enz_bounds=enz_bounds, catalysis=catalysis,
        fluxs_stored=fluxs_stored,
        fba_idx_metab_conv=fba_idx_metab_conv,
        fba_idx_ext_exch=fba_idx_ext_exch,
        fba_idx_int_exch=fba_idx_int_exch,
        fba_idx_int_lim=fba_idx_int_lim,
        fba_idx_int_unlim=fba_idx_int_unlim,
        fba_sub_idx_substrates=fba_sub_idx_substrates,
        fba_sub_idx_int_exch_constraints=fba_sub_idx_int_exch_constraints,
        rxn_idx_fba=rxn_idx_fba,
    )
    JSON_OUT.write_text(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "source_mat": str(MAT.relative_to(REPO)),
        "matrix_npz": str(NPZ_OUT.relative_to(REPO)),
        "shapes": {
            "S": list(S.shape),
            "RHS": list(RHS.shape),
            "fbaReactionBounds": list(bounds.shape),
            "fbaObjective": list(obj.shape),
            "fbaEnzymeBounds": list(enz_bounds.shape),
            "fluxs_stored": list(fluxs_stored.shape),
        },
        "counts": {
            "n_fba_reactions": n_fba_rxn,
            "n_fba_substrates": n_fba_sub,
            "n_metabolic_conversion_cols": n_metab_conv,
            "n_external_exchange_cols": int(fba_idx_ext_exch.size),
            "n_internal_exchange_cols": int(fba_idx_int_exch.size),
            "n_reactions_total": len(rxn_wcm_ids),
            "n_substrates_total": len(sub_wcm_ids),
            "n_enzymes_total": len(enz_wcm_ids),
            "fluxs_nonzero": int((fluxs_stored != 0).sum()),
        },
        "biomass_col": biomass_col,
        "biomass_objective_coefficient": float(obj[biomass_col]),
        "stored_runtime": {
            "growth_per_s": growth_stored,
            "growth_per_h": growth_stored * 3600.0,
            "growth0_per_s": growth0_stored,
            "meanInitialGrowthRate_per_s": mean_init_growth,
            "doublingTime_s": doubling_time,
            "doublingTime_h": doubling_time / 3600.0,
        },
        "ids": {
            "reaction_wcm_645": rxn_wcm_ids,
            "reaction_names_645": rxn_names,
            "reaction_types_645": rxn_types,
            "substrate_wcm_585": sub_wcm_ids,
            "substrate_names_585": sub_names,
            "enzyme_wcm_104": enz_wcm_ids,
            "fba_col_to_reaction_wcm": fba_col_rxn_wcm_id,
        },
        "interpretation": (
            "Karr-native FBA snapshot: 376 substrates x 504 reactions. "
            "504 fba cols = 336 metabolic-conversion + 124 external-exchange "
            "+ 42 internal-exchange (35 limited + 7 unlimited). Biomass at "
            f"col {biomass_col} with obj=+{float(obj[biomass_col]):.0f}. "
            "Per-FBA-column reaction WCM IDs are present only for the 336 "
            "metabolicConversion cols (others are substrate-scoped exchange "
            "pseudo-reactions). Stored runtime growth = "
            f"{growth_stored*3600:.4f} /h is the Mode E oracle ground truth."
        ),
    }, indent=2))

    print(f"wrote {JSON_OUT.relative_to(REPO)} ({JSON_OUT.stat().st_size:,} B)")
    print(f"wrote {NPZ_OUT.relative_to(REPO)} ({NPZ_OUT.stat().st_size:,} B)")
    print(f"S: {S.shape}, biomass_col={biomass_col}, "
          f"stored growth={growth_stored*3600:.4f} /h")


if __name__ == "__main__":
    main()
