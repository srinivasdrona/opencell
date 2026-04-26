"""D.1: Extract Karr's compartmented metabolic-reaction stoichiometry into
a committable fixture.

Reads `data/m1_sources/karr_flat/sim_fitted_targeted.mat` (gitignored)
and writes:
  - data/karr_fixtures/karr_native_m1_compartmented.json (metadata + IDs)
  - data/karr_fixtures/karr_native_m1_compartmented.npz  (sparse S +
    cell-scale conversion constants)

Schema:
  S_compartmented[585, 645, 3] - int8 (sufficient for [-128, 127])
    indices: substrate_idx (0..584), reaction_idx (0..644), compartment_idx (0..2)
    compartment 0=cytosol, 1=extracellular, 2=membrane
    sign: positive = produced by reaction, negative = consumed.

Honest scope:
  This fixture is the INPUT data needed for true LP-derived per-substrate
  per-compartment replenishment. It does NOT itself implement that LP-
  derived replenishment, because the spike (Phase D.1 spike) showed
  Karr's FBA submodel does not source ATP/CTP/GTP/UTP through internal
  exchanges (those go through non-FBA processes M4-M28). What we CAN do
  with this fixture is cross-validate the calibrated C.4 baseline by
  computing the SS net production per substrate per compartment from the
  FBA solution and comparing to the C.4 demand-based baseline.

Run:
  cd /mnt/e/opencell && source .venv-wsl/bin/activate && \
      python scripts/karr_native_ingest_compartmented.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

REPO = Path(__file__).resolve().parents[1]
MAT = REPO / "data" / "m1_sources" / "karr_flat" / "sim_fitted_targeted.mat"
JSON_OUT = REPO / "data" / "karr_fixtures" / "karr_native_m1_compartmented.json"
NPZ_OUT  = REPO / "data" / "karr_fixtures" / "karr_native_m1_compartmented.npz"

SCHEMA_VERSION = "karr_native_m1_compartmented__v1"

# Karr's metabolism uses 3 of the 6 KB compartments. From the existing
# karr_native_m1_dynamics extract: [cytosol, extracellular, membrane].
COMPARTMENT_WIDS_3 = ["c", "e", "m"]

# Cell dry mass (g/cell) at SS, sourced from Karr's mass-state extract;
# already used by `karr_native_m1_dynamics`.
CELL_DRY_MASS_G = 3.944640855678535e-15


def _to_struct(rec):
    """Resolve scipy mat_struct -> attrgetter."""
    return rec


def main() -> None:
    if not MAT.exists():
        raise FileNotFoundError(
            f"Run scripts/matlab/extract_karr_targeted.m first; missing {MAT}"
        )
    raw = loadmat(MAT, squeeze_me=True, struct_as_record=False)
    sim = raw["data"]
    met = sim.metabolism

    S = np.asarray(met.reactionStoichiometryMatrix, dtype=np.int16)  # (585, 645, 3)
    if S.ndim != 3 or S.shape != (585, 645, 3):
        raise RuntimeError(f"unexpected S shape: {S.shape}")
    nnz = int(np.count_nonzero(S))

    sub_wids = [str(s) for s in np.atleast_1d(met.substrateWholeCellModelIDs).tolist()]
    rxn_wids = [str(s) for s in np.atleast_1d(met.reactionWholeCellModelIDs).tolist()]
    if len(sub_wids) != 585:
        raise RuntimeError(f"expected 585 substrate IDs, got {len(sub_wids)}")
    if len(rxn_wids) != 645:
        raise RuntimeError(f"expected 645 reaction IDs, got {len(rxn_wids)}")

    # Sanity-check: sum over compartments should match Karr's projected
    # FBA stoichiometry (376 internal substrates x 504 FBA cols) up to
    # the substrate/reaction subset projection. We can't directly compare
    # without the exact projection, so we publish a quick row/col sums
    # audit and let the fixture stand on its own.
    S_aggregate = S.sum(axis=2)  # (585, 645) — molecule counts ignoring compartment
    nnz_agg = int(np.count_nonzero(S_aggregate))

    # Per-compartment column-mass conservation check (signed sum per rxn,
    # per compartment). For balanced reactions, mass-weighted sum is 0;
    # but counts-only sum is not 0 because mass is encoded in atom counts.
    per_rxn_per_cmp_signed = S.sum(axis=0)  # (645, 3)
    n_rxns_with_cyt_imbalance = int(np.count_nonzero(per_rxn_per_cmp_signed[:, 0]))

    cyt_idx, ext_idx, mem_idx = 0, 1, 2
    nnz_cyt = int(np.count_nonzero(S[:, :, cyt_idx]))
    nnz_ext = int(np.count_nonzero(S[:, :, ext_idx]))
    nnz_mem = int(np.count_nonzero(S[:, :, mem_idx]))

    # Save NPZ.
    NPZ_OUT.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        NPZ_OUT,
        S_compartmented=S,
        S_aggregate=S_aggregate,
    )

    out = {
        "schema_version": SCHEMA_VERSION,
        "source_mat": str(MAT.relative_to(REPO)).replace("\\", "/"),
        "matrix_npz": str(NPZ_OUT.relative_to(REPO)).replace("\\", "/"),
        "shapes": {
            "S_compartmented": [585, 645, 3],
            "S_aggregate": [585, 645],
        },
        "compartment_wids_3": COMPARTMENT_WIDS_3,
        "compartment_index_map": {
            "c": 0, "e": 1, "m": 2,
        },
        "ids": {
            "substrate_wcm_585": sub_wids,
            "reaction_wcm_645": rxn_wids,
        },
        "stats": {
            "nnz_total": nnz,
            "nnz_aggregate": nnz_agg,
            "nnz_cytosol": nnz_cyt,
            "nnz_extracellular": nnz_ext,
            "nnz_membrane": nnz_mem,
            "n_rxns_with_cyt_signed_imbalance": n_rxns_with_cyt_imbalance,
        },
        "cell_dry_mass_g": CELL_DRY_MASS_G,
        "interpretation": {
            "S": "S_compartmented[s, r, k] = signed stoichiometric coefficient "
                 "of substrate s in reaction r in compartment k. Positive = "
                 "produced; negative = consumed. dtype int16.",
            "compartments": "k=0:Cytosol, k=1:Extracellular, k=2:Membrane "
                            "(3 of Karr's 6 KB compartments; the others -- "
                            "DNA, Terminal Organelle Cytosol, Terminal "
                            "Organelle Membrane -- carry no metabolic flux).",
            "S_aggregate": "Convenience sum over compartment dim; useful for "
                           "compartment-agnostic stoichiometry queries.",
            "honest_scope": (
                "This fixture provides per-compartment per-substrate "
                "stoichiometry for the 645-reaction superset. Of those, "
                "only 504 are inside the FBA LP (336 metabolic + 124 "
                "external exchange + 42 internal exchange + 1 biomass + "
                "1 biomass-exchange). The remaining 141 reactions live "
                "outside the FBA submodel (hosted by non-metabolism "
                "processes M4-M28). Per-tick LP-derived per-substrate "
                "replenishment for NTPs/AAs requires those non-FBA "
                "processes, which are not yet wired into the chassis. "
                "This fixture is the data foundation for that work; the "
                "supply-side calibration helper "
                "`opencell.m1.compartmented.compute_lp_supply_baseline` "
                "extracts the SS per-substrate per-compartment net flux "
                "from the FBA solution as a cross-check on C.4's "
                "demand-side calibrated baseline."
            ),
        },
    }
    JSON_OUT.write_text(json.dumps(out, indent=2))
    print(f"[OK] wrote {JSON_OUT.relative_to(REPO)}")
    print(f"[OK] wrote {NPZ_OUT.relative_to(REPO)}")
    print(f"     S_compartmented shape={S.shape}  nnz={nnz}")
    print(f"     nnz_cyt={nnz_cyt}  nnz_ext={nnz_ext}  nnz_mem={nnz_mem}")


if __name__ == "__main__":
    main()
