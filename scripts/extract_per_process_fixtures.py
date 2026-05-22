"""Extract per-process MAT fixtures into Python-native form.

These fixtures (28 process + 16 state) under
data/m1_sources/WholeCell/src_test/+edu/+stanford/+covert/+cell/+sim/{+process,+state}/fixtures/
are MATLAB v5 .mat files holding *MCOS* (MATLAB Class Object System) serialized
instances of MATLAB classes (e.g. edu.stanford.covert.cell.sim.process.Transcription).

The actual class data lives in the file's `__function_workspace__` subsystem
blob, in MATLAB's undocumented MCOS format.  Neither scipy.io nor pymatreader
nor mat4py can decode MCOS — pymatreader explicitly warns:
    "Complex objects (like classes) are not supported."

Per the M1 brief we MUST stay Python-only (no MATLAB call-out).  We therefore
emit a *best-effort* extraction:

  * <Name>.json   — full provenance (source path, sha256, size, MCOS class
                    name, function_workspace byte count, mat-format version)
                    plus an `extraction_status` field marking
                    "unparsed_mcos_payload" so downstream tests know the .npz
                    arrays are NOT field-level oracles yet.
  * <Name>.npz    — the small MCOS pointer array (the 6-uint32 `arr` field)
                    plus any non-MCOS top-level scalar arrays we encounter.
                    Currently this is sparse; the script is written so it
                    will automatically pick up real arrays if/when a future
                    MCOS decoder is wired in.

Re-running the script is idempotent: outputs are byte-identical for a given
input (deterministic dtype/shape, no timestamps, sorted keys in JSON).

Usage:
    python scripts/extract_per_process_fixtures.py --all
    python scripts/extract_per_process_fixtures.py --name Transcription
    python scripts/extract_per_process_fixtures.py --name CellMass --kind state

To ingest the MATLAB-flattened outputs from
`scripts/matlab/extract_per_process_fixtures.m` (which DOES decode the MCOS
payloads — MATLAB itself understands the format when class definitions are
on path):
    python scripts/extract_per_process_fixtures.py --all --from-flat
    python scripts/extract_per_process_fixtures.py --name Transcription --from-flat
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import scipy.io as sio

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PROCESS = (
    REPO_ROOT
    / "data/m1_sources/WholeCell/src_test/+edu/+stanford/+covert/+cell/+sim/+process/fixtures"
)
SRC_STATE = (
    REPO_ROOT
    / "data/m1_sources/WholeCell/src_test/+edu/+stanford/+covert/+cell/+sim/+state/fixtures"
)
OUT_DIR = REPO_ROOT / "data/karr_fixtures/per_process"


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _detect_mat_version(p: Path) -> str:
    """Return 'v7.3' for HDF5-based files, 'v5' for classic MAT v5, 'unknown' otherwise."""
    with p.open("rb") as f:
        head = f.read(128)
    if head[:8] == b"\x89HDF\r\n\x1a\n":
        return "v7.3"
    # MAT v5 header is 116 ASCII bytes of description + 4 bytes + 2-byte version + 'MI'/'IM'
    if b"MATLAB 5.0 MAT-file" in head or b"MATLAB 5 MAT-file" in head:
        return "v5"
    return "unknown"


def _flatten_struct(obj, prefix: str, arrays: dict, scalars: dict) -> None:
    """Walk a scipy struct_as_record=False object recursively.

    Currently only triggers for top-level non-MCOS structs (none observed in
    the WholeCell fixtures); included so the script transparently supports a
    future MCOS-decoded path that produces real nested structs.
    """
    if hasattr(obj, "_fieldnames"):
        for fn in obj._fieldnames:
            _flatten_struct(getattr(obj, fn), f"{prefix}/{fn}" if prefix else fn, arrays, scalars)
        return
    if isinstance(obj, np.ndarray):
        if obj.dtype == object and obj.size == 1:
            _flatten_struct(obj.flat[0], prefix, arrays, scalars)
            return
        if obj.size == 1 and obj.dtype.kind in "iufb":
            scalars[prefix] = obj.flat[0].item()
            return
        # bytes/strings stored as object array
        if obj.dtype == object:
            try:
                vals = [
                    b.decode("latin1", "replace") if isinstance(b, (bytes, bytearray)) else b
                    for b in obj.flat
                ]
                if all(isinstance(v, str) for v in vals):
                    scalars[prefix] = vals if len(vals) > 1 else vals[0]
                    return
            except Exception:
                pass
        arrays[prefix] = np.ascontiguousarray(obj)
        return
    if isinstance(obj, (bytes, bytearray)):
        scalars[prefix] = obj.decode("latin1", "replace")
        return
    if isinstance(obj, (int, float, bool, str)):
        scalars[prefix] = obj
        return
    scalars[prefix] = repr(obj)


def extract_one(src: Path, out_dir: Path) -> dict:
    """Extract a single .mat fixture. Returns the manifest entry."""
    out_dir.mkdir(parents=True, exist_ok=True)
    name = src.stem
    sha = _sha256(src)
    mat_version = _detect_mat_version(src)
    entry: dict = {
        "name": name,
        "source_path": src.relative_to(REPO_ROOT).as_posix(),
        "source_sha256": sha,
        "source_size_bytes": src.stat().st_size,
        "mat_format": mat_version,
        "extraction_status": "unknown",
        "notes": [],
    }

    if mat_version == "v7.3":
        entry["extraction_status"] = "blocked_v73_hdf5"
        entry["notes"].append(
            "MAT v7.3 (HDF5) — current toolchain only attempts v5; needs h5py walker."
        )
        return entry

    try:
        d = sio.loadmat(str(src), squeeze_me=False, struct_as_record=False)
    except Exception as e:
        entry["extraction_status"] = "scipy_load_failed"
        entry["notes"].append(f"scipy.io.loadmat raised: {type(e).__name__}: {e}")
        return entry

    arrays: dict = {}
    scalars: dict = {}
    top_keys = [k for k in d if not k.startswith("__")]
    entry["top_level_keys"] = top_keys

    is_mcos = False
    mcos_class = None
    for k in top_keys:
        v = d[k]
        if isinstance(v, np.ndarray) and v.dtype.names == ("s0", "s1", "s2", "arr"):
            is_mcos = True
            try:
                mcos_class = bytes(v[0]["s2"]).decode("latin1", "replace")
                ptr = np.asarray(v[0]["arr"], dtype=np.uint32).reshape(-1)
                arrays[f"{k}/__mcos__/arr"] = ptr
                scalars[f"{k}/__mcos__/s0"] = bytes(v[0]["s0"]).decode("latin1", "replace")
                scalars[f"{k}/__mcos__/s1"] = bytes(v[0]["s1"]).decode("latin1", "replace")
                scalars[f"{k}/__mcos__/s2"] = mcos_class
            except Exception as e:
                entry["notes"].append(f"failed to read MCOS pointer: {e!r}")
        else:
            try:
                obj = v[0, 0] if v.shape == (1, 1) else (v.flat[0] if v.size == 1 else v)
                _flatten_struct(obj, k, arrays, scalars)
            except Exception as e:
                entry["notes"].append(f"flatten failed for top-key {k!r}: {e!r}")

    fws = d.get("__function_workspace__")
    if fws is not None:
        entry["function_workspace_bytes"] = int(np.asarray(fws).nbytes)
    if is_mcos:
        entry["mcos_class"] = mcos_class
        entry["extraction_status"] = "unparsed_mcos_payload"
        entry["notes"].append(
            "MCOS-serialized MATLAB class object; field-level decode requires "
            "MATLAB or a custom MCOS subsystem decoder. Source .mat sha256 + "
            "MCOS pointer preserved so a future decoder can re-extract."
        )
    else:
        entry["extraction_status"] = "extracted" if (arrays or scalars) else "empty"

    # Deterministic emission: sort keys, fixed dtype.
    npz_path = out_dir / f"{name}.npz"
    if arrays:
        np.savez(npz_path, **{k: arrays[k] for k in sorted(arrays)})
    else:
        # Always emit an .npz so re-runs are stable and downstream code can
        # blindly np.load() any fixture; use a tiny sentinel array.
        np.savez(npz_path, __empty__=np.zeros(0, dtype=np.uint8))

    json_path = out_dir / f"{name}.json"
    payload = {
        "manifest": entry,
        "scalars": {k: scalars[k] for k in sorted(scalars)},
        "array_keys": sorted(arrays),
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    # Use basenames only so output is location-independent (validation
    # re-extracts to a temp dir; hashes must match the committed payload).
    entry["out_npz"] = npz_path.name
    entry["out_json"] = json_path.name
    return entry


def extract_one_from_flat(flat_mat: Path, out_dir: Path, kind: str) -> dict:
    """Ingest a MATLAB-flattened `<Name>_flat.mat` into the per_process scheme.

    The MATLAB script `scripts/matlab/extract_per_process_fixtures.m`
    deserializes the original MCOS object inside MATLAB (which natively
    understands MCOS when the +edu class definitions are on path) and
    writes a v7 .mat with one top-level struct `data` holding the fully
    flattened object tree (numeric arrays, nested structs, sentinel
    strings for unhandled types). scipy can read that.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    if not flat_mat.exists():
        return {
            "name": flat_mat.stem.removesuffix("_flat"),
            "extraction_status": "missing_flat_input",
            "notes": [f"expected {flat_mat} from MATLAB extract step"],
        }

    name = flat_mat.stem.removesuffix("_flat")
    sha = _sha256(flat_mat)
    entry: dict = {
        "name": name,
        "source_path": flat_mat.relative_to(REPO_ROOT).as_posix()
        if flat_mat.is_relative_to(REPO_ROOT)
        else str(flat_mat),
        "source_sha256": sha,
        "source_size_bytes": flat_mat.stat().st_size,
        "mat_format": "v7_flattened_by_matlab",
        "extraction_status": "unknown",
        "notes": [],
        "kind": kind,
    }

    try:
        d = sio.loadmat(str(flat_mat), squeeze_me=False, struct_as_record=False)
    except Exception as e:
        entry["extraction_status"] = "scipy_load_failed"
        entry["notes"].append(f"scipy.io.loadmat raised: {type(e).__name__}: {e}")
        return entry

    arrays: dict = {}
    scalars: dict = {}
    if "data" not in d:
        entry["extraction_status"] = "no_data_field"
        entry["notes"].append(
            "expected top-level struct named 'data'; got: "
            + ", ".join(k for k in d if not k.startswith("__"))
        )
        return entry

    try:
        obj = d["data"]
        # MATLAB writes the struct nested in a 1x1 object array.
        obj = (
            obj[0, 0]
            if hasattr(obj, "shape") and obj.shape == (1, 1)
            else (obj.flat[0] if hasattr(obj, "size") and obj.size == 1 else obj)
        )
        _flatten_struct(obj, "", arrays, scalars)
    except Exception as e:
        entry["extraction_status"] = "flatten_failed"
        entry["notes"].append(f"flatten raised: {type(e).__name__}: {e}")
        return entry

    # Filter out object-dtype arrays from npz emission. These are pickled
    # cell/struct trees that the MATLAB cycle-cut left as sentinel strings;
    # they balloon disk usage (10-30 MB per fixture) without carrying
    # real numeric oracle data. Their keys remain in array_keys metadata
    # and their decoded structure is preserved in the *_flat.mat audit
    # trail. Numeric tensors (the actual oracle payload) keep going through.
    dropped_object: list[str] = []
    numeric_arrays: dict = {}
    for k, v in arrays.items():
        if v.dtype == object:
            dropped_object.append(k)
        else:
            numeric_arrays[k] = v

    npz_path = out_dir / f"{name}.npz"
    if numeric_arrays:
        np.savez_compressed(
            npz_path,
            **{k.replace("/", "__"): numeric_arrays[k] for k in sorted(numeric_arrays)},
        )
    else:
        np.savez_compressed(npz_path, __empty__=np.zeros(0, dtype=np.uint8))

    json_path = out_dir / f"{name}.json"
    payload = {
        "manifest": entry,
        "scalars": {k: scalars[k] for k in sorted(scalars)},
        "array_keys": sorted(arrays),
    }
    entry["extraction_status"] = "extracted_from_matlab_flat"
    entry["arrays_count"] = len(numeric_arrays)
    entry["scalars_count"] = len(scalars)
    if dropped_object:
        entry["dropped_object_dtype_count"] = len(dropped_object)
        entry["notes"].append(
            f"dropped {len(dropped_object)} object-dtype array(s) from npz "
            "(cycle-cut sentinel/cell trees); see <Name>_flat.mat for full payload."
        )
    payload["manifest"] = entry
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    entry["out_npz"] = npz_path.name
    entry["out_json"] = json_path.name
    return entry


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, bytes):
        return o.decode("latin1", "replace")
    return repr(o)


def discover_sources() -> list[tuple[str, Path]]:
    """Return [(kind, path)] for every .mat fixture under +process and +state."""
    out = []
    for kind, root in (("process", SRC_PROCESS), ("state", SRC_STATE)):
        if not root.exists():
            print(f"WARNING: source root missing: {root}", file=sys.stderr)
            continue
        for p in sorted(root.glob("*.mat")):
            out.append((kind, p))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--name", help="Single fixture name (e.g. Transcription)")
    ap.add_argument(
        "--kind",
        choices=("process", "state"),
        help="Where to look when --name is given (default: try both)",
    )
    ap.add_argument("--all", action="store_true", help="Extract every fixture")
    ap.add_argument("--out", default=str(OUT_DIR), help="Output directory")
    ap.add_argument(
        "--from-flat",
        action="store_true",
        help="Ingest MATLAB-flattened <Name>_flat.mat outputs from "
        "scripts/matlab/extract_per_process_fixtures.m instead "
        "of attempting MCOS decode in pure Python.",
    )
    ap.add_argument(
        "--flat-dir",
        default=str(OUT_DIR),
        help="Where to find <Name>_flat.mat files (default: same as --out)",
    )
    args = ap.parse_args()

    if not (args.all or args.name):
        ap.error("Pass --all or --name")

    out_dir = Path(args.out)
    sources = discover_sources()
    if args.name:
        wanted = []
        for kind, p in sources:
            if args.kind and kind != args.kind:
                continue
            if p.stem == args.name:
                wanted.append((kind, p))
        if not wanted:
            print(f"ERROR: no fixture matched name={args.name!r}", file=sys.stderr)
            return 2
        sources = wanted

    manifest = {"fixtures": []}
    rc = 0
    flat_dir = Path(args.flat_dir)
    for kind, p in sources:
        if args.from_flat:
            flat_mat = flat_dir / f"{p.stem}_flat.mat"
            entry = extract_one_from_flat(flat_mat, out_dir, kind)
        else:
            entry = extract_one(p, out_dir)
            entry["kind"] = kind
        manifest["fixtures"].append(entry)
        status = entry["extraction_status"]
        ok_statuses = ("extracted", "unparsed_mcos_payload", "extracted_from_matlab_flat")
        flag = "OK" if status in ok_statuses else "WARN"
        print(f"[{flag}] {kind:7s} {p.stem:32s} -> {status}")
        if status not in (*ok_statuses, "empty"):
            rc = 1

    if args.all:
        manifest["fixtures"].sort(key=lambda e: (e["kind"], e["name"]))
        manifest_path = out_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(
            f"\nWrote {manifest_path.relative_to(REPO_ROOT)} ({len(manifest['fixtures'])} fixtures)"
        )

    return rc


if __name__ == "__main__":
    sys.exit(main())
