"""Gate 2 — validate OC process input surfaces against the frozen Karr spec."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent

_DERIVE_SPEC = importlib.util.spec_from_file_location(
    "_gate2_derive_input_spec",
    SCRIPT_DIR / "derive_input_spec.py",
)
assert _DERIVE_SPEC is not None and _DERIVE_SPEC.loader is not None
derive_input_spec = importlib.util.module_from_spec(_DERIVE_SPEC)
_DERIVE_SPEC.loader.exec_module(derive_input_spec)

REPO_ROOT = derive_input_spec.REPO_ROOT
PROCESS_NAMES = derive_input_spec.PROCESS_NAMES
DEFAULT_SPEC_DIR = derive_input_spec.OUTPUT_ROOT
DEFAULT_FIXTURE_DIR = derive_input_spec.FIXTURE_ROOT
_REPLAY_COMMON_PATH = REPO_ROOT / "tests" / "vivarium" / "l2_2_replay_common_v2.py"
_SOURCE_TRUTH_PATH = DEFAULT_SPEC_DIR / "_gate0_source_truth.json"
_CONSTANT_INVENTORY_PATH = DEFAULT_SPEC_DIR / "_gate0_constant_inventory.json"

_STATUS_CONFORM = "CONFORM"
_STATUS_DIVERGE = "DIVERGE"
_STATUS_NOT_EXPOSED = "NOT_EXPOSED"

_PREVIEW_LIMIT = 12
_ROLE_TO_SPEC_FIELD = {
    "substrates": "substrateWholeCellModelIDs",
    "enzymes": "enzymeWholeCellModelIDs",
    "stimuli": "stimuliWholeCellModelIDs",
}
_ROLE_ATTR_CANDIDATES = {
    "substrates": (
        "substrate_wids",
        "_substrate_wids",
        "fixture_substrate_wids",
        "allocation_substrate_wids",
        "aa_ids",
    ),
    "enzymes": (
        "enzyme_wids",
        "fixture_enzyme_wids",
        "gtpase_wids",
        "enzyme_component_wids",
        "catalytic_enzyme_wids",
        "complex_enzyme_wids",
    ),
    "stimuli": (
        "stimuli_wids",
        "stimulus_wids",
    ),
}
_COMPARTMENT_SUFFIX_RE = re.compile(r"@compartment_\d+$")
_TOKEN_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
_SURFACE_LEAF_IGNORE = {
    "_command_result",
    "_condition_path",
    "_parallel",
    "_parameters",
    "_pending_command",
    "_rng",
    "_schema",
    "_schema_override",
}
_STOICH_REACTION_ID_TERMINALS = {
    "reaction_wids",
    "rxn_wcm_ids_645",
}
_STOICH_FULL_MATRIX_TERMINALS = {
    "reaction_stoich",
}
_STOICH_PARTIAL_MATRIX_TERMINALS = {
    "reaction_small_molecule_stoich",
}
_STOICH_SUBSTRATE_ID_TERMINALS = {
    "substrate_wids",
    "substrate_wids_585",
}


@dataclass(slots=True)
class RoleComparison:
    role: str
    status: str
    missing_in_oc: list[str] = field(default_factory=list)
    extra_in_oc: list[str] = field(default_factory=list)
    expected_count: int = 0
    actual_count: int = 0
    attr_used: str | None = None
    note: str | None = None


@dataclass(slots=True)
class ClassResult:
    status: str
    details: list[str] = field(default_factory=list)


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _load_process_specs() -> Mapping[str, Any]:
    replay_spec = importlib.util.spec_from_file_location(
        "_gate2_replay_common_v2",
        _REPLAY_COMMON_PATH,
    )
    assert replay_spec is not None and replay_spec.loader is not None
    replay_common = importlib.util.module_from_spec(replay_spec)
    sys.modules[replay_spec.name] = replay_common
    replay_spec.loader.exec_module(replay_common)
    return replay_common._PROCESS_SPECS


def _load_spec_payload(spec_path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _load_source_truth(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for entry in payload.get("processes", []):
        name = str(entry.get("name", "")).strip()
        if name:
            out[name] = entry
    return out


def _normalized_process_key(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _load_constant_inventory(path: Path) -> dict[str, list[str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    process_name_by_key = {
        _normalized_process_key(process_name): process_name for process_name in PROCESS_NAMES
    }
    out: dict[str, list[str]] = {}
    for entry in payload.get("processes", []):
        raw_name = str(entry.get("name", "")).strip()
        process_name = process_name_by_key.get(_normalized_process_key(raw_name))
        if process_name is None:
            continue
        names = [str(item.get("name", "")).strip() for item in entry.get("fixed", [])]
        names.extend(str(item.get("name", "")).strip() for item in entry.get("fitted", []))
        out[process_name] = [name for name in names if name]
    return out


def _normalize_vocab_value(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, bytes):
        return [value.decode("utf-8", errors="replace")]
    if isinstance(value, str):
        return [value]
    if isinstance(value, np.ndarray):
        return [str(item) for item in value.reshape(-1).tolist()]
    if isinstance(value, Iterable):
        return [str(item) for item in value]
    return [str(value)]


def _normalize_wid(wid: str) -> str:
    return _COMPARTMENT_SUFFIX_RE.sub("", wid)


def _compare_vocab_sets(*, expected: Iterable[str], actual: Iterable[str]) -> tuple[list[str], list[str]]:
    expected_set = set(expected)
    actual_set = set(actual)
    return sorted(expected_set - actual_set), sorted(actual_set - expected_set)


def _preview_items(items: list[str]) -> str:
    if len(items) <= _PREVIEW_LIMIT:
        preview = items
    else:
        preview = [*items[:_PREVIEW_LIMIT], f"+{len(items) - _PREVIEW_LIMIT} more"]
    return f"[{', '.join(preview)}] (count={len(items)})"


def _expected_vocab(spec_payload: Mapping[str, Any], *, role: str) -> list[str]:
    vocabularies = spec_payload.get("vocabularies") or {}
    field_name = _ROLE_TO_SPEC_FIELD[role]
    return [_normalize_wid(str(item)) for item in vocabularies.get(field_name, [])]


def _resolve_role_vocab(process: Any, *, role: str) -> tuple[list[str], str | None, bool]:
    first_existing_attr: str | None = None
    for attr_name in _ROLE_ATTR_CANDIDATES[role]:
        if not hasattr(process, attr_name):
            continue
        if first_existing_attr is None:
            first_existing_attr = attr_name
        raw_value = getattr(process, attr_name)
        values = [_normalize_wid(item) for item in _normalize_vocab_value(raw_value)]
        if values:
            return values, attr_name, True
    return [], first_existing_attr, first_existing_attr is not None


def _evaluate_vocab_role(
    *,
    process_name: str,
    role: str,
    expected: list[str],
    actual: list[str],
    attr_used: str | None,
    had_any_attr: bool,
) -> RoleComparison:
    missing_in_oc, extra_in_oc = _compare_vocab_sets(expected=expected, actual=actual)

    if process_name == "Metabolism" and role == "substrates" and not actual:
        return RoleComparison(
            role=role,
            status=_STATUS_NOT_EXPOSED,
            expected_count=len(set(expected)),
            actual_count=0,
            attr_used=attr_used,
            note=(
                "OC exposes metabolism substrates through the FBA model rather than a "
                "flat 585-WID list, so a comparable flat substrate surface is not exposed."
            ),
        )

    if missing_in_oc or extra_in_oc:
        status = _STATUS_DIVERGE
        note = None
        if not actual and expected and not had_any_attr:
            status = _STATUS_NOT_EXPOSED
            note = "No OC attribute exposed this vocabulary role."
        elif not actual and expected:
            status = _STATUS_NOT_EXPOSED
            note = f"Candidate OC attribute {attr_used!r} is empty."
        return RoleComparison(
            role=role,
            status=status,
            missing_in_oc=missing_in_oc,
            extra_in_oc=extra_in_oc,
            expected_count=len(set(expected)),
            actual_count=len(set(actual)),
            attr_used=attr_used,
            note=note,
        )

    return RoleComparison(
        role=role,
        status=_STATUS_CONFORM,
        expected_count=len(set(expected)),
        actual_count=len(set(actual)),
        attr_used=attr_used,
    )


def _combine_statuses(statuses: Iterable[str]) -> str:
    status_set = set(statuses)
    if _STATUS_DIVERGE in status_set:
        return _STATUS_DIVERGE
    if _STATUS_NOT_EXPOSED in status_set:
        return _STATUS_NOT_EXPOSED
    return _STATUS_CONFORM


def _evaluate_vocabulary_class(process_name: str, process: Any, spec_payload: Mapping[str, Any]) -> ClassResult:
    role_results: list[RoleComparison] = []
    for role in ("substrates", "enzymes", "stimuli"):
        expected = _expected_vocab(spec_payload, role=role)
        actual, attr_used, had_any_attr = _resolve_role_vocab(process, role=role)
        role_results.append(
            _evaluate_vocab_role(
                process_name=process_name,
                role=role,
                expected=expected,
                actual=actual,
                attr_used=attr_used,
                had_any_attr=had_any_attr,
            )
        )

    status = _combine_statuses(result.status for result in role_results)
    details: list[str] = []
    for result in role_results:
        if result.status == _STATUS_CONFORM:
            continue
        detail = (
            f"{result.role}: {result.status} "
            f"(expected={result.expected_count}, actual={result.actual_count}, attr={result.attr_used!r})"
        )
        if result.missing_in_oc:
            detail += f" missing_in_oc={_preview_items(result.missing_in_oc)}"
        if result.extra_in_oc:
            detail += f" extra_in_oc={_preview_items(result.extra_in_oc)}"
        if result.note:
            detail += f" note={result.note}"
        details.append(detail)

    return ClassResult(status=status, details=details)


def _tokens(value: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(value)]


def _walk_surface(value: Any, *, path: str, depth: int, leaves: dict[str, Any], seen: set[int]) -> None:
    if value is None:
        return
    if isinstance(value, (str, bytes, bytearray, bool, int, float, np.ndarray, list, tuple, set)):
        leaves[path] = value
        return
    if depth <= 0:
        leaves[path] = value
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_str = str(key)
            _walk_surface(
                item,
                path=f"{path}.{key_str}" if path else key_str,
                depth=depth - 1,
                leaves=leaves,
                seen=seen,
            )
        return
    if not hasattr(value, "__dict__"):
        leaves[path] = value
        return
    identity = id(value)
    if identity in seen:
        return
    seen.add(identity)
    for attr_name, attr_value in sorted(vars(value).items()):
        if attr_name in _SURFACE_LEAF_IGNORE:
            continue
        if callable(attr_value):
            continue
        _walk_surface(
            attr_value,
            path=f"{path}.{attr_name}" if path else attr_name,
            depth=depth - 1,
            leaves=leaves,
            seen=seen,
        )


def _collect_surface_leaves(process: Any) -> dict[str, Any]:
    leaves: dict[str, Any] = {}
    _walk_surface(process, path="", depth=2, leaves=leaves, seen=set())
    return leaves


def _find_surface_candidates(leaves: Mapping[str, Any], terminals: set[str]) -> list[tuple[str, Any]]:
    return [
        (path, value)
        for path, value in leaves.items()
        if path.rsplit(".", 1)[-1] in terminals
    ]


def _coerce_string_list(value: Any) -> list[str]:
    return [str(item) for item in _normalize_vocab_value(value)]


def _coerce_matrix(value: Any) -> np.ndarray | None:
    if isinstance(value, np.ndarray):
        return value
    try:
        matrix = np.asarray(value)
    except Exception:  # noqa: BLE001
        return None
    return matrix if matrix.ndim == 2 else None


def _spec_reaction_species(spec_payload: Mapping[str, Any]) -> dict[str, set[str]] | None:
    stoichiometry = spec_payload.get("stoichiometry") or {}
    reactions = stoichiometry.get("reactions")
    if not isinstance(reactions, Mapping):
        return None
    out: dict[str, set[str]] = {}
    for reaction_wid, reaction_payload in reactions.items():
        consume = reaction_payload.get("consume") or {}
        produce = reaction_payload.get("produce") or {}
        out[str(reaction_wid)] = {str(item) for item in consume} | {str(item) for item in produce}
    return out


def _build_oc_reaction_species(
    *,
    reaction_ids: list[str],
    substrate_ids: list[str],
    stoich_matrix: np.ndarray,
) -> dict[str, set[str]] | None:
    if stoich_matrix.shape != (len(substrate_ids), len(reaction_ids)):
        return None
    out: dict[str, set[str]] = {}
    for reaction_index, reaction_id in enumerate(reaction_ids):
        column = stoich_matrix[:, reaction_index]
        species = {
            substrate_ids[row_index]
            for row_index in np.flatnonzero(column).tolist()
        }
        out[reaction_id] = species
    return out


def _evaluate_stoichiometry_class(process: Any, spec_payload: Mapping[str, Any]) -> ClassResult:
    spec_species = _spec_reaction_species(spec_payload)
    if spec_species is None:
        return ClassResult(status=_STATUS_CONFORM)

    leaves = _collect_surface_leaves(process)
    reaction_id_candidates = _find_surface_candidates(leaves, _STOICH_REACTION_ID_TERMINALS)
    full_matrix_candidates = _find_surface_candidates(leaves, _STOICH_FULL_MATRIX_TERMINALS)
    partial_matrix_candidates = _find_surface_candidates(leaves, _STOICH_PARTIAL_MATRIX_TERMINALS)
    substrate_id_candidates = _find_surface_candidates(leaves, _STOICH_SUBSTRATE_ID_TERMINALS)

    best_species: dict[str, set[str]] | None = None
    best_reaction_path: str | None = None
    best_matrix_path: str | None = None
    best_substrate_path: str | None = None

    for reaction_path, reaction_value in reaction_id_candidates:
        reaction_ids = _coerce_string_list(reaction_value)
        for substrate_path, substrate_value in substrate_id_candidates:
            substrate_ids = [_normalize_wid(item) for item in _coerce_string_list(substrate_value)]
            for matrix_path, matrix_value in full_matrix_candidates:
                matrix = _coerce_matrix(matrix_value)
                if matrix is None:
                    continue
                species = _build_oc_reaction_species(
                    reaction_ids=reaction_ids,
                    substrate_ids=substrate_ids,
                    stoich_matrix=matrix,
                )
                if species is None:
                    continue
                best_species = species
                best_reaction_path = reaction_path
                best_matrix_path = matrix_path
                best_substrate_path = substrate_path
                break
            if best_species is not None:
                break
        if best_species is not None:
            break

    if best_species is None:
        reason = "OC does not expose a comparable reaction-id + full stoichiometry surface."
        if reaction_id_candidates and partial_matrix_candidates:
            reason = (
                "OC exposes reaction ids and partial small-molecule stoichiometry, but not a "
                "comparable full reaction species surface."
            )
        return ClassResult(
            status=_STATUS_NOT_EXPOSED,
            details=[reason],
        )

    spec_reactions = sorted(spec_species)
    oc_reactions = sorted(best_species)
    missing_in_oc, extra_in_oc = _compare_vocab_sets(expected=spec_reactions, actual=oc_reactions)

    shared = sorted(set(spec_species) & set(best_species))
    species_mismatches: list[str] = []
    for reaction_id in shared:
        spec_set = spec_species[reaction_id]
        oc_set = best_species[reaction_id]
        if spec_set == oc_set:
            continue
        missing_species, extra_species = _compare_vocab_sets(expected=spec_set, actual=oc_set)
        detail = f"{reaction_id}:"
        if missing_species:
            detail += f" missing_species={_preview_items(missing_species)}"
        if extra_species:
            detail += f" extra_species={_preview_items(extra_species)}"
        species_mismatches.append(detail)

    details: list[str] = []
    if missing_in_oc:
        details.append(f"reactions missing_in_oc={_preview_items(missing_in_oc)}")
    if extra_in_oc:
        details.append(f"reactions extra_in_oc={_preview_items(extra_in_oc)}")
    if species_mismatches:
        details.append(
            "species_mismatches="
            + _preview_items(species_mismatches)
        )

    if details:
        details.append(
            "surface="
            f"reaction_ids:{best_reaction_path} matrix:{best_matrix_path} substrates:{best_substrate_path}"
        )
        return ClassResult(status=_STATUS_DIVERGE, details=details)

    return ClassResult(status=_STATUS_CONFORM)


def _evaluate_state_refs_class(
    process_name: str,
    process: Any,
    source_truth: Mapping[str, dict[str, Any]],
) -> ClassResult:
    del process_name, process, source_truth
    return ClassResult(
        status=_STATUS_NOT_EXPOSED,
        details=["State-ref validation not yet wired in this chunk."],
    )


def _evaluate_constants_class(
    process_name: str,
    process: Any,
    spec_payload: Mapping[str, Any],
    constant_inventory: Mapping[str, list[str]],
) -> ClassResult:
    del process_name, process, spec_payload, constant_inventory
    return ClassResult(
        status=_STATUS_NOT_EXPOSED,
        details=["Constant validation not yet wired in this chunk."],
    )


def _process_spec_items(
    process_specs: Mapping[str, Any] | None,
    *,
    process_names: tuple[str, ...],
) -> list[tuple[str, Any]]:
    specs = process_specs if process_specs is not None else _load_process_specs()
    return [(process_name, specs[process_name]) for process_name in process_names]


def _matrix_lines(process_results: list[tuple[str, dict[str, ClassResult]]]) -> list[str]:
    headers = ("Process", "Vocab", "Stoich", "StateRefs", "Constants")
    rows = [
        (
            process_name,
            class_results["vocab"].status,
            class_results["stoich"].status,
            class_results["state_refs"].status,
            class_results["constants"].status,
        )
        for process_name, class_results in process_results
    ]
    widths = [
        max(len(header), *(len(row[index]) for row in rows))
        for index, header in enumerate(headers)
    ]
    lines = [
        "  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)),
        "  ".join("-" * widths[index] for index in range(len(headers))),
    ]
    for row in rows:
        lines.append("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
    return lines


def _detail_lines(process_results: list[tuple[str, dict[str, ClassResult]]]) -> list[str]:
    lines: list[str] = []
    for process_name, class_results in process_results:
        for class_name, class_result in class_results.items():
            if class_result.status == _STATUS_CONFORM:
                continue
            lines.append(f"{process_name} [{class_name}] {class_result.status}")
            for detail in class_result.details:
                lines.append(f"  - {detail}")
    return lines


def _gate_result(
    *,
    spec_dir: Path = DEFAULT_SPEC_DIR,
    fixture_dir: Path = DEFAULT_FIXTURE_DIR,
    process_specs: Mapping[str, Any] | None = None,
    process_names: tuple[str, ...] = PROCESS_NAMES,
) -> tuple[int, str]:
    expected = tuple(process_names)

    if not spec_dir.exists():
        return 0, (
            "GATE 2 (OC vs spec): SKIPPED — frozen spec dir absent at "
            f"{_display_path(spec_dir)}."
        )
    if not fixture_dir.exists():
        return 0, (
            "GATE 2 (OC vs spec): SKIPPED — fixtures absent at "
            f"{_display_path(fixture_dir)}."
        )

    missing_fixture_files = [
        process_name
        for process_name in expected
        if not (fixture_dir / f"{process_name}_flat.mat").exists()
    ]
    if missing_fixture_files:
        preview = ", ".join(missing_fixture_files[:4])
        if len(missing_fixture_files) > 4:
            preview += f", +{len(missing_fixture_files) - 4} more"
        return 0, (
            "GATE 2 (OC vs spec): SKIPPED — fixtures absent for "
            f"{len(missing_fixture_files)}/{len(expected)} expected process(es): {preview}."
        )

    source_truth = _load_source_truth(_SOURCE_TRUTH_PATH) if _SOURCE_TRUTH_PATH.exists() else {}
    constant_inventory = (
        _load_constant_inventory(_CONSTANT_INVENTORY_PATH)
        if _CONSTANT_INVENTORY_PATH.exists()
        else {}
    )

    process_results: list[tuple[str, dict[str, ClassResult]]] = []
    construct_errors: list[str] = []

    for process_name, spec in _process_spec_items(process_specs, process_names=expected):
        spec_path = spec_dir / f"{process_name}.yaml"
        if not spec_path.exists():
            process_results.append(
                (
                    process_name,
                    {
                        "vocab": ClassResult(
                            status=_STATUS_DIVERGE,
                            details=[f"Missing frozen spec file {_display_path(spec_path)}"],
                        ),
                        "stoich": ClassResult(status=_STATUS_NOT_EXPOSED),
                        "state_refs": ClassResult(status=_STATUS_NOT_EXPOSED),
                        "constants": ClassResult(status=_STATUS_NOT_EXPOSED),
                    },
                )
            )
            continue

        spec_payload = _load_spec_payload(spec_path)

        try:
            process = spec.process_cls({"rng_seed": 0})
        except Exception as exc:  # noqa: BLE001
            construct_errors.append(
                f"{process_name}: CONSTRUCT_ERROR {exc.__class__.__name__}: {exc}"
            )
            process_results.append(
                (
                    process_name,
                    {
                        "vocab": ClassResult(status=_STATUS_DIVERGE, details=["Process construction failed."]),
                        "stoich": ClassResult(status=_STATUS_NOT_EXPOSED),
                        "state_refs": ClassResult(status=_STATUS_NOT_EXPOSED),
                        "constants": ClassResult(status=_STATUS_NOT_EXPOSED),
                    },
                )
            )
            continue

        class_results = {
            "vocab": _evaluate_vocabulary_class(process_name, process, spec_payload),
            "stoich": _evaluate_stoichiometry_class(process, spec_payload),
            "state_refs": _evaluate_state_refs_class(process_name, process, source_truth),
            "constants": _evaluate_constants_class(
                process_name,
                process,
                spec_payload,
                constant_inventory,
            ),
        }
        process_results.append((process_name, class_results))

    matrix_lines = _matrix_lines(process_results)
    details = _detail_lines(process_results)
    diverge_cells = sum(
        class_result.status == _STATUS_DIVERGE
        for _, class_results in process_results
        for class_result in class_results.values()
    )
    not_exposed_cells = sum(
        class_result.status == _STATUS_NOT_EXPOSED
        for _, class_results in process_results
        for class_result in class_results.values()
    )

    if construct_errors:
        details.extend(f"construct_error: {item}" for item in construct_errors)

    summary = (
        f"GATE 2 (OC vs spec): {'FAIL' if diverge_cells else 'PASS'} — "
        f"diverge_cells={diverge_cells}, not_exposed_cells={not_exposed_cells}, "
        f"processes={len(expected)}"
    )
    message_lines = [summary, "Matrix:", *matrix_lines]
    if details:
        message_lines.extend(["Details:", *details])

    return (1 if diverge_cells else 0), "\n".join(message_lines)


def main() -> int:
    code, message = _gate_result()
    print(message)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
