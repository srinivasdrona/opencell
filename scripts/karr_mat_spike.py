"""A4 spike: open one Karr 2012 .mat fixture, walk its structure,
extract a single parameter into the A3 provenance store with full
provenance + meaning-recovery assessment.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import scipy.io

MAT = Path("data/karr_fixtures/MetabolicReaction.mat")


def describe(name: str, v, depth: int = 0) -> dict:
    pad = "  " * depth
    info: dict = {"path": name}
    if isinstance(v, np.ndarray):
        info["shape"] = list(v.shape)
        info["dtype"] = str(v.dtype)
        if v.dtype.names:
            info["fields"] = list(v.dtype.names)
            print(f"{pad}{name}: struct shape={v.shape} fields={v.dtype.names}")
            children = []
            squeezed = v.squeeze()
            if squeezed.ndim == 0:
                squeezed.item() if isinstance(squeezed, np.ndarray) else squeezed
                for fname in v.dtype.names:
                    sub = squeezed[fname] if isinstance(squeezed, np.void) else v[fname]
                    children.append(describe(f"{name}.{fname}", sub, depth + 1))
            info["children"] = children
        else:
            sample = None
            try:
                flat = np.asarray(v).ravel()
                if flat.size > 0 and np.issubdtype(v.dtype, np.number):
                    sample = [float(x) for x in flat[:3]]
            except Exception:
                pass
            info["sample"] = sample
            print(f"{pad}{name}: array shape={v.shape} dtype={v.dtype} sample={sample}")
    else:
        info["repr"] = repr(v)[:80]
        print(f"{pad}{name}: {type(v).__name__} {repr(v)[:60]}")
    return info


def main() -> int:
    if not MAT.exists():
        print(f"missing fixture: {MAT}", file=sys.stderr)
        return 2

    blob = MAT.read_bytes()
    sha = hashlib.sha256(blob).hexdigest()
    print(f"file: {MAT}")
    print(f"bytes: {len(blob)}")
    print(f"sha256: {sha}\n")

    raw = scipy.io.loadmat(str(MAT), squeeze_me=False, struct_as_record=True)
    keys = [k for k in raw if not k.startswith("__")]
    print(f"top-level keys: {keys}\n")

    walk = []
    for k in keys:
        walk.append(describe(k, raw[k], 0))

    # Try to find ONE numeric scalar / vector to extract.
    # MATLAB struct: top key usually 'data' or matches state name.
    # Walk recursively; pick first numeric leaf with non-empty array.
    extracted = None

    def find_leaf(prefix: str, v) -> None:
        nonlocal extracted
        if extracted is not None:
            return
        if isinstance(v, np.ndarray):
            if v.dtype == object:
                # MATLAB cell array — unwrap one level
                flat = v.ravel()
                for i, item in enumerate(flat):
                    find_leaf(f"{prefix}[{i}]", item)
                return
            if v.dtype.names:
                sq = v.squeeze()
                if isinstance(sq, np.void):
                    for fname in v.dtype.names:
                        find_leaf(f"{prefix}.{fname}", sq[fname])
                elif sq.ndim == 0:
                    for fname in v.dtype.names:
                        find_leaf(f"{prefix}.{fname}", v[fname])
                else:
                    for fname in v.dtype.names:
                        find_leaf(f"{prefix}.{fname}", v[fname])
            elif np.issubdtype(v.dtype, np.number) and v.size > 0:
                arr = np.asarray(v).ravel()
                extracted = {
                    "path": prefix,
                    "shape": list(v.shape),
                    "dtype": str(v.dtype),
                    "values_first3": [float(x) for x in arr[:3]],
                    "n_elements": int(arr.size),
                }

    for k in keys:
        find_leaf(k, raw[k])

    print("\nfirst-leaf extraction:")
    print(json.dumps(extracted, indent=2))

    # Route the extracted leaf into the A3 provenance store end-to-end.
    from opencell.provenance import ProvenanceStore

    store_path = Path("artifacts/karr_a4_provenance.jsonl")
    store_path.parent.mkdir(parents=True, exist_ok=True)
    if store_path.exists():
        store_path.unlink()
    store = ProvenanceStore(store_path)

    if extracted is not None:
        store.record_measured(
            param_name=f"karr2012.MetabolicReaction.{extracted['path']}",
            value=extracted["values_first3"][0],
            unit="UNKNOWN_unit_not_recoverable_from_mat_alone",
            source_kind="model_artifact",
            source_ref=(
                "https://github.com/CovertLab/WholeCell/blob/master/"
                "src_test/%2Bedu/%2Bstanford/%2Bcovert/%2Bcell/%2Bsim/"
                f"%2Bstate/fixtures/MetabolicReaction.mat#sha256:{sha}"
            ),
            scope={
                "organism": "Mycoplasma genitalium G37",
                "model": "Karr2012",
                "submodel": "MetabolicReaction",
                "context": "test fixture, not full simulation state",
            },
            transformation_lineage=[
                f"raw .mat key '{extracted['path']}'",
                f"shape {extracted['shape']} dtype {extracted['dtype']}",
                "took values[0] as scalar — units unrecovered from fixture alone",
            ],
            recorded_by="agent:A4_spike",
            notes=(
                "MEANING NOT RECOVERED. The fixture lacks unit metadata, "
                "field-name documentation, and biological context. Recovery "
                "requires reading the corresponding .m source in "
                "src/+edu/+stanford/+covert/+cell/+sim/+state/MetabolicReaction.m. "
                "Unit field set to UNKNOWN_unit_not_recoverable_from_mat_alone "
                "to make the gap loud."
            ),
        )
        events = store.all()
        print(f"\nA3 store now has {len(events)} event(s).")
        print(f"event_id: {events[0].event_id}")

    print("\n--- meaning-recovery assessment ---")
    print("EXTRACTED: yes — 1 numeric leaf written to A3 store.")
    print("INTERPRETED: NO — no units, no field semantics from the .mat alone.")
    print("VERDICT: A4 succeeds at mechanics, fails at semantics. Karr port")
    print("requires reading the corresponding .m source file to recover meaning.")

    out = Path("artifacts/karr_a4_walk.json")
    out.write_text(json.dumps({"sha256": sha, "walk": walk, "extracted": extracted}, indent=2))
    print(f"\nwrote walk dump: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
