"""Vivarium composer: M1 (Karr metabolism) + M2 (transcription) + M3 (translation).

This is the **chassis-composition proof**: M1, M2 and M3 tick together
inside a single Engine, share the ``substrates`` store, and run for
many seconds without crashing.

Topology (shared stores):
  * ``metabolic_reaction``  -- written by M1 only (645 fluxs + growth scalars)
  * ``substrates``          -- M1 declares all 585 substrate WCM IDs
                               seeded from Karr's cytosol snapshot;
                               M2 writes negative ATP/CTP/GTP/UTP deltas;
                               M3 writes per-AA negative deltas keyed by
                               the 20 standard amino-acid WCM IDs (these
                               IDs already live inside Karr's 585-substrate
                               vocabulary, so no extra placeholder key is
                               required).
                               All three processes share the same store.
  * ``rna``                 -- written by M2 only (525 RNA counts)
  * ``protein``             -- written by M3 only (482 protein counts)

Substrate writeback is still chassis-grade only:  M2/M3's per-tick
deltas are decremented from the shared counts; M1 does not yet
read them back into its FBA bounds (that requires Karr's
calcFluxBounds() port + the 585->1686 metabolite-x-compartment count
mapping, both deferred to the integrator pass).
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from opencell.m1 import calc_flux_bounds as cfb
from opencell.m1 import karr_metabolism as km
from opencell.m2 import transcription as tx
from opencell.m2 import transcription_v2 as tx_v2
from opencell.m3 import translation as tl
from opencell.m3 import translation_v2 as tl_v2
from opencell.vivarium.karr_allocation_step import KarrAllocationStep
from opencell.vivarium.karr_cell_cycle_coordinator import CellCycleCoordinator
from opencell.vivarium.karr_chromosome_condensation import (
    KarrChromosomeCondensationProcess,
)
from opencell.vivarium.karr_chromosome_segregation import KarrChromosomeSegregationProcess
from opencell.vivarium.karr_cytokinesis import KarrCytokinesisProcess
from opencell.vivarium.karr_macromolecular_complexation import MacromolecularComplexationProcess
from opencell.vivarium.karr_macromolecular_complexation_stub import MacromolecularComplexationStubProcess
from opencell.vivarium.karr_dna_damage import KarrDNADamageProcess
from opencell.vivarium.karr_dna_repair import KarrDNARepairProcess
from opencell.vivarium.karr_dna_supercoiling import KarrDNASupercoilingProcess
from opencell.vivarium.karr_ftsz_polymerization import KarrFtsZPolymerizationProcess
from opencell.vivarium.karr_metabolism import KarrMetabolismProcess
from opencell.vivarium.karr_transcription import KarrTranscriptionProcess
from opencell.vivarium.karr_transcription_v2 import KarrTranscriptionV2Process
from opencell.vivarium.karr_transcription_v3 import KarrTranscriptionV3Process
from opencell.vivarium.karr_translation import KarrTranslationProcess
from opencell.vivarium.karr_translation_v2 import KarrTranslationV2Process
from opencell.vivarium.karr_translation_v3 import KarrTranslationV3Process
from opencell.vivarium.karr_protein_activation import KarrProteinActivationProcess
from opencell.vivarium.karr_protein_decay_light import ProteinDecayLightProcess
from opencell.vivarium.karr_protein_folding import KarrProteinFoldingProcess
from opencell.vivarium.karr_protein_modification import KarrProteinModificationProcess
from opencell.vivarium.karr_protein_processing_i import KarrProteinProcessingIProcess
from opencell.vivarium.karr_protein_processing_ii import KarrProteinProcessingIIProcess
from opencell.vivarium.karr_protein_translocation import KarrProteinTranslocationProcess
from opencell.vivarium.karr_request_calculators import (
    RequestCalculatorD2,
    RequestCalculatorMetabolism,
    RequestCalculatorPD,
    RequestCalculatorPTransloc,
    RequestCalculatorProteinPathway,
    RequestCalculatorRibAsm,
    RequestCalculatorRNAPathway,
    RequestCalculatorTranscription,
    RequestCalculatorTRNA,
    RequestCalculatorTranslation,
)
from opencell.vivarium.karr_ribosome_assembly import KarrRibosomeAssemblyProcess
from opencell.vivarium.karr_replication import KarrReplicationProcess
from opencell.vivarium.karr_replication_initiation import KarrReplicationInitiationProcess
from opencell.vivarium.karr_rna_decay import RnaDecayLightProcess
from opencell.vivarium.karr_rna_modification import KarrRNAModificationProcess
from opencell.vivarium.karr_rna_processing import KarrRNAProcessingProcess
from opencell.vivarium.karr_host_interaction import KarrHostInteractionProcess
from opencell.vivarium.karr_observability_step import KarrObservabilityStep
from opencell.vivarium.karr_terminal_organelle_assembly import (
    KarrTerminalOrganelleAssemblyProcess,
)
from opencell.vivarium.karr_transcriptional_regulation import (
    KarrTranscriptionalRegulationProcess,
)
from opencell.vivarium.karr_trna_aminoacylation import KarrTRNAAminoacylationProcess

if TYPE_CHECKING:
    from vivarium.core.engine import Engine


_M1_SUBSTRATE_DEFAULT = 1.0
_KARR_CYTOSOL_COMPARTMENT_0 = 0


def _load_karr_initial_substrate_counts(
    m1_model: km.KarrMetabolismModel,
) -> dict[str, float]:
    """Map Karr's 585 substrate IDs to cytosol counts from the dynamics snapshot."""
    dyn = cfb.load_default_dynamics()
    sub_ids = [str(wid) for wid in m1_model.raw["ids"]["substrate_wcm_585"]]
    if dyn.substrates_snapshot.shape[0] != len(sub_ids):
        raise ValueError(
            "Karr dynamics substrate snapshot row count "
            f"{dyn.substrates_snapshot.shape[0]} != substrate ID count {len(sub_ids)}"
        )
    return {
        sid: float(dyn.substrates_snapshot[idx, _KARR_CYTOSOL_COMPARTMENT_0])
        for idx, sid in enumerate(sub_ids)
    }


CHASSIS_V6_EXPECTED_PROCESS_KEYS: tuple[str, ...] = (
    "karr_replication",
    "karr_replication_initiation",
    "karr_dna_supercoiling",
    "karr_chromosome_condensation",
    "karr_chromosome_segregation",
    "karr_dna_damage",
    "karr_dna_repair",
    "karr_ftsz_polymerization",
    "karr_cytokinesis",
    "karr_terminal_organelle_assembly",
    "karr_cell_cycle_coordinator",
    "karr_host_interaction",
    "karr_rna_decay",
    "karr_rna_processing",
    "karr_rna_modification",
    "karr_trna_aminoacylation",
    "karr_ribosome_assembly",
    "karr_protein_processing_i",
    "karr_protein_processing_ii",
    "karr_protein_folding",
    "karr_protein_modification",
    "karr_protein_translocation",
    "karr_protein_activation",
    "karr_protein_decay_light",
    "karr_macromolecular_complexation",
    "karr_metabolism",
    "karr_transcription",
    "karr_translation",
)

CHASSIS_V6_RUNTIME_IDENTITY_EXPECTED_CLASSES: dict[str, type[Any]] = {
    # Composition L0 currently flags only these runtime identity promotions.
    "karr_transcription": KarrTranscriptionV3Process,
    "karr_translation": KarrTranslationV3Process,
}
CHASSIS_V6_RUNTIME_IDENTITY_EXPECTED_CLASS_QUALNAMES: dict[str, str] = {
    key: cls.__qualname__ for key, cls in CHASSIS_V6_RUNTIME_IDENTITY_EXPECTED_CLASSES.items()
}
CHASSIS_V6_RUNTIME_IDENTITY_LEGACY_KEYS: tuple[str, ...] = (
    "karr_transcription_v3",
    "karr_translation_v3",
)
_TRANSLATION_FIXTURE_NPZ_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "karr_fixtures" / "per_process" / "Translation.npz"
)
_TRANSLATION_FIXTURE_MONOMERS_KEY = "fixture__monomers"


def _resolve_process_map(chassis: Any) -> Mapping[str, Any]:
    if isinstance(chassis, Mapping):
        maybe_processes = chassis.get("processes")
        if isinstance(maybe_processes, Mapping):
            return maybe_processes
        return chassis
    maybe_processes = getattr(chassis, "processes", None)
    if isinstance(maybe_processes, Mapping):
        return maybe_processes
    raise TypeError(
        "Expected a chassis/composite with a process mapping (mapping['processes'] or .processes)."
    )


def assert_chassis_runtime_identity(chassis: Any) -> None:
    """Fail fast when v6 TX/TL runtime classes drift from the audited v3 bindings."""
    process_map = _resolve_process_map(chassis)
    failures: list[str] = []

    for key, expected_cls in CHASSIS_V6_RUNTIME_IDENTITY_EXPECTED_CLASSES.items():
        proc = process_map.get(key)
        if proc is None:
            failures.append(f"missing process key '{key}'")
            continue
        observed_cls = proc.__class__
        if observed_cls is not expected_cls:
            expected_class_path = f"{expected_cls.__module__}.{expected_cls.__qualname__}"
            observed_class_path = f"{observed_cls.__module__}.{observed_cls.__qualname__}"
            failures.append(
                f"{key}: expected class {expected_class_path}, observed {observed_class_path}"
            )

    for legacy_key in CHASSIS_V6_RUNTIME_IDENTITY_LEGACY_KEYS:
        if legacy_key in process_map:
            failures.append(f"legacy process key '{legacy_key}' should not exist in v6 runtime map")

    if failures:
        raise AssertionError(
            "Chassis runtime identity guardrail failed:\n - " + "\n - ".join(failures)
        )


def _load_translation_fixture_monomers() -> np.ndarray:
    if not _TRANSLATION_FIXTURE_NPZ_PATH.exists():
        raise FileNotFoundError(f"Translation fixture companion NPZ not found: {_TRANSLATION_FIXTURE_NPZ_PATH}")
    with np.load(_TRANSLATION_FIXTURE_NPZ_PATH, allow_pickle=False) as payload:
        if _TRANSLATION_FIXTURE_MONOMERS_KEY not in payload:
            raise KeyError(
                f"Missing '{_TRANSLATION_FIXTURE_MONOMERS_KEY}' in {_TRANSLATION_FIXTURE_NPZ_PATH}"
            )
        return np.asarray(payload[_TRANSLATION_FIXTURE_MONOMERS_KEY], dtype=float).reshape(-1)


def compute_baseline_demand_per_s(
    m2_model: tx.KarrTranscriptionModel,
    m3_model: tl.KarrTranslationModel,
    *,
    condition: int = 1,
) -> dict[str, float]:
    """Build the {sid: rate_per_s} map used by M1's pool-replenishment
    source term.

    Combines un-throttled M2 NTP demand (4 keys) and un-throttled M3
    per-AA demand (20 keys) at ``synth_scale=1.0``.  This is the rate
    at which M1 must produce each demand-side substrate to keep the
    Karr-snapshot pool flat under the actual M2/M3 models attached to
    the composer (so e.g. ``condition`` and custom models propagate).
    """
    ntp = tx.ntp_consumption_per_s(
        tx.calibrated_chassis_model(m2_model),
        condition=condition,
    )
    aa = tl.aa_consumption_per_s(m3_model)
    out: dict[str, float] = {s: float(ntp[s]) for s in ("ATP", "CTP", "GTP", "UTP")}
    for a in m3_model.aa_wcm_ids:
        out[a] = float(aa[a])
    return out


def build_karr_m1_m2_engine(
    *,
    m1_model: km.KarrMetabolismModel | None = None,
    m2_model: tx.KarrTranscriptionModel | None = None,
    time_step_s: float = 1.0,
    emit_step_s: float | None = None,
    condition: int = 1,
) -> Engine:
    """Build a Vivarium Engine running M1 and M2 in lockstep (1s tick)."""
    from vivarium.core.engine import Engine

    if m1_model is None:
        m1_model = km.load_default()
    if m2_model is None:
        m2_model = tx.load_default()

    m1_proc = KarrMetabolismProcess(
        {
            "model": m1_model,
            "time_step": time_step_s,
        }
    )
    m2_proc = KarrTranscriptionProcess(
        {
            "model": m2_model,
            "time_step": time_step_s,
            "condition": condition,
            "substrate_default": _M1_SUBSTRATE_DEFAULT,
        }
    )

    rxn_ids = m1_model.rxn_wcm_ids_645
    sub_ids = m1_model.raw["ids"]["substrate_wcm_585"]
    rna_init = {
        g: float(m2_model.counts_mature[i, condition]) for i, g in enumerate(m2_model.gene_wcm_ids)
    }

    engine = Engine(
        processes={"m1_karr": m1_proc, "m2_karr": m2_proc},
        topology={
            "m1_karr": {
                "metabolic_reaction": ("metabolic_reaction",),
                "substrates": ("substrates",),
            },
            "m2_karr": {
                "rna": ("rna",),
                "substrates": ("substrates",),
            },
        },
        initial_state={
            "metabolic_reaction": {
                "fluxs": {rid: float(m1_model.fluxs_stored[i]) for i, rid in enumerate(rxn_ids)},
                "growth_per_s": float(m1_model.stored_runtime["growth_per_s"]),
                "growth_per_h": float(m1_model.stored_runtime["growth_per_h"]),
            },
            "substrates": {sid: _M1_SUBSTRATE_DEFAULT for sid in sub_ids},
            "rna": {"counts": rna_init},
        },
        emit_step=emit_step_s or time_step_s,
    )
    return engine


def build_karr_m1_m2_m3_engine(
    *,
    m1_model: km.KarrMetabolismModel | None = None,
    m2_model: tx.KarrTranscriptionModel | None = None,
    m3_model: tl.KarrTranslationModel | None = None,
    time_step_s: float = 1.0,
    emit_step_s: float | None = None,
    condition: int = 1,
    dynamic_bounds: bool = False,
    enable_throttle: bool = False,
    enable_pool_replenishment: bool = False,
) -> Engine:
    """Build a Vivarium Engine running M1, M2 AND M3 in lockstep (1s tick).

    ``dynamic_bounds=True`` enables Phase B M1 dynamic-bounds mode:
    M1 reads M2/M3 NTP/AA demand from the shared ``substrates`` store
    into a private compartmented state, recomputes flux bounds via
    Karr's ``calcFluxBounds`` (rules 1-5) every tick, and emits a
    ``m1_dynamic_diagnostics`` port.

    ``enable_throttle=True`` (Phase C.3) wires the read side of the
    closed loop: M1 publishes its 24 demand-side cytosol pools into a
    shared ``m1_pools`` store every tick, and M2/M3 read it to clamp
    their analytical-integrator synthesis scale ``f`` to the per-tick
    pool head-room.  Requires ``dynamic_bounds=True``.  Default off
    keeps the 528-test baseline trajectory unchanged.

    ``enable_pool_replenishment=True`` (Phase C.4) closes the chassis
    loop: at the end of every tick M1 adds a calibrated source term
    (un-throttled M2/M3 demand at this composer's ``condition`` /
    models) to its internal cytosol slice.  Under f=1 drain == replenish
    so pools stay at Karr's snapshot SS; under throttle-induced
    starvation pools recover and the throttle eventually unfreezes.
    Requires ``dynamic_bounds=True``.  Default off keeps the prior
    pure-drain semantics intact.
    """
    from vivarium.core.engine import Engine

    if enable_throttle and not dynamic_bounds:
        raise ValueError(
            "enable_throttle=True requires dynamic_bounds=True "
            "(throttle reads m1_pools which only M1 dynamic mode publishes)"
        )
    if enable_pool_replenishment and not dynamic_bounds:
        raise ValueError("enable_pool_replenishment=True requires dynamic_bounds=True")

    if m1_model is None:
        m1_model = km.load_default()
    if m2_model is None:
        m2_model = tx.load_default()
    if m3_model is None:
        m3_model = tl.load_default()

    baseline_demand: dict[str, float] | None = None
    if enable_pool_replenishment:
        baseline_demand = compute_baseline_demand_per_s(
            m2_model,
            m3_model,
            condition=condition,
        )

    m1_proc = KarrMetabolismProcess(
        {
            "model": m1_model,
            "time_step": time_step_s,
            "dynamic_bounds": dynamic_bounds,
            "enable_pool_replenishment": enable_pool_replenishment,
            "baseline_demand_per_s": baseline_demand,
        }
    )
    m2_proc = KarrTranscriptionProcess(
        {
            "model": m2_model,
            "time_step": time_step_s,
            "condition": condition,
            "substrate_default": _M1_SUBSTRATE_DEFAULT,
            "enable_throttle": enable_throttle,
        }
    )
    m3_proc = KarrTranslationProcess(
        {
            "model": m3_model,
            "time_step": time_step_s,
            "substrate_default": _M1_SUBSTRATE_DEFAULT,
            "enable_throttle": enable_throttle,
        }
    )
    d2_proc = MacromolecularComplexationStubProcess()

    rxn_ids = m1_model.rxn_wcm_ids_645
    sub_ids = m1_model.raw["ids"]["substrate_wcm_585"]
    rna_init = {
        g: float(m2_model.counts_mature[i, condition]) for i, g in enumerate(m2_model.gene_wcm_ids)
    }
    prot_init = {
        p: float(m3_model.counts_mature[i]) for i, p in enumerate(m3_model.protein_wcm_ids)
    }

    initial_substrates: dict[str, float] = {sid: _M1_SUBSTRATE_DEFAULT for sid in sub_ids}
    # M3 now writes per-AA deltas using IDs that are already in M1's 585
    # substrate vocabulary; no extra placeholder key required.

    m1_topo = {
        "metabolic_reaction": ("metabolic_reaction",),
        "substrates": ("substrates",),
    }
    m2_topo: dict[str, tuple[str, ...]] = {
        "rna": ("rna",),
        "substrates": ("substrates",),
    }
    m3_topo: dict[str, tuple[str, ...]] = {
        "protein": ("protein",),
        "substrates": ("substrates",),
    }
    d2_topo: dict[str, tuple[str, ...]] = {
        "complex": ("complex",),
    }
    if dynamic_bounds:
        m1_topo["m1_dynamic_diagnostics"] = ("m1_dynamic_diagnostics",)
        m1_topo["m1_pools"] = ("m1_pools",)
    if enable_throttle:
        m2_topo["m1_pools"] = ("m1_pools",)
        m3_topo["m1_pools"] = ("m1_pools",)

    initial_state: dict[str, Any] = {
        "metabolic_reaction": {
            "fluxs": {rid: float(m1_model.fluxs_stored[i]) for i, rid in enumerate(rxn_ids)},
            "growth_per_s": float(m1_model.stored_runtime["growth_per_s"]),
            "growth_per_h": float(m1_model.stored_runtime["growth_per_h"]),
        },
        "substrates": initial_substrates,
        "rna": {"counts": rna_init},
        "protein": {"counts": prot_init},
        "complex": {
            "counts": {
                wid: float(d2_proc._complex_counts_schema[wid]["_default"])
                for wid in d2_proc.d2_owned_wids
            },
        },
    }
    if dynamic_bounds:
        initial_state["m1_dynamic_diagnostics"] = {k: 0.0 for k in m1_proc._diagnostics_schema()}
        from opencell.vivarium.karr_metabolism import _CYTOSOL_COMPARTMENT_0

        initial_state["m1_pools"] = {
            sid: float(m1_proc._sub_state[idx, _CYTOSOL_COMPARTMENT_0])
            for sid, idx in m1_proc._demand_idx_pairs
        }

    engine = Engine(
        processes={
            "m1_karr": m1_proc,
            "m2_karr": m2_proc,
            "m3_karr": m3_proc,
            "d2_stub": d2_proc,
        },
        topology={
            "m1_karr": m1_topo,
            "m2_karr": m2_topo,
            "m3_karr": m3_topo,
            "d2_stub": d2_topo,
        },
        initial_state=initial_state,
        emit_step=emit_step_s or time_step_s,
    )
    return engine


def build_karr_chassis_v2(
    *,
    m1_model: km.KarrMetabolismModel | None = None,
    m2_model: tx.KarrTranscriptionModel | None = None,
    m3_model: tl.KarrTranslationModel | None = None,
    m2_mechanism_inputs: tx_v2.MechanismInputs | None = None,
    m3_mechanism_inputs: tl_v2.RibosomeMechanismInputs | None = None,
    time_step_s: float = 1.0,
    emit_step_s: float | None = None,
    condition: int = 1,
    dynamic_bounds: bool = False,
    enable_pool_replenishment: bool = False,
) -> Engine:
    """Build the A3 v2 chassis (M1 + M2v2 + M3v2 + d2-stub).

    Use this builder for forward-modeling work where M2/M3 should be
    mechanism-driven and read ``complex.counts`` every tick. Keep using
    :func:`build_karr_m1_m2_m3_engine` for legacy regression tests that
    still target v1 prescribed-rate behavior.
    """
    from vivarium.core.engine import Engine

    if enable_pool_replenishment and not dynamic_bounds:
        raise ValueError("enable_pool_replenishment=True requires dynamic_bounds=True")

    if m1_model is None:
        m1_model = km.load_default()
    if m2_model is None:
        m2_model = tx.load_default()
    if m3_model is None:
        m3_model = tl.load_default()
    if m2_mechanism_inputs is None:
        m2_mechanism_inputs = tx_v2.load_default()
    if m3_mechanism_inputs is None:
        m3_mechanism_inputs = tl_v2.load_default()

    baseline_demand: dict[str, float] | None = None
    if enable_pool_replenishment:
        baseline_demand = compute_baseline_demand_per_s(
            m2_model,
            m3_model,
            condition=condition,
        )

    m1_proc = KarrMetabolismProcess(
        {
            "model": m1_model,
            "time_step": time_step_s,
            "dynamic_bounds": dynamic_bounds,
            "enable_pool_replenishment": enable_pool_replenishment,
            "baseline_demand_per_s": baseline_demand,
        }
    )
    m2_proc = KarrTranscriptionV2Process(
        {
            "kinetics_model": tx.calibrated_chassis_model(m2_model),
            "mechanism_inputs": m2_mechanism_inputs,
            "time_step": time_step_s,
            "substrate_default": _M1_SUBSTRATE_DEFAULT,
        }
    )
    m3_proc = KarrTranslationV2Process(
        {
            "kinetics_model": m3_model,
            "mechanism_inputs": m3_mechanism_inputs,
            "time_step": time_step_s,
            "substrate_default": _M1_SUBSTRATE_DEFAULT,
        }
    )
    d2_proc = MacromolecularComplexationStubProcess()

    rxn_ids = m1_model.rxn_wcm_ids_645
    sub_ids = m1_model.raw["ids"]["substrate_wcm_585"]
    rna_init = {
        g: float(m2_model.counts_mature[i, condition]) for i, g in enumerate(m2_model.gene_wcm_ids)
    }
    prot_init = {
        p: float(m3_model.counts_mature[i]) for i, p in enumerate(m3_model.protein_wcm_ids)
    }

    initial_substrates: dict[str, float] = {sid: _M1_SUBSTRATE_DEFAULT for sid in sub_ids}
    complex_counts: dict[str, float] = {
        wid: float(d2_proc._complex_counts_schema[wid]["_default"]) for wid in d2_proc.d2_owned_wids
    }
    if "RIBOSOME_70S" not in complex_counts:
        complex_counts["RIBOSOME_70S"] = float(m3_mechanism_inputs.n_active_ribosomes)

    m1_topo = {
        "metabolic_reaction": ("metabolic_reaction",),
        "substrates": ("substrates",),
    }
    m2_topo: dict[str, tuple[str, ...]] = {
        "rna": ("rna",),
        "substrates": ("substrates",),
        "complex": ("complex",),
    }
    m3_topo: dict[str, tuple[str, ...]] = {
        "protein": ("protein",),
        "substrates": ("substrates",),
        "complex": ("complex",),
    }
    d2_topo: dict[str, tuple[str, ...]] = {
        "complex": ("complex",),
    }
    if dynamic_bounds:
        m1_topo["m1_dynamic_diagnostics"] = ("m1_dynamic_diagnostics",)
        m1_topo["m1_pools"] = ("m1_pools",)

    initial_state: dict[str, Any] = {
        "metabolic_reaction": {
            "fluxs": {rid: float(m1_model.fluxs_stored[i]) for i, rid in enumerate(rxn_ids)},
            "growth_per_s": float(m1_model.stored_runtime["growth_per_s"]),
            "growth_per_h": float(m1_model.stored_runtime["growth_per_h"]),
        },
        "substrates": initial_substrates,
        "rna": {"counts": rna_init},
        "protein": {"counts": prot_init},
        "complex": {"counts": complex_counts},
    }
    if dynamic_bounds:
        initial_state["m1_dynamic_diagnostics"] = {k: 0.0 for k in m1_proc._diagnostics_schema()}
        from opencell.vivarium.karr_metabolism import _CYTOSOL_COMPARTMENT_0

        initial_state["m1_pools"] = {
            sid: float(m1_proc._sub_state[idx, _CYTOSOL_COMPARTMENT_0])
            for sid, idx in m1_proc._demand_idx_pairs
        }

    engine = Engine(
        processes={
            "m1_karr": m1_proc,
            "m2_karr": m2_proc,
            "m3_karr": m3_proc,
            "d2_stub": d2_proc,
        },
        topology={
            "m1_karr": m1_topo,
            "m2_karr": m2_topo,
            "m3_karr": m3_topo,
            "d2_stub": d2_topo,
        },
        initial_state=initial_state,
        emit_step=emit_step_s or time_step_s,
    )
    return engine


def build_karr_chassis_v3(
    m1_model: km.KarrMetabolismModel | None = None,
    m2_model: tx.KarrTranscriptionModel | None = None,
    m3_model: tl.KarrTranslationModel | None = None,
    *,
    m2_mechanism_inputs: tx_v2.MechanismInputs | None = None,
    m3_mechanism_inputs: tl_v2.RibosomeMechanismInputs | None = None,
    time_step_s: float = 1.0,
    emit_step_s: float | None = None,
    condition: int = 1,
    dynamic_bounds: bool = False,
    enable_pool_replenishment: bool = False,
) -> Engine:
    """Build the A3 v3 chassis (M1 + M2v3 + M3v3 + D2-real + PD-light).

    v3 differences from v2:
      - M2/M3 wrappers are delta-emitting accumulate writers (v3 wrappers)
      - D2-stub is replaced with real D.2 complexation
      - ProteinDecay-light closes the complex ratchet
      - RequestCalculator steps + KarrAllocationStep wire Karr-style requests
    """
    from vivarium.core.engine import Engine

    if enable_pool_replenishment and not dynamic_bounds:
        raise ValueError("enable_pool_replenishment=True requires dynamic_bounds=True")

    if m1_model is None:
        m1_model = km.load_default()
    if m2_model is None:
        m2_model = tx.load_default()
    if m3_model is None:
        m3_model = tl.load_default()
    if m2_mechanism_inputs is None:
        m2_mechanism_inputs = tx_v2.load_default()
    if m3_mechanism_inputs is None:
        m3_mechanism_inputs = tl_v2.load_default()

    baseline_demand: dict[str, float] | None = None
    if enable_pool_replenishment:
        baseline_demand = compute_baseline_demand_per_s(
            m2_model,
            m3_model,
            condition=condition,
        )

    m1_proc = KarrMetabolismProcess(
        {
            "model": m1_model,
            "time_step": time_step_s,
            "dynamic_bounds": dynamic_bounds,
            "use_allocator_budget": True,
            "enable_pool_replenishment": enable_pool_replenishment,
            "baseline_demand_per_s": baseline_demand,
        }
    )
    m2_proc = KarrTranscriptionV3Process(
        {
            "kinetics_model": tx.calibrated_chassis_model(m2_model),
            "mechanism_inputs": m2_mechanism_inputs,
            "time_step": time_step_s,
            "use_allocator_budget": True,
            "substrate_default": _M1_SUBSTRATE_DEFAULT,
        }
    )
    m3_proc = KarrTranslationV3Process(
        {
            "kinetics_model": m3_model,
            "mechanism_inputs": m3_mechanism_inputs,
            "time_step": time_step_s,
            "use_allocator_budget": True,
            "substrate_default": _M1_SUBSTRATE_DEFAULT,
        }
    )
    d2_proc = MacromolecularComplexationProcess({"time_step": time_step_s})
    decay_proc = ProteinDecayLightProcess({"time_step": time_step_s})
    p_trans_proc = KarrProteinTranslocationProcess({"time_step": time_step_s})

    allocation_substrates = sorted(
        set(m1_model.raw["ids"]["substrate_wcm_585"])
        | set(m1_proc.allocation_substrate_wids)
        | set(m2_proc.allocation_substrate_wids)
        | set(m3_proc.allocation_substrate_wids)
        | set(d2_proc.substrate_wids)
        | set(decay_proc.substrate_wids)
        | set(p_trans_proc.allocation_substrate_wids)
    )
    consumer_processes: list[tuple[str, list[str]]] = [
        (m2_proc.name, list(m2_proc.allocation_substrate_wids)),
        (m3_proc.name, list(m3_proc.allocation_substrate_wids)),
        ("karr_macromolecular_complexation", list(d2_proc.substrate_wids)),
        ("karr_protein_decay_light", ["ATP", "H2O"]),
        (p_trans_proc.name, list(p_trans_proc.allocation_substrate_wids)),
    ]
    if m1_proc.allocation_substrate_wids:
        consumer_processes.insert(0, (m1_proc.name, list(m1_proc.allocation_substrate_wids)))
    allocation_step = KarrAllocationStep(
        {
            "consumer_processes": consumer_processes,
            "substrate_wids": allocation_substrates,
        }
    )
    req_d2 = RequestCalculatorD2({"d2_real_proc": d2_proc})
    req_pd = RequestCalculatorPD({"pd_light_proc": decay_proc})
    req_metabolism = RequestCalculatorMetabolism({"metabolism_proc": m1_proc})
    req_transcription = RequestCalculatorTranscription({"transcription_proc": m2_proc})
    req_translation = RequestCalculatorTranslation({"translation_proc": m3_proc})
    req_protein_translocation = RequestCalculatorPTransloc(
        {"protein_translocation_proc": p_trans_proc}
    )

    rxn_ids = m1_model.rxn_wcm_ids_645
    m1_sub_ids = [str(wid) for wid in m1_model.raw["ids"]["substrate_wcm_585"]]
    rna_init = {
        g: float(m2_model.counts_mature[i, condition]) for i, g in enumerate(m2_model.gene_wcm_ids)
    }
    prot_init = {
        p: float(m3_model.counts_mature[i]) for i, p in enumerate(m3_model.protein_wcm_ids)
    }

    initial_substrates: dict[str, float] = {sid: 0.0 for sid in allocation_substrates}
    for sid in m1_sub_ids:
        initial_substrates[sid] = _M1_SUBSTRATE_DEFAULT
    # Seed D.2's free-monomer substrate pool from M3's mature monomer snapshot.
    for wid, cnt in prot_init.items():
        if wid in initial_substrates:
            initial_substrates[wid] = max(initial_substrates[wid], cnt)
    for wid, cnt in rna_init.items():
        if wid in initial_substrates:
            initial_substrates[wid] = max(initial_substrates[wid], cnt)

    complex_counts = {
        "RNA_POLYMERASE": float(m2_mechanism_inputs.n_active_rnap),
        "RIBOSOME_70S": float(m3_mechanism_inputs.n_active_ribosomes),
    }

    m1_topo = {
        "metabolic_reaction": ("metabolic_reaction",),
        "substrates": ("substrates",),
        "substrates_allocated": ("substrates_allocated",),
    }
    if dynamic_bounds:
        m1_topo["m1_dynamic_diagnostics"] = ("m1_dynamic_diagnostics",)
        m1_topo["m1_pools"] = ("m1_pools",)

    topology: dict[str, dict[str, tuple[str, ...]]] = {
        "karr_metabolism": m1_topo,
        "karr_transcription_v3": {
            "rna": ("rna",),
            "substrates": ("substrates",),
            "complex": ("complex",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_translation_v3": {
            "protein": ("protein",),
            "substrates": ("substrates",),
            "complex": ("complex",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_macromolecular_complexation": {
            "substrates": ("substrates",),
            "complex": ("complex",),
            "requests": ("_internal_requests",),
            "substrates_allocated": ("_internal_substrates_allocated",),
        },
        "karr_protein_decay_light": {
            "complex": ("complex",),
            "substrates": ("substrates",),
            "protein": ("protein",),
            "rna": ("rna",),
            "requests": ("_internal_requests",),
            "substrates_allocated": ("_internal_substrates_allocated",),
        },
        "karr_protein_translocation": {
            "substrates": ("substrates",),
            "protein": ("protein",),
            "requests": ("_internal_requests_ptrans",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "request_calculator_d2": {
            "complex": ("complex",),
            "requests": ("requests",),
        },
        "request_calculator_pd": {
            "complex": ("complex",),
            "requests": ("requests",),
        },
        "request_calculator_metabolism": {
            "requests": ("requests",),
        },
        "request_calculator_transcription": {
            "complex": ("complex",),
            "requests": ("requests",),
        },
        "request_calculator_translation": {
            "complex": ("complex",),
            "requests": ("requests",),
        },
        "request_calculator_protein_translocation": {
            "substrates": ("substrates",),
            "protein": ("protein",),
            "requests": ("requests",),
        },
        "karr_allocation_step": {
            "substrates": ("substrates",),
            "requests": ("requests",),
            "substrates_allocated": ("substrates_allocated",),
        },
    }

    initial_state: dict[str, Any] = {
        "metabolic_reaction": {
            "fluxs": {rid: float(m1_model.fluxs_stored[i]) for i, rid in enumerate(rxn_ids)},
            "growth_per_s": float(m1_model.stored_runtime["growth_per_s"]),
            "growth_per_h": float(m1_model.stored_runtime["growth_per_h"]),
        },
        "substrates": initial_substrates,
        "rna": {"counts": rna_init},
        "protein": {
            "counts": prot_init,
            "location": {wid: "cytoplasm" for wid in p_trans_proc.translocatable_wids},
        },
        "complex": {"counts": complex_counts},
    }
    if dynamic_bounds:
        initial_state["m1_dynamic_diagnostics"] = {k: 0.0 for k in m1_proc._diagnostics_schema()}
        from opencell.vivarium.karr_metabolism import _CYTOSOL_COMPARTMENT_0

        initial_state["m1_pools"] = {
            sid: float(m1_proc._sub_state[idx, _CYTOSOL_COMPARTMENT_0])
            for sid, idx in m1_proc._demand_idx_pairs
        }

    engine = Engine(
        processes={
            "karr_metabolism": m1_proc,
            "karr_transcription_v3": m2_proc,
            "karr_translation_v3": m3_proc,
            "karr_macromolecular_complexation": d2_proc,
            "karr_protein_decay_light": decay_proc,
            "karr_protein_translocation": p_trans_proc,
        },
        steps={
            "request_calculator_d2": req_d2,
            "request_calculator_pd": req_pd,
            "request_calculator_metabolism": req_metabolism,
            "request_calculator_transcription": req_transcription,
            "request_calculator_translation": req_translation,
            "request_calculator_protein_translocation": req_protein_translocation,
            "karr_allocation_step": allocation_step,
        },
        flow={
            "request_calculator_d2": [],
            "request_calculator_pd": [],
            "request_calculator_metabolism": [],
            "request_calculator_transcription": [],
            "request_calculator_translation": [],
            "request_calculator_protein_translocation": [],
            "karr_allocation_step": [
                ("request_calculator_d2",),
                ("request_calculator_pd",),
                ("request_calculator_metabolism",),
                ("request_calculator_transcription",),
                ("request_calculator_translation",),
                ("request_calculator_protein_translocation",),
            ],
        },
        topology=topology,
        initial_state=initial_state,
        emit_step=emit_step_s or time_step_s,
        display_info=False,
    )
    return engine


def build_karr_chassis_v4(
    m1_model: km.KarrMetabolismModel | None = None,
    m2_model: tx.KarrTranscriptionModel | None = None,
    m3_model: tl.KarrTranslationModel | None = None,
    *,
    m2_mechanism_inputs: tx_v2.MechanismInputs | None = None,
    m3_mechanism_inputs: tl_v2.RibosomeMechanismInputs | None = None,
    time_step_s: float = 1.0,
    emit_step_s: float | None = None,
    condition: int = 1,
    dynamic_bounds: bool = False,
    enable_pool_replenishment: bool = False,
    karr_parity_mode: bool = True,
) -> Engine:
    """Build the Phase-B chassis v4 with RNA/protein maturation processes."""
    from vivarium.core.engine import Engine

    if enable_pool_replenishment and not dynamic_bounds:
        raise ValueError("enable_pool_replenishment=True requires dynamic_bounds=True")

    if m1_model is None:
        m1_model = km.load_default()
    if m2_model is None:
        m2_model = tx.load_default()
    if m3_model is None:
        m3_model = tl.load_default()
    if m2_mechanism_inputs is None:
        m2_mechanism_inputs = tx_v2.load_default()
    if m3_mechanism_inputs is None:
        m3_mechanism_inputs = tl_v2.load_default()

    baseline_demand: dict[str, float] | None = None
    if enable_pool_replenishment:
        baseline_demand = compute_baseline_demand_per_s(
            m2_model,
            m3_model,
            condition=condition,
        )

    m1_proc = KarrMetabolismProcess(
        {
            "model": m1_model,
            "time_step": time_step_s,
            "dynamic_bounds": dynamic_bounds,
            "use_allocator_budget": True,
            "enable_pool_replenishment": enable_pool_replenishment,
            "baseline_demand_per_s": baseline_demand,
        }
    )
    m2_proc = KarrTranscriptionV3Process(
        {
            "kinetics_model": tx.calibrated_chassis_model(m2_model),
            "mechanism_inputs": m2_mechanism_inputs,
            "time_step": time_step_s,
            "use_allocator_budget": True,
            "substrate_default": _M1_SUBSTRATE_DEFAULT,
        }
    )
    m3_proc = KarrTranslationV3Process(
        {
            "kinetics_model": m3_model,
            "mechanism_inputs": m3_mechanism_inputs,
            "time_step": time_step_s,
            "use_allocator_budget": True,
            "substrate_default": _M1_SUBSTRATE_DEFAULT,
        }
    )
    d2_proc = MacromolecularComplexationProcess({"time_step": time_step_s})
    decay_proc = ProteinDecayLightProcess({"time_step": time_step_s})
    trna_proc = KarrTRNAAminoacylationProcess(
        {
            "time_step": time_step_s,
            "emit_noop_update": True,
            "emit_trace_heartbeat_on_noop": True,
        }
    )
    ribasm_proc = KarrRibosomeAssemblyProcess({"time_step": time_step_s})
    tx_reg_proc = KarrTranscriptionalRegulationProcess({"time_step": time_step_s})
    rna_proc = KarrRNAProcessingProcess({"time_step": time_step_s})
    rna_mod_proc = KarrRNAModificationProcess({"time_step": time_step_s})
    pp1_proc = KarrProteinProcessingIProcess({"time_step": time_step_s})
    pp2_proc = KarrProteinProcessingIIProcess({"time_step": time_step_s})
    p_mod_proc = KarrProteinModificationProcess({"time_step": time_step_s})
    p_fold_proc = KarrProteinFoldingProcess({"time_step": time_step_s})
    p_trans_proc = KarrProteinTranslocationProcess({"time_step": time_step_s})
    p_activation_proc = KarrProteinActivationProcess({"time_step": time_step_s})
    ftsz_proc = KarrFtsZPolymerizationProcess({"time_step": time_step_s})

    trna_consumed = [
        trna_proc.substrate_wids[int(i)]
        for i in np.flatnonzero(np.any(trna_proc.reaction_stoich < 0, axis=1))
    ]
    rna_proc_consumed = [
        rna_proc.substrate_wids[int(i)]
        for i in np.flatnonzero(np.any(rna_proc.reaction_stoich < 0, axis=1))
    ]
    rna_mod_consumed = [
        rna_mod_proc.substrate_wids[int(i)]
        for i in np.flatnonzero(np.any(rna_mod_proc.reaction_stoich < 0, axis=1))
    ]
    pp2_consumed = [
        pp2_proc.substrate_wids[int(i)]
        for i in np.flatnonzero(np.any(pp2_proc.reaction_stoich < 0, axis=1))
    ]
    p_mod_consumed = [
        p_mod_proc.substrate_wids[int(i)]
        for i in np.flatnonzero(np.any(p_mod_proc.reaction_stoich < 0, axis=1))
    ]
    p_fold_consumed = [
        p_fold_proc.substrate_wids[p_fold_proc.substrate_idx_atp],
        p_fold_proc.substrate_wids[p_fold_proc.substrate_idx_fe2],
        p_fold_proc.substrate_wids[p_fold_proc.substrate_idx_mg],
        p_fold_proc.substrate_wids[p_fold_proc.substrate_idx_zinc],
    ]

    allocation_substrates = sorted(
        set(m1_model.raw["ids"]["substrate_wcm_585"])
        | set(m1_proc.allocation_substrate_wids)
        | set(m2_proc.allocation_substrate_wids)
        | set(m3_proc.allocation_substrate_wids)
        | set(d2_proc.substrate_wids)
        | set(decay_proc.substrate_wids)
        | set(trna_consumed)
        | set(ribasm_proc.substrate_wids)
        | set(rna_proc_consumed)
        | set(rna_mod_consumed)
        | {pp1_proc.substrate_wids[pp1_proc.substrate_idx_water]}
        | set(pp2_consumed)
        | set(p_mod_consumed)
        | set(p_fold_consumed)
        | set(p_trans_proc.allocation_substrate_wids)
        | set(p_activation_proc.substrate_wids)
        | {ftsz_proc.gtp_wid}
    )
    consumer_processes = [
        (m2_proc.name, list(m2_proc.allocation_substrate_wids)),
        (m3_proc.name, list(m3_proc.allocation_substrate_wids)),
        ("karr_macromolecular_complexation", list(d2_proc.substrate_wids)),
        ("karr_protein_decay_light", ["ATP", "H2O"]),
        (
            ribasm_proc.name,
            [ribasm_proc.substrate_wid_gtp, ribasm_proc.substrate_wid_h2o],
        ),
        (trna_proc.name, trna_consumed),
        (rna_proc.name, rna_proc_consumed),
        (rna_mod_proc.name, rna_mod_consumed),
        (pp1_proc.name, [pp1_proc.substrate_wids[pp1_proc.substrate_idx_water]]),
        (pp2_proc.name, pp2_consumed),
        (p_mod_proc.name, p_mod_consumed),
        (p_fold_proc.name, p_fold_consumed),
        (p_trans_proc.name, list(p_trans_proc.allocation_substrate_wids)),
        (ftsz_proc.name, [ftsz_proc.gtp_wid]),
    ]
    if m1_proc.allocation_substrate_wids:
        consumer_processes.insert(0, (m1_proc.name, list(m1_proc.allocation_substrate_wids)))
    allocation_step = KarrAllocationStep(
        {
            "consumer_processes": consumer_processes,
            "substrate_wids": allocation_substrates,
        }
    )
    req_d2 = RequestCalculatorD2({"d2_real_proc": d2_proc})
    req_pd = RequestCalculatorPD({"pd_light_proc": decay_proc})
    req_ribasm = RequestCalculatorRibAsm({"ribasm_proc": ribasm_proc})
    req_trna = RequestCalculatorTRNA({"trna_proc": trna_proc})
    req_rna = RequestCalculatorRNAPathway(
        {
            "rna_processing_proc": rna_proc,
            "rna_modification_proc": rna_mod_proc,
        }
    )
    req_protein = RequestCalculatorProteinPathway(
        {
            "protein_processing_i_proc": pp1_proc,
            "protein_processing_ii_proc": pp2_proc,
            "protein_modification_proc": p_mod_proc,
            "protein_folding_proc": p_fold_proc,
            "protein_translocation_proc": p_trans_proc,
        }
    )
    req_metabolism = RequestCalculatorMetabolism(
        {
            "metabolism_proc": m1_proc,
            "karr_parity_mode": karr_parity_mode,
        }
    )
    req_transcription = RequestCalculatorTranscription({"transcription_proc": m2_proc})
    req_translation = RequestCalculatorTranslation({"translation_proc": m3_proc})
    req_protein_translocation = RequestCalculatorPTransloc(
        {"protein_translocation_proc": p_trans_proc}
    )

    rxn_ids = m1_model.rxn_wcm_ids_645
    m1_sub_ids = [str(wid) for wid in m1_model.raw["ids"]["substrate_wcm_585"]]
    rna_init = {
        g: float(m2_model.counts_mature[i, condition]) for i, g in enumerate(m2_model.gene_wcm_ids)
    }
    prot_init = {
        p: float(m3_model.counts_mature[i]) for i, p in enumerate(m3_model.protein_wcm_ids)
    }

    initial_substrates: dict[str, float] = {sid: 0.0 for sid in allocation_substrates}
    for sid in m1_sub_ids:
        initial_substrates[sid] = _M1_SUBSTRATE_DEFAULT
    for wid, cnt in prot_init.items():
        if wid in initial_substrates:
            initial_substrates[wid] = max(initial_substrates[wid], cnt)
    for wid, cnt in rna_init.items():
        if wid in initial_substrates:
            initial_substrates[wid] = max(initial_substrates[wid], cnt)

    aminoacylated_init: dict[str, float] = {wid: 0.0 for wid in trna_proc.aminoacylated_rna_wids}
    for wid in trna_proc.free_rna_wids:
        total = max(0.0, float(rna_init.get(wid, 0.0)))
        free = total / 3.0
        charged = total - free
        rna_init[wid] = free
        if wid in aminoacylated_init:
            aminoacylated_init[wid] = charged
    rna_modified_init: dict[str, float] = {wid: 0.0 for wid in rna_mod_proc.modified_rna_wids}
    tx_rate_fold_init: dict[str, float] = {tu_wid: 1.0 for tu_wid in m2_proc.tu_wids}
    trna_gene_wids = set(trna_proc.free_rna_wids)
    for gidx, gene_wid in enumerate(m2_proc.gene_ids):
        if gene_wid in trna_gene_wids:
            tx_rate_fold_init[f"TU_{gidx + 1:03d}"] = 0.0

    protein_unprocessed_init = {
        wid: 0.0
        for wid in sorted(
            set(pp1_proc.unprocessed_monomer_wids) | set(pp2_proc.unprocessed_monomer_wids)
        )
    }
    protein_unfolded_init = {wid: 0.0 for wid in p_fold_proc.unfolded_monomer_wids}
    protein_unmodified_init = {
        wid: float(prot_init.get(wid, 0.0)) for wid in p_mod_proc.unmodified_monomer_wids
    }
    protein_processed_init = {wid: 0.0 for wid in pp2_proc.processed_monomer_wids}
    protein_signal_seq_init = {wid: 0.0 for wid in pp2_proc.signal_sequence_monomer_wids}
    protein_modified_init = {wid: 0.0 for wid in p_mod_proc.modified_monomer_wids}
    protein_enzyme_init = {
        wid: float(prot_init.get(wid, 0.0))
        for wid in sorted(set(pp1_proc.enzyme_wids) | set(pp2_proc.enzyme_wids))
    }
    protein_enzyme_init["MG_106_DIMER"] = 22.0  # from PP1_flat.mat enzymes column
    protein_enzyme_init["MG_172_MONOMER"] = 38.0  # from PP1_flat.mat enzymes column
    protein_location_init = {wid: "cytoplasm" for wid in p_trans_proc.translocatable_wids}
    protein_activity_init = {wid: 0 for wid in p_activation_proc.regulated_protein_wids}

    complex_counts = {
        "RNA_POLYMERASE": float(m2_mechanism_inputs.n_active_rnap),
        "RIBOSOME_70S": float(m3_mechanism_inputs.n_active_ribosomes),
    }
    for wid in ribasm_proc.complex_wids:
        complex_counts.setdefault(wid, 0.0)

    m1_topo = {
        "metabolic_reaction": ("metabolic_reaction",),
        "substrates": ("substrates",),
        "substrates_allocated": ("substrates_allocated",),
    }
    if dynamic_bounds:
        m1_topo["m1_dynamic_diagnostics"] = ("m1_dynamic_diagnostics",)
        m1_topo["m1_pools"] = ("m1_pools",)

    topology: dict[str, dict[str, tuple[str, ...]]] = {
        "karr_metabolism": m1_topo,
        "karr_transcription_v3": {
            "rna": ("rna",),
            "substrates": ("substrates",),
            "complex": ("complex",),
            "substrates_allocated": ("substrates_allocated",),
            "tx_rate_fold_change": ("tx_rate_fold_change",),
        },
        "karr_translation_v3": {
            "protein": ("protein",),
            "substrates": ("substrates",),
            "complex": ("complex",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_macromolecular_complexation": {
            "substrates": ("substrates",),
            "complex": ("complex",),
            "requests": ("_internal_requests_d2",),
            "substrates_allocated": ("_internal_substrates_allocated_d2",),
        },
        "karr_protein_decay_light": {
            "complex": ("complex",),
            "substrates": ("substrates",),
            "protein": ("protein",),
            "rna": ("rna",),
            "requests": ("_internal_requests_pd",),
            "substrates_allocated": ("_internal_substrates_allocated_pd",),
        },
        "karr_trna_aminoacylation": {
            "substrates": ("substrates",),
            "rna": ("rna",),
            "protein": ("protein",),
            "requests": ("_internal_requests_trna",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_ribosome_assembly": {
            "substrates": ("substrates",),
            "rna": ("rna",),
            "protein": ("protein",),
            "complex": ("complex",),
            "requests": ("_internal_requests_ribasm",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_transcriptional_regulation": {
            "protein": ("protein",),
            "tf_binding": ("tf_binding",),
            "tx_rate_fold_change": ("tx_rate_fold_change",),
        },
        "karr_rna_processing": {
            "substrates": ("substrates",),
            "rna": ("rna",),
            "protein": ("protein",),
            "requests": ("_internal_requests_rna_proc",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_rna_modification": {
            "substrates": ("substrates",),
            "rna": ("rna",),
            "protein": ("protein",),
            "complex": ("complex",),
            "requests": ("_internal_requests_rna_mod",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_protein_processing_i": {
            "substrates": ("substrates",),
            "protein": ("protein",),
            "requests": ("_internal_requests_pp1",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_protein_processing_ii": {
            "substrates": ("substrates",),
            "protein": ("protein",),
            "requests": ("_internal_requests_pp2",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_protein_modification": {
            "substrates": ("substrates",),
            "protein": ("protein",),
            "requests": ("_internal_requests_pmod",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_protein_folding": {
            "substrates": ("substrates",),
            "protein": ("protein",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_protein_translocation": {
            "substrates": ("substrates",),
            "protein": ("protein",),
            "requests": ("_internal_requests_ptrans",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_protein_activation": {
            "substrates": ("activation_substrates",),
            "stimuli": ("stimuli",),
            "protein": ("protein",),
        },
        "karr_ftsz_polymerization": {
            "cell": ("cell",),
            "substrates": ("substrates",),
            "requests": ("requests",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "request_calculator_d2": {
            "complex": ("complex",),
            "requests": ("requests",),
        },
        "request_calculator_pd": {
            "complex": ("complex",),
            "requests": ("requests",),
        },
        "request_calculator_ribasm": {
            "substrates": ("substrates",),
            "rna": ("rna",),
            "protein": ("protein",),
            "requests": ("requests",),
        },
        "request_calculator_trna": {
            "substrates": ("substrates",),
            "rna": ("rna",),
            "requests": ("requests",),
        },
        "request_calculator_rna_pathway": {
            "substrates": ("substrates",),
            "rna": ("rna",),
            "requests": ("requests",),
        },
        "request_calculator_protein_pathway": {
            "substrates": ("substrates",),
            "protein": ("protein",),
            "requests": ("requests",),
        },
        "request_calculator_metabolism": {
            "requests": ("requests",),
        },
        "request_calculator_transcription": {
            "complex": ("complex",),
            "requests": ("requests",),
        },
        "request_calculator_translation": {
            "complex": ("complex",),
            "requests": ("requests",),
        },
        "request_calculator_protein_translocation": {
            "substrates": ("substrates",),
            "protein": ("protein",),
            "requests": ("requests",),
        },
        "karr_allocation_step": {
            "substrates": ("substrates",),
            "requests": ("requests",),
            "substrates_allocated": ("substrates_allocated",),
        },
    }

    initial_state: dict[str, Any] = {
        "metabolic_reaction": {
            "fluxs": {rid: float(m1_model.fluxs_stored[i]) for i, rid in enumerate(rxn_ids)},
            "growth_per_s": float(m1_model.stored_runtime["growth_per_s"]),
            "growth_per_h": float(m1_model.stored_runtime["growth_per_h"]),
        },
        "substrates": initial_substrates,
        "rna": {
            "counts": rna_init,
            "aminoacylated_counts": aminoacylated_init,
            "modified_counts": rna_modified_init,
        },
        "protein": {
            "counts": prot_init,
            "unprocessed_counts": protein_unprocessed_init,
            "unfolded_counts": protein_unfolded_init,
            "unmodified_counts": protein_unmodified_init,
            "processed_counts": protein_processed_init,
            "signal_sequence_counts": protein_signal_seq_init,
            "modified_counts": protein_modified_init,
            "enzyme_counts": protein_enzyme_init,
            "location": protein_location_init,
            "activity": protein_activity_init,
        },
        "complex": {"counts": complex_counts},
        "stimuli": {wid: 0.0 for wid in p_activation_proc.stimuli_wids},
        "activation_substrates": {
            wid: float(initial_substrates.get(wid, 0.0)) for wid in p_activation_proc.substrate_wids
        },
        "tx_rate_fold_change": tx_rate_fold_init,
        "cell": {
            "ftsz_ring_count": float(ftsz_proc.initial_ring_count),
            "ftsz_ring_complete": bool(
                ftsz_proc.initial_ring_count
                >= int(ftsz_proc.parameters["ring_complete_threshold"])
            ),
        },
    }
    if dynamic_bounds:
        initial_state["m1_dynamic_diagnostics"] = {k: 0.0 for k in m1_proc._diagnostics_schema()}
        from opencell.vivarium.karr_metabolism import _CYTOSOL_COMPARTMENT_0

        initial_state["m1_pools"] = {
            sid: float(m1_proc._sub_state[idx, _CYTOSOL_COMPARTMENT_0])
            for sid, idx in m1_proc._demand_idx_pairs
        }

    engine = Engine(
        processes={
            "karr_metabolism": m1_proc,
            "karr_transcription_v3": m2_proc,
            "karr_translation_v3": m3_proc,
            "karr_macromolecular_complexation": d2_proc,
            "karr_protein_decay_light": decay_proc,
            "karr_trna_aminoacylation": trna_proc,
            "karr_ribosome_assembly": ribasm_proc,
            "karr_transcriptional_regulation": tx_reg_proc,
            "karr_rna_processing": rna_proc,
            "karr_rna_modification": rna_mod_proc,
            "karr_protein_processing_i": pp1_proc,
            "karr_protein_processing_ii": pp2_proc,
            "karr_protein_modification": p_mod_proc,
            "karr_protein_folding": p_fold_proc,
            "karr_protein_translocation": p_trans_proc,
            "karr_protein_activation": p_activation_proc,
            "karr_ftsz_polymerization": ftsz_proc,
        },
        steps={
            "request_calculator_d2": req_d2,
            "request_calculator_pd": req_pd,
            "request_calculator_ribasm": req_ribasm,
            "request_calculator_trna": req_trna,
            "request_calculator_rna_pathway": req_rna,
            "request_calculator_protein_pathway": req_protein,
            "request_calculator_metabolism": req_metabolism,
            "request_calculator_transcription": req_transcription,
            "request_calculator_translation": req_translation,
            "request_calculator_protein_translocation": req_protein_translocation,
            "karr_allocation_step": allocation_step,
        },
        flow={
            "request_calculator_d2": [],
            "request_calculator_pd": [],
            "request_calculator_ribasm": [],
            "request_calculator_trna": [],
            "request_calculator_rna_pathway": [],
            "request_calculator_protein_pathway": [],
            "request_calculator_metabolism": [],
            "request_calculator_transcription": [],
            "request_calculator_translation": [],
            "request_calculator_protein_translocation": [],
            "karr_allocation_step": [
                ("request_calculator_d2",),
                ("request_calculator_pd",),
                ("request_calculator_ribasm",),
                ("request_calculator_trna",),
                ("request_calculator_rna_pathway",),
                ("request_calculator_protein_pathway",),
                ("request_calculator_metabolism",),
                ("request_calculator_transcription",),
                ("request_calculator_translation",),
                ("request_calculator_protein_translocation",),
            ],
        },
        topology=topology,
        initial_state=initial_state,
        emit_step=emit_step_s or time_step_s,
    )
    return engine




def build_karr_chassis_v5(
    m1_model: km.KarrMetabolismModel | None = None,
    m2_model: tx.KarrTranscriptionModel | None = None,
    m3_model: tl.KarrTranslationModel | None = None,
    *,
    m2_mechanism_inputs: tx_v2.MechanismInputs | None = None,
    m3_mechanism_inputs: tl_v2.RibosomeMechanismInputs | None = None,
    time_step_s: float = 1.0,
    emit_step_s: float | None = None,
    condition: int = 1,
    dynamic_bounds: bool = False,
    enable_pool_replenishment: bool = False,
    seed_from_fixture: bool = True,
    karr_parity_mode: bool = True,
) -> Engine:
    """Build the Phase-C chassis v5 with integrated replication/cell-cycle processes."""
    from vivarium.core.engine import Engine

    if enable_pool_replenishment and not dynamic_bounds:
        raise ValueError("enable_pool_replenishment=True requires dynamic_bounds=True")

    if m1_model is None:
        m1_model = km.load_default()
    if m2_model is None:
        m2_model = tx.load_default()
    if m3_model is None:
        m3_model = tl.load_default()
    if m2_mechanism_inputs is None:
        m2_mechanism_inputs = tx_v2.load_default()
    if m3_mechanism_inputs is None:
        m3_mechanism_inputs = tl_v2.load_default()

    baseline_demand: dict[str, float] | None = None
    if enable_pool_replenishment:
        baseline_demand = compute_baseline_demand_per_s(
            m2_model,
            m3_model,
            condition=condition,
        )

    m1_proc = KarrMetabolismProcess(
        {
            "model": m1_model,
            "time_step": time_step_s,
            "dynamic_bounds": dynamic_bounds,
            "use_allocator_budget": True,
            "enable_pool_replenishment": enable_pool_replenishment,
            "baseline_demand_per_s": baseline_demand,
        }
    )
    # L0 runtime-identity invariant (S03/S04): v5/v6 canonical chassis binds
    # TX/TL to the v3 process classes, never the legacy wrapper classes.
    m2_proc = KarrTranscriptionV3Process(
        {
            "kinetics_model": tx.calibrated_chassis_model(m2_model),
            "mechanism_inputs": m2_mechanism_inputs,
            "time_step": time_step_s,
            "use_allocator_budget": True,
            "substrate_default": _M1_SUBSTRATE_DEFAULT,
        }
    )
    m3_proc = KarrTranslationV3Process(
        {
            "kinetics_model": m3_model,
            "mechanism_inputs": m3_mechanism_inputs,
            "time_step": time_step_s,
            "use_allocator_budget": True,
            "substrate_default": _M1_SUBSTRATE_DEFAULT,
        }
    )
    d2_proc = MacromolecularComplexationProcess({"time_step": time_step_s})
    decay_proc = ProteinDecayLightProcess({"time_step": time_step_s})
    trna_proc = KarrTRNAAminoacylationProcess(
        {
            "time_step": time_step_s,
            "emit_noop_update": True,
            "emit_trace_heartbeat_on_noop": True,
        }
    )
    ribasm_proc = KarrRibosomeAssemblyProcess({"time_step": time_step_s})
    tx_reg_proc = KarrTranscriptionalRegulationProcess({"time_step": time_step_s})
    rna_proc = KarrRNAProcessingProcess({"time_step": time_step_s})
    rna_mod_proc = KarrRNAModificationProcess({"time_step": time_step_s})
    pp1_proc = KarrProteinProcessingIProcess({"time_step": time_step_s})
    pp2_proc = KarrProteinProcessingIIProcess({"time_step": time_step_s})
    p_mod_proc = KarrProteinModificationProcess({"time_step": time_step_s})
    p_fold_proc = KarrProteinFoldingProcess({"time_step": time_step_s})
    p_trans_proc = KarrProteinTranslocationProcess({"time_step": time_step_s})
    p_activation_proc = KarrProteinActivationProcess({"time_step": time_step_s})

    rep_init_proc = KarrReplicationInitiationProcess({"time_step": time_step_s})
    rep_proc = KarrReplicationProcess({"time_step": time_step_s})
    supercoil_proc = KarrDNASupercoilingProcess({"time_step": time_step_s})
    condensation_proc = KarrChromosomeCondensationProcess({"time_step": time_step_s})
    segregation_proc = KarrChromosomeSegregationProcess({"time_step": time_step_s})
    dna_damage_proc = KarrDNADamageProcess({"time_step": time_step_s})
    dna_repair_proc = KarrDNARepairProcess({"time_step": time_step_s})
    ftsz_proc = KarrFtsZPolymerizationProcess({"time_step": time_step_s})
    cytokinesis_proc = KarrCytokinesisProcess({"time_step": time_step_s})
    terminal_organelle_proc = KarrTerminalOrganelleAssemblyProcess({"time_step": time_step_s})

    coordinator_step = CellCycleCoordinator(
        {
            "time_step": time_step_s,
            "terc_position_bp": float(rep_proc.terc_position_bp),
        }
    )

    trna_consumed = [
        trna_proc.substrate_wids[int(i)]
        for i in np.flatnonzero(np.any(trna_proc.reaction_stoich < 0, axis=1))
    ]
    rna_proc_consumed = [
        rna_proc.substrate_wids[int(i)]
        for i in np.flatnonzero(np.any(rna_proc.reaction_stoich < 0, axis=1))
    ]
    rna_mod_consumed = [
        rna_mod_proc.substrate_wids[int(i)]
        for i in np.flatnonzero(np.any(rna_mod_proc.reaction_stoich < 0, axis=1))
    ]
    pp2_consumed = [
        pp2_proc.substrate_wids[int(i)]
        for i in np.flatnonzero(np.any(pp2_proc.reaction_stoich < 0, axis=1))
    ]
    p_mod_consumed = [
        p_mod_proc.substrate_wids[int(i)]
        for i in np.flatnonzero(np.any(p_mod_proc.reaction_stoich < 0, axis=1))
    ]
    p_fold_consumed = [
        p_fold_proc.substrate_wids[p_fold_proc.substrate_idx_atp],
        p_fold_proc.substrate_wids[p_fold_proc.substrate_idx_fe2],
        p_fold_proc.substrate_wids[p_fold_proc.substrate_idx_mg],
        p_fold_proc.substrate_wids[p_fold_proc.substrate_idx_zinc],
    ]

    allocation_substrates = sorted(
        set(m1_model.raw["ids"]["substrate_wcm_585"])
        | set(m1_proc.allocation_substrate_wids)
        | set(m2_proc.allocation_substrate_wids)
        | set(m3_proc.allocation_substrate_wids)
        | set(d2_proc.substrate_wids)
        | set(decay_proc.substrate_wids)
        | set(trna_consumed)
        | set(ribasm_proc.substrate_wids)
        | set(rna_proc_consumed)
        | set(rna_mod_consumed)
        | {pp1_proc.substrate_wids[pp1_proc.substrate_idx_water]}
        | set(pp2_consumed)
        | set(p_mod_consumed)
        | set(p_fold_consumed)
        | set(p_trans_proc.allocation_substrate_wids)
        | set(p_activation_proc.substrate_wids)
        | {rep_init_proc.atp_wid, rep_init_proc.water_wid}
        | set(rep_proc.dntp_wids)
        | {rep_proc.atp_wid}
        | {supercoil_proc.atp_wid, supercoil_proc.h2o_wid}
        | {condensation_proc.atp_wid, condensation_proc.water_wid}
        | {segregation_proc.gtp_wid, segregation_proc.h2o_wid}
        | set(dna_repair_proc.tracked_substrates)
        | {ftsz_proc.gtp_wid}
        | {cytokinesis_proc.gtp_wid}
    )
    allocation_step = KarrAllocationStep(
        {
            "consumer_processes": [
                (m1_proc.name, list(m1_proc.allocation_substrate_wids)),
                (m2_proc.name, list(m2_proc.allocation_substrate_wids)),
                (m3_proc.name, list(m3_proc.allocation_substrate_wids)),
                ("karr_macromolecular_complexation", list(d2_proc.substrate_wids)),
                ("karr_protein_decay_light", ["ATP", "H2O"]),
                (
                    ribasm_proc.name,
                    [ribasm_proc.substrate_wid_gtp, ribasm_proc.substrate_wid_h2o],
                ),
                (trna_proc.name, trna_consumed),
                (rna_proc.name, rna_proc_consumed),
                (rna_mod_proc.name, rna_mod_consumed),
                (pp1_proc.name, [pp1_proc.substrate_wids[pp1_proc.substrate_idx_water]]),
                (pp2_proc.name, pp2_consumed),
                (p_mod_proc.name, p_mod_consumed),
                (p_fold_proc.name, p_fold_consumed),
                (p_trans_proc.name, list(p_trans_proc.allocation_substrate_wids)),
                (rep_init_proc.name, [rep_init_proc.atp_wid, rep_init_proc.water_wid]),
                (rep_proc.name, [*rep_proc.dntp_wids, rep_proc.atp_wid]),
                (supercoil_proc.name, [supercoil_proc.atp_wid, supercoil_proc.h2o_wid]),
                (
                    condensation_proc.name,
                    [condensation_proc.atp_wid, condensation_proc.water_wid],
                ),
                (
                    segregation_proc.name,
                    [segregation_proc.gtp_wid, segregation_proc.h2o_wid],
                ),
                (dna_repair_proc.name, list(dna_repair_proc.tracked_substrates)),
                (ftsz_proc.name, [ftsz_proc.gtp_wid]),
                (cytokinesis_proc.name, [cytokinesis_proc.gtp_wid]),
            ],
            "substrate_wids": allocation_substrates,
        }
    )
    req_d2 = RequestCalculatorD2({"d2_real_proc": d2_proc})
    req_pd = RequestCalculatorPD({"pd_light_proc": decay_proc})
    req_ribasm = RequestCalculatorRibAsm({"ribasm_proc": ribasm_proc})
    req_trna = RequestCalculatorTRNA({"trna_proc": trna_proc})
    req_rna = RequestCalculatorRNAPathway(
        {
            "rna_processing_proc": rna_proc,
            "rna_modification_proc": rna_mod_proc,
        }
    )
    req_protein = RequestCalculatorProteinPathway(
        {
            "protein_processing_i_proc": pp1_proc,
            "protein_processing_ii_proc": pp2_proc,
            "protein_modification_proc": p_mod_proc,
            "protein_folding_proc": p_fold_proc,
            "protein_translocation_proc": p_trans_proc,
        }
    )
    req_metabolism = RequestCalculatorMetabolism(
        {
            "metabolism_proc": m1_proc,
            "karr_parity_mode": karr_parity_mode,
        }
    )
    req_transcription = RequestCalculatorTranscription({"transcription_proc": m2_proc})
    req_translation = RequestCalculatorTranslation({"translation_proc": m3_proc})
    req_protein_translocation = RequestCalculatorPTransloc(
        {"protein_translocation_proc": p_trans_proc}
    )

    rxn_ids = m1_model.rxn_wcm_ids_645
    m1_sub_ids = [str(wid) for wid in m1_model.raw["ids"]["substrate_wcm_585"]]
    rna_init = {
        g: float(m2_model.counts_mature[i, condition]) for i, g in enumerate(m2_model.gene_wcm_ids)
    }
    prot_init = {
        p: float(m3_model.counts_mature[i]) for i, p in enumerate(m3_model.protein_wcm_ids)
    }

    karr_initial_counts = _load_karr_initial_substrate_counts(m1_model)
    initial_substrates: dict[str, float] = {sid: 0.0 for sid in allocation_substrates}
    for sid in m1_sub_ids:
        initial_substrates[sid] = karr_initial_counts.get(sid, _M1_SUBSTRATE_DEFAULT)
    for wid, cnt in prot_init.items():
        if wid in initial_substrates:
            initial_substrates[wid] = max(initial_substrates[wid], cnt)
    for wid, cnt in rna_init.items():
        if wid in initial_substrates:
            initial_substrates[wid] = max(initial_substrates[wid], cnt)

    aminoacylated_init: dict[str, float] = {wid: 0.0 for wid in trna_proc.aminoacylated_rna_wids}
    for wid in trna_proc.free_rna_wids:
        total = max(0.0, float(rna_init.get(wid, 0.0)))
        free = total / 3.0
        charged = total - free
        rna_init[wid] = free
        if wid in aminoacylated_init:
            aminoacylated_init[wid] = charged
    rna_modified_init: dict[str, float] = {wid: 0.0 for wid in rna_mod_proc.modified_rna_wids}
    tx_rate_fold_init: dict[str, float] = {tu_wid: 1.0 for tu_wid in m2_proc.tu_wids}
    trna_gene_wids = set(trna_proc.free_rna_wids)
    for gidx, gene_wid in enumerate(m2_proc.gene_ids):
        if gene_wid in trna_gene_wids:
            tx_rate_fold_init[f"TU_{gidx + 1:03d}"] = 0.0

    # Track-A5 decision: keep non-fixture seeding as an explicit opt-out for
    # debugging/non-replay experiments, but default to fixture-aligned t=0 parity.
    if seed_from_fixture:
        fixture_monomers = _load_translation_fixture_monomers()
        n_fixture = int(fixture_monomers.size)
        n_model = len(m3_model.protein_wcm_ids)
        if n_fixture != n_model:
            raise ValueError(
                "Translation fixture/model monomer dimension mismatch: "
                f"fixture={n_fixture} model={n_model}"
            )
        protein_unprocessed_seed = {
            pid: float(fixture_monomers[idx]) for idx, pid in enumerate(m3_model.protein_wcm_ids)
        }
    else:
        protein_unprocessed_seed = {
            pid: float(prot_init.get(pid, 0.0)) for pid in m3_model.protein_wcm_ids
        }

    unprocessed_monomer_wids = set(pp1_proc.unprocessed_monomer_wids) | set(
        pp2_proc.unprocessed_monomer_wids
    )
    if seed_from_fixture:
        # Ensure every translation monomer is explicitly initialized so ports-schema
        # defaults cannot reintroduce non-zero counts_mature values.
        unprocessed_monomer_wids |= set(m3_model.protein_wcm_ids)
    protein_unprocessed_init = {
        wid: float(protein_unprocessed_seed.get(wid, 0.0))
        for wid in sorted(unprocessed_monomer_wids)
    }
    protein_unfolded_init = {
        wid: float(prot_init.get(wid, 0.0)) for wid in p_fold_proc.unfolded_monomer_wids
    }
    protein_unmodified_init = {
        wid: float(prot_init.get(wid, 0.0)) for wid in p_mod_proc.unmodified_monomer_wids
    }
    protein_processed_init = {wid: 0.0 for wid in pp2_proc.processed_monomer_wids}
    protein_signal_seq_init = {wid: 0.0 for wid in pp2_proc.signal_sequence_monomer_wids}
    protein_modified_init = {wid: 0.0 for wid in p_mod_proc.modified_monomer_wids}
    protein_enzyme_init = {
        wid: float(prot_init.get(wid, 0.0))
        for wid in sorted(set(pp1_proc.enzyme_wids) | set(pp2_proc.enzyme_wids))
    }
    protein_enzyme_init["MG_106_DIMER"] = 22.0  # from PP1_flat.mat enzymes column
    protein_enzyme_init["MG_172_MONOMER"] = 38.0  # from PP1_flat.mat enzymes column
    protein_location_init = {wid: "cytoplasm" for wid in p_trans_proc.translocatable_wids}
    protein_activity_init = {wid: 0 for wid in p_activation_proc.regulated_protein_wids}

    complex_counts = {
        "RNA_POLYMERASE": float(m2_mechanism_inputs.n_active_rnap),
        "RIBOSOME_70S": float(m3_mechanism_inputs.n_active_ribosomes),
    }
    for wid in ribasm_proc.complex_wids:
        complex_counts.setdefault(wid, 0.0)

    m1_topo = {
        "metabolic_reaction": ("metabolic_reaction",),
        "substrates": ("substrates",),
        "substrates_allocated": ("substrates_allocated",),
    }
    if dynamic_bounds:
        m1_topo["m1_dynamic_diagnostics"] = ("m1_dynamic_diagnostics",)
        m1_topo["m1_pools"] = ("m1_pools",)

    topology: dict[str, dict[str, tuple[str, ...]]] = {
        "karr_metabolism": m1_topo,
        "karr_transcription_v3": {
            "rna": ("rna",),
            "substrates": ("substrates",),
            "complex": ("complex",),
            "substrates_allocated": ("substrates_allocated",),
            "tx_rate_fold_change": ("tx_rate_fold_change",),
        },
        "karr_translation_v3": {
            "protein": ("protein",),
            "substrates": ("substrates",),
            "complex": ("complex",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_macromolecular_complexation": {
            "substrates": ("substrates",),
            "complex": ("complex",),
            "requests": ("_internal_requests_d2",),
            "substrates_allocated": ("_internal_substrates_allocated_d2",),
        },
        "karr_protein_decay_light": {
            "complex": ("complex",),
            "substrates": ("substrates",),
            "protein": ("protein",),
            "rna": ("rna",),
            "requests": ("_internal_requests_pd",),
            "substrates_allocated": ("_internal_substrates_allocated_pd",),
        },
        "karr_trna_aminoacylation": {
            "substrates": ("substrates",),
            "rna": ("rna",),
            "protein": ("protein",),
            "requests": ("_internal_requests_trna",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_ribosome_assembly": {
            "substrates": ("substrates",),
            "rna": ("rna",),
            "protein": ("protein",),
            "complex": ("complex",),
            "requests": ("_internal_requests_ribasm",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_transcriptional_regulation": {
            "protein": ("protein",),
            "tf_binding": ("tf_binding",),
            "tx_rate_fold_change": ("tx_rate_fold_change",),
        },
        "karr_rna_processing": {
            "substrates": ("substrates",),
            "rna": ("rna",),
            "protein": ("protein",),
            "requests": ("_internal_requests_rna_proc",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_rna_modification": {
            "substrates": ("substrates",),
            "rna": ("rna",),
            "protein": ("protein",),
            "complex": ("complex",),
            "requests": ("_internal_requests_rna_mod",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_protein_processing_i": {
            "substrates": ("substrates",),
            "protein": ("protein",),
            "requests": ("_internal_requests_pp1",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_protein_processing_ii": {
            "substrates": ("substrates",),
            "protein": ("protein",),
            "requests": ("_internal_requests_pp2",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_protein_modification": {
            "substrates": ("substrates",),
            "protein": ("protein",),
            "requests": ("_internal_requests_pmod",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_protein_folding": {
            "substrates": ("substrates",),
            "protein": ("protein",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_protein_translocation": {
            "substrates": ("substrates",),
            "protein": ("protein",),
            "requests": ("_internal_requests_ptrans",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_protein_activation": {
            "substrates": ("activation_substrates",),
            "stimuli": ("stimuli",),
            "protein": ("protein",),
        },
        "karr_replication_initiation": {
            "chromosome": ("chromosome",),
            "protein": ("protein",),
            "substrates": ("substrates",),
            "requests": ("requests",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_replication": {
            "chromosome": ("chromosome",),
            "substrates": ("substrates",),
            "requests": ("requests",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_dna_supercoiling": {
            "chromosome": ("chromosome",),
            "protein": ("protein",),
            "substrates": ("substrates",),
            "requests": ("requests",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_chromosome_condensation": {
            "chromosome": ("chromosome",),
            "substrates": ("substrates",),
            "requests": ("requests",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_chromosome_segregation": {
            "chromosome": ("chromosome",),
            "protein": ("protein",),
            "substrates": ("substrates",),
            "requests": ("requests",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_dna_damage": {
            "chromosome": ("chromosome",),
        },
        "karr_dna_repair": {
            "chromosome": ("chromosome",),
            "protein": ("protein",),
            "substrates": ("substrates",),
            "requests": ("requests",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_ftsz_polymerization": {
            "cell": ("cell",),
            "substrates": ("substrates",),
            "requests": ("requests",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_cytokinesis": {
            "cell": ("cell",),
            "chromosome": ("chromosome",),
            "substrates": ("substrates",),
            "requests": ("requests",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "karr_terminal_organelle_assembly": {
            "protein": ("protein",),
            "cell": ("cell",),
        },
        "request_calculator_d2": {
            "complex": ("complex",),
            "requests": ("requests",),
        },
        "request_calculator_pd": {
            "complex": ("complex",),
            "requests": ("requests",),
        },
        "request_calculator_ribasm": {
            "substrates": ("substrates",),
            "rna": ("rna",),
            "protein": ("protein",),
            "requests": ("requests",),
        },
        "request_calculator_trna": {
            "substrates": ("substrates",),
            "rna": ("rna",),
            "requests": ("requests",),
        },
        "request_calculator_rna_pathway": {
            "substrates": ("substrates",),
            "rna": ("rna",),
            "requests": ("requests",),
        },
        "request_calculator_protein_pathway": {
            "substrates": ("substrates",),
            "protein": ("protein",),
            "requests": ("requests",),
        },
        "request_calculator_protein_translocation": {
            "substrates": ("substrates",),
            "protein": ("protein",),
            "requests": ("requests",),
        },
        "request_calculator_metabolism": {
            "requests": ("requests",),
        },
        "request_calculator_transcription": {
            "complex": ("complex",),
            "requests": ("requests",),
        },
        "request_calculator_translation": {
            "complex": ("complex",),
            "requests": ("requests",),
        },
        "karr_allocation_step": {
            "substrates": ("substrates",),
            "requests": ("requests",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "cell_cycle_coordinator": {
            "chromosome": ("chromosome",),
            "cell": ("cell",),
        },
    }

    initial_state: dict[str, Any] = {
        "metabolic_reaction": {
            "fluxs": {rid: float(m1_model.fluxs_stored[i]) for i, rid in enumerate(rxn_ids)},
            "growth_per_s": float(m1_model.stored_runtime["growth_per_s"]),
            "growth_per_h": float(m1_model.stored_runtime["growth_per_h"]),
        },
        "substrates": initial_substrates,
        "rna": {
            "counts": rna_init,
            "aminoacylated_counts": aminoacylated_init,
            "modified_counts": rna_modified_init,
        },
        "protein": {
            "counts": prot_init,
            "unprocessed_counts": protein_unprocessed_init,
            "unfolded_counts": protein_unfolded_init,
            "unmodified_counts": protein_unmodified_init,
            "processed_counts": protein_processed_init,
            "signal_sequence_counts": protein_signal_seq_init,
            "modified_counts": protein_modified_init,
            "enzyme_counts": protein_enzyme_init,
            "location": protein_location_init,
            "activity": protein_activity_init,
        },
        "complex": {"counts": complex_counts},
        "stimuli": {wid: 0.0 for wid in p_activation_proc.stimuli_wids},
        "activation_substrates": {
            wid: float(initial_substrates.get(wid, 0.0)) for wid in p_activation_proc.substrate_wids
        },
        "tx_rate_fold_change": tx_rate_fold_init,
        "chromosome": {
            "replication_state": "idle",
            "fork_position_bp": {"left": 0.0, "right": 0.0},
            "fork_positions": {"left": 0.0, "right": 0.0},
            "events": {"replication_complete": 0.0},
            "supercoil_density": float(supercoil_proc.equilibrium_sigma),
            "supercoiled": True,
            "smc_bound_count": float(condensation_proc.trace_anchor_bound),
            "condensation_level": float(condensation_proc.default_condensation_level),
            "forks_passing": False,
            "segregation_progress": 0.0,
            "segregation_complete": False,
            "daughter_pole_positions": {"left": 0.0, "right": 0.0},
            "cell_cycle_event": "none",
            "damage_sites": [],
            "replication_stall_flag": 0.0,
            "repair_count": 0.0,
            "repair_count_by_pathway": {
                "ber": 0.0,
                "ner": 0.0,
                "hr": 0.0,
                "nhej_like": 0.0,
            },
        },
        "cell": {
            "ftsz_ring_count": float(ftsz_proc.initial_ring_count),
            "ftsz_ring_complete": bool(
                ftsz_proc.initial_ring_count
                >= int(ftsz_proc.parameters["ring_complete_threshold"])
            ),
            "cycle_phase": "idle",
            "gate_allow_cytokinesis": False,
            "division_progress": 0.0,
            "division_complete": False,
            "division_event_count": 0.0,
            "terminal_organelle_count": 0.0,
            "terminal_organelle_components_assembled": {
                wid: 0.0 for wid in terminal_organelle_proc.component_wids
            },
        },
    }
    if dynamic_bounds:
        initial_state["m1_dynamic_diagnostics"] = {k: 0.0 for k in m1_proc._diagnostics_schema()}
        from opencell.vivarium.karr_metabolism import _CYTOSOL_COMPARTMENT_0

        initial_state["m1_pools"] = {
            sid: float(m1_proc._sub_state[idx, _CYTOSOL_COMPARTMENT_0])
            for sid, idx in m1_proc._demand_idx_pairs
        }

    engine = Engine(
        processes={
            "karr_metabolism": m1_proc,
            "karr_transcription_v3": m2_proc,
            "karr_translation_v3": m3_proc,
            "karr_macromolecular_complexation": d2_proc,
            "karr_protein_decay_light": decay_proc,
            "karr_trna_aminoacylation": trna_proc,
            "karr_ribosome_assembly": ribasm_proc,
            "karr_transcriptional_regulation": tx_reg_proc,
            "karr_rna_processing": rna_proc,
            "karr_rna_modification": rna_mod_proc,
            "karr_protein_processing_i": pp1_proc,
            "karr_protein_processing_ii": pp2_proc,
            "karr_protein_modification": p_mod_proc,
            "karr_protein_folding": p_fold_proc,
            "karr_protein_translocation": p_trans_proc,
            "karr_protein_activation": p_activation_proc,
            "karr_replication_initiation": rep_init_proc,
            "karr_replication": rep_proc,
            "karr_dna_supercoiling": supercoil_proc,
            "karr_chromosome_condensation": condensation_proc,
            "karr_chromosome_segregation": segregation_proc,
            "karr_dna_damage": dna_damage_proc,
            "karr_dna_repair": dna_repair_proc,
            "karr_ftsz_polymerization": ftsz_proc,
            "karr_cytokinesis": cytokinesis_proc,
            "karr_terminal_organelle_assembly": terminal_organelle_proc,
        },
        steps={
            "request_calculator_d2": req_d2,
            "request_calculator_pd": req_pd,
            "request_calculator_ribasm": req_ribasm,
            "request_calculator_trna": req_trna,
            "request_calculator_rna_pathway": req_rna,
            "request_calculator_protein_pathway": req_protein,
            "request_calculator_protein_translocation": req_protein_translocation,
            "request_calculator_metabolism": req_metabolism,
            "request_calculator_transcription": req_transcription,
            "request_calculator_translation": req_translation,
            "karr_allocation_step": allocation_step,
            "cell_cycle_coordinator": coordinator_step,
        },
        flow={
            "request_calculator_d2": [],
            "request_calculator_pd": [],
            "request_calculator_ribasm": [],
            "request_calculator_trna": [],
            "request_calculator_rna_pathway": [],
            "request_calculator_protein_pathway": [],
            "request_calculator_protein_translocation": [],
            "request_calculator_metabolism": [],
            "request_calculator_transcription": [],
            "request_calculator_translation": [],
            "karr_allocation_step": [
                ("request_calculator_d2",),
                ("request_calculator_pd",),
                ("request_calculator_ribasm",),
                ("request_calculator_trna",),
                ("request_calculator_rna_pathway",),
                ("request_calculator_protein_pathway",),
                ("request_calculator_protein_translocation",),
                ("request_calculator_metabolism",),
                ("request_calculator_transcription",),
                ("request_calculator_translation",),
            ],
            "cell_cycle_coordinator": [("karr_allocation_step",)],
        },
        topology=topology,
        initial_state=initial_state,
        emit_step=emit_step_s or time_step_s,
    )
    return engine



def build_karr_chassis_v6(
    m1_model: km.KarrMetabolismModel | None = None,
    m2_model: tx.KarrTranscriptionModel | None = None,
    m3_model: tl.KarrTranslationModel | None = None,
    *,
    m2_mechanism_inputs: tx_v2.MechanismInputs | None = None,
    m3_mechanism_inputs: tl_v2.RibosomeMechanismInputs | None = None,
    time_step_s: float = 1.0,
    emit_step_s: float | None = None,
    condition: int = 1,
    dynamic_bounds: bool = True,
    enable_pool_replenishment: bool = False,
    host_adhesion_gates_division: bool = False,
    seed_from_fixture: bool = True,
    karr_parity_mode: bool = True,
) -> Any:
    """Build the Phase-D v6 composite (v5 + RNA decay + HostInteraction).

    Runtime-identity invariant: TX/TL keys in the returned process map must
    point to the canonical v3 runtime classes (`KarrTranscriptionV3Process`
    and `KarrTranslationV3Process`) under canonical keys
    (`karr_transcription`, `karr_translation`).
    """
    del host_adhesion_gates_division

    from vivarium.core.composer import Composite

    base_engine = build_karr_chassis_v5(
        m1_model=m1_model,
        m2_model=m2_model,
        m3_model=m3_model,
        m2_mechanism_inputs=m2_mechanism_inputs,
        m3_mechanism_inputs=m3_mechanism_inputs,
        time_step_s=time_step_s,
        emit_step_s=emit_step_s,
        condition=condition,
        dynamic_bounds=dynamic_bounds,
        enable_pool_replenishment=enable_pool_replenishment,
        seed_from_fixture=seed_from_fixture,
        karr_parity_mode=karr_parity_mode,
    )

    processes = dict(base_engine.processes)
    steps = dict(base_engine.steps)
    flow = {key: list(deps) for key, deps in base_engine.flow.items()}
    topology: dict[str, dict[str, tuple[str, ...]] | tuple[str, ...]] = {}
    for proc_key, proc_topology in base_engine.topology.items():
        if isinstance(proc_topology, dict):
            topology[proc_key] = dict(proc_topology)
        else:
            topology[proc_key] = proc_topology
    initial_state = deepcopy(base_engine.initial_state)

    # Canonical process-key map expected by chassis_v6 integration gates.
    # Runtime-identity guardrail below enforces that remapped keys still point
    # to canonical v3 classes rather than legacy wrapper classes.
    for old_key, new_key in (
        ("karr_transcription_v3", "karr_transcription"),
        ("karr_translation_v3", "karr_translation"),
    ):
        processes[new_key] = processes.pop(old_key)
        processes[new_key].name = new_key
        topology[new_key] = topology.pop(old_key)
        # Bug 1 fix: do NOT mark as Step. Step marking causes timestep=0 in
        # Vivarium's engine (_calculate_update(path, step, 0)), silencing
        # biology. TX/TL must remain Processes with real dt.

    # Promote coordinator from step inventory to process inventory so it is
    # visible in the process-key scorecard while preserving existing class logic.
    coordinator_step = steps.pop("cell_cycle_coordinator")
    processes["karr_cell_cycle_coordinator"] = coordinator_step
    topology["karr_cell_cycle_coordinator"] = topology.pop("cell_cycle_coordinator")
    flow.pop("cell_cycle_coordinator", None)

    rna_decay_proc = RnaDecayLightProcess({"time_step": time_step_s})
    processes["karr_rna_decay"] = rna_decay_proc
    topology["karr_rna_decay"] = {
        "rna": ("rna",),
        "substrates": ("substrates",),
        "requests": ("requests",),
        "substrates_allocated": ("substrates_allocated",),
    }
    host_interaction_proc = KarrHostInteractionProcess({"time_step": time_step_s})
    processes["karr_host_interaction"] = host_interaction_proc
    topology["karr_host_interaction"] = {
        "cell": ("cell",),
        "protein": ("protein",),
    }

    allocation_step = steps["karr_allocation_step"]
    consumer_map: dict[str, list[str]] = {
        str(proc_name): [str(wid) for wid in wids]
        for proc_name, wids in allocation_step.parameters["consumer_processes"]
    }
    for old_key, new_key in (
        ("karr_transcription_v3", "karr_transcription"),
        ("karr_translation_v3", "karr_translation"),
    ):
        if old_key in consumer_map:
            existing = consumer_map.get(new_key, [])
            consumer_map[new_key] = sorted(set(existing) | set(consumer_map.pop(old_key)))
    existing_rna_wids = consumer_map.get(rna_decay_proc.name, [])
    consumer_map[rna_decay_proc.name] = sorted(set(existing_rna_wids) | {"H2O"})
    consumer_processes = [(proc_name, wids) for proc_name, wids in consumer_map.items()]
    substrate_wids = sorted(set(allocation_step.parameters["substrate_wids"]) | {"H2O"})
    steps["karr_allocation_step"] = KarrAllocationStep(
        {
            "consumer_processes": consumer_processes,
            "substrate_wids": substrate_wids,
        }
    )
    steps["karr_observability_step"] = KarrObservabilityStep(
        {
            "m1_model": processes["karr_metabolism"].model,
            "m2_model": processes["karr_transcription"].kinetics_model,
            "m3_model": processes["karr_translation"].kinetics_model,
            "genome_half_bp": float(processes["karr_replication"].terc_position_bp),
        }
    )
    topology["karr_observability_step"] = {
        "rna": ("rna",),
        "protein": ("protein",),
        "chromosome": ("chromosome",),
        "cell": ("cell",),
        "substrates": ("substrates",),
        "phenotype_observables": ("phenotype_observables",),
    }
    flow["karr_observability_step"] = [("karr_allocation_step",)]

    chromosome_state = initial_state.setdefault("chromosome", {})
    chromosome_state.pop("damage_sites", None)
    chromosome_state.setdefault("damage_events_cumulative", [])
    chromosome_state.setdefault("repair_events_cumulative", [])
    assert_chassis_runtime_identity(processes)

    return Composite(
        processes=processes,
        steps=steps,
        flow=flow,
        topology=topology,
        state=initial_state,
    )

__all__ = [
    "CHASSIS_V6_EXPECTED_PROCESS_KEYS",
    "assert_chassis_runtime_identity",
    "build_karr_chassis_v6",
    "build_karr_chassis_v5",
    "build_karr_chassis_v4",
    "build_karr_chassis_v3",
    "build_karr_chassis_v2",
    "build_karr_m1_m2_engine",
    "build_karr_m1_m2_m3_engine",
    "compute_baseline_demand_per_s",
]
