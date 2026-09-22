"""Source-faithful port of Karr's compartmented ProteinActivation process."""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/ProteinActivation_flat.mat"
_DEFAULT_MONOMER_FIXTURE_PATH = "data/karr_fixtures/per_process/ProteinMonomer_flat.mat"
_DEFAULT_COMPLEX_FIXTURE_PATH = "data/karr_fixtures/per_process/ProteinComplex_flat.mat"
_DEFAULT_GEOMETRY_FIXTURE_PATH = "data/karr_fixtures/per_process/CellGeometry_flat.mat"

# Karr ConstantUtil.nAvogadro, used verbatim by ProteinActivation.m.
_KARR_N_AVOGADRO = 6.0221417930e23

_ACTIVE_NONCYTOSOL_COUNTS = "activation_active_noncytosol_counts"
_INACTIVE_COUNTS = "activation_inactive_counts"
_REGULATED_PROTEINS = (
    "MG_085_HEXAMER",
    "MG_101_MONOMER",
    "MG_127_MONOMER",
    "MG_205_DIMER",
    "MG_236_MONOMER",
    "MG_409_DIMER",
)


def _resolve_fixture_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate

    repo_root = Path(__file__).resolve().parents[2]
    rooted = repo_root / candidate
    if rooted.exists():
        return rooted

    raise FileNotFoundError(f"Fixture not found: {path}")


def _load_fixture(path: str | Path) -> Any:
    resolved = _resolve_fixture_path(path)
    return loadmat(str(resolved), squeeze_me=True, struct_as_record=False)["data"].fixture


def _coerce_scalar(value: object) -> object:
    out = value
    while isinstance(out, np.ndarray):
        if out.size == 0:
            return ""
        out = out.flat[0]
    return out


def _parse_wid_array(cell_array: np.ndarray) -> list[str]:
    values = np.asarray(cell_array, dtype=object)
    return [str(_coerce_scalar(raw)) for raw in values.ravel()]


def _sanitize_rule_text(rule: str) -> str:
    text = rule.strip()
    text = text.replace("&&", "&").replace("||", "|")
    text = text.replace("~", " not ")
    text = text.replace("&", " and ").replace("|", " or ")
    return re.sub(r"\s+", " ", text).strip()


def _assert_rule_ast_is_safe(tree: ast.AST) -> None:
    allowed = (
        ast.Expression,
        ast.BoolOp,
        ast.UnaryOp,
        ast.BinOp,
        ast.Compare,
        ast.Name,
        ast.Load,
        ast.Constant,
        ast.And,
        ast.Or,
        ast.Not,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Mod,
        ast.USub,
        ast.UAdd,
        ast.Gt,
        ast.GtE,
        ast.Lt,
        ast.LtE,
        ast.Eq,
        ast.NotEq,
    )
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise ValueError(f"Unsupported activation rule syntax: {type(node).__name__}")


def _compile_rule(raw_rule: object) -> tuple[Callable[[dict[str, float]], bool], str, set[str]]:
    rule = _coerce_scalar(raw_rule)

    if callable(rule):
        return (lambda signals, fn=rule: bool(fn(signals))), "<callable-rule>", set()
    if not isinstance(rule, str):
        raise TypeError(f"Unsupported activation rule type: {type(rule).__name__}")

    normalized = _sanitize_rule_text(rule)
    tree = ast.parse(normalized, mode="eval")
    _assert_rule_ast_is_safe(tree)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    code = compile(tree, "<protein-activation-rule>", "eval")

    def _rule_eval(signals: dict[str, float]) -> bool:
        namespace = {name: float(signals[name]) for name in names}
        return bool(eval(code, {"__builtins__": {}}, namespace))  # noqa: S307 - guarded AST

    return _rule_eval, rule, names


def _one_based_indices(values: object) -> np.ndarray:
    return np.asarray(values, dtype=np.int64).reshape(-1) - 1


def _matrix_indices(values: object) -> np.ndarray:
    return np.asarray(values, dtype=np.int64) - 1


def _require_mapping(states: Mapping[str, Any], key: str, path: str) -> Mapping[str, Any]:
    if key not in states:
        raise KeyError(f"ProteinActivation missing required state key '{path}'")
    value = states[key]
    if not isinstance(value, Mapping):
        raise TypeError(f"ProteinActivation state '{path}' must be a mapping")
    return value


def _require_float(states: Mapping[str, Any], key: str, path: str) -> float:
    if key not in states:
        raise KeyError(f"ProteinActivation missing required state key '{path}'")
    value = float(states[key])
    if not np.isfinite(value):
        raise ValueError(f"ProteinActivation state '{path}' must be finite")
    return value


class KarrProteinActivationProcess(Process):
    """Karr Process_ProteinActivation with shared compartmented protein state.

    Representation
    --------------
    The existing flat ``protein.counts`` and ``complex.counts`` leaves remain
    the active-count authority for fixture compartment 0, so every sibling
    consumer reads the same molecules ProteinActivation transfers. Active
    counts for compartments 1-5 and inactive counts for all six compartments
    live under dedicated branches of those same shared roots. No process-local
    active/inactive matrix is persisted.

    Inputs
    ------
    ``stimuli`` contains the extracellular signal vector and ``geometry``
    supplies the live cell volume. True stimulus rows remain raw. Every other
    row is converted from molecule count to mM with Karr's Avogadro constant
    before rule evaluation.

    Outputs
    -------
    Each nonempty (protein, compartment) tuple is transferred completely to
    either active or inactive state. ``protein.activity`` is emitted only as a
    compatibility projection from the resulting active matrix.

    Initialization
    --------------
    Canonical defaults are cross-validated against ProteinMonomer and
    ProteinComplex mature/inactivated indices. Missing production state keys
    fail explicitly rather than falling back to zero.

    The same representation is used by direct process calls and Vivarium.
    """

    name = "karr_protein_activation"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "protein_monomer_fixture_path": _DEFAULT_MONOMER_FIXTURE_PATH,
        "protein_complex_fixture_path": _DEFAULT_COMPLEX_FIXTURE_PATH,
        "geometry_fixture_path": _DEFAULT_GEOMETRY_FIXTURE_PATH,
        "time_step": 1.0,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        _initialize_process(self)

    def canonical_state(self) -> dict[str, Any]:
        return _canonical_state(self)

    def state_matrices(self, states: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray]:
        return _state_matrices(self, states)

    def converted_signals(self, states: Mapping[str, Any]) -> dict[str, float]:
        return _converted_signals(self, states)

    def ports_schema(self) -> dict[str, Any]:
        return _ports_schema(self)

    def evaluate_activation_rules(self, states: Mapping[str, Any]) -> np.ndarray:
        active, inactive = self.state_matrices(states)
        return self._evaluate_from_matrices(
            active=active,
            inactive=inactive,
            signals=self._collect_rule_signals(states),
        )

    def canonical_total_matrix(self) -> np.ndarray:
        return self.canonical_active + self.canonical_inactive

    def _collect_rule_signals(self, states: Mapping[str, Any]) -> dict[str, float]:
        """Read required live inputs and apply Karr's count-to-mM conversion."""
        return self.converted_signals(states)

    def _evaluate_from_matrices(
        self,
        *,
        active: np.ndarray,
        inactive: np.ndarray,
        signals: dict[str, float],
    ) -> np.ndarray:
        return _evaluate_from_matrices(
            self,
            active=active,
            inactive=inactive,
            signals=signals,
        )

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del timestep
        return _next_update(self, states)


def _initialize_process(process: KarrProteinActivationProcess) -> None:
    fixture = _load_fixture(process.parameters["fixture_path"])
    monomer_fixture = _load_fixture(process.parameters["protein_monomer_fixture_path"])
    complex_fixture = _load_fixture(process.parameters["protein_complex_fixture_path"])
    geometry_fixture = _load_fixture(process.parameters["geometry_fixture_path"])

    process.substrate_wids = _parse_wid_array(fixture.substrateWholeCellModelIDs)
    process.stimuli_wids = _parse_wid_array(fixture.stimuliWholeCellModelIDs)
    process.enzyme_wids = _parse_wid_array(fixture.enzymeWholeCellModelIDs)
    process._stimuli_wid_set = set(process.stimuli_wids)

    fixture_active = np.asarray(fixture.substrates, dtype=np.float64)
    fixture_inactive = np.asarray(fixture.inactivatedSubstrates, dtype=np.float64)
    if fixture_active.ndim != 2 or fixture_inactive.shape != fixture_active.shape:
        raise ValueError(
            "ProteinActivation fixture active/inactive state must be equal 2D matrices"
        )
    if fixture_active.shape[0] != len(process.substrate_wids):
        raise ValueError("ProteinActivation substrate rows do not match WID count")

    process.compartment_count = int(fixture_active.shape[1])
    process.compartment_keys = tuple(
        str(index) for index in range(process.compartment_count)
    )
    process.shared_flat_compartment_index = 0
    process.shared_flat_compartment_key = process.compartment_keys[0]

    raw_stimulus_rows = _one_based_indices(fixture.stimulusStimulusLocalIndexs)
    if np.any(raw_stimulus_rows < 0) or np.any(
        raw_stimulus_rows >= len(process.stimuli_wids)
    ):
        raise ValueError("ProteinActivation fixture has invalid true-stimulus indices")
    process.true_stimulus_wids = frozenset(
        process.stimuli_wids[int(index)] for index in raw_stimulus_rows
    )

    fixture_stimuli = np.asarray(fixture.stimuli, dtype=np.float64)
    if fixture_stimuli.shape != (
        len(process.stimuli_wids),
        process.compartment_count,
    ):
        raise ValueError("ProteinActivation fixture stimuli shape is inconsistent")
    raw_nonzero_columns = np.flatnonzero(
        np.any(fixture_stimuli[raw_stimulus_rows, :] != 0.0, axis=0)
    )
    if raw_nonzero_columns.size != 1:
        raise ValueError(
            "ProteinActivation cannot identify one extracellular fixture column "
            "from true-stimulus values"
        )
    process.extracellular_compartment_index = int(raw_nonzero_columns[0])
    process.default_stimuli = {
        wid: float(fixture_stimuli[index, process.extracellular_compartment_index])
        for index, wid in enumerate(process.stimuli_wids)
    }

    process.default_geometry_volume = float(_coerce_scalar(geometry_fixture.volume))
    if (
        not np.isfinite(process.default_geometry_volume)
        or process.default_geometry_volume <= 0.0
    ):
        raise ValueError("ProteinActivation CellGeometry fixture volume must be positive")

    monomer_local = _one_based_indices(fixture.substrateMonomerLocalIndexs)
    monomer_global = _matrix_indices(fixture.substrateMonomerGlobalIndexs)
    monomer_compartments = np.asarray(
        fixture.substrateMonomerCompartmentIndexs, dtype=np.int64
    )
    complex_local = _one_based_indices(fixture.substrateComplexLocalIndexs)
    complex_global = _matrix_indices(fixture.substrateComplexGlobalIndexs)
    complex_compartments = np.asarray(
        fixture.substrateComplexCompartmentIndexs, dtype=np.int64
    )

    expected_compartments = np.arange(
        1, process.compartment_count + 1, dtype=np.int64
    )
    process.store_by_wid = {}
    for local_index, global_row, compartments in zip(
        monomer_local, monomer_global, monomer_compartments, strict=True
    ):
        _validate_index_row(
            kind="monomer",
            global_row=global_row,
            compartments=compartments,
            expected_compartments=expected_compartments,
        )
        process.store_by_wid[process.substrate_wids[int(local_index)]] = "protein"
    for local_index, global_row, compartments in zip(
        complex_local, complex_global, complex_compartments, strict=True
    ):
        _validate_index_row(
            kind="complex",
            global_row=global_row,
            compartments=compartments,
            expected_compartments=expected_compartments,
        )
        process.store_by_wid[process.substrate_wids[int(local_index)]] = "complex"

    _validate_canonical_state_projection(
        process=process,
        fixture_active=fixture_active,
        fixture_inactive=fixture_inactive,
        monomer_fixture=monomer_fixture,
        complex_fixture=complex_fixture,
        monomer_local=monomer_local,
        monomer_global=monomer_global,
        complex_local=complex_local,
        complex_global=complex_global,
    )

    process.regulated_protein_wids = [
        wid for wid in _REGULATED_PROTEINS if wid in process.substrate_wids
    ]
    if len(process.regulated_protein_wids) != len(_REGULATED_PROTEINS):
        missing = sorted(
            set(_REGULATED_PROTEINS) - set(process.regulated_protein_wids)
        )
        raise ValueError(f"Missing regulated proteins in fixture: {missing}")
    process.regulated_fixture_rows = np.asarray(
        [process.substrate_wids.index(wid) for wid in process.regulated_protein_wids],
        dtype=np.int64,
    )
    process.canonical_active = fixture_active[
        process.regulated_fixture_rows, :
    ].copy()
    process.canonical_inactive = fixture_inactive[
        process.regulated_fixture_rows, :
    ].copy()
    if np.any(process.canonical_active[:, 1:] != 0.0) or np.any(
        process.canonical_inactive[:, 1:] != 0.0
    ):
        raise ValueError(
            "ProteinActivation canonical regulated state cannot share the flat "
            "compartment-0 count leaves without duplication"
        )

    raw_rules = np.asarray(fixture.activationRules, dtype=object).ravel().tolist()
    if len(raw_rules) != len(process.substrate_wids):
        raise ValueError(
            "ProteinActivation fixture mismatch: "
            f"{len(raw_rules)} rules for {len(process.substrate_wids)} substrates"
        )

    process.rule_strings = {}
    process.rules = {}
    rule_by_wid = {
        wid: raw_rules[index] for index, wid in enumerate(process.substrate_wids)
    }
    referenced: set[str] = set()
    for wid in process.regulated_protein_wids:
        compiled, source, names = _compile_rule(rule_by_wid[wid])
        process.rules[wid] = compiled
        process.rule_strings[wid] = source
        referenced.update(names)

    unknown_names = referenced - process._stimuli_wid_set
    if unknown_names:
        raise ValueError(
            f"Activation rule references unknown signals: {sorted(unknown_names)}"
        )
    process._referenced_names = sorted(referenced)


def _validate_index_row(
    *,
    kind: str,
    global_row: np.ndarray,
    compartments: np.ndarray,
    expected_compartments: np.ndarray,
) -> None:
    if not np.array_equal(compartments, expected_compartments):
        raise ValueError(f"ProteinActivation {kind} compartment mapping is incomplete")
    if not np.all(global_row == global_row[0]):
        raise ValueError(
            f"ProteinActivation {kind} global index varies by compartment"
        )


def _validate_canonical_state_projection(
    *,
    process: KarrProteinActivationProcess,
    fixture_active: np.ndarray,
    fixture_inactive: np.ndarray,
    monomer_fixture: Any,
    complex_fixture: Any,
    monomer_local: np.ndarray,
    monomer_global: np.ndarray,
    complex_local: np.ndarray,
    complex_global: np.ndarray,
) -> None:
    monomer_counts = np.asarray(monomer_fixture.counts, dtype=np.float64)
    monomer_mature = _one_based_indices(monomer_fixture.matureIndexs)
    monomer_inactive = _one_based_indices(monomer_fixture.inactivatedIndexs)
    complex_counts = np.asarray(complex_fixture.counts, dtype=np.float64)
    complex_mature = _one_based_indices(complex_fixture.matureIndexs)
    complex_inactive = _one_based_indices(complex_fixture.inactivatedIndexs)

    _validate_store_projection(
        process=process,
        fixture_active=fixture_active,
        fixture_inactive=fixture_inactive,
        local_indices=monomer_local,
        global_indices=monomer_global,
        counts=monomer_counts,
        mature_indices=monomer_mature,
        inactive_indices=monomer_inactive,
        kind="monomer",
    )
    _validate_store_projection(
        process=process,
        fixture_active=fixture_active,
        fixture_inactive=fixture_inactive,
        local_indices=complex_local,
        global_indices=complex_global,
        counts=complex_counts,
        mature_indices=complex_mature,
        inactive_indices=complex_inactive,
        kind="complex",
    )


def _validate_store_projection(
    *,
    process: KarrProteinActivationProcess,
    fixture_active: np.ndarray,
    fixture_inactive: np.ndarray,
    local_indices: np.ndarray,
    global_indices: np.ndarray,
    counts: np.ndarray,
    mature_indices: np.ndarray,
    inactive_indices: np.ndarray,
    kind: str,
) -> None:
    for local_index, global_row in zip(
        local_indices, global_indices, strict=True
    ):
        global_index = int(global_row[0])
        active = counts[int(mature_indices[global_index]), :]
        inactive = counts[int(inactive_indices[global_index]), :]
        if not np.array_equal(
            active, fixture_active[int(local_index), :]
        ) or not np.array_equal(inactive, fixture_inactive[int(local_index), :]):
            raise ValueError(
                f"ProteinActivation {kind} state mismatch for "
                f"{process.substrate_wids[int(local_index)]}"
            )


def _state_branch_schema(
    process: KarrProteinActivationProcess,
    store_name: str,
) -> dict[str, Any]:
    wids = [
        wid
        for wid in process.regulated_protein_wids
        if process.store_by_wid[wid] == store_name
    ]
    return {
        "counts": {
            wid: {
                "_default": float(
                    process.canonical_active[
                        process.regulated_protein_wids.index(wid), 0
                    ]
                ),
                "_updater": "accumulate",
                "_emit": False,
            }
            for wid in wids
        },
        _ACTIVE_NONCYTOSOL_COUNTS: {
            wid: {
                process.compartment_keys[compartment]: {
                    "_default": float(
                        process.canonical_active[
                            process.regulated_protein_wids.index(wid), compartment
                        ]
                    ),
                    "_updater": "accumulate",
                    "_emit": False,
                }
                for compartment in range(1, process.compartment_count)
            }
            for wid in wids
        },
        _INACTIVE_COUNTS: {
            wid: {
                process.compartment_keys[compartment]: {
                    "_default": float(
                        process.canonical_inactive[
                            process.regulated_protein_wids.index(wid), compartment
                        ]
                    ),
                    "_updater": "accumulate",
                    "_emit": False,
                }
                for compartment in range(process.compartment_count)
            }
            for wid in wids
        },
    }


def _ports_schema(process: KarrProteinActivationProcess) -> dict[str, Any]:
    protein_schema = _state_branch_schema(process, "protein")
    protein_schema["activity"] = {
        wid: {
            "_default": int(np.any(process.canonical_active[index, :] != 0.0)),
            "_updater": "set",
            "_emit": True,
        }
        for index, wid in enumerate(process.regulated_protein_wids)
    }
    return {
        "protein": protein_schema,
        "complex": _state_branch_schema(process, "complex"),
        "stimuli": {
            wid: {
                "_default": float(process.default_stimuli[wid]),
                "_updater": "set",
                "_emit": False,
            }
            for wid in process.stimuli_wids
        },
        "geometry": {
            "volume": {
                "_default": process.default_geometry_volume,
                "_updater": "set",
                "_emit": False,
            }
        },
    }


def _canonical_state(process: KarrProteinActivationProcess) -> dict[str, Any]:
    state: dict[str, Any] = {
        "protein": {
            "counts": {},
            _ACTIVE_NONCYTOSOL_COUNTS: {},
            _INACTIVE_COUNTS: {},
            "activity": {},
        },
        "complex": {
            "counts": {},
            _ACTIVE_NONCYTOSOL_COUNTS: {},
            _INACTIVE_COUNTS: {},
        },
        "stimuli": dict(process.default_stimuli),
        "geometry": {"volume": process.default_geometry_volume},
    }
    for index, wid in enumerate(process.regulated_protein_wids):
        store = state[process.store_by_wid[wid]]
        store["counts"][wid] = float(process.canonical_active[index, 0])
        store[_ACTIVE_NONCYTOSOL_COUNTS][wid] = {
            process.compartment_keys[compartment]: float(
                process.canonical_active[index, compartment]
            )
            for compartment in range(1, process.compartment_count)
        }
        store[_INACTIVE_COUNTS][wid] = {
            process.compartment_keys[compartment]: float(
                process.canonical_inactive[index, compartment]
            )
            for compartment in range(process.compartment_count)
        }
        state["protein"]["activity"][wid] = int(
            np.any(process.canonical_active[index, :] != 0.0)
        )
    return state


def _state_matrices(
    process: KarrProteinActivationProcess,
    states: Mapping[str, Any],
) -> tuple[np.ndarray, np.ndarray]:
    active = np.zeros(
        (len(process.regulated_protein_wids), process.compartment_count),
        dtype=np.float64,
    )
    inactive = np.zeros_like(active)

    for row, wid in enumerate(process.regulated_protein_wids):
        store_name = process.store_by_wid[wid]
        store = _require_mapping(states, store_name, store_name)
        counts = _require_mapping(store, "counts", f"{store_name}.counts")
        active[row, 0] = _require_float(
            counts, wid, f"{store_name}.counts.{wid}"
        )

        noncytosol = _require_mapping(
            store,
            _ACTIVE_NONCYTOSOL_COUNTS,
            f"{store_name}.{_ACTIVE_NONCYTOSOL_COUNTS}",
        )
        wid_noncytosol = _require_mapping(
            noncytosol,
            wid,
            f"{store_name}.{_ACTIVE_NONCYTOSOL_COUNTS}.{wid}",
        )
        for compartment in range(1, process.compartment_count):
            key = process.compartment_keys[compartment]
            active[row, compartment] = _require_float(
                wid_noncytosol,
                key,
                f"{store_name}.{_ACTIVE_NONCYTOSOL_COUNTS}.{wid}.{key}",
            )

        inactive_store = _require_mapping(
            store,
            _INACTIVE_COUNTS,
            f"{store_name}.{_INACTIVE_COUNTS}",
        )
        wid_inactive = _require_mapping(
            inactive_store,
            wid,
            f"{store_name}.{_INACTIVE_COUNTS}.{wid}",
        )
        for compartment, key in enumerate(process.compartment_keys):
            inactive[row, compartment] = _require_float(
                wid_inactive,
                key,
                f"{store_name}.{_INACTIVE_COUNTS}.{wid}.{key}",
            )

    if np.any(active < 0.0) or np.any(inactive < 0.0):
        raise ValueError("ProteinActivation active/inactive counts must be nonnegative")
    return active, inactive


def _converted_signals(
    process: KarrProteinActivationProcess,
    states: Mapping[str, Any],
) -> dict[str, float]:
    stimuli = _require_mapping(states, "stimuli", "stimuli")
    geometry = _require_mapping(states, "geometry", "geometry")
    volume = _require_float(geometry, "volume", "geometry.volume")
    if volume <= 0.0:
        raise ValueError("ProteinActivation geometry.volume must be positive")

    signals: dict[str, float] = {}
    for wid in process.stimuli_wids:
        value = _require_float(stimuli, wid, f"stimuli.{wid}")
        if wid in process.true_stimulus_wids:
            signals[wid] = value
        else:
            signals[wid] = value / (_KARR_N_AVOGADRO / 1000.0) / volume
    return signals


def _evaluate_from_matrices(
    process: KarrProteinActivationProcess,
    *,
    active: np.ndarray,
    inactive: np.ndarray,
    signals: dict[str, float],
) -> np.ndarray:
    activated = np.zeros_like(active, dtype=bool)
    for compartment in range(process.compartment_count):
        for row, wid in enumerate(process.regulated_protein_wids):
            if active[row, compartment] == 0.0 and inactive[row, compartment] == 0.0:
                continue
            activated[row, compartment] = process.rules[wid](signals)
    return activated


def _write_count_delta(
    process: KarrProteinActivationProcess,
    update: dict[str, Any],
    *,
    store_name: str,
    wid: str,
    compartment: int,
    active_delta: float,
    inactive_delta: float,
) -> None:
    store_update = update.setdefault(store_name, {})
    if active_delta != 0.0:
        if compartment == process.shared_flat_compartment_index:
            store_update.setdefault("counts", {})[wid] = active_delta
        else:
            store_update.setdefault(_ACTIVE_NONCYTOSOL_COUNTS, {}).setdefault(
                wid, {}
            )[process.compartment_keys[compartment]] = active_delta
    if inactive_delta != 0.0:
        store_update.setdefault(_INACTIVE_COUNTS, {}).setdefault(wid, {})[
            process.compartment_keys[compartment]
        ] = inactive_delta


def _next_update(
    process: KarrProteinActivationProcess,
    states: dict[str, Any],
) -> dict[str, Any]:
    active, inactive = process.state_matrices(states)
    activated = process._evaluate_from_matrices(
        active=active,
        inactive=inactive,
        signals=process._collect_rule_signals(states),
    )

    active_after = np.where(activated, active + inactive, 0.0)
    inactive_after = np.where(activated, 0.0, active + inactive)
    active_delta = active_after - active
    inactive_delta = inactive_after - inactive

    update: dict[str, Any] = {
        "protein": {
            "activity": {
                wid: int(np.any(active_after[row, :] != 0.0))
                for row, wid in enumerate(process.regulated_protein_wids)
            }
        }
    }
    for row, wid in enumerate(process.regulated_protein_wids):
        store_name = process.store_by_wid[wid]
        for compartment in range(process.compartment_count):
            _write_count_delta(
                process,
                update,
                store_name=store_name,
                wid=wid,
                compartment=compartment,
                active_delta=float(active_delta[row, compartment]),
                inactive_delta=float(inactive_delta[row, compartment]),
            )
    return update


__all__ = ["KarrProteinActivationProcess"]
