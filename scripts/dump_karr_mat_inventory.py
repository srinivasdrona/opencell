"""Full Karr .mat field inventory (catalog only, no payloads committed).

Walks every leaf field in all 8 Karr WholeCell .mat files under
data/m1_sources/karr_flat/ and emits:

  - data/karr_archive/full_inventory.json           (one dict per leaf)
  - data/karr_archive/full_inventory_summary.md     (per-file summary)

For each leaf we record kind, dtype, shape, nbytes, sha256 (ndarrays only,
skipped if > 50 MB), a small sample preview, and which ingest scripts (per
ARCHIVE_SPEC in scripts/build_karr_archive.py) consume that exact path.

This is a discovery tool: "does Karr have field X?" — never reads the full
payload of large arrays beyond what's needed for shape/dtype/sample/sha256.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from scipy.io import loadmat
from scipy.io.matlab import mat_struct

try:
    from scipy.io.matlab import MatlabFunction, MatlabOpaque
except ImportError:  # older scipy
    MatlabFunction = MatlabOpaque = ()  # type: ignore

try:
    import h5py
except ImportError:
    h5py = None

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "m1_sources" / "karr_flat"
DST = ROOT / "data" / "karr_archive"
DST.mkdir(parents=True, exist_ok=True)

OUT_JSON = DST / "full_inventory.json"
OUT_MD = DST / "full_inventory_summary.md"

SAMPLE_MAX_ELEMS = 8
SHA256_MAX_BYTES = 50 * 1024 * 1024  # 50 MB
STRUCT_ARRAY_ROW_LIMIT = 0  # walk only row 0 for schema discovery


# ---------------------------------------------------------------------------
# Load ARCHIVE_SPEC from build_karr_archive.py to derive consumed_by mapping.
# ---------------------------------------------------------------------------


def _load_archive_spec() -> dict:
    spec_path = ROOT / "scripts" / "build_karr_archive.py"
    spec_mod_spec = importlib.util.spec_from_file_location("_build_karr_archive", spec_path)
    mod = importlib.util.module_from_spec(spec_mod_spec)
    spec_mod_spec.loader.exec_module(mod)  # type: ignore
    return mod.ARCHIVE_SPEC


def _consumed_paths_for(spec_entry: dict) -> set[str]:
    """Flatten an ARCHIVE_SPEC entry into a set of dotted leaf paths (no [N])."""
    out: set[str] = set()
    for f in spec_entry.get("fields", []) or []:
        out.add(f)
    for f in spec_entry.get("scalars", []) or []:
        out.add(f)
    for sa_path, sa_def in (spec_entry.get("struct_arrays") or {}).items():
        for s in sa_def.get("scalars", []) or []:
            out.add(f"{sa_path}.{s}")
        for nested_name, nested_scalars in (sa_def.get("nested_struct_arrays") or {}).items():
            for s in nested_scalars:
                out.add(f"{sa_path}.{nested_name}.{s}")
    return out


def _build_consumed_index(archive_spec: dict) -> dict[str, dict[str, list[str]]]:
    """{ '<key>.mat' : { 'dotted.path': [consumer scripts] } }."""
    idx: dict[str, dict[str, list[str]]] = {}
    for key, entry in archive_spec.items():
        mat_name = f"{key}.mat"
        consumers = [c.strip() for c in str(entry.get("consumer", "")).split("+") if c.strip()]
        path_map: dict[str, list[str]] = {}
        for p in _consumed_paths_for(entry):
            path_map[p] = list(consumers)
        idx[mat_name] = path_map
    return idx


# ---------------------------------------------------------------------------
# Path / sample / sha helpers
# ---------------------------------------------------------------------------


def _strip_indices(path: str) -> str:
    """Remove '[N]' segments so 'a.b[0].c' -> 'a.b.c' for matching against spec."""
    out = []
    i = 0
    while i < len(path):
        if path[i] == "[":
            j = path.find("]", i)
            i = j + 1 if j != -1 else len(path)
        else:
            out.append(path[i])
            i += 1
    return "".join(out)


def _consumed_by(consumed_index_for_file: dict[str, list[str]], path: str) -> list[str]:
    if not consumed_index_for_file:
        return []
    # Drop the top-level variable name (first dotted segment) for matching.
    suffix = path.split(".", 1)[1] if "." in path else path
    suffix = _strip_indices(suffix)
    return list(consumed_index_for_file.get(suffix, []))


def _sample_preview(arr, kind: str) -> str | None:
    try:
        if kind == "ndarray":
            if arr.size == 0:
                return "[]"
            if arr.size > SAMPLE_MAX_ELEMS:
                return None
            flat = arr.flatten().tolist()
            return repr(flat)
        if kind == "string":
            s = str(arr)
            return s if len(s) <= 120 else s[:117] + "..."
        if kind == "string_array":
            n = arr.size if hasattr(arr, "size") else len(arr)
            if n > SAMPLE_MAX_ELEMS:
                return None
            return repr([str(x) for x in np.asarray(arr).flat])
    except Exception:
        return None
    return None


def _sha256_of(arr: np.ndarray) -> str | None:
    try:
        if arr.nbytes > SHA256_MAX_BYTES:
            return None
        return hashlib.sha256(arr.tobytes()).hexdigest()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Classify a value
# ---------------------------------------------------------------------------


def _classify(value) -> str:
    if value is None:
        return "empty"
    if isinstance(value, mat_struct):
        return "struct"
    if MatlabFunction and isinstance(value, MatlabFunction):
        return "function_handle"
    if MatlabOpaque and isinstance(value, MatlabOpaque):
        return "object"
    if isinstance(value, np.ndarray):
        if value.size == 0:
            return "empty"
        if value.dtype == object:
            flat0 = value.flat[0]
            if isinstance(flat0, mat_struct):
                return "struct_array" if value.size > 1 else "struct"
            if isinstance(flat0, (str, bytes, np.str_)):
                return "string_array" if value.size > 1 else "string"
            if MatlabFunction and isinstance(flat0, MatlabFunction):
                return "function_handle"
            if MatlabOpaque and isinstance(flat0, MatlabOpaque):
                return "object"
            return "object"
        # Numeric / bool / structured
        return "ndarray"
    if isinstance(value, (str, bytes, np.str_)):
        return "string"
    if isinstance(value, (int, float, bool, np.generic)):
        return "ndarray"  # treat scalar as 0-d ndarray after coercion below
    return "unknown"


def _make_leaf(source_file: str, path: str, value, consumed_index_for_file) -> dict:
    kind = _classify(value)
    rec: dict = {
        "source_file": source_file,
        "path": path,
        "kind": kind,
        "dtype": None,
        "shape": None,
        "nbytes": 0,
        "sha256": None,
        "sample": None,
        "consumed_by": _consumed_by(consumed_index_for_file, path),
    }

    if kind == "ndarray":
        arr = value if isinstance(value, np.ndarray) else np.asarray(value)
        rec["dtype"] = str(arr.dtype)
        rec["shape"] = list(arr.shape)
        rec["nbytes"] = int(arr.nbytes)
        rec["sha256"] = _sha256_of(arr)
        rec["sample"] = _sample_preview(arr, "ndarray")
    elif kind == "string":
        s = (
            value
            if isinstance(value, str)
            else (
                value.decode("utf-8", "replace")
                if isinstance(value, bytes)
                else str(np.asarray(value).flat[0])
            )
        )
        rec["dtype"] = "str"
        rec["shape"] = [len(s)]
        rec["sample"] = _sample_preview(s, "string")
    elif kind == "string_array":
        arr = np.asarray(value)
        rec["dtype"] = "object<str>"
        rec["shape"] = list(arr.shape)
        rec["sample"] = _sample_preview(arr, "string_array")
    elif kind == "struct_array":
        arr = np.atleast_1d(value)
        rec["dtype"] = "mat_struct[]"
        rec["shape"] = list(arr.shape)
        rec["length"] = int(arr.size)
    elif kind == "struct":
        rec["dtype"] = "mat_struct"
    elif kind == "empty":
        if isinstance(value, np.ndarray):
            rec["dtype"] = str(value.dtype)
            rec["shape"] = list(value.shape)
    elif kind == "function_handle" or kind == "object":
        rec["dtype"] = type(value).__name__
    else:
        rec["dtype"] = type(value).__name__

    return rec


# ---------------------------------------------------------------------------
# Walkers
# ---------------------------------------------------------------------------


def _walk_struct(
    value, path: str, source_file: str, consumed_idx, leaves: list, errors: list
) -> None:
    """Recursively walk a mat_struct, emitting a leaf for every field."""
    try:
        for name in value._fieldnames:
            child_path = f"{path}.{name}"
            try:
                child = getattr(value, name)
            except Exception as e:
                errors.append(f"{source_file}:{child_path}: getattr failed: {e!r}")
                continue
            _walk_value(child, child_path, source_file, consumed_idx, leaves, errors)
    except Exception as e:
        errors.append(f"{source_file}:{path}: struct walk failed: {e!r}\n{traceback.format_exc()}")


def _walk_value(
    value, path: str, source_file: str, consumed_idx, leaves: list, errors: list
) -> None:
    """Emit a leaf and, if struct/struct_array, recurse into row-0 schema."""
    try:
        leaf = _make_leaf(source_file, path, value, consumed_idx)
    except Exception as e:
        errors.append(f"{source_file}:{path}: classify failed: {e!r}")
        leaves.append(
            {
                "source_file": source_file,
                "path": path,
                "kind": "unknown",
                "dtype": None,
                "shape": None,
                "nbytes": 0,
                "sha256": None,
                "sample": None,
                "consumed_by": [],
                "error": repr(e),
            }
        )
        return

    leaves.append(leaf)

    kind = leaf["kind"]
    if kind == "struct":
        _walk_struct(value, path, source_file, consumed_idx, leaves, errors)
    elif kind == "struct_array":
        try:
            arr = np.atleast_1d(value)
            row0 = arr.flat[0]
            if isinstance(row0, mat_struct):
                _walk_struct(row0, f"{path}[0]", source_file, consumed_idx, leaves, errors)
        except Exception as e:
            errors.append(f"{source_file}:{path}: struct_array row-0 walk failed: {e!r}")


# ---------------------------------------------------------------------------
# v7.0 .mat (scipy.io.loadmat) walker
# ---------------------------------------------------------------------------


def walk_mat_v7(path: Path, consumed_idx, errors: list) -> list[dict]:
    leaves: list[dict] = []
    md = loadmat(str(path), struct_as_record=False, squeeze_me=True)
    for var_name, value in md.items():
        if var_name.startswith("__"):
            continue
        try:
            _walk_value(value, var_name, path.name, consumed_idx, leaves, errors)
        except Exception as e:
            errors.append(
                f"{path.name}:{var_name}: top-level walk failed: {e!r}\n{traceback.format_exc()}"
            )
    return leaves


# ---------------------------------------------------------------------------
# v7.3 .mat (HDF5) walker
# ---------------------------------------------------------------------------


def walk_mat_v73(path: Path, consumed_idx, errors: list) -> list[dict]:
    leaves: list[dict] = []
    if h5py is None:
        errors.append(f"{path.name}: h5py not installed; skipping HDF5 walk")
        return leaves

    with h5py.File(str(path), "r") as f:

        def visit(name, obj) -> None:
            try:
                if isinstance(obj, h5py.Dataset):
                    dotted = name.replace("/", ".")
                    rec = {
                        "source_file": path.name,
                        "path": dotted,
                        "kind": "ndarray",
                        "dtype": str(obj.dtype),
                        "shape": list(obj.shape),
                        "nbytes": int(obj.size * obj.dtype.itemsize) if obj.dtype.itemsize else 0,
                        "sha256": None,
                        "sample": None,
                        "consumed_by": _consumed_by(consumed_idx, dotted),
                    }
                    # sha256 + sample only for small datasets
                    if rec["nbytes"] and rec["nbytes"] <= SHA256_MAX_BYTES:
                        try:
                            arr = obj[()]
                            if isinstance(arr, np.ndarray):
                                rec["sha256"] = hashlib.sha256(arr.tobytes()).hexdigest()
                                if arr.size <= SAMPLE_MAX_ELEMS:
                                    rec["sample"] = repr(arr.flatten().tolist())
                        except Exception as e:
                            errors.append(f"{path.name}:{dotted}: read for sha failed: {e!r}")
                    leaves.append(rec)
            except Exception as e:
                errors.append(f"{path.name}:{name}: visit failed: {e!r}")

        f.visititems(visit)
    return leaves


# ---------------------------------------------------------------------------
# Summary writer
# ---------------------------------------------------------------------------


def write_summary(all_leaves: list[dict], errors: list[str]) -> None:
    by_file: dict[str, list[dict]] = {}
    for L in all_leaves:
        by_file.setdefault(L["source_file"], []).append(L)

    lines: list[str] = []
    lines.append("# Karr .mat Full Inventory Summary")
    lines.append("")
    lines.append(f"Generated: {datetime.now(UTC).isoformat()}")
    lines.append("Source dir: `data/m1_sources/karr_flat/`")
    lines.append(f"Total leaves: **{len(all_leaves)}** across **{len(by_file)}** files")
    lines.append("")
    total_consumed = sum(1 for L in all_leaves if L["consumed_by"])
    lines.append(f"Consumed by ingest scripts: **{total_consumed}** / {len(all_leaves)}")
    lines.append("")

    for fname in sorted(by_file):
        leaves = by_file[fname]
        kinds: dict[str, int] = {}
        total_bytes = 0
        for L in leaves:
            kinds[L["kind"]] = kinds.get(L["kind"], 0) + 1
            total_bytes += L.get("nbytes") or 0
        consumed_here = sum(1 for L in leaves if L["consumed_by"])
        lines.append(f"## `{fname}`")
        lines.append("")
        lines.append(f"- Leaves: **{len(leaves)}**  (consumed: {consumed_here})")
        lines.append(f"- Total ndarray bytes: **{total_bytes:,}**")
        lines.append("- Kinds: " + ", ".join(f"`{k}`={v}" for k, v in sorted(kinds.items())))
        lines.append("")
        top = sorted(leaves, key=lambda L: L.get("nbytes") or 0, reverse=True)[:20]
        lines.append("### Top-20 largest leaves")
        lines.append("")
        lines.append("| nbytes | dtype | shape | path |")
        lines.append("|---:|---|---|---|")
        for L in top:
            if not L.get("nbytes"):
                continue
            shape = L.get("shape")
            lines.append(f"| {L['nbytes']:,} | {L.get('dtype')} | {shape} | `{L['path']}` |")
        lines.append("")

    if errors:
        lines.append("## Errors / warnings")
        lines.append("")
        for e in errors[:200]:
            lines.append(f"- {e}")
        if len(errors) > 200:
            lines.append(f"- ... and {len(errors) - 200} more")
        lines.append("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    if not SRC.exists():
        print(f"ERROR: source dir not found: {SRC}", file=sys.stderr)
        return 2

    archive_spec = _load_archive_spec()
    consumed_index = _build_consumed_index(archive_spec)

    mat_files = sorted(SRC.glob("*.mat"))
    print(f"Found {len(mat_files)} .mat files in {SRC}", file=sys.stderr)

    all_leaves: list[dict] = []
    errors: list[str] = []

    for mp in mat_files:
        idx_for_file = consumed_index.get(mp.name, {})
        is_v73 = (mp.name == "metabolism_dynamics.mat") or _is_hdf5(mp)
        print(f"  walking {mp.name}  ({'v7.3/HDF5' if is_v73 else 'v7.0'})", file=sys.stderr)
        try:
            if is_v73:
                leaves = walk_mat_v73(mp, idx_for_file, errors)
            else:
                leaves = walk_mat_v7(mp, idx_for_file, errors)
            all_leaves.extend(leaves)
            print(f"    -> {len(leaves)} leaves", file=sys.stderr)
        except Exception as e:
            errors.append(f"{mp.name}: file-level failure: {e!r}\n{traceback.format_exc()}")
            print(f"    !! {e!r}", file=sys.stderr)

    OUT_JSON.write_text(json.dumps(all_leaves, indent=2, default=str), encoding="utf-8")
    write_summary(all_leaves, errors)

    # ---- stdout validation ----
    print()
    print(f"Total leaves: {len(all_leaves)}")
    counts: dict[str, int] = {}
    for L in all_leaves:
        counts[L["kind"]] = counts.get(L["kind"], 0) + 1
    print("Counts by kind:")
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {k:>16}: {v}")
    print()
    print(f"Output: {OUT_JSON}  ({OUT_JSON.stat().st_size:,} bytes)")
    print(f"Output: {OUT_MD}  ({OUT_MD.stat().st_size:,} bytes)")
    print()
    print("Top-5 largest leaves:")
    top = sorted(all_leaves, key=lambda L: L.get("nbytes") or 0, reverse=True)[:5]
    for L in top:
        print(f"  {L.get('nbytes'):>12,}  {L.get('dtype'):<20}  {L['source_file']}::{L['path']}")
    if errors:
        print(f"\n{len(errors)} non-fatal errors/warnings (see summary md tail)", file=sys.stderr)
    return 0


def _is_hdf5(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            sig = f.read(8)
        return sig.startswith(b"\x89HDF\r\n\x1a\n")
    except Exception:
        return False


if __name__ == "__main__":
    sys.exit(main())
