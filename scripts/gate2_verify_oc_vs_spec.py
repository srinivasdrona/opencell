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
from scipy.io import loadmat

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
_STATE_USAGE_PATH = DEFAULT_SPEC_DIR / "_karr_state_usage.json"

_STATUS_CONFORM = "CONFORM"
_STATUS_DIVERGE = "DIVERGE"
_STATUS_NOT_EXPOSED = "NOT_EXPOSED"
_STATUS_NA = "N/A"

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
_STOICH_CATALYSIS_TERMINALS = {
    "reaction_catalysis",
}
_STOICH_SUBSTRATE_ID_TERMINALS = {
    "substrate_wids",
    "substrate_wids_585",
}
_STOICH_ENZYME_ID_TERMINALS = {
    "enzyme_wids",
    "catalytic_enzyme_wids",
    "complex_enzyme_wids",
    "monomer_enzyme_wids",
}
_IGNORED_STATE_USAGE_PORTS = {
    "boundenzymes",
    "requests",
    "substratesallocated",
    "txratefoldchange",
}
_PORT_STATE_CLASSES = {
    "cell": {"Geometry"},
    "chromosome": {"Chromosome"},
    "complex": {"ProteinComplex"},
    "complexs": {"ProteinComplex"},
    "enzymes": {"ProteinComplex", "ProteinMonomer"},
    "ftszring": {"FtsZRing"},
    "geometry": {"Geometry"},
    "host": {"Host"},
    "mass": {"Mass"},
    "metabolicreaction": {"MetabolicReaction"},
    "metabolite": {"Metabolite"},
    "monomer": {"ProteinMonomer"},
    "monomers": {"ProteinMonomer"},
    "polypeptide": {"Polypeptide"},
    "protein": {"ProteinMonomer"},
    "ribosome": {"Ribosome"},
    "rna": {"Rna"},
    "rnapolymerase": {"RNAPolymerase"},
    "rnapolymerases": {"RNAPolymerase"},
    "stimuli": {"Stimulus"},
    "stimulus": {"Stimulus"},
    "substrates": {"Metabolite"},
    "transcript": {"Transcript"},
    "transcripts": {"Transcript"},
}
_FIXTURE_LOCAL_INDEX_STATE_CLASSES = {
    "Complex": "ProteinComplex",
    "Metabolite": "Metabolite",
    "Monomer": "ProteinMonomer",
    "RNA": "Rna",
    "Stimulus": "Stimulus",
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


def _load_state_usage(path: Path) -> dict[str, list[str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    for process_name, entry in payload.items():
        if not isinstance(entry, Mapping):
            continue
        states = [str(item) for item in entry.get("states_used", []) if str(item).strip()]
        out[str(process_name)] = states
    return out


def _load_fixture(path: Path) -> object:
    return loadmat(str(path), squeeze_me=True, struct_as_record=False)["data"].fixture


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


def _model_substrate_wids(process: object) -> list[str]:
    """Metabolism holds its 585 substrates in the FBA model, not a flat attr.
    Reach `process.model.raw['ids']['substrate_wcm_585']` so its substrate vocab
    is validatable instead of NOT_EXPOSED."""
    model = getattr(process, "model", None)
    raw = getattr(model, "raw", None)
    if isinstance(raw, Mapping):
        ids = raw.get("ids")
        if isinstance(ids, Mapping):
            for key in ("substrate_wcm_585", "substrate_wcm"):
                value = ids.get(key)
                if value is not None:
                    return [str(item) for item in value]
    return []


def _resolve_role_vocab(process: object, *, role: str) -> tuple[list[str], str | None, bool]:
    first_existing_attr: str | None = None
    for attr_name in _ROLE_ATTR_CANDIDATES[role]:
        if not hasattr(process, attr_name):
            continue
        if first_existing_attr is None:
            first_existing_attr = attr_name
        raw_value = getattr(process, attr_name)
        # RAW (un-normalized) so callers can check ORDER + detect @compartment tags
        # instead of collapsing them.
        values = [str(item) for item in _normalize_vocab_value(raw_value)]
        if values:
            return values, attr_name, True
    if role == "substrates":
        model_subs = _model_substrate_wids(process)
        if model_subs:
            return (
                [str(item) for item in model_subs],
                "model.raw['ids']['substrate_wcm_585']",
                True,
            )
    return [], first_existing_attr, first_existing_attr is not None


def _dedupe_preserving_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _evaluate_vocab_role(
    *,
    process_name: str,
    role: str,
    expected: list[str],
    actual: list[str],
    attr_used: str | None,
    had_any_attr: bool,
) -> RoleComparison:
    # `actual` is RAW (may carry @compartment_N tags and duplicates). Detect the
    # compartment-qualified representation explicitly rather than silently collapsing it.
    has_compartment = any("@compartment" in item for item in actual)
    actual_bare = [_normalize_wid(item) for item in actual]
    missing_in_oc, extra_in_oc = _compare_vocab_sets(expected=expected, actual=actual_bare)

    if process_name == "Metabolism" and role == "substrates" and not actual:
        return RoleComparison(
            role=role, status=_STATUS_NOT_EXPOSED,
            expected_count=len(set(expected)), actual_count=0, attr_used=attr_used,
            note=(
                "OC exposes metabolism substrates through the FBA model rather than a "
                "flat 585-WID list, so a comparable flat substrate surface is not exposed."
            ),
        )

    # Species-set mismatch (or absent attr) — same as before, DIVERGE / NOT_EXPOSED.
    if missing_in_oc or extra_in_oc:
        status = _STATUS_DIVERGE
        note = None
        if not actual and expected and not had_any_attr:
            status, note = _STATUS_NOT_EXPOSED, "No OC attribute exposed this vocabulary role."
        elif not actual and expected:
            status, note = _STATUS_NOT_EXPOSED, f"Candidate OC attribute {attr_used!r} is empty."
        return RoleComparison(
            role=role, status=status, missing_in_oc=missing_in_oc, extra_in_oc=extra_in_oc,
            expected_count=len(set(expected)), actual_count=len(set(actual_bare)),
            attr_used=attr_used, note=note,
        )

    # Species set matches — now enforce ORDER (index alignment) and surface compartment
    # qualification / duplicates instead of hiding them.
    compare_list = _dedupe_preserving_order(actual_bare) if has_compartment else actual_bare
    order_ok = compare_list == expected
    has_dupes = (not has_compartment) and len(actual_bare) != len(set(actual_bare))
    notes: list[str] = []
    if has_compartment:
        notes.append(
            f"OC uses compartment-qualified WIDs ({len(actual)} entries -> "
            f"{len(compare_list)} species); compartment ASSIGNMENT is not validated by "
            "the vocab check."
        )
    if not order_ok:
        first_diff = next(
            (i for i in range(min(len(compare_list), len(expected)))
             if compare_list[i] != expected[i]),
            min(len(compare_list), len(expected)),
        )
        notes.append(
            f"ORDER/length mismatch (index alignment): first diff at position {first_diff} "
            f"(spec={expected[first_diff] if first_diff < len(expected) else '<end>'} "
            f"oc={compare_list[first_diff] if first_diff < len(compare_list) else '<end>'}); "
            f"len spec={len(expected)} oc={len(compare_list)}"
        )
    if has_dupes:
        notes.append(f"OC vocab has duplicate WIDs (len={len(actual_bare)}, unique={len(set(actual_bare))})")

    # Order/length mismatch is a real (index-alignment) DIVERGE. Compartment-qualified
    # representation with matching species+order is CONFORM-with-note (species right).
    if not order_ok:
        return RoleComparison(
            role=role, status=_STATUS_DIVERGE,
            expected_count=len(set(expected)), actual_count=len(set(actual_bare)),
            attr_used=attr_used, note=" | ".join(notes),
        )
    return RoleComparison(
        role=role, status=_STATUS_CONFORM,
        expected_count=len(set(expected)), actual_count=len(set(actual_bare)),
        attr_used=attr_used, note=" | ".join(notes) if notes else None,
    )


def _combine_statuses(statuses: Iterable[str]) -> str:
    status_set = set(statuses)
    if _STATUS_DIVERGE in status_set:
        return _STATUS_DIVERGE
    if _STATUS_NOT_EXPOSED in status_set:
        return _STATUS_NOT_EXPOSED
    return _STATUS_CONFORM


def _evaluate_vocabulary_class(
    process_name: str,
    process: object,
    spec_payload: Mapping[str, Any],
) -> ClassResult:
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
        if result.status == _STATUS_CONFORM and not result.note:
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


def _walk_surface(
    value: object,
    *,
    path: str,
    depth: int,
    leaves: dict[str, object],
    seen: set[int],
) -> None:
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


def _collect_surface_leaves(process: object) -> dict[str, object]:
    leaves: dict[str, object] = {}
    _walk_surface(process, path="", depth=2, leaves=leaves, seen=set())
    return leaves


def _find_surface_candidates(leaves: Mapping[str, Any], terminals: set[str]) -> list[tuple[str, Any]]:
    return [
        (path, value)
        for path, value in leaves.items()
        if path.rsplit(".", 1)[-1] in terminals
    ]


def _coerce_string_list(value: object) -> list[str]:
    return [str(item) for item in _normalize_vocab_value(value)]


def _coerce_matrix(value: object) -> np.ndarray | None:
    if isinstance(value, np.ndarray):
        return value
    try:
        matrix = np.asarray(value)
    except Exception:  # noqa: BLE001
        return None
    return matrix if matrix.ndim == 2 else None


def _normalize_surface_name(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _spec_reaction_ids(spec_payload: Mapping[str, Any]) -> list[str]:
    vocabularies = spec_payload.get("vocabularies") or {}
    reaction_ids = vocabularies.get("reactionWholeCellModelIDs")
    if isinstance(reaction_ids, Iterable) and not isinstance(reaction_ids, str | bytes):
        out = [str(item) for item in reaction_ids]
        if out:
            return out
    spec_species = _spec_reaction_species(spec_payload) or {}
    return list(spec_species)


def _spec_reaction_species(
    spec_payload: Mapping[str, Any],
    *,
    reaction_field: str = "reactions",
) -> dict[str, set[str]] | None:
    stoichiometry = spec_payload.get("stoichiometry") or {}
    reactions = stoichiometry.get(reaction_field)
    if not isinstance(reactions, Mapping):
        return None
    out: dict[str, set[str]] = {}
    for reaction_wid, reaction_payload in reactions.items():
        consume = reaction_payload.get("consume") or {}
        produce = reaction_payload.get("produce") or {}
        out[str(reaction_wid)] = {str(item) for item in consume} | {str(item) for item in produce}
    return out


def _spec_reaction_signed(
    spec_payload: Mapping[str, Any],
    *,
    reaction_field: str = "reactions",
) -> dict[str, dict[str, float]] | None:
    """Spec reactions as SIGNED coefficients: consumed species negative, produced
    positive, keyed by normalized species WID. Enables coefficient + sign + direction
    comparison (not just species presence)."""
    stoichiometry = spec_payload.get("stoichiometry") or {}
    reactions = stoichiometry.get(reaction_field)
    if not isinstance(reactions, Mapping):
        return None
    out: dict[str, dict[str, float]] = {}
    for reaction_wid, reaction_payload in reactions.items():
        coeffs: dict[str, float] = {}
        for species, value in (reaction_payload.get("consume") or {}).items():
            key = _normalize_wid(str(species))
            coeffs[key] = coeffs.get(key, 0.0) - float(value)
        for species, value in (reaction_payload.get("produce") or {}).items():
            key = _normalize_wid(str(species))
            coeffs[key] = coeffs.get(key, 0.0) + float(value)
        out[str(reaction_wid)] = {k: v for k, v in coeffs.items() if v != 0.0}
    return out


def _build_oc_reaction_signed_from_surface(
    *,
    matrix_value: object,
    reaction_ids: list[str],
    species_ids: list[str],
) -> dict[str, dict[str, float]] | None:
    """OC reactions as SIGNED coefficients from a [species x reactions] (or transposed)
    matrix, or a consume/produce mapping. Values kept with sign (consumed negative,
    produced positive per the stoichiometry-matrix convention)."""
    if isinstance(matrix_value, Mapping):
        out: dict[str, dict[str, float]] = {}
        for reaction_id, payload in matrix_value.items():
            coeffs: dict[str, float] = {}
            if isinstance(payload, Mapping):
                if "consume" in payload or "produce" in payload:
                    for species, value in (payload.get("consume") or {}).items():
                        key = _normalize_wid(str(species))
                        coeffs[key] = coeffs.get(key, 0.0) - float(value)
                    for species, value in (payload.get("produce") or {}).items():
                        key = _normalize_wid(str(species))
                        coeffs[key] = coeffs.get(key, 0.0) + float(value)
                else:
                    for species, value in payload.items():
                        coeffs[_normalize_wid(str(species))] = float(value)
            out[str(reaction_id)] = {k: v for k, v in coeffs.items() if v != 0.0}
        return out
    matrix = _coerce_matrix(matrix_value)
    if matrix is None or not reaction_ids or not species_ids:
        return None
    out = {}
    if matrix.shape == (len(species_ids), len(reaction_ids)):
        for j, reaction_id in enumerate(reaction_ids):
            column = matrix[:, j]
            out[reaction_id] = {
                species_ids[i]: float(column[i]) for i in np.flatnonzero(column).tolist()
            }
        return out
    if matrix.shape == (len(reaction_ids), len(species_ids)):
        for j, reaction_id in enumerate(reaction_ids):
            row = matrix[j, :]
            out[reaction_id] = {
                species_ids[i]: float(row[i]) for i in np.flatnonzero(row).tolist()
            }
        return out
    return None


def _evaluate_metabolism_fba(process: object, fixture_path: Path) -> ClassResult | None:
    """Metabolism's spec stoichiometry is a raw-matrix fingerprint (no expanded reactions
    dict), so the reaction-dict check returns N/A. But OC's Metabolism loads a Karr-native
    FBA snapshot (`model.raw['matrix_npz']`) whose matrices we CAN validate directly against
    the fixture's FBA matrices (fixture == spec == live source, via Gate 0/1). Returns a
    ClassResult if this is an FBA-model process, else None (caller falls back to N/A)."""
    model = getattr(process, "model", None)
    raw = getattr(model, "raw", None)
    if not isinstance(raw, Mapping) or "matrix_npz" not in raw:
        return None
    npz_path = REPO_ROOT / str(raw["matrix_npz"])
    if not npz_path.exists():
        return None
    npz = np.load(npz_path, allow_pickle=True)
    required_fba_keys = {"S", "lb", "ub", "obj", "enz_bounds"}
    if not required_fba_keys.issubset(set(npz.files)):
        return None  # not an FBA snapshot (e.g. Transcription's matrix_npz)
    fixture = _load_fixture(fixture_path)
    if not hasattr(fixture, "fbaReactionStoichiometryMatrix"):
        return None  # fixture carries no FBA matrices to validate against
    fba_bounds = np.asarray(fixture.fbaReactionBounds, dtype=np.float64)
    # OC npz key -> fixture FBA matrix
    pairs: list[tuple[str, np.ndarray, np.ndarray]] = [
        ("S", np.asarray(npz["S"], float), np.asarray(fixture.fbaReactionStoichiometryMatrix, float)),
        ("lb", np.asarray(npz["lb"], float), fba_bounds[:, 0]),
        ("ub", np.asarray(npz["ub"], float), fba_bounds[:, 1]),
        ("obj", np.asarray(npz["obj"], float), np.asarray(fixture.fbaObjective, float)),
        ("enz_bounds", np.asarray(npz["enz_bounds"], float), np.asarray(fixture.fbaEnzymeBounds, float)),
    ]
    if "RHS" in npz and hasattr(fixture, "fbaRightHandSide"):
        pairs.append(("RHS", np.asarray(npz["RHS"], float), np.asarray(fixture.fbaRightHandSide, float)))
    findings: list[str] = []
    for name, oc_arr, fx_arr in pairs:
        if oc_arr.shape != fx_arr.shape:
            findings.append(f"{name}: SHAPE oc={oc_arr.shape} fixture={fx_arr.shape}")
        elif not np.array_equal(oc_arr, fx_arr, equal_nan=True):
            findings.append(f"{name}: VALUE mismatch (max|diff|={float(np.nanmax(np.abs(oc_arr - fx_arr))):g})")
    if findings:
        return ClassResult(
            status=_STATUS_DIVERGE,
            details=["OC FBA matrices vs fixture FBA:", *findings],
        )
    return ClassResult(
        status=_STATUS_CONFORM,
        details=[
            "OC Karr-native FBA snapshot (model.raw['matrix_npz']) == fixture FBA matrices "
            "(S/lb/ub/obj/enz_bounds/RHS, exact); fixture == spec == source via Gate 0/1."
        ],
    )


def _build_oc_reaction_species_from_mapping(value: object) -> dict[str, set[str]] | None:
    if not isinstance(value, Mapping):
        return None
    out: dict[str, set[str]] = {}
    for reaction_id, payload in value.items():
        if isinstance(payload, Mapping):
            if "consume" in payload or "produce" in payload:
                consume = payload.get("consume") or {}
                produce = payload.get("produce") or {}
                species = {str(item) for item in consume} | {str(item) for item in produce}
            else:
                species = {str(item) for item in payload}
        else:
            species = {str(item) for item in _normalize_vocab_value(payload)}
        out[str(reaction_id)] = {_normalize_wid(species_id) for species_id in species}
    return out


def _build_oc_reaction_species(
    *,
    reaction_ids: list[str],
    substrate_ids: list[str],
    stoich_matrix: np.ndarray,
) -> dict[str, set[str]] | None:
    if not reaction_ids or not substrate_ids:
        return None
    out: dict[str, set[str]] = {}
    if stoich_matrix.shape == (len(substrate_ids), len(reaction_ids)):
        for reaction_index, reaction_id in enumerate(reaction_ids):
            column = stoich_matrix[:, reaction_index]
            out[reaction_id] = {
                substrate_ids[row_index]
                for row_index in np.flatnonzero(column).tolist()
            }
        return out
    if stoich_matrix.shape == (len(reaction_ids), len(substrate_ids)):
        for reaction_index, reaction_id in enumerate(reaction_ids):
            row = stoich_matrix[reaction_index, :]
            out[reaction_id] = {
                substrate_ids[column_index]
                for column_index in np.flatnonzero(row).tolist()
            }
        return out
    return None


def _build_oc_reaction_species_from_surface(
    *,
    matrix_value: object,
    reaction_ids: list[str],
    species_ids: list[str],
) -> dict[str, set[str]] | None:
    mapping = _build_oc_reaction_species_from_mapping(matrix_value)
    if mapping is not None:
        return mapping
    matrix = _coerce_matrix(matrix_value)
    if matrix is None:
        return None
    return _build_oc_reaction_species(
        reaction_ids=reaction_ids,
        substrate_ids=species_ids,
        stoich_matrix=matrix,
    )


def _reaction_id_candidates(
    leaves: Mapping[str, Any],
    *,
    fixture_reaction_ids: list[str],
    spec_reaction_ids: list[str],
) -> list[tuple[str, list[str]]]:
    candidates: list[tuple[str, list[str]]] = []
    for path, value in _find_surface_candidates(leaves, _STOICH_REACTION_ID_TERMINALS):
        reaction_ids = _coerce_string_list(value)
        if reaction_ids:
            candidates.append((path, reaction_ids))
    if not candidates and fixture_reaction_ids:
        candidates.append(("fixture.reactionWholeCellModelIDs(order fallback)", fixture_reaction_ids))
    if not candidates and spec_reaction_ids:
        candidates.append(("spec.vocabularies.reactionWholeCellModelIDs(order fallback)", spec_reaction_ids))
    return candidates


def _ports_schema(process: object) -> dict[str, object]:
    schema = process.ports_schema()
    return schema if isinstance(schema, dict) else {}


def _fixture_field_has_values(fixture: object, field_name: str) -> bool:
    if not hasattr(fixture, field_name):
        return False
    value = getattr(fixture, field_name)
    try:
        return np.asarray(value).size > 0
    except Exception:  # noqa: BLE001
        return False


def _reachable_states_from_ports(ports: Iterable[str]) -> set[str]:
    reachable: set[str] = set()
    for port in ports:
        normalized = _normalize_surface_name(port)
        if normalized in _IGNORED_STATE_USAGE_PORTS:
            continue
        reachable.update(_PORT_STATE_CLASSES.get(normalized, set()))
    return reachable


def _reachable_states_from_fixture(fixture: object) -> set[str]:
    reachable: set[str] = set()
    for prefix in ("substrate", "enzyme"):
        for fixture_state, state_class in _FIXTURE_LOCAL_INDEX_STATE_CLASSES.items():
            field_name = f"{prefix}{fixture_state}LocalIndexs"
            if _fixture_field_has_values(fixture, field_name):
                reachable.add(state_class)
    return reachable


def _evaluate_stoichiometry_class(
    process: object,
    spec_payload: Mapping[str, Any],
    *,
    fixture_path: Path,
) -> ClassResult:
    leaves = _collect_surface_leaves(process)
    full_matrix_candidates = _find_surface_candidates(leaves, _STOICH_FULL_MATRIX_TERMINALS)
    partial_matrix_candidates = _find_surface_candidates(leaves, _STOICH_PARTIAL_MATRIX_TERMINALS)

    selected_spec_field = "reactions"
    matrix_groups: tuple[tuple[str, list[tuple[str, Any]], list[tuple[str, Any]]], ...]
    if full_matrix_candidates:
        matrix_groups = (("reaction_stoich", full_matrix_candidates, _find_surface_candidates(leaves, _STOICH_SUBSTRATE_ID_TERMINALS)),)
    elif partial_matrix_candidates:
        selected_spec_field = "reactions_small_molecule"
        matrix_groups = (
            (
                "reaction_small_molecule_stoich",
                partial_matrix_candidates,
                _find_surface_candidates(leaves, _STOICH_SUBSTRATE_ID_TERMINALS),
            ),
        )
    else:
        matrix_groups = ()

    spec_signed = _spec_reaction_signed(spec_payload, reaction_field=selected_spec_field)
    if spec_signed is None:
        fba_result = _evaluate_metabolism_fba(process, fixture_path)
        if fba_result is not None:
            return fba_result
        return ClassResult(
            status=_STATUS_NA,
            details=["No stoichiometry section in spec (process defines no reactions)."],
        )

    spec_reaction_ids = list(spec_signed) or _spec_reaction_ids(spec_payload)
    fixture = _load_fixture(fixture_path)
    fixture_reaction_ids = _coerce_string_list(getattr(fixture, "reactionWholeCellModelIDs", []))
    reaction_id_candidates = _reaction_id_candidates(
        leaves,
        fixture_reaction_ids=fixture_reaction_ids,
        spec_reaction_ids=spec_reaction_ids,
    )

    best_signed: dict[str, dict[str, float]] = {}
    used_surfaces: list[str] = []
    aligned_surface_found = False

    for matrix_kind, matrix_candidates, species_candidates in matrix_groups:
        for reaction_path, reaction_ids in reaction_id_candidates:
            for species_path, species_value in species_candidates:
                species_ids = [_normalize_wid(item) for item in _coerce_string_list(species_value)]
                for matrix_path, matrix_value in matrix_candidates:
                    signed = _build_oc_reaction_signed_from_surface(
                        matrix_value=matrix_value,
                        reaction_ids=reaction_ids,
                        species_ids=species_ids,
                    )
                    if signed is None:
                        continue
                    aligned_surface_found = True
                    for reaction_id, reaction_coeffs in signed.items():
                        best_signed.setdefault(reaction_id, {}).update(reaction_coeffs)
                    used_surfaces.append(
                        f"{matrix_kind}:{matrix_path} reaction_ids:{reaction_path} species:{species_path}"
                    )
                    break

    if not aligned_surface_found:
        exposed_surface_parts: list[str] = []
        if full_matrix_candidates:
            exposed_surface_parts.append("reaction_stoich")
        if partial_matrix_candidates:
            exposed_surface_parts.append("reaction_small_molecule_stoich")
        if reaction_id_candidates:
            exposed_surface_parts.append("reaction_ids")
        if _find_surface_candidates(leaves, _STOICH_SUBSTRATE_ID_TERMINALS):
            exposed_surface_parts.append("substrate_ids")
        if exposed_surface_parts:
            return ClassResult(
                status=_STATUS_DIVERGE,
                details=[
                    "Unable to align exposed OC reaction surfaces: "
                    + ", ".join(exposed_surface_parts)
                ],
            )
        return ClassResult(
            status=_STATUS_NOT_EXPOSED,
            details=["OC does not expose a comparable reaction surface."],
        )

    spec_reactions = sorted(spec_signed)
    oc_reactions = sorted(best_signed)
    missing_in_oc, extra_in_oc = _compare_vocab_sets(expected=spec_reactions, actual=oc_reactions)

    shared = sorted(set(spec_signed) & set(best_signed))
    reaction_mismatches: list[str] = []
    for reaction_id in shared:
        spec_c = spec_signed[reaction_id]
        oc_c = best_signed[reaction_id]
        missing_species = sorted(set(spec_c) - set(oc_c))
        extra_species = sorted(set(oc_c) - set(spec_c))
        coeff_mismatch = [
            f"{s}(spec={spec_c[s]:g},oc={oc_c[s]:g})"
            for s in sorted(set(spec_c) & set(oc_c))
            if abs(spec_c[s] - oc_c[s]) > 1e-6 + 1e-6 * abs(spec_c[s])
        ]
        if not (missing_species or extra_species or coeff_mismatch):
            continue
        detail = f"{reaction_id}:"
        if missing_species:
            detail += f" missing_species={_preview_items(missing_species)}"
        if extra_species:
            detail += f" extra_species={_preview_items(extra_species)}"
        if coeff_mismatch:
            detail += f" coeff/sign_mismatch={_preview_items(coeff_mismatch)}"
        reaction_mismatches.append(detail)

    details: list[str] = []
    if missing_in_oc:
        details.append(f"reactions missing_in_oc={_preview_items(missing_in_oc)}")
    if extra_in_oc:
        details.append(f"reactions extra_in_oc={_preview_items(extra_in_oc)}")
    if reaction_mismatches:
        details.append("reaction_mismatches=" + _preview_items(reaction_mismatches))

    if details:
        details.append("surface=" + "; ".join(used_surfaces))
        return ClassResult(status=_STATUS_DIVERGE, details=details)

    return ClassResult(status=_STATUS_CONFORM)


def _evaluate_state_usage_class(
    process_name: str,
    process: object,
    *,
    fixture_path: Path,
    state_usage: Mapping[str, list[str]],
) -> ClassResult:
    try:
        ports = sorted(_ports_schema(process))
    except Exception as exc:  # noqa: BLE001
        return ClassResult(
            status=_STATUS_DIVERGE,
            details=[f"ports_schema() failed: {exc.__class__.__name__}: {exc}"],
        )

    fixture = _load_fixture(fixture_path)
    states_used = sorted(set(state_usage.get(process_name, [])))
    oc_reachable = sorted(
        _reachable_states_from_ports(ports) | _reachable_states_from_fixture(fixture)
    )
    missing_states = sorted(set(states_used) - set(oc_reachable))

    caveat = (
        "HEURISTIC / INFO-ONLY (does not fail the gate): the Karr-side usage is a text "
        "parse that counts writes-as-reads and misses MATLAB alias reads, and the OC-side "
        "reachability (ports + fixture LocalIndexs) does not model OC's PRIVATE fixture-state "
        "loads in __init__. So both false-positives and false-negatives are possible. Pending "
        "rework to read-only/alias-aware extraction + true OC read-surface inventory."
    )

    if not missing_states:
        return ClassResult(status=_STATUS_CONFORM, details=[caveat])

    return ClassResult(
        status=_STATUS_NOT_EXPOSED,
        details=[
            f"apparent missing_states={_preview_items(missing_states)}",
            f"states_used(parsed)={_preview_items(states_used)}",
            f"oc_reachable(inferred)={_preview_items(oc_reachable)}",
            caveat,
        ],
    )


def _significant_tokens(name: str) -> set[str]:
    return {tok.lower() for tok in _tokens(name) if len(tok) >= 3 and not tok.isdigit()}


def _oc_attribute_values(process: object) -> dict[str, object]:
    out: dict[str, object] = {}
    for attr, value in vars(process).items():
        if attr.startswith("__"):
            continue
        out[attr] = value
    return out


def _spec_constant_shape(spec_val: object) -> list[int] | None:
    if isinstance(spec_val, Mapping) and "shape" in spec_val:
        return [int(x) for x in spec_val["shape"]]
    return None


def _values_match(spec_val: object, oc_val: object) -> bool | None:
    """True/False if comparable; None if not confidently comparable."""
    shape = _spec_constant_shape(spec_val)
    if shape is not None:
        arr = _coerce_matrix(oc_val)
        if arr is None:
            oc_arr = np.asarray(oc_val)
            if oc_arr.dtype == object:
                return None
            arr = oc_arr
        oc_shape = [d for d in arr.shape]
        return sorted(d for d in oc_shape if d != 1) == sorted(d for d in shape if d != 1)
    if isinstance(spec_val, bool):
        return bool(oc_val) == spec_val if isinstance(oc_val, (bool, int)) else None
    if isinstance(spec_val, (int, float)):
        try:
            oc_num = float(np.asarray(oc_val, dtype=float).reshape(-1)[0]) if np.ndim(oc_val) else float(oc_val)
        except (TypeError, ValueError):
            return None
        return abs(float(spec_val) - oc_num) <= 1e-9 + 1e-6 * abs(float(spec_val))
    if isinstance(spec_val, str):
        return str(oc_val) == spec_val if isinstance(oc_val, (str, bytes, np.str_)) else None
    if isinstance(spec_val, list):
        oc_list = _normalize_vocab_value(oc_val)
        spec_list = [str(x) for x in spec_val]
        if oc_list and all(_looks_numeric(x) for x in spec_list):
            try:
                return np.allclose(
                    np.asarray(spec_val, dtype=float),
                    np.asarray(oc_val, dtype=float).reshape(-1),
                )
            except (TypeError, ValueError):
                return None
        return oc_list == spec_list if oc_list else None
    return None


def _looks_numeric(value: str) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def _evaluate_constants_class(
    process_name: str,
    process: object,
    spec_payload: Mapping[str, Any],
    constant_inventory: Mapping[str, list[str]],
) -> ClassResult:
    names = constant_inventory.get(process_name, [])
    params = spec_payload.get("params", {})
    if not names or not isinstance(params, Mapping):
        return ClassResult(
            status=_STATUS_NOT_EXPOSED,
            details=["No constant inventory / params available for this process."],
        )

    oc_attrs = _oc_attribute_values(process)
    oc_tokens = {attr: _significant_tokens(attr) for attr in oc_attrs}

    matched: list[str] = []
    value_mismatch: list[str] = []
    not_confirmed: list[str] = []

    for name in names:
        if name not in params:
            not_confirmed.append(name)
            continue
        spec_val = params[name]
        want = _significant_tokens(name)
        # OC attributes whose name corresponds to this constant (>=2 shared tokens,
        # or the constant's whole token set is contained in the attr's).
        corresponded = [
            attr
            for attr, toks in oc_tokens.items()
            if want and (len(want & toks) >= 2 or want <= toks)
        ]
        if not corresponded:
            not_confirmed.append(name)
            continue
        verdicts = [_values_match(spec_val, oc_attrs[attr]) for attr in corresponded]
        if any(v is True for v in verdicts):
            matched.append(name)
        elif all(v is False for v in verdicts):
            value_mismatch.append(f"{name}(oc_attrs={corresponded[:3]})")
        else:
            not_confirmed.append(name)

    details = [
        f"matched={len(matched)}/{len(names)}  "
        f"potential_mismatch={len(value_mismatch)}  not_confirmed={len(not_confirmed)}",
        "NOTE: constants VALUE fidelity is authoritatively validated by Gate 0 "
        "(spec==source) + Gate 1 (spec==fixture) + replay (behavioral). This is a "
        "best-effort static coverage layer; name-matching is fuzzy so it is INFO-only "
        "(does not fail the gate).",
    ]
    if value_mismatch:
        details.append(
            "potential value differences (name-corresponded, VERIFY MANUALLY — may be "
            f"name collisions): {value_mismatch[:8]}"
        )
    if not_confirmed:
        details.append(f"not_confirmed (no corresponding OC attr): {not_confirmed[:12]}")

    # Constants never fail the gate (fuzzy static matching); report coverage as INFO.
    if matched and not not_confirmed and not value_mismatch:
        return ClassResult(status=_STATUS_CONFORM, details=details)
    return ClassResult(status=_STATUS_NOT_EXPOSED, details=details)


def _process_spec_items(
    process_specs: Mapping[str, Any] | None,
    *,
    process_names: tuple[str, ...],
) -> list[tuple[str, Any]]:
    specs = process_specs if process_specs is not None else _load_process_specs()
    return [(process_name, specs[process_name]) for process_name in process_names]


def _matrix_lines(process_results: list[tuple[str, dict[str, ClassResult]]]) -> list[str]:
    headers = ("Process", "Vocab", "Stoich", "StateUsage", "Constants")
    rows = [
        (
            process_name,
            class_results["vocab"].status,
            class_results["stoich"].status,
            class_results["state_usage"].status,
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
            if class_result.status == _STATUS_CONFORM and not class_result.details:
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

    constant_inventory = (
        _load_constant_inventory(_CONSTANT_INVENTORY_PATH)
        if _CONSTANT_INVENTORY_PATH.exists()
        else {}
    )
    state_usage = _load_state_usage(_STATE_USAGE_PATH) if _STATE_USAGE_PATH.exists() else {}

    process_results: list[tuple[str, dict[str, ClassResult]]] = []
    construct_errors: list[str] = []

    for process_name, spec in _process_spec_items(process_specs, process_names=expected):
        spec_path = spec_dir / f"{process_name}.yaml"
        fixture_path = fixture_dir / f"{process_name}_flat.mat"
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
                        "state_usage": ClassResult(status=_STATUS_DIVERGE),
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
                        "state_usage": ClassResult(status=_STATUS_DIVERGE),
                        "constants": ClassResult(status=_STATUS_NOT_EXPOSED),
                    },
                )
            )
            continue

        class_results = {
            "vocab": _evaluate_vocabulary_class(process_name, process, spec_payload),
            "stoich": _evaluate_stoichiometry_class(
                process,
                spec_payload,
                fixture_path=fixture_path,
            ),
            "state_usage": _evaluate_state_usage_class(
                process_name,
                process,
                fixture_path=fixture_path,
                state_usage=state_usage,
            ),
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
    na_cells = sum(
        class_result.status == _STATUS_NA
        for _, class_results in process_results
        for class_result in class_results.values()
    )

    if construct_errors:
        details.extend(f"construct_error: {item}" for item in construct_errors)

    summary = (
        f"GATE 2 (OC vs spec): {'FAIL' if diverge_cells else 'PASS'} — "
        f"diverge_cells={diverge_cells}, not_exposed_cells={not_exposed_cells}, "
        f"na_cells={na_cells}, processes={len(expected)}"
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
