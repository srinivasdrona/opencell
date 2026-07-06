#!/usr/bin/env python3
"""Extract per-process Karr substrate stoichiometry from fixtures + MATLAB source cues.

This extractor supports:
- class=matrix: stoichiometry matrix drives substrate deltas.
- class=inline: substrate deltas are explicit arithmetic in evolveState.
- class=none: no small-molecule substrate stoichiometry in evolveState.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
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


# Default reaction-stoichiometry fields used by already-resolved processes.
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

MAX_REACTION_COEFFICIENTS_PER_SUBSTRATE = 256


@dataclass(frozen=True)
class MatrixSpec:
    field: str
    orientation: str  # "sr" for substrates x reactions, "rs" for reactions x substrates
    row_selector_attr: str | None = None
    multiplier: float = 1.0


@dataclass(frozen=True)
class InlineRule:
    consume_attrs: tuple[str, ...] = ()
    produce_attrs: tuple[str, ...] = ()
    both_attrs: tuple[str, ...] = ()
    consume_wids: tuple[str, ...] = ()
    produce_wids: tuple[str, ...] = ()
    both_wids: tuple[str, ...] = ()
    note: str = ""


@dataclass
class ProcessRecord:
    payload: dict[str, Any]
    blocker: bool
    n_entries: int


MATRIX_OVERRIDES: dict[str, tuple[MatrixSpec, ...]] = {
    "RNAProcessing": (MatrixSpec("reactantByproductMatrix", "sr"),),
    "RNADecay": (MatrixSpec("decayReactions", "rs"),),
    "ProteinFolding": (
        MatrixSpec(
            "proteinProstheticGroupMatrix",
            "rs",
            row_selector_attr="monomerComplexIndexs_folded",
            multiplier=-1.0,
        ),
    ),
    "ProteinDecay": (
        MatrixSpec("complexDecayReactions", "sr"),
        MatrixSpec("monomerDecayReactions", "sr"),
    ),
    "MacromolecularComplexation": (MatrixSpec("complexComposition", "sr", multiplier=-1.0),),
}


INLINE_RULES: dict[str, InlineRule] = {
    "ReplicationInitiation": InlineRule(
        consume_attrs=("substrateIndexs_atp", "substrateIndexs_water"),
        produce_attrs=(
            "substrateIndexs_adp",
            "substrateIndexs_phosphate",
            "substrateIndexs_hydrogen",
        ),
        note="evolveState helper paths: ATP activation/regeneration and ATP-hydrolysis on DnaA polymer dissociation",
    ),
    "Replication": InlineRule(
        consume_attrs=(
            "substrateIndexs_atp",
            "substrateIndexs_water",
            "substrateIndexs_dntp",
            "substrateIndexs_nad",
        ),
        produce_attrs=(
            "substrateIndexs_adp",
            "substrateIndexs_phosphate",
            "substrateIndexs_hydrogen",
            "substrateIndexs_diphosphate",
            "substrateIndexs_nmn",
            "substrateIndexs_amp",
        ),
    ),
    "DNASupercoiling": InlineRule(
        consume_attrs=("substrateIndexs_atp", "substrateIndexs_water"),
        produce_attrs=(
            "substrateIndexs_adp",
            "substrateIndexs_phosphate",
            "substrateIndexs_hydrogen",
        ),
    ),
    "ChromosomeCondensation": InlineRule(
        consume_attrs=("substrateIndexs_atp", "substrateIndexs_water"),
        produce_attrs=(
            "substrateIndexs_adp",
            "substrateIndexs_phosphate",
            "substrateIndexs_hydrogen",
        ),
    ),
    "ChromosomeSegregation": InlineRule(
        consume_attrs=("substrateIndexs_gtp", "substrateIndexs_water"),
        produce_attrs=(
            "substrateIndexs_gdp",
            "substrateIndexs_phosphate",
            "substrateIndexs_hydrogen",
        ),
    ),
    "Transcription": InlineRule(
        consume_attrs=("substrateIndexs_ntp", "substrateIndexs_water"),
        produce_attrs=("substrateIndexs_diphosphate", "substrateIndexs_hydrogen"),
        note="NTP consumption occurs through polymerize(...) return update; diphosphate/water/hydrogen are explicit in evolveState",
    ),
    "Translation": InlineRule(
        consume_attrs=("substrateIndexs_gtp", "substrateIndexs_water"),
        produce_attrs=(
            "substrateIndexs_gdp",
            "substrateIndexs_phosphate",
            "substrateIndexs_hydrogen",
        ),
    ),
    "ProteinProcessingI": InlineRule(
        consume_attrs=("substrateIndexs_water",),
        produce_attrs=(
            "substrateIndexs_formate",
            "substrateIndexs_hydrogen",
            "substrateIndexs_methionine",
        ),
    ),
    "ProteinProcessingII": InlineRule(
        consume_attrs=("substrateIndexs_water", "substrateIndexs_PG160"),
        produce_attrs=("substrateIndexs_SNGLYP", "substrateIndexs_hydrogen"),
    ),
    "ProteinTranslocation": InlineRule(
        consume_attrs=(
            "substrateIndexs_atp",
            "substrateIndexs_gtp",
            "substrateIndexs_water",
        ),
        produce_attrs=(
            "substrateIndexs_adp",
            "substrateIndexs_gdp",
            "substrateIndexs_phosphate",
            "substrateIndexs_hydrogen",
        ),
    ),
    "RibosomeAssembly": InlineRule(
        consume_attrs=("substrateIndexs_gtp", "substrateIndexs_water"),
        produce_attrs=(
            "substrateIndexs_gdp",
            "substrateIndexs_phosphate",
            "substrateIndexs_hydrogen",
        ),
        note="explicit fixed stoichiometry vector [-1; 1; 1; -1; 1] on [GTP, GDP, PI, H2O, H]",
    ),
    "FtsZPolymerization": InlineRule(
        consume_attrs=("substrateIndexs_water",),
        produce_attrs=("substrateIndexs_phosphate", "substrateIndexs_hydrogen"),
        both_attrs=("substrateIndexs_gtp", "substrateIndexs_gdp"),
        note="applySubstrateLimits updates GTP/GDP with both exchange and hydrolysis correction terms",
    ),
    "Cytokinesis": InlineRule(
        consume_attrs=("substrateIndexs_water",),
        produce_attrs=("substrateIndexs_phosphate", "substrateIndexs_hydrogen"),
    ),
}


MATRIX_INLINE_AUGMENT_RULES: dict[str, InlineRule] = {
    "ProteinDecay": InlineRule(
        consume_attrs=("substrateIndexs_atp", "substrateIndexs_water"),
        produce_attrs=(
            "substrateIndexs_adp",
            "substrateIndexs_phosphate",
            "substrateIndexs_hydrogen",
        ),
        note="additional ATP/H2O hydrolysis terms are explicit in evolveState helper paths",
    )
}


NONE_PROCESS_NOTES = {
    "TranscriptionalRegulation": "No process substrates are declared (substrateWholeCellModelIDs empty); evolveState updates TF/chromosome binding state only.",
    "HostInteraction": "No process substrates are declared (substrateWholeCellModelIDs empty); evolveState updates host signaling booleans only.",
    "TerminalOrganelleAssembly": "evolveState relocates terminal-organelle proteins across compartments; no small-molecule substrate stoichiometry.",
    "ProteinActivation": "evolveState toggles protein activation state between substrates/inactivatedSubstrates pools; no small-molecule substrate stoichiometry.",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=OUT_DIR,
        help=f"Output directory (default: {OUT_DIR})",
    )
    parser.add_argument(
        "--only",
        type=str,
        default="",
        help="Comma-separated process names to (re)extract. Others are preserved from existing JSON files.",
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


def _select_default_matrix(process_name: str, fx: Any) -> tuple[str | None, np.ndarray | None]:
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
            "reaction_index": int(i + 1),
            "coefficient": float(vector[i]),
        }
        for i in nz
    ]


def _role_from_vector(vector: np.ndarray) -> tuple[str, float, float]:
    consume_total = float(np.sum(-vector[vector < 0]))
    produce_total = float(np.sum(vector[vector > 0]))
    if consume_total > 0 and produce_total > 0:
        role = "both"
    elif consume_total > 0:
        role = "consume"
    else:
        role = "produce"
    return role, consume_total, produce_total


def _build_matrix_entry(
    wid: str,
    vector: np.ndarray,
    compartment: str | None = None,
) -> dict[str, Any]:
    role, consume_total, produce_total = _role_from_vector(vector)
    nz_count = int(np.count_nonzero(vector))
    entry: dict[str, Any] = {
        "wid": wid,
        "role": role,
        "net_coefficient": float(np.sum(vector)),
        "consume_coefficient_total": consume_total,
        "produce_coefficient_total": produce_total,
        "nonzero_reaction_count": nz_count,
    }
    if nz_count <= MAX_REACTION_COEFFICIENTS_PER_SUBSTRATE:
        entry["reaction_coefficients"] = _reaction_coefficients(vector)
    else:
        entry["reaction_coefficients"] = []
        entry["reaction_coefficients_omitted"] = True
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
            entries.append(_build_matrix_entry(substrate_wids[i], matrix[i, :]))
        return entries, int(nz_rows.size)

    n_comp = matrix.shape[2]
    comp_names = _compartment_names_from_fixture(fx, n_comp)
    for i in nz_rows:
        for comp_idx in range(n_comp):
            vector = matrix[i, :, comp_idx]
            if not np.any(vector != 0):
                continue
            entries.append(
                _build_matrix_entry(
                    substrate_wids[i],
                    vector,
                    compartment=comp_names[comp_idx],
                )
            )
    return entries, int(nz_rows.size)


def _build_substrate_entries_2d(
    matrix_sr: np.ndarray,
    substrate_wids: list[str],
) -> tuple[list[dict[str, Any]], int]:
    entries: list[dict[str, Any]] = []
    row_mask = np.any(matrix_sr != 0, axis=1)
    nz_rows = np.flatnonzero(row_mask)
    for i in nz_rows:
        entries.append(_build_matrix_entry(substrate_wids[i], matrix_sr[i, :]))
    return entries, int(nz_rows.size)


def _resolve_selector_indices(selector: np.ndarray, n_rows: int) -> np.ndarray:
    idx = np.asarray(selector).reshape(-1).astype(int, copy=False)
    if idx.size == 0:
        return idx
    # MATLAB fixtures are generally 1-based index arrays.
    if np.min(idx) >= 1 and np.max(idx) <= n_rows:
        idx = idx - 1
    if np.min(idx) < 0 or np.max(idx) >= n_rows:
        raise ValueError("selector indices out of bounds")
    return idx


def _build_override_matrix(process_name: str, fx: Any) -> tuple[list[str], np.ndarray] | None:
    specs = MATRIX_OVERRIDES.get(process_name)
    if not specs:
        return None

    parts: list[np.ndarray] = []
    field_names: list[str] = []

    for spec in specs:
        if not hasattr(fx, spec.field):
            continue
        arr = np.asarray(getattr(fx, spec.field))
        if arr.size == 0 or arr.ndim != 2:
            continue
        arr = arr.astype(float, copy=False)

        if spec.row_selector_attr:
            if not hasattr(fx, spec.row_selector_attr):
                continue
            selector_raw = np.asarray(getattr(fx, spec.row_selector_attr))
            idx = _resolve_selector_indices(selector_raw, arr.shape[0])
            arr = arr[idx, :]

        if spec.orientation == "sr":
            mat_sr = arr
        elif spec.orientation == "rs":
            mat_sr = arr.T
        else:
            raise ValueError(f"Unsupported orientation {spec.orientation!r}")
        mat_sr = mat_sr * float(spec.multiplier)

        parts.append(mat_sr)
        field_names.append(spec.field)

    if not parts:
        return None

    n_rows = parts[0].shape[0]
    if any(p.shape[0] != n_rows for p in parts):
        raise ValueError("override matrices have incompatible substrate row counts")

    matrix = np.concatenate(parts, axis=1)
    return field_names, matrix


def _get_indices_from_attr(fx: Any, attr: str, n_substrates: int) -> list[int]:
    if not hasattr(fx, attr):
        return []
    raw = np.asarray(getattr(fx, attr)).reshape(-1)
    out: list[int] = []
    for v in raw:
        try:
            idx1 = int(v)
        except (TypeError, ValueError):
            continue
        idx0 = idx1 - 1
        if 0 <= idx0 < n_substrates and idx0 not in out:
            out.append(idx0)
    return out


def _inline_signs_by_wid(
    fx: Any,
    substrate_wids: list[str],
    rule: InlineRule,
) -> dict[str, set[str]]:
    n_sub = len(substrate_wids)
    signs: dict[str, set[str]] = defaultdict(set)
    wid_set = set(substrate_wids)

    def add_attr(attr: str, sign: str) -> None:
        for idx0 in _get_indices_from_attr(fx, attr, n_sub):
            signs[substrate_wids[idx0]].add(sign)

    for attr in rule.consume_attrs:
        add_attr(attr, "consume")
    for attr in rule.produce_attrs:
        add_attr(attr, "produce")
    for attr in rule.both_attrs:
        add_attr(attr, "consume")
        add_attr(attr, "produce")

    for wid in rule.consume_wids:
        if wid in wid_set:
            signs[wid].add("consume")
    for wid in rule.produce_wids:
        if wid in wid_set:
            signs[wid].add("produce")
    for wid in rule.both_wids:
        if wid in wid_set:
            signs[wid].add("consume")
            signs[wid].add("produce")

    return signs


def _inline_entry(wid: str, signs: set[str]) -> dict[str, Any]:
    if "consume" in signs and "produce" in signs:
        role = "both"
        net = 0.0
    elif "consume" in signs:
        role = "consume"
        net = -1.0
    else:
        role = "produce"
        net = 1.0
    return {
        "wid": wid,
        "role": role,
        "net_coefficient": net,
        "consume_coefficient_total": float(1.0 if "consume" in signs else 0.0),
        "produce_coefficient_total": float(1.0 if "produce" in signs else 0.0),
        "nonzero_reaction_count": 0,
        "reaction_coefficients": [],
    }


def _merge_sign_roles(
    entries: list[dict[str, Any]],
    substrate_order: list[str],
    signs_by_wid: dict[str, set[str]],
) -> list[dict[str, Any]]:
    by_wid = {entry["wid"]: entry for entry in entries}

    for wid, signs in signs_by_wid.items():
        if wid not in by_wid:
            by_wid[wid] = _inline_entry(wid, signs)
            continue

        prior = by_wid[wid]
        prior_signs: set[str] = set()
        if prior.get("role") in {"consume", "both"}:
            prior_signs.add("consume")
        if prior.get("role") in {"produce", "both"}:
            prior_signs.add("produce")
        merged = prior_signs | signs

        if merged == {"consume"}:
            prior["role"] = "consume"
        elif merged == {"produce"}:
            prior["role"] = "produce"
        else:
            prior["role"] = "both"
            if abs(float(prior.get("net_coefficient", 0.0))) == 1.0:
                prior["net_coefficient"] = 0.0

    order_map = {wid: i for i, wid in enumerate(substrate_order)}
    return sorted(by_wid.values(), key=lambda e: order_map.get(e["wid"], 10**9))


def _blocker_payload(
    process_name: str,
    reason: str,
    source: str,
    substrate_wids: list[str],
    fx: Any,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "process": process_name,
        "source": source,
        "status": "BLOCKER",
        "reason": reason,
        "n_substrate_ids": len(substrate_wids),
    }
    stoich_fields = sorted(
        [a for a in dir(fx) if "stoichi" in a.lower() and not a.startswith("_")]
    )
    if stoich_fields:
        payload["available_stoichiometry_fields"] = stoich_fields
    if extra:
        payload.update(extra)
    return payload


def _matrix_record(
    process_name: str,
    fx: Any,
    substrate_wids: list[str],
    fixture_rel: str,
    matlab_rel: str,
) -> ProcessRecord | None:
    if process_name in NONE_PROCESS_NOTES:
        return None

    try:
        override = _build_override_matrix(process_name, fx)
    except ValueError as exc:
        payload = _blocker_payload(
            process_name,
            f"Invalid override matrix assembly: {exc}",
            f"{fixture_rel} + {matlab_rel}",
            substrate_wids,
            fx,
        )
        return ProcessRecord(payload=payload, blocker=True, n_entries=0)

    if override is not None:
        field_names, matrix = override
        if matrix.shape[0] != len(substrate_wids):
            payload = _blocker_payload(
                process_name,
                "Override matrix row count does not match substrate IDs length.",
                f"{fixture_rel}:{'+'.join(field_names)}",
                substrate_wids,
                fx,
                extra={
                    "matrix_shape": list(matrix.shape),
                    "n_matrix_rows": int(matrix.shape[0]),
                },
            )
            return ProcessRecord(payload=payload, blocker=True, n_entries=0)

        entries, n_substrates_nonzero = _build_substrate_entries_2d(matrix, substrate_wids)
        source_note = (
            f"{fixture_rel}:data.fixture.{'+'.join(field_names)}; "
            f"MATLAB source: {matlab_rel}"
        )
        payload = {
            "process": process_name,
            "class": "matrix",
            "source": source_note,
            "matrix_field": " + ".join(field_names),
            "matrix_shape": list(matrix.shape),
            "substrates": entries,
            "n_substrates": int(n_substrates_nonzero),
            "n_reactions": int(matrix.shape[1]),
            "n_entries": int(len(entries)),
        }
        return ProcessRecord(payload=payload, blocker=False, n_entries=len(entries))

    matrix_field, matrix = _select_default_matrix(process_name, fx)
    if matrix_field is None or matrix is None:
        return None

    n_rows = matrix.shape[0]
    if len(substrate_wids) != n_rows:
        payload = _blocker_payload(
            process_name,
            "Default matrix row count does not match substrate IDs length.",
            f"{fixture_rel}:{matrix_field}",
            substrate_wids,
            fx,
            extra={
                "matrix_shape": list(matrix.shape),
                "n_matrix_rows": int(n_rows),
            },
        )
        return ProcessRecord(payload=payload, blocker=True, n_entries=0)

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
        "process": process_name,
        "class": "matrix",
        "source": source_note,
        "matrix_field": matrix_field,
        "matrix_shape": list(matrix.shape),
        "substrates": entries,
        "n_substrates": int(n_substrates_nonzero),
        "n_reactions": int(matrix.shape[1]),
        "n_entries": int(len(entries)),
    }
    return ProcessRecord(payload=payload, blocker=False, n_entries=len(entries))


def _inline_record(
    process_name: str,
    fx: Any,
    substrate_wids: list[str],
    fixture_rel: str,
    matlab_rel: str,
    rule: InlineRule,
) -> ProcessRecord:
    signs_by_wid = _inline_signs_by_wid(fx, substrate_wids, rule)
    if not signs_by_wid:
        payload = _blocker_payload(
            process_name,
            "Inline rule produced no substrate matches in fixture substrateIndexs_* fields.",
            f"{fixture_rel} + {matlab_rel}",
            substrate_wids,
            fx,
            extra={"inline_rule": rule.__dict__},
        )
        return ProcessRecord(payload=payload, blocker=True, n_entries=0)

    entries = [
        _inline_entry(wid, signs_by_wid[wid])
        for wid in substrate_wids
        if wid in signs_by_wid
    ]
    payload: dict[str, Any] = {
        "process": process_name,
        "class": "inline",
        "source": (
            f"{matlab_rel}:evolveState substrate arithmetic + {fixture_rel}:substrateIndexs_* "
            "mapping to substrateWholeCellModelIDs"
        ),
        "substrates": entries,
        "n_substrates": int(len(entries)),
        "n_reactions": 0,
        "n_entries": int(len(entries)),
    }
    if rule.note:
        payload["note"] = rule.note
    return ProcessRecord(payload=payload, blocker=False, n_entries=len(entries))


def _none_record(
    process_name: str,
    fixture_rel: str,
    matlab_rel: str,
    note: str,
) -> ProcessRecord:
    payload = {
        "process": process_name,
        "class": "none",
        "source": f"{matlab_rel} + {fixture_rel}",
        "note": note,
        "substrates": [],
        "n_substrates": 0,
        "n_reactions": 0,
        "n_entries": 0,
    }
    return ProcessRecord(payload=payload, blocker=False, n_entries=0)


def _process_record(process_meta: dict[str, Any]) -> ProcessRecord:
    name = process_meta["name"]
    fixture_rel = f"data/karr_fixtures/per_process/{name}_flat.mat"
    matlab_rel = (
        f"data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/{name}.m"
    )

    fx = _load_fixture(name)
    substrate_wids = _get_substrate_wids(fx)

    if name in NONE_PROCESS_NOTES:
        return _none_record(name, fixture_rel, matlab_rel, NONE_PROCESS_NOTES[name])

    matrix_record = _matrix_record(name, fx, substrate_wids, fixture_rel, matlab_rel)
    if matrix_record is not None:
        if matrix_record.blocker:
            return matrix_record
        if name in MATRIX_INLINE_AUGMENT_RULES:
            signs_by_wid = _inline_signs_by_wid(
                fx, substrate_wids, MATRIX_INLINE_AUGMENT_RULES[name]
            )
            merged_entries = _merge_sign_roles(
                matrix_record.payload["substrates"],
                substrate_wids,
                signs_by_wid,
            )
            matrix_record.payload["substrates"] = merged_entries
            matrix_record.payload["n_substrates"] = int(len(merged_entries))
            matrix_record.payload["n_entries"] = int(len(merged_entries))
            note = MATRIX_INLINE_AUGMENT_RULES[name].note
            if note:
                matrix_record.payload["note"] = note
            matrix_record.n_entries = len(merged_entries)
        return matrix_record

    rule = INLINE_RULES.get(name)
    if rule is not None:
        return _inline_record(name, fx, substrate_wids, fixture_rel, matlab_rel, rule)

    if len(substrate_wids) == 0:
        return _none_record(
            name,
            fixture_rel,
            matlab_rel,
            "No process substrates are declared in fixture; no small-molecule substrate stoichiometry available.",
        )

    payload = _blocker_payload(
        name,
        (
            "Could not classify process as matrix, inline, or none. "
            "Checked default reactionStoichiometry fields, matrix overrides, and inline rule table."
        ),
        f"{fixture_rel} + {matlab_rel} inspection",
        substrate_wids,
        fx,
        extra={
            "checked_matrix_fields": _matrix_candidates(name),
            "checked_override_fields": [
                spec.field for spec in MATRIX_OVERRIDES.get(name, tuple())
            ],
        },
    )
    return ProcessRecord(payload=payload, blocker=True, n_entries=0)


def _write_process_json(out_dir: Path, process: str, payload: dict[str, Any]) -> None:
    path = out_dir / f"{process}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")


def _record_from_existing_payload(payload: dict[str, Any]) -> ProcessRecord:
    blocker = payload.get("status") == "BLOCKER"
    if blocker:
        return ProcessRecord(payload=payload, blocker=True, n_entries=0)
    n_entries = int(payload.get("n_entries", len(payload.get("substrates", []))))
    return ProcessRecord(payload=payload, blocker=False, n_entries=n_entries)


def _build_readme(records: list[ProcessRecord]) -> str:
    total_entries = sum(r.n_entries for r in records if not r.blocker)
    lines: list[str] = []
    lines.append("# Karr Per-Process Stoichiometry Oracle")
    lines.append("")
    lines.append("Generated by `scripts/extract_karr_stoichiometry.py`.")
    lines.append("")
    lines.append("## Per-process Source + Counts")
    lines.append("")
    lines.append("| Process | Status | Class | Source/matrix | n_substrates | n_entries |")
    lines.append("|---|---|---|---|---:|---:|")
    for record in records:
        payload = record.payload
        process = payload["process"]
        if record.blocker:
            lines.append(
                f"| {process} | BLOCKER | - | {payload['source']} | 0 | 0 |"
            )
            continue
        klass = payload.get("class")
        if not klass:
            klass = "matrix" if payload.get("matrix_field") else "legacy"
        source_summary = payload.get("matrix_field", payload.get("source", ""))
        lines.append(
            f"| {process} | OK | {klass} | {source_summary} | "
            f"{payload.get('n_substrates', 0)} | {payload.get('n_entries', len(payload.get('substrates', [])))} |"
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
            reason = blocker.get("reason", "No reason recorded.")
            lines.append(f"- `{blocker['process']}`: {reason}")
            checked = blocker.get("checked_override_fields")
            if checked:
                lines.append(f"  - checked override fields: {', '.join(checked)}")
            checked_default = blocker.get("checked_matrix_fields")
            if checked_default:
                lines.append(f"  - checked default matrix fields: {', '.join(checked_default)}")
    lines.append("")
    return "\n".join(lines)


def _parse_only_arg(only: str, valid_names: set[str]) -> set[str]:
    if not only.strip():
        return set(valid_names)
    selected = {name.strip() for name in only.split(",") if name.strip()}
    unknown = sorted(selected - valid_names)
    if unknown:
        raise ValueError(f"--only includes unknown process names: {', '.join(unknown)}")
    return selected


def main() -> None:
    args = _parse_args()
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = _load_targets()
    valid_names = {meta["name"] for meta in targets}
    selected = _parse_only_arg(args.only, valid_names)

    records: list[ProcessRecord] = []
    for process_meta in targets:
        name = process_meta["name"]
        path = out_dir / f"{name}.json"
        if name in selected:
            record = _process_record(process_meta)
            records.append(record)
            _write_process_json(out_dir, name, record.payload)
            continue

        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            records.append(_record_from_existing_payload(payload))
            continue

        record = _process_record(process_meta)
        records.append(record)
        _write_process_json(out_dir, name, record.payload)

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
