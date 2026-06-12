from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import h5py
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
    project_trace_matrix_to_482,
    refresh_allocator_views,
)
from opencell.m3 import translation as m3_karr_translation  # noqa: E402
from opencell.m1 import karr_metabolism as m1_karr_metabolism  # noqa: E402
from opencell.vivarium.karr_metabolism import KarrMetabolismProcess  # noqa: E402
from opencell.vivarium.karr_translation import KarrTranslationProcess  # noqa: E402
from opencell.vivarium.karr_transcription import KarrTranscriptionProcess  # noqa: E402
from opencell.vivarium.karr_rna_decay import RnaDecayLightProcess  # noqa: E402
from opencell.vivarium.karr_rna_processing import KarrRNAProcessingProcess  # noqa: E402
from opencell.vivarium.karr_rna_modification import KarrRNAModificationProcess  # noqa: E402
from opencell.vivarium.karr_trna_aminoacylation import KarrTRNAAminoacylationProcess  # noqa: E402
from opencell.vivarium.karr_protein_decay_light import ProteinDecayLightProcess  # noqa: E402
from opencell.vivarium.karr_cytokinesis import KarrCytokinesisProcess  # noqa: E402
from opencell.vivarium.karr_macromolecular_complexation import (  # noqa: E402
    MacromolecularComplexationProcess,
)


_ACTUAL_REPO_ROOT = Path(__file__).resolve().parents[2]
L2_2_VALIDATION_SEED = 0xCA11B
ABSOLUTE_FLOOR = 1.0
TRIVIAL_RNG_K_ENG = 2.0
ALGORITHMIC_SHALLOW_K_ENG = 2.0
ALGORITHMIC_DEEP_K_ENG = 3.0
_METABOLISM_ORACLE_PATH = _REPO_ROOT / "data" / "karr_fixtures" / "per_process_replay" / "Metabolism.npz"
_TRANSLATION_ORACLE_PATH = (
    _REPO_ROOT / "data" / "karr_fixtures" / "per_process_replay" / "Translation.npz"
)
_TRANSCRIPTION_ORACLE_PATH = (
    _REPO_ROOT / "data" / "karr_fixtures" / "per_process_replay" / "Transcription.npz"
)
_TRANSCRIPTION_FIXTURE_PATH = _REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "Transcription_flat.mat"
_RNA_DECAY_ORACLE_PATH = _REPO_ROOT / "data" / "karr_fixtures" / "per_process_replay" / "RNADecay.npz"
_PROTEIN_DECAY_ORACLE_PATH = (
    _REPO_ROOT / "data" / "karr_fixtures" / "per_process_replay" / "ProteinDecay.npz"
)
_CYTOKINESIS_ORACLE_PATH = (
    _REPO_ROOT / "data" / "karr_fixtures" / "per_process_replay" / "Cytokinesis.npz"
)
_MACROMOL_MONOMER_STORE_PATH_OVERRIDE = {"monomers": ("substrates",)}
_TRANSLATION_MRNA_STORE_PATH_OVERRIDE = {"mRNAs": ("rna", "counts")}
_RNA_STORE_PATH_OVERRIDE = {"RNAs": ("rna", "counts")}
_RNA_SLOT_COUNTS_STATE_KEY = "_l2_rna_slot_counts"
_RNA_SLOT_WIDS_STATE_KEY = "_l2_rna_slot_wids"
_EXTERNAL_V2_PROCESS_ROOT_FALLBACK = frozenset(
    {"RNAProcessing", "RNAModification", "tRNAAminoacylation"}
)


def _karr_native_root() -> Path:
    return _REPO_ROOT / "data" / "m1_sources" / "karr_native"


def _karr_native_candidate_roots(process_name: str) -> tuple[Path, ...]:
    candidates = [_karr_native_root()]
    if (
        process_name in _EXTERNAL_V2_PROCESS_ROOT_FALLBACK
        and _REPO_ROOT == _ACTUAL_REPO_ROOT
    ):
        candidates.extend(
            (
                Path("E:/opencell/data/m1_sources/karr_native"),
                Path("/mnt/e/opencell/data/m1_sources/karr_native"),
            )
        )
    seen: set[str] = set()
    unique: list[Path] = []
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return tuple(unique)


def _v2_seed_mat_path(process_name: str, seed: int) -> Path:
    rel = Path(f"per_process_traces_v2_s{int(seed):03d}") / f"{process_name}_100ticks.mat"
    for root in _karr_native_candidate_roots(process_name):
        candidate = root / rel
        if candidate.exists():
            return candidate
    return _karr_native_root() / rel


def _ensembles_seed_mat_path(process_name: str, seed: int) -> Path:
    return (
        _karr_native_root()
        / "ensembles"
        / str(process_name).lower()
        / f"seed_{int(seed):03d}"
        / f"{process_name}_100ticks.mat"
    )


def _ensembles_manifest_path(process_name: str) -> Path:
    return _karr_native_root() / "ensembles" / str(process_name).lower() / "MANIFEST.json"


def _legacy_seed_slice(legacy_oracle: dict[str, Any], key: str, seed_count: int) -> np.ndarray:
    arr = np.asarray(legacy_oracle[key], dtype=np.float64)
    if arr.ndim != 3:
        raise ValueError(f"Legacy oracle key {key!r} must have shape (seed, tick, dim); got {arr.shape}")
    if arr.shape[0] == int(seed_count):
        return np.asarray(arr, dtype=np.float64)
    if arr.shape[0] != 1:
        raise ValueError(
            f"Legacy oracle key {key!r} cannot be expanded to {seed_count} seeds from shape {arr.shape}"
        )
    return np.repeat(arr, int(seed_count), axis=0)


def _matlab_ref_to_vector(handle: h5py.File, ref: Any) -> np.ndarray:
    if not ref:
        raise ValueError("Encountered null HDF5 reference in MATLAB trace cell array.")
    arr = np.asarray(handle[ref][()], dtype=np.float64)
    return np.asarray(arr.reshape(-1), dtype=np.float64)


def _matlab_channel_matrix(handle: h5py.File, dataset: h5py.Dataset) -> np.ndarray:
    if dataset.ndim != 2 or 1 not in dataset.shape:
        raise ValueError(
            "MATLAB trace channel must be a 2D cell array with a singleton axis; "
            f"got {dataset.name} shape={dataset.shape}"
        )
    if dataset.shape[0] == 1:
        refs = [dataset[0, tick] for tick in range(dataset.shape[1])]
    else:
        refs = [dataset[tick, 0] for tick in range(dataset.shape[0])]
    vectors = [_matlab_ref_to_vector(handle, ref) for ref in refs]
    widths = {int(vector.shape[0]) for vector in vectors}
    if len(widths) > 1:
        raise ValueError(
            f"Inconsistent vector widths in {dataset.name}: {sorted(widths)}"
        )
    return np.asarray(np.stack(vectors, axis=0), dtype=np.float64)


def _load_seeded_mat_channels(seed_paths: list[Path]) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], int]:
    before_by_channel: dict[str, list[np.ndarray]] = {}
    after_by_channel: dict[str, list[np.ndarray]] = {}
    before_keys_expected: tuple[str, ...] | None = None
    after_keys_expected: tuple[str, ...] | None = None
    n_ticks_expected: int | None = None

    for seed_path in seed_paths:
        with h5py.File(seed_path, "r") as handle:
            if "states_before" not in handle or "states_after" not in handle:
                raise ValueError(f"Missing states_before/states_after groups in {seed_path}")

            before_group = handle["states_before"]
            after_group = handle["states_after"]
            before_keys = tuple(sorted(str(key) for key in before_group.keys()))
            after_keys = tuple(sorted(str(key) for key in after_group.keys()))
            if before_keys_expected is None:
                before_keys_expected = before_keys
                after_keys_expected = after_keys
            elif before_keys != before_keys_expected or after_keys != after_keys_expected:
                raise ValueError(
                    "Observable schema drift across ensemble seeds: "
                    f"{seed_path} before={before_keys} after={after_keys}; "
                    f"expected before={before_keys_expected} after={after_keys_expected}"
                )

            for channel in before_keys:
                matrix = _matlab_channel_matrix(handle, before_group[channel])
                if n_ticks_expected is None:
                    n_ticks_expected = int(matrix.shape[0])
                elif matrix.shape[0] != n_ticks_expected:
                    raise ValueError(
                        f"Tick-count drift in {seed_path} channel {channel!r}: "
                        f"{matrix.shape[0]} vs expected {n_ticks_expected}"
                    )
                before_by_channel.setdefault(channel, []).append(matrix)

            for channel in after_keys:
                matrix = _matlab_channel_matrix(handle, after_group[channel])
                if n_ticks_expected is None:
                    n_ticks_expected = int(matrix.shape[0])
                elif matrix.shape[0] != n_ticks_expected:
                    raise ValueError(
                        f"Tick-count drift in {seed_path} channel {channel!r}: "
                        f"{matrix.shape[0]} vs expected {n_ticks_expected}"
                    )
                after_by_channel.setdefault(channel, []).append(matrix)

    before_stacked = {
        channel: np.asarray(np.stack(matrices, axis=0), dtype=np.float64)
        for channel, matrices in before_by_channel.items()
    }
    after_stacked = {
        channel: np.asarray(np.stack(matrices, axis=0), dtype=np.float64)
        for channel, matrices in after_by_channel.items()
    }
    return before_stacked, after_stacked, int(n_ticks_expected or 0)


def _required_ensemble_keys(process_name: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if process_name == "Metabolism":
        return ("substrates", "enzymes", "boundEnzymes"), ("substrates",)
    if process_name == "Translation":
        return ("substrates", "enzymes", "boundEnzymes", "monomers", "mRNAs"), (
            "substrates",
            "monomers",
            "boundEnzymes",
        )
    if process_name == "Transcription":
        return ("substrates", "enzymes", "boundEnzymes", "RNAs"), (
            "substrates",
            "RNAs",
            "boundEnzymes",
        )
    if process_name == "RNADecay":
        return ("substrates", "enzymes", "boundEnzymes", "RNAs"), ("substrates", "RNAs")
    if process_name == "RNAProcessing":
        return (
            "substrates",
            "enzymes",
            "boundEnzymes",
            "unprocessedRNAs",
            "processedRNAs",
            "intergenicRNAs",
        ), ("substrates", "unprocessedRNAs", "processedRNAs", "intergenicRNAs")
    if process_name == "RNAModification":
        return (
            "substrates",
            "enzymes",
            "boundEnzymes",
            "unmodifiedRNAs",
            "modifiedRNAs",
        ), ("substrates", "unmodifiedRNAs", "modifiedRNAs")
    if process_name == "tRNAAminoacylation":
        return (
            "substrates",
            "enzymes",
            "boundEnzymes",
            "freeRNAs",
            "aminoacylatedRNAs",
        ), ("substrates", "freeRNAs", "aminoacylatedRNAs")
    if process_name == "ProteinDecay":
        return ("substrates", "enzymes", "monomers", "complexs"), (
            "substrates",
            "monomers",
            "complexs",
        )
    if process_name == "MacromolecularComplexation":
        return ("substrates", "complexs"), ("substrates", "complexs")
    if process_name == "Cytokinesis":
        return ("substrates", "enzymes", "boundEnzymes"), ("substrates",)
    raise ValueError(f"Unsupported Design-A process {process_name!r}.")


def _format_ensemble_oracle(
    *,
    process_name: str,
    oracle_path: Path,
    seed_paths: list[Path],
    before_channels: dict[str, np.ndarray],
    after_channels: dict[str, np.ndarray],
) -> dict[str, Any]:
    canonical_seed_count = int(len(seed_paths))
    n_ticks_available = int(next(iter(before_channels.values())).shape[1]) if before_channels else 0
    required_before, required_after = _required_ensemble_keys(process_name)
    legacy_oracle: dict[str, Any] | None = None

    def before_channel(channel: str, legacy_key: str) -> np.ndarray:
        nonlocal legacy_oracle
        if channel in before_channels:
            return np.asarray(before_channels[channel], dtype=np.float64)
        if legacy_oracle is None:
            legacy_oracle = _oracle_dispatch()[process_name]()
        return _legacy_seed_slice(legacy_oracle, legacy_key, canonical_seed_count)

    def after_channel(channel: str, legacy_key: str) -> np.ndarray:
        nonlocal legacy_oracle
        if channel in after_channels:
            return np.asarray(after_channels[channel], dtype=np.float64)
        if legacy_oracle is None:
            legacy_oracle = _oracle_dispatch()[process_name]()
        return _legacy_seed_slice(legacy_oracle, legacy_key, canonical_seed_count)

    missing_before = [channel for channel in required_before if channel not in before_channels]
    missing_after = [channel for channel in required_after if channel not in after_channels]

    if process_name == "Metabolism":
        return {
            "process": process_name,
            "oracle_path": oracle_path,
            "canonical_seed_count": canonical_seed_count,
            "n_ticks_available": n_ticks_available,
            "before_substrates": before_channel("substrates", "before_substrates"),
            "after_substrates": after_channel("substrates", "after_substrates"),
            "before_enzymes": before_channel("enzymes", "before_enzymes"),
            "before_bound_enzymes": before_channel("boundEnzymes", "before_bound_enzymes"),
            "ensemble_missing_before_channels": tuple(missing_before),
            "ensemble_missing_after_channels": tuple(missing_after),
        }

    if process_name == "Transcription":
        before_substrates_raw = before_channel("substrates", "before_substrates")
        after_substrates_raw = after_channel("substrates", "after_substrates")
        before_rnas_raw = before_channel("RNAs", "before_rnas")
        after_rnas_raw = after_channel("RNAs", "after_rnas")
        return {
            "process": process_name,
            "oracle_path": oracle_path,
            "canonical_seed_count": canonical_seed_count,
            "n_ticks_available": n_ticks_available,
            "before_substrates": np.asarray(
                [_project_transcription_substrate_cube(seed_matrix) for seed_matrix in before_substrates_raw],
                dtype=np.float64,
            ),
            "before_enzymes": before_channel("enzymes", "before_enzymes"),
            "before_bound_enzymes": before_channel("boundEnzymes", "before_bound_enzymes"),
            "before_rnas": np.asarray(
                [_project_transcription_rna_cube(seed_matrix) for seed_matrix in before_rnas_raw],
                dtype=np.float64,
            ),
            "after_substrates": np.asarray(
                [_project_transcription_substrate_cube(seed_matrix) for seed_matrix in after_substrates_raw],
                dtype=np.float64,
            ),
            "after_rnas": np.asarray(
                [_project_transcription_rna_cube(seed_matrix) for seed_matrix in after_rnas_raw],
                dtype=np.float64,
            ),
            "after_bound_enzymes": after_channel("boundEnzymes", "after_bound_enzymes"),
            "ensemble_missing_before_channels": tuple(missing_before),
            "ensemble_missing_after_channels": tuple(missing_after),
        }

    if process_name == "Translation":
        before_substrates_raw = before_channel("substrates", "before_substrates")
        after_substrates_raw = after_channel("substrates", "after_substrates")
        return {
            "process": process_name,
            "oracle_path": oracle_path,
            "canonical_seed_count": canonical_seed_count,
            "n_ticks_available": n_ticks_available,
            "before_substrates": np.asarray(
                [_project_translation_substrate_cube(seed_matrix) for seed_matrix in before_substrates_raw],
                dtype=np.float64,
            ),
            "before_enzymes": before_channel("enzymes", "before_enzymes"),
            "before_bound_enzymes": before_channel("boundEnzymes", "before_bound_enzymes"),
            "before_monomers": before_channel("monomers", "before_monomers"),
            "before_mrnas": before_channel("mRNAs", "before_mrnas"),
            "after_substrates": np.asarray(
                [_project_translation_substrate_cube(seed_matrix) for seed_matrix in after_substrates_raw],
                dtype=np.float64,
            ),
            "after_monomers": after_channel("monomers", "after_monomers"),
            "after_bound_enzymes": after_channel("boundEnzymes", "after_bound_enzymes"),
            "ensemble_missing_before_channels": tuple(missing_before),
            "ensemble_missing_after_channels": tuple(missing_after),
        }

    if process_name == "RNADecay":
        return {
            "process": process_name,
            "oracle_path": oracle_path,
            "canonical_seed_count": canonical_seed_count,
            "n_ticks_available": n_ticks_available,
            "before_substrates": before_channel("substrates", "before_substrates"),
            "before_enzymes": before_channel("enzymes", "before_enzymes"),
            "before_bound_enzymes": before_channel("boundEnzymes", "before_bound_enzymes"),
            "before_rnas": before_channel("RNAs", "before_rnas"),
            "after_substrates": after_channel("substrates", "after_substrates"),
            "after_rnas": after_channel("RNAs", "after_rnas"),
            "ensemble_missing_before_channels": tuple(missing_before),
            "ensemble_missing_after_channels": tuple(missing_after),
        }

    if process_name == "RNAProcessing":
        return {
            "process": process_name,
            "oracle_path": oracle_path,
            "canonical_seed_count": canonical_seed_count,
            "n_ticks_available": n_ticks_available,
            "before_substrates": before_channel("substrates", "before_substrates"),
            "before_enzymes": before_channel("enzymes", "before_enzymes"),
            "before_bound_enzymes": before_channel("boundEnzymes", "before_bound_enzymes"),
            "before_rnas": _concatenate_rna_channels(
                before_channel("unprocessedRNAs", "before_rnas"),
                before_channel("processedRNAs", "before_rnas"),
                before_channel("intergenicRNAs", "before_rnas"),
            ),
            "after_substrates": after_channel("substrates", "after_substrates"),
            "after_rnas": _concatenate_rna_channels(
                after_channel("unprocessedRNAs", "after_rnas"),
                after_channel("processedRNAs", "after_rnas"),
                after_channel("intergenicRNAs", "after_rnas"),
            ),
            "ensemble_missing_before_channels": tuple(missing_before),
            "ensemble_missing_after_channels": tuple(missing_after),
        }

    if process_name == "RNAModification":
        return {
            "process": process_name,
            "oracle_path": oracle_path,
            "canonical_seed_count": canonical_seed_count,
            "n_ticks_available": n_ticks_available,
            "before_substrates": before_channel("substrates", "before_substrates"),
            "before_enzymes": before_channel("enzymes", "before_enzymes"),
            "before_bound_enzymes": before_channel("boundEnzymes", "before_bound_enzymes"),
            "before_rnas": _concatenate_rna_channels(
                before_channel("unmodifiedRNAs", "before_rnas"),
                before_channel("modifiedRNAs", "before_rnas"),
            ),
            "after_substrates": after_channel("substrates", "after_substrates"),
            "after_rnas": _concatenate_rna_channels(
                after_channel("unmodifiedRNAs", "after_rnas"),
                after_channel("modifiedRNAs", "after_rnas"),
            ),
            "ensemble_missing_before_channels": tuple(missing_before),
            "ensemble_missing_after_channels": tuple(missing_after),
        }

    if process_name == "tRNAAminoacylation":
        return {
            "process": process_name,
            "oracle_path": oracle_path,
            "canonical_seed_count": canonical_seed_count,
            "n_ticks_available": n_ticks_available,
            "before_substrates": before_channel("substrates", "before_substrates"),
            "before_enzymes": before_channel("enzymes", "before_enzymes"),
            "before_bound_enzymes": before_channel("boundEnzymes", "before_bound_enzymes"),
            "before_rnas": _concatenate_rna_channels(
                before_channel("freeRNAs", "before_rnas"),
                before_channel("aminoacylatedRNAs", "before_rnas"),
            ),
            "after_substrates": after_channel("substrates", "after_substrates"),
            "after_rnas": _concatenate_rna_channels(
                after_channel("freeRNAs", "after_rnas"),
                after_channel("aminoacylatedRNAs", "after_rnas"),
            ),
            "ensemble_missing_before_channels": tuple(missing_before),
            "ensemble_missing_after_channels": tuple(missing_after),
        }

    if process_name == "ProteinDecay":
        before_monomers_raw = before_channel("monomers", "before_monomers")
        before_complexs_raw = before_channel("complexs", "before_complexs")
        after_monomers_raw = after_channel("monomers", "after_monomers")
        after_complexs_raw = after_channel("complexs", "after_complexs")
        return {
            "process": process_name,
            "oracle_path": oracle_path,
            "canonical_seed_count": canonical_seed_count,
            "n_ticks_available": n_ticks_available,
            "before_substrates": before_channel("substrates", "before_substrates"),
            "before_enzymes": before_channel("enzymes", "before_enzymes"),
            "before_monomers": np.asarray(
                [_project_protein_decay_monomer_cube(seed_matrix) for seed_matrix in before_monomers_raw],
                dtype=np.float64,
            ),
            "before_complexs": np.asarray(
                [_project_protein_decay_complex_cube(seed_matrix) for seed_matrix in before_complexs_raw],
                dtype=np.float64,
            ),
            "after_substrates": after_channel("substrates", "after_substrates"),
            "after_monomers": np.asarray(
                [_project_protein_decay_monomer_cube(seed_matrix) for seed_matrix in after_monomers_raw],
                dtype=np.float64,
            ),
            "after_complexs": np.asarray(
                [_project_protein_decay_complex_cube(seed_matrix) for seed_matrix in after_complexs_raw],
                dtype=np.float64,
            ),
            "ensemble_missing_before_channels": tuple(missing_before),
            "ensemble_missing_after_channels": tuple(missing_after),
        }

    if process_name == "MacromolecularComplexation":
        before_substrates_raw = before_channel("substrates", "before_substrates")
        after_substrates_raw = after_channel("substrates", "after_substrates")
        before_complexs_raw = before_channel("complexs", "before_complexs")
        after_complexs_raw = after_channel("complexs", "after_complexs")
        return {
            "process": process_name,
            "oracle_path": oracle_path,
            "canonical_seed_count": canonical_seed_count,
            "n_ticks_available": n_ticks_available,
            "before_substrates": before_substrates_raw,
            "before_monomers": np.asarray(
                [_project_macromol_monomer_cube(seed_matrix) for seed_matrix in before_substrates_raw],
                dtype=np.float64,
            ),
            "before_complexs": before_complexs_raw,
            "after_substrates": after_substrates_raw,
            "after_monomers": np.asarray(
                [_project_macromol_monomer_cube(seed_matrix) for seed_matrix in after_substrates_raw],
                dtype=np.float64,
            ),
            "after_complexs": after_complexs_raw,
            "ensemble_missing_before_channels": tuple(missing_before),
            "ensemble_missing_after_channels": tuple(missing_after),
        }

    if process_name == "Cytokinesis":
        return {
            "process": process_name,
            "oracle_path": oracle_path,
            "canonical_seed_count": canonical_seed_count,
            "n_ticks_available": n_ticks_available,
            "before_substrates": before_channel("substrates", "before_substrates"),
            "after_substrates": after_channel("substrates", "after_substrates"),
            "before_enzymes": before_channel("enzymes", "before_enzymes"),
            "before_bound_enzymes": before_channel("boundEnzymes", "before_bound_enzymes"),
            "ensemble_missing_before_channels": tuple(missing_before),
            "ensemble_missing_after_channels": tuple(missing_after),
        }

    raise ValueError(f"Unsupported Design-A process {process_name!r}.")


def _load_v2_ensemble(process_name: str, max_seeds: int = 50) -> dict[str, Any] | None:
    seed_paths = [
        _v2_seed_mat_path(process_name, seed)
        for seed in range(int(max_seeds))
        if _v2_seed_mat_path(process_name, seed).exists()
    ]
    if (
        process_name == "MacromolecularComplexation"
        and _REPO_ROOT == _ACTUAL_REPO_ROOT
        and len(seed_paths) < int(max_seeds)
    ):
        for candidate_root in (
            Path("E:/opencell/data/m1_sources/karr_native"),
            Path("/mnt/e/opencell/data/m1_sources/karr_native"),
        ):
            candidate_seed_paths = [
                candidate_root
                / f"per_process_traces_v2_s{seed:03d}"
                / f"{process_name}_100ticks.mat"
                for seed in range(int(max_seeds))
                if (
                    candidate_root
                    / f"per_process_traces_v2_s{seed:03d}"
                    / f"{process_name}_100ticks.mat"
                ).exists()
            ]
            if len(candidate_seed_paths) > len(seed_paths):
                seed_paths = candidate_seed_paths
    if not seed_paths:
        return None
    before_channels, after_channels, _ = _load_seeded_mat_channels(seed_paths)
    return _format_ensemble_oracle(
        process_name=process_name,
        oracle_path=seed_paths[0],
        seed_paths=seed_paths,
        before_channels=before_channels,
        after_channels=after_channels,
    )


def _load_ensembles_layout(process_name: str, max_seeds: int = 50) -> dict[str, Any] | None:
    seed_paths = [
        _ensembles_seed_mat_path(process_name, seed)
        for seed in range(int(max_seeds))
        if _ensembles_seed_mat_path(process_name, seed).exists()
    ]
    if not seed_paths:
        return None

    before_channels, after_channels, _ = _load_seeded_mat_channels(seed_paths)
    manifest_path = _ensembles_manifest_path(process_name)
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_seed_count = manifest.get("present_seed_count", manifest.get("expected_seed_count"))
        if manifest_seed_count is not None and int(manifest_seed_count) != len(seed_paths):
            raise ValueError(
                f"Manifest seed-count mismatch for {process_name}: "
                f"manifest={manifest_seed_count} actual={len(seed_paths)}"
            )
        manifest_observables = manifest.get("observable_schema_set")
        if manifest_observables is not None:
            observed_schema = tuple(sorted(set(before_channels) | set(after_channels)))
            expected_schema = tuple(sorted(str(channel) for channel in manifest_observables))
            if observed_schema != expected_schema:
                raise ValueError(
                    f"Manifest observable mismatch for {process_name}: "
                    f"manifest={expected_schema} actual={observed_schema}"
                )

    return _format_ensemble_oracle(
        process_name=process_name,
        oracle_path=manifest_path if manifest_path.exists() else seed_paths[0],
        seed_paths=seed_paths,
        before_channels=before_channels,
        after_channels=after_channels,
    )


def _oracle_dispatch() -> dict[str, Any]:
    return {
        "Metabolism": _load_metabolism_oracle,
        "Translation": _load_translation_oracle,
        "Transcription": _load_transcription_oracle,
        "RNADecay": _load_rna_decay_oracle,
        "ProteinDecay": _load_protein_decay_oracle,
        "MacromolecularComplexation": _load_macromol_oracle,
        "Cytokinesis": _load_cytokinesis_oracle,
    }


def load_karr_oracle(process: str) -> dict[str, Any]:
    """Load the canonical Karr oracle for a Design-A process."""
    v2_oracle = _load_v2_ensemble(process)
    specialized_ensemble_oracle = _load_ensembles_layout(process)
    if v2_oracle is not None and specialized_ensemble_oracle is not None:
        if int(v2_oracle.get("canonical_seed_count", 0)) >= int(
            specialized_ensemble_oracle.get("canonical_seed_count", 0)
        ):
            return v2_oracle
        return specialized_ensemble_oracle
    if v2_oracle is not None:
        return v2_oracle
    if specialized_ensemble_oracle is not None:
        return specialized_ensemble_oracle

    loaders = _oracle_dispatch()
    loader = loaders.get(process)
    if loader is None:
        raise ValueError(f"Unsupported Design-A process {process!r}.")

    legacy_oracle = loader()
    legacy_warnings = list(legacy_oracle.get("warnings", ()))
    legacy_warnings.append(
        "KARR_LEGACY_SINGLE_SEED_FALLBACK: no ensemble found for "
        f"{process} at per_process_traces_v2_s{{NNN}}/ or ensembles/<process>/seed_NNN/; "
        f"using legacy single-seed npz at per_process_replay/{process}.npz. "
        "Distributional gate is degraded to N-OC-samples vs 1-Karr-sample."
    )
    legacy_oracle["canonical_seed_count"] = 1
    legacy_oracle["warnings"] = legacy_warnings
    return legacy_oracle


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


def _load_translation_oracle() -> dict[str, Any]:
    if not _TRANSLATION_ORACLE_PATH.exists():
        raise FileNotFoundError(f"Missing Translation oracle fixture: {_TRANSLATION_ORACLE_PATH}")

    with np.load(_TRANSLATION_ORACLE_PATH, allow_pickle=False) as payload:
        before_substrates_raw = np.asarray(payload["state_before__substrates"], dtype=np.float64)[:, 0, :]
        after_substrates_raw = np.asarray(payload["states_after__substrates"], dtype=np.float64)[:, 0, :]
        before_enzymes = np.asarray(payload["state_before__enzymes"], dtype=np.float64)[:, 0, :]
        before_bound = np.asarray(payload["state_before__boundEnzymes"], dtype=np.float64)[:, 0, :]
        before_monomers = np.asarray(payload["state_before__monomers"], dtype=np.float64)[:, 0, :]
        before_mrnas = np.asarray(payload["state_before__mRNAs"], dtype=np.float64)[:, 0, :]
        after_monomers = np.asarray(payload["states_after__monomers"], dtype=np.float64)[:, 0, :]
        after_bound = np.asarray(payload["states_after__boundEnzymes"], dtype=np.float64)[:, 0, :]

    before_substrates = _project_translation_substrate_cube(before_substrates_raw)
    after_substrates = _project_translation_substrate_cube(after_substrates_raw)
    return {
        "process": "Translation",
        "oracle_path": _TRANSLATION_ORACLE_PATH,
        "canonical_seed_count": 1,
        "n_ticks_available": int(before_substrates.shape[0]),
        "before_substrates": before_substrates[np.newaxis, :, :],
        "before_enzymes": before_enzymes[np.newaxis, :, :],
        "before_bound_enzymes": before_bound[np.newaxis, :, :],
        "before_monomers": before_monomers[np.newaxis, :, :],
        "before_mrnas": before_mrnas[np.newaxis, :, :],
        "after_substrates": after_substrates[np.newaxis, :, :],
        "after_monomers": after_monomers[np.newaxis, :, :],
        "after_bound_enzymes": after_bound[np.newaxis, :, :],
    }


def _load_rna_decay_oracle() -> dict[str, Any]:
    if not _RNA_DECAY_ORACLE_PATH.exists():
        raise FileNotFoundError(f"Missing RNADecay oracle fixture: {_RNA_DECAY_ORACLE_PATH}")

    with np.load(_RNA_DECAY_ORACLE_PATH, allow_pickle=False) as payload:
        before_substrates = np.asarray(payload["state_before__substrates"], dtype=np.float64)[:, 0, :]
        before_enzymes = np.asarray(payload["state_before__enzymes"], dtype=np.float64)[:, 0, :]
        before_bound = np.asarray(payload["state_before__boundEnzymes"], dtype=np.float64)[:, 0, :]
        before_rnas = np.asarray(payload["state_before__RNAs"], dtype=np.float64)[:, 0, :]
        after_substrates = np.asarray(payload["states_after__substrates"], dtype=np.float64)[:, 0, :]
        after_rnas = np.asarray(payload["states_after__RNAs"], dtype=np.float64)[:, 0, :]

    return {
        "process": "RNADecay",
        "oracle_path": _RNA_DECAY_ORACLE_PATH,
        "canonical_seed_count": 1,
        "n_ticks_available": int(before_substrates.shape[0]),
        "before_substrates": before_substrates[np.newaxis, :, :],
        "before_enzymes": before_enzymes[np.newaxis, :, :],
        "before_bound_enzymes": before_bound[np.newaxis, :, :],
        "before_rnas": before_rnas[np.newaxis, :, :],
        "after_substrates": after_substrates[np.newaxis, :, :],
        "after_rnas": after_rnas[np.newaxis, :, :],
    }


def _load_protein_decay_oracle() -> dict[str, Any]:
    if not _PROTEIN_DECAY_ORACLE_PATH.exists():
        raise FileNotFoundError(f"Missing ProteinDecay oracle fixture: {_PROTEIN_DECAY_ORACLE_PATH}")

    with np.load(_PROTEIN_DECAY_ORACLE_PATH, allow_pickle=False) as payload:
        before_substrates = np.asarray(payload["state_before__substrates"], dtype=np.float64)[:, 0, :]
        before_enzymes = np.asarray(payload["state_before__enzymes"], dtype=np.float64)[:, 0, :]
        before_monomers_raw = np.asarray(payload["state_before__monomers"], dtype=np.float64)
        before_complexs_raw = np.asarray(payload["state_before__complexs"], dtype=np.float64)
        after_substrates = np.asarray(payload["states_after__substrates"], dtype=np.float64)[:, 0, :]
        after_monomers_raw = np.asarray(payload["states_after__monomers"], dtype=np.float64)
        after_complexs_raw = np.asarray(payload["states_after__complexs"], dtype=np.float64)

    before_monomers = _project_protein_decay_monomer_cube(before_monomers_raw)
    before_complexs = _project_protein_decay_complex_cube(before_complexs_raw)
    after_monomers = _project_protein_decay_monomer_cube(after_monomers_raw)
    after_complexs = _project_protein_decay_complex_cube(after_complexs_raw)

    return {
        "process": "ProteinDecay",
        "oracle_path": _PROTEIN_DECAY_ORACLE_PATH,
        "canonical_seed_count": 1,
        "n_ticks_available": int(before_substrates.shape[0]),
        "before_substrates": before_substrates[np.newaxis, :, :],
        "before_enzymes": before_enzymes[np.newaxis, :, :],
        "before_monomers": before_monomers[np.newaxis, :, :],
        "before_complexs": before_complexs[np.newaxis, :, :],
        "after_substrates": after_substrates[np.newaxis, :, :],
        "after_monomers": after_monomers[np.newaxis, :, :],
        "after_complexs": after_complexs[np.newaxis, :, :],
    }


def _load_macromol_oracle() -> dict[str, Any]:
    raise FileNotFoundError(
        "MacromolecularComplexation has no dedicated legacy single-seed loader; "
        "use per_process_traces_v2 ensemble inputs."
    )


def _load_cytokinesis_oracle() -> dict[str, Any]:
    if not _CYTOKINESIS_ORACLE_PATH.exists():
        raise FileNotFoundError(f"Missing Cytokinesis oracle fixture: {_CYTOKINESIS_ORACLE_PATH}")

    with np.load(_CYTOKINESIS_ORACLE_PATH, allow_pickle=False) as payload:
        before_substrates = np.asarray(payload["state_before__substrates"], dtype=np.float64)[:, 0, :]
        after_substrates = np.asarray(payload["states_after__substrates"], dtype=np.float64)[:, 0, :]
        before_enzymes = np.asarray(payload["state_before__enzymes"], dtype=np.float64)[:, 0, :]
        before_bound = np.asarray(payload["state_before__boundEnzymes"], dtype=np.float64)[:, 0, :]

    return {
        "process": "Cytokinesis",
        "oracle_path": _CYTOKINESIS_ORACLE_PATH,
        "canonical_seed_count": 1,
        "n_ticks_available": int(before_substrates.shape[0]),
        "before_substrates": before_substrates[np.newaxis, :, :],
        "after_substrates": after_substrates[np.newaxis, :, :],
        "before_enzymes": before_enzymes[np.newaxis, :, :],
        "before_bound_enzymes": before_bound[np.newaxis, :, :],
    }


def _concatenate_rna_channels(*segments: np.ndarray) -> np.ndarray:
    arrays = [np.asarray(segment, dtype=np.float64) for segment in segments]
    return np.asarray(np.concatenate(arrays, axis=2), dtype=np.float64)


def _split_rna_vector(vector: np.ndarray, segment_lengths: tuple[int, ...]) -> tuple[np.ndarray, ...]:
    arr = np.asarray(vector, dtype=np.float64).reshape(-1)
    expected = int(sum(segment_lengths))
    if arr.size != expected:
        raise ValueError(f"RNA vector length mismatch: got {arr.size}, expected {expected}")
    offsets: list[int] = [0]
    for length in segment_lengths:
        offsets.append(offsets[-1] + int(length))
    return tuple(arr[offsets[idx] : offsets[idx + 1]] for idx in range(len(segment_lengths)))


def _replace_active_rna_wids(
    *,
    full_before: np.ndarray,
    full_wids: tuple[str, ...],
    active_after: np.ndarray,
    active_wids: list[str] | tuple[str, ...],
) -> np.ndarray:
    out = np.asarray(full_before, dtype=np.float64).reshape(-1).copy()
    active_arr = np.asarray(active_after, dtype=np.float64).reshape(-1)
    active_ids = [str(wid) for wid in active_wids]
    if active_arr.size != len(active_ids):
        raise ValueError(
            f"Active RNA vector/WID mismatch: len(vector)={active_arr.size} len(wids)={len(active_ids)}"
        )
    index_by_wid = {str(wid): idx for idx, wid in enumerate(full_wids)}
    for idx, wid in enumerate(active_ids):
        full_idx = index_by_wid.get(wid)
        if full_idx is not None:
            out[full_idx] = float(active_arr[idx])
    return out


@lru_cache(maxsize=1)
def _rna_processing_channel_metadata() -> dict[str, Any]:
    unprocessed_wids = tuple(load_fixture_channel_wids("RNAProcessing", "unprocessedRNAs"))
    raw_processed_wids = tuple(load_fixture_channel_wids("RNAProcessing", "processedRNAs"))
    intergenic_wids = tuple(load_fixture_channel_wids("RNAProcessing", "intergenicRNAs"))
    unprocessed_set = set(unprocessed_wids)
    processed_state_wids = tuple(
        f"processed::{wid}" if wid in unprocessed_set else wid
        for wid in raw_processed_wids
    )
    return {
        "unprocessed_wids": unprocessed_wids,
        "processed_state_wids": processed_state_wids,
        "intergenic_wids": intergenic_wids,
        "primary_wids": tuple(unprocessed_wids + processed_state_wids + intergenic_wids),
    }


@lru_cache(maxsize=1)
def _rna_modification_channel_metadata() -> dict[str, Any]:
    unmodified_wids = tuple(load_fixture_channel_wids("RNAModification", "unmodifiedRNAs"))
    modified_wids = tuple(load_fixture_channel_wids("RNAModification", "modifiedRNAs"))
    return {
        "unmodified_wids": unmodified_wids,
        "modified_wids": modified_wids,
        "primary_wids": tuple(unmodified_wids + modified_wids),
    }


@lru_cache(maxsize=1)
def _trna_aminoacylation_channel_metadata() -> dict[str, Any]:
    free_wids = tuple(load_fixture_channel_wids("tRNAAminoacylation", "freeRNAs"))
    amino_wids = tuple(load_fixture_channel_wids("tRNAAminoacylation", "aminoacylatedRNAs"))
    return {
        "free_wids": free_wids,
        "aminoacylated_wids": amino_wids,
        "primary_wids": tuple(free_wids + amino_wids),
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
def _translation_model() -> Any:
    return m3_karr_translation.load_default()


@lru_cache(maxsize=None)
def _transcription_process(seed: int) -> KarrTranscriptionProcess:
    return KarrTranscriptionProcess({"rng_seed": int(seed)})


@lru_cache(maxsize=None)
def _translation_process(seed: int) -> KarrTranslationProcess:
    model = _translation_model()
    with forbid_sut_oracle_file_io():
        return KarrTranslationProcess({"rng_seed": int(seed), "model": model})


@lru_cache(maxsize=None)
def _rna_decay_process(seed: int) -> RnaDecayLightProcess:
    with forbid_sut_oracle_file_io():
        return RnaDecayLightProcess({"rng_seed": int(seed)})


@lru_cache(maxsize=None)
def _rna_processing_process(seed: int) -> KarrRNAProcessingProcess:
    metadata = _rna_processing_channel_metadata()
    with forbid_sut_oracle_file_io():
        process = KarrRNAProcessingProcess({"rng_seed": int(seed)})
    process.rna_primary_wids = list(metadata["primary_wids"])
    return process


@lru_cache(maxsize=None)
def _rna_modification_process(seed: int) -> KarrRNAModificationProcess:
    metadata = _rna_modification_channel_metadata()
    with forbid_sut_oracle_file_io():
        process = KarrRNAModificationProcess({"rng_seed": int(seed)})
    process.rna_primary_wids = list(metadata["primary_wids"])
    return process


@lru_cache(maxsize=None)
def _trna_aminoacylation_process(seed: int) -> KarrTRNAAminoacylationProcess:
    metadata = _trna_aminoacylation_channel_metadata()
    with forbid_sut_oracle_file_io():
        process = KarrTRNAAminoacylationProcess({"rng_seed": int(seed)})
    process.rna_primary_wids = list(metadata["primary_wids"])
    return process


@lru_cache(maxsize=None)
def _protein_decay_process(seed: int) -> ProteinDecayLightProcess:
    with forbid_sut_oracle_file_io():
        return ProteinDecayLightProcess({"rng_seed": int(seed)})


@lru_cache(maxsize=1)
def _macromol_channel_metadata() -> dict[str, Any]:
    fixture_path = _REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "MacromolecularComplexation_flat.mat"
    if not fixture_path.exists() and _REPO_ROOT == _ACTUAL_REPO_ROOT:
        for candidate in (
            Path("E:/opencell/data/karr_fixtures/per_process/MacromolecularComplexation_flat.mat"),
            Path("/mnt/e/opencell/data/karr_fixtures/per_process/MacromolecularComplexation_flat.mat"),
        ):
            if candidate.exists():
                fixture_path = candidate
                break
    fixture = loadmat(str(fixture_path), squeeze_me=True, struct_as_record=False)["data"].fixture
    substrate_wids = tuple(str(x) for x in np.asarray(fixture.substrateWholeCellModelIDs, dtype=object).reshape(-1))
    monomer_indices = tuple(
        sorted(
            {
                int(value) - 1
                for value in np.asarray(fixture.substrateMonomerLocalIndexs, dtype=np.int64).reshape(-1)
                if int(value) > 0
            }
        )
    )
    return {
        "substrate_wids": substrate_wids,
        "monomer_indices": monomer_indices,
        "monomer_wids": tuple(substrate_wids[idx] for idx in monomer_indices),
    }


@lru_cache(maxsize=None)
def _macromol_process(seed: int) -> MacromolecularComplexationProcess:
    metadata = _macromol_channel_metadata()
    with forbid_sut_oracle_file_io():
        process = MacromolecularComplexationProcess({"rng_seed": int(seed)})
    process.monomer_wids = list(metadata["monomer_wids"])
    process.monomer_indices = np.asarray(metadata["monomer_indices"], dtype=np.int64)
    return process


@lru_cache(maxsize=None)
def _cytokinesis_process(seed: int) -> KarrCytokinesisProcess:
    with forbid_sut_oracle_file_io():
        return KarrCytokinesisProcess(
            {
                "rng_seed": int(seed),
                # Avoid the trace_path open during __init__ which would otherwise
                # trigger forbid_sut_oracle_file_io. The trace tick count is only
                # used to default active_division_rate; we provide that explicitly.
                "trace_path": "",
                "active_division_rate_per_s": 0.01,
            }
        )


def _sample_seed(seed: int, tick: int) -> int:
    ss = np.random.SeedSequence([L2_2_VALIDATION_SEED, int(seed), int(tick)])
    return int(ss.generate_state(1, dtype=np.uint32)[0])


def _tick_dispatch() -> dict[str, Any]:
    return {
        "Metabolism": _run_metabolism_tick,
        "Translation": _run_translation_tick,
        "Transcription": _run_transcription_tick,
        "RNADecay": _run_rna_decay_tick,
        "RNAProcessing": _run_rna_processing_tick,
        "RNAModification": _run_rna_modification_tick,
        "tRNAAminoacylation": _run_trna_aminoacylation_tick,
        "ProteinDecay": _run_protein_decay_tick,
        "MacromolecularComplexation": _run_macromol_tick,
        "Cytokinesis": _run_cytokinesis_tick,
    }


def run_oc_tick(process_name: str, seed: int, tick: int, state: dict[str, Any]) -> dict[str, Any]:
    runners = _tick_dispatch()
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


def _run_translation_tick(seed: int, tick: int, state: dict[str, Any]) -> dict[str, Any]:
    """Run one OpenCell Translation tick from a prepared state snapshot."""
    process = _translation_process(_sample_seed(seed, tick))
    runtime_state = build_state_template(process)
    substrate_wids = list(state["substrate_wids"])
    enzyme_wids = list(state["enzyme_wids"])
    monomer_wids = list(state["monomer_wids"])
    mrna_wids = list(state["mrna_wids"])

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
        observable="monomers",
        vector=np.asarray(state["oracle_before_monomers"], dtype=np.float64),
        wids=monomer_wids,
    )
    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="mRNAs",
        vector=np.asarray(state["oracle_before_mrnas"], dtype=np.float64),
        wids=mrna_wids,
        store_path_override=_TRANSLATION_MRNA_STORE_PATH_OVERRIDE,
    )
    overlay_trace_after_hint(
        state=runtime_state,
        observable="substrates",
        vector=np.asarray(state["oracle_after_substrates"], dtype=np.float64),
        wids=substrate_wids,
    )
    overlay_trace_after_hint(
        state=runtime_state,
        observable="monomers",
        vector=np.asarray(state["oracle_after_monomers"], dtype=np.float64),
        wids=monomer_wids,
    )
    overlay_trace_after_hint(
        state=runtime_state,
        observable="boundEnzymes",
        vector=np.asarray(state["oracle_after_bound_enzymes"], dtype=np.float64),
        wids=enzyme_wids,
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
        "monomers": np.asarray(
            project_observable_from_state(
                process=process,
                state=runtime_state,
                observable="monomers",
                wids=monomer_wids,
                bound_enzymes_before=np.asarray(state["oracle_before_bound_enzymes"], dtype=np.float64),
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


def _overlay_rna_decay_slot_counts(
    *,
    state: dict[str, Any],
    vector: np.ndarray,
    wids: list[str],
) -> None:
    state[_RNA_SLOT_COUNTS_STATE_KEY] = np.asarray(vector, dtype=np.float64).reshape(-1).copy()
    state[_RNA_SLOT_WIDS_STATE_KEY] = tuple(str(wid) for wid in wids)


def _apply_rna_decay_slot_update(*, process: Any, state: dict[str, Any]) -> None:
    slot_counts = state.get(_RNA_SLOT_COUNTS_STATE_KEY)
    slot_delta = getattr(process, "_last_rna_delta_vector", None)
    if slot_counts is None or slot_delta is None:
        return

    counts_arr = np.asarray(slot_counts, dtype=np.float64).reshape(-1)
    delta_arr = np.asarray(slot_delta, dtype=np.float64).reshape(-1)
    if counts_arr.shape != delta_arr.shape:
        raise ValueError(
            "RNADecay slot-count update shape mismatch: "
            f"counts={counts_arr.shape} delta={delta_arr.shape}"
        )
    state[_RNA_SLOT_COUNTS_STATE_KEY] = counts_arr + delta_arr


def _project_rna_decay_slot_counts(
    *,
    process: Any,
    state: dict[str, Any],
    wids: list[str],
    bound_enzymes_before: np.ndarray | None,
) -> np.ndarray:
    slot_counts = state.get(_RNA_SLOT_COUNTS_STATE_KEY)
    slot_wids = state.get(_RNA_SLOT_WIDS_STATE_KEY)
    if slot_counts is not None:
        counts_arr = np.asarray(slot_counts, dtype=np.float64).reshape(-1)
        if counts_arr.size == len(wids) and (
            slot_wids is None or tuple(str(wid) for wid in wids) == tuple(slot_wids)
        ):
            return counts_arr

    return np.asarray(
        project_observable_from_state(
            process=process,
            state=state,
            observable="RNAs",
            wids=wids,
            bound_enzymes_before=bound_enzymes_before,
            store_path_override=_RNA_STORE_PATH_OVERRIDE,
        ),
        dtype=np.float64,
    )


def _run_rna_decay_tick(seed: int, tick: int, state: dict[str, Any]) -> dict[str, Any]:
    """Run one OpenCell RNADecay tick from a prepared state snapshot."""
    process = _rna_decay_process(_sample_seed(seed, tick))
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
        observable="RNAs",
        vector=np.asarray(state["oracle_before_rnas"], dtype=np.float64),
        wids=rna_wids,
        store_path_override=_RNA_STORE_PATH_OVERRIDE,
    )
    _overlay_rna_decay_slot_counts(
        state=runtime_state,
        vector=np.asarray(state["oracle_before_rnas"], dtype=np.float64),
        wids=rna_wids,
    )
    refresh_allocator_views(process, runtime_state)
    with forbid_sut_oracle_file_io():
        update = process.next_update(1.0, runtime_state)
    apply_count_update(runtime_state, update)
    _apply_rna_decay_slot_update(process=process, state=runtime_state)
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
            _project_rna_decay_slot_counts(
                process=process,
                state=runtime_state,
                wids=rna_wids,
                bound_enzymes_before=np.asarray(state["oracle_before_bound_enzymes"], dtype=np.float64),
            ),
            dtype=np.float64,
        ),
        "sample_seed": _sample_seed(seed, tick),
    }


def _run_rna_processing_tick(seed: int, tick: int, state: dict[str, Any]) -> dict[str, Any]:
    """Run one OpenCell RNAProcessing tick from a prepared state snapshot."""
    process = _rna_processing_process(_sample_seed(seed, tick))
    metadata = _rna_processing_channel_metadata()
    runtime_state = build_state_template(process)
    substrate_wids = list(state["substrate_wids"])
    enzyme_wids = list(state["enzyme_wids"])
    bound_enzymes_before = np.asarray(state["oracle_before_bound_enzymes"], dtype=np.float64)
    unprocessed_before, processed_before, intergenic_before = _split_rna_vector(
        np.asarray(state["oracle_before_rnas"], dtype=np.float64),
        (
            len(metadata["unprocessed_wids"]),
            len(metadata["processed_state_wids"]),
            len(metadata["intergenic_wids"]),
        ),
    )

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
        observable="unprocessedRNAs",
        vector=unprocessed_before,
        wids=list(process.unprocessed_rna_wids),
    )
    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="processedRNAs",
        vector=processed_before,
        wids=list(process.processed_rna_wids),
    )
    refresh_allocator_views(process, runtime_state)
    with forbid_sut_oracle_file_io():
        update = process.next_update(1.0, runtime_state)
    apply_count_update(runtime_state, update)

    unprocessed_after = project_observable_from_state(
        process=process,
        state=runtime_state,
        observable="unprocessedRNAs",
        wids=list(process.unprocessed_rna_wids),
        bound_enzymes_before=bound_enzymes_before,
    )
    processed_after = project_observable_from_state(
        process=process,
        state=runtime_state,
        observable="processedRNAs",
        wids=list(process.processed_rna_wids),
        bound_enzymes_before=bound_enzymes_before,
    )
    rna_after = np.asarray(
        np.concatenate([unprocessed_after, processed_after, intergenic_before]),
        dtype=np.float64,
    )
    return {
        "substrates": np.asarray(
            project_observable_from_state(
                process=process,
                state=runtime_state,
                observable="substrates",
                wids=substrate_wids,
                bound_enzymes_before=bound_enzymes_before,
            ),
            dtype=np.float64,
        ),
        "RNAs": rna_after,
        "sample_seed": _sample_seed(seed, tick),
    }


def _run_rna_modification_tick(seed: int, tick: int, state: dict[str, Any]) -> dict[str, Any]:
    """Run one OpenCell RNAModification tick from a prepared state snapshot."""
    process = _rna_modification_process(_sample_seed(seed, tick))
    metadata = _rna_modification_channel_metadata()
    runtime_state = build_state_template(process)
    substrate_wids = list(state["substrate_wids"])
    enzyme_wids = list(state["enzyme_wids"])
    bound_enzymes_before = np.asarray(state["oracle_before_bound_enzymes"], dtype=np.float64)
    full_unmodified_before, full_modified_before = _split_rna_vector(
        np.asarray(state["oracle_before_rnas"], dtype=np.float64),
        (
            len(metadata["unmodified_wids"]),
            len(metadata["modified_wids"]),
        ),
    )
    active_unmodified_before = project_vector_onto_wids(
        karr_vector=full_unmodified_before,
        karr_wids=metadata["unmodified_wids"],
        oc_wids=list(process.unmodified_rna_wids),
    )
    active_modified_before = project_vector_onto_wids(
        karr_vector=full_modified_before,
        karr_wids=metadata["modified_wids"],
        oc_wids=list(process.modified_rna_wids),
    )

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
        observable="unmodifiedRNAs",
        vector=active_unmodified_before,
        wids=list(process.unmodified_rna_wids),
    )
    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="modifiedRNAs",
        vector=active_modified_before,
        wids=list(process.modified_rna_wids),
    )
    refresh_allocator_views(process, runtime_state)
    with forbid_sut_oracle_file_io():
        update = process.next_update(1.0, runtime_state)
    apply_count_update(runtime_state, update)

    active_unmodified_after = project_observable_from_state(
        process=process,
        state=runtime_state,
        observable="unmodifiedRNAs",
        wids=list(process.unmodified_rna_wids),
        bound_enzymes_before=bound_enzymes_before,
    )
    active_modified_after = project_observable_from_state(
        process=process,
        state=runtime_state,
        observable="modifiedRNAs",
        wids=list(process.modified_rna_wids),
        bound_enzymes_before=bound_enzymes_before,
    )
    full_unmodified_after = _replace_active_rna_wids(
        full_before=full_unmodified_before,
        full_wids=metadata["unmodified_wids"],
        active_after=active_unmodified_after,
        active_wids=list(process.unmodified_rna_wids),
    )
    full_modified_after = _replace_active_rna_wids(
        full_before=full_modified_before,
        full_wids=metadata["modified_wids"],
        active_after=active_modified_after,
        active_wids=list(process.modified_rna_wids),
    )
    return {
        "substrates": np.asarray(
            project_observable_from_state(
                process=process,
                state=runtime_state,
                observable="substrates",
                wids=substrate_wids,
                bound_enzymes_before=bound_enzymes_before,
            ),
            dtype=np.float64,
        ),
        "RNAs": np.asarray(
            np.concatenate([full_unmodified_after, full_modified_after]),
            dtype=np.float64,
        ),
        "sample_seed": _sample_seed(seed, tick),
    }


def _run_trna_aminoacylation_tick(seed: int, tick: int, state: dict[str, Any]) -> dict[str, Any]:
    """Run one OpenCell tRNAAminoacylation tick from a prepared state snapshot."""
    process = _trna_aminoacylation_process(_sample_seed(seed, tick))
    metadata = _trna_aminoacylation_channel_metadata()
    runtime_state = build_state_template(process)
    substrate_wids = list(state["substrate_wids"])
    enzyme_wids = list(state["enzyme_wids"])
    bound_enzymes_before = np.asarray(state["oracle_before_bound_enzymes"], dtype=np.float64)
    free_before, aminoacylated_before = _split_rna_vector(
        np.asarray(state["oracle_before_rnas"], dtype=np.float64),
        (
            len(metadata["free_wids"]),
            len(metadata["aminoacylated_wids"]),
        ),
    )

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
        observable="freeRNAs",
        vector=free_before,
        wids=list(process.free_rna_wids),
    )
    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="aminoacylatedRNAs",
        vector=aminoacylated_before,
        wids=list(process.aminoacylated_rna_wids),
    )
    refresh_allocator_views(process, runtime_state)
    with forbid_sut_oracle_file_io():
        update = process.next_update(1.0, runtime_state)
    apply_count_update(runtime_state, update)

    free_after = project_observable_from_state(
        process=process,
        state=runtime_state,
        observable="freeRNAs",
        wids=list(process.free_rna_wids),
        bound_enzymes_before=bound_enzymes_before,
    )
    aminoacylated_after = project_observable_from_state(
        process=process,
        state=runtime_state,
        observable="aminoacylatedRNAs",
        wids=list(process.aminoacylated_rna_wids),
        bound_enzymes_before=bound_enzymes_before,
    )
    return {
        "substrates": np.asarray(
            project_observable_from_state(
                process=process,
                state=runtime_state,
                observable="substrates",
                wids=substrate_wids,
                bound_enzymes_before=bound_enzymes_before,
            ),
            dtype=np.float64,
        ),
        "RNAs": np.asarray(
            np.concatenate([free_after, aminoacylated_after]),
            dtype=np.float64,
        ),
        "sample_seed": _sample_seed(seed, tick),
    }


def _run_protein_decay_tick(seed: int, tick: int, state: dict[str, Any]) -> dict[str, Any]:
    """Run one OpenCell ProteinDecay tick from a prepared state snapshot."""
    process = _protein_decay_process(_sample_seed(seed, tick))
    runtime_state = build_state_template(process)
    substrate_wids = list(state["substrate_wids"])
    enzyme_wids = list(state["enzyme_wids"])
    monomer_wids = list(state["monomer_wids"])
    complex_wids = list(state["complex_wids"])
    bound_enzymes_before = np.zeros(len(enzyme_wids), dtype=np.float64)

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
        observable="monomers",
        vector=np.asarray(state["oracle_before_monomers"], dtype=np.float64),
        wids=monomer_wids,
    )
    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="complexs",
        vector=np.asarray(state["oracle_before_complexs"], dtype=np.float64),
        wids=complex_wids,
    )
    # Do not feed ProteinDecay's measured channels back through trace_hint:
    # ProteinDecayLightProcess.next_update has a trace-hint replay path for
    # substrates/monomers/complexs, so doing so launders the oracle directly
    # into the projected output instead of measuring the SUT update.
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
                bound_enzymes_before=bound_enzymes_before,
            ),
            dtype=np.float64,
        ),
        "monomers": np.asarray(
            project_observable_from_state(
                process=process,
                state=runtime_state,
                observable="monomers",
                wids=monomer_wids,
                bound_enzymes_before=bound_enzymes_before,
            ),
            dtype=np.float64,
        ),
        "complexs": np.asarray(
            project_observable_from_state(
                process=process,
                state=runtime_state,
                observable="complexs",
                wids=complex_wids,
                bound_enzymes_before=bound_enzymes_before,
            ),
            dtype=np.float64,
        ),
        "sample_seed": _sample_seed(seed, tick),
    }


def _run_macromol_tick(seed: int, tick: int, state: dict[str, Any]) -> dict[str, Any]:
    """Run one OpenCell MacromolecularComplexation tick from a prepared state snapshot."""
    process = _macromol_process(_sample_seed(seed, tick))
    runtime_state = build_state_template(process)
    substrate_wids = list(state["substrate_wids"])
    monomer_wids = list(state["monomer_wids"])
    complex_wids = list(state["complex_wids"])

    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="substrates",
        vector=np.asarray(state["oracle_before_substrates"], dtype=np.float64),
        wids=substrate_wids,
    )
    # MacromolecularComplexation's logical monomer channel is the monomer-only
    # subset of the mixed substrate pool; keep it in the same underlying store.
    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="monomers",
        vector=np.asarray(state["oracle_before_monomers"], dtype=np.float64),
        wids=monomer_wids,
        store_path_override=_MACROMOL_MONOMER_STORE_PATH_OVERRIDE,
    )
    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="complexs",
        vector=np.asarray(state["oracle_before_complexs"], dtype=np.float64),
        wids=complex_wids,
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
                bound_enzymes_before=None,
            ),
            dtype=np.float64,
        ),
        "monomers": np.asarray(
            project_observable_from_state(
                process=process,
                state=runtime_state,
                observable="monomers",
                wids=monomer_wids,
                bound_enzymes_before=None,
                store_path_override=_MACROMOL_MONOMER_STORE_PATH_OVERRIDE,
            ),
            dtype=np.float64,
        ),
        "complexs": np.asarray(
            project_observable_from_state(
                process=process,
                state=runtime_state,
                observable="complexs",
                wids=complex_wids,
                bound_enzymes_before=None,
            ),
            dtype=np.float64,
        ),
        "sample_seed": _sample_seed(seed, tick),
    }


def _run_cytokinesis_tick(seed: int, tick: int, state: dict[str, Any]) -> dict[str, Any]:
    """Run one OpenCell Cytokinesis tick from a prepared state snapshot.

    Cytokinesis has primary_channel=substrates per catalog. The SUT exposes 4 substrate
    WIDs (GTP, H, H2O, PI) but the Karr replay oracle only snapshots the 3 reaction
    byproducts (PI, H2O, H - GTP hydrolysis products). Project SUT output down to the
    3 oracle WIDs for the W1 comparison.

    The SUT writes substrates only when the division event fires within the tick's
    seed_window=[-50, 0] from division. Expected verdict at flat 100-tick replay is
    INSUFFICIENT_SAMPLES per catalog notes.
    """
    process = _cytokinesis_process(_sample_seed(seed, tick))
    runtime_state = build_state_template(process)
    sut_substrate_wids = list(process._substrate_wids)
    oracle_substrate_wids = list(state["substrate_wids"])
    enzyme_wids = list(state["enzyme_wids"])
    bound_enzymes_before = np.asarray(state["oracle_before_bound_enzymes"], dtype=np.float64)

    oracle_before_substrates = np.asarray(state["oracle_before_substrates"], dtype=np.float64)
    sut_before_substrates = np.zeros(len(sut_substrate_wids), dtype=np.float64)
    for oracle_idx, wid in enumerate(oracle_substrate_wids):
        if wid in sut_substrate_wids:
            sut_idx = sut_substrate_wids.index(wid)
            sut_before_substrates[sut_idx] = oracle_before_substrates[oracle_idx]

    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="substrates",
        vector=sut_before_substrates,
        wids=sut_substrate_wids,
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
        vector=bound_enzymes_before,
        wids=enzyme_wids,
    )
    refresh_allocator_views(process, runtime_state)
    with forbid_sut_oracle_file_io():
        update = process.next_update(1.0, runtime_state)
    apply_count_update(runtime_state, update)

    sut_substrates_after = np.asarray(
        project_observable_from_state(
            process=process,
            state=runtime_state,
            observable="substrates",
            wids=sut_substrate_wids,
            bound_enzymes_before=bound_enzymes_before,
        ),
        dtype=np.float64,
    )
    oracle_substrates_out = np.zeros(len(oracle_substrate_wids), dtype=np.float64)
    for oracle_idx, wid in enumerate(oracle_substrate_wids):
        if wid in sut_substrate_wids:
            sut_idx = sut_substrate_wids.index(wid)
            oracle_substrates_out[oracle_idx] = sut_substrates_after[sut_idx]

    return {
        "substrates": oracle_substrates_out,
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


@lru_cache(maxsize=1)
def _translation_projection_inputs() -> dict[str, Any]:
    process = _translation_process(0)
    return {
        "karr_substrate_wids": tuple(load_fixture_channel_wids("Translation", "substrates")),
        "oc_substrate_wids": tuple(str(x) for x in getattr(process, "aa_ids", ())),
    }


def _project_translation_substrate_cube(values: np.ndarray) -> np.ndarray:
    inputs = _translation_projection_inputs()
    arr = np.asarray(values, dtype=np.float64)
    out = np.zeros((arr.shape[0], len(inputs["oc_substrate_wids"])), dtype=np.float64)
    for tick in range(arr.shape[0]):
        out[tick, :] = project_vector_onto_wids(
            karr_vector=arr[tick],
            karr_wids=inputs["karr_substrate_wids"],
            oc_wids=inputs["oc_substrate_wids"],
        )
    return out


@lru_cache(maxsize=1)
def _protein_decay_projection_inputs() -> dict[str, Any]:
    process = _protein_decay_process(0)
    return {
        "complex_width": len(process.complex_wids),
    }


def _project_protein_decay_monomer_cube(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    return np.asarray(
        [project_trace_matrix_to_482(arr[tick]) for tick in range(arr.shape[0])],
        dtype=np.float64,
    )


def _project_protein_decay_complex_cube(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    complex_width = int(_protein_decay_projection_inputs()["complex_width"])
    flat = arr.reshape(arr.shape[0], -1)
    return np.asarray(flat[:, :complex_width], dtype=np.float64)


def _project_macromol_monomer_cube(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    monomer_indices = np.asarray(_macromol_channel_metadata()["monomer_indices"], dtype=np.int64)
    return np.asarray(arr[:, monomer_indices], dtype=np.float64)


__all__ = [
    "ALGORITHMIC_DEEP_K_ENG",
    "ALGORITHMIC_SHALLOW_K_ENG",
    "ABSOLUTE_FLOOR",
    "L2_2_VALIDATION_SEED",
    "TRIVIAL_RNG_K_ENG",
    "_METABOLISM_ORACLE_PATH",
    "_TRANSLATION_ORACLE_PATH",
    "_RNA_DECAY_ORACLE_PATH",
    "_PROTEIN_DECAY_ORACLE_PATH",
    "_TRANSCRIPTION_ORACLE_PATH",
    "compute_null_q95",
    "compute_w1",
    "load_karr_oracle",
    "run_oc_tick",
]
