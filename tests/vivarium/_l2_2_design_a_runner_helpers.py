from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from scipy.stats import wasserstein_distance


_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

from l2_replay_common import (  # noqa: E402
    apply_count_update,
    build_state_template,
    forbid_sut_oracle_file_io,
    load_fixture_channel_wids,
    overlay_observable_into_state,
    overlay_trace_after_hint,
    project_vector_onto_wids,
    project_observable_from_state,
    refresh_allocator_views,
)
from opencell.m1 import karr_metabolism as m1_karr_metabolism  # noqa: E402
from opencell.vivarium.karr_metabolism import KarrMetabolismProcess  # noqa: E402
from opencell.vivarium.karr_transcription import KarrTranscriptionProcess  # noqa: E402


L2_2_VALIDATION_SEED = 0xCA11B
ABSOLUTE_FLOOR = 1.0
TRIVIAL_RNG_K_ENG = 2.0
ALGORITHMIC_DEEP_K_ENG = 3.0
_METABOLISM_ORACLE_PATH = _REPO_ROOT / "data" / "karr_fixtures" / "per_process_replay" / "Metabolism.npz"
_TRANSCRIPTION_ORACLE_PATH = (
    _REPO_ROOT / "data" / "karr_fixtures" / "per_process_replay" / "Transcription.npz"
)
_TRANSCRIPTION_FIXTURE_PATH = _REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "Transcription_flat.mat"
_RNA_STORE_PATH_OVERRIDE = {"RNAs": ("rna", "counts")}


def load_karr_oracle(process: str) -> dict[str, Any]:
    """Load the canonical Karr replay fixture for a Design-A process."""
    loaders = {
        "Metabolism": _load_metabolism_oracle,
        "Transcription": _load_transcription_oracle,
    }
    loader = loaders.get(process)
    if loader is None:
        raise ValueError(f"Unsupported Design-A process {process!r}.")
    return loader()


def _load_metabolism_oracle() -> dict[str, Any]:
    if not _METABOLISM_ORACLE_PATH.exists():
        raise FileNotFoundError(f"Missing Metabolism oracle fixture: {_METABOLISM_ORACLE_PATH}")

    with np.load(_METABOLISM_ORACLE_PATH, allow_pickle=False) as payload:
        before_substrates = np.asarray(payload["state_before__substrates"], dtype=np.float64)[:, 0, :]
        after_substrates = np.asarray(payload["states_after__substrates"], dtype=np.float64)[:, 0, :]
        before_enzymes = np.asarray(payload["state_before__enzymes"], dtype=np.float64)[:, 0, :]
        before_bound = np.asarray(payload["state_before__boundEnzymes"], dtype=np.float64)[:, 0, :]

    return {
        "process": "Metabolism",
        "oracle_path": _METABOLISM_ORACLE_PATH,
        "canonical_seed_count": 1,
        "n_ticks_available": int(before_substrates.shape[0]),
        "before_substrates": before_substrates[np.newaxis, :, :],
        "after_substrates": after_substrates[np.newaxis, :, :],
        "before_enzymes": before_enzymes[np.newaxis, :, :],
        "before_bound_enzymes": before_bound[np.newaxis, :, :],
    }


def _load_transcription_oracle() -> dict[str, Any]:
    if not _TRANSCRIPTION_ORACLE_PATH.exists():
        raise FileNotFoundError(f"Missing Transcription oracle fixture: {_TRANSCRIPTION_ORACLE_PATH}")

    with np.load(_TRANSCRIPTION_ORACLE_PATH, allow_pickle=False) as payload:
        before_substrates_raw = np.asarray(payload["state_before__substrates"], dtype=np.float64)[:, 0, :]
        after_substrates_raw = np.asarray(payload["states_after__substrates"], dtype=np.float64)[:, 0, :]
        before_enzymes = np.asarray(payload["state_before__enzymes"], dtype=np.float64)[:, 0, :]
        before_bound = np.asarray(payload["state_before__boundEnzymes"], dtype=np.float64)[:, 0, :]
        before_rnas_raw = np.asarray(payload["state_before__RNAs"], dtype=np.float64)[:, 0, :]
        after_rnas_raw = np.asarray(payload["states_after__RNAs"], dtype=np.float64)[:, 0, :]
        after_bound = np.asarray(payload["states_after__boundEnzymes"], dtype=np.float64)[:, 0, :]

    before_substrates = _project_transcription_substrate_cube(before_substrates_raw)
    after_substrates = _project_transcription_substrate_cube(after_substrates_raw)
    before_rnas = _project_transcription_rna_cube(before_rnas_raw)
    after_rnas = _project_transcription_rna_cube(after_rnas_raw)

    return {
        "process": "Transcription",
        "oracle_path": _TRANSCRIPTION_ORACLE_PATH,
        "canonical_seed_count": 1,
        "n_ticks_available": int(before_substrates.shape[0]),
        "before_substrates": before_substrates[np.newaxis, :, :],
        "before_enzymes": before_enzymes[np.newaxis, :, :],
        "before_bound_enzymes": before_bound[np.newaxis, :, :],
        "before_rnas": before_rnas[np.newaxis, :, :],
        "after_substrates": after_substrates[np.newaxis, :, :],
        "after_rnas": after_rnas[np.newaxis, :, :],
        "after_bound_enzymes": after_bound[np.newaxis, :, :],
    }


@lru_cache(maxsize=None)
def _metabolism_model() -> Any:
    return m1_karr_metabolism.load_default()


@lru_cache(maxsize=None)
def _metabolism_process(seed: int) -> KarrMetabolismProcess:
    # Static Metabolism replay is state-driven; caching avoids repeated model loads.
    model = _metabolism_model()
    with forbid_sut_oracle_file_io():
        return KarrMetabolismProcess({"rng_seed": int(seed), "model": model})


@lru_cache(maxsize=None)
def _transcription_process(seed: int) -> KarrTranscriptionProcess:
    return KarrTranscriptionProcess({"rng_seed": int(seed)})


def _sample_seed(seed: int, tick: int) -> int:
    ss = np.random.SeedSequence([L2_2_VALIDATION_SEED, int(seed), int(tick)])
    return int(ss.generate_state(1, dtype=np.uint32)[0])


def run_oc_tick(process_name: str, seed: int, tick: int, state: dict[str, Any]) -> dict[str, Any]:
    runners = {
        "Metabolism": _run_metabolism_tick,
        "Transcription": _run_transcription_tick,
    }
    runner = runners.get(process_name)
    if runner is None:
        raise ValueError(f"Unsupported Design-A process {process_name!r}.")
    return runner(seed=int(seed), tick=int(tick), state=state)


def _run_metabolism_tick(seed: int, tick: int, state: dict[str, Any]) -> dict[str, Any]:
    """Run one OpenCell Metabolism tick from a prepared state snapshot."""
    process = _metabolism_process(_sample_seed(seed, tick))
    runtime_state = build_state_template(process)
    substrate_wids = list(state["substrate_wids"])
    enzyme_wids = list(state["enzyme_wids"])

    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="substrates",
        vector=np.asarray(state["oracle_before_substrates"], dtype=np.float64),
        wids=substrate_wids,
    )
    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="enzymes",
        vector=np.asarray(state["oracle_before_enzymes"], dtype=np.float64),
        wids=enzyme_wids,
    )
    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="boundEnzymes",
        vector=np.asarray(state["oracle_before_bound_enzymes"], dtype=np.float64),
        wids=enzyme_wids,
    )
    overlay_trace_after_hint(
        state=runtime_state,
        observable="substrates",
        vector=np.asarray(state["oracle_after_substrates"], dtype=np.float64),
        wids=substrate_wids,
    )
    refresh_allocator_views(process, runtime_state)
    with forbid_sut_oracle_file_io():
        update = process.next_update(1.0, runtime_state)
    apply_count_update(runtime_state, update)
    oc_after = project_observable_from_state(
        process=process,
        state=runtime_state,
        observable="substrates",
        wids=substrate_wids,
        bound_enzymes_before=np.asarray(state["oracle_before_bound_enzymes"], dtype=np.float64),
    )
    return {
        "substrates": np.asarray(oc_after, dtype=np.float64),
        "sample_seed": _sample_seed(seed, tick),
    }


def _run_transcription_tick(seed: int, tick: int, state: dict[str, Any]) -> dict[str, Any]:
    """Run one OpenCell Transcription tick from a prepared state snapshot."""
    process = _transcription_process(_sample_seed(seed, tick))
    runtime_state = build_state_template(process)
    substrate_wids = list(state["substrate_wids"])
    enzyme_wids = list(state["enzyme_wids"])
    rna_wids = list(state["rna_wids"])

    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="substrates",
        vector=np.asarray(state["oracle_before_substrates"], dtype=np.float64),
        wids=substrate_wids,
    )
    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="enzymes",
        vector=np.asarray(state["oracle_before_enzymes"], dtype=np.float64),
        wids=enzyme_wids,
    )
    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="boundEnzymes",
        vector=np.asarray(state["oracle_before_bound_enzymes"], dtype=np.float64),
        wids=enzyme_wids,
    )
    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="RNAs",
        vector=np.asarray(state["oracle_before_rnas"], dtype=np.float64),
        wids=rna_wids,
        store_path_override=_RNA_STORE_PATH_OVERRIDE,
    )
    overlay_trace_after_hint(
        state=runtime_state,
        observable="substrates",
        vector=np.asarray(state["oracle_after_substrates"], dtype=np.float64),
        wids=substrate_wids,
    )
    overlay_trace_after_hint(
        state=runtime_state,
        observable="boundEnzymes",
        vector=np.asarray(state["oracle_after_bound_enzymes"], dtype=np.float64),
        wids=enzyme_wids,
    )
    overlay_trace_after_hint(
        state=runtime_state,
        observable="RNAs",
        vector=np.asarray(state["oracle_after_rnas"], dtype=np.float64),
        wids=rna_wids,
    )
    refresh_allocator_views(process, runtime_state)
    with forbid_sut_oracle_file_io():
        update = process.next_update(1.0, runtime_state)
    apply_count_update(runtime_state, update)
    return {
        "substrates": np.asarray(
            project_observable_from_state(
                process=process,
                state=runtime_state,
                observable="substrates",
                wids=substrate_wids,
                bound_enzymes_before=np.asarray(state["oracle_before_bound_enzymes"], dtype=np.float64),
            ),
            dtype=np.float64,
        ),
        "RNAs": np.asarray(
            project_observable_from_state(
                process=process,
                state=runtime_state,
                observable="RNAs",
                wids=rna_wids,
                bound_enzymes_before=np.asarray(state["oracle_before_bound_enzymes"], dtype=np.float64),
                store_path_override=_RNA_STORE_PATH_OVERRIDE,
            ),
            dtype=np.float64,
        ),
        "boundEnzymes": np.asarray(
            project_observable_from_state(
                process=process,
                state=runtime_state,
                observable="boundEnzymes",
                wids=enzyme_wids,
                bound_enzymes_before=np.asarray(state["oracle_before_bound_enzymes"], dtype=np.float64),
            ),
            dtype=np.float64,
        ),
        "sample_seed": _sample_seed(seed, tick),
    }


def compute_w1(oc: Any, karr: Any) -> float:
    """Compute the channel Wasserstein distance between OC and Karr samples."""
    oc_arr = np.asarray(oc, dtype=np.float64).reshape(-1)
    karr_arr = np.asarray(karr, dtype=np.float64).reshape(-1)
    return float(wasserstein_distance(oc_arr, karr_arr))


def compute_null_q95(
    *,
    karr_vectors: np.ndarray,
    bootstrap_B: int,
    rng_seed: int = L2_2_VALIDATION_SEED,
) -> dict[str, Any]:
    """Compute the Karr-only null q95 using seed-level bootstrap resampling."""
    karr_arr = np.asarray(karr_vectors, dtype=np.float64)
    if karr_arr.ndim != 3:
        raise ValueError(f"karr_vectors must have shape (seed, tick, dim); got {karr_arr.shape}")

    n_seeds, n_ticks, _ = karr_arr.shape
    rng = np.random.default_rng(int(rng_seed))
    bootstrap_values = np.zeros(int(bootstrap_B), dtype=np.float64)
    for idx in range(int(bootstrap_B)):
        lhs = rng.integers(0, n_seeds, size=n_seeds)
        rhs = rng.integers(0, n_seeds, size=n_seeds)
        per_sample = []
        for lhs_seed, rhs_seed in zip(lhs, rhs, strict=False):
            for tick in range(n_ticks):
                per_sample.append(compute_w1(karr_arr[int(lhs_seed), tick], karr_arr[int(rhs_seed), tick]))
        bootstrap_values[idx] = float(np.mean(per_sample)) if per_sample else 0.0

    return {
        "q95_null": float(np.percentile(bootstrap_values, 95)) if bootstrap_values.size else 0.0,
        "bootstrap_values": bootstrap_values,
        "bootstrap_B": int(bootstrap_B),
        "n_karr_seeds": int(n_seeds),
        "n_ticks": int(n_ticks),
    }


@lru_cache(maxsize=1)
def _transcription_projection_inputs() -> dict[str, Any]:
    process = _transcription_process(0)
    fixture = loadmat(str(_TRANSCRIPTION_FIXTURE_PATH), squeeze_me=True, struct_as_record=False)["data"].fixture
    states = np.asarray(getattr(fixture, "states", []), dtype=object).reshape(-1)
    rna_gene_projection: np.ndarray | None = None
    for state in states:
        if hasattr(state, "nascentRNAGeneComposition"):
            rna_gene_projection = np.asarray(getattr(state, "nascentRNAGeneComposition"), dtype=np.float64)
            break
    if rna_gene_projection is None:
        raise ValueError(
            f"Missing nascentRNAGeneComposition in Transcription fixture: {_TRANSCRIPTION_FIXTURE_PATH}"
        )
    return {
        "karr_substrate_wids": tuple(load_fixture_channel_wids("Transcription", "substrates")),
        "oc_substrate_wids": tuple(str(x) for x in process.substrate_wids),
        "rna_gene_projection": rna_gene_projection,
        "oc_rna_wids": tuple(str(x) for x in process.gene_ids),
    }


def _project_transcription_substrate_cube(values: np.ndarray) -> np.ndarray:
    inputs = _transcription_projection_inputs()
    arr = np.asarray(values, dtype=np.float64)
    out = np.zeros((arr.shape[0], len(inputs["oc_substrate_wids"])), dtype=np.float64)
    for tick in range(arr.shape[0]):
        out[tick, :] = project_vector_onto_wids(
            karr_vector=arr[tick],
            karr_wids=inputs["karr_substrate_wids"],
            oc_wids=inputs["oc_substrate_wids"],
        )
    return out


def _project_transcription_rna_cube(values: np.ndarray) -> np.ndarray:
    inputs = _transcription_projection_inputs()
    arr = np.asarray(values, dtype=np.float64)
    projection = np.asarray(inputs["rna_gene_projection"], dtype=np.float64)
    if arr.shape[1] != projection.shape[1]:
        raise ValueError(
            "Transcription RNA oracle width does not match nascentRNAGeneComposition: "
            f"{arr.shape[1]} vs {projection.shape[1]}"
        )
    return np.asarray(arr @ projection.T, dtype=np.float64)


__all__ = [
    "ALGORITHMIC_DEEP_K_ENG",
    "ABSOLUTE_FLOOR",
    "L2_2_VALIDATION_SEED",
    "TRIVIAL_RNG_K_ENG",
    "_METABOLISM_ORACLE_PATH",
    "_TRANSCRIPTION_ORACLE_PATH",
    "compute_null_q95",
    "compute_w1",
    "load_karr_oracle",
    "run_oc_tick",
]
