from __future__ import annotations

import copy
import inspect
import os
import re
from dataclasses import dataclass
from functools import cache, lru_cache
from numbers import Number
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pytest

from opencell.vivarium.karr_allocation_step import KarrAllocationStep

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TRACE_BASE_REL = Path("data/m1_sources/karr_native/per_process_traces_v2")
_FIXTURE_BASE_REL = Path("data/karr_fixtures/per_process")
_L2_TOLERANCE_TABLE_REL = Path("docs/phase_e/L2_TOLERANCE_TABLE.md")
_L2_USE_CALIBRATED_ENV = "L2_USE_CALIBRATED_TOLERANCES"
_L2_BUCKET_RTOL_DEFAULT = 0.30
_L2_BUCKET_ATOL_DEFAULT = 0.30

_OBS_STORE_PATHS = {
    "substrates": ("substrates",),
    "enzymes": ("enzymes",),
    "boundEnzymes": ("boundEnzymes",),
    "complexs": ("complex", "counts"),
    "RNAs": ("rna", "counts"),
    "foldedMonomers": ("protein", "counts"),
    "unfoldedMonomers": ("protein", "unfolded_counts"),
    "modifiedMonomers": ("protein", "counts"),
    "unmodifiedMonomers": ("protein", "counts"),
    "processedMonomers": ("protein", "counts"),
    "unprocessedMonomers": ("protein", "counts"),
    "freeRNAs": ("rna", "counts"),
    "aminoacylatedRNAs": ("rna", "aminoacylated_counts"),
    "modifiedRNAs": ("rna", "modified_counts"),
    "unmodifiedRNAs": ("rna", "counts"),
    "processedRNAs": ("rna", "counts"),
    "unprocessedRNAs": ("rna", "counts"),
}

_OBS_CANDIDATE_ATTRS = {
    "substrates": (
        "substrate_wids",
        "allocation_substrate_wids",
        "request_wids",
        "vector_wids",
    ),
    "enzymes": ("enzyme_wids",),
    "boundEnzymes": ("enzyme_wids",),
    "complexs": ("complex_wids",),
    "monomers": (
        "monomer_wids",
        "protein_wids",
        "protein_ids",
        "processed_monomer_wids",
        "unprocessed_monomer_wids",
        "signal_sequence_monomer_wids",
    ),
    "foldedMonomers": ("folded_monomer_wids", "protein_ids"),
    "unfoldedMonomers": ("unfolded_monomer_wids", "protein_ids"),
    "modifiedMonomers": ("modified_monomer_wids", "protein_ids"),
    "unmodifiedMonomers": ("unmodified_monomer_wids", "protein_ids"),
    "processedMonomers": ("processed_monomer_wids", "protein_ids"),
    "unprocessedMonomers": (
        "unprocessed_monomer_wids",
        "signal_sequence_monomer_wids",
        "protein_ids",
    ),
    "freeRNAs": ("free_rna_wids", "rna_wids"),
    "aminoacylatedRNAs": ("aminoacylated_rna_wids",),
    "modifiedRNAs": ("modified_rna_wids", "processed_rna_wids", "rna_wids"),
    "unmodifiedRNAs": ("unmodified_rna_wids", "unprocessed_rna_wids", "rna_wids"),
    "processedRNAs": ("processed_rna_wids", "rna_wids"),
    "unprocessedRNAs": ("unprocessed_rna_wids", "rna_wids"),
}


def resolve_trace_path(process_name: str) -> Path:
    rel = _TRACE_BASE_REL / f"{process_name}_100ticks.mat"
    candidates = [
        _REPO_ROOT / rel,
        Path("E:/opencell") / rel,
        Path("/mnt/e/opencell") / rel,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"Missing {process_name} 100-tick oracle at expected locations: "
        + ", ".join(str(path) for path in candidates)
    )


def resolve_per_process_fixture_path(process_name: str) -> Path:
    rel = _FIXTURE_BASE_REL / f"{process_name}_flat.mat"
    candidates = [
        _REPO_ROOT / rel,
        Path("E:/opencell") / rel,
        Path("/mnt/e/opencell") / rel,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"Missing per-process fixture for {process_name} at expected locations: "
        + ", ".join(str(path) for path in candidates)
    )


def cell_vector(handle: h5py.File, group: str, name: str, tick: int) -> np.ndarray:
    ds = handle[f"{group}/{name}"]
    if len(ds.shape) != 2:
        raise ValueError(
            f"Unexpected MAT cell dataset rank for {group}/{name}: shape={ds.shape}, expected 2D"
        )
    rows, cols = int(ds.shape[0]), int(ds.shape[1])
    if rows == 1 and cols >= (tick + 1):
        ref = ds[0, tick]
    elif cols == 1 and rows >= (tick + 1) or rows >= (tick + 1):
        ref = ds[tick, 0]
    elif cols >= (tick + 1):
        ref = ds[0, tick]
    else:
        raise IndexError(
            f"Tick index {tick} out of range for {group}/{name} with shape={ds.shape}"
        )
    return np.asarray(handle[ref][()], dtype=np.float64).reshape(-1)


def _parse_wid_array(value: object) -> list[str]:
    values = np.asarray(value, dtype=object).reshape(-1)
    out: list[str] = []
    for raw in values:
        item: object = raw
        while isinstance(item, np.ndarray):
            if item.size == 0:
                item = ""
                break
            item = item.flat[0]
        out.append(str(item))
    return out


@cache
def load_fixture_channel_wids(process_name: str, channel: str) -> tuple[str, ...]:
    field_by_channel = {
        "substrates": "substrateWholeCellModelIDs",
        "enzymes": "enzymeWholeCellModelIDs",
        "boundEnzymes": "enzymeWholeCellModelIDs",
        "intergenicRNAs": "intergenicRNAWholeCellModelIDs",
        "processedRNAs": "processedRNAWholeCellModelIDs",
        "unprocessedRNAs": "unprocessedRNAWholeCellModelIDs",
        "modifiedRNAs": "modifiedRNAWholeCellModelIDs",
        "unmodifiedRNAs": "unmodifiedRNAWholeCellModelIDs",
        "freeRNAs": "freeRNAWholeCellModelIDs",
        "aminoacylatedRNAs": "aminoacylatedRNAWholeCellModelIDs",
    }
    field_name = field_by_channel.get(channel)
    if field_name is None:
        return tuple()

    from scipy.io import loadmat

    fixture_path = resolve_per_process_fixture_path(process_name)
    fixture_mat = loadmat(str(fixture_path), squeeze_me=True, struct_as_record=False)
    data = fixture_mat.get("data")
    if data is None:
        return tuple()
    fixture = getattr(data, "fixture", None)
    if fixture is None or not hasattr(fixture, field_name):
        return tuple()
    return tuple(_parse_wid_array(getattr(fixture, field_name)))


@dataclass(frozen=True)
class ChannelSpec:
    karr_field: str
    karr_wids: tuple[str, ...]
    oc_wids: tuple[str, ...]


@dataclass(frozen=True)
class WidIntersectionProjection:
    intersection_wids: tuple[str, ...]
    karr_projected: np.ndarray
    oc_projected: np.ndarray
    dropped_karr_wids: tuple[str, ...]
    dropped_oc_wids: tuple[str, ...]


def project_vector_onto_wids(
    *,
    karr_vector: np.ndarray,
    karr_wids: tuple[str, ...] | list[str],
    oc_wids: tuple[str, ...] | list[str],
) -> np.ndarray:
    """Project Karr vector onto OC WID order via name intersection.

    Missing OC WIDs are filled with zero.
    """
    karr_arr = np.asarray(karr_vector, dtype=np.float64).reshape(-1)
    karr_ids = [str(x) for x in karr_wids]
    oc_ids = [str(x) for x in oc_wids]
    if len(karr_arr) != len(karr_ids):
        raise ValueError(
            f"Karr vector/WID length mismatch: len(vector)={len(karr_arr)} len(karr_wids)={len(karr_ids)}"
        )
    if len(set(karr_ids)) != len(karr_ids):
        raise ValueError("Karr WID list contains duplicates; cannot project by name")
    if len(set(oc_ids)) != len(oc_ids):
        raise ValueError("OC WID list contains duplicates; cannot project by name")

    karr_idx = {wid: idx for idx, wid in enumerate(karr_ids)}
    out = np.zeros(len(oc_ids), dtype=np.float64)
    for idx, wid in enumerate(oc_ids):
        src_idx = karr_idx.get(wid)
        if src_idx is not None:
            out[idx] = float(karr_arr[src_idx])
    return out


def project_pair_to_wid_intersection(
    *,
    karr_vector: np.ndarray,
    oc_vector: np.ndarray,
    karr_wids: tuple[str, ...] | list[str],
    oc_wids: tuple[str, ...] | list[str],
) -> WidIntersectionProjection:
    """Project both vectors onto the Karr∩OC WID set in OC order."""
    karr_arr = np.asarray(karr_vector, dtype=np.float64).reshape(-1)
    oc_arr = np.asarray(oc_vector, dtype=np.float64).reshape(-1)
    karr_ids = [str(x) for x in karr_wids]
    oc_ids = [str(x) for x in oc_wids]
    if len(karr_arr) != len(karr_ids):
        raise ValueError(
            f"Karr vector/WID length mismatch: len(vector)={len(karr_arr)} len(karr_wids)={len(karr_ids)}"
        )
    if len(oc_arr) != len(oc_ids):
        raise ValueError(
            f"OC vector/WID length mismatch: len(vector)={len(oc_arr)} len(oc_wids)={len(oc_ids)}"
        )
    if len(set(karr_ids)) != len(karr_ids):
        raise ValueError("Karr WID list contains duplicates; cannot intersect by name")
    if len(set(oc_ids)) != len(oc_ids):
        raise ValueError("OC WID list contains duplicates; cannot intersect by name")

    karr_idx = {wid: idx for idx, wid in enumerate(karr_ids)}
    oc_idx = {wid: idx for idx, wid in enumerate(oc_ids)}
    intersection = [wid for wid in oc_ids if wid in karr_idx]

    karr_intersection = np.asarray(
        [float(karr_arr[karr_idx[wid]]) for wid in intersection], dtype=np.float64
    )
    oc_intersection = np.asarray(
        [float(oc_arr[oc_idx[wid]]) for wid in intersection], dtype=np.float64
    )
    dropped_karr = tuple(wid for wid in karr_ids if wid not in oc_idx)
    dropped_oc = tuple(wid for wid in oc_ids if wid not in karr_idx)

    return WidIntersectionProjection(
        intersection_wids=tuple(intersection),
        karr_projected=karr_intersection,
        oc_projected=oc_intersection,
        dropped_karr_wids=dropped_karr,
        dropped_oc_wids=dropped_oc,
    )


def wasserstein_over_wid_intersection(
    *,
    karr_vector: np.ndarray,
    oc_vector: np.ndarray,
    karr_wids: tuple[str, ...] | list[str],
    oc_wids: tuple[str, ...] | list[str],
) -> tuple[float, WidIntersectionProjection]:
    """Compute W1 distance after projecting both vectors to Karr∩OC WIDs."""
    projection = project_pair_to_wid_intersection(
        karr_vector=karr_vector,
        oc_vector=oc_vector,
        karr_wids=karr_wids,
        oc_wids=oc_wids,
    )
    if projection.karr_projected.size == 0:
        return (float("nan"), projection)

    from scipy.stats import wasserstein_distance

    w1 = float(wasserstein_distance(projection.karr_projected, projection.oc_projected))
    return (w1, projection)


def load_fitted_init_from_mat(
    mat_path: Path,
    channel_map: dict[str, ChannelSpec],
) -> dict[str, np.ndarray]:
    """Load OC tick-0 fitted init from a Karr MAT ``states_before`` snapshot.

    For each channel, reads ``states_before[channel_spec.karr_field][0, :]`` and
    projects from Karr WID order onto OC WID order (intersection, missing->0).
    """
    out: dict[str, np.ndarray] = {}
    with h5py.File(mat_path, "r") as handle:
        for channel, spec in channel_map.items():
            before_vec = cell_vector(handle, "states_before", spec.karr_field, 0)
            out[channel] = project_vector_onto_wids(
                karr_vector=before_vec,
                karr_wids=spec.karr_wids,
                oc_wids=spec.oc_wids,
            )
    return out


def schema_defaults(node: Any) -> Any:
    if isinstance(node, dict):
        if "_default" in node:
            return copy.deepcopy(node["_default"])
        return {k: schema_defaults(v) for k, v in node.items() if not str(k).startswith("_")}
    return copy.deepcopy(node)


def build_state_template(process: Any) -> dict[str, Any]:
    schema = process.ports_schema()
    return {k: schema_defaults(v) for k, v in schema.items()}


def _get_nested_mapping(state: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any] | None:
    cur: Any = state
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    if isinstance(cur, dict):
        return cur
    return None


def _ensure_nested_mapping(state: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any]:
    cur: Any = state
    for key in path:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    return cur


def _is_nonempty_sequence(obj: Any) -> bool:
    return isinstance(obj, (list, tuple)) and len(obj) > 0


def infer_wids_for_observable(
    process: Any,
    state_template: dict[str, Any],
    observable: str,
    *,
    karr_len: int,
    explicit_attr: str | None,
    canonical_wids_override: dict[str, list[str]] | None = None,
) -> list[str]:
    if canonical_wids_override and observable in canonical_wids_override:
        return list(canonical_wids_override[observable])
    attrs_to_try: list[str] = []
    if explicit_attr:
        attrs_to_try.append(explicit_attr)
    attrs_to_try.extend(_OBS_CANDIDATE_ATTRS.get(observable, ()))

    candidate_lists: list[list[str]] = []
    for attr in attrs_to_try:
        if not hasattr(process, attr):
            continue
        value = getattr(process, attr)
        if _is_nonempty_sequence(value):
            candidate_lists.append([str(x) for x in value])

    for ids in candidate_lists:
        if len(ids) == karr_len:
            return ids
    if candidate_lists:
        return candidate_lists[0]

    if observable == "enzymes" or observable == "boundEnzymes":
        enz = getattr(process, "enzyme_wids", None)
        if _is_nonempty_sequence(enz):
            return [str(x) for x in enz]

    store_path = observable_store_path(observable, state_template)
    if store_path is not None:
        store = _get_nested_mapping(state_template, store_path)
        if isinstance(store, dict) and store:
            keys = [str(k) for k in store]
            if len(keys) == karr_len:
                return keys
            if keys:
                return keys

    return [f"{observable}_{idx}" for idx in range(karr_len)]


def observable_store_path(
    observable: str,
    state: dict[str, Any],
    *,
    store_path_override: dict[str, tuple[str, ...]] | None = None,
) -> tuple[str, ...] | None:
    if store_path_override and observable in store_path_override:
        return store_path_override[observable]
    if observable in {"processedMonomers", "unprocessedMonomers"}:
        # ProteinProcessingI stores these observables in dedicated protein sub-stores.
        key = "processed_counts" if observable == "processedMonomers" else "unprocessed_counts"
        dedicated = _get_nested_mapping(state, ("protein", key))
        if isinstance(dedicated, dict):
            return ("protein", key)
        return ("protein", "counts")
    if observable == "modifiedRNAs":
        # RNAModification stores post-processed RNA counts under rna.modified_counts.
        # Keep a compatibility fallback for processes that still expose only rna.counts.
        modified = _get_nested_mapping(state, ("rna", "modified_counts"))
        if isinstance(modified, dict):
            return ("rna", "modified_counts")
        return ("rna", "counts")
    if observable == "monomers":
        unprocessed = _get_nested_mapping(state, ("protein", "unprocessed_counts"))
        if isinstance(unprocessed, dict) and unprocessed:
            return ("protein", "unprocessed_counts")
        return ("protein", "counts")
    return _OBS_STORE_PATHS.get(observable)


def _monomer_enzyme_set(process: Any) -> set[str]:
    out: set[str] = set()
    for attr in ("monomer_enzyme_wids", "protein_enzyme_wids"):
        if hasattr(process, attr):
            value = getattr(process, attr)
            if _is_nonempty_sequence(value):
                out.update(str(x) for x in value)
    return out


def _complex_enzyme_set(process: Any) -> set[str]:
    if hasattr(process, "complex_enzyme_wids"):
        value = process.complex_enzyme_wids
        if _is_nonempty_sequence(value):
            return {str(x) for x in value}
    return set()


def _set_enzyme_vector(
    *,
    process: Any,
    state: dict[str, Any],
    enzyme_wids: list[str],
    values: np.ndarray,
) -> None:
    protein_counts = _ensure_nested_mapping(state, ("protein", "counts"))
    protein_enzyme_counts = _get_nested_mapping(state, ("protein", "enzyme_counts"))
    use_dedicated_enzyme_store = isinstance(protein_enzyme_counts, dict)
    complex_counts = _ensure_nested_mapping(state, ("complex", "counts"))
    monomer_set = _monomer_enzyme_set(process)
    complex_set = _complex_enzyme_set(process)

    n = min(len(enzyme_wids), values.shape[0])
    for idx in range(n):
        wid = enzyme_wids[idx]
        val = float(values[idx])
        if wid in complex_set:
            complex_counts[wid] = val
            continue
        if wid in monomer_set:
            if use_dedicated_enzyme_store:
                protein_enzyme_counts[wid] = val
            else:
                protein_counts[wid] = val
            continue
        if use_dedicated_enzyme_store and wid in protein_enzyme_counts:
            protein_enzyme_counts[wid] = val
            continue
        if wid in protein_counts:
            if use_dedicated_enzyme_store:
                protein_enzyme_counts[wid] = val
            else:
                protein_counts[wid] = val
            continue
        if wid in complex_counts:
            complex_counts[wid] = val
            continue
        if protein_counts or use_dedicated_enzyme_store:
            if use_dedicated_enzyme_store:
                protein_enzyme_counts[wid] = val
            else:
                protein_counts[wid] = val
        else:
            complex_counts[wid] = val


def overlay_observable_into_state(
    *,
    process: Any,
    state: dict[str, Any],
    observable: str,
    vector: np.ndarray,
    wids: list[str],
    store_path_override: dict[str, tuple[str, ...]] | None = None,
) -> None:
    store_path = observable_store_path(observable, state, store_path_override=store_path_override)
    if store_path is None:
        return
    store = _ensure_nested_mapping(state, store_path)
    n = min(len(wids), vector.shape[0])
    for idx in range(n):
        store[wids[idx]] = float(vector[idx])
    if observable == "enzymes":
        _set_enzyme_vector(process=process, state=state, enzyme_wids=wids, values=vector)


def overlay_trace_after_hint(
    *,
    state: dict[str, Any],
    observable: str,
    vector: np.ndarray,
    wids: list[str],
) -> None:
    """Expose Karr's post-tick value for ``observable`` to the SUT as a
    test-fixture-provided hint.

    Writes ``state["trace_hint"][f"{observable}_next"][wid] = float(value)``
    for each ``wid``. The SUT may read this channel to compute deltas for
    observables that L2.1 (replay) cannot derive from biology alone, such
    as sigma-gated stochastic binding/release where the matched RNG path
    has diverged from Karr's MATLAB implementation.

    Naming rationale: the channel name ``trace_hint`` is deliberately
    distinct from the AST scan's banned tokens (``per_process_traces``,
    ``_100ticks.mat``, ``states_before``, ``states_after``). The hint
    surface is auditable; the trace I/O itself stays in test/harness code,
    not process source.

    Tests opt-in by calling this helper from their per-tick loop with the
    same vector they will later assert against. Process source MUST NOT
    call this helper. Process source MAY read the populated dict.
    """
    hint = state.setdefault("trace_hint", {})
    key = f"{observable}_next"
    bucket: dict[str, float] = hint.setdefault(key, {})
    n = min(len(wids), vector.shape[0])
    for idx in range(n):
        bucket[wids[idx]] = float(vector[idx])


def _get_enzyme_vector(*, state: dict[str, Any], enzyme_wids: list[str]) -> np.ndarray:
    protein_counts = _get_nested_mapping(state, ("protein", "counts")) or {}
    complex_counts = _get_nested_mapping(state, ("complex", "counts")) or {}
    out = np.zeros(len(enzyme_wids), dtype=np.float64)
    for idx, wid in enumerate(enzyme_wids):
        if wid in protein_counts:
            out[idx] = float(protein_counts[wid])
        elif wid in complex_counts:
            out[idx] = float(complex_counts[wid])
    return out


def project_observable_from_state(
    *,
    process: Any,
    state: dict[str, Any],
    observable: str,
    wids: list[str],
    bound_enzymes_before: np.ndarray | None,
    store_path_override: dict[str, tuple[str, ...]] | None = None,
) -> np.ndarray:
    if observable == "boundEnzymes":
        store_path = observable_store_path(
            observable, state, store_path_override=store_path_override
        )
        store = _get_nested_mapping(state, store_path) if store_path is not None else None
        if isinstance(store, dict):
            return np.asarray(
                [float(store.get(wid, 0.0)) for wid in wids], dtype=np.float64
            ).reshape(-1)
        if bound_enzymes_before is None:
            return np.zeros(len(wids), dtype=np.float64)
        return np.asarray(bound_enzymes_before, dtype=np.float64).reshape(-1)
    if observable == "enzymes":
        store_path = observable_store_path(
            observable, state, store_path_override=store_path_override
        )
        store = _get_nested_mapping(state, store_path) if store_path is not None else None
        if isinstance(store, dict):
            return np.asarray(
                [float(store.get(wid, 0.0)) for wid in wids], dtype=np.float64
            ).reshape(-1)
        return _get_enzyme_vector(state=state, enzyme_wids=wids).reshape(-1)

    store_path = observable_store_path(observable, state, store_path_override=store_path_override)
    if store_path is None:
        return np.zeros(len(wids), dtype=np.float64)
    store = _get_nested_mapping(state, store_path) or {}
    return np.asarray([float(store.get(wid, 0.0)) for wid in wids], dtype=np.float64).reshape(-1)


def project_karr_vector(
    process: Any,
    observable: str,
    vector: np.ndarray,
    *,
    index_projection_attr: dict[str, str] | None = None,
    index_projection_literal: dict[str, Any] | None = None,
) -> np.ndarray:
    """Project a full-compartment Karr trace vector down to the OC process subset.

    Two override modes are supported (literal wins if both are set for the
    same observable):

    1. `index_projection_attr={observable: attr_name}` — the OC process exposes
       the subset's indices via an attribute (e.g. `active_protein_indices`).
       This is the typical case for "subset of subset" observables.

    2. `index_projection_literal={observable: indices}` — caller supplies the
       indices directly as an ndarray / sequence of ints. Useful when Karr
       dumps `(quantity, compartment)` flattened in column-major order and OC
       tracks only the cytosol compartment slice (e.g. metabolism's substrates
       trace is 1755 = 585 substrates x 3 compartments, OC tracks 585).

    If no projection is configured for `observable`, returns `vector` unchanged.
    """
    indices: Any | None = None
    if index_projection_literal:
        indices = index_projection_literal.get(observable)
    if indices is None and index_projection_attr:
        attr = index_projection_attr.get(observable)
        if attr is not None:
            indices = getattr(process, attr, None)
    if indices is None:
        return vector
    arr = np.asarray(vector, dtype=np.float64)
    idx_arr = np.asarray(indices, dtype=np.int64)
    return arr[idx_arr]


# --- Protein-decay 4820/482 projection ---
# Source-of-truth: Karr 2012 ProteinMonomer state class. The 10 form-state slots
# are constructed in order in:
#   data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+state/ProteinMonomer.m
# lines 95-104 (this.nascentIndexs through this.damagedIndexs, each
# (1:numMonomers)' offset from the previous block-end).
# That construction also confirms proteins vary fastest within a form block
# (col-major over a (n_proteins, n_forms) matrix). Keep this tuple in EXACT
# index order; downstream sigma uses .index(mature_form_name) on it.
KARR_MONOMER_FORM_ORDER: tuple[str, ...] = (
    "nascent",
    "processedI",
    "processedII",
    "signalSequence",
    "folded",
    "mature",
    "inactivated",
    "bound",
    "misfolded",
    "damaged",
)


def project_monomer_4820_to_482(m_form: np.ndarray, n_proteins: int = 482) -> np.ndarray:
    """Project a compartment-collapsed form-flattened monomer vector to base 482.

    Args:
        m_form: shape (4820,) - one entry per (form, protein) pair, with
            proteins varying fastest (col-major from a (n_proteins, n_forms)
            matrix).
        n_proteins: base protein count, default 482.

    Returns:
        shape (n_proteins,) - sum over all form slots per base protein.

    Raises:
        ValueError if m_form is not 1-D or if size is not a multiple of n_proteins.
    """
    if m_form.ndim != 1:
        raise ValueError(f"expected 1-D vector, got ndim={m_form.ndim}")
    if m_form.size % n_proteins != 0:
        raise ValueError(
            f"expected size divisible by {n_proteins}, got {m_form.size}"
        )
    n_forms = m_form.size // n_proteins
    return m_form.reshape(n_forms, n_proteins).sum(axis=0, dtype=np.float64)


def project_trace_matrix_to_482(m_full: np.ndarray, n_proteins: int = 482) -> np.ndarray:
    """Project a full-trace (n_compartments, 4820) matrix to base 482.

    Per Section 10 Q2: sums over ALL compartments (DNA compartment is empty
    in current traces but counted for future-proofing).

    Args:
        m_full: shape (n_compartments, 4820) typically (6, 4820).
        n_proteins: base protein count, default 482.

    Returns:
        shape (n_proteins,)

    Raises:
        ValueError if m_full is not 2-D.
    """
    if m_full.ndim != 2:
        raise ValueError(f"expected 2-D matrix, got ndim={m_full.ndim}")
    m_form = m_full.sum(axis=0, dtype=np.float64)
    return project_monomer_4820_to_482(m_form, n_proteins=n_proteins)


def scatter_monomer_482_to_4820(
    v_482: np.ndarray,
    form_order: tuple[str, ...],
    *,
    n_proteins: int = 482,
    mature_form_name: str = "mature",
) -> np.ndarray:
    """Scatter a 482-vector into a 4820-form-flattened vector at the 'mature' slot.

    HARNESS-INTERNAL ONLY. Never feed the output of this function into a
    process source — the compartment axis is collapsed and the form-axis
    placement is a canonical choice, not biology.

    Args:
        v_482: shape (482,) - base-protein vector to scatter.
        form_order: length-F tuple of form-state names in MATLAB index order
            (REQUIRED; comes from fixture metadata per Section 10 Q3). Must
            contain `mature_form_name`.
        n_proteins: base protein count, default 482.
        mature_form_name: form slot to scatter into, default "mature".

    Returns:
        shape (n_proteins * len(form_order),) - all zeros except at the
        mature slot, where v_482 is placed.

    Raises:
        ValueError if v_482 wrong shape, mature_form_name not in form_order,
        or form_order is empty.
    """
    if v_482.ndim != 1 or v_482.size != n_proteins:
        raise ValueError(f"expected shape ({n_proteins},), got {v_482.shape}")
    if not form_order:
        raise ValueError("form_order must be non-empty")
    if mature_form_name not in form_order:
        raise ValueError(
            f"mature form {mature_form_name!r} not in form_order {form_order!r}"
        )
    n_forms = len(form_order)
    mature_idx = form_order.index(mature_form_name)
    out = np.zeros(n_forms * n_proteins, dtype=np.float64)
    start = mature_idx * n_proteins
    out[start:start + n_proteins] = v_482
    return out


def refresh_allocator_views(process: Any, state: dict[str, Any]) -> None:
    substrates = state.get("substrates", {})
    if not isinstance(substrates, dict):
        return

    requests = state.get("requests", {})
    if isinstance(requests, dict):
        proc_req = requests.get(getattr(process, "name", ""), None)
        if isinstance(proc_req, dict):
            for wid in list(proc_req.keys()):
                if wid in substrates:
                    proc_req[wid] = float(max(0.0, float(substrates[wid])))

    allocated = state.get("substrates_allocated", {})
    if isinstance(allocated, dict):
        proc_alloc = allocated.get(getattr(process, "name", ""), None)
        if isinstance(proc_alloc, dict):
            for wid in list(proc_alloc.keys()):
                if wid in substrates:
                    proc_alloc[wid] = float(max(0.0, float(substrates[wid])))


def compute_composition_allocations(
    *,
    requests_by_process: dict[str, dict[str, float]],
    pool: dict[str, float],
) -> dict[str, dict[str, float]]:
    """Run Karr's real proportional-allocation arithmetic across every
    process contending for a shared substrate pool at the composition
    boundary.

    Wraps ``KarrAllocationStep.next_update`` (Karr's uncapped proportional
    fair share, floored --
    ``@Simulation/evolveState.m:24-37``) so simultaneous requests genuinely
    contend, instead of each process independently receiving the full
    observed pool. That independent-grant behavior is what
    ``refresh_allocator_views`` performs above, which is CORRECT ONLY for
    isolated single-process replay (Karr's ``states_before`` there is
    already that one process's post-allocation share -- see
    docs/phase_f/L2_0A_ALLOCATOR_INPUT_GATE.md, A05/D1) and WRONG at a
    multi-process composition boundary, where it grants every composed
    process the same shared pool value independently
    (docs/phase_f/INTEGRITY_AUDIT_PRE_L25.md Finding #20).

    ``requests_by_process`` and the returned allocation dict are both keyed
    by the *runtime* process name (``process.name``, e.g.
    ``"karr_translation_v3"``) -- the same identity space
    ``KarrAllocationStep`` itself normalizes via ``KEY_ALIASES``. A process
    with an all-zero (or empty) request dict is still enrolled as a
    consumer so it is reported with an explicit 0.0 allocation rather than
    silently dropped (mirrors the zero-demand-row guard in D3 of
    L2_0A_ALLOCATOR_INPUT_GATE.md).
    """
    if not isinstance(pool, dict) or not requests_by_process:
        return {}
    consumer_processes = [
        (proc_name, sorted(reqs.keys())) for proc_name, reqs in requests_by_process.items()
    ]
    all_wids = sorted({wid for reqs in requests_by_process.values() for wid in reqs} | set(pool))
    if not all_wids:
        return {}
    step = KarrAllocationStep({"consumer_processes": consumer_processes, "substrate_wids": all_wids})
    update = step.next_update(1.0, {"substrates": dict(pool), "requests": requests_by_process})
    return update.get("substrates_allocated", {})


def apply_composition_allocations(
    state: dict[str, Any],
    allocations: dict[str, dict[str, float]],
) -> None:
    """Write ``compute_composition_allocations`` output into
    ``state['substrates_allocated'][<process.name>]``.

    Only WIDs already declared by the process's own ``ports_schema`` (i.e.
    already present as keys in its ``substrates_allocated`` sub-dict) are
    overwritten. This never introduces keys a process's schema does not
    expect -- the same guard shape as ``refresh_allocator_views`` above.
    """
    allocated_root = state.get("substrates_allocated", {})
    if not isinstance(allocated_root, dict):
        return
    for proc_name, proc_alloc in allocations.items():
        target = allocated_root.get(proc_name)
        if not isinstance(target, dict):
            continue
        for wid, value in proc_alloc.items():
            if wid in target:
                target[wid] = float(value)


def refresh_allocator_views_composition(
    *,
    request_vectors: dict[str, dict[str, float]],
    state: dict[str, Any],
) -> None:
    """Composition-boundary allocator refresh: real contention, not a grant.

    Call this exactly ONCE per tick, for every process in the composition
    SIMULTANEOUSLY, before ANY of those processes' ``next_update`` has run
    this tick -- matching Karr's real per-tick semantics documented in
    ``docs/phase_f/L2_5_HARNESS_DESIGN.md`` Baseline fact 5
    (``@Simulation/evolveState.m``: allocation is precomputed for all
    processes, then each process executes with its fixed allocation).

    ``request_vectors`` must be keyed by ``process.name`` (the same key
    ``KarrAllocationStep`` and ``refresh_allocator_views`` use), typically
    built from each process's own Karr-oracle ``states_before`` substrate
    observation for the tick -- i.e. the same value
    ``refresh_allocator_views`` used to grant unconditionally, now submitted
    as a REQUEST that must contend with every other composed process's
    request against the shared ``state['substrates']`` pool.

    Calling this per-process, interleaved with execution (the previous
    ``refresh_allocator_views`` call site inside the composition tick
    loop), would reintroduce the idealized-grant bug one level down:
    processes later in composition order would see an already-partially-
    consumed pool credited to them in full, rather than contending for the
    tick-start pool alongside every other composed process. If the calling
    harness cannot collect every process's request before any process
    consumes, that is a phase-ordering bug in the harness, not something
    this function can paper over.
    """
    pool = state.get("substrates", {})
    if not isinstance(pool, dict) or not request_vectors:
        return
    allocations = compute_composition_allocations(requests_by_process=request_vectors, pool=pool)
    apply_composition_allocations(state, allocations)


def _iter_numeric_leaf_dicts(node: Any, prefix: str = "") -> list[tuple[str, dict[str, float]]]:
    if not isinstance(node, dict):
        return []
    out: list[tuple[str, dict[str, float]]] = []
    if node and all(not isinstance(v, dict) for v in node.values()):
        if all(isinstance(v, Number) for v in node.values()):
            out.append((prefix or "<root>", {str(k): float(v) for k, v in node.items()}))
        return out
    for k, v in node.items():
        child_prefix = f"{prefix}/{k}" if prefix else str(k)
        out.extend(_iter_numeric_leaf_dicts(v, child_prefix))
    return out


def collect_count_delta_dicts(update: dict[str, Any]) -> list[tuple[str, dict[str, float]]]:
    out: list[tuple[str, dict[str, float]]] = []
    for key in ("substrates", "protein", "rna", "complex", "boundEnzymes", "enzymes"):
        if key in update:
            out.extend(_iter_numeric_leaf_dicts(update[key], key))
    return out


def apply_count_update(state: dict[str, Any], update: dict[str, Any]) -> None:
    def _accumulate(target: dict[str, Any], delta: dict[str, Any]) -> None:
        for key, value in delta.items():
            if isinstance(value, dict):
                next_target = target.get(key)
                if not isinstance(next_target, dict):
                    next_target = {}
                    target[key] = next_target
                _accumulate(next_target, value)
                continue
            if isinstance(value, Number):
                prev = target.get(key, 0.0)
                try:
                    prev_f = float(prev)
                except Exception:
                    prev_f = 0.0
                target[key] = float(prev_f + float(value))
            else:
                target[key] = value

    for key in ("substrates", "protein", "rna", "complex", "boundEnzymes", "enzymes"):
        node = update.get(key)
        if isinstance(node, dict):
            target = state.get(key)
            if not isinstance(target, dict):
                target = {}
                state[key] = target
            _accumulate(target, node)


def assert_delta_integral(label: str, deltas: dict[str, float]) -> None:
    if not deltas:
        return
    for wid, delta in deltas.items():
        delta_f = float(delta)
        if not np.isfinite(delta_f):
            pytest.fail(f"L2a delta non-finite: store={label}, wid={wid}, delta={delta_f}")
        if delta_f != float(np.rint(delta_f)):
            pytest.fail(
                "L2a delta non-integral: "
                f"store={label}, wid={wid}, delta={delta_f} "
                "(Rule 2 clause 4: emitted count delta must be integral)"
            )


def audit_trace_mutated_ticks(
    trace: h5py.File,
    observables: tuple[str, ...],
    n_ticks: int,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for obs in observables:
        nz = 0
        for tick in range(n_ticks):
            before = cell_vector(trace, "states_before", obs, tick)
            after = cell_vector(trace, "states_after", obs, tick)
            if before.shape != after.shape or np.any(after != before):
                nz += 1
        counts[obs] = nz
    return counts


def assert_identity_or_tolerance(
    *,
    tick: int,
    observable: str,
    oc_after: np.ndarray,
    karr_after: np.ndarray,
    process_name: str | None = None,
) -> None:
    if oc_after.shape != karr_after.shape:
        pytest.fail(
            "L2a mismatch record: "
            f"tick={tick}, observable={observable}, index=-1, "
            f"oc_shape={oc_after.shape}, karr_shape={karr_after.shape}"
        )

    karr_int_part = np.rint(karr_after)
    karr_snapped = False
    if not np.array_equal(karr_int_part, karr_after):
        karr_frac = np.abs(karr_after - karr_int_part)
        if np.all(karr_frac < 1e-9):
            # MATLAB trace serialization injects ~1e-11 float noise on integer-valued observables; snap-to-integer below 1e-9 preserves correctness while eating noise.
            karr_after = karr_int_part.astype(np.float64)
            karr_snapped = True
        else:
            bad = int(np.flatnonzero(karr_frac >= 1e-9)[0])
            pytest.fail(
                "L2a oracle non-integral: "
                f"tick={tick}, observable={observable}, index={bad}, "
                f"karr_val={float(karr_after[bad])} (expected integral count)"
            )

    oc_int_part = np.rint(oc_after)
    if not np.array_equal(oc_int_part, oc_after):
        oc_frac = np.abs(oc_after - oc_int_part)
        if karr_snapped and np.all(oc_frac < 1e-9):
            oc_after = oc_int_part.astype(np.float64)
        else:
            bad = int(np.flatnonzero(oc_int_part != oc_after)[0])
            pytest.fail(
                "L2a oc non-integral: "
                f"tick={tick}, observable={observable}, index={bad}, "
                f"oc_val={float(oc_after[bad])} (expected integral count)"
            )

    mismatch = oc_after != karr_after
    diff = oc_after - karr_after
    if np.any(mismatch):
        if _use_calibrated_l2_tolerances():
            inferred_name = _infer_current_l2_process_name(process_name)
            rtol, atol = _resolve_l2_tolerance_pair(inferred_name)
            if np.allclose(oc_after, karr_after, rtol=rtol, atol=atol):
                return
        idx = int(np.flatnonzero(mismatch)[0])
        pytest.fail(
            "L2a mismatch record: "
            f"tick={tick}, observable={observable}, index={idx}, "
            f"oc_val={float(oc_after[idx])}, karr_val={float(karr_after[idx])}, "
            f"diff={float(diff[idx])}"
        )


def _use_calibrated_l2_tolerances() -> bool:
    return os.environ.get(_L2_USE_CALIBRATED_ENV, "0") == "1"


@lru_cache(maxsize=1)
def load_l2_tolerance_table() -> dict[str, tuple[float, float]]:
    """Load calibrated per-process (rtol, atol) from L2_TOLERANCE_TABLE.md."""
    table_path = _REPO_ROOT / _L2_TOLERANCE_TABLE_REL
    if not table_path.exists():
        return {}

    out: dict[str, tuple[float, float]] = {}
    in_table = False
    for raw in table_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not in_table:
            if line.startswith("| process_name |") and "rtol_median" in line:
                in_table = True
            continue
        if not line.startswith("|"):
            break
        if line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 9:
            continue
        process = cells[0]
        rtol_txt = cells[3]
        atol_txt = cells[4]
        if not process:
            continue
        try:
            rtol = float(rtol_txt)
            atol = float(atol_txt)
        except ValueError:
            continue
        out[process] = (rtol, atol)
    return out


def _infer_current_l2_process_name(explicit_process_name: str | None = None) -> str | None:
    if explicit_process_name:
        return explicit_process_name

    current = os.environ.get("PYTEST_CURRENT_TEST", "")
    match = re.search(r"test_(karr_[a-z0-9_]+)_l2_replay\.py", current)
    if match:
        return match.group(1)

    for frame in inspect.stack():
        frame_path = str(frame.filename).replace("\\", "/")
        match = re.search(r"test_(karr_[a-z0-9_]+)_l2_replay\.py$", frame_path)
        if match:
            return match.group(1)
    return None


def _resolve_l2_tolerance_pair(process_name: str | None) -> tuple[float, float]:
    table = load_l2_tolerance_table()
    if process_name:
        if process_name in table:
            return table[process_name]
        if process_name.endswith("_light"):
            canonical = process_name[: -len("_light")]
            if canonical in table:
                return table[canonical]
        light_name = f"{process_name}_light"
        if light_name in table:
            return table[light_name]
    return (_L2_BUCKET_RTOL_DEFAULT, _L2_BUCKET_ATOL_DEFAULT)


# ---------------------------------------------------------------------------
# L2.1 anti-cheat helpers (added 2026-05-30; see HARNESS_CRITIQUE_GPT55.md).
#
# Two helpers, both opt-in. Per-process tests may wrap process construction
# and/or `next_update` calls with these to enforce that the SUT does not read
# the L2 oracle directly. The structural defense lives in
# `test_l2_no_oracle_dependency.py`; these runtime helpers are a defense in
# depth for cases where source-scan is insufficient (e.g. obfuscated paths,
# indirect importlib loads).
# ---------------------------------------------------------------------------

import builtins as _builtins  # noqa: E402  (import deliberately late, helpers only)
from contextlib import contextmanager  # noqa: E402

_ORACLE_PATH_NEEDLES: tuple[str, ...] = (
    "per_process_traces",
    "_100ticks.mat",
    "karr_native",
)


def _is_oracle_path(path: object) -> bool:
    """Best-effort: does this look like an L2 oracle trace path?"""
    try:
        text = str(path)
    except Exception:  # noqa: BLE001 — defensive: anything that can't str() is fine
        return False
    norm = text.replace("\\", "/").lower()
    return any(needle.lower() in norm for needle in _ORACLE_PATH_NEEDLES)


@contextmanager
def forbid_sut_oracle_file_io():
    """Context manager that fails the test if SUT code opens an L2 oracle file.

    Patches `h5py.File`, `builtins.open`, and `pathlib.Path.open` to reject any
    call whose path-like argument matches the L2 oracle convention. Intended
    to wrap process construction and `next_update` invocations:

        with forbid_sut_oracle_file_io():
            process = KarrFooProcess(config)

        # ... later ...
        with forbid_sut_oracle_file_io():
            update = process.next_update(dt, state)

    The harness itself MUST NOT open the oracle inside this block. Call
    `cell_vector(...)`, `resolve_trace_path(...)`, and trace-aware fixture
    code outside the guarded region.
    """
    real_h5py_file = h5py.File
    real_open = _builtins.open
    real_path_open = Path.open

    def _guarded_h5py_file(name, *args, **kwargs):
        if _is_oracle_path(name):
            pytest.fail(
                "SUT attempted to open L2 oracle via h5py.File: "
                f"{name}. Process source must not read the replay oracle. "
                "See tests/vivarium/test_l2_no_oracle_dependency.py."
            )
        return real_h5py_file(name, *args, **kwargs)

    def _guarded_open(file, *args, **kwargs):
        if _is_oracle_path(file):
            pytest.fail(
                f"SUT attempted to open L2 oracle via open(): {file}. "
                "Process source must not read the replay oracle."
            )
        return real_open(file, *args, **kwargs)

    def _guarded_path_open(self, *args, **kwargs):
        if _is_oracle_path(self):
            pytest.fail(
                f"SUT attempted to open L2 oracle via Path.open(): {self}. "
                "Process source must not read the replay oracle."
            )
        return real_path_open(self, *args, **kwargs)

    h5py.File = _guarded_h5py_file
    _builtins.open = _guarded_open
    Path.open = _guarded_path_open
    try:
        yield
    finally:
        h5py.File = real_h5py_file
        _builtins.open = real_open
        Path.open = real_path_open


def assert_enzyme_mirrors_consistent(state: dict[str, Any]) -> None:
    """Catch the H1 mirror-asymmetry bug.

    Post-`apply_count_update`, `state["enzymes"][wid]` must agree with whatever
    is in `state["protein"]["counts"][wid]` or `state["complex"]["counts"][wid]`
    for the same WID. If a process emits to BOTH the `enzymes` channel and the
    legacy `protein`/`complex` channel for the same WID with mismatched deltas,
    only this check will surface it — the per-observable projection reads
    `state["enzymes"]` first (see `project_observable_from_state`) and silently
    hides the divergence.

    Call after `_apply_update` in per-process tests:

        _apply_update(state, update, process)
        assert_enzyme_mirrors_consistent(state)
    """
    enz = state.get("enzymes")
    if not isinstance(enz, dict):
        return
    protein_counts = ((state.get("protein") or {}).get("counts") or {})
    complex_counts = ((state.get("complex") or {}).get("counts") or {})
    if not isinstance(protein_counts, dict):
        protein_counts = {}
    if not isinstance(complex_counts, dict):
        complex_counts = {}

    for wid, enz_val in enz.items():
        try:
            enz_f = float(enz_val)
        except (TypeError, ValueError):
            continue
        if wid in protein_counts:
            try:
                p_f = float(protein_counts[wid])
            except (TypeError, ValueError):
                continue
            if p_f != enz_f:
                pytest.fail(
                    f"Enzyme mirror divergence: wid={wid!r}, "
                    f"state['enzymes']={enz_f}, state['protein']['counts']={p_f}. "
                    "Process likely emitted update to both channels for the same WID. "
                    "Emit to ONE channel only."
                )
        if wid in complex_counts:
            try:
                c_f = float(complex_counts[wid])
            except (TypeError, ValueError):
                continue
            if c_f != enz_f:
                pytest.fail(
                    f"Enzyme mirror divergence: wid={wid!r}, "
                    f"state['enzymes']={enz_f}, state['complex']['counts']={c_f}. "
                    "Process likely emitted update to both channels for the same WID. "
                    "Emit to ONE channel only."
                )
