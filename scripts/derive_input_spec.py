from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import numpy as np
import yaml
from scipy import sparse
from scipy.io import loadmat

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "data" / "karr_fixtures" / "per_process"
OUTPUT_ROOT = REPO_ROOT / "data" / "karr_input_spec"

PROCESS_NAMES = (
    "ChromosomeCondensation",
    "ChromosomeSegregation",
    "Cytokinesis",
    "DNADamage",
    "DNARepair",
    "DNASupercoiling",
    "FtsZPolymerization",
    "HostInteraction",
    "MacromolecularComplexation",
    "Metabolism",
    "ProteinActivation",
    "ProteinDecay",
    "ProteinFolding",
    "ProteinModification",
    "ProteinProcessingI",
    "ProteinProcessingII",
    "ProteinTranslocation",
    "Replication",
    "ReplicationInitiation",
    "RibosomeAssembly",
    "RNADecay",
    "RNAModification",
    "RNAProcessing",
    "TerminalOrganelleAssembly",
    "Transcription",
    "TranscriptionalRegulation",
    "Translation",
    "tRNAAminoacylation",
)

WHOLE_CELL_MODEL_IDS_SUFFIX = "WholeCellModelIDs"
CAMEL_TOKEN_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
LOCAL_ROOT_ALIASES = {
    "stimulus": "stimuli",
}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fixture_path(process_name: str) -> Path:
    return FIXTURE_ROOT / f"{process_name}_flat.mat"


def _path_for_report(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _unwrap_object_scalar(value: Any) -> Any:
    current = value
    while isinstance(current, np.ndarray) and current.dtype == object and current.size == 1:
        current = current.reshape(-1)[0]
    return current


def _fixture_field_names(fixture: Any) -> tuple[str, ...]:
    fields = getattr(fixture, "_fieldnames", None)
    if fields is None:
        raise ValueError("Expected MATLAB mat_struct fixture with _fieldnames.")
    return tuple(str(name) for name in fields)


def _is_mat_struct(value: Any) -> bool:
    return hasattr(value, "_fieldnames")


def _dense_array(value: Any) -> np.ndarray:
    current = _unwrap_object_scalar(value)
    if sparse.issparse(current):
        return np.asarray(current.toarray())
    return np.asarray(current)


def _to_text(value: Any) -> str:
    current = _unwrap_object_scalar(value)
    if isinstance(current, bytes):
        return current.decode("utf-8", errors="replace")
    if isinstance(current, str):
        return current
    if isinstance(current, np.generic):
        return str(current.item())
    if isinstance(current, np.ndarray):
        if current.dtype == object and current.size == 1:
            return _to_text(current.reshape(-1)[0])
        if current.dtype.kind in {"U", "S"}:
            if current.ndim == 0:
                return str(current.item())
            if current.ndim == 1:
                parts = [str(item) for item in current.tolist()]
                if parts and all(len(part) == 1 for part in parts):
                    return "".join(parts)
                return str(parts[0]) if len(parts) == 1 else " ".join(parts)
            return "".join(_to_text(item) for item in current.reshape(-1))
        if current.size == 1:
            return _to_text(current.reshape(-1)[0])
    return str(current)


def _extract_string_list(value: Any) -> list[str]:
    current = _unwrap_object_scalar(value)

    if current is None:
        return []
    if isinstance(current, bytes):
        token = current.decode("utf-8", errors="replace").strip()
        return [token] if token else []
    if isinstance(current, str):
        token = current.strip()
        return [token] if token else []
    if isinstance(current, np.generic):
        return _extract_string_list(current.item())
    if isinstance(current, np.ndarray):
        if current.size == 0:
            return []
        if current.dtype == object:
            out: list[str] = []
            for item in current.reshape(-1):
                out.extend(_extract_string_list(item))
            return out
        if current.dtype.kind in {"U", "S"}:
            if current.ndim == 0:
                token = str(current.item()).strip()
                return [token] if token else []
            if current.ndim == 1:
                parts = [str(item) for item in current.tolist()]
                if parts and all(len(part) == 1 for part in parts):
                    token = "".join(parts).strip()
                    return [token] if token else []
                return [part.strip() for part in parts if part.strip()]
            return [_to_text(row).strip() for row in current.tolist() if _to_text(row).strip()]
        if current.size == 1:
            return _extract_string_list(current.reshape(-1)[0])
        return [str(item).strip() for item in current.reshape(-1) if str(item).strip()]
    if isinstance(current, (list, tuple)):
        out: list[str] = []
        for item in current:
            out.extend(_extract_string_list(item))
        return out

    token = str(current).strip()
    return [token] if token else []


def _to_index_list(value: Any, *, field_name: str) -> list[int]:
    current = _unwrap_object_scalar(value)
    arr = _dense_array(current)

    if arr.dtype == object:
        pieces: list[int] = []
        for item in arr.reshape(-1):
            pieces.extend(_to_index_list(item, field_name=field_name))
        return pieces

    if arr.size == 0:
        return []
    if not np.issubdtype(arr.dtype, np.number):
        raise TypeError(f"Role-group field {field_name!r} is non-numeric (dtype={arr.dtype}).")

    out: list[int] = []
    for raw in arr.reshape(-1):
        value_f = float(raw)
        if not value_f.is_integer():
            raise ValueError(f"Role-group field {field_name!r} contains non-integer index {value_f!r}.")
        out.append(int(value_f))
    return out


def _normalize_python_scalar(value: Any) -> Any:
    current = _unwrap_object_scalar(value)
    if isinstance(current, np.generic):
        current = current.item()
    if isinstance(current, bytes):
        return current.decode("utf-8", errors="replace")
    if isinstance(current, (bool, int, float, str)) or current is None:
        return current
    return str(current)


def _normalize_nested(value: Any) -> Any:
    current = _unwrap_object_scalar(value)

    if _is_mat_struct(current):
        return {
            str(name): _normalize_nested(getattr(current, name))
            for name in sorted(_fixture_field_names(current))
        }

    if sparse.issparse(current):
        return _normalize_nested(current.toarray())

    if isinstance(current, np.ndarray):
        if current.ndim == 0:
            return _normalize_nested(current.item())
        if current.dtype == object:
            return [_normalize_nested(item) for item in current.tolist()]
        if current.dtype.kind in {"U", "S"}:
            return current.astype(str).tolist()
        return current.tolist()

    if isinstance(current, (list, tuple)):
        return [_normalize_nested(item) for item in current]

    return _normalize_python_scalar(current)


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _normalize_nested(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _leaf_count(value: Any) -> int:
    if isinstance(value, dict):
        return sum(_leaf_count(item) for item in value.values())
    if isinstance(value, list):
        return sum(_leaf_count(item) for item in value)
    return 1


def _should_emit_direct(value: Any) -> bool:
    return _leaf_count(value) <= 16 and len(_canonical_json_bytes(value)) <= 4096


def _numeric_bytes(arr: np.ndarray) -> bytes:
    dense = np.asarray(arr)
    if dense.dtype == np.bool_:
        normalized = dense.astype(np.int8, copy=False)
    elif np.issubdtype(dense.dtype, np.integer) or np.issubdtype(dense.dtype, np.unsignedinteger):
        normalized = dense.astype(np.int64, copy=False)
    elif np.issubdtype(dense.dtype, np.floating):
        normalized = dense.astype(np.float64, copy=False)
    elif np.issubdtype(dense.dtype, np.complexfloating):
        normalized = dense.astype(np.complex128, copy=False)
    else:
        raise TypeError(f"Unsupported numeric dtype for hashing: {dense.dtype}")
    return np.ascontiguousarray(normalized).tobytes(order="C")


def _value_sha256(value: Any) -> str:
    current = _unwrap_object_scalar(value)
    if sparse.issparse(current):
        current = current.toarray()
    if isinstance(current, np.ndarray) and current.dtype.kind in {"b", "i", "u", "f", "c"}:
        return sha256_bytes(_numeric_bytes(current))
    return sha256_bytes(_canonical_json_bytes(current))


def _is_small_direct_array(arr: np.ndarray) -> bool:
    return arr.ndim > 0 and arr.size <= 16 and 0 not in arr.shape


def _summarize_large_value(value: Any) -> dict[str, Any]:
    arr = _dense_array(value)
    return {
        "dtype": str(arr.dtype),
        "shape": list(arr.shape),
        "sha256": _value_sha256(arr),
    }


def _emit_param_value(value: Any) -> Any:
    current = _unwrap_object_scalar(value)

    if _is_mat_struct(current):
        normalized = {
            str(name): _emit_param_value(getattr(current, name))
            for name in sorted(_fixture_field_names(current))
        }
        if _should_emit_direct(normalized):
            return normalized
        return {
            "fields": sorted(_fixture_field_names(current)),
            "kind": "mat_struct",
            "sha256": _value_sha256(current),
        }

    if sparse.issparse(current):
        current = current.toarray()

    if isinstance(current, np.ndarray):
        if current.ndim == 0:
            return _emit_param_value(current.item())
        if _is_small_direct_array(current):
            normalized = _normalize_nested(current)
            if _should_emit_direct(normalized):
                return normalized
        return _summarize_large_value(current)

    if isinstance(current, (list, tuple)):
        normalized = _normalize_nested(current)
        if _should_emit_direct(normalized):
            return normalized
        arr = np.asarray(current, dtype=object)
        return _summarize_large_value(arr)

    return _normalize_python_scalar(current)


def _stoich_coeff(value: Any) -> Any:
    scalar = _normalize_python_scalar(value)
    if isinstance(scalar, float) and scalar.is_integer():
        return int(scalar)
    return scalar


def _reaction_breakdown(
    matrix: Any,
    *,
    field_name: str,
    substrate_wids: list[str],
    reaction_wids: list[str],
) -> tuple[dict[str, Any] | None, str | None]:
    arr = _dense_array(matrix)
    if arr.ndim != 2:
        return None, f"{field_name} is not 2-D (shape={list(arr.shape)})"

    expected_shape = (len(substrate_wids), len(reaction_wids))
    transposed_shape = (len(reaction_wids), len(substrate_wids))

    if arr.shape != expected_shape:
        return (
            None,
            f"{field_name} shape does not align to "
            f"substrates x reactions (shape={list(arr.shape)}, expected={list(expected_shape)}, "
            f"transpose={list(transposed_shape)})",
        )

    if expected_shape == transposed_shape:
        return None, f"{field_name} axis orientation is ambiguous because substrate and reaction counts match"

    reactions: dict[str, Any] = {}
    for reaction_index, reaction_wid in enumerate(reaction_wids):
        consume: dict[str, Any] = {}
        produce: dict[str, Any] = {}
        column = arr[:, reaction_index]
        nonzero_rows = np.flatnonzero(column)
        for row_index in nonzero_rows.tolist():
            coeff = _stoich_coeff(column[row_index])
            substrate_wid = substrate_wids[row_index]
            if coeff < 0:
                consume[substrate_wid] = abs(coeff)
            elif coeff > 0:
                produce[substrate_wid] = coeff
        reactions[reaction_wid] = {"consume": consume, "produce": produce}
    return reactions, None


def _camel_tokens(value: str) -> list[str]:
    tokens = CAMEL_TOKEN_RE.findall(value)
    return tokens if tokens else [value]


def _resolve_indices_against_vocab(indices: list[int], vocab: list[str]) -> list[str] | None:
    resolved_wids: list[str] = []
    for index in indices:
        zero_based = index - 1
        if zero_based < 0 or zero_based >= len(vocab):
            return None
        resolved_wids.append(vocab[zero_based])
    return resolved_wids


def _candidate_vocab_fields_for_local_prefix(prefix: str, vocabularies: dict[str, list[str]]) -> list[str]:
    local_root = prefix.split("Local", 1)[0]
    tokens = _camel_tokens(local_root)
    candidates: list[str] = []
    seen: set[str] = set()

    for token_count in range(len(tokens), 0, -1):
        raw_root = "".join(tokens[:token_count])
        for root in (raw_root, LOCAL_ROOT_ALIASES.get(raw_root)):
            if not root or root in seen:
                continue
            seen.add(root)
            vocab_field = f"{root}{WHOLE_CELL_MODEL_IDS_SUFFIX}"
            if vocab_field in vocabularies:
                candidates.append(vocab_field)

    return candidates


def _resolve_role_group(
    field_name: str,
    *,
    indices: list[int],
    vocabularies: dict[str, list[str]],
) -> tuple[list[str] | None, str | None, bool]:
    prefix = field_name.split("Indexs", 1)[0]
    exact_vocab_field = f"{prefix}{WHOLE_CELL_MODEL_IDS_SUFFIX}"
    if exact_vocab_field in vocabularies:
        return (
            _resolve_indices_against_vocab(indices, vocabularies[exact_vocab_field]),
            exact_vocab_field,
            False,
        )

    if "Local" not in prefix:
        return None, None, False

    for vocab_field in _candidate_vocab_fields_for_local_prefix(prefix, vocabularies):
        return _resolve_indices_against_vocab(indices, vocabularies[vocab_field]), vocab_field, True

    return None, None, False


def derive_process_spec(process_name: str, *, output_dir: Path) -> dict[str, Any]:
    fixture_path = _fixture_path(process_name)
    fixture_relpath = fixture_path.relative_to(REPO_ROOT).as_posix()

    fixture_sha = sha256_file(fixture_path)
    mat = loadmat(fixture_path, squeeze_me=True, struct_as_record=False)
    if "data" not in mat:
        raise KeyError(f"Fixture {fixture_relpath} is missing top-level 'data'.")

    fixture = getattr(mat["data"], "fixture", None)
    if fixture is None:
        raise KeyError(f"Fixture {fixture_relpath} is missing 'data.fixture'.")

    vocabularies: dict[str, list[str]] = {}
    role_groups: dict[str, dict[str, Any]] = {}
    stoichiometry: dict[str, Any] = {}
    params: dict[str, Any] = {}
    unresolved_role_groups: list[str] = []
    ambiguous_stoichiometry: list[str] = []
    sentinel_index_fields_moved_to_params: list[str] = []
    newly_resolved_local_role_groups: list[str] = []
    identity_over_vocab_role_groups: list[str] = []

    fields = _fixture_field_names(fixture)

    for field_name in fields:
        raw_value = getattr(fixture, field_name)
        if field_name.endswith(WHOLE_CELL_MODEL_IDS_SUFFIX):
            vocabularies[field_name] = _extract_string_list(raw_value)

    for field_name in fields:
        raw_value = getattr(fixture, field_name)

        if field_name.endswith(WHOLE_CELL_MODEL_IDS_SUFFIX):
            continue

        if "Indexs" in field_name:
            try:
                indices = _to_index_list(raw_value, field_name=field_name)
            except (TypeError, ValueError):
                params[field_name] = _emit_param_value(raw_value)
                continue

            if any(index == 0 for index in indices):
                params[field_name] = _emit_param_value(raw_value)
                sentinel_index_fields_moved_to_params.append(field_name)
                continue

            resolved_wids, vocab_field, used_local_fallback = _resolve_role_group(
                field_name,
                indices=indices,
                vocabularies=vocabularies,
            )
            if resolved_wids is None:
                unresolved_role_groups.append(field_name)

            role_group_entry: dict[str, Any] = {"indices": indices, "wids": resolved_wids}
            if (
                resolved_wids is not None
                and "Local" in field_name
                and vocab_field is not None
                and resolved_wids == vocabularies[vocab_field]
            ):
                role_group_entry["identity_over_vocab"] = True
                identity_over_vocab_role_groups.append(field_name)
            if resolved_wids is not None and used_local_fallback:
                newly_resolved_local_role_groups.append(field_name)

            role_groups[field_name] = role_group_entry
            continue

        if field_name.startswith("reaction") and field_name.endswith("Matrix"):
            arr = _dense_array(raw_value)
            stoichiometry[field_name] = {
                "shape": list(arr.shape),
                "sha256": _value_sha256(arr),
            }
            if field_name == "reactionStoichiometryMatrix":
                substrate_wids = vocabularies.get("substrateWholeCellModelIDs")
                reaction_wids = vocabularies.get("reactionWholeCellModelIDs")
                if substrate_wids and reaction_wids:
                    reactions, issue = _reaction_breakdown(
                        raw_value,
                        field_name=field_name,
                        substrate_wids=substrate_wids,
                        reaction_wids=reaction_wids,
                    )
                    if reactions is not None:
                        stoichiometry["reactions"] = reactions
                        stoichiometry["reactions_source_field"] = field_name
                    if issue is not None:
                        ambiguous_stoichiometry.append(issue)
                else:
                    ambiguous_stoichiometry.append(
                        "reactionStoichiometryMatrix could not be resolved because substrateWholeCellModelIDs or reactionWholeCellModelIDs is missing"
                    )
            if field_name == "reactionSmallMoleculeStoichiometryMatrix":
                substrate_wids = vocabularies.get("substrateWholeCellModelIDs")
                reaction_wids = vocabularies.get("reactionWholeCellModelIDs")
                if substrate_wids and reaction_wids:
                    reactions, issue = _reaction_breakdown(
                        raw_value,
                        field_name=field_name,
                        substrate_wids=substrate_wids,
                        reaction_wids=reaction_wids,
                    )
                    if reactions is not None:
                        stoichiometry["reactions_small_molecule"] = reactions
                        stoichiometry["reactions_small_molecule_source_field"] = field_name
                    if issue is not None:
                        ambiguous_stoichiometry.append(issue)
                else:
                    ambiguous_stoichiometry.append(
                        "reactionSmallMoleculeStoichiometryMatrix could not be resolved because substrateWholeCellModelIDs or reactionWholeCellModelIDs is missing"
                    )
            continue

        params[field_name] = _emit_param_value(raw_value)

    payload: dict[str, Any] = {
        "params": params,
        "process": process_name,
        "role_groups": role_groups,
        "source": {
            "fixture": fixture_relpath,
            "fixture_sha256": fixture_sha,
        },
        "vocabularies": vocabularies,
    }
    if stoichiometry:
        payload["stoichiometry"] = stoichiometry

    yaml_text = yaml.safe_dump(
        payload,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=True,
        width=4096,
    )
    if not yaml_text.endswith("\n"):
        yaml_text += "\n"

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{process_name}.yaml"
    output_bytes = yaml_text.encode("utf-8")
    output_path.write_bytes(output_bytes)

    substrate_fixture = _extract_string_list(getattr(fixture, "substrateWholeCellModelIDs", []))
    vocabulary_matches_fixture = {
        field_name: vocabularies[field_name] == _extract_string_list(getattr(fixture, field_name))
        for field_name in fields
        if field_name.endswith(WHOLE_CELL_MODEL_IDS_SUFFIX)
    }

    return {
        "ambiguous_stoichiometry": ambiguous_stoichiometry,
        "fixture_relpath": fixture_relpath,
        "fixture_sha256": fixture_sha,
        "identity_over_vocab_role_groups": identity_over_vocab_role_groups,
        "newly_resolved_local_role_groups": newly_resolved_local_role_groups,
        "output_path": _path_for_report(output_path),
        "process_name": process_name,
        "sentinel_index_fields_moved_to_params": sentinel_index_fields_moved_to_params,
        "spec_sha256": sha256_bytes(output_bytes),
        "substrate_vocab_count": len(vocabularies.get("substrateWholeCellModelIDs", [])),
        "substrate_vocab_matches_fixture": vocabularies.get("substrateWholeCellModelIDs", []) == substrate_fixture,
        "vocabulary_matches_fixture": vocabulary_matches_fixture,
        "unresolved_role_groups": unresolved_role_groups,
    }


def derive_input_specs(
    *,
    output_dir: Path = OUTPUT_ROOT,
    process_names: tuple[str, ...] = PROCESS_NAMES,
) -> dict[str, Any]:
    reports: dict[str, Any] = {}
    manifest: dict[str, dict[str, str]] = {}
    missing_fixtures: list[str] = []

    for process_name in process_names:
        fixture_path = _fixture_path(process_name)
        if not fixture_path.exists():
            missing_fixtures.append(process_name)
            continue
        print(f"deriving {process_name}...")
        report = derive_process_spec(process_name, output_dir=output_dir)
        reports[process_name] = report
        manifest[process_name] = {
            "fixture_sha256": report["fixture_sha256"],
            "spec_sha256": report["spec_sha256"],
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "MANIFEST.json"
    manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    manifest_path.write_text(manifest_text, encoding="utf-8")

    unresolved_role_groups = {
        process_name: report["unresolved_role_groups"]
        for process_name, report in reports.items()
        if report["unresolved_role_groups"]
    }
    ambiguous_stoichiometry = {
        process_name: report["ambiguous_stoichiometry"]
        for process_name, report in reports.items()
        if report["ambiguous_stoichiometry"]
    }
    identity_over_vocab_role_groups = {
        process_name: report["identity_over_vocab_role_groups"]
        for process_name, report in reports.items()
        if report["identity_over_vocab_role_groups"]
    }
    newly_resolved_local_role_groups = {
        process_name: report["newly_resolved_local_role_groups"]
        for process_name, report in reports.items()
        if report["newly_resolved_local_role_groups"]
    }
    sentinel_index_fields_moved_to_params = {
        process_name: report["sentinel_index_fields_moved_to_params"]
        for process_name, report in reports.items()
        if report["sentinel_index_fields_moved_to_params"]
    }
    substrate_vocab_counts = {
        process_name: {
            "count": report["substrate_vocab_count"],
            "matches_fixture": report["substrate_vocab_matches_fixture"],
        }
        for process_name, report in reports.items()
    }
    vocabulary_matches_fixture = {
        process_name: report["vocabulary_matches_fixture"]
        for process_name, report in reports.items()
    }

    return {
        "ambiguous_stoichiometry": ambiguous_stoichiometry,
        "identity_over_vocab_role_groups": identity_over_vocab_role_groups,
        "manifest_path": _path_for_report(manifest_path),
        "missing_fixtures": missing_fixtures,
        "newly_resolved_local_role_groups": newly_resolved_local_role_groups,
        "process_reports": reports,
        "produced_processes": sorted(reports),
        "requested_processes": list(process_names),
        "sentinel_index_fields_moved_to_params": sentinel_index_fields_moved_to_params,
        "substrate_vocab_counts": substrate_vocab_counts,
        "unresolved_role_groups": unresolved_role_groups,
        "vocabulary_matches_fixture": vocabulary_matches_fixture,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Derive frozen Karr input-spec YAML from per-process MATLAB fixtures.")
    parser.add_argument(
        "--process",
        action="append",
        dest="processes",
        help="Restrict derivation to the named process. Repeatable.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_ROOT,
        help="Directory to receive generated YAML files and MANIFEST.json.",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        help="Optional JSON summary path for missing fixtures, unresolved groups, and sanity counts.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    requested = tuple(args.processes) if args.processes else PROCESS_NAMES
    summary = derive_input_specs(output_dir=args.output_dir, process_names=requested)

    if args.report_json is not None:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"derived {len(summary['produced_processes'])} process specs into {args.output_dir}")
    if summary["missing_fixtures"]:
        print("missing fixtures: " + ", ".join(summary["missing_fixtures"]))
    if summary["unresolved_role_groups"]:
        count = sum(len(groups) for groups in summary["unresolved_role_groups"].values())
        print(f"unresolved role groups: {count}")
    if summary["ambiguous_stoichiometry"]:
        count = sum(len(issues) for issues in summary["ambiguous_stoichiometry"].values())
        print(f"ambiguous stoichiometry issues: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
