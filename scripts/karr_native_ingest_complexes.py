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
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from opencell._karr_archive import load_karr_archive  # noqa: E402

OUT = REPO / "data" / "karr_fixtures" / "karr_protein_complexes.json"

SCHEMA_VERSION = "karr_protein_complexes__v1"


def _scalar_to_py(v):
    if isinstance(v, np.generic):
        return v.item()
    return v


def _participants_from_nested(complexes_sa, nested_name: str, idx: int):
    """Read complexes[idx].<nested_name> as a list of participant dicts."""
    nested = getattr(complexes_sa, nested_name, None)
    if nested is None:
        return []
    sub_sa = nested.per_parent(idx)  # _StructArray slice for this parent
    out = []
    for j in range(len(sub_sa)):
        wid = str(sub_sa.molecule_wid[j]).strip()
        if not wid:
            continue
        out.append(
            {
                "molecule_wid": wid,
                "coefficient": float(sub_sa.coefficient[j]),
                "compartment_wid": str(sub_sa.compartment_wid[j]),
            }
        )
    return out


def main() -> None:
    arc = load_karr_archive()
    pc = arc["protein_complexes"]
    complexes_sa = pc.complexes  # _StructArray length 201

    complexes = []
    n = len(complexes_sa)
    for i in range(n):
        wid = str(complexes_sa.wholeCellModelID[i]).strip()
        if not wid:
            continue
        complexes.append(
            {
                "wid": wid,
                "name": str(complexes_sa.name[i]),
                "idx_1based": int(_scalar_to_py(complexes_sa.idx[i]) or 0),
                "num_subunits": int(_scalar_to_py(complexes_sa.numSubunits[i]) or 0),
                "num_distinct_subunits": int(
                    _scalar_to_py(complexes_sa.numDistinctSubunits[i]) or 0
                ),
                "dna_footprint": int(_scalar_to_py(complexes_sa.dnaFootprint[i]) or 0),
                "density": float(_scalar_to_py(complexes_sa.density[i]) or 0.0),
                "activation_rule": str(complexes_sa.activationRule[i] or "")
                if str(complexes_sa.activationRule[i] or "") != "[]"
                else "",
                "formation_compartment_wid": (
                    str(complexes_sa.formation_compartment_wid[i] or "")
                    if str(complexes_sa.formation_compartment_wid[i] or "") != "[]"
                    else ""
                ),
                "monomers": _participants_from_nested(complexes_sa, "monomers", i),
                "subcomplexes": _participants_from_nested(complexes_sa, "subcomplexes", i),
                "metabolites": _participants_from_nested(complexes_sa, "metabolites", i),
                "prosthetic": _participants_from_nested(complexes_sa, "prosthetic", i),
                "chaperones": _participants_from_nested(complexes_sa, "chaperones", i),
                "rnas": _participants_from_nested(complexes_sa, "rnas", i),
            }
        )

    out = {
        "schema_version": SCHEMA_VERSION,
        "source_archive": "data/karr_archive/",
        "source_archive_files": ["protein_complexes"],
        "source_kb_file": str(getattr(pc, "x_source_file", None) or "data/knowledgeBase.mat"),
        "matlab_release": str(getattr(pc, "x_matlab_release", None) or "unknown"),
        "extract_timestamp_utc": str(getattr(pc, "x_extract_timestamp_utc", None) or ""),
        "counts": {
            "n_complexes": len(complexes),
            "n_monomer_wids_482": len(pc.monomer_wids_482 or []),
            "n_metabolite_wids_722": len(pc.metabolite_wids_722 or []),
            "n_compartment_wids_6": len(pc.compartment_wids_6 or []),
        },
        "compartment_wids": [str(x) for x in (pc.compartment_wids_6 or [])],
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
