"""Build snapshot-oracle replay fixtures from per-process flat MATLAB fixtures.

Usage:
    py -3.12 scripts/build_replay_fixtures_from_flat.py --all-chromosome
    py -3.12 scripts/build_replay_fixtures_from_flat.py --process Replication
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_FLAT_ROOT = _REPO_ROOT / "data" / "karr_fixtures" / "per_process"
_DEFAULT_OUTPUT_ROOT = _REPO_ROOT / "data" / "karr_fixtures" / "per_process_replay"

CHROMOSOME_PROCESSES = (
    "Replication",
    "ReplicationInitiation",
    "ChromosomeCondensation",
    "DnaSupercoiling",
)

_INPUT_PROCESS_NAME_BY_OUTPUT = {
    "DnaSupercoiling": "DNASupercoiling",
}

_ALIAS_TO_OUTPUT_PROCESS = {
    "DNASupercoiling": "DnaSupercoiling",
}

_PARAM_HINTS_BY_PROCESS = {
    "Replication": (
        "dnaPolymeraseElongationRate",
        "okazakiFragmentMeanLength",
    ),
    "ReplicationInitiation": (
        "kb1ATP",
        "k_Regen",
    ),
    "ChromosomeCondensation": (
        "smcSepNt",
        "smcSepProbCenter",
    ),
    "DnaSupercoiling": (
        "gyraseActivityRate",
        "topoIActivityRate",
    ),
}

_CHROMOSOME_PROXY_FIELDS_BY_PROCESS = {
    "Replication": (
        "leadingStrandIndexs",
        "laggingStrandIndexs",
        "oriCPosition",
        "terCPosition",
        "dnaAFunctionalBoxIndexs_R1234",
        "dnaAFunctionalBoxIndexs_R5",
        "dnaAFunctionalBoxStartPositions",
    ),
    "ReplicationInitiation": (
        "dnaABoxStatus_NotExist",
        "dnaABoxStatus_NotBound",
        "dnaABoxStatus_DnaAATPBound",
        "dnaABoxStatus_DnaAADPBound",
        "dnaABoxIndexs_7mer",
        "dnaABoxIndexs_8mer",
        "dnaABoxIndexs_9mer",
        "dnaABoxIndexs_R12345",
        "dnaABoxIndexs_R1234",
        "dnaABoxIndexs_R5",
        "dnaABoxStartPositions",
    ),
    "ChromosomeCondensation": (
        "smcSepNt",
        "smcSepProbCenter",
    ),
    "DnaSupercoiling": (
        "gyraseMeanDwellTime",
        "gyraseSigmaLimit",
        "topoISigmaLimit",
        "topoIVSigmaLimit",
        "gyraseDeltaLK",
        "topoIDeltaLK",
        "topoIVDeltaLK",
        "tuIndexs",
        "tuCoordinates",
    ),
}


@dataclass(frozen=True)
class BuildResult:
    process_name: str
    output_path: Path
    bytes_written: int
    param_keys: tuple[str, ...]
    chromosome_proxy_fields: tuple[str, ...]


def _normalize_process_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        return normalized
    return _ALIAS_TO_OUTPUT_PROCESS.get(normalized, normalized)


def _fixture_field_names(fixture: Any) -> tuple[str, ...]:
    fields = getattr(fixture, "_fieldnames", None)
    if not fields:
        raise ValueError("Expected fixture mat_struct with _fieldnames.")
    return tuple(str(name) for name in fields)


def _unwrap_object_scalar(value: Any) -> Any:
    current = value
    while isinstance(current, np.ndarray) and current.dtype == object and current.size == 1:
        current = current.reshape(-1)[0]
    return current


def _to_text(value: Any) -> str:
    current = _unwrap_object_scalar(value)
    if isinstance(current, bytes):
        return current.decode("utf-8", errors="replace")
    if isinstance(current, str):
        return current
    if isinstance(current, np.ndarray):
        if current.size == 0:
            return ""
        if current.dtype.kind in {"U", "S"}:
            return str(current.reshape(-1)[0])
        if current.size == 1:
            return _to_text(current.reshape(-1)[0])
    if isinstance(current, np.generic):
        return str(current.item())
    return str(current)


def _decode_name_list(raw: Any) -> tuple[str, ...]:
    arr = np.asarray(raw, dtype=object)
    names: list[str] = []
    for token in arr.reshape(-1):
        name = _to_text(token).strip()
        if not name:
            continue
        names.append(name)
    return tuple(names)


def _to_numeric_vector(raw: Any, *, field_name: str) -> np.ndarray:
    value = _unwrap_object_scalar(raw)
    arr = np.asarray(value)
    if arr.dtype == object:
        if arr.size == 0:
            raise ValueError(f"Fixture field '{field_name}' is empty.")
        pieces: list[np.ndarray] = []
        for item in arr.reshape(-1):
            item_arr = np.asarray(_unwrap_object_scalar(item))
            if item_arr.size == 0:
                continue
            if not np.issubdtype(item_arr.dtype, np.number):
                raise TypeError(f"Fixture field '{field_name}' contains non-numeric values.")
            pieces.append(item_arr.astype(np.float64).reshape(-1))
        if not pieces:
            raise ValueError(f"Fixture field '{field_name}' is empty after object unwrapping.")
        return np.concatenate(pieces)

    if arr.size == 0:
        raise ValueError(f"Fixture field '{field_name}' is empty.")
    if not np.issubdtype(arr.dtype, np.number):
        raise TypeError(f"Fixture field '{field_name}' is non-numeric (dtype={arr.dtype}).")
    return arr.astype(np.float64).reshape(-1)


def _to_python(value: Any) -> Any:
    current = _unwrap_object_scalar(value)

    if hasattr(current, "_fieldnames"):
        out: dict[str, Any] = {}
        for name in getattr(current, "_fieldnames", []) or []:
            out[str(name)] = _to_python(getattr(current, name))
        return out

    if isinstance(current, np.ndarray):
        if current.dtype == object:
            if current.size == 0:
                return []
            if current.size == 1:
                return _to_python(current.reshape(-1)[0])
            return [_to_python(item) for item in current.reshape(-1)]
        if current.dtype.kind in {"U", "S"}:
            if current.size == 1:
                return str(current.reshape(-1)[0])
            return current.astype(str)
        return np.asarray(current)

    if isinstance(current, (np.integer, np.floating, np.bool_)):
        return current.item()
    if isinstance(current, bytes):
        return current.decode("utf-8", errors="replace")
    if isinstance(current, (list, tuple)):
        return [_to_python(item) for item in current]
    return current


def _load_flat_fixture(path: Path) -> Any:
    payload = loadmat(path, squeeze_me=False, struct_as_record=False)
    if "data" not in payload:
        raise KeyError(f"Expected top-level 'data' struct in {path}.")

    data = payload["data"]
    if not isinstance(data, np.ndarray) or data.size == 0:
        raise ValueError(f"Invalid 'data' payload in {path}.")
    root = data[0, 0]

    fixture = getattr(root, "fixture", None)
    if not isinstance(fixture, np.ndarray) or fixture.size == 0:
        raise ValueError(f"Missing 'fixture' struct in {path}.")
    return fixture[0, 0]


def _extract_params(fixture: Any, *, process_name: str) -> dict[str, Any]:
    fixture_fields = set(_fixture_field_names(fixture))
    param_names: list[str] = []
    for names_field in ("fixedConstantNames__", "fittedConstantNames__"):
        if not hasattr(fixture, names_field):
            continue
        for name in _decode_name_list(getattr(fixture, names_field)):
            if name in fixture_fields and name not in param_names:
                param_names.append(name)

    for hinted_name in _PARAM_HINTS_BY_PROCESS[process_name]:
        if hinted_name in fixture_fields and hinted_name not in param_names:
            param_names.append(hinted_name)

    params = {name: _to_python(getattr(fixture, name)) for name in param_names}
    if not params:
        raise ValueError(f"No parameter fields extracted for process '{process_name}'.")
    return params


def _extract_chromosome(
    fixture: Any,
    *,
    process_name: str,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    fixture_fields = set(_fixture_field_names(fixture))
    if "chromosome" not in fixture_fields:
        raise ValueError(f"Missing required fixture field 'chromosome' for {process_name}.")

    chromosome_value = _to_python(getattr(fixture, "chromosome"))
    chromosome: dict[str, Any]
    if isinstance(chromosome_value, dict):
        chromosome = chromosome_value
    else:
        chromosome = {"handle": chromosome_value}

    proxy_fields: dict[str, Any] = {}
    for field_name in _CHROMOSOME_PROXY_FIELDS_BY_PROCESS[process_name]:
        if field_name not in fixture_fields:
            continue
        proxy_fields[field_name] = _to_python(getattr(fixture, field_name))

    if proxy_fields:
        chromosome["process_local_fields"] = proxy_fields

    if isinstance(chromosome_value, dict):
        chromosome["unpack_strategy"] = "direct_struct"
    else:
        chromosome["unpack_strategy"] = (
            "matlab_handle_fallback: scipy loadmat exposes Chromosome handle as opaque text; "
            "captured process-local chromosome-coupled fields alongside handle reference"
        )
    return chromosome, tuple(proxy_fields.keys())


def _build_metadata(
    *,
    process_name: str,
    flat_path: Path,
    fields_captured: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "source": "flat",
        "process_name": process_name,
        "oracle_kind": "snapshot_state",
        "extraction_timestamp": datetime.now(timezone.utc).isoformat(),
        "flat_path": flat_path.relative_to(_REPO_ROOT).as_posix(),
        "fields_captured": list(fields_captured),
    }


def build_process_fixture_from_flat(
    *,
    process_name: str,
    flat_root: Path,
    output_root: Path,
) -> BuildResult | None:
    input_process_name = _INPUT_PROCESS_NAME_BY_OUTPUT.get(process_name, process_name)
    flat_path = flat_root / f"{input_process_name}_flat.mat"
    if not flat_path.exists():
        return None

    fixture = _load_flat_fixture(flat_path)
    for required in ("substrates", "enzymes", "boundEnzymes", "chromosome"):
        if not hasattr(fixture, required):
            raise ValueError(f"Missing required fixture field '{required}' in {flat_path}.")

    initial_substrates = _to_numeric_vector(getattr(fixture, "substrates"), field_name="substrates")
    initial_enzymes = _to_numeric_vector(getattr(fixture, "enzymes"), field_name="enzymes")
    initial_bound_enzymes = _to_numeric_vector(
        getattr(fixture, "boundEnzymes"),
        field_name="boundEnzymes",
    )
    chromosome_payload, chromosome_proxy_fields = _extract_chromosome(
        fixture,
        process_name=process_name,
    )
    params = _extract_params(fixture, process_name=process_name)

    arrays: dict[str, np.ndarray] = {
        "initial__substrates": initial_substrates.astype(np.float64, copy=False),
        "initial__enzymes": initial_enzymes.astype(np.float64, copy=False),
        "initial__boundEnzymes": initial_bound_enzymes.astype(np.float64, copy=False),
        "initial__chromosome": np.array([chromosome_payload], dtype=object),
        "params": np.array([params], dtype=object),
    }
    metadata = _build_metadata(
        process_name=process_name,
        flat_path=flat_path,
        fields_captured=tuple(arrays.keys()),
    )
    arrays["metadata"] = np.array([metadata], dtype=object)

    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / f"{process_name}_from_flat.npz"
    np.savez_compressed(output_path, **arrays)

    return BuildResult(
        process_name=process_name,
        output_path=output_path,
        bytes_written=output_path.stat().st_size,
        param_keys=tuple(sorted(params.keys())),
        chromosome_proxy_fields=chromosome_proxy_fields,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--process",
        action="append",
        help=f"Process name to extract (repeatable). Allowed: {', '.join(CHROMOSOME_PROCESSES)}.",
    )
    parser.add_argument(
        "--all-chromosome",
        action="store_true",
        help="Build flat snapshot fixtures for all chromosome-focused processes in Track B Option B.",
    )
    parser.add_argument(
        "--flat-root",
        type=Path,
        default=_DEFAULT_FLAT_ROOT,
        help="Directory containing <Process>_flat.mat files.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=_DEFAULT_OUTPUT_ROOT,
        help="Output directory for <Process>_from_flat.npz fixtures.",
    )
    return parser.parse_args()


def _resolve_processes(args: argparse.Namespace) -> tuple[str, ...]:
    requested = [
        _normalize_process_name(name)
        for name in (args.process or [])
        if name and name.strip()
    ]
    if args.all_chromosome or not requested:
        return CHROMOSOME_PROCESSES

    unknown = sorted(set(requested) - set(CHROMOSOME_PROCESSES))
    if unknown:
        raise ValueError(
            f"Unsupported process name(s): {', '.join(unknown)}. "
            f"Allowed: {', '.join(CHROMOSOME_PROCESSES)}."
        )
    return tuple(requested)


def main() -> int:
    args = _parse_args()
    processes = _resolve_processes(args)

    rc = 0
    for process_name in processes:
        try:
            result = build_process_fixture_from_flat(
                process_name=process_name,
                flat_root=args.flat_root,
                output_root=args.output_root,
            )
        except Exception as exc:  # pragma: no cover - surfaced in CLI output
            print(f"[fail] {process_name}: {exc}")
            rc = 1
            continue

        if result is None:
            continue

        print(
            f"[ok] {result.process_name}: output={result.output_path}, bytes={result.bytes_written}, "
            f"n_params={len(result.param_keys)}, chromosome_proxy_fields={list(result.chromosome_proxy_fields)}"
        )

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
