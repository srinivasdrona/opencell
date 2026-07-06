#!/usr/bin/env python3
"""Extract exhaustive Karr per-process stoichiometry tables from flat fixtures.

This script builds ground-truth stoichiometry artifacts for the 28 canonical Karr
processes. It prefers the matrix field used by each process's evolveState
writeback when available, and reports BLOCKER records for processes with no
locatable reaction stoichiometry matrix.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat


REPO_ROOT = Path(__file__).resolve().parents[1]
TARGETS_JSON = REPO_ROOT / "scripts" / "swarm" / "class_a_targets.json"
FIXTURE_DIR = REPO_ROOT / "data" / "karr_fixtures" / "per_process"
PROCESS_SRC_DIR = (
    REPO_ROOT
    / "data"
    / "m1_sources"
    / "WholeCell"
    / "src"
    / "+edu"
    / "+stanford"
    / "+covert"
    / "+cell"
    / "+sim"
    / "+process"
)
OUT_DIR = REPO_ROOT / "data" / "karr_method_inventory" / "karr_stoichiometry"

# DNADamage/DNARepair factor reactionStoichiometryMatrix and apply the
# small-molecule factor to substrates during evolveState.
PREFERRED_FIELDS_BY_PROCESS = {
    "DNADamage": [
        "reactionSmallMoleculeStoichiometryMatrix",
        "reactionStoichiometryMatrix",
    ],
    "DNARepair": [
        "reactionSmallMoleculeStoichiometryMatrix",
        "reactionStoichiometryMatrix",
    ],
}

DEFAULT_FIELD_ORDER = [
    "reactionStoichiometryMatrix",
    "reactionSmallMoleculeStoichiometryMatrix",
    "fbaReactionStoichiometryMatrix",
]


@dataclass
class ProcessRecord:
    payload: dict[str, Any]
    blocker: bool
    n_entries: int


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=OUT_DIR,
        help=f"Output directory (default: {OUT_DIR})",
    )
    return parser.parse_args()


def _load_targets() -> list[dict[str, Any]]:
    data = json.loads(TARGETS_JSON.read_text(encoding="utf-8"))
    return list(data["processes"])


def _load_fixture(process_name: str) -> Any:
    fixture_path = FIXTURE_DIR / f"{process_name}_flat.mat"
    mat = loadmat(fixture_path, squeeze_me=True, struct_as_record=False)
    data = mat["data"]
    if not hasattr(data, "fixture"):
        raise ValueError(f"{fixture_path} missing data.fixture payload")
    return data.fixture


def _stringify_matlab_string(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray):
        if value.dtype.kind in {"U", "S"}:
            return "".join(np.asarray(value).reshape(-1).tolist())
        if value.size == 1:
            return _stringify_matlab_string(value.reshape(-1)[0])
        return str(value.tolist())
    return str(value)


def _get_substrate_wids(fx: Any) -> list[str]:
    if not hasattr(fx, "substrateWholeCellModelIDs"):
        return []
    raw = np.asarray(getattr(fx, "substrateWholeCellModelIDs"), dtype=object).reshape(-1)
    return [_stringify_matlab_string(v) for v in raw]


def _matrix_candidates(process_name: str) -> list[str]:
    fields: list[str] = []
    for field in PREFERRED_FIELDS_BY_PROCESS.get(process_name, []):
        if field not in fields:
            fields.append(field)
    for field in DEFAULT_FIELD_ORDER:
        if field not in fields:
            fields.append(field)
    return fields


def _select_matrix(process_name: str, fx: Any) -> tuple[str | None, np.ndarray | None]:
    for field in _matrix_candidates(process_name):
        if not hasattr(fx, field):
            continue
        arr = np.asarray(getattr(fx, field))
        if arr.size == 0:
            continue
        if arr.ndim not in (2, 3):
            continue
        return field, arr.astype(float, copy=False)
    return None, None


def _nonzero_row_mask(matrix: np.ndarray) -> np.ndarray:
    if matrix.ndim == 2:
        return np.any(matrix != 0, axis=1)
    if matrix.ndim == 3:
        return np.any(matrix != 0, axis=(1, 2))
    raise ValueError(f"Unsupported matrix ndim={matrix.ndim}")


def _compartment_names_from_fixture(fx: Any, n_compartments: int) -> list[str]:
    names = [f"compartment_{i + 1}" for i in range(n_compartments)]
    index_to_name: dict[int, str] = {}
    for attr in dir(fx):
        if not attr.startswith("compartmentIndexs_"):
            continue
        raw_val = getattr(fx, attr)
        arr = np.asarray(raw_val).reshape(-1)
        if arr.size != 1:
            continue
        idx = int(arr[0])
        if 1 <= idx <= n_compartments:
            index_to_name[idx - 1] = attr.replace("compartmentIndexs_", "", 1)
    for idx, name in index_to_name.items():
        names[idx] = name
    return names


def _reaction_coefficients(vector: np.ndarray) -> list[dict[str, float]]:
    nz = np.flatnonzero(vector != 0)
    return [
        {
            "reaction_index": int(i + 1),  # MATLAB-compatible 1-based index
            "coefficient": float(vector[i]),
        }
        for i in nz
    ]


def _build_entry(
    wid: str,
    vector: np.ndarray,
    compartment: str | None = None,
) -> dict[str, Any]:
    consume_total = float(np.sum(-vector[vector < 0]))
    produce_total = float(np.sum(vector[vector > 0]))
    if consume_total > 0 and produce_total > 0:
        role = "both"
    elif consume_total > 0:
        role = "consume"
    else:
        role = "produce"

    entry: dict[str, Any] = {
        "wid": wid,
        "role": role,
        "net_coefficient": float(np.sum(vector)),
        "consume_coefficient_total": consume_total,
        "produce_coefficient_total": produce_total,
        "nonzero_reaction_count": int(np.count_nonzero(vector)),
        "reaction_coefficients": _reaction_coefficients(vector),
    }
    if compartment is not None:
        entry["compartment"] = compartment
    return entry


def _build_substrate_entries_with_fixture(
    fx: Any,
    matrix: np.ndarray,
    substrate_wids: list[str],
) -> tuple[list[dict[str, Any]], int]:
    entries: list[dict[str, Any]] = []
    row_mask = _nonzero_row_mask(matrix)
    nz_rows = np.flatnonzero(row_mask)

    if matrix.ndim == 2:
        for i in nz_rows:
            entries.append(_build_entry(substrate_wids[i], matrix[i, :]))
        return entries, int(nz_rows.size)

    n_comp = matrix.shape[2]
    comp_names = _compartment_names_from_fixture(fx, n_comp)
    for i in nz_rows:
        for comp_idx in range(n_comp):
            vector = matrix[i, :, comp_idx]
            if not np.any(vector != 0):
                continue
            entries.append(
                _build_entry(
                    substrate_wids[i],
                    vector,
                    compartment=comp_names[comp_idx],
                )
            )
    return entries, int(nz_rows.size)


def _process_record(process_meta: dict[str, Any]) -> ProcessRecord:
    name = process_meta["name"]
    fixture_rel = f"data/karr_fixtures/per_process/{name}_flat.mat"
    matlab_rel = (
        f"data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/{name}.m"
    )

    fx = _load_fixture(name)
    substrate_wids = _get_substrate_wids(fx)
    matrix_field, matrix = _select_matrix(name, fx)

    if matrix_field is None or matrix is None:
        blocker_payload = {
            "process": name,
            "source": f"{fixture_rel} + {matlab_rel} inspection",
            "status": "BLOCKER",
            "reason": (
                "No non-empty reaction stoichiometry matrix field found in fixture "
                "(checked reactionStoichiometryMatrix-family fields)."
            ),
            "checked_matrix_fields": _matrix_candidates(name),
            "available_stoichiometry_fields": sorted(
                [a for a in dir(fx) if "stoichi" in a.lower() and not a.startswith("_")]
            ),
            "n_substrate_ids": len(substrate_wids),
        }
        return ProcessRecord(payload=blocker_payload, blocker=True, n_entries=0)

    n_rows = matrix.shape[0]
    if len(substrate_wids) != n_rows:
        blocker_payload = {
            "process": name,
            "source": f"{fixture_rel}:{matrix_field}",
            "status": "BLOCKER",
            "reason": (
                "Matrix row count does not match substrateWholeCellModelIDs length; "
                "cannot map rows to WIDs safely."
            ),
            "matrix_shape": list(matrix.shape),
            "n_substrate_ids": len(substrate_wids),
            "n_matrix_rows": int(n_rows),
        }
        return ProcessRecord(payload=blocker_payload, blocker=True, n_entries=0)

    entries, n_substrates_nonzero = _build_substrate_entries_with_fixture(
        fx,
        matrix,
        substrate_wids,
    )

    if matrix.ndim == 2:
        compartment_note = (
            "matrix is compartment-flat (2D substrates x reactions); compartment omitted"
        )
    else:
        compartment_note = (
            "matrix encodes explicit compartment axis (3D substrates x reactions x compartments)"
        )

    source_note = (
        f"{fixture_rel}:data.fixture.{matrix_field}; {compartment_note}; "
        f"MATLAB source: {matlab_rel}"
    )

    payload = {
        "process": name,
        "source": source_note,
        "matrix_field": matrix_field,
        "matrix_shape": list(matrix.shape),
        "substrates": entries,
        "n_substrates": int(n_substrates_nonzero),
        "n_reactions": int(matrix.shape[1]),
        "n_entries": int(len(entries)),
    }
    return ProcessRecord(payload=payload, blocker=False, n_entries=len(entries))


def _write_process_json(out_dir: Path, process: str, payload: dict[str, Any]) -> None:
    path = out_dir / f"{process}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")


def _build_readme(records: list[ProcessRecord]) -> str:
    total_entries = sum(r.n_entries for r in records if not r.blocker)
    lines: list[str] = []
    lines.append("# Karr Per-Process Stoichiometry Oracle")
    lines.append("")
    lines.append("Generated by `scripts/extract_karr_stoichiometry.py`.")
    lines.append("")
    lines.append("## Per-process Source + Counts")
    lines.append("")
    lines.append("| Process | Status | Matrix field/source | n_substrates | n_entries |")
    lines.append("|---|---|---|---:|---:|")
    for record in records:
        payload = record.payload
        if record.blocker:
            lines.append(
                f"| {payload['process']} | BLOCKER | "
                f"{payload['source']} | 0 | 0 |"
            )
            continue
        lines.append(
            f"| {payload['process']} | OK | {payload['matrix_field']} "
            f"from fixture | {payload['n_substrates']} | {payload['n_entries']} |"
        )
    lines.append("")
    lines.append(f"Total substrate entries written: **{total_entries}**")
    lines.append("")
    lines.append("## Blockers")
    lines.append("")
    blockers = [r.payload for r in records if r.blocker]
    if not blockers:
        lines.append("None.")
    else:
        for blocker in blockers:
            lines.append(f"- `{blocker['process']}`: {blocker['reason']}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = _parse_args()
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = _load_targets()
    records: list[ProcessRecord] = []
    for process_meta in targets:
        record = _process_record(process_meta)
        records.append(record)
        _write_process_json(out_dir, process_meta["name"], record.payload)

    combined = {
        "generated_by": "scripts/extract_karr_stoichiometry.py",
        "records": [r.payload for r in records],
        "n_processes": len(records),
        "n_blockers": sum(1 for r in records if r.blocker),
        "total_substrate_entries": sum(r.n_entries for r in records if not r.blocker),
    }
    (out_dir / "index.json").write_text(
        json.dumps(combined, indent=2, sort_keys=False),
        encoding="utf-8",
    )

    (out_dir / "README.md").write_text(_build_readme(records), encoding="utf-8")

    print(
        f"Wrote {len(records)} process records to {out_dir} "
        f"({combined['n_blockers']} blockers, "
        f"{combined['total_substrate_entries']} substrate entries)."
    )


if __name__ == "__main__":
    main()
