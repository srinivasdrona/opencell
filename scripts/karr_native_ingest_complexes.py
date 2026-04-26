"""Ingest Karr's protein-complex composition extract into a committable
JSON fixture.

Reads `data/m1_sources/karr_flat/protein_complexes.mat` (gitignored,
produced by `scripts/matlab/extract_protein_complexes.m`) and writes a
normalised, schema-versioned JSON fixture at
`data/karr_fixtures/karr_protein_complexes.json`.

The fixture is the runtime source for `opencell.m1.protein_complexes`;
no MAT access at runtime.

Run:
  cd /mnt/e/opencell && source .venv-wsl/bin/activate && \
      python scripts/karr_native_ingest_complexes.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

REPO = Path(__file__).resolve().parents[1]
MAT = REPO / "data" / "m1_sources" / "karr_flat" / "protein_complexes.mat"
OUT = REPO / "data" / "karr_fixtures" / "karr_protein_complexes.json"

SCHEMA_VERSION = "karr_protein_complexes__v1"


def _to_dict(rec):
    """scipy mat_struct -> nested Python dict/list/scalar."""
    import scipy.io.matlab as mlab

    if isinstance(rec, mlab.mat_struct):
        return {f: _to_dict(getattr(rec, f)) for f in rec._fieldnames}
    if isinstance(rec, np.ndarray):
        if rec.dtype == object:
            if rec.size == 1:
                return _to_dict(rec.flat[0])
            return [_to_dict(x) for x in rec.flat]
        if rec.size == 1:
            v = rec.item()
            return v.item() if hasattr(v, "item") else v
        return rec.tolist()
    if isinstance(rec, (np.generic,)):
        return rec.item()
    return rec


def _participant(p):
    """Normalise a participant dict from the MAT extract."""
    return {
        "molecule_wid": str(p.get("molecule_wid", "")),
        "coefficient": float(p.get("coefficient", 0.0)),
        "compartment_wid": str(p.get("compartment_wid", "")),
    }


def _participants(plist):
    if plist is None:
        return []
    if isinstance(plist, dict):
        plist = [plist]
    out = []
    for p in plist:
        if not isinstance(p, dict):
            continue
        wid = str(p.get("molecule_wid", "")).strip()
        if not wid:
            continue
        out.append(_participant(p))
    return out


def main() -> None:
    if not MAT.exists():
        raise FileNotFoundError(
            f"Run scripts/matlab/extract_protein_complexes.m first; missing {MAT}"
        )
    raw = loadmat(MAT, squeeze_me=True, struct_as_record=False)
    data = _to_dict(raw["data"])

    complexes_in = data["complexes"]
    if isinstance(complexes_in, dict):
        complexes_in = [complexes_in]

    complexes = []
    for entry in complexes_in:
        if not isinstance(entry, dict):
            continue
        wid = str(entry.get("wholeCellModelID", "")).strip()
        if not wid:
            continue
        complexes.append({
            "wid": wid,
            "name": str(entry.get("name", "")),
            "idx_1based": int(entry.get("idx", 0)),
            "num_subunits": int(entry.get("numSubunits", 0) or 0),
            "num_distinct_subunits": int(entry.get("numDistinctSubunits", 0) or 0),
            "dna_footprint": int(entry.get("dnaFootprint", 0) or 0),
            "density": float(entry.get("density", 0.0) or 0.0),
            "activation_rule": str(entry.get("activationRule", "") or ""),
            "formation_compartment_wid": str(entry.get("formation_compartment_wid", "") or ""),
            "monomers":     _participants(entry.get("monomers")),
            "subcomplexes": _participants(entry.get("subcomplexes")),
            "metabolites":  _participants(entry.get("metabolites")),
            "prosthetic":   _participants(entry.get("prosthetic")),
            "chaperones":   _participants(entry.get("chaperones")),
            "rnas":         _participants(entry.get("rnas")),
        })

    out = {
        "schema_version": SCHEMA_VERSION,
        "source_mat": str(MAT.relative_to(REPO)).replace("\\", "/"),
        "source_kb_file": data.get("x_source_file", "data/knowledgeBase.mat"),
        "matlab_release": data.get("x_matlab_release", "unknown"),
        "extract_timestamp_utc": data.get("x_extract_timestamp_utc", ""),
        "counts": {
            "n_complexes": len(complexes),
            "n_monomer_wids_482": len(data.get("monomer_wids_482", [])),
            "n_metabolite_wids_722": len(data.get("metabolite_wids_722", [])),
            "n_compartment_wids_6": len(data.get("compartment_wids_6", [])),
        },
        "compartment_wids": [str(x) for x in data.get("compartment_wids_6", [])],
        "complexes": complexes,
        "interpretation": {
            "convention": (
                "Each complex appears in its own biosynthesis as the +1 "
                "product. Reactant participants (monomers, sub-complexes, "
                "metabolites, prosthetic groups, RNAs, chaperone substrates) "
                "carry positive stoichiometric coefficients indicating how "
                "many copies are required to assemble one complex. "
                "Negative coefficients (rare) indicate net release."
            ),
            "compartments": "c=Cytosol, d=DNA, e=Extracellular, m=Membrane, tc=Terminal Organelle Cytosol, tm=Terminal Organelle Membrane",
            "monomers": "molecule_wid is a ProteinMonomer WCM ID (e.g. MG_003_MONOMER)",
            "subcomplexes": "molecule_wid is another complex WCM ID (e.g. RIBOSOME_30S inside RIBOSOME_70S)",
            "metabolites": "molecule_wid is a Metabolite WCM ID; covers metal/cofactor binding (Mg2+, ADP, ATP, etc).",
            "prosthetic": "covalently-bound prosthetic groups",
            "chaperones": "chaperone substrate participants (typically empty for our complexes)",
            "rnas": "Gene-level WCM IDs of rRNAs / tRNAs incorporated into the complex",
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"[OK] wrote {OUT.relative_to(REPO)}")
    print(f"     n_complexes = {len(complexes)}")

    # Quick spot-check.
    for target in ("DNA_GYRASE", "RNA_POLYMERASE", "RIBOSOME_30S", "RIBOSOME_50S", "RIBOSOME_70S"):
        for c in complexes:
            if c["wid"] == target:
                mons = c["monomers"]
                subs = c["subcomplexes"]
                rnas = c["rnas"]
                print(f"  {target}: monomers={len(mons)} subs={len(subs)} rnas={len(rnas)}")
                break


if __name__ == "__main__":
    main()
