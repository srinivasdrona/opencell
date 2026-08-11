from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_TESTS_DIR = _REPO_ROOT / "tests" / "vivarium"
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

from _l2_2_design_a_runner_helpers import _chromosome_projection_component  # type: ignore
from l2_2_replay_common_v2 import (  # type: ignore
    _PROCESS_SPECS,
    _build_context,
    _inject_hidden_read_surface,
    _project_trace_vector,
)
from l2_replay_common import (  # type: ignore
    apply_count_update,
    build_state_template,
    collect_count_delta_dicts,
    overlay_observable_into_state,
    project_observable_from_state,
    refresh_allocator_views,
)
from opencell.state.chromosome_store import ChromosomeStore, _read_matlab_dataset


TARGET_PROCESSES = (
    "DNARepair",
    "Metabolism",
    "ProteinDecay",
    "Replication",
    "TranscriptionalRegulation",
    "ChromosomeSegregation",
    "Cytokinesis",
    "DNADamage",
    "HostInteraction",
    "RNAModification",
    "RibosomeAssembly",
)

CLASS_EXISTING_WINDOW_PASS = "EXISTING_WINDOW_PASS"
CLASS_CODE_GAP = "CODE_GAP"
CLASS_MISSING_ACTIVE_EXTRACTION = "MISSING_ACTIVE_EXTRACTION"

COUNT_STORE_KEYS = frozenset(
    {
        "substrates",
        "protein",
        "rna",
        "complex",
        "boundEnzymes",
        "enzymes",
    }
)
IGNORED_UPDATE_KEYS = frozenset({"requests", "substrates_allocated"})

STANDARD_MANIFEST_PATH = _REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "oracle_population_manifest.json"
CYTOKINESIS_EVENT_MANIFEST = (
    _REPO_ROOT / "docs" / "phase_f" / "l2_event" / "evidence_bundle" / "Cytokinesis" / "input_manifest.json"
)
RIBOSOME_EVENT_MANIFEST = (
    _REPO_ROOT / "docs" / "phase_f" / "l2_event" / "evidence_bundle" / "RibosomeAssembly" / "input_manifest.json"
)

DIRECT_SPECIAL_TRACES: dict[str, tuple[Path, ...]] = {
    "RNAModification": (
        Path("/mnt/e/opencell/data/m1_sources/karr_native/per_process_traces_v2_event_s000/RNAModification_100ticks.mat"),
    ),
    "DNADamage": (
        Path("/mnt/e/opencell/data/m1_sources/karr_native/per_process_traces_v2/DNADamage_100ticks.mat"),
        Path("/mnt/e/opencell/data/m1_sources/karr_native/dnadamage_fullcycle/DNADamage_32400ticks.mat"),
    ),
}

CHROMOSOME_ACTIVITY_TOKENS: dict[str, tuple[str, ...]] = {
    "DNARepair": (
        "repair_event_present",
        "damagedBases.delta_nnz",
        "strandBreaks.delta_nnz",
        "gapSites.delta_nnz",
        "abasicSites.delta_nnz",
        "damagedSugarPhosphates.delta_nnz",
    ),
    "Replication": (
        "polymerizedRegions.delta_value_sum_strand_1",
        "polymerizedRegions.delta_value_sum_strand_2",
        "polymerizedRegions.delta_value_sum_strand_3",
        "polymerizedRegions.delta_value_sum_strand_4",
        "polymerizedRegions.delta_nnz",
    ),
    "DNADamage": (
        "repair_event_present",
        "damagedBases.delta_nnz",
        "abasicSites.delta_nnz",
        "strandBreaks.delta_nnz",
        "damagedSugarPhosphates.delta_nnz",
        "intrastrandCrossLinks.delta_nnz",
        "gapSites.delta_nnz",
    ),
}

CUSTOM_ACTIVITY_OBSERVABLES: dict[str, tuple[str, ...]] = {
    "Cytokinesis": (
        "chromosome_segregated",
        "pinchedDiameter",
        "ftsZRing_numEdgesOneStraight",
        "ftsZRing_numEdgesTwoStraight",
        "ftsZRing_numEdgesTwoBent",
        "ftsZRing_numResidualBent",
        "substrates",
    ),
    "RibosomeAssembly": ("complexs", "RNAs", "monomers", "substrates"),
}

CUSTOM_COMPARE_OBSERVABLES: dict[str, tuple[str, ...]] = {
    "Cytokinesis": (
        "pinchedDiameter",
        "ftsZRing_numEdgesOneStraight",
        "ftsZRing_numEdgesTwoStraight",
        "ftsZRing_numEdgesTwoBent",
        "ftsZRing_numResidualBent",
    ),
    "RibosomeAssembly": ("RNAs",),
}

CUSTOM_VECTOR_SURFACES: dict[str, dict[str, tuple[str, ...]]] = {
    "Cytokinesis": {
        "chromosome_segregated": ("chromosome", "segregated"),
        "pinchedDiameter": ("geometry", "pinchedDiameter"),
        "ftsZRing_numEdgesOneStraight": ("ftsZRing", "numEdgesOneStraight"),
        "ftsZRing_numEdgesTwoStraight": ("ftsZRing", "numEdgesTwoStraight"),
        "ftsZRing_numEdgesTwoBent": ("ftsZRing", "numEdgesTwoBent"),
        "ftsZRing_numResidualBent": ("ftsZRing", "numResidualBent"),
    },
    "RibosomeAssembly": {
        "RNAs": ("rna", "counts"),
    },
}

CUSTOM_WID_ATTRS: dict[str, dict[str, str]] = {
    "RibosomeAssembly": {
        "RNAs": "rna_subunit_wids",
    },
}

PROCESS_ACTIVITY_PREDICATE_TEXT: dict[str, str] = {
    "DNARepair": "chromosome primary_projection repair_event_present + damage-field delta_nnz",
    "Metabolism": "substrates delta on projected Karr replay surface",
    "ProteinDecay": "substrates/monomers/complexs delta on projected Karr replay surface",
    "Replication": "chromosome primary_projection polymerizedRegions delta_value_sum_strand_1..4 + delta_nnz",
    "TranscriptionalRegulation": "projected Karr replay observables delta on accepted trace surface",
    "ChromosomeSegregation": "projected Karr replay observables delta on accepted trace surface",
    "Cytokinesis": "event-window scalar deltas: chromosome_segregated/pinchedDiameter/ftsZ ring channels",
    "DNADamage": "chromosome primary_projection damage-field delta_nnz",
    "HostInteraction": "projected Karr replay observables delta on accepted trace surface",
    "RNAModification": "modifiedRNAs/unmodifiedRNAs projected delta on event-window trace",
    "RibosomeAssembly": "complexs/RNAs/monomers projected delta on event-window trace",
}

SPECIAL_FIRST_PROCESSES = frozenset({"Cytokinesis", "RNAModification", "RibosomeAssembly"})


@dataclass(frozen=True)
class ProcessConfig:
    process_name: str
    missing_extraction_request: str


PROCESS_CONFIGS: dict[str, ProcessConfig] = {
    "DNARepair": ProcessConfig(
        process_name="DNARepair",
        missing_extraction_request=(
            "No new extraction requested unless every canonical per_process_traces_v2 seed stays inactive; "
            "preferred next source remains the existing standard seeded cohort."
        ),
    ),
    "Metabolism": ProcessConfig(
        process_name="Metabolism",
        missing_extraction_request=(
            "No new extraction requested unless every canonical per_process_traces_v2 seed stays inactive; "
            "preferred next source remains the existing standard seeded cohort."
        ),
    ),
    "ProteinDecay": ProcessConfig(
        process_name="ProteinDecay",
        missing_extraction_request=(
            "If all canonical standard seeds remain inactive, request a later-life-cycle per_process_traces_v2 "
            "window for ProteinDecay before any new MATLAB sweep."
        ),
    ),
    "Replication": ProcessConfig(
        process_name="Replication",
        missing_extraction_request=(
            "No new extraction requested unless every canonical per_process_traces_v2 seed stays inactive; "
            "preferred next source remains the existing standard seeded cohort."
        ),
    ),
    "TranscriptionalRegulation": ProcessConfig(
        process_name="TranscriptionalRegulation",
        missing_extraction_request=(
            "If all canonical standard seeds remain inactive, request the earliest non-trivial "
            "per_process_traces_v2 seed for TranscriptionalRegulation."
        ),
    ),
    "ChromosomeSegregation": ProcessConfig(
        process_name="ChromosomeSegregation",
        missing_extraction_request=(
            "Request a late-cell-cycle active ChromosomeSegregation window; the canonical birth-window "
            "cohort remains inactive."
        ),
    ),
    "Cytokinesis": ProcessConfig(
        process_name="Cytokinesis",
        missing_extraction_request=(
            "Request Cytokinesis event windows for seeds 1-49 only after the authorized cohort-wide "
            "onset-span survey; seed 0 already exists."
        ),
    ),
    "DNADamage": ProcessConfig(
        process_name="DNADamage",
        missing_extraction_request=(
            "Request a source-backed stimulus-conditioned DNADamage active window "
            "(UVB_radiation or gamma_radiation); existing standard/full-cycle traces are no-stimulus."
        ),
    ),
    "HostInteraction": ProcessConfig(
        process_name="HostInteraction",
        missing_extraction_request=(
            "Request a host-conditioned HostInteraction active window; baseline no-host traces are inactive "
            "by construction."
        ),
    ),
    "RNAModification": ProcessConfig(
        process_name="RNAModification",
        missing_extraction_request=(
            "Reuse the existing RNAModification event-window seed if present; otherwise request the same "
            "tick_offset burn-in window."
        ),
    ),
    "RibosomeAssembly": ProcessConfig(
        process_name="RibosomeAssembly",
        missing_extraction_request=(
            "Reuse the existing RibosomeAssembly 50-seed event-window cohort if present; otherwise request "
            "the same tick_offset=200 event-window batch."
        ),
    ),
}


@dataclass
class TraceDiffDetail:
    observable: str
    detail_path: str
    index: int | None
    before: float | bool | None
    after: float | bool | None


@dataclass
class TraceCandidate:
    path: str
    repo_relative_hint: str
    sha256: str
    trace_family: str
    n_ticks: int
    rng_seed: int | None
    tick_offset: float | None
    states_after_keys: list[str]
    first_active_tick: int | None
    first_active_absolute_tick: float | None
    active_tick_count: int
    first_active_detail: TraceDiffDetail | None
    source_manifest: str | None
    duplicate_of: str | None = None


@dataclass
class BitIdentityResult:
    pass_all_compared_ticks: bool
    compared_surfaces: list[str]
    first_mismatch_tick: int | None
    first_mismatch_observable: str | None
    first_mismatch_index: int | None
    first_mismatch_oc_val: float | bool | None
    first_mismatch_karr_val: float | bool | None
    first_mismatch_diff: float | None
    compared_tick_count: int


@dataclass
class HonestReplayResult:
    karr_active_ticks: int
    oc_active_ticks: int
    oc_active_on_karr_active_ticks: int
    first_karr_active_tick: int | None
    first_karr_active_detail: TraceDiffDetail | None
    first_oc_active_tick: int | None
    first_measured_mismatch: TraceDiffDetail | None


def _repo_relative_hint(path: Path) -> str:
    posix = path.as_posix()
    if posix.startswith("/mnt/e/"):
        return posix.removeprefix("/mnt/e/")
    return posix


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _detect_trace_family(path: Path) -> str:
    posix = path.as_posix()
    if "per_process_traces_v2_event_s" in posix:
        return "event_window"
    if "dnadamage_fullcycle" in posix:
        return "full_cycle"
    if "per_process_traces_v2_s" in posix:
        return "seeded_standard"
    if "per_process_traces_v2/" in posix:
        return "canonical_standard"
    return "other"


def _metadata_scalar(group: h5py.Group, name: str) -> int | float | None:
    if name not in group:
        return None
    raw = np.asarray(group[name][()]).reshape(-1)
    if raw.size == 0:
        return None
    value = raw[0]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value)
    return None


def _cell_ref(ds: h5py.Dataset, tick: int) -> h5py.Reference:
    if len(ds.shape) != 2:
        raise ValueError(f"Unexpected MAT cell rank {ds.shape} for dataset {ds.name}")
    rows, cols = int(ds.shape[0]), int(ds.shape[1])
    if rows == 1 and cols >= tick + 1:
        return ds[0, tick]
    if cols == 1 and rows >= tick + 1:
        return ds[tick, 0]
    if rows >= tick + 1:
        return ds[tick, 0]
    if cols >= tick + 1:
        return ds[0, tick]
    raise IndexError(f"Tick {tick} out of range for {ds.name} shape={ds.shape}")


def _read_numeric_vector(trace: h5py.File, group: str, observable: str, tick: int) -> np.ndarray | None:
    dataset_path = f"{group}/{observable}"
    if dataset_path not in trace:
        return None
    ds = trace[dataset_path]
    if not isinstance(ds, h5py.Dataset):
        return None
    payload = trace[_cell_ref(ds, tick)]
    if not isinstance(payload, h5py.Dataset):
        return None
    arr = np.asarray(payload[()])
    if arr.dtype.kind not in {"b", "i", "u", "f"}:
        return None
    return arr.reshape(-1).astype(np.float64)


def _trace_chromosome_store(trace: h5py.File, group: str, tick: int) -> ChromosomeStore:
    ds = trace[f"{group}/chromosome"]
    return ChromosomeStore.from_hdf5_group(trace[_cell_ref(ds, tick)])


def _trace_chromosome_group(trace: h5py.File, group: str, tick: int) -> h5py.Group:
    ds = trace[f"{group}/chromosome"]
    return trace[_cell_ref(ds, tick)]


def _chromosome_field_arrays(chromosome_group: h5py.Group, field_name: str) -> tuple[np.ndarray, np.ndarray]:
    if field_name not in chromosome_group:
        return (
            np.array([], dtype=np.int64),
            np.array([], dtype=np.int64),
        )
    field_group = chromosome_group[field_name]
    if not isinstance(field_group, h5py.Group):
        return (
            np.array([], dtype=np.int64),
            np.array([], dtype=np.int64),
        )
    raw_strands = np.asarray(_read_matlab_dataset(field_group["strands"]), dtype=np.int64).reshape(-1)
    raw_values = np.asarray(_read_matlab_dataset(field_group["values"]), dtype=np.int64).reshape(-1)
    return raw_strands, raw_values


def _chromosome_token_delta_from_groups(
    spec_token: str,
    before_group: h5py.Group,
    after_group: h5py.Group,
) -> float:
    if spec_token == "repair_event_present":
        damage_fields = (
            "damagedBases",
            "strandBreaks",
            "gapSites",
            "abasicSites",
            "damagedSugarPhosphates",
        )
        for field_name in damage_fields:
            before_strands, _ = _chromosome_field_arrays(before_group, field_name)
            after_strands, _ = _chromosome_field_arrays(after_group, field_name)
            if before_strands.size != after_strands.size:
                return 1.0
        return 0.0

    field_name, op = spec_token.split(".", 1)
    before_strands, before_values = _chromosome_field_arrays(before_group, field_name)
    after_strands, after_values = _chromosome_field_arrays(after_group, field_name)
    if op == "delta_value_sum":
        return float(after_values.sum() - before_values.sum())
    if op == "delta_nnz":
        return float(after_values.size - before_values.size)
    if op.startswith("delta_value_sum_strand_"):
        strand_n = int(op.removeprefix("delta_value_sum_strand_"))
        before_sum = float(before_values[before_strands == strand_n].sum()) if before_strands.size else 0.0
        after_sum = float(after_values[after_strands == strand_n].sum()) if after_strands.size else 0.0
        return after_sum - before_sum
    raise ValueError(f"Unsupported chromosome projection op: {op!r} (token {spec_token!r})")


def _deep_get(mapping: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _deep_set(mapping: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    current = mapping
    for key in path[:-1]:
        next_node = current.get(key)
        if not isinstance(next_node, dict):
            next_node = {}
            current[key] = next_node
        current = next_node
    current[path[-1]] = value


def _deep_merge_replace(target: dict[str, Any], delta: dict[str, Any]) -> None:
    for key, value in delta.items():
        if isinstance(value, dict):
            node = target.get(key)
            if not isinstance(node, dict):
                node = {}
                target[key] = node
            _deep_merge_replace(node, value)
            continue
        target[key] = copy.deepcopy(value)


def _infer_custom_wids(process: Any, process_name: str, observable: str, vector_len: int) -> list[str]:
    explicit_attr = CUSTOM_WID_ATTRS.get(process_name, {}).get(observable)
    if explicit_attr is not None and hasattr(process, explicit_attr):
        raw = getattr(process, explicit_attr)
        return [str(item) for item in raw]
    return [f"{observable}_{idx}" for idx in range(vector_len)]


def _overlay_custom_observable(
    *,
    state: dict[str, Any],
    observable: str,
    vector: np.ndarray,
    process_name: str,
    wids: list[str],
) -> None:
    path = CUSTOM_VECTOR_SURFACES.get(process_name, {}).get(observable)
    if path is None:
        raise KeyError(f"No custom overlay path for {process_name}:{observable}")
    if len(path) == 2 and path[1] == "counts":
        target = _deep_get(state, path)
        if not isinstance(target, dict):
            target = {}
            _deep_set(state, path, target)
        for wid, value in zip(wids, vector, strict=False):
            target[wid] = float(value)
        return
    value = float(vector[0]) if vector.size else 0.0
    if path[-1].endswith("segregated"):
        _deep_set(state, path, bool(value))
    else:
        _deep_set(state, path, value)


def _project_custom_observable(
    *,
    state: dict[str, Any],
    observable: str,
    process_name: str,
    wids: list[str],
) -> np.ndarray:
    path = CUSTOM_VECTOR_SURFACES.get(process_name, {}).get(observable)
    if path is None:
        raise KeyError(f"No custom projection path for {process_name}:{observable}")
    if len(path) == 2 and path[1] == "counts":
        target = _deep_get(state, path)
        if not isinstance(target, dict):
            return np.zeros(len(wids), dtype=np.float64)
        return np.asarray([float(target.get(wid, 0.0)) for wid in wids], dtype=np.float64)
    raw = _deep_get(state, path)
    if isinstance(raw, bool):
        return np.asarray([1.0 if raw else 0.0], dtype=np.float64)
    if raw is None:
        return np.asarray([0.0], dtype=np.float64)
    return np.asarray([float(raw)], dtype=np.float64)


def _recursive_update_nontrivial(node: Any) -> bool:
    if isinstance(node, dict):
        return any(_recursive_update_nontrivial(value) for value in node.values())
    if isinstance(node, (list, tuple)):
        return any(_recursive_update_nontrivial(value) for value in node)
    if isinstance(node, bool):
        return bool(node)
    if isinstance(node, (int, np.integer)):
        return int(node) != 0
    if isinstance(node, (float, np.floating)):
        value = float(node)
        return math.isfinite(value) and abs(value) > 0.0
    if isinstance(node, np.ndarray):
        if node.dtype == np.bool_:
            return bool(np.any(node))
        if node.dtype.kind in {"i", "u", "f"}:
            return bool(np.any(node != 0))
    return False


def _first_vector_mismatch(observable: str, oc_after: np.ndarray, karr_after: np.ndarray) -> TraceDiffDetail | None:
    if oc_after.shape != karr_after.shape:
        return TraceDiffDetail(
            observable=observable,
            detail_path="shape",
            index=None,
            before=float(oc_after.shape[0]),
            after=float(karr_after.shape[0]),
        )
    mismatch = oc_after != karr_after
    if not np.any(mismatch):
        return None
    idx = int(np.flatnonzero(mismatch)[0])
    before = oc_after[idx]
    after = karr_after[idx]
    return TraceDiffDetail(
        observable=observable,
        detail_path=observable,
        index=idx,
        before=bool(before) if isinstance(before, (bool, np.bool_)) else float(before),
        after=bool(after) if isinstance(after, (bool, np.bool_)) else float(after),
    )


def _default_activity_observables(process_name: str) -> tuple[str, ...]:
    spec = _PROCESS_SPECS[process_name]
    return tuple(obs for obs in spec.observables if obs not in spec.pass_through)


def _chromosome_activity_detail(process_name: str, trace: h5py.File, tick: int) -> TraceDiffDetail | None:
    tokens = CHROMOSOME_ACTIVITY_TOKENS.get(process_name, ())
    if not tokens:
        return None
    before_group = _trace_chromosome_group(trace, "states_before", tick)
    after_group = _trace_chromosome_group(trace, "states_after", tick)
    for token in tokens:
        delta = float(_chromosome_token_delta_from_groups(token, before_group, after_group))
        if abs(delta) > 0.0:
            return TraceDiffDetail(
                observable="chromosome",
                detail_path=token,
                index=None,
                before=0.0,
                after=delta,
            )
    return None


def _trace_activity_detail(process_name: str, ctx: Any, tick: int) -> TraceDiffDetail | None:
    trace = ctx.trace
    chrom_detail = _chromosome_activity_detail(process_name, trace, tick)
    if chrom_detail is not None:
        return chrom_detail

    custom_order = CUSTOM_ACTIVITY_OBSERVABLES.get(process_name, ())
    for observable in custom_order:
        before = _read_numeric_vector(trace, "states_before", observable, tick)
        after = _read_numeric_vector(trace, "states_after", observable, tick)
        if before is None or after is None:
            continue
        detail = _first_vector_mismatch(observable, before, after)
        if detail is not None:
            return detail

    for observable in _default_activity_observables(process_name):
        before = _project_trace_vector(ctx, "states_before", observable, tick)
        after = _project_trace_vector(ctx, "states_after", observable, tick)
        detail = _first_vector_mismatch(observable, before, after)
        if detail is not None:
            return detail
    return None


def _scan_activity_without_context(process_name: str, trace: h5py.File, tick: int) -> TraceDiffDetail | None:
    chrom_detail = _chromosome_activity_detail(process_name, trace, tick)
    if chrom_detail is not None:
        return chrom_detail
    for observable in CUSTOM_ACTIVITY_OBSERVABLES.get(process_name, ()):
        before = _read_numeric_vector(trace, "states_before", observable, tick)
        after = _read_numeric_vector(trace, "states_after", observable, tick)
        if before is None or after is None:
            continue
        detail = _first_vector_mismatch(observable, before, after)
        if detail is not None:
            return detail
    return None


def _process_requires_context_for_activity_scan(process_name: str) -> bool:
    return not (
        process_name in CHROMOSOME_ACTIVITY_TOKENS or process_name in CUSTOM_ACTIVITY_OBSERVABLES
    )


def _summarize_trace_candidate(
    process_name: str,
    path: Path,
    *,
    known_sha: str | None,
    source_manifest: str | None,
) -> TraceCandidate:
    with h5py.File(path, "r") as handle:
        metadata = handle["metadata"]
        n_ticks = int(_metadata_scalar(metadata, "n_ticks") or 0)
        tick_offset_raw = _metadata_scalar(metadata, "tick_offset")
        tick_offset = float(tick_offset_raw) if tick_offset_raw is not None else None
        rng_seed_raw = _metadata_scalar(metadata, "rng_seed")
        rng_seed = int(rng_seed_raw) if isinstance(rng_seed_raw, int) else 0
        ctx = None
        if _process_requires_context_for_activity_scan(process_name):
            ctx = _build_context(name=process_name, rng_seed=rng_seed, handle=handle)

        first_active_tick: int | None = None
        first_active_detail: TraceDiffDetail | None = None
        active_tick_count = 0
        for tick in range(n_ticks):
            if ctx is None:
                detail = _scan_activity_without_context(process_name, handle, tick)
            else:
                detail = _trace_activity_detail(process_name, ctx, tick)
            if detail is None:
                continue
            active_tick_count += 1
            if first_active_tick is None:
                first_active_tick = tick
                first_active_detail = detail

        absolute_tick = None
        if first_active_tick is not None:
            absolute_tick = float(first_active_tick if tick_offset is None else tick_offset + first_active_tick)

        return TraceCandidate(
            path=path.as_posix(),
            repo_relative_hint=_repo_relative_hint(path),
            sha256=known_sha or _sha256(path),
            trace_family=_detect_trace_family(path),
            n_ticks=n_ticks,
            rng_seed=rng_seed,
            tick_offset=tick_offset,
            states_after_keys=sorted(handle["states_after"].keys()),
            first_active_tick=first_active_tick,
            first_active_absolute_tick=absolute_tick,
            active_tick_count=active_tick_count,
            first_active_detail=first_active_detail,
            source_manifest=source_manifest,
        )


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _standard_candidates_from_manifest(process_name: str) -> list[tuple[Path, str | None, str | None]]:
    payload = _load_json(STANDARD_MANIFEST_PATH)
    sources = {entry["name"]: Path(entry["path"]) for entry in payload.get("sources", [])}
    process_rows = payload.get("processes", {}).get(process_name, {}).get("files", [])
    candidates: list[tuple[Path, str | None, str | None]] = []
    for row in process_rows:
        source_name = row.get("source_name")
        relative_path = row.get("relative_path")
        if not source_name or not relative_path:
            continue
        source_root = sources.get(source_name)
        if source_root is None:
            continue
        path = source_root / "data" / "m1_sources" / "karr_native" / relative_path
        candidates.append((path, row.get("sha256"), STANDARD_MANIFEST_PATH.name))
    return candidates


def _direct_standard_candidate(process_name: str) -> list[tuple[Path, str | None, str | None]]:
    rel = Path("data") / "m1_sources" / "karr_native" / "per_process_traces_v2" / f"{process_name}_100ticks.mat"
    candidates = [
        _REPO_ROOT / rel,
        Path("E:/opencell") / rel,
        Path("/mnt/e/opencell") / rel,
    ]
    for candidate in candidates:
        if candidate.exists():
            return [(candidate, None, "direct_standard_fallback")]
    return []


def _event_candidates_from_manifest(manifest_path: Path) -> list[tuple[Path, str | None, str | None]]:
    if not manifest_path.exists():
        return []
    payload = _load_json(manifest_path)
    candidates: list[tuple[Path, str | None, str | None]] = []
    for row in payload.get("inputs", []):
        rel = row.get("path")
        if not rel:
            continue
        candidates.append((Path("/mnt/e/opencell-worktrees") / rel.removeprefix("data/"), None, manifest_path.name))
    return candidates


def _special_candidates(process_name: str) -> list[tuple[Path, str | None, str | None]]:
    candidates: list[tuple[Path, str | None, str | None]] = []
    if process_name == "Cytokinesis":
        payload = _load_json(CYTOKINESIS_EVENT_MANIFEST)
        for row in payload.get("inputs", []):
            rel = row["path"]
            candidates.append(
                (
                    Path("/mnt/e/opencell-worktrees/l2-event-cytokinesis-20260805") / rel,
                    row.get("sha256"),
                    CYTOKINESIS_EVENT_MANIFEST.name,
                )
            )
        return candidates
    if process_name == "RibosomeAssembly":
        payload = _load_json(RIBOSOME_EVENT_MANIFEST)
        for row in payload.get("inputs", []):
            rel = row["path"]
            candidates.append(
                (
                    Path("/mnt/e/opencell-worktrees/l2-event-ribosome-20260805") / rel,
                    row.get("sha256"),
                    RIBOSOME_EVENT_MANIFEST.name,
                )
            )
        return candidates
    for path in DIRECT_SPECIAL_TRACES.get(process_name, ()):
        candidates.append((path, None, None))
    return candidates


def _find_trace_candidates(
    process_name: str,
    *,
    progress: bool = False,
    candidate_limit: int | None = None,
) -> list[TraceCandidate]:
    standard_candidates = _standard_candidates_from_manifest(process_name)
    if not standard_candidates:
        standard_candidates = _direct_standard_candidate(process_name)
    special_candidates = _special_candidates(process_name)
    if process_name in SPECIAL_FIRST_PROCESSES:
        raw_candidates = special_candidates + standard_candidates
    else:
        raw_candidates = standard_candidates + special_candidates
    deduped: dict[str, tuple[Path, str | None, str | None]] = {}
    for path, sha, source_manifest in raw_candidates:
        if path.exists():
            deduped[path.as_posix()] = (path, sha, source_manifest)

    summaries: list[TraceCandidate] = []
    seen_hashes: dict[str, str] = {}
    for idx, (path, sha, source_manifest) in enumerate(deduped.values()):
        if candidate_limit is not None and idx >= candidate_limit:
            break
        if progress:
            print(f"[l21-audit] scan-candidate {process_name} path={path.as_posix()}", file=sys.stderr, flush=True)
        candidate = _summarize_trace_candidate(
            process_name,
            path,
            known_sha=sha,
            source_manifest=source_manifest,
        )
        if progress:
            print(
                f"[l21-audit] scanned-candidate {process_name} first_active_tick={candidate.first_active_tick} "
                f"active_tick_count={candidate.active_tick_count}",
                file=sys.stderr,
                flush=True,
            )
        duplicate_of = seen_hashes.get(candidate.sha256)
        if duplicate_of is not None:
            candidate.duplicate_of = duplicate_of
        else:
            seen_hashes[candidate.sha256] = candidate.repo_relative_hint
        summaries.append(candidate)
        if (
            candidate.first_active_absolute_tick == 0.0
            and candidate.first_active_tick == 0
            and candidate.duplicate_of is None
        ):
            break
    summaries.sort(
        key=lambda c: (
            c.first_active_tick is None,
            math.inf if c.first_active_absolute_tick is None else c.first_active_absolute_tick,
            c.first_active_tick if c.first_active_tick is not None else math.inf,
            c.path,
        )
    )
    return summaries


def _apply_non_count_updates(state: dict[str, Any], update: dict[str, Any]) -> None:
    for key, value in update.items():
        if key in COUNT_STORE_KEYS or key in IGNORED_UPDATE_KEYS:
            continue
        if isinstance(value, dict):
            target = state.get(key)
            if not isinstance(target, dict):
                target = {}
                state[key] = target
            _deep_merge_replace(target, value)
        else:
            state[key] = copy.deepcopy(value)


def _honest_replay(
    process_name: str,
    trace_path: Path,
    *,
    progress: bool = False,
) -> tuple[BitIdentityResult, HonestReplayResult]:
    with h5py.File(trace_path, "r") as handle:
        metadata = handle["metadata"]
        rng_seed_raw = _metadata_scalar(metadata, "rng_seed")
        rng_seed = int(rng_seed_raw) if isinstance(rng_seed_raw, int) else 0
        ctx = _build_context(name=process_name, rng_seed=rng_seed, handle=handle)
        process = ctx.process
        spec = ctx.spec

        compared_surfaces = list(spec.observables)
        for surface in CUSTOM_COMPARE_OBSERVABLES.get(process_name, ()):
            if surface not in compared_surfaces:
                compared_surfaces.append(surface)
        for token in CHROMOSOME_ACTIVITY_TOKENS.get(process_name, ()):
            if token not in compared_surfaces:
                compared_surfaces.append(token)

        wids_by_surface = dict(ctx.wids_by_observable)
        for surface in CUSTOM_COMPARE_OBSERVABLES.get(process_name, ()):
            if surface in wids_by_surface:
                continue
            before = _read_numeric_vector(handle, "states_before", surface, 0)
            vector_len = 0 if before is None else int(before.shape[0])
            wids_by_surface[surface] = _infer_custom_wids(
                process=process,
                process_name=process_name,
                observable=surface,
                vector_len=vector_len,
            )

        first_mismatch: TraceDiffDetail | None = None
        first_mismatch_tick: int | None = None
        first_karr_active_tick: int | None = None
        first_karr_active_detail: TraceDiffDetail | None = None
        first_oc_active_tick: int | None = None
        karr_active_ticks = 0
        oc_active_ticks = 0
        oc_active_on_karr_active_ticks = 0

        for tick in range(ctx.n_ticks):
            if progress and (tick == 0 or tick == ctx.n_ticks - 1 or tick % 25 == 0):
                print(
                    f"[l21-audit] replay-tick {process_name} tick={tick}/{ctx.n_ticks - 1}",
                    file=sys.stderr,
                    flush=True,
                )
            state = build_state_template(process)
            before_vectors: dict[str, np.ndarray] = {}
            before_chromosome_store: ChromosomeStore | None = None

            for observable in spec.observables:
                before = _project_trace_vector(ctx, "states_before", observable, tick)
                before_vectors[observable] = before
                overlay_observable_into_state(
                    process=process,
                    state=state,
                    observable=observable,
                    vector=before,
                    wids=wids_by_surface[observable],
                    store_path_override=spec.store_path_override,
                )

            for observable in CUSTOM_COMPARE_OBSERVABLES.get(process_name, ()):
                before = _read_numeric_vector(handle, "states_before", observable, tick)
                if before is None:
                    continue
                before_vectors[observable] = before
                _overlay_custom_observable(
                    state=state,
                    observable=observable,
                    vector=before,
                    process_name=process_name,
                    wids=wids_by_surface[observable],
                )

            _inject_hidden_read_surface(ctx=ctx, state=state, tick=tick)
            if CHROMOSOME_ACTIVITY_TOKENS.get(process_name):
                before_chromosome_store = ChromosomeStore.from_state_mapping(
                    state.get("chromosome", {}),
                    shape=getattr(process, "chromosome_shape", ChromosomeStore().shape),
                )
            refresh_allocator_views(process, state)

            update = process.next_update(1.0, state)
            if _recursive_update_nontrivial(update):
                oc_active_ticks += 1
                if first_oc_active_tick is None:
                    first_oc_active_tick = tick

            for label, deltas in collect_count_delta_dicts(update):
                for value in deltas.values():
                    float(value)
            apply_count_update(state, update)
            _apply_non_count_updates(state, update)

            karr_detail = _trace_activity_detail(process_name, ctx, tick)
            if karr_detail is not None:
                karr_active_ticks += 1
                if first_karr_active_tick is None:
                    first_karr_active_tick = tick
                    first_karr_active_detail = karr_detail
                if _recursive_update_nontrivial(update):
                    oc_active_on_karr_active_ticks += 1

            after_chromosome_store: ChromosomeStore | None = None
            if before_chromosome_store is not None:
                after_chromosome_store = ChromosomeStore.from_state_mapping(
                    state.get("chromosome", {}),
                    shape=before_chromosome_store.shape,
                )

            for surface in compared_surfaces:
                if surface in spec.pass_through:
                    continue
                if surface in CHROMOSOME_ACTIVITY_TOKENS.get(process_name, ()):
                    if before_chromosome_store is None or after_chromosome_store is None:
                        continue
                    oc_after = np.asarray(
                        [float(_chromosome_projection_component(surface, before_chromosome_store, after_chromosome_store))],
                        dtype=np.float64,
                    )
                    karr_before_store = _trace_chromosome_store(handle, "states_before", tick)
                    karr_after_store = _trace_chromosome_store(handle, "states_after", tick)
                    karr_after = np.asarray(
                        [float(_chromosome_projection_component(surface, karr_before_store, karr_after_store))],
                        dtype=np.float64,
                    )
                elif surface in CUSTOM_COMPARE_OBSERVABLES.get(process_name, ()):
                    oc_after = _project_custom_observable(
                        state=state,
                        observable=surface,
                        process_name=process_name,
                        wids=wids_by_surface[surface],
                    )
                    karr_after = _read_numeric_vector(handle, "states_after", surface, tick)
                    if karr_after is None:
                        continue
                else:
                    oc_after = project_observable_from_state(
                        process=process,
                        state=state,
                        observable=surface,
                        wids=wids_by_surface[surface],
                        bound_enzymes_before=before_vectors.get("boundEnzymes"),
                        store_path_override=spec.store_path_override,
                    )
                    karr_after = _project_trace_vector(ctx, "states_after", surface, tick)

                mismatch = _first_vector_mismatch(surface, oc_after, karr_after)
                if mismatch is not None and first_mismatch is None:
                    first_mismatch = mismatch
                    first_mismatch_tick = tick

        bit_result = BitIdentityResult(
            pass_all_compared_ticks=first_mismatch is None,
            compared_surfaces=compared_surfaces,
            first_mismatch_tick=first_mismatch_tick,
            first_mismatch_observable=first_mismatch.observable if first_mismatch else None,
            first_mismatch_index=first_mismatch.index if first_mismatch else None,
            first_mismatch_oc_val=first_mismatch.before if first_mismatch else None,
            first_mismatch_karr_val=first_mismatch.after if first_mismatch else None,
            first_mismatch_diff=(
                None
                if first_mismatch is None or first_mismatch.before is None or first_mismatch.after is None
                else float(first_mismatch.before) - float(first_mismatch.after)
            ),
            compared_tick_count=ctx.n_ticks,
        )
        honest_result = HonestReplayResult(
            karr_active_ticks=karr_active_ticks,
            oc_active_ticks=oc_active_ticks,
            oc_active_on_karr_active_ticks=oc_active_on_karr_active_ticks,
            first_karr_active_tick=first_karr_active_tick,
            first_karr_active_detail=first_karr_active_detail,
            first_oc_active_tick=first_oc_active_tick,
            first_measured_mismatch=first_mismatch,
        )
        return bit_result, honest_result


def _choose_earliest_active(candidates: list[TraceCandidate]) -> TraceCandidate | None:
    active = [candidate for candidate in candidates if candidate.first_active_tick is not None]
    if not active:
        return None
    active.sort(
        key=lambda candidate: (
            math.inf if candidate.first_active_absolute_tick is None else candidate.first_active_absolute_tick,
            candidate.first_active_tick if candidate.first_active_tick is not None else math.inf,
            candidate.path,
        )
    )
    return active[0]


def _classify_process(
    process_name: str,
    *,
    progress: bool = False,
    candidate_limit: int | None = None,
    skip_replay: bool = False,
) -> dict[str, Any]:
    candidates = _find_trace_candidates(process_name, progress=progress, candidate_limit=candidate_limit)
    chosen = _choose_earliest_active(candidates)

    row: dict[str, Any] = {
        "process": process_name,
        "activity_predicate": PROCESS_ACTIVITY_PREDICATE_TEXT[process_name],
        "scanned_candidate_count": len(candidates),
        "candidate_traces": [asdict(candidate) for candidate in candidates],
        "chosen_trace": None,
        "bit_identity": None,
        "honest_replay": None,
        "classification": None,
        "existing_trace_suffices": False,
        "extraction_request": None,
    }

    if chosen is None:
        row["classification"] = CLASS_MISSING_ACTIVE_EXTRACTION
        row["extraction_request"] = PROCESS_CONFIGS[process_name].missing_extraction_request
        return row

    if skip_replay:
        row["chosen_trace"] = asdict(chosen)
        row["classification"] = "SKIPPED_REPLAY"
        row["existing_trace_suffices"] = True
        return row

    if progress:
        print(
            f"[l21-audit] chosen-trace {process_name} path={chosen.path} first_active_tick={chosen.first_active_tick}",
            file=sys.stderr,
            flush=True,
        )
    bit_identity, honest = _honest_replay(process_name=process_name, trace_path=Path(chosen.path), progress=progress)
    row["chosen_trace"] = asdict(chosen)
    row["bit_identity"] = asdict(bit_identity)
    row["honest_replay"] = asdict(honest)
    row["existing_trace_suffices"] = True

    if honest.oc_active_on_karr_active_ticks == 0:
        row["classification"] = CLASS_CODE_GAP
    elif bit_identity.pass_all_compared_ticks:
        row["classification"] = CLASS_EXISTING_WINDOW_PASS
    else:
        row["classification"] = CLASS_CODE_GAP

    if row["classification"] == CLASS_CODE_GAP:
        row["code_gap_anchor"] = {
            "first_karr_active_tick": honest.first_karr_active_tick,
            "first_karr_active_detail": (
                None if honest.first_karr_active_detail is None else asdict(honest.first_karr_active_detail)
            ),
            "first_measured_mismatch": (
                None if honest.first_measured_mismatch is None else asdict(honest.first_measured_mismatch)
            ),
        }
    return row


def run_audit(
    *,
    target_processes: tuple[str, ...] = TARGET_PROCESSES,
    progress: bool = False,
    candidate_limit: int | None = None,
    skip_replay: bool = False,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for process_name in target_processes:
        if progress:
            print(f"[l21-audit] start {process_name}", file=sys.stderr, flush=True)
        row = _classify_process(
            process_name,
            progress=progress,
            candidate_limit=candidate_limit,
            skip_replay=skip_replay,
        )
        rows.append(row)
        if progress:
            print(
                f"[l21-audit] done {process_name} classification={row['classification']}",
                file=sys.stderr,
                flush=True,
            )
    counts = {
        CLASS_EXISTING_WINDOW_PASS: sum(1 for row in rows if row["classification"] == CLASS_EXISTING_WINDOW_PASS),
        CLASS_CODE_GAP: sum(1 for row in rows if row["classification"] == CLASS_CODE_GAP),
        CLASS_MISSING_ACTIVE_EXTRACTION: sum(
            1 for row in rows if row["classification"] == CLASS_MISSING_ACTIVE_EXTRACTION
        ),
    }
    return {
        "generated_by": "scripts/l21_active_window_audit.py",
        "standard_manifest": STANDARD_MANIFEST_PATH.as_posix(),
        "process_count": len(rows),
        "counts": counts,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit existing local active windows for L2.1 closure.")
    parser.add_argument(
        "--write-json",
        type=Path,
        default=None,
        help="Optional path to write the manifest JSON.",
    )
    parser.add_argument(
        "--process",
        action="append",
        choices=TARGET_PROCESSES,
        default=None,
        help="Limit the audit to one or more target processes.",
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Print per-process progress to stderr while auditing.",
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=None,
        help="Debug option: limit scanned candidate traces per process.",
    )
    parser.add_argument(
        "--skip-replay",
        action="store_true",
        help="Debug option: stop after choosing the earliest active trace and skip bit-identity replay.",
    )
    args = parser.parse_args()

    target_processes = tuple(args.process) if args.process else TARGET_PROCESSES
    payload = run_audit(
        target_processes=target_processes,
        progress=args.progress,
        candidate_limit=args.candidate_limit,
        skip_replay=args.skip_replay,
    )
    text = json.dumps(payload, indent=2, sort_keys=False)
    if args.write_json is not None:
        args.write_json.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {args.write_json}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
