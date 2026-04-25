"""Ingest scripts/matlab/extract_karr_m1_dynamics.m output into a
Python-friendly fixture for opencell.m1.calc_flux_bounds.

Reads:  data/m1_sources/karr_flat/metabolism_dynamics.mat (HDF5 v7.3)
Writes: data/karr_fixtures/karr_native_m1_dynamics.{json,npz}

Also computes the M1<->M2/M3 overlap audit and writes findings to the
JSON's `audit` block.

MATLAB indexing notes
---------------------
Per Metabolism.m line 724, substrateIndexs_fba = sub2ind([585 3], ...)
i.e. column-major linear indices (1-based) into a (585, 3) substrate
matrix.  Conversion to 0-based:
    sub0 = (linear_1based - 1) % 585
    cmp0 = (linear_1based - 1) // 585
"""
from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC_MAT = ROOT / "data" / "m1_sources" / "karr_flat" / "metabolism_dynamics.mat"
OUT_DIR = ROOT / "data" / "karr_fixtures"
JSON_OUT = OUT_DIR / "karr_native_m1_dynamics.json"
NPZ_OUT = OUT_DIR / "karr_native_m1_dynamics.npz"

M1_BASE_JSON = OUT_DIR / "karr_native_m1.json"

N_SUB = 585
N_CMP = 3


def _read_dataset(f, key):
    arr = np.array(f[key])
    return arr


def _to_0based_int(arr):
    return np.asarray(arr, dtype=np.int64).reshape(-1) - 1


def main() -> None:
    print(f"Reading {SRC_MAT}")
    with h5py.File(SRC_MAT, "r") as f:
        # H5 v7.3 transposes 2D arrays — restore column-major shape.
        substrates_585x3 = _read_dataset(f, "snapshot_substrates").T  # (585, 3)
        enzymes_104 = _read_dataset(f, "snapshot_enzymes").reshape(-1).astype(float)
        cell_dry_mass = float(_read_dataset(f, "snapshot_cell_dry_mass").item())
        step_size_sec = float(_read_dataset(f, "step_size_sec").item())

        sub_idx_fba_1based = _read_dataset(f, "substrate_indexs_fba").reshape(-1)
        sub_idx_external_1based = _read_dataset(
            f, "substrate_indexs_external_exch").reshape(-1)
        sub_idx_internal_lim_1based = _read_dataset(
            f, "substrate_indexs_internal_lim").reshape(-1)
        compartment_extracellular = int(
            _read_dataset(f, "compartment_indexs_extracellular").item()) - 1

        fba_rxn_idx_metab_conv = _to_0based_int(_read_dataset(
            f, "fba_rxn_idx_metab_conv"))
        fba_rxn_idx_external_exch = _to_0based_int(_read_dataset(
            f, "fba_rxn_idx_external_exch"))
        fba_rxn_idx_internal_exch = _to_0based_int(_read_dataset(
            f, "fba_rxn_idx_internal_exch"))
        fba_rxn_idx_internal_lim_exch = _to_0based_int(_read_dataset(
            f, "fba_rxn_idx_internal_lim_exch"))
        fba_rxn_idx_internal_unlim_exch = _to_0based_int(_read_dataset(
            f, "fba_rxn_idx_internal_unlim_exch"))
        fba_rxn_idx_biomass_production = _to_0based_int(_read_dataset(
            f, "fba_rxn_idx_biomass_production"))
        fba_rxn_idx_biomass_exchange = _to_0based_int(_read_dataset(
            f, "fba_rxn_idx_biomass_exchange"))

        bounds_dyn_no_prot = _read_dataset(f, "bounds_dynamic_no_protein").T  # (504,2)
        bounds_dyn_with_prot = _read_dataset(f, "bounds_dynamic_with_protein").T

    # Convert MATLAB column-major linear indices -> (sub_idx_0, cmp_idx_0)
    lin0 = sub_idx_fba_1based.astype(np.int64) - 1
    sub0_fba = (lin0 % N_SUB).astype(np.int64)
    cmp0_fba = (lin0 // N_SUB).astype(np.int64)
    assert sub0_fba.size == 368
    assert cmp0_fba.max() < N_CMP and cmp0_fba.min() >= 0

    sub_idx_external_0 = (sub_idx_external_1based.astype(np.int64) - 1)
    sub_idx_internal_lim_0 = (sub_idx_internal_lim_1based.astype(np.int64) - 1)
    assert sub_idx_external_0.max() < N_SUB
    assert sub_idx_internal_lim_0.max() < N_SUB

    # ---- Overlap audit -----------------------------------------------
    # Load 585 substrate WCM IDs from the existing M1 fixture
    m1_meta = json.loads(M1_BASE_JSON.read_text())
    sub_ids = m1_meta["ids"]["substrate_wcm_585"]

    # The 368 (sub_idx, cmp_idx) FBA-substrate pairs.  Build a per-substrate
    # set of compartments that ARE represented in the FBA system.
    sub_to_cmps: dict[int, set[int]] = {}
    for s, c in zip(sub0_fba.tolist(), cmp0_fba.tolist()):
        sub_to_cmps.setdefault(int(s), set()).add(int(c))

    def classify(name: str) -> dict:
        if name not in sub_ids:
            return {"name": name, "in_585": False,
                    "in_fba_substrate_space": False,
                    "compartments_in_fba": []}
        i = sub_ids.index(name)
        cmps = sorted(sub_to_cmps.get(i, set()))
        return {"name": name, "in_585": True,
                "in_fba_substrate_space": len(cmps) > 0,
                "compartments_in_fba": cmps}

    audit_species = (
        ["ATP", "CTP", "GTP", "UTP", "AA_total"]
        + ["ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY",
           "HIS", "ILE", "LEU", "LYS", "MET", "PHE", "PRO", "SER",
           "THR", "TRP", "TYR", "VAL"]
    )
    audit = [classify(n) for n in audit_species]

    # Quick console summary
    print("\n--- Overlap audit (M2/M3 written species in M1 FBA space) ---")
    for a in audit:
        flag = ""
        if not a["in_585"]:
            flag = "  <- NOT IN 585 ID SPACE"
        elif not a["in_fba_substrate_space"]:
            flag = "  <- in 585 but NOT mapped by S (M1 cannot see it)"
        print(f"  {a['name']:8s}  in_585={a['in_585']!s:5s}  "
              f"fba_cmps={a['compartments_in_fba']}{flag}")

    # ---- Save ---------------------------------------------------------
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        NPZ_OUT,
        substrates_snapshot=substrates_585x3,
        enzymes_snapshot=enzymes_104,
        substrate_idx_fba_sub0=sub0_fba,
        substrate_idx_fba_cmp0=cmp0_fba,
        substrate_idx_external_exch_0=sub_idx_external_0,
        substrate_idx_internal_lim_0=sub_idx_internal_lim_0,
        fba_rxn_idx_metab_conv=fba_rxn_idx_metab_conv,
        fba_rxn_idx_external_exch=fba_rxn_idx_external_exch,
        fba_rxn_idx_internal_exch=fba_rxn_idx_internal_exch,
        fba_rxn_idx_internal_lim_exch=fba_rxn_idx_internal_lim_exch,
        fba_rxn_idx_internal_unlim_exch=fba_rxn_idx_internal_unlim_exch,
        fba_rxn_idx_biomass_production=fba_rxn_idx_biomass_production,
        fba_rxn_idx_biomass_exchange=fba_rxn_idx_biomass_exchange,
        bounds_dynamic_no_protein=bounds_dyn_no_prot,
        bounds_dynamic_with_protein=bounds_dyn_with_prot,
    )
    JSON_OUT.write_text(json.dumps({
        "schema_version": "m1_dynamics_v1",
        "source_mat": str(SRC_MAT.relative_to(ROOT)),
        "matrix_npz": NPZ_OUT.name,
        "scalars": {
            "cell_dry_mass": cell_dry_mass,
            "step_size_sec": step_size_sec,
            "compartment_extracellular_0based": compartment_extracellular,
            "n_substrates": N_SUB,
            "n_compartments": N_CMP,
            "n_fba_reactions": 504,
            "n_fba_substrate_rows_real": int(sub0_fba.size),
            "n_external_exchange": int(sub_idx_external_0.size),
            "n_internal_limited": int(sub_idx_internal_lim_0.size),
        },
        "interpretation": {
            "substrates_snapshot": "(585, 3) snapshot counts; cols=[cytosol, extracellular, membrane]",
            "substrate_idx_fba_sub0": "(368,) substrate_id index into 585 for each FBA-substrate row",
            "substrate_idx_fba_cmp0": "(368,) compartment index into 3 for each FBA-substrate row",
            "substrate_idx_external_exch_0": "indices into 585 (substrate-only); compartment is implicitly extracellular",
            "substrate_idx_internal_lim_0": "indices into 585 (substrate-only); compartment is implicitly cytosol per MATLAB linear indexing semantics",
            "bounds_dynamic_no_protein": "(504, 2) MATLAB calcFluxBounds output with applyProteinBounds=false",
        },
        "audit": audit,
    }, indent=2, default=float))
    print(f"\nWrote {JSON_OUT}")
    print(f"Wrote {NPZ_OUT}")


if __name__ == "__main__":
    main()
