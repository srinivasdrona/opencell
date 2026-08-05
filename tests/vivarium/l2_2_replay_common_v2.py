from __future__ import annotations

import hashlib
import json
import sys
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pytest

# Ensure pytest imports from this worktree even if another editable install exists.
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

from l2_replay_common import (
    apply_count_update,
    assert_delta_integral,
    audit_trace_mutated_ticks,
    build_state_template,
    cell_vector,
    collect_count_delta_dicts,
    infer_wids_for_observable,
    overlay_observable_into_state,
    overlay_trace_after_hint,
    project_karr_vector,
    project_observable_from_state,
    refresh_allocator_views,
    refresh_allocator_views_composition,
    resolve_trace_path,
)
from l2_replay_common import (
    assert_identity_or_tolerance as _assert_identity_or_tolerance_shared,
)

from opencell.state.chromosome_store import ChromosomeStore
from opencell.vivarium.karr_chromosome_condensation import KarrChromosomeCondensationProcess
from opencell.vivarium.karr_chromosome_segregation import KarrChromosomeSegregationProcess
from opencell.vivarium.karr_cytokinesis import KarrCytokinesisProcess
from opencell.vivarium.karr_dna_damage import KarrDNADamageProcess
from opencell.vivarium.karr_dna_repair import KarrDNARepairProcess
from opencell.vivarium.karr_dna_supercoiling import KarrDNASupercoilingProcess
from opencell.vivarium.karr_ftsz_polymerization import KarrFtsZPolymerizationProcess
from opencell.vivarium.karr_host_interaction import KarrHostInteractionProcess
from opencell.vivarium.karr_macromolecular_complexation import MacromolecularComplexationProcess
from opencell.vivarium.karr_metabolism import KarrMetabolismProcess
from opencell.vivarium.karr_protein_activation import KarrProteinActivationProcess
from opencell.vivarium.karr_protein_decay_light import ProteinDecayLightProcess
from opencell.vivarium.karr_protein_folding import KarrProteinFoldingProcess
from opencell.vivarium.karr_protein_modification import KarrProteinModificationProcess
from opencell.vivarium.karr_protein_processing_i import KarrProteinProcessingIProcess
from opencell.vivarium.karr_protein_processing_ii import KarrProteinProcessingIIProcess
from opencell.vivarium.karr_protein_translocation import KarrProteinTranslocationProcess
from opencell.vivarium.karr_replication import KarrReplicationProcess
from opencell.vivarium.karr_replication_initiation import KarrReplicationInitiationProcess
from opencell.vivarium.karr_ribosome_assembly import KarrRibosomeAssemblyProcess
from opencell.vivarium.karr_rna_decay import RnaDecayLightProcess
from opencell.vivarium.karr_rna_modification import KarrRNAModificationProcess
from opencell.vivarium.karr_rna_processing import KarrRNAProcessingProcess
from opencell.vivarium.karr_terminal_organelle_assembly import KarrTerminalOrganelleAssemblyProcess
from opencell.vivarium.karr_transcription import KarrTranscriptionProcess
from opencell.vivarium.karr_transcriptional_regulation import KarrTranscriptionalRegulationProcess
from opencell.vivarium.karr_translation_v3 import KarrTranslationV3Process
from opencell.vivarium.karr_trna_aminoacylation import KarrTRNAAminoacylationProcess

_COMPOSITION_ORDER_V2 = (
    "Translation",
    "RNAProcessing",
    "ProteinProcessingI",
    "ProteinProcessingII",
    "ChromosomeCondensation",
    "ChromosomeSegregation",
    "HostInteraction",
    "TerminalOrganelleAssembly",
    "Transcription",
    "RNADecay",
    "RNAModification",
    "ProteinDecay",
    "ProteinModification",
    "Metabolism",
    "tRNAAminoacylation",
    "MacromolecularComplexation",
    "ProteinFolding",
    "ProteinTranslocation",
    "DNASupercoiling",
    "Replication",
    "ReplicationInitiation",
    "DNARepair",
    "Cytokinesis",
    "FtsZPolymerization",
    "RibosomeAssembly",
    "DNADamage",
    "ProteinActivation",
    "TranscriptionalRegulation",
)

ORACLE_DISTRIBUTIONAL = "distributional"
ORACLE_BIT_IDENTITY = "bit_identity"
_SUPPORTED_ORACLE_TYPES = {
    ORACLE_DISTRIBUTIONAL,
    ORACLE_BIT_IDENTITY,
}

CAUSE_1_WID_SET_MISMATCH = "CAUSE_1_WID_SET_MISMATCH"
CAUSE_2_ORACLE_INJECTION_MISALIGNMENT = "CAUSE_2_ORACLE_INJECTION_MISALIGNMENT"
CAUSE_3_COMPOSITION_ORDER_ERROR = "CAUSE_3_COMPOSITION_ORDER_ERROR"
CAUSE_4_UPSTREAM_STATE_POLLUTION = "CAUSE_4_UPSTREAM_STATE_POLLUTION"
CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE = "CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE"
CAUSE_6_HARNESS_BUG = "CAUSE_6_HARNESS_BUG"
CAUSE_7_ORACLE_TRACE_DEFECT = "CAUSE_7_ORACLE_TRACE_DEFECT"
CAUSE_UNCLASSIFIED = "CAUSE_UNCLASSIFIED"

_CAUSE_CODES = {
    CAUSE_1_WID_SET_MISMATCH,
    CAUSE_2_ORACLE_INJECTION_MISALIGNMENT,
    CAUSE_3_COMPOSITION_ORDER_ERROR,
    CAUSE_4_UPSTREAM_STATE_POLLUTION,
    CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE,
    CAUSE_6_HARNESS_BUG,
    CAUSE_7_ORACLE_TRACE_DEFECT,
    CAUSE_UNCLASSIFIED,
}

# Generated per run from the under-test set. Tests may override selected entries.
OWNER_MANIFEST: dict[str, str] = {}
OWNER_MANIFEST_OVERRIDES: dict[str, str] = {}


@dataclass(frozen=True)
class _ProcessSpec:
    process_cls: type
    observables: tuple[str, ...]
    pass_through: frozenset[str]
    observable_to_wids_attr: dict[str, str]
    store_path_override: dict[str, tuple[str, ...]] | None = None
    index_projection_literal: dict[str, Any] | None = None
    trace_after_hint_observables: tuple[str, ...] = ()
    hidden_read_surface: tuple[str, ...] = ()
    requires_hints_for_honest_mode: bool = False
    oracle_type: str = ORACLE_DISTRIBUTIONAL


@dataclass
class _ProcessContext:
    name: str
    spec: _ProcessSpec
    process: Any
    trace: h5py.File
    n_ticks: int
    wids_by_observable: dict[str, list[str]]
    process_wid_to_master_idx: dict[str, dict[str, int]] = field(default_factory=dict)
    master_idx_to_process_wid: dict[str, dict[int, str]] = field(default_factory=dict)
    process_idx_to_master_idx: dict[str, dict[int, int]] = field(default_factory=dict)


_PROCESS_SPECS: dict[str, _ProcessSpec] = {
    "Translation": _ProcessSpec(
        process_cls=KarrTranslationV3Process,
        observables=("substrates", "enzymes", "boundEnzymes", "monomers"),
        pass_through=frozenset(),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
            "monomers": "protein_ids",
        },
        index_projection_literal={"substrates": np.arange(26)},
        trace_after_hint_observables=("enzymes", "boundEnzymes", "substrates"),
    ),
    "RNAProcessing": _ProcessSpec(
        process_cls=KarrRNAProcessingProcess,
        observables=("substrates", "enzymes", "boundEnzymes", "processedRNAs", "unprocessedRNAs"),
        pass_through=frozenset({"boundEnzymes", "enzymes"}),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
            "processedRNAs": "processed_rna_wids",
            "unprocessedRNAs": "unprocessed_rna_wids",
        },
    ),
    "Transcription": _ProcessSpec(
        process_cls=KarrTranscriptionProcess,
        observables=("substrates", "enzymes", "boundEnzymes"),
        pass_through=frozenset({"boundEnzymes", "enzymes"}),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
        },
        # Faithful 12-species transcription substrate vocabulary from fixture.
        index_projection_literal={"substrates": np.arange(12)},
        trace_after_hint_observables=("enzymes", "boundEnzymes", "substrates"),
    ),
    "RNADecay": _ProcessSpec(
        process_cls=RnaDecayLightProcess,
        observables=("substrates", "enzymes", "boundEnzymes"),
        pass_through=frozenset({"boundEnzymes", "enzymes"}),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
        },
        trace_after_hint_observables=("substrates",),
    ),
    "RNAModification": _ProcessSpec(
        process_cls=KarrRNAModificationProcess,
        observables=("substrates", "enzymes", "boundEnzymes", "modifiedRNAs", "unmodifiedRNAs"),
        pass_through=frozenset({"boundEnzymes", "enzymes"}),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
            "modifiedRNAs": "modified_rna_wids",
            "unmodifiedRNAs": "unmodified_rna_wids",
        },
        index_projection_literal={
            "modifiedRNAs": np.array(
                [
                    6, 7, 37, 88, 89, 125, 136, 137, 138, 139, 140, 141, 142, 143, 148,
                    168, 170, 171, 175, 190, 191, 192, 193, 194, 199, 225, 226, 228, 229,
                    230, 231, 232, 233, 234, 259, 261, 263, 287,
                ]
            ),
            "unmodifiedRNAs": np.array(
                [
                    6, 7, 37, 88, 89, 125, 136, 137, 138, 139, 140, 141, 142, 143, 148,
                    168, 170, 171, 175, 190, 191, 192, 193, 194, 199, 225, 226, 228, 229,
                    230, 231, 232, 233, 234, 259, 261, 263, 287,
                ]
            ),
        },
    ),
    "ProteinDecay": _ProcessSpec(
        process_cls=ProteinDecayLightProcess,
        observables=("substrates", "enzymes", "boundEnzymes", "monomers", "complexs"),
        pass_through=frozenset({"boundEnzymes", "enzymes"}),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
            "monomers": "protein_wids",
            "complexs": "complex_wids",
        },
        index_projection_literal={
            "monomers": np.arange(482),
            "complexs": np.arange(147),
        },
        trace_after_hint_observables=("substrates", "monomers", "complexs"),
    ),
    "ProteinModification": _ProcessSpec(
        process_cls=KarrProteinModificationProcess,
        observables=("substrates", "enzymes", "boundEnzymes", "modifiedMonomers", "unmodifiedMonomers"),
        pass_through=frozenset({"boundEnzymes", "enzymes"}),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
            "modifiedMonomers": "modified_monomer_wids",
            "unmodifiedMonomers": "unmodified_monomer_wids",
        },
        store_path_override={
            "modifiedMonomers": ("protein", "modified_counts"),
            "unmodifiedMonomers": ("protein", "unmodified_counts"),
        },
        index_projection_literal={
            "modifiedMonomers": np.array(
                [
                    69, 168, 221, 223, 279, 280, 281, 289, 313, 325,
                    337, 353, 390, 406, 415, 421, 438, 448, 461, 470,
                ]
            ),
            "unmodifiedMonomers": np.array(
                [
                    69, 168, 221, 223, 279, 280, 281, 289, 313, 325,
                    337, 353, 390, 406, 415, 421, 438, 448, 461, 470,
                ]
            ),
        },
        trace_after_hint_observables=("unmodifiedMonomers",),
    ),
    "Metabolism": _ProcessSpec(
        process_cls=KarrMetabolismProcess,
        observables=("substrates", "enzymes", "boundEnzymes"),
        pass_through=frozenset({"boundEnzymes", "enzymes"}),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
        },
        index_projection_literal={"substrates": np.arange(585)},
        trace_after_hint_observables=("substrates",),
    ),
    "tRNAAminoacylation": _ProcessSpec(
        process_cls=KarrTRNAAminoacylationProcess,
        observables=("substrates", "enzymes", "boundEnzymes", "freeRNAs", "aminoacylatedRNAs"),
        pass_through=frozenset({"boundEnzymes", "enzymes"}),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
            "freeRNAs": "free_rna_wids",
            "aminoacylatedRNAs": "aminoacylated_rna_wids",
        },
    ),
    "MacromolecularComplexation": _ProcessSpec(
        process_cls=MacromolecularComplexationProcess,
        observables=("substrates", "enzymes", "boundEnzymes", "complexs"),
        pass_through=frozenset({"boundEnzymes", "enzymes"}),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
            "complexs": "complex_wids",
        },
    ),
    "ProteinFolding": _ProcessSpec(
        process_cls=KarrProteinFoldingProcess,
        observables=("substrates", "enzymes", "boundEnzymes", "foldedMonomers", "unfoldedMonomers"),
        pass_through=frozenset({"boundEnzymes", "enzymes"}),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
            "foldedMonomers": "folded_monomer_wids",
            "unfoldedMonomers": "unfolded_monomer_wids",
        },
    ),
    "ProteinTranslocation": _ProcessSpec(
        process_cls=KarrProteinTranslocationProcess,
        observables=("substrates", "enzymes", "boundEnzymes", "monomers"),
        pass_through=frozenset({"boundEnzymes", "enzymes"}),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
            "monomers": "monomer_wids",
        },
        index_projection_literal={"monomers": np.arange(482)},
    ),
    "DNASupercoiling": _ProcessSpec(
        process_cls=KarrDNASupercoilingProcess,
        observables=("substrates", "enzymes", "boundEnzymes"),
        pass_through=frozenset({"boundEnzymes", "enzymes"}),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
        },
        trace_after_hint_observables=("enzymes", "boundEnzymes", "substrates"),
        hidden_read_surface=(
            "chromosome",
            "stimulus.values",
            "rnaPolymerase.supercoilingBindingProbFoldChange",
        ),
    ),
    "Replication": _ProcessSpec(
        process_cls=KarrReplicationProcess,
        observables=("substrates", "enzymes", "boundEnzymes"),
        pass_through=frozenset({"boundEnzymes", "enzymes"}),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
        },
        trace_after_hint_observables=("enzymes", "boundEnzymes"),
        hidden_read_surface=("chromosome",),
    ),
    "ReplicationInitiation": _ProcessSpec(
        process_cls=KarrReplicationInitiationProcess,
        observables=("substrates", "enzymes", "boundEnzymes"),
        pass_through=frozenset(),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
        },
        trace_after_hint_observables=("enzymes", "boundEnzymes"),
        hidden_read_surface=("chromosome",),
    ),
    "DNARepair": _ProcessSpec(
        process_cls=KarrDNARepairProcess,
        observables=("substrates", "enzymes", "boundEnzymes"),
        pass_through=frozenset({"boundEnzymes", "enzymes"}),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
        },
        hidden_read_surface=("chromosome",),
    ),
    "Cytokinesis": _ProcessSpec(
        process_cls=KarrCytokinesisProcess,
        observables=("substrates", "enzymes", "boundEnzymes"),
        pass_through=frozenset({"boundEnzymes", "enzymes"}),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
        },
        hidden_read_surface=("chromosome",),
    ),
    "FtsZPolymerization": _ProcessSpec(
        process_cls=KarrFtsZPolymerizationProcess,
        observables=("substrates", "enzymes", "boundEnzymes"),
        pass_through=frozenset({"boundEnzymes"}),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
        },
        trace_after_hint_observables=("enzymes", "boundEnzymes"),
    ),
    "RibosomeAssembly": _ProcessSpec(
        process_cls=KarrRibosomeAssemblyProcess,
        observables=("substrates", "enzymes", "boundEnzymes", "monomers", "complexs"),
        pass_through=frozenset({"boundEnzymes", "enzymes"}),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "gtpase_wids",
            "boundEnzymes": "gtpase_wids",
            "monomers": "monomer_subunit_wids",
            "complexs": "complex_wids",
        },
    ),
    "DNADamage": _ProcessSpec(
        process_cls=KarrDNADamageProcess,
        observables=("substrates", "enzymes", "boundEnzymes"),
        pass_through=frozenset({"boundEnzymes", "enzymes"}),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
        },
        hidden_read_surface=("chromosome",),
    ),
    "ProteinProcessingI": _ProcessSpec(
        process_cls=KarrProteinProcessingIProcess,
        observables=("substrates", "enzymes", "boundEnzymes", "processedMonomers", "unprocessedMonomers"),
        pass_through=frozenset({"boundEnzymes", "enzymes"}),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
            "processedMonomers": "processed_monomer_wids",
            "unprocessedMonomers": "unprocessed_monomer_wids",
        },
        store_path_override={
            "processedMonomers": ("protein", "processed_counts"),
            "unprocessedMonomers": ("protein", "unprocessed_counts"),
        },
    ),
    "ProteinProcessingII": _ProcessSpec(
        process_cls=KarrProteinProcessingIIProcess,
        observables=("substrates", "enzymes", "boundEnzymes", "processedMonomers", "unprocessedMonomers"),
        pass_through=frozenset({"boundEnzymes", "enzymes"}),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
            "processedMonomers": "processed_monomer_wids",
            "unprocessedMonomers": "unprocessed_monomer_wids",
        },
        store_path_override={
            "processedMonomers": ("protein", "processed_counts"),
            "unprocessedMonomers": ("protein", "counts"),
        },
    ),
    "ChromosomeCondensation": _ProcessSpec(
        process_cls=KarrChromosomeCondensationProcess,
        observables=("substrates", "enzymes", "boundEnzymes"),
        pass_through=frozenset(),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
        },
        trace_after_hint_observables=("enzymes", "boundEnzymes"),
        hidden_read_surface=("chromosome",),
        requires_hints_for_honest_mode=False,
        oracle_type=ORACLE_BIT_IDENTITY,
    ),
    "ChromosomeSegregation": _ProcessSpec(
        process_cls=KarrChromosomeSegregationProcess,
        observables=("substrates", "enzymes", "boundEnzymes"),
        pass_through=frozenset(),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
        },
        hidden_read_surface=("chromosome",),
        requires_hints_for_honest_mode=False,
        oracle_type=ORACLE_BIT_IDENTITY,
    ),
    "HostInteraction": _ProcessSpec(
        process_cls=KarrHostInteractionProcess,
        observables=("substrates", "enzymes", "boundEnzymes"),
        pass_through=frozenset(),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
        },
        requires_hints_for_honest_mode=False,
        oracle_type=ORACLE_BIT_IDENTITY,
    ),
    "ProteinActivation": _ProcessSpec(
        process_cls=KarrProteinActivationProcess,
        observables=("substrates", "enzymes", "boundEnzymes"),
        pass_through=frozenset({"boundEnzymes", "enzymes"}),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
        },
        index_projection_literal={"substrates": np.arange(10)},
        hidden_read_surface=("stimulus.values",),
        requires_hints_for_honest_mode=False,
        oracle_type=ORACLE_BIT_IDENTITY,
    ),
    "TerminalOrganelleAssembly": _ProcessSpec(
        process_cls=KarrTerminalOrganelleAssemblyProcess,
        observables=("substrates", "enzymes", "boundEnzymes"),
        pass_through=frozenset(),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
        },
        requires_hints_for_honest_mode=False,
        oracle_type=ORACLE_BIT_IDENTITY,
    ),
    "TranscriptionalRegulation": _ProcessSpec(
        process_cls=KarrTranscriptionalRegulationProcess,
        observables=("substrates", "enzymes", "boundEnzymes"),
        pass_through=frozenset({"boundEnzymes", "enzymes"}),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
        },
        trace_after_hint_observables=("enzymes", "boundEnzymes"),
        requires_hints_for_honest_mode=False,
        oracle_type=ORACLE_BIT_IDENTITY,
    ),
}


def _ordered_under_test(under_test_processes: list[str]) -> list[str]:
    unknown = [name for name in under_test_processes if name not in _PROCESS_SPECS]
    if unknown:
        pytest.fail(f"L2.2.v2 unsupported process name(s): {unknown}")
    under_test_set = set(under_test_processes)
    ordered = [name for name in _COMPOSITION_ORDER_V2 if name in under_test_set]
    if len(ordered) != len(under_test_set):
        missing = sorted(under_test_set.difference(ordered))
        pytest.fail(f"L2.2.v2 composition-order map missing process(es): {missing}")
    return ordered


def _project_trace_vector(ctx: _ProcessContext, group: str, observable: str, tick: int) -> np.ndarray:
    return project_karr_vector(
        ctx.process,
        observable,
        cell_vector(ctx.trace, group, observable, tick),
        index_projection_literal=ctx.spec.index_projection_literal,
    )


def _owned_observables(spec: _ProcessSpec) -> tuple[str, ...]:
    return tuple(obs for obs in spec.observables if obs not in spec.pass_through)


def _assert_bit_identity(
    *,
    tick: int,
    observable: str,
    oc_after: np.ndarray,
    karr_after: np.ndarray,
    process_name: str,
) -> None:
    if oc_after.shape != karr_after.shape:
        pytest.fail(
            "L2.5 bit-identity shape mismatch: "
            f"tick={tick}, process={process_name}, observable={observable}, "
            f"oc_shape={oc_after.shape}, karr_shape={karr_after.shape}"
        )

    karr_int_part = np.rint(karr_after)
    karr_snapped = False
    if not np.array_equal(karr_int_part, karr_after):
        karr_frac = np.abs(karr_after - karr_int_part)
        if np.all(karr_frac < 1e-9):
            karr_after = karr_int_part.astype(np.float64)
            karr_snapped = True
        else:
            bad = int(np.flatnonzero(karr_frac >= 1e-9)[0])
            pytest.fail(
                "L2.5 oracle non-integral: "
                f"tick={tick}, process={process_name}, observable={observable}, index={bad}, "
                f"karr_val={float(karr_after[bad])}"
            )

    oc_int_part = np.rint(oc_after)
    if not np.array_equal(oc_int_part, oc_after):
        oc_frac = np.abs(oc_after - oc_int_part)
        if karr_snapped and np.all(oc_frac < 1e-9):
            oc_after = oc_int_part.astype(np.float64)
        else:
            bad = int(np.flatnonzero(oc_frac >= 1e-9)[0])
            pytest.fail(
                "L2.5 oc non-integral: "
                f"tick={tick}, process={process_name}, observable={observable}, index={bad}, "
                f"oc_val={float(oc_after[bad])}"
            )

    mismatch = oc_after != karr_after
    if np.any(mismatch):
        idx = int(np.flatnonzero(mismatch)[0])
        diff = float(oc_after[idx] - karr_after[idx])
        pytest.fail(
            "L2.5 bit-identity mismatch: "
            f"tick={tick}, process={process_name}, observable={observable}, index={idx}, "
            f"oc_val={float(oc_after[idx])}, karr_val={float(karr_after[idx])}, diff={diff}"
        )


def _matches_oracle(
    *,
    tick: int,
    process_name: str,
    oracle_type: str,
    observable: str,
    oc_after: np.ndarray,
    karr_after: np.ndarray,
) -> bool:
    if oracle_type not in _SUPPORTED_ORACLE_TYPES:
        pytest.fail(
            "L2.2.v2 precondition failed (unknown oracle type): "
            f"process={process_name}, oracle_type={oracle_type}, "
            f"supported={sorted(_SUPPORTED_ORACLE_TYPES)}"
        )
    try:
        if oracle_type == ORACLE_BIT_IDENTITY:
            _assert_bit_identity(
                tick=tick,
                observable=observable,
                oc_after=oc_after,
                karr_after=karr_after,
                process_name=process_name,
            )
        else:
            _assert_identity_or_tolerance_shared(
                tick=tick,
                observable=observable,
                oc_after=oc_after,
                karr_after=karr_after,
                process_name=process_name,
            )
    except BaseException:
        return False
    return True


def _trace_hints_enabled(*, disable_trace_hints: bool, oracle_type: str) -> bool:
    del oracle_type
    return not disable_trace_hints


def _cell_tick_ref(ds: h5py.Dataset, tick: int) -> h5py.Reference:
    if len(ds.shape) != 2:
        raise ValueError(
            f"Unexpected MAT cell dataset rank: shape={ds.shape}, expected 2D"
        )
    rows, cols = int(ds.shape[0]), int(ds.shape[1])
    if rows == 1 and cols >= (tick + 1):
        return ds[0, tick]
    if cols == 1 and rows >= (tick + 1):
        return ds[tick, 0]
    if rows >= (tick + 1):
        return ds[tick, 0]
    if cols >= (tick + 1):
        return ds[0, tick]
    raise IndexError(f"Tick index {tick} out of range for dataset with shape={ds.shape}")


def _trace_cell_payload(
    *,
    ctx: _ProcessContext,
    group: str,
    name: str,
    tick: int,
) -> h5py.Dataset | h5py.Group | None:
    dataset_path = f"{group}/{name}"
    if dataset_path not in ctx.trace:
        return None
    ds = ctx.trace[dataset_path]
    if not isinstance(ds, h5py.Dataset):
        return None
    ref = _cell_tick_ref(ds, tick)
    if not ref:
        return None
    payload = ctx.trace[ref]
    if isinstance(payload, (h5py.Dataset, h5py.Group)):
        return payload
    return None


def _inject_hidden_chromosome_state(*, ctx: _ProcessContext, state: dict[str, Any], tick: int) -> None:
    chrom_state = state.get("chromosome")
    if not isinstance(chrom_state, dict):
        return
    payload = _trace_cell_payload(ctx=ctx, group="states_before", name="chromosome", tick=tick)
    if not isinstance(payload, h5py.Group):
        return
    injected = ChromosomeStore.from_hdf5_group(payload).to_state()
    chrom_state.update(injected)


def _inject_hidden_stimulus_values(*, ctx: _ProcessContext, state: dict[str, Any], tick: int) -> None:
    stimuli_state = state.get("stimuli")
    if not isinstance(stimuli_state, dict):
        return
    payload = _trace_cell_payload(ctx=ctx, group="states_before", name="stimulus", tick=tick)
    if not isinstance(payload, h5py.Dataset):
        return
    vec = np.asarray(payload[()], dtype=np.float64).reshape(-1)
    process_wids = getattr(ctx.process, "stimuli_wids", None)
    if process_wids is None:
        return
    wids = [str(wid) for wid in process_wids]
    if len(wids) != int(vec.shape[0]):
        return
    for wid, value in zip(wids, vec, strict=False):
        stimuli_state[wid] = float(value)


def _inject_hidden_rnap_supercoiling_fold_change(
    *,
    ctx: _ProcessContext,
    state: dict[str, Any],
    tick: int,
) -> None:
    payload = _trace_cell_payload(ctx=ctx, group="states_before", name="rnaPolymerase", tick=tick)
    if not isinstance(payload, h5py.Group):
        return
    key = "supercoilingBindingProbFoldChange"
    if key not in payload:
        return
    node = payload[key]
    if not isinstance(node, h5py.Dataset):
        return
    arr = np.asarray(node[()], dtype=np.float64).reshape(-1)
    if arr.size == 0:
        return
    rp_state = state.setdefault("rnaPolymerase", {})
    if not isinstance(rp_state, dict):
        return
    rp_state[key] = float(arr[0])


def _inject_hidden_read_surface(*, ctx: _ProcessContext, state: dict[str, Any], tick: int) -> None:
    for channel in ctx.spec.hidden_read_surface:
        if channel == "chromosome":
            _inject_hidden_chromosome_state(ctx=ctx, state=state, tick=tick)
            continue
        if channel == "stimulus.values":
            _inject_hidden_stimulus_values(ctx=ctx, state=state, tick=tick)
            continue
        if channel == "rnaPolymerase.supercoilingBindingProbFoldChange":
            _inject_hidden_rnap_supercoiling_fold_change(ctx=ctx, state=state, tick=tick)
            continue
        pytest.fail(f"L2.2.v2 harness bug: unsupported hidden_read_surface channel {channel!r}")


def _first_mismatch_detail(oc_after: np.ndarray, karr_after: np.ndarray) -> tuple[int, float, float, float]:
    if oc_after.shape != karr_after.shape:
        return (-1, float("nan"), float("nan"), float("nan"))
    mismatch = oc_after != karr_after
    if not np.any(mismatch):
        return (-1, 0.0, 0.0, 0.0)
    idx = int(np.flatnonzero(mismatch)[0])
    oc_val = float(oc_after[idx])
    karr_val = float(karr_after[idx])
    return (idx, oc_val, karr_val, float(oc_val - karr_val))


def _apply_update(state: dict[str, Any], update: dict[str, Any]) -> None:
    for label, deltas in collect_count_delta_dicts(update):
        assert_delta_integral(label, deltas)
    apply_count_update(state, update)


def _build_counterfactual_step_vector(
    *,
    ctx: _ProcessContext,
    tick: int,
    observable: str,
    disable_trace_hints: bool,
    oracle_type: str,
) -> np.ndarray:
    state = build_state_template(ctx.process)
    before_vectors: dict[str, np.ndarray] = {}
    for obs in ctx.spec.observables:
        before_vectors[obs] = _project_trace_vector(ctx, "states_before", obs, tick)
        overlay_observable_into_state(
            process=ctx.process,
            state=state,
            observable=obs,
            vector=before_vectors[obs],
            wids=ctx.wids_by_observable[obs],
            store_path_override=ctx.spec.store_path_override,
        )
    _inject_hidden_read_surface(ctx=ctx, state=state, tick=tick)
    # H5 fix (STATUS_cause_4_sweep.md): counterfactual replay must honor the same
    # hint policy as composition mode; otherwise no-hint composition is compared
    # against hint-assisted isolated replay.
    if _trace_hints_enabled(disable_trace_hints=disable_trace_hints, oracle_type=oracle_type):
        for obs in ctx.spec.trace_after_hint_observables:
            after_vec = _project_trace_vector(ctx, "states_after", obs, tick)
            overlay_trace_after_hint(
                state=state,
                observable=obs,
                vector=after_vec,
                wids=ctx.wids_by_observable[obs],
            )
    refresh_allocator_views(ctx.process, state)
    update = ctx.process.next_update(1.0, state)
    _apply_update(state, update)
    return project_observable_from_state(
        process=ctx.process,
        state=state,
        observable=observable,
        wids=ctx.wids_by_observable[observable],
        bound_enzymes_before=before_vectors.get("boundEnzymes"),
        store_path_override=ctx.spec.store_path_override,
    )


def _build_context(
    name: str,
    rng_seed: int,
    handle: h5py.File,
    process_config_override: dict[str, Any] | None = None,
) -> _ProcessContext:
    spec = _PROCESS_SPECS[name]
    n_ticks = int(np.asarray(handle["metadata/n_ticks"][()]).reshape(-1)[0])
    if "metadata" in handle and "rng_seed" in handle["metadata"]:
        recorded_seed = int(np.asarray(handle["metadata/rng_seed"][()]).reshape(-1)[0])
        assert int(rng_seed) == recorded_seed

    process_config = {"rng_seed": int(rng_seed)}
    if process_config_override:
        process_config.update(process_config_override)
    process = spec.process_cls(process_config)
    state_template = build_state_template(process)
    probe_ctx = _ProcessContext(
        name=name,
        spec=spec,
        process=process,
        trace=handle,
        n_ticks=n_ticks,
        wids_by_observable={},
    )

    wids_by_observable: dict[str, list[str]] = {}
    for observable in spec.observables:
        karr_before = _project_trace_vector(probe_ctx, "states_before", observable, 0)
        runtime_wids = infer_wids_for_observable(
            process,
            state_template,
            observable,
            karr_len=int(karr_before.shape[0]),
            explicit_attr=spec.observable_to_wids_attr.get(observable),
        )
        if len(runtime_wids) != int(karr_before.shape[0]):
            pytest.fail(
                "L2.2.v2 precondition failed (wid-length mismatch): "
                f"process={name}, observable={observable}, "
                f"len(runtime_wids)={len(runtime_wids)}, len(initial_oracle_vector)={int(karr_before.shape[0])}"
            )
        if len(set(runtime_wids)) != len(runtime_wids):
            pytest.fail(
                "L2.2.v2 precondition failed (duplicate WID in runtime list): "
                f"process={name}, observable={observable}"
            )
        wids_by_observable[observable] = runtime_wids

    return _ProcessContext(
        name=name,
        spec=spec,
        process=process,
        trace=handle,
        n_ticks=n_ticks,
        wids_by_observable=wids_by_observable,
    )


def _build_union_master_wids(
    *,
    ordered: list[str],
    contexts: dict[str, _ProcessContext],
) -> tuple[list[str], dict[str, list[str]]]:
    all_observables: list[str] = []
    for name in ordered:
        for obs in contexts[name].spec.observables:
            if obs not in all_observables:
                all_observables.append(obs)

    master_wids_by_observable: dict[str, list[str]] = {}
    for obs in all_observables:
        seen: set[str] = set()
        union: list[str] = []
        for name in ordered:
            wids = contexts[name].wids_by_observable.get(obs)
            if wids is None:
                continue
            for wid in wids:
                if wid not in seen:
                    seen.add(wid)
                    union.append(wid)
        master_wids_by_observable[obs] = union
    return all_observables, master_wids_by_observable


def _master_wids_hash(
    *,
    all_observables: list[str],
    master_wids_by_observable: dict[str, list[str]],
) -> str:
    payload = [(obs, tuple(master_wids_by_observable[obs])) for obs in all_observables]
    digest = hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode("utf-8")).hexdigest()
    return digest


def _assign_master_maps(
    *,
    ordered: list[str],
    contexts: dict[str, _ProcessContext],
    all_observables: list[str],
    master_wids_by_observable: dict[str, list[str]],
) -> None:
    for name in ordered:
        ctx = contexts[name]
        ctx.process_wid_to_master_idx = {}
        ctx.master_idx_to_process_wid = {}
        ctx.process_idx_to_master_idx = {}
        for obs in all_observables:
            if obs not in ctx.wids_by_observable:
                continue
            master_wids = master_wids_by_observable[obs]
            master_wid_to_idx = {wid: idx for idx, wid in enumerate(master_wids)}
            proc_wids = ctx.wids_by_observable[obs]
            proc_wid_to_master: dict[str, int] = {}
            proc_idx_to_master: dict[int, int] = {}
            master_to_proc: dict[int, str] = {}
            for proc_idx, wid in enumerate(proc_wids):
                if wid not in master_wid_to_idx:
                    pytest.fail(
                        "L2.2.v2 precondition failed (runtime WID missing from master union): "
                        f"process={name}, observable={obs}, wid={wid}"
                    )
                master_idx = int(master_wid_to_idx[wid])
                proc_wid_to_master[wid] = master_idx
                proc_idx_to_master[proc_idx] = master_idx
                master_to_proc[master_idx] = wid
            ctx.process_wid_to_master_idx[obs] = proc_wid_to_master
            ctx.process_idx_to_master_idx[obs] = proc_idx_to_master
            ctx.master_idx_to_process_wid[obs] = master_to_proc


def _build_shared_state_template(
    *,
    ordered: list[str],
    contexts: dict[str, _ProcessContext],
) -> dict[str, Any]:
    state = build_state_template(contexts[ordered[0]].process)
    for name in ordered[1:]:
        template = build_state_template(contexts[name].process)
        for port, port_state in template.items():
            if port not in state:
                state[port] = port_state
                continue
            existing = state[port]
            if isinstance(existing, dict) and isinstance(port_state, dict):
                for key, value in port_state.items():
                    existing.setdefault(key, value)
    return state


def _build_owner_manifest(
    *,
    ordered: list[str],
    contexts: dict[str, _ProcessContext],
    all_observables: list[str],
) -> dict[str, str]:
    manifest: dict[str, str] = {}
    for obs in all_observables:
        mutating_candidates = [name for name in ordered if obs in _owned_observables(contexts[name].spec)]
        exposing_candidates = [name for name in ordered if obs in contexts[name].spec.observables]
        if mutating_candidates:
            manifest[obs] = mutating_candidates[0]
        elif exposing_candidates:
            manifest[obs] = exposing_candidates[0]

    for observable, owner in OWNER_MANIFEST_OVERRIDES.items():
        manifest[observable] = owner
    return manifest


def _validate_owner_manifest(
    *,
    ordered: list[str],
    contexts: dict[str, _ProcessContext],
    all_observables: list[str],
    owner_manifest: dict[str, str],
) -> None:
    missing = [obs for obs in all_observables if obs not in owner_manifest]
    if missing:
        pytest.fail(f"L2.2.v2 precondition failed (owner manifest missing observables): {missing}")

    unknown_keys = sorted(set(owner_manifest).difference(all_observables))
    if unknown_keys:
        pytest.fail(
            "L2.2.v2 precondition failed (owner manifest has unknown observables): "
            f"{unknown_keys}"
        )

    ordered_set = set(ordered)
    for obs in all_observables:
        owner = owner_manifest[obs]
        if owner not in ordered_set:
            pytest.fail(
                "L2.2.v2 precondition failed (owner not in under-test set): "
                f"observable={obs}, owner={owner}, under_test={ordered}"
            )
        if obs not in contexts[owner].spec.observables:
            pytest.fail(
                "L2.2.v2 precondition failed (owner does not expose observable): "
                f"observable={obs}, owner={owner}"
            )
        if obs not in contexts[owner].wids_by_observable:
            pytest.fail(
                "L2.2.v2 precondition failed (owner runtime WIDs missing): "
                f"observable={obs}, owner={owner}"
            )
        mutating_candidates = [name for name in ordered if obs in _owned_observables(contexts[name].spec)]
        if mutating_candidates and owner not in mutating_candidates:
            pytest.fail(
                "L2.2.v2 precondition failed (non-mutating owner selected for hard assertion surface): "
                f"observable={obs}, owner={owner}, mutating_candidates={mutating_candidates}"
            )


def _projection_via_master(
    *,
    process_name: str,
    observable: str,
    state: dict[str, Any],
    contexts: dict[str, _ProcessContext],
    owner_manifest: dict[str, str],
    master_wids_by_observable: dict[str, list[str]],
) -> tuple[np.ndarray, np.ndarray]:
    owner_name = owner_manifest[observable]
    owner_ctx = contexts[owner_name]
    master_wids = master_wids_by_observable[observable]
    master_vector = project_observable_from_state(
        process=owner_ctx.process,
        state=state,
        observable=observable,
        wids=master_wids,
        bound_enzymes_before=None,
        store_path_override=owner_ctx.spec.store_path_override,
    )

    process_ctx = contexts[process_name]
    proc_wids = process_ctx.wids_by_observable[observable]
    idx_map = process_ctx.process_idx_to_master_idx[observable]
    out = np.zeros(len(proc_wids), dtype=np.float64)
    for proc_idx in range(len(proc_wids)):
        master_idx = idx_map[proc_idx]
        out[proc_idx] = float(master_vector[master_idx])
    return out, master_vector


def _base_failure_record(
    *,
    cause_code: str,
    tick: int,
    process_name: str,
    observable: str,
    idx: int,
    oc_val: float,
    karr_val: float,
    diff: float,
    ordered: list[str],
    master_hash: str,
    master_wids_by_observable: dict[str, list[str]],
    contexts: dict[str, _ProcessContext],
    owner_manifest: dict[str, str],
    oracle_type_by_process: dict[str, str],
) -> dict[str, Any]:
    wid_lists = {
        name: list(contexts[name].wids_by_observable.get(observable, []))
        for name in ordered
        if observable in contexts[name].wids_by_observable
    }
    process_wids = contexts[process_name].wids_by_observable.get(observable, [])
    process_wid: str | None = None
    if 0 <= idx < len(process_wids):
        process_wid = process_wids[idx]

    process_idx_to_master = contexts[process_name].process_idx_to_master_idx.get(observable, {})
    master_idx = process_idx_to_master.get(idx) if idx >= 0 else None
    owner_name = owner_manifest.get(observable)
    owner_wid: str | None = None
    if owner_name is not None and master_idx is not None:
        owner_wid = contexts[owner_name].master_idx_to_process_wid.get(observable, {}).get(master_idx)

    return {
        "cause_code": cause_code,
        "tick": tick,
        "process": process_name,
        "oracle_type": oracle_type_by_process[process_name],
        "observable": observable,
        "index": idx,
        "process_wid": process_wid,
        "master_index": master_idx,
        "owner_wid": owner_wid,
        "oc_val": oc_val,
        "karr_val": karr_val,
        "diff": diff,
        "composition_order": list(ordered),
        "owner_manifest_observable_owner": owner_manifest.get(observable),
        "master_wids_hash": master_hash,
        "master_wids": list(master_wids_by_observable.get(observable, [])),
        "wid_lists_by_process": wid_lists,
        "process_wid_to_master_idx": {
            name: contexts[name].process_wid_to_master_idx.get(observable, {})
            for name in ordered
            if observable in contexts[name].process_wid_to_master_idx
        },
    }


def _diagnose_cause_1_wid_set_mismatch(
    *,
    tick: int,
    process_name: str,
    observable: str,
    mismatch_index: int,
    contexts: dict[str, _ProcessContext],
    ordered: list[str],
) -> dict[str, Any] | None:
    if mismatch_index < 0:
        return None
    process_wids = contexts[process_name].wids_by_observable.get(observable, [])
    if mismatch_index >= len(process_wids):
        return None
    process_wid = process_wids[mismatch_index]
    process_master_idx = contexts[process_name].process_idx_to_master_idx.get(observable, {}).get(
        mismatch_index
    )
    if process_master_idx is None:
        return None
    for other_name in ordered:
        if other_name == process_name:
            continue
        other_master_to_wid = contexts[other_name].master_idx_to_process_wid.get(observable)
        if other_master_to_wid is None or process_master_idx not in other_master_to_wid:
            continue
        compared_wid = other_master_to_wid[process_master_idx]
        if compared_wid != process_wid:
            return {
                "cause_code": CAUSE_1_WID_SET_MISMATCH,
                "tick": tick,
                "process_wid": process_wid,
                "compared_process": other_name,
                "compared_wid": compared_wid,
                "comparison_index": mismatch_index,
                "comparison_master_index": process_master_idx,
            }
    return None


def _diagnose_cause_2_oracle_injection_misalignment() -> None:
    raise NotImplementedError("diagnostic not yet implemented for v2.0")


def _diagnose_cause_3_composition_order_error() -> None:
    raise NotImplementedError("diagnostic not yet implemented for v2.0")


def _structured_fail(record: dict[str, Any]) -> None:
    cause = record.get("cause_code")
    if cause not in _CAUSE_CODES:
        pytest.fail(
            "L2.2.v2 harness bug: structured record emitted unknown cause_code "
            f"{cause!r} (allowed={sorted(_CAUSE_CODES)})"
        )
    pytest.fail("L2.2.v2 structured failure: " + json.dumps(record, sort_keys=True))


def _resolve_trace_path_for_seed(process_name: str, rng_seed: int, *, prefer_seeded: bool) -> Path:
    base = resolve_trace_path(process_name)
    if not prefer_seeded:
        return base
    seed_dir = f"{base.parent.name}_s{int(rng_seed):03d}"
    seeded = base.parent.parent / seed_dir / base.name
    if seeded.exists():
        return seeded
    return base


def run_integrated_replay_v2(
    *,
    under_test_processes: list[str],
    rng_seed: int,
    disable_trace_hints: bool = False,
    oracle_type_by_process: dict[str, str] | None = None,
    process_config_overrides: dict[str, dict[str, Any]] | None = None,
) -> None:
    ordered = _ordered_under_test(under_test_processes)

    with ExitStack() as stack:
        if process_config_overrides is None:
            process_config_overrides = {}
        unknown_process_config_overrides = sorted(set(process_config_overrides).difference(ordered))
        if unknown_process_config_overrides:
            pytest.fail(
                "L2.2.v2 precondition failed (process config override for unknown process): "
                f"{unknown_process_config_overrides}, under_test={ordered}"
            )
        contexts: dict[str, _ProcessContext] = {}
        for name in ordered:
            prefer_seeded = bool(_PROCESS_SPECS[name].hidden_read_surface)
            trace_handle = stack.enter_context(
                h5py.File(
                    _resolve_trace_path_for_seed(
                        name,
                        rng_seed,
                        prefer_seeded=prefer_seeded,
                    ),
                    "r",
                )
            )
            contexts[name] = _build_context(
                name,
                rng_seed,
                trace_handle,
                process_config_override=process_config_overrides.get(name),
            )

        n_ticks_values = {contexts[name].n_ticks for name in ordered}
        if len(n_ticks_values) != 1:
            pytest.fail(f"L2.2.v2 n_ticks mismatch across traces: {sorted(n_ticks_values)}")
        n_ticks = next(iter(n_ticks_values))

        all_observables, master_wids_by_observable = _build_union_master_wids(
            ordered=ordered,
            contexts=contexts,
        )
        all_observables_second, master_wids_by_observable_second = _build_union_master_wids(
            ordered=ordered,
            contexts=contexts,
        )
        master_hash = _master_wids_hash(
            all_observables=all_observables,
            master_wids_by_observable=master_wids_by_observable,
        )
        master_hash_second = _master_wids_hash(
            all_observables=all_observables_second,
            master_wids_by_observable=master_wids_by_observable_second,
        )
        if master_hash != master_hash_second:
            pytest.fail(
                "L2.2.v2 precondition failed (non-deterministic union master list): "
                f"hash_1={master_hash}, hash_2={master_hash_second}"
            )
        if all_observables != all_observables_second:
            pytest.fail(
                "L2.2.v2 precondition failed (observable order non-deterministic): "
                f"first={all_observables}, second={all_observables_second}"
            )

        _assign_master_maps(
            ordered=ordered,
            contexts=contexts,
            all_observables=all_observables,
            master_wids_by_observable=master_wids_by_observable,
        )

        owner_manifest = _build_owner_manifest(
            ordered=ordered,
            contexts=contexts,
            all_observables=all_observables,
        )
        _validate_owner_manifest(
            ordered=ordered,
            contexts=contexts,
            all_observables=all_observables,
            owner_manifest=owner_manifest,
        )

        OWNER_MANIFEST.clear()
        OWNER_MANIFEST.update(owner_manifest)
        order_idx = {name: idx for idx, name in enumerate(ordered)}
        if oracle_type_by_process is None:
            oracle_type_by_process = {}
        unknown_oracle_overrides = sorted(set(oracle_type_by_process).difference(ordered))
        if unknown_oracle_overrides:
            pytest.fail(
                "L2.2.v2 precondition failed (oracle override for unknown process): "
                f"{unknown_oracle_overrides}, under_test={ordered}"
            )
        resolved_oracle_type_by_process = {
            name: str(oracle_type_by_process.get(name, contexts[name].spec.oracle_type))
            for name in ordered
        }
        for name, oracle_type in resolved_oracle_type_by_process.items():
            if oracle_type not in _SUPPORTED_ORACLE_TYPES:
                pytest.fail(
                    "L2.2.v2 precondition failed (unsupported oracle type): "
                    f"process={name}, oracle_type={oracle_type}, "
                    f"supported={sorted(_SUPPORTED_ORACLE_TYPES)}"
                )
        if disable_trace_hints:
            requires_hints = [
                name
                for name in ordered
                if contexts[name].spec.requires_hints_for_honest_mode
            ]
            if requires_hints:
                pytest.fail(
                    "L2.2.v2 precondition failed (honest mode requires trace hints): "
                    f"processes={requires_hints}"
                )
        mutators_by_observable = {
            obs: [name for name in ordered if obs in _owned_observables(contexts[name].spec)]
            for obs in all_observables
        }

        no_op_messages: list[str] = []
        for name in ordered:
            ctx = contexts[name]
            mutated = _owned_observables(ctx.spec)
            mutated_tick_counts = audit_trace_mutated_ticks(ctx.trace, mutated, n_ticks)
            if (
                resolved_oracle_type_by_process[name] != ORACLE_BIT_IDENTITY
                and sum(mutated_tick_counts.values()) == 0
            ):
                no_op_messages.append(
                    f"{name}: all owned observables are no-op across {n_ticks} ticks: {mutated_tick_counts}"
                )
        if no_op_messages:
            pytest.skip(
                "L2.2.v2 N/A: no-op trace for at least one under-test process. "
                + " | ".join(no_op_messages)
            )

        for tick in range(n_ticks):
            shared_state = _build_shared_state_template(
                ordered=ordered,
                contexts=contexts,
            )
            before_vectors: dict[str, dict[str, np.ndarray]] = {}
            after_vectors: dict[str, dict[str, np.ndarray]] = {}
            step_vectors: dict[tuple[str, str], np.ndarray] = {}
            step_compare_vectors: dict[tuple[str, str], np.ndarray] = {}
            upstream_mutated_master_indices_by_observable: dict[str, set[int]] = {
                obs: set() for obs in all_observables
            }
            upstream_mutated_master_before_by_observable: dict[str, dict[int, float]] = {
                obs: {} for obs in all_observables
            }

            for name in ordered:
                ctx = contexts[name]
                before_vectors[name] = {
                    obs: _project_trace_vector(ctx, "states_before", obs, tick)
                    for obs in ctx.spec.observables
                }
                after_vectors[name] = {
                    obs: _project_trace_vector(ctx, "states_after", obs, tick)
                    for obs in ctx.spec.observables
                }

            # Composition-boundary allocation (process closure before pair
            # execution): collect every composed process's own Karr-oracle
            # substrate need for this tick and run the REAL allocator
            # arithmetic once, simultaneously, before any process in the
            # composition executes. Replaces the idealized per-process
            # `refresh_allocator_views` grant (see docs/phase_f/
            # INTEGRITY_AUDIT_PRE_L25.md Finding #20) with genuine
            # contention via KarrAllocationStep. Uses the tick-start pool
            # (before_vectors are per-process oracle observations, computed
            # above for every process before any of them has executed this
            # tick), consistent with evolveState.m's precompute-then-execute
            # semantics (docs/phase_f/L2_5_HARNESS_DESIGN.md Baseline fact 5).
            composition_requests = {
                contexts[name].process.name: dict(
                    zip(
                        contexts[name].wids_by_observable["substrates"],
                        before_vectors[name]["substrates"].tolist(),
                        strict=False,
                    )
                )
                for name in ordered
                if "substrates" in contexts[name].spec.observables
            }

            # `shared_state` is a fresh per-tick template (`_build_shared_state_template`
            # seeds every port from each process's own port-schema default, e.g. 0.0
            # for "substrates" -- see docs/phase_f/L2_5_HARNESS_DESIGN.md). Only
            # `ordered[0]`'s "substrates" slice gets overlaid before the per-process
            # loop runs; every other composed process's own substrate WIDs are still
            # at that 0.0 default at this point. Reading the pool here without first
            # overlaying every process's own tick-start substrate view would starve
            # not-yet-overlaid WIDs to an artificial zero pool, corrupting the
            # allocator's `counts_available` for WIDs owned by later processes even
            # when they are NOT contended with any other composed process. Overlay
            # every process's own "substrates" observable first so the pool the
            # allocator sees is the true, complete tick-start pool.
            for name in ordered:
                ctx = contexts[name]
                if "substrates" in ctx.spec.observables:
                    overlay_observable_into_state(
                        process=ctx.process,
                        state=shared_state,
                        observable="substrates",
                        vector=before_vectors[name]["substrates"],
                        wids=ctx.wids_by_observable["substrates"],
                        store_path_override=ctx.spec.store_path_override,
                    )
            refresh_allocator_views_composition(
                request_vectors=composition_requests,
                state=shared_state,
            )

            for name in ordered:
                ctx = contexts[name]
                owned_observables = _owned_observables(ctx.spec)
                if _trace_hints_enabled(
                    disable_trace_hints=disable_trace_hints,
                    oracle_type=resolved_oracle_type_by_process[name],
                ):
                    for obs in ctx.spec.trace_after_hint_observables:
                        overlay_trace_after_hint(
                            state=shared_state,
                            observable=obs,
                            vector=after_vectors[name][obs],
                            wids=ctx.wids_by_observable[obs],
                        )

                for obs in ctx.spec.observables:
                    overlay_vec = before_vectors[name][obs]
                    upstream_exposers = [
                        p
                        for p in ordered
                        if order_idx[p] < order_idx[name] and obs in contexts[p].spec.observables
                    ]
                    mutated_master_indices = upstream_mutated_master_indices_by_observable[obs]
                    mutated_master_before = upstream_mutated_master_before_by_observable[obs]
                    # H6 fix (STATUS_cause_4_sweep.md): do not wipe shared WIDs that
                    # were already mutated by upstream steps in this tick.
                    if obs in owned_observables and upstream_exposers and mutated_master_indices:
                        running_vec = project_observable_from_state(
                            process=ctx.process,
                            state=shared_state,
                            observable=obs,
                            wids=ctx.wids_by_observable[obs],
                            bound_enzymes_before=before_vectors[name].get("boundEnzymes"),
                            store_path_override=ctx.spec.store_path_override,
                        )
                        overlay_vec = before_vectors[name][obs].copy()
                        for proc_idx, proc_wid in enumerate(ctx.wids_by_observable[obs]):
                            master_idx = ctx.process_wid_to_master_idx[obs][proc_wid]
                            if master_idx in mutated_master_indices:
                                baseline_before_upstream = mutated_master_before.get(master_idx)
                                if (
                                    baseline_before_upstream is not None
                                    and overlay_vec[proc_idx] == baseline_before_upstream
                                ):
                                    # Keep upstream-mutated shared WIDs from the
                                    # live shared state when both processes share
                                    # the same pre-mutation baseline on that WID.
                                    overlay_vec[proc_idx] = running_vec[proc_idx]
                    overlay_observable_into_state(
                        process=ctx.process,
                        state=shared_state,
                        observable=obs,
                        vector=overlay_vec,
                        wids=ctx.wids_by_observable[obs],
                        store_path_override=ctx.spec.store_path_override,
                    )

                owned_master_before_step: dict[str, np.ndarray] = {}
                for obs in owned_observables:
                    _, master_before = _projection_via_master(
                        process_name=name,
                        observable=obs,
                        state=shared_state,
                        contexts=contexts,
                        owner_manifest=owner_manifest,
                        master_wids_by_observable=master_wids_by_observable,
                    )
                    owned_master_before_step[obs] = master_before

                oc_before_step: dict[str, np.ndarray] = {}
                for obs in owned_observables:
                    oc_before_step[obs] = project_observable_from_state(
                        process=ctx.process,
                        state=shared_state,
                        observable=obs,
                        wids=ctx.wids_by_observable[obs],
                        bound_enzymes_before=before_vectors[name].get("boundEnzymes"),
                        store_path_override=ctx.spec.store_path_override,
                    )

                # Day-35 fix: inject hidden read-surface channels (chromosome,
                # stimulus.values, rnaPolymerase.supercoilingBindingProbFoldChange)
                # into the shared state before this process runs. Without this,
                # processes that read these surfaces (e.g., DNARepair reads
                # chromosome) see the template defaults and produce wrong
                # biology in composition mode while counterfactual replay
                # (which DOES inject the surface) matches oracle. Matches the
                # counterfactual contract in _build_counterfactual_step_vector.
                _inject_hidden_read_surface(ctx=ctx, state=shared_state, tick=tick)

                update = ctx.process.next_update(1.0, shared_state)
                _apply_update(shared_state, update)
                for obs, master_before in owned_master_before_step.items():
                    _, master_after_for_obs = _projection_via_master(
                        process_name=name,
                        observable=obs,
                        state=shared_state,
                        contexts=contexts,
                        owner_manifest=owner_manifest,
                        master_wids_by_observable=master_wids_by_observable,
                    )
                    changed_master_indices = np.flatnonzero(master_after_for_obs != master_before)
                    if changed_master_indices.size:
                        for idx in changed_master_indices.tolist():
                            idx_int = int(idx)
                            upstream_mutated_master_indices_by_observable[obs].add(idx_int)
                            upstream_mutated_master_before_by_observable[obs][idx_int] = float(
                                master_before[idx_int]
                            )
                upstream = [p for p in ordered if order_idx[p] < order_idx[name]]

                for obs in owned_observables:
                    oc_after_step = project_observable_from_state(
                        process=ctx.process,
                        state=shared_state,
                        observable=obs,
                        wids=ctx.wids_by_observable[obs],
                        bound_enzymes_before=before_vectors[name].get("boundEnzymes"),
                        store_path_override=ctx.spec.store_path_override,
                    )
                    oc_via_master, master_after = _projection_via_master(
                        process_name=name,
                        observable=obs,
                        state=shared_state,
                        contexts=contexts,
                        owner_manifest=owner_manifest,
                        master_wids_by_observable=master_wids_by_observable,
                    )
                    step_vectors[(name, obs)] = oc_after_step
                    obs_mutators = mutators_by_observable.get(obs, [])
                    skip_projection_parity_check = (
                        len(obs_mutators) > 1 and owner_manifest.get(obs) != name
                    )

                    if (
                        not skip_projection_parity_check
                        and (
                            oc_after_step.shape != oc_via_master.shape
                            or np.any(oc_after_step != oc_via_master)
                        )
                    ):
                        idx_h, oc_h, via_h, diff_h = _first_mismatch_detail(oc_after_step, oc_via_master)
                        record = _base_failure_record(
                            cause_code=CAUSE_6_HARNESS_BUG,
                            tick=tick,
                            process_name=name,
                            observable=obs,
                            idx=idx_h,
                            oc_val=oc_h,
                            karr_val=via_h,
                            diff=diff_h,
                            ordered=ordered,
                            master_hash=master_hash,
                            master_wids_by_observable=master_wids_by_observable,
                            contexts=contexts,
                            owner_manifest=owner_manifest,
                            oracle_type_by_process=resolved_oracle_type_by_process,
                        )
                        record["harness_projection_disagreement"] = {
                            "projection_direct": oc_after_step.tolist(),
                            "projection_via_master": oc_via_master.tolist(),
                            "master_vector": master_after.tolist(),
                        }
                        _structured_fail(record)

                    karr_after = after_vectors[name][obs]
                    upstream_mutators = [p for p in obs_mutators if order_idx[p] < order_idx[name]]
                    compare_mode = "delta" if upstream_mutators else "absolute"
                    if compare_mode == "delta":
                        oc_compare = oc_after_step - oc_before_step[obs]
                        karr_compare = karr_after - before_vectors[name][obs]
                    else:
                        oc_compare = oc_after_step
                        karr_compare = karr_after
                    step_compare_vectors[(name, obs)] = oc_compare

                    if _matches_oracle(
                        tick=tick,
                        process_name=name,
                        oracle_type=resolved_oracle_type_by_process[name],
                        observable=obs,
                        oc_after=oc_compare,
                        karr_after=karr_compare,
                    ):
                        continue

                    idx, oc_val, karr_val, diff = _first_mismatch_detail(oc_compare, karr_compare)
                    base_record = _base_failure_record(
                        cause_code=CAUSE_UNCLASSIFIED,
                        tick=tick,
                        process_name=name,
                        observable=obs,
                        idx=idx,
                        oc_val=oc_val,
                        karr_val=karr_val,
                        diff=diff,
                        ordered=ordered,
                        master_hash=master_hash,
                        master_wids_by_observable=master_wids_by_observable,
                        contexts=contexts,
                        owner_manifest=owner_manifest,
                        oracle_type_by_process=resolved_oracle_type_by_process,
                    )
                    base_record["upstream_processes"] = upstream
                    base_record["compare_mode"] = compare_mode
                    base_record["shared_observable_mutators"] = obs_mutators
                    base_record["raw_vectors"] = {
                        "oc_after_step": oc_after_step.tolist(),
                        "karr_after": karr_after.tolist(),
                        "oc_compare": oc_compare.tolist(),
                        "karr_compare": karr_compare.tolist(),
                    }

                    cause_1 = _diagnose_cause_1_wid_set_mismatch(
                        tick=tick,
                        process_name=name,
                        observable=obs,
                        mismatch_index=idx,
                        contexts=contexts,
                        ordered=ordered,
                    )
                    if cause_1 is not None:
                        base_record.update(cause_1)
                        _structured_fail(base_record)

                    isolated_result: str
                    oc_counterfactual: np.ndarray | None = None
                    try:
                        oc_counterfactual = _build_counterfactual_step_vector(
                            ctx=ctx,
                            tick=tick,
                            observable=obs,
                            disable_trace_hints=disable_trace_hints,
                            oracle_type=resolved_oracle_type_by_process[name],
                        )
                        oc_counterfactual_compare = (
                            oc_counterfactual - before_vectors[name][obs]
                            if compare_mode == "delta"
                            else oc_counterfactual
                        )
                        isolated_matches = _matches_oracle(
                            tick=tick,
                            process_name=name,
                            oracle_type=resolved_oracle_type_by_process[name],
                            observable=obs,
                            oc_after=oc_counterfactual_compare,
                            karr_after=karr_compare,
                        )
                        isolated_result = "matches_oracle" if isolated_matches else "diverges_from_oracle"
                        base_record["isolated_replay_result"] = isolated_result
                        base_record["raw_vectors"]["oc_counterfactual"] = oc_counterfactual.tolist()
                        base_record["raw_vectors"]["oc_counterfactual_compare"] = (
                            oc_counterfactual_compare.tolist()
                        )
                    except BaseException as exc:  # noqa: BLE001
                        isolated_matches = False
                        isolated_result = f"diagnostic_error:{exc.__class__.__name__}:{exc}"
                        base_record["isolated_replay_result"] = isolated_result

                    if isolated_result.startswith("diagnostic_error:"):
                        base_record["cause_code"] = CAUSE_UNCLASSIFIED
                        _structured_fail(base_record)

                    if isolated_matches and upstream_mutators:
                        base_record["cause_code"] = CAUSE_4_UPSTREAM_STATE_POLLUTION
                    elif isolated_matches:
                        base_record["cause_code"] = CAUSE_UNCLASSIFIED
                        base_record["reclassification"] = {
                            "reclassified_from": CAUSE_4_UPSTREAM_STATE_POLLUTION,
                            "reason": "upstream_mutators_empty",
                        }
                    else:
                        base_record["cause_code"] = CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE
                    _structured_fail(base_record)

            for name in ordered:
                ctx = contexts[name]
                for obs in _owned_observables(ctx.spec):
                    if len(mutators_by_observable.get(obs, [])) > 1:
                        # Shared owned-observables are asserted on per-step process deltas.
                        # Final-state absolute values include upstream/downstream baselines
                        # and are not attributable to a single process oracle surface.
                        continue
                    oc_after_final = project_observable_from_state(
                        process=ctx.process,
                        state=shared_state,
                        observable=obs,
                        wids=ctx.wids_by_observable[obs],
                        bound_enzymes_before=before_vectors[name].get("boundEnzymes"),
                        store_path_override=ctx.spec.store_path_override,
                    )
                    karr_after = after_vectors[name][obs]
                    if _matches_oracle(
                        tick=tick,
                        process_name=name,
                        oracle_type=resolved_oracle_type_by_process[name],
                        observable=obs,
                        oc_after=oc_after_final,
                        karr_after=karr_after,
                    ):
                        continue
                    idx, oc_val, karr_val, diff = _first_mismatch_detail(oc_after_final, karr_after)
                    step_aligned = _matches_oracle(
                        tick=tick,
                        process_name=name,
                        oracle_type=resolved_oracle_type_by_process[name],
                        observable=obs,
                        oc_after=step_compare_vectors[(name, obs)],
                        karr_after=karr_after,
                    )
                    record = _base_failure_record(
                        cause_code=CAUSE_4_UPSTREAM_STATE_POLLUTION
                        if step_aligned
                        else CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE,
                        tick=tick,
                        process_name=name,
                        observable=obs,
                        idx=idx,
                        oc_val=oc_val,
                        karr_val=karr_val,
                        diff=diff,
                        ordered=ordered,
                        master_hash=master_hash,
                        master_wids_by_observable=master_wids_by_observable,
                        contexts=contexts,
                        owner_manifest=owner_manifest,
                        oracle_type_by_process=resolved_oracle_type_by_process,
                    )
                    record["raw_vectors"] = {
                        "oc_after_final": oc_after_final.tolist(),
                        "karr_after": karr_after.tolist(),
                        "oc_after_step": step_vectors[(name, obs)].tolist(),
                    }
                    _structured_fail(record)


__all__ = [
    "_COMPOSITION_ORDER_V2",
    "CAUSE_1_WID_SET_MISMATCH",
    "CAUSE_2_ORACLE_INJECTION_MISALIGNMENT",
    "CAUSE_3_COMPOSITION_ORDER_ERROR",
    "CAUSE_4_UPSTREAM_STATE_POLLUTION",
    "CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE",
    "CAUSE_6_HARNESS_BUG",
    "CAUSE_7_ORACLE_TRACE_DEFECT",
    "CAUSE_UNCLASSIFIED",
    "OWNER_MANIFEST",
    "OWNER_MANIFEST_OVERRIDES",
    "run_integrated_replay_v2",
]
