"""Karr archive loader: replaces direct .mat reads with a Python-native API.

Usage:
    from opencell._karr_archive import load_karr_archive
    arc = load_karr_archive()
    # mat-style attribute access:
    arc["sim_fitted_targeted"].metabolism.fbaObjective   # ndarray
    arc["proteins_targeted"].matureIndexs                 # ndarray
    arc["knowledgeBase_targeted"].knowledgeBase.genes.wholeCellModelID  # list[str]

Each "<file>" key returns a `_Namespace` whose attribute access walks the
dotted path used in the original .mat (e.g., the m2 ingest pattern
``sim["data"].processes.Process_Transcription.fittedConstants.transcriptionUnitBindingProbabilities``
becomes ``arc["sim_fitted_targeted"].processes.Process_Transcription.fittedConstants.transcriptionUnitBindingProbabilities``).

For struct arrays (e.g. KB.genes is an array of 525 gene structs in MATLAB),
the archive stores parallel columns: ``arc["knowledgeBase_targeted"].knowledgeBase.genes``
returns a ``_StructArray`` whose ``.wholeCellModelID``, ``.symbol``, ``.expression``
etc. are vectors aligned by row. Iteration yields per-row dict-like views so
existing code patterns ``for g in genes: g.wholeCellModelID`` still work.

The archive is built by ``scripts/build_karr_archive.py`` from the raw .mat
files. After that one-time build, ``load_karr_archive()`` runs anywhere with
zero MATLAB and zero .mat dependency.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_NPZ = ROOT / "data" / "karr_archive" / "karr_archive.npz"
DEFAULT_STRINGS = ROOT / "data" / "karr_archive" / "karr_archive_strings.json"
DEFAULT_MANIFEST = ROOT / "data" / "karr_archive" / "karr_archive_manifest.json"


class _StructArrayRow:
    """Per-row view of a struct array, mimicking MATLAB struct attribute access."""
    __slots__ = ("_parent", "_idx")

    def __init__(self, parent: "_StructArray", idx: int):
        self._parent = parent
        self._idx = idx

    def __getattr__(self, name: str) -> Any:
        col = self._parent._columns.get(name)
        if col is None:
            raise AttributeError(name)
        return col[self._idx]


class _StructArray:
    """A struct array stored as parallel columns. Iterates as per-row views.

    Columns can be ndarrays (shape (N,) or (N, k)) or Python lists (length N).
    Attribute access on the struct-array itself returns the column directly;
    iteration / indexing returns _StructArrayRow views.
    """

    def __init__(self, columns: dict[str, Any], length: int,
                 nested: dict[str, "_NestedStructArray"] | None = None):
        self._columns = columns
        self._length = length
        self._nested = nested or {}

    def __len__(self) -> int:
        return self._length

    def __iter__(self):
        for i in range(self._length):
            yield _StructArrayRow(self, i)

    def __getitem__(self, idx: int) -> _StructArrayRow:
        if idx < 0:
            idx += self._length
        if idx < 0 or idx >= self._length:
            raise IndexError(idx)
        return _StructArrayRow(self, idx)

    def __getattr__(self, name: str):
        if name in self._columns:
            return self._columns[name]
        if name in self._nested:
            return self._nested[name]
        raise AttributeError(name)


class _NestedStructArray:
    """Nested struct array (e.g. complex.monomers): length-N parent with
    flat sub-columns and an offsets array carving sub-rows back to parents."""

    def __init__(self, columns: dict[str, Any], offsets: np.ndarray):
        self._columns = columns
        self._offsets = offsets

    def per_parent(self, parent_idx: int) -> "_StructArray":
        """Return the sub struct-array belonging to parent row `parent_idx`."""
        lo = int(self._offsets[parent_idx])
        hi = int(self._offsets[parent_idx + 1])
        cols = {}
        for k, v in self._columns.items():
            if isinstance(v, np.ndarray):
                cols[k] = v[lo:hi]
            else:
                cols[k] = v[lo:hi]
        return _StructArray(cols, hi - lo)

    def __getattr__(self, name: str):
        if name in self._columns:
            return self._columns[name]
        raise AttributeError(name)


class _Namespace:
    """Tree node mirroring nested struct attribute access."""
    __slots__ = ("_d",)

    def __init__(self):
        self._d: dict[str, Any] = {}

    def _set(self, key: str, val: Any) -> None:
        self._d[key] = val

    def __getattr__(self, name: str):
        if name == "_d":
            raise AttributeError(name)
        try:
            return self._d[name]
        except KeyError:
            raise AttributeError(name)

    def __contains__(self, name: str) -> bool:
        return name in self._d

    def __repr__(self) -> str:
        return f"_Namespace(keys={sorted(self._d.keys())})"


def _walk_set(root: _Namespace, dotted: str, value: Any) -> None:
    parts = dotted.split("__")
    cur = root
    for p in parts[:-1]:
        if p not in cur._d:
            cur._set(p, _Namespace())
        nxt = cur._d[p]
        if not isinstance(nxt, _Namespace):
            # A leaf already exists at this path; merge by promoting
            # to a _Namespace and re-attaching the leaf under "_value".
            promoted = _Namespace()
            promoted._set("_value", nxt)
            cur._set(p, promoted)
            nxt = promoted
        cur = nxt
    cur._set(parts[-1], value)


def _build_struct_arrays(file_root: _Namespace, file_manifest: dict, npz, strings) -> None:
    """Reconstruct _StructArray objects from the flat columnar storage."""
    prefix = file_manifest.get("__prefix__")  # set by caller (basename)
    for fpath, entry in file_manifest.items():
        if fpath.startswith("__"):
            continue
        if not isinstance(entry, dict) or "columns" not in entry:
            continue  # not a struct array
        cols: dict[str, Any] = {}
        for col_name, col_entry in entry["columns"].items():
            key = f"{prefix}__{fpath.replace('.', '__')}__{col_name}"
            if col_entry["kind"] == "ndarray":
                cols[col_name] = npz[key]
            else:
                cols[col_name] = strings[key]
        nested_objs: dict[str, _NestedStructArray] = {}
        for nf_name, nf_entry in entry.get("nested", {}).items():
            n_cols: dict[str, Any] = {}
            for col_name, col_entry in nf_entry["columns"].items():
                key = f"{prefix}__{fpath.replace('.', '__')}__{nf_name}__{col_name}"
                if col_entry["kind"] == "ndarray":
                    n_cols[col_name] = npz[key]
                else:
                    n_cols[col_name] = strings[key]
            offsets = npz[nf_entry["offsets_key"]]
            nested_objs[nf_name] = _NestedStructArray(n_cols, offsets)
        sa = _StructArray(cols, entry["length"], nested_objs)
        _walk_set(file_root, fpath.replace(".", "__"), sa)


def _load_npz_lazy(path: Path):
    """Load all arrays into a plain dict (small archive, eager load is fine)."""
    with np.load(path, allow_pickle=True) as nz:
        return {k: nz[k] for k in nz.files}


@lru_cache(maxsize=1)
def load_karr_archive(npz_path: str | None = None,
                      strings_path: str | None = None,
                      manifest_path: str | None = None) -> dict[str, _Namespace]:
    """Load the Karr archive once per process; return {basename: _Namespace}."""
    npz_p = Path(npz_path) if npz_path else DEFAULT_NPZ
    strings_p = Path(strings_path) if strings_path else DEFAULT_STRINGS
    manifest_p = Path(manifest_path) if manifest_path else DEFAULT_MANIFEST
    if not npz_p.exists():
        raise FileNotFoundError(
            f"Karr archive not found at {npz_p}. "
            "Run scripts/build_karr_archive.py to generate it (requires raw .mat files)."
        )

    npz = _load_npz_lazy(npz_p)
    with open(strings_p) as f:
        strings = json.load(f)
    with open(manifest_p) as f:
        manifest = json.load(f)

    out: dict[str, _Namespace] = {}
    for basename, info in manifest["files"].items():
        root = _Namespace()
        # Plain fields: walk paths under each file.
        for fpath, entry in info["fields"].items():
            if not isinstance(entry, dict):
                continue
            if "columns" in entry:
                continue  # struct array, handled below
            kind = entry.get("kind")
            key = f"{basename}__{fpath.replace('.', '__')}"
            if kind == "ndarray":
                val: Any = npz[key]
            elif kind in ("string", "string_list", "object_list", "scalar", "repr"):
                val = strings.get(key)
            else:
                val = strings.get(key, npz.get(key))
            _walk_set(root, fpath.replace(".", "__"), val)
        # Struct arrays.
        info["fields"]["__prefix__"] = basename  # local hack for builder
        _build_struct_arrays(root, info["fields"], npz, strings)
        del info["fields"]["__prefix__"]
        out[basename] = root
    return out


def archive_path() -> Path:
    """Return the path to the canonical karr archive npz (for sha-checks)."""
    return DEFAULT_NPZ


__all__ = ["load_karr_archive", "archive_path"]
