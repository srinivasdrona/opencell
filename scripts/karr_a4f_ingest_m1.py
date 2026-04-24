"""Ingest M1 central-carbon subnetwork from sourced upstream data.

Sources (no synthesis):
  - data/m1_sources/iPS189.xml             : Suthers 2009 SBML (PLoS supp s005)
  - data/m1_sources/WholeCellKB/.../data.xlsx: Karr WholeCellKB (Reactions sheet)
  - data/karr_fixtures/parameters.json     : Karr WholeCell parameters (A4F)

Output: data/karr_fixtures/iPS189_m1.json containing the central carbon
subnetwork (stoichiometry, reversibility, Karr-sourced flux bounds where
available, AK kinetics from WholeCellKB) with full provenance per value.

Subnetwork selection is *automatic*: any iPS189 reaction whose entire
species set is contained in a curated metabolite scope (glycolysis +
fermentation + adenylate + cofactors). The scope itself is a structural
choice, not a parameter value.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import libsbml
import openpyxl


REPO = Path(r"E:\opencell")
SBML_PATH = REPO / "data" / "m1_sources" / "iPS189.xml"
WCKB_XLSX = REPO / "data" / "m1_sources" / "WholeCellKB" / "public" / "fixtures" / "data.xlsx"
KARR_PARAMS = REPO / "data" / "karr_fixtures" / "parameters.json"
OUT_PATH = REPO / "data" / "karr_fixtures" / "iPS189_m1.json"

# Metabolite scope for central carbon + fermentation + adenylate + cofactors.
# This is a structural decision (which subgraph to include), not a
# parameter value. Selection is by substring on iPS189 species WIDs.
SCOPE_KEYS = (
    # glycolysis intermediates
    "g6p", "f6p", "fdp", "dhap", "g3p", "13dpg", "3pg", "2pg", "pep", "pyr", "glc",
    # fermentation
    "lac", "ac_", "accoa", "actp", "coa",
    # adenylate
    "atp", "adp", "amp",
    # cofactors / inorganics
    "nad", "nadh", "nadp", "nadph", "pi_", "ppi", "h2o", "h_",
)

# WholeCellKB Reactions sheet column mapping (verified by
# scripts/m1_extract_wckb.py).
WCKB_COL_WID = 0
WCKB_COL_NAME = 1
WCKB_COL_KEQ = 23
WCKB_COL_FWD = 26


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def select_subnetwork(model):
    """Pick reactions whose species are all in SCOPE_KEYS-matching set."""
    species_in_scope = set()
    for i in range(model.getNumSpecies()):
        s = model.getSpecies(i)
        sid_lc = s.getId().lower()
        if any(k in sid_lc for k in SCOPE_KEYS):
            species_in_scope.add(s.getId())

    out = []
    for i in range(model.getNumReactions()):
        rx = model.getReaction(i)
        all_species = set()
        for j in range(rx.getNumReactants()):
            all_species.add(rx.getReactant(j).getSpecies())
        for j in range(rx.getNumProducts()):
            all_species.add(rx.getProduct(j).getSpecies())
        if all_species and all_species.issubset(species_in_scope):
            out.append(rx)
    return species_in_scope, out


def reaction_dict(rx):
    reactants = [
        {"species": rx.getReactant(j).getSpecies(),
         "stoichiometry": rx.getReactant(j).getStoichiometry()}
        for j in range(rx.getNumReactants())
    ]
    products = [
        {"species": rx.getProduct(j).getSpecies(),
         "stoichiometry": rx.getProduct(j).getStoichiometry()}
        for j in range(rx.getNumProducts())
    ]
    return {
        "id": rx.getId(),
        "name": rx.getName() or "",
        "reversible": bool(rx.getReversible()),
        "reactants": reactants,
        "products": products,
    }


def load_wckb_kinetics(xlsx_path: Path):
    """Return {reaction_name_lc: {Keq, fwd_rate}} from WholeCellKB."""
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb["Reactions"]
    out = {}
    for ri, row in enumerate(ws.iter_rows(values_only=True)):
        if ri < 2:
            continue
        wid = row[WCKB_COL_WID]
        if not wid:
            continue
        keq = row[WCKB_COL_KEQ]
        fwd = row[WCKB_COL_FWD]
        if keq in (None, "") and fwd in (None, ""):
            continue
        out[wid.lower()] = {
            "wckb_wid": wid,
            "wckb_name": row[WCKB_COL_NAME],
            "Keq": keq if keq not in (None, "") else None,
            "forward_rate": str(fwd) if fwd not in (None, "") else None,
        }
    return out


def attach_kinetics(reactions, wckb_kin):
    """Attach Karr WholeCellKB kinetics by fuzzy reaction-name match."""
    # iPS189 ids look like 'R_PFK', 'R_ADK1'. WCKB ids look like 'PfkA', 'Adk1'.
    # Match strategy: strip 'R_' prefix from iPS189, lowercase, look for any
    # WCKB id whose lowercase representation contains it (or vice versa).
    for rx in reactions:
        rid = rx["id"]
        stem = rid[2:].lower() if rid.startswith("R_") else rid.lower()
        match = None
        if stem in wckb_kin:
            match = wckb_kin[stem]
        else:
            for k, v in wckb_kin.items():
                if stem == k or stem.startswith(k) or k.startswith(stem):
                    match = v
                    break
        rx["wckb_kinetics"] = match
    return reactions


def main():
    assert SBML_PATH.exists(), SBML_PATH
    assert WCKB_XLSX.exists(), WCKB_XLSX
    assert KARR_PARAMS.exists(), KARR_PARAMS

    sbml_doc = libsbml.SBMLReader().readSBML(str(SBML_PATH))
    if sbml_doc.getNumErrors():
        raise RuntimeError(f"SBML errors: {sbml_doc.getNumErrors()}")
    model = sbml_doc.getModel()

    species_scope, rxs = select_subnetwork(model)
    rx_records = [reaction_dict(rx) for rx in rxs]

    wckb_kin = load_wckb_kinetics(WCKB_XLSX)
    rx_records = attach_kinetics(rx_records, wckb_kin)

    # Karr A4F sourced bounds (already in parameters.json)
    karr_params = json.loads(KARR_PARAMS.read_text())
    metab = karr_params["processes"]["Metabolism"]
    karr_bounds = {
        "exchangeRateUpperBound_carbon": {
            "value": metab["exchangeRateUpperBound_carbon"],
            "unit": "mmol/(gDW*h)",
            "applies_to": ["R_EX_glc_D_e_"],
            "source": "Karr 2012 parameters.json::processes.Metabolism",
        },
        "exchangeRateUpperBound_noncarbon": {
            "value": metab["exchangeRateUpperBound_noncarbon"],
            "unit": "mmol/(gDW*h)",
            "applies_to": ["R_EX_pi_e_", "R_EX_h2o_e_", "R_EX_nac_e_",
                           "R_EX_h_e_", "R_EX_coa_e_", "R_EX_acoa_e_",
                           "R_EX_datp_e_"],
            "source": "Karr 2012 parameters.json::processes.Metabolism",
        },
        "nonGrowthAssociatedMaintenance": {
            "value": metab["nonGrowthAssociatedMaintenance"],
            "unit": "mmol_ATP/(gDW*h)",
            "applies_to": ["R_ATPM"],  # NGAM enforced as lb on ATPM
            "source": "Karr 2012 parameters.json::processes.Metabolism",
            "unit_provenance": "UNVERIFIED in karr_parameters_unit_map.yaml; "
                               "follows COBRA convention",
        },
        "growthAssociatedMaintenance": {
            "value": metab["growthAssociatedMaintenance"],
            "unit": "mmol_ATP/mmol_biomass",
            "applies_to": [],  # only used when biomass reaction is added (deferred)
            "source": "Karr 2012 parameters.json::processes.Metabolism",
            "unit_provenance": "UNVERIFIED in karr_parameters_unit_map.yaml",
        },
    }

    out = {
        "schema_version": 1,
        "subnetwork_name": "M1_central_carbon_iPS189",
        "selection_rule": (
            "Auto-selected: iPS189 reactions whose species set is contained "
            "in the central-carbon + fermentation + adenylate + cofactor "
            "metabolite scope (substring match on WIDs)."
        ),
        "scope_substrings": list(SCOPE_KEYS),
        "n_species_in_scope": len(species_scope),
        "n_reactions": len(rx_records),
        "default_flux_bound_magnitude": 1000.0,
        "default_flux_bound_convention": "COBRA convention (cobrapy default 1000)",
        "default_flux_bound_unit": "mmol/(gDW*h)",
        "sources": {
            "iPS189_sbml": {
                "path": str(SBML_PATH.relative_to(REPO)),
                "sha256": _sha256(SBML_PATH),
                "size_bytes": SBML_PATH.stat().st_size,
                "citation": "Suthers PF et al. 2009 PLoS Comput Biol 5(2):e1000285. "
                            "DOI:10.1371/journal.pcbi.1000285. Supplementary file s005.",
            },
            "wholecellkb_xlsx": {
                "path": str(WCKB_XLSX.relative_to(REPO)),
                "sha256": _sha256(WCKB_XLSX),
                "size_bytes": WCKB_XLSX.stat().st_size,
                "citation": "Karr JR et al. 2012 Cell 150(2). WholeCellKB github "
                            "CovertLab/WholeCellKB. Sheet 'Reactions' Keq=col23 "
                            "forward_rate=col26.",
            },
            "karr_parameters_json": {
                "path": str(KARR_PARAMS.relative_to(REPO)),
                "sha256": _sha256(KARR_PARAMS),
                "size_bytes": KARR_PARAMS.stat().st_size,
                "citation": "Karr 2012 parameters.json (CovertLab/WholeCell), "
                            "ingested via A4F.",
            },
        },
        "karr_sourced_bounds": karr_bounds,
        "reactions": rx_records,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2))
    print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size} bytes)")
    print(f"  reactions:  {len(rx_records)}")
    print(f"  species in scope: {len(species_scope)}")
    print(f"  with WCKB kinetics: "
          f"{sum(1 for r in rx_records if r.get('wckb_kinetics'))}")


if __name__ == "__main__":
    main()
