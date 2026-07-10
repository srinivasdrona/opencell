"""Gate 0 (constants) — live Karr source constants vs extracted flat fixtures.

Companion to `scripts/matlab/gate0_dump_process_constants.m`. The MATLAB dump resolves
each process's declared fixed/fitted constant surface from the live fitted simulation
and records an exact per-constant encoding. This comparator loads the extracted
per-process flat fixtures and re-encodes the same values with matching column-major
canonicalization so extraction drift cannot be frozen in as "source truth".

Exit 0 = PASS / clean SKIP; exit 1 = any finding.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

_REPO = Path(__file__).resolve().parents[1]
_SRC_CONSTANTS = _REPO / "data" / "karr_input_spec" / "_gate0_source_constants.json"
_FIXTURE_DIR = _REPO / "data" / "karr_fixtures" / "per_process"

_NUMERIC_DTYPES: dict[str, np.dtype[object]] = {
    "double": np.dtype(np.float64),
    "logical": np.dtype(np.uint8),
    "uint8": np.dtype(np.uint8),
    "uint16": np.dtype(np.uint16),
    "uint32": np.dtype(np.uint32),
    "uint64": np.dtype(np.uint64),
    "int8": np.dtype(np.int8),
    "int16": np.dtype(np.int16),
    "int32": np.dtype(np.int32),
    "int64": np.dtype(np.int64),
}


def _load_fixture(proc: str) -> object | None:
    path = _FIXTURE_DIR / f"{proc}_flat.mat"
    if not path.exists():
        return None
    return loadmat(path, squeeze_me=True, struct_as_record=False)["data"].fixture


def _unwrap_object_scalar(value: object) -> object:
    current = value
    while isinstance(current, np.ndarray) and current.dtype == object and current.size == 1:
        current = current.reshape(-1, order="F")[0]
    return current


def _shape_list(value: object) -> list[int]:
    arr = np.asarray(value)
    return [int(x) for x in arr.shape]


def _trim_trailing_ones(shape: list[int]) -> list[int]:
    out = list(shape)
    while out and out[-1] == 1:
        out.pop()
    return out


def _squeeze_singletons(shape: list[int]) -> list[int]:
    return [dim for dim in shape if dim != 1]


def _shapes_reconcile(src_size: list[int], fx_size: list[int], *, empty: bool = False) -> bool:
    if src_size == fx_size:
        return True

    a = _trim_trailing_ones(list(src_size))
    b = _trim_trailing_ones(list(fx_size))
    if a == b:
        return True

    a_pad = a + [1] * max(0, len(b) - len(a))
    b_pad = b + [1] * max(0, len(a) - len(b))
    if a_pad == b_pad:
        return True

    if _squeeze_singletons(src_size) == _squeeze_singletons(fx_size):
        return True

    if empty:
        a_arr = np.asarray(a or [1], dtype=np.int64)
        b_arr = np.asarray(b or [1], dtype=np.int64)
        if int(np.prod(a_arr)) == 0 and int(np.prod(b_arr)) == 0:
            return True

    return False


def _to_text(value: object) -> str:
    current = _unwrap_object_scalar(value)
    if isinstance(current, bytes):
        return current.decode("utf-8", errors="replace")
    if isinstance(current, str):
        return current
    if isinstance(current, np.bytes_):
        return current.tobytes().decode("utf-8", errors="replace")
    if isinstance(current, np.str_):
        return str(current)
    if isinstance(current, np.ndarray):
        if current.size == 0:
            return ""
        if current.dtype == object and current.size == 1:
            return _to_text(current.reshape(-1, order="F")[0])
        if current.dtype.kind in {"U", "S"}:
            if current.ndim == 0:
                return str(current.item())
            flat = current.reshape(-1, order="F")
            if flat.size == 1:
                return str(flat[0])
            if all(len(str(x)) == 1 for x in flat):
                return "".join(str(x) for x in flat)
    raise TypeError(f"Expected string-like value, got {type(current).__name__}")


def _decode_name_list(raw: object) -> list[str]:
    if raw is None:
        return []
    current = _unwrap_object_scalar(raw)
    if isinstance(current, (str, bytes, np.str_, np.bytes_)):
        text = _to_text(current).strip()
        return [text] if text else []
    arr = np.asarray(current, dtype=object)
    if arr.size == 0:
        return []
    names: list[str] = []
    for item in arr.reshape(-1, order="F"):
        text = _to_text(item).strip()
        if text:
            names.append(text)
    return names


def _source_numeric_values(raw: object, cls: str) -> np.ndarray:
    dtype = np.uint8 if cls == "logical" else np.float64
    return np.asarray(raw, dtype=dtype).reshape(-1)


def _coerce_numeric_array(value: object, src_class: str) -> np.ndarray:
    current = _unwrap_object_scalar(value)
    arr = np.asarray(current)
    if arr.dtype == object:
        raise TypeError(f"expected numeric array, got object dtype ({type(current).__name__})")
    if not (
        np.issubdtype(arr.dtype, np.number) or np.issubdtype(arr.dtype, np.bool_)
    ):
        raise TypeError(f"expected numeric array, got dtype={arr.dtype}")

    if src_class == "logical":
        if not np.all((arr == 0) | (arr == 1)):
            raise ValueError("logical fixture contains values outside {0,1}")
        return arr.astype(np.uint8, copy=False)

    return arr.astype(np.float64, copy=False)


def _colmajor_nonzero(arr: np.ndarray, src_class: str) -> tuple[np.ndarray, np.ndarray]:
    flat = arr.reshape(-1, order="F")
    idx = np.flatnonzero(flat)
    values = flat[idx]
    dtype = _NUMERIC_DTYPES[src_class]
    return (idx + 1).astype(np.int64), values.astype(dtype, copy=False)


def _is_empty(value: object) -> bool:
    current = _unwrap_object_scalar(value)
    if isinstance(current, np.ndarray):
        return current.size == 0
    if isinstance(current, (list, tuple)):
        return len(current) == 0
    return False


def _decode_char_value(
    value: object, expect_rows: bool
) -> tuple[str | list[str], list[int] | None]:
    current = _unwrap_object_scalar(value)
    if isinstance(current, (bytes, str, np.bytes_, np.str_)):
        return _to_text(current), None

    arr = np.asarray(current)
    if arr.dtype == object and arr.size == 1:
        return _decode_char_value(arr.reshape(-1, order="F")[0], expect_rows)
    if arr.dtype.kind not in {"U", "S"}:
        raise TypeError(f"expected char-like fixture value, got dtype={arr.dtype}")

    shape = [int(x) for x in arr.shape]
    if not expect_rows:
        flat = arr.reshape(-1, order="F")
        if all(len(str(x)) == 1 for x in flat):
            return "".join(str(x) for x in flat), shape
        if flat.size == 1:
            return str(flat[0]), shape
        raise TypeError("expected scalar/row-vector char value")

    if arr.ndim == 0:
        return [str(arr.item())], shape
    if arr.ndim == 1:
        return [str(x) for x in arr.reshape(-1, order="F")], shape
    rows = ["".join(str(x) for x in arr[i, :]) for i in range(arr.shape[0])]
    return rows, shape


def _decode_cellstr(value: object) -> tuple[list[str], list[int]]:
    current = _unwrap_object_scalar(value)
    if isinstance(current, (bytes, str, np.bytes_, np.str_)):
        return [_to_text(current)], []
    if isinstance(current, (list, tuple)):
        arr = np.asarray(current, dtype=object)
    else:
        arr = np.asarray(current)
    shape = [int(x) for x in arr.shape]
    if arr.size == 0:
        return [], shape
    flat = arr.reshape(-1, order="F")
    return [_to_text(item) for item in flat], shape


def _decode_cell_items(value: object) -> tuple[list[object], list[int]]:
    current = _unwrap_object_scalar(value)
    if isinstance(current, np.ndarray) and current.dtype == object:
        return list(current.reshape(-1, order="F")), [int(x) for x in current.shape]
    if isinstance(current, (list, tuple)):
        arr = np.asarray(current, dtype=object)
        return list(arr.reshape(-1, order="F")), [int(x) for x in arr.shape]
    return [current], []


def _compare_numeric(
    path: str, src: dict[str, object], value: object, findings: list[str]
) -> None:
    src_class = str(src["class"])
    src_size = [int(x) for x in src["size"]]
    src_idx = np.asarray(src["nz_idx"], dtype=np.int64).reshape(-1)
    src_val = _source_numeric_values(src["nz_val"], src_class)

    try:
        fx_arr = _coerce_numeric_array(value, src_class)
    except (TypeError, ValueError) as exc:
        findings.append(f"{path}: NUMERIC decode mismatch ({exc})")
        return

    fx_size = _shape_list(fx_arr)
    if not _shapes_reconcile(src_size, fx_size):
        findings.append(f"{path}: SHAPE mismatch src={src_size} fixture={fx_size}")
        return

    fx_idx, fx_val = _colmajor_nonzero(fx_arr, src_class)
    if fx_idx.shape != src_idx.shape or not np.array_equal(fx_idx, src_idx):
        only_src = np.setdiff1d(src_idx, fx_idx)
        only_fix = np.setdiff1d(fx_idx, src_idx)
        findings.append(
            f"{path}: NONZERO-INDEX mismatch "
            f"(src_nnz={src_idx.size} fix_nnz={fx_idx.size}; "
            f"idx_only_in_source={only_src[:8].tolist()} "
            f"idx_only_in_fixture={only_fix[:8].tolist()})"
        )
        return

    equal = np.array_equal(fx_val, src_val, equal_nan=True)
    if not equal:
        mismatch_mask = ~(fx_val == src_val)
        if np.issubdtype(fx_val.dtype, np.floating) or np.issubdtype(src_val.dtype, np.floating):
            mismatch_mask &= ~(np.isnan(fx_val) & np.isnan(src_val))
        bad = int(np.flatnonzero(mismatch_mask)[0])
        findings.append(
            f"{path}: VALUE mismatch at nz#{bad} (src={src_val[bad]} fixture={fx_val[bad]})"
        )


def _compare_empty(
    path: str, src: dict[str, object], value: object, findings: list[str]
) -> None:
    if not _is_empty(value):
        findings.append(f"{path}: EMPTY mismatch fixture is non-empty")
        return
    src_size = [int(x) for x in src["size"]]
    fx_size = _shape_list(value)
    if not _shapes_reconcile(src_size, fx_size, empty=True):
        findings.append(f"{path}: EMPTY-SHAPE mismatch src={src_size} fixture={fx_size}")


def _compare_char(
    path: str, src: dict[str, object], value: object, findings: list[str]
) -> None:
    src_size = [int(x) for x in src["size"]]
    expect_rows = isinstance(src["value"], list)
    try:
        fx_value, fx_size = _decode_char_value(value, expect_rows=expect_rows)
    except TypeError as exc:
        findings.append(f"{path}: CHAR decode mismatch ({exc})")
        return

    if fx_value != src["value"]:
        findings.append(f"{path}: CHAR value mismatch src={src['value']!r} fixture={fx_value!r}")
        return
    if fx_size is not None and not _shapes_reconcile(src_size, fx_size):
        findings.append(f"{path}: CHAR-SHAPE mismatch src={src_size} fixture={fx_size}")


def _compare_cellstr(
    path: str, src: dict[str, object], value: object, findings: list[str]
) -> None:
    src_size = [int(x) for x in src["size"]]
    try:
        fx_list, fx_size = _decode_cellstr(value)
    except TypeError as exc:
        findings.append(f"{path}: CELLSTR decode mismatch ({exc})")
        return

    if not _shapes_reconcile(src_size, fx_size):
        findings.append(f"{path}: CELLSTR-SHAPE mismatch src={src_size} fixture={fx_size}")
        return

    src_list = [str(x) for x in src["value"]]
    if fx_list != src_list:
        findings.append(f"{path}: CELLSTR value mismatch src={src_list!r} fixture={fx_list!r}")


def _compare_cell(
    path: str, src: dict[str, object], value: object, findings: list[str]
) -> None:
    src_size = [int(x) for x in src["size"]]
    fx_items, fx_size = _decode_cell_items(value)
    if not _shapes_reconcile(src_size, fx_size):
        findings.append(f"{path}: CELL-SHAPE mismatch src={src_size} fixture={fx_size}")
        return

    src_items = list(src["items"])
    if len(fx_items) != len(src_items):
        findings.append(f"{path}: CELL-LEN mismatch src={len(src_items)} fixture={len(fx_items)}")
        return

    for idx, (src_item, fx_item) in enumerate(zip(src_items, fx_items, strict=True), start=1):
        _compare_entry(f"{path}{{{idx}}}", src_item, fx_item, findings)


def _compare_entry(
    path: str, src: dict[str, object], value: object, findings: list[str]
) -> None:
    kind = str(src["kind"])
    if kind == "numeric":
        _compare_numeric(path, src, value, findings)
        return
    if kind == "empty":
        _compare_empty(path, src, value, findings)
        return
    if kind == "char":
        _compare_char(path, src, value, findings)
        return
    if kind == "cellstr":
        _compare_cellstr(path, src, value, findings)
        return
    if kind == "cell":
        _compare_cell(path, src, value, findings)
        return
    findings.append(f"{path}: unsupported SOURCE kind {kind!r}")


def _compare_name_set(
    proc: str,
    label: str,
    src_names: list[str],
    fx: object,
    fixture_field: str,
    findings: list[str],
) -> None:
    raw = getattr(fx, fixture_field, None)
    if raw is None:
        findings.append(f"{proc}.{fixture_field}: present in SOURCE, ABSENT in fixture")
        return

    fx_names = _decode_name_list(raw)
    only_src = sorted(set(src_names) - set(fx_names))
    only_fix = sorted(set(fx_names) - set(src_names))
    if only_src or only_fix:
        findings.append(
            f"{proc}.{fixture_field}: {label} NAME-SET mismatch "
            f"(only_in_source={only_src} only_in_fixture={only_fix})"
        )


def main() -> int:
    if not _SRC_CONSTANTS.exists():
        print(
            "GATE 0 (constants): SKIPPED — source dump absent at "
            f"{_SRC_CONSTANTS.relative_to(_REPO)}. Regenerate: gate0_dump_process_constants.m"
        )
        return 0

    src = json.loads(_SRC_CONSTANTS.read_text())
    findings: list[str] = []
    n_processes = 0
    n_constants = 0

    for proc_entry in src["processes"]:
        proc = str(proc_entry["name"])
        n_processes += 1
        fx = _load_fixture(proc)
        if fx is None:
            findings.append(f"{proc}: fixture file ABSENT at per_process/{proc}_flat.mat")
            continue

        fixed_names = [str(x) for x in proc_entry.get("fixed_names", [])]
        fitted_names = [str(x) for x in proc_entry.get("fitted_names", [])]
        _compare_name_set(proc, "FIXED", fixed_names, fx, "fixedConstantNames__", findings)
        _compare_name_set(proc, "FITTED", fitted_names, fx, "fittedConstantNames__", findings)

        all_names = list(dict.fromkeys([*fixed_names, *fitted_names]))
        constants = proc_entry.get("constants") or {}
        for name in all_names:
            n_constants += 1
            src_const = constants.get(name)
            if src_const is None:
                findings.append(f"{proc}.{name}: present in SOURCE names, ABSENT in source dump body")
                continue

            fx_value = getattr(fx, name, None)
            if fx_value is None:
                findings.append(f"{proc}.{name}: present in SOURCE, ABSENT in fixture")
                continue

            _compare_entry(f"{proc}.{name}", src_const, fx_value, findings)

    if findings:
        print(f"GATE 0 (constants): FAIL — {len(findings)} finding(s):")
        for finding in findings:
            print(f"  - {finding}")
        return 1

    print(
        f"GATE 0 (constants): PASS — {n_processes} processes, "
        f"{n_constants} constants; source == fixture, exact."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
