from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
import re
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
    project_trace_matrix_to_482,
    refresh_allocator_views,
)
from opencell.m3 import translation as m3_karr_translation  # noqa: E402
from opencell.m1 import karr_metabolism as m1_karr_metabolism  # noqa: E402
from opencell.vivarium.karr_metabolism import KarrMetabolismProcess  # noqa: E402
from opencell.vivarium.karr_translation import KarrTranslationProcess  # noqa: E402
from opencell.vivarium.karr_transcription import KarrTranscriptionProcess  # noqa: E402
from opencell.vivarium.karr_rna_decay import RnaDecayLightProcess  # noqa: E402
from opencell.vivarium.karr_protein_decay_light import ProteinDecayLightProcess  # noqa: E402
from opencell.vivarium.karr_macromolecular_complexation import (  # noqa: E402
    MacromolecularComplexationProcess,
)
from opencell.vivarium.karr_replication_initiation import KarrReplicationInitiationProcess  # noqa: E402


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
_MACROMOL_ORACLE_PATH = (
    _REPO_ROOT / "data" / "karr_fixtures" / "per_process_replay" / "MacromolecularComplexation.npz"
)
_REPLICATION_INITIATION_ORACLE_PATH = (
    _REPO_ROOT
    / "data"
    / "karr_fixtures"
    / "per_process_replay"
    / "ReplicationInitiation_from_trajectory.npz"
)
_TRANSLATION_MRNA_STORE_PATH_OVERRIDE = {"mRNAs": ("rna", "counts")}
_RNA_STORE_PATH_OVERRIDE = {"RNAs": ("rna", "counts")}
_RNA_SLOT_COUNTS_STATE_KEY = "_l2_rna_slot_counts"
_RNA_SLOT_WIDS_STATE_KEY = "_l2_rna_slot_wids"


def _oracle_dispatch() -> dict[str, Any]:
    return {
        "Metabolism": _load_metabolism_oracle,
        "Translation": _load_translation_oracle,
        "Transcription": _load_transcription_oracle,
        "RNADecay": _load_rna_decay_oracle,
        "ProteinDecay": _load_protein_decay_oracle,
        "MacromolecularComplexation": _load_macromol_oracle,
        "ReplicationInitiation": _load_replication_initiation_oracle,
    }


def load_karr_oracle(process: str) -> dict[str, Any]:
    """Load the canonical Karr replay fixture for a Design-A process."""
    loaders = _oracle_dispatch()
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
    if not _MACROMOL_ORACLE_PATH.exists():
        raise FileNotFoundError(
            f"Missing MacromolecularComplexation oracle fixture: {_MACROMOL_ORACLE_PATH}"
        )

    with np.load(_MACROMOL_ORACLE_PATH, allow_pickle=False) as payload:
        before_substrates = np.asarray(payload["state_before__substrates"], dtype=np.float64)[:, 0, :]
        after_substrates = np.asarray(payload["states_after__substrates"], dtype=np.float64)[:, 0, :]
        before_complexs = np.asarray(payload["state_before__complexs"], dtype=np.float64)[:, 0, :]
        after_complexs = np.asarray(payload["states_after__complexs"], dtype=np.float64)[:, 0, :]

    n_ticks = int(before_substrates.shape[0])
    # The replay export stores MATLAB-empty enzyme arrays as width-2 placeholders,
    # but the SUT exposes zero enzyme WIDs; normalize them to true zero-width cubes.
    before_enzymes = np.zeros((n_ticks, 0), dtype=np.float64)

    return {
        "process": "MacromolecularComplexation",
        "oracle_path": _MACROMOL_ORACLE_PATH,
        "canonical_seed_count": 1,
        "n_ticks_available": n_ticks,
        "before_substrates": before_substrates[np.newaxis, :, :],
        "before_enzymes": before_enzymes[np.newaxis, :, :],
        "before_complexs": before_complexs[np.newaxis, :, :],
        "after_substrates": after_substrates[np.newaxis, :, :],
        "after_complexs": after_complexs[np.newaxis, :, :],
    }


def _load_replication_initiation_oracle() -> dict[str, Any]:
    if not _REPLICATION_INITIATION_ORACLE_PATH.exists():
        raise FileNotFoundError(
            "Missing ReplicationInitiation oracle fixture: "
            f"{_REPLICATION_INITIATION_ORACLE_PATH}"
        )

    with np.load(_REPLICATION_INITIATION_ORACLE_PATH, allow_pickle=True) as payload:
        before_substrates = np.asarray(payload["state_before__substrates"], dtype=np.float64)[:, 0, :]
        before_enzymes = np.asarray(payload["state_before__enzymes"], dtype=np.float64)[:, 0, :]
        before_bound = np.asarray(payload["state_before__boundEnzymes"], dtype=np.float64)[:, 0, :]
        after_substrates = np.asarray(payload["states_after__substrates"], dtype=np.float64)[:, 0, :]
        after_enzymes = np.asarray(payload["states_after__enzymes"], dtype=np.float64)[:, 0, :]
        after_bound = np.asarray(payload["states_after__boundEnzymes"], dtype=np.float64)[:, 0, :]

    return {
        "process": "ReplicationInitiation",
        "oracle_path": _REPLICATION_INITIATION_ORACLE_PATH,
        "canonical_seed_count": 1,
        "n_ticks_available": int(before_substrates.shape[0]),
        "before_substrates": before_substrates[np.newaxis, :, :],
        "before_enzymes": before_enzymes[np.newaxis, :, :],
        "before_bound_enzymes": before_bound[np.newaxis, :, :],
        "after_substrates": after_substrates[np.newaxis, :, :],
        "after_enzymes": after_enzymes[np.newaxis, :, :],
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
def _protein_decay_process(seed: int) -> ProteinDecayLightProcess:
    with forbid_sut_oracle_file_io():
        return ProteinDecayLightProcess({"rng_seed": int(seed)})


@lru_cache(maxsize=None)
def _macromol_process(seed: int) -> MacromolecularComplexationProcess:
    with forbid_sut_oracle_file_io():
        return MacromolecularComplexationProcess({"rng_seed": int(seed)})
def _replication_initiation_process(seed: int) -> KarrReplicationInitiationProcess:
    with forbid_sut_oracle_file_io():
        return KarrReplicationInitiationProcess({"rng_seed": int(seed)})


def _sample_seed(seed: int, tick: int) -> int:
    ss = np.random.SeedSequence([L2_2_VALIDATION_SEED, int(seed), int(tick)])
    return int(ss.generate_state(1, dtype=np.uint32)[0])


def _tick_dispatch() -> dict[str, Any]:
    return {
        "Metabolism": _run_metabolism_tick,
        "Translation": _run_translation_tick,
        "Transcription": _run_transcription_tick,
        "RNADecay": _run_rna_decay_tick,
        "ProteinDecay": _run_protein_decay_tick,
        "MacromolecularComplexation": _run_macromol_tick,
        "ReplicationInitiation": _run_repinit_tick,
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
    """Run one OpenCell MacromolecularComplexation tick from a prepared snapshot."""
    process = _macromol_process(_sample_seed(seed, tick))
    runtime_state = build_state_template(process)
    substrate_wids = list(state["substrate_wids"])
    complex_wids = list(state["complex_wids"])
    bound_enzymes_before = np.zeros(0, dtype=np.float64)

    maybe_replay = getattr(process, "_maybe_replay_from_hint", None)
    if callable(maybe_replay):
        setattr(process, "_maybe_replay_from_hint", lambda *_args, **_kwargs: None)

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




def _repinit_species_descriptor(wid: str) -> tuple[int, int]:
    if wid == "MG_469_MONOMER":
        return (1, 0)

    mixed_match = re.search(r"_(\d+)MER_(\d+)ATP_ADP$", wid)
    if mixed_match:
        mer_length = int(mixed_match.group(1))
        atp_moieties = int(mixed_match.group(2))
        return (mer_length, atp_moieties)

    atp_match = re.search(r"_(\d+)MER_ATP$", wid)
    if atp_match:
        mer_length = int(atp_match.group(1))
        return (mer_length, mer_length)

    adp_match = re.search(r"_(\d+)MER_ADP$", wid)
    if adp_match:
        mer_length = int(adp_match.group(1))
        return (mer_length, 0)

    raise ValueError(f"Unrecognized ReplicationInitiation DnaA species wid: {wid!r}")


def _prime_repinit_state_from_trace(
    *,
    process: KarrReplicationInitiationProcess,
    state: dict[str, Any],
    enzyme_before: np.ndarray,
    bound_before: np.ndarray,
) -> None:
    enzyme_vec = np.asarray(enzyme_before, dtype=np.float64).reshape(-1)
    bound_vec = np.asarray(bound_before, dtype=np.float64).reshape(-1)
    if enzyme_vec.size != len(process.enzyme_wids):
        raise ValueError(
            "ReplicationInitiation enzyme width mismatch: "
            f"{enzyme_vec.size} vs {len(process.enzyme_wids)}"
        )
    if bound_vec.size != len(process.enzyme_wids):
        raise ValueError(
            "ReplicationInitiation bound-enzyme width mismatch: "
            f"{bound_vec.size} vs {len(process.enzyme_wids)}"
        )

    free_dnaa_adp = 0
    free_dnaa_atp = 0
    bound_atp = np.zeros(process.n_sites, dtype=np.int64)
    bound_adp = np.zeros(process.n_sites, dtype=np.int64)
    site_totals = state["chromosome"]["dnaa_complex_count"]
    candidate_sites = list(process.non_oric_site_ids) + list(process.oric_site_ids)
    site_cursor = 0

    for wid, raw_count in zip(process.enzyme_wids, enzyme_vec, strict=False):
        count = max(0, int(np.rint(float(raw_count))))
        if count <= 0:
            continue
        mer_length, atp_moieties = _repinit_species_descriptor(wid)
        free_dnaa_atp += count * atp_moieties
        free_dnaa_adp += count * (mer_length - atp_moieties)

    for wid, raw_count in zip(process.enzyme_wids, bound_vec, strict=False):
        count = max(0, int(np.rint(float(raw_count))))
        if count <= 0:
            continue
        mer_length, atp_moieties = _repinit_species_descriptor(wid)
        adp_moieties = mer_length - atp_moieties
        for _ in range(count):
            if site_cursor >= len(candidate_sites):
                raise ValueError(
                    "ReplicationInitiation bound-site reconstruction exhausted candidate sites."
                )
            site_id = candidate_sites[site_cursor]
            site_cursor += 1
            site_idx = process.site_id_to_index[site_id]
            bound_atp[site_idx] = atp_moieties
            bound_adp[site_idx] = adp_moieties
            site_totals[site_id] = float(mer_length)

    dnaa_adp_wid, dnaa_atp_wid = process.enzyme_wids[0], process.enzyme_wids[1]
    protein_counts = state["protein"]["counts"]
    protein_counts[dnaa_adp_wid] = float(free_dnaa_adp)
    protein_counts[dnaa_atp_wid] = float(free_dnaa_atp)

    process._initialized = True
    process._free_dnaa_adp = int(free_dnaa_adp)
    process._free_dnaa_atp = int(free_dnaa_atp)
    process._bound_atp = bound_atp
    process._bound_adp = bound_adp


def _run_repinit_tick(seed: int, tick: int, state: dict[str, Any]) -> dict[str, Any]:
    """Run one OpenCell ReplicationInitiation tick from a prepared state snapshot."""
    process = _replication_initiation_process(_sample_seed(seed, tick))
    runtime_state = build_state_template(process)
    substrate_wids = list(state["substrate_wids"])
    enzyme_wids = list(state["enzyme_wids"])

    substrate_before = np.asarray(state["oracle_before_substrates"], dtype=np.float64)
    enzyme_before = np.asarray(state["oracle_before_enzymes"], dtype=np.float64)
    bound_before = np.asarray(state["oracle_before_bound_enzymes"], dtype=np.float64)

    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="substrates",
        vector=substrate_before,
        wids=substrate_wids,
    )
    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="enzymes",
        vector=enzyme_before,
        wids=enzyme_wids,
    )
    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="boundEnzymes",
        vector=bound_before,
        wids=enzyme_wids,
    )
    _prime_repinit_state_from_trace(
        process=process,
        state=runtime_state,
        enzyme_before=enzyme_before,
        bound_before=bound_before,
    )
    refresh_allocator_views(process, runtime_state)
    runtime_state["trace_hint"] = {}
    runtime_state["substrates_allocated"][process.name][process.atp_wid] = float(
        substrate_before[process.substrate_index_atp]
    )
    runtime_state["substrates_allocated"][process.name][process.water_wid] = float(
        substrate_before[process.substrate_index_water]
    )
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
                bound_enzymes_before=bound_before,
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
    "_MACROMOL_ORACLE_PATH",
    "_REPLICATION_INITIATION_ORACLE_PATH",
    "_TRANSCRIPTION_ORACLE_PATH",
    "compute_null_q95",
    "compute_w1",
    "load_karr_oracle",
    "run_oc_tick",
]
