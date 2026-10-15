"""Vivarium Step helpers that compute per-tick allocation requests."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from vivarium.core.process import Step

from opencell.m1.compartmented import AVOGADRO, SECONDS_PER_HOUR
from opencell.m3 import translation_v2 as tl_v2


def _consumed_wids_from_stoich(substrate_wids: list[str], stoich: np.ndarray) -> list[str]:
    consumed_idx = np.flatnonzero(np.any(np.asarray(stoich, dtype=np.int64) < 0, axis=1))
    return [substrate_wids[int(idx)] for idx in consumed_idx]


def _require_process_dependencies(
    owner: str, parameters: dict[str, Any], expected: dict[str, type]
) -> None:
    """Fail closed at construction unless every named parameter is the exact process family."""
    problems: list[str] = []
    for parameter, expected_cls in expected.items():
        value = parameters.get(parameter)
        if value is None:
            problems.append(f"{parameter} is missing (expected {expected_cls.__name__})")
        elif not isinstance(value, expected_cls):
            problems.append(
                f"{parameter} must be a {expected_cls.__name__}, got {type(value).__name__}"
            )
    if problems:
        raise ValueError(f"{owner} requires explicit process dependencies: " + "; ".join(problems))


def _request_from_available(
    substrate_state: dict[str, Any],
    target_wids: list[str],
    *,
    active: bool,
) -> dict[str, float]:
    if not active:
        return {wid: 0.0 for wid in target_wids}
    return {wid: max(0.0, float(substrate_state.get(wid, 0.0))) for wid in target_wids}


class _SafeDtMixin:
    def _safe_dt(self, timestep: float, eps: float | None = None) -> float:
        """Return a strictly-positive effective dt for substrate-demand scaling.

        Per RC-shared PR (2026-05-26): Vivarium Step.timestep can legitimately
        arrive as 0.0 between composite scheduling cycles. Naive `* timestep`
        scaling then collapses substrate demand to 0 and suppresses requests.

        Strategy: prefer the wrapped process's configured `time_step` when
        available; otherwise floor the incoming timestep at `eps` (default 1.0 s).
        """

        configured = getattr(getattr(self, "_proc", None), "parameters", {}).get("time_step")
        if configured is not None:
            configured_dt = float(configured)
            if configured_dt > 0.0:
                return configured_dt
        floor = 1.0 if eps is None else float(eps)
        return max(floor, float(timestep))


class RequestCalculatorD2(Step):
    """Emit D.2-real metabolite requests.

    Karr D.2 (MacromolecularComplexation) requests no metabolites in
    ``calcResourceRequirements_Current``, so this step writes zeros.
    """

    name = "request_calculator_d2"
    defaults: dict[str, Any] = {"d2_real_proc": None}

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        d2_real_proc = self.parameters.get("d2_real_proc")
        if d2_real_proc is None:
            raise ValueError("RequestCalculatorD2 requires parameter: d2_real_proc")
        self._d2_real_proc = d2_real_proc
        self._zero_requests = {wid: 0.0 for wid in self._d2_real_proc.substrate_wids}

    def ports_schema(self) -> dict[str, Any]:
        return {
            "complex": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self._d2_real_proc.complex_wids
                }
            },
            "requests": {
                "karr_macromolecular_complexation": {
                    wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                    for wid in self._d2_real_proc.substrate_wids
                }
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del timestep, states
        return {"requests": {"karr_macromolecular_complexation": dict(self._zero_requests)}}


class RequestCalculatorPD(_SafeDtMixin, Step):
    """Estimate ProteinDecay-light ATP/H2O requirements for this tick."""

    name = "request_calculator_pd"
    defaults: dict[str, Any] = {"pd_light_proc": None}

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        pd_light_proc = self.parameters.get("pd_light_proc")
        if pd_light_proc is None:
            raise ValueError("RequestCalculatorPD requires parameter: pd_light_proc")
        self._pd_light_proc = pd_light_proc
        self._proc = pd_light_proc

    def ports_schema(self) -> dict[str, Any]:
        return {
            "complex": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self._pd_light_proc.complex_wids
                }
            },
            "requests": {
                "karr_protein_decay_light": {
                    "ATP": {"_default": 0.0, "_updater": "set", "_emit": False},
                    "H2O": {"_default": 0.0, "_updater": "set", "_emit": False},
                }
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        if not bool(self._pd_light_proc.parameters["consume_atp_h2o"]):
            return {"requests": {"karr_protein_decay_light": {"ATP": 0.0, "H2O": 0.0}}}

        complex_counts = np.asarray(
            [
                float(states["complex"]["counts"].get(wid, 0.0))
                for wid in self._pd_light_proc.complex_wids
            ],
            dtype=np.float64,
        )
        rates = self._pd_light_proc._complex_rates_per_s()
        expected_decays = rates * complex_counts * self._safe_dt(timestep)

        atp_req = float(
            abs(
                self._pd_light_proc.complex_decay_reactions[
                    self._pd_light_proc.substrate_index_atp, :
                ]
                @ expected_decays
            )
        )
        h2o_req = float(
            abs(
                self._pd_light_proc.complex_decay_reactions[
                    self._pd_light_proc.substrate_index_water, :
                ]
                @ expected_decays
            )
        )

        return {
            "requests": {
                "karr_protein_decay_light": {
                    "ATP": atp_req,
                    "H2O": h2o_req,
                }
            }
        }


class RequestCalculatorRibAsm(Step):
    """Compute RibosomeAssembly GTP/H2O request from current subunit state."""

    name = "request_calculator_ribasm"
    defaults: dict[str, Any] = {"ribasm_proc": None}

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        from opencell.vivarium.karr_ribosome_assembly import KarrRibosomeAssemblyProcess

        _require_process_dependencies(
            type(self).__name__,
            self.parameters,
            {"ribasm_proc": KarrRibosomeAssemblyProcess},
        )
        self._ribasm_proc = self.parameters["ribasm_proc"]

    def ports_schema(self) -> dict[str, Any]:
        return {
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self._ribasm_proc.substrate_wids
            },
            "rna": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self._ribasm_proc.rna_subunit_wids
                }
            },
            "protein": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self._ribasm_proc.protein_state_wids
                }
            },
            "requests": {
                self._ribasm_proc.name: {
                    self._ribasm_proc.substrate_wid_gtp: {
                        "_default": 0.0,
                        "_updater": "set",
                        "_emit": False,
                    },
                    self._ribasm_proc.substrate_wid_h2o: {
                        "_default": 0.0,
                        "_updater": "set",
                        "_emit": False,
                    },
                }
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del timestep
        formable = self._ribasm_proc.estimate_formable_without_substrates(states)
        hydrolysis_events = sum(
            int(formable.get(particle_wid, 0))
            * int(self._ribasm_proc.n_gtpases_per_particle[particle_wid])
            for particle_wid in self._ribasm_proc.complex_wids
        )
        request = float(max(0, hydrolysis_events))
        return {
            "requests": {
                self._ribasm_proc.name: {
                    self._ribasm_proc.substrate_wid_gtp: request,
                    self._ribasm_proc.substrate_wid_h2o: request,
                }
            }
        }


class RequestCalculatorTRNA(Step):
    """Compute allocation request for tRNA aminoacylation metabolites."""

    name = "request_calculator_trna"
    defaults: dict[str, Any] = {"trna_proc": None}

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        trna_proc = self.parameters.get("trna_proc")
        if trna_proc is None:
            raise ValueError("RequestCalculatorTRNA requires parameter: trna_proc")
        self._trna_proc = trna_proc
        self._consumed_substrate_wids = _consumed_wids_from_stoich(
            self._trna_proc.substrate_wids,
            self._trna_proc.reaction_stoich,
        )

    def ports_schema(self) -> dict[str, Any]:
        return {
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self._trna_proc.substrate_wids
            },
            "rna": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self._trna_proc.free_rna_wids
                }
            },
            "requests": {
                self._trna_proc.name: {
                    wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                    for wid in self._trna_proc.substrate_wids
                }
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del timestep
        free_total = sum(
            max(0.0, float(states.get("rna", {}).get("counts", {}).get(wid, 0.0)))
            for wid in self._trna_proc.free_rna_wids
        )
        substrate_state = states.get("substrates", {})
        requests = {wid: 0.0 for wid in self._trna_proc.substrate_wids}
        active = free_total > 0.0
        if active:
            for wid in self._consumed_substrate_wids:
                avail = max(0.0, float(substrate_state.get(wid, 0.0)))
                if wid == "ATP":
                    # Karr-parity: scale request with availability (no floor).
                    requests[wid] = avail * 25.0
                else:
                    requests[wid] = avail
        return {"requests": {self._trna_proc.name: requests}}


class RequestCalculatorRNAPathway(Step):
    """Compute shared requests for RNAProcessing + RNAModification."""

    name = "request_calculator_rna_pathway"
    defaults: dict[str, Any] = {"rna_processing_proc": None, "rna_modification_proc": None}

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._rp_proc = self.parameters.get("rna_processing_proc")
        self._rm_proc = self.parameters.get("rna_modification_proc")
        if self._rp_proc is None or self._rm_proc is None:
            raise ValueError(
                "RequestCalculatorRNAPathway requires rna_processing_proc and rna_modification_proc"
            )

    def ports_schema(self) -> dict[str, Any]:
        return {
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in sorted(
                    set(self._rp_proc.substrate_wids) | set(self._rm_proc.substrate_wids)
                )
            },
            "rna": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in sorted(
                        set(self._rp_proc.rna_wids) | set(self._rm_proc.processed_rna_wids)
                    )
                }
            },
            "protein": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in sorted(
                        set(self._rp_proc.monomer_enzyme_wids)
                        | set(self._rm_proc.monomer_enzyme_wids)
                    )
                }
            },
            "complex": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in sorted(
                        set(self._rp_proc.complex_enzyme_wids)
                        | set(self._rm_proc.complex_enzyme_wids)
                    )
                }
            },
            "requests": {
                self._rp_proc.name: {
                    wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                    for wid in self._rp_proc.substrate_wids
                },
                self._rm_proc.name: {
                    wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                    for wid in self._rm_proc.substrate_wids
                },
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del timestep
        rp_request = self._rp_proc.calculate_request(states)
        rm_request = self._rm_proc.calculate_request(states)
        return {
            "requests": {
                self._rp_proc.name: rp_request,
                self._rm_proc.name: rm_request,
            }
        }


class RequestCalculatorProteinPathway(Step):
    """Compute shared requests for protein maturation pathway processes."""

    name = "request_calculator_protein_pathway"
    defaults: dict[str, Any] = {
        "protein_processing_i_proc": None,
        "protein_processing_ii_proc": None,
        "protein_modification_proc": None,
        "protein_folding_proc": None,
        "protein_translocation_proc": None,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        from opencell.vivarium.karr_protein_folding import KarrProteinFoldingProcess
        from opencell.vivarium.karr_protein_modification import (
            KarrProteinModificationProcess,
        )
        from opencell.vivarium.karr_protein_processing_i import (
            KarrProteinProcessingIProcess,
        )
        from opencell.vivarium.karr_protein_processing_ii import (
            KarrProteinProcessingIIProcess,
        )
        from opencell.vivarium.karr_protein_translocation import (
            KarrProteinTranslocationProcess,
        )

        _require_process_dependencies(
            type(self).__name__,
            self.parameters,
            {
                "protein_processing_i_proc": KarrProteinProcessingIProcess,
                "protein_processing_ii_proc": KarrProteinProcessingIIProcess,
                "protein_modification_proc": KarrProteinModificationProcess,
                "protein_folding_proc": KarrProteinFoldingProcess,
                "protein_translocation_proc": KarrProteinTranslocationProcess,
            },
        )
        self._pp1_proc = self.parameters["protein_processing_i_proc"]
        self._pp2_proc = self.parameters["protein_processing_ii_proc"]
        self._pm_proc = self.parameters["protein_modification_proc"]
        self._pf_proc = self.parameters["protein_folding_proc"]
        self._pt_proc = self.parameters["protein_translocation_proc"]

        self._pp2_consumed = _consumed_wids_from_stoich(
            self._pp2_proc.substrate_wids, self._pp2_proc.reaction_stoich
        )
        self._pm_consumed = _consumed_wids_from_stoich(
            self._pm_proc.substrate_wids, self._pm_proc.reaction_stoich
        )

    def ports_schema(self) -> dict[str, Any]:
        from opencell.vivarium.protein_state import MIGRATED_WIDS

        all_substrate_wids = sorted(
            set(self._pp1_proc.substrate_wids)
            | set(self._pp2_proc.substrate_wids)
            | set(self._pm_proc.substrate_wids)
            | set(self._pf_proc.substrate_wids)
            | set(self._pt_proc.request_wids)
        )
        return {
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in all_substrate_wids
            },
            "protein": {
                # Filtered by MIGRATED_WIDS: two of PP2's enzyme WIDs
                # (signal peptidase / DAG transferase inputs) happen to also
                # be migrated translocatable monomers; declaring an
                # "accumulate" updater for them here would conflict with
                # the authority's rejecting updater on the same leaf (a
                # genuine schema-merge warning, not cosmetic -- it would let
                # a future writer attach the wrong updater and silently
                # corrupt the derived flat projection). This class's own
                # `next_update` never reads `protein.counts` for enzyme
                # values, so the filter changes no computed value.
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in sorted(
                        set(self._pp1_proc.enzyme_wids)
                        | set(self._pp2_proc.enzyme_wids)
                        | set(self._pm_proc.enzyme_wids)
                        | set(self._pf_proc.enzyme_wids)
                        | set(self._pt_proc.protein_count_wids)
                    )
                    if wid not in MIGRATED_WIDS
                },
                # Design D4: the PT-specific `location` declaration (the
                # Stage-1 leak frozen-manifest C3 checks for) is deleted
                # outright -- `protein.location` has no Karr analogue and no
                # process declares it anywhere after Stage 2. `unprocessed_counts`
                # is pp1/pp2's own nascent-queue surface and is filtered by
                # `MIGRATED_WIDS` to match their own `ports_schema()` exactly
                # (every translocatable WID is migrated, so its nascent pool
                # lives at the compartment authority, not this legacy branch).
                "unprocessed_counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in sorted(
                        set(self._pp1_proc.unprocessed_monomer_wids)
                        | set(self._pp2_proc.unprocessed_monomer_wids)
                    )
                    if wid not in MIGRATED_WIDS
                },
                # Design D1/C6: filtered the same way, even though this
                # class's manifest entry is only checked on
                # `unprocessed_counts`/`location` -- C6 walks the REALIZED
                # store after a 100-tick chassis run, and an unfiltered
                # schema declaration here would resurrect a migrated WID's
                # leaf via mere default-value presence, independent of
                # whether this Step's `next_update` ever writes a nonzero
                # delta to it.
                "processed_counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self._pp2_proc.processed_monomer_wids
                    if wid not in MIGRATED_WIDS
                },
                "unfolded_counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self._pf_proc.unfolded_monomer_wids
                    if wid not in MIGRATED_WIDS
                },
                "unmodified_counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self._pm_proc.unmodified_monomer_wids
                    if wid not in MIGRATED_WIDS
                },
            },
            "requests": {
                self._pp1_proc.name: {
                    wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                    for wid in self._pp1_proc.substrate_wids
                },
                self._pp2_proc.name: {
                    wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                    for wid in self._pp2_proc.substrate_wids
                },
                self._pm_proc.name: {
                    wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                    for wid in self._pm_proc.substrate_wids
                },
                self._pf_proc.name: {
                    wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                    for wid in self._pf_proc.substrate_wids
                },
                self._pt_proc.name: {
                    wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                    for wid in self._pt_proc.request_wids
                },
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del timestep
        substrate_state = states.get("substrates", {})
        protein_state = states.get("protein", {})
        unprocessed_state = protein_state.get("unprocessed_counts", {})
        processed_state = protein_state.get("processed_counts", {})
        unfolded_state = protein_state.get("unfolded_counts", {})
        unmodified_state = protein_state.get("unmodified_counts", {})

        pp1_active = any(
            float(unprocessed_state.get(wid, 0.0)) > 0.0
            for wid in self._pp1_proc.unprocessed_monomer_wids
        )
        pp2_active = any(
            float(processed_state.get(wid, 0.0)) > 0.0 for wid in self._pp2_proc.lipoprotein_wids
        )
        pm_active = any(
            float(unmodified_state.get(wid, 0.0)) > 0.0
            for wid in self._pm_proc.unmodified_monomer_wids
        )
        pf_active = any(
            float(unfolded_state.get(wid, 0.0)) > 0.0 for wid in self._pf_proc.unfolded_monomer_wids
        )

        pp1_req = {wid: 0.0 for wid in self._pp1_proc.substrate_wids}
        pp1_req[self._pp1_proc.substrate_wids[self._pp1_proc.substrate_idx_water]] = (
            max(
                0.0,
                float(
                    substrate_state.get(
                        self._pp1_proc.substrate_wids[self._pp1_proc.substrate_idx_water], 0.0
                    )
                ),
            )
            if pp1_active
            else 0.0
        )

        pp2_req = {wid: 0.0 for wid in self._pp2_proc.substrate_wids}
        pp2_req.update(
            _request_from_available(substrate_state, self._pp2_consumed, active=pp2_active)
        )

        pm_req = {wid: 0.0 for wid in self._pm_proc.substrate_wids}
        pm_req.update(_request_from_available(substrate_state, self._pm_consumed, active=pm_active))

        pf_req = {
            wid: (
                max(0.0, float(substrate_state.get(wid, 0.0)))
                if pf_active
                and (
                    wid == self._pf_proc.substrate_wids[self._pf_proc.substrate_idx_atp]
                    or wid == self._pf_proc.substrate_wids[self._pf_proc.substrate_idx_fe2]
                    or wid == self._pf_proc.substrate_wids[self._pf_proc.substrate_idx_mg]
                    or wid == self._pf_proc.substrate_wids[self._pf_proc.substrate_idx_zinc]
                )
                else 0.0
            )
            for wid in self._pf_proc.substrate_wids
        }

        # Design D4: this calculator's PT contribution is deleted outright
        # (not merely zeroed) -- `RequestCalculatorPTransloc` is the sole
        # writer of `requests[self._pt_proc.name]`; it reads only the
        # compartment authority and enzyme pools, never this class's legacy
        # `counts`/`location` reads (both gone). Leaving a second,
        # now-reading-nothing writer here would be exactly the dual-writer
        # shape this design bans, even though its value happened to be
        # overwritten by the later-running PTransloc calculator today.
        return {
            "requests": {
                self._pp1_proc.name: pp1_req,
                self._pp2_proc.name: pp2_req,
                self._pm_proc.name: pm_req,
                self._pf_proc.name: pf_req,
            }
        }


class RequestCalculatorTranscription(_SafeDtMixin, Step):
    """Compute allocator requests for mechanism-driven transcription."""

    name = "request_calculator_transcription"
    defaults: dict[str, Any] = {"transcription_proc": None}

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        tx_proc = self.parameters.get("transcription_proc")
        if tx_proc is None:
            raise ValueError("RequestCalculatorTranscription requires parameter: transcription_proc")
        self._tx_proc = tx_proc
        self._proc = tx_proc
        self._request_wids = list(self._tx_proc.allocation_substrate_wids)

    def ports_schema(self) -> dict[str, Any]:
        return {
            "complex": {
                "counts": {
                    "RNA_POLYMERASE": {
                        "_default": float(self._tx_proc._fallback_n_active_rnap),
                        "_updater": "accumulate",
                        "_emit": False,
                    }
                }
            },
            "requests": {
                self._tx_proc.name: {
                    wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                    for wid in self._request_wids
                }
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        if not (
            bool(self._tx_proc.parameters.get("write_substrate_deltas", True))
            and bool(self._tx_proc.parameters.get("use_allocator_budget", False))
        ):
            return {"requests": {self._tx_proc.name: {wid: 0.0 for wid in self._request_wids}}}

        n_active = float(
            states.get("complex", {})
            .get("counts", {})
            .get("RNA_POLYMERASE", self._tx_proc._fallback_n_active_rnap)
        )
        n_active = max(0.0, n_active)
        total_nt = self._tx_proc._predict_total_nt_polymerization_per_s(n_active)
        per_ntp_need = max(0.0, total_nt / 4.0 * self._safe_dt(timestep))
        requests = {wid: per_ntp_need for wid in self._request_wids}
        return {"requests": {self._tx_proc.name: requests}}


class RequestCalculatorTranslation(_SafeDtMixin, Step):
    """Compute allocator requests for mechanism-driven translation."""

    name = "request_calculator_translation"
    defaults: dict[str, Any] = {"translation_proc": None}

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        tl_proc = self.parameters.get("translation_proc")
        if tl_proc is None:
            raise ValueError("RequestCalculatorTranslation requires parameter: translation_proc")
        self._tl_proc = tl_proc
        self._proc = tl_proc
        self._request_wids = list(self._tl_proc.allocation_substrate_wids)

    def ports_schema(self) -> dict[str, Any]:
        return {
            "complex": {
                "counts": {
                    "RIBOSOME_70S": {
                        "_default": float(self._tl_proc._fallback_n_active_ribosomes),
                        "_updater": "accumulate",
                        "_emit": False,
                    }
                }
            },
            "requests": {
                self._tl_proc.name: {
                    wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                    for wid in self._request_wids
                }
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        if not (
            bool(self._tl_proc.parameters.get("write_substrate_deltas", True))
            and bool(self._tl_proc.parameters.get("use_allocator_budget", False))
        ):
            return {"requests": {self._tl_proc.name: {wid: 0.0 for wid in self._request_wids}}}

        n_active = float(
            states.get("complex", {})
            .get("counts", {})
            .get("RIBOSOME_70S", self._tl_proc._fallback_n_active_ribosomes)
        )
        n_active = max(0.0, n_active)
        rates = tl_v2.predict_synthesis_per_s(self._tl_proc.mechanism_inputs, n_active=n_active)
        need_by_aa = self._tl_proc._predict_substrate_need(rates, self._safe_dt(timestep))
        requests = {wid: max(0.0, float(need_by_aa.get(wid, 0.0))) for wid in self._request_wids}
        return {"requests": {self._tl_proc.name: requests}}


class RequestCalculatorPTransloc(_SafeDtMixin, Step):
    """Compute allocator requests for protein translocation substrate demand.

    Literal transcription of `ProteinTranslocation.m:284-301`
    `calcResourceRequirements_Current` (design D4): `translocases` and `SRPs`
    are enzyme-capacity caps (complex/protein counts x rate x dt, in amino
    acids -- no division by `aaTranslocatedPerATP`); `ATP`/`GTP` are each
    capped by the corresponding capacity against the sum of pending
    `processed_i["c"]` copies' exact cost. No substrate-pool read anywhere
    in this class -- the pool-floor deviation (PT-S4-03) is deleted, not
    guarded.
    """

    name = "request_calculator_protein_translocation"
    defaults: dict[str, Any] = {"protein_translocation_proc": None}

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        from opencell.vivarium.karr_protein_translocation import (
            KarrProteinTranslocationProcess,
        )

        _require_process_dependencies(
            type(self).__name__,
            self.parameters,
            {"protein_translocation_proc": KarrProteinTranslocationProcess},
        )
        pt_proc = self.parameters["protein_translocation_proc"]
        self._pt_proc = pt_proc
        self._proc = pt_proc
        self._request_wids = list(self._pt_proc.allocation_substrate_wids)
        self._atp_wid = str(self._pt_proc.atp_wid)
        self._gtp_wid = str(self._pt_proc.gtp_wid)
        self._h2o_wid = str(self._pt_proc.h2o_wid)
        self._complex_enzyme_wid_set = set(self._pt_proc.complex_enzyme_wids)

    def ports_schema(self) -> dict[str, Any]:
        from opencell.vivarium.protein_state import MIGRATED_WIDS, compartment_counts_schema

        processed_i_schema = compartment_counts_schema(MIGRATED_WIDS)["processed_i"]
        return {
            # Design D4: declared for topology-wiring compatibility only
            # (C12's own minimal composite wires it); `next_update` never
            # reads from this port -- the pool-floor read path is deleted,
            # not merely unused.
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self._request_wids
            },
            "complex": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self._pt_proc.complex_count_wids
                }
            },
            "protein": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in sorted(set(self._pt_proc.protein_count_wids))
                },
                "compartment_counts": {
                    "processed_i": {
                        wid: processed_i_schema[wid]
                        for wid in self._pt_proc.translocatable_wids_in_fixture_order
                    }
                },
            },
            "requests": {
                self._pt_proc.name: {
                    wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                    for wid in self._request_wids
                }
            },
        }

    def _enzyme_count(self, states: dict[str, Any], wid: str) -> float:
        if wid in self._complex_enzyme_wid_set:
            complex_counts_state = states.get("complex", {}).get("counts", {})
            return max(0.0, float(complex_counts_state.get(wid, 0.0)))
        protein_counts_state = states.get("protein", {}).get("counts", {})
        return max(0.0, float(protein_counts_state.get(wid, 0.0)))

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        dt = self._safe_dt(timestep)
        processed_i_state = (
            states.get("protein", {}).get("compartment_counts", {}).get("processed_i", {})
        )
        requests = {wid: 0.0 for wid in self._request_wids}

        atpase = self._enzyme_count(states, self._pt_proc.translocase_atpase_wid)
        pore = self._enzyme_count(states, self._pt_proc.translocase_pore_wid)
        srp = self._enzyme_count(states, self._pt_proc.srp_wid)
        receptor = self._enzyme_count(states, self._pt_proc.srp_receptor_wid)

        # `:284-285` -- translocases in amino acids (NOT divided by
        # `aaTranslocatedPerATP`, unlike `evolveState`'s per-copy cost).
        translocases = math.ceil(
            min(atpase, pore) * self._pt_proc.translocase_specific_rate * dt
        )
        # `:286` -- SRPs in monomers.
        srps = math.ceil(min(srp, receptor) * dt)

        atp_need = 0.0
        srp_pending = 0.0
        for wid in self._pt_proc.translocatable_wids_in_fixture_order:
            pending = max(0.0, float(processed_i_state.get(wid, {}).get("c", 0.0)))
            if pending <= 0.0:
                continue
            atp_need += pending * float(self._pt_proc.atp_cost_by_wid[wid])
            if self._pt_proc.pathway_by_wid.get(wid) == "srp":
                srp_pending += pending

        # `:287` -- ATP capped by translocase capacity against pending-copy cost.
        atp_request = min(float(translocases), atp_need)
        # `:288` -- GTP capped by SRP capacity against pending SRP-pathway copies.
        gtp_request = float(self._pt_proc.srp_gtp_cost_per_monomer) * min(
            float(srps), srp_pending
        )
        # `:289` -- water identity.
        h2o_request = atp_request + gtp_request

        requests[self._atp_wid] = atp_request
        requests[self._gtp_wid] = gtp_request
        requests[self._h2o_wid] = h2o_request
        return {"requests": {self._pt_proc.name: requests}}


class RequestCalculatorMetabolism(Step):
    """Emit allocator requests for dynamic-bounds metabolism substrate demand."""

    name = "request_calculator_metabolism"
    defaults: dict[str, Any] = {
        "metabolism_proc": None,
        "parameters_fixture_path": None,
        "include_growth_coupled_gam": True,
        "cell_dry_mass_g": None,
        "growth_rate_per_s": None,
        "karr_parity_mode": True,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        m1_proc = self.parameters.get("metabolism_proc")
        if m1_proc is None:
            raise ValueError("RequestCalculatorMetabolism requires parameter: metabolism_proc")
        self._m1_proc = m1_proc
        self.karr_parity_mode = bool(self.parameters.get("karr_parity_mode", True))
        self._request_wids = list(self._m1_proc.allocation_substrate_wids)
        self._atp_wid = "ATP" if "ATP" in self._request_wids else None

        params_doc = self._load_parameters_fixture_doc(self.parameters.get("parameters_fixture_path"))
        metabolism_params = params_doc.get("processes", {}).get("Metabolism", {})
        self._ngam_mmol_per_gdw_h = float(
            metabolism_params.get("nonGrowthAssociatedMaintenance", 0.0)
        )
        self._gam_mmol_per_mmol_biomass = float(
            metabolism_params.get("growthAssociatedMaintenance", 0.0)
        )
        self._include_growth_coupled_gam = bool(self.parameters.get("include_growth_coupled_gam", True))
        self._cell_dry_mass_g = self._resolve_cell_dry_mass_g(params_doc)
        self._growth_rate_per_s = self._resolve_growth_rate_per_s(params_doc)
        self._tick_s_default = max(
            0.0,
            float(getattr(self._m1_proc, "parameters", {}).get("time_step", 0.0)),
        )

    def ports_schema(self) -> dict[str, Any]:
        return {
            "requests": {
                self._m1_proc.name: {
                    wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                    for wid in self._request_wids
                }
            }
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del states
        if not self._request_wids:
            return {"requests": {}}
        if not bool(self._m1_proc.use_allocator_budget):
            return {"requests": {self._m1_proc.name: {wid: 0.0 for wid in self._request_wids}}}

        requests = {
            wid: max(0.0, float(self._m1_proc._last_allocation_demand.get(wid, 0.0)))
            for wid in self._request_wids
        }
        if self._atp_wid is not None and not self.karr_parity_mode:
            requests[self._atp_wid] = max(
                requests[self._atp_wid],
                self._atp_floor_request_for_tick(float(timestep)),
            )
        return {"requests": {self._m1_proc.name: requests}}

    @staticmethod
    def _default_parameters_fixture_path() -> Path:
        return Path(__file__).resolve().parents[2] / "data" / "karr_fixtures" / "parameters.json"

    @classmethod
    def _load_parameters_fixture_doc(cls, fixture_path: str | Path | None) -> dict[str, Any]:
        path = Path(fixture_path) if fixture_path is not None else cls._default_parameters_fixture_path()
        payload = json.loads(path.read_text())
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid parameters fixture payload at {path}")
        return payload

    def _resolve_cell_dry_mass_g(self, params_doc: dict[str, Any]) -> float:
        explicit = self.parameters.get("cell_dry_mass_g")
        if explicit is not None:
            return max(0.0, float(explicit))

        model = getattr(self._m1_proc, "model", None)
        if model is not None:
            stored_runtime = getattr(model, "stored_runtime", {})
            if isinstance(stored_runtime, dict):
                for key in ("cell_dry_total_mass_g", "cell_initial_dry_weight_g"):
                    if key in stored_runtime:
                        return max(0.0, float(stored_runtime[key]))

        mass_state = params_doc.get("states", {}).get("Mass", {})
        return max(0.0, float(mass_state.get("cellInitialDryWeight", 0.0)))

    def _resolve_growth_rate_per_s(self, params_doc: dict[str, Any]) -> float:
        explicit = self.parameters.get("growth_rate_per_s")
        if explicit is not None:
            return max(0.0, float(explicit))

        model = getattr(self._m1_proc, "model", None)
        if model is not None:
            stored_runtime = getattr(model, "stored_runtime", {})
            if isinstance(stored_runtime, dict):
                for key in ("meanInitialGrowthRate_per_s", "growth0_per_s", "growth_per_s"):
                    if key in stored_runtime:
                        return max(0.0, float(stored_runtime[key]))

        met_state = params_doc.get("states", {}).get("MetabolicReaction", {})
        return max(0.0, float(met_state.get("meanInitialGrowthRate", 0.0)))

    def _atp_floor_request_for_tick(self, timestep: float) -> float:
        tick = max(0.0, float(timestep))
        if tick <= 0.0:
            tick = self._tick_s_default
        ngam_mmol = (
            self._ngam_mmol_per_gdw_h
            * self._cell_dry_mass_g
            * tick
            / float(SECONDS_PER_HOUR)
        )
        gam_mmol = 0.0
        if self._include_growth_coupled_gam:
            gam_mmol = (
                self._gam_mmol_per_mmol_biomass
                * self._growth_rate_per_s
                * self._cell_dry_mass_g
                * tick
            )
        total_mmol = max(0.0, ngam_mmol + gam_mmol)
        return total_mmol * 1e-3 * float(AVOGADRO)


__all__ = [
    "RequestCalculatorD2",
    "RequestCalculatorPD",
    "RequestCalculatorRibAsm",
    "RequestCalculatorTRNA",
    "RequestCalculatorRNAPathway",
    "RequestCalculatorProteinPathway",
    "RequestCalculatorTranscription",
    "RequestCalculatorTranslation",
    "RequestCalculatorPTransloc",
    "RequestCalculatorMetabolism",
]
