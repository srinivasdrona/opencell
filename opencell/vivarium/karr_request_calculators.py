"""Vivarium Step helpers that compute per-tick allocation requests."""

from __future__ import annotations

from typing import Any

import numpy as np
from vivarium.core.process import Step

from opencell.m3 import translation_v2 as tl_v2


def _consumed_wids_from_stoich(substrate_wids: list[str], stoich: np.ndarray) -> list[str]:
    consumed_idx = np.flatnonzero(np.any(np.asarray(stoich, dtype=np.int64) < 0, axis=1))
    return [substrate_wids[int(idx)] for idx in consumed_idx]


def _request_from_available(
    substrate_state: dict[str, Any],
    target_wids: list[str],
    *,
    active: bool,
) -> dict[str, float]:
    if not active:
        return {wid: 0.0 for wid in target_wids}
    return {wid: max(0.0, float(substrate_state.get(wid, 0.0))) for wid in target_wids}


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


class RequestCalculatorPD(Step):
    """Estimate ProteinDecay-light ATP/H2O requirements for this tick."""

    name = "request_calculator_pd"
    defaults: dict[str, Any] = {"pd_light_proc": None}

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        pd_light_proc = self.parameters.get("pd_light_proc")
        if pd_light_proc is None:
            raise ValueError("RequestCalculatorPD requires parameter: pd_light_proc")
        self._pd_light_proc = pd_light_proc

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
        expected_decays = rates * complex_counts * float(timestep)

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
        ribasm_proc = self.parameters.get("ribasm_proc")
        if ribasm_proc is None:
            raise ValueError("RequestCalculatorRibAsm requires parameter: ribasm_proc")
        self._ribasm_proc = ribasm_proc

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
                    requests[wid] = max(25.0, avail * 25.0)
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
        self._rp_consumed = _consumed_wids_from_stoich(
            self._rp_proc.substrate_wids, self._rp_proc.reaction_stoich
        )
        self._rm_consumed = _consumed_wids_from_stoich(
            self._rm_proc.substrate_wids, self._rm_proc.reaction_stoich
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
                        set(self._rp_proc.rna_wids) | set(self._rm_proc.unmodified_rna_wids)
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
        substrate_state = states.get("substrates", {})
        rna_counts = states.get("rna", {}).get("counts", {})
        rp_active = any(
            float(rna_counts.get(wid, 0.0)) > 0.0 for wid in self._rp_proc.unprocessed_rna_wids
        )
        rm_active = any(
            float(rna_counts.get(wid, 0.0)) > 0.0 for wid in self._rm_proc.unmodified_rna_wids
        )

        rp_request = {wid: 0.0 for wid in self._rp_proc.substrate_wids}
        rp_request.update(
            _request_from_available(substrate_state, self._rp_consumed, active=rp_active)
        )
        rm_request = {wid: 0.0 for wid in self._rm_proc.substrate_wids}
        rm_request.update(
            _request_from_available(substrate_state, self._rm_consumed, active=rm_active)
        )
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
        self._pp1_proc = self.parameters.get("protein_processing_i_proc")
        self._pp2_proc = self.parameters.get("protein_processing_ii_proc")
        self._pm_proc = self.parameters.get("protein_modification_proc")
        self._pf_proc = self.parameters.get("protein_folding_proc")
        self._pt_proc = self.parameters.get("protein_translocation_proc")
        if any(
            p is None
            for p in (self._pp1_proc, self._pp2_proc, self._pm_proc, self._pf_proc, self._pt_proc)
        ):
            raise ValueError(
                "RequestCalculatorProteinPathway requires all protein pathway process parameters"
            )

        self._pp2_consumed = _consumed_wids_from_stoich(
            self._pp2_proc.substrate_wids, self._pp2_proc.reaction_stoich
        )
        self._pm_consumed = _consumed_wids_from_stoich(
            self._pm_proc.substrate_wids, self._pm_proc.reaction_stoich
        )

    def ports_schema(self) -> dict[str, Any]:
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
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in sorted(
                        set(self._pp1_proc.enzyme_wids)
                        | set(self._pp2_proc.enzyme_wids)
                        | set(self._pm_proc.enzyme_wids)
                        | set(self._pf_proc.enzyme_wids)
                        | set(self._pt_proc.protein_count_wids)
                    )
                },
                "unprocessed_counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in sorted(
                        set(self._pp1_proc.unprocessed_monomer_wids)
                        | set(self._pp2_proc.unprocessed_monomer_wids)
                    )
                },
                "processed_counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self._pp2_proc.processed_monomer_wids
                },
                "unfolded_counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self._pf_proc.unfolded_monomer_wids
                },
                "unmodified_counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self._pm_proc.unmodified_monomer_wids
                },
                "location": {
                    wid: {"_default": "cytoplasm", "_updater": "set", "_emit": False}
                    for wid in self._pt_proc.translocatable_wids
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
        counts_state = protein_state.get("counts", {})
        unprocessed_state = protein_state.get("unprocessed_counts", {})
        processed_state = protein_state.get("processed_counts", {})
        unfolded_state = protein_state.get("unfolded_counts", {})
        unmodified_state = protein_state.get("unmodified_counts", {})
        location_state = protein_state.get("location", {})

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
        pt_active = any(
            float(counts_state.get(wid, 0.0)) > 0.0
            and str(location_state.get(wid, "cytoplasm")) == "cytoplasm"
            for wid in self._pt_proc.translocatable_wids
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

        pt_req = {
            wid: (max(0.0, float(substrate_state.get(wid, 0.0))) if pt_active else 0.0)
            for wid in self._pt_proc.request_wids
        }

        return {
            "requests": {
                self._pp1_proc.name: pp1_req,
                self._pp2_proc.name: pp2_req,
                self._pm_proc.name: pm_req,
                self._pf_proc.name: pf_req,
                self._pt_proc.name: pt_req,
            }
        }


class RequestCalculatorTranscription(Step):
    """Compute allocator requests for mechanism-driven transcription."""

    name = "request_calculator_transcription"
    defaults: dict[str, Any] = {"transcription_proc": None}

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        tx_proc = self.parameters.get("transcription_proc")
        if tx_proc is None:
            raise ValueError("RequestCalculatorTranscription requires parameter: transcription_proc")
        self._tx_proc = tx_proc
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
        per_ntp_need = max(0.0, total_nt / 4.0 * float(timestep))
        requests = {wid: per_ntp_need for wid in self._request_wids}
        return {"requests": {self._tx_proc.name: requests}}


class RequestCalculatorTranslation(Step):
    """Compute allocator requests for mechanism-driven translation."""

    name = "request_calculator_translation"
    defaults: dict[str, Any] = {"translation_proc": None}

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        tl_proc = self.parameters.get("translation_proc")
        if tl_proc is None:
            raise ValueError("RequestCalculatorTranslation requires parameter: translation_proc")
        self._tl_proc = tl_proc
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
        need_by_aa = self._tl_proc._predict_substrate_need(rates, timestep)
        requests = {wid: max(0.0, float(need_by_aa.get(wid, 0.0))) for wid in self._request_wids}
        return {"requests": {self._tl_proc.name: requests}}


class RequestCalculatorMetabolism(Step):
    """Emit allocator requests for dynamic-bounds metabolism substrate demand."""

    name = "request_calculator_metabolism"
    defaults: dict[str, Any] = {"metabolism_proc": None}

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        m1_proc = self.parameters.get("metabolism_proc")
        if m1_proc is None:
            raise ValueError("RequestCalculatorMetabolism requires parameter: metabolism_proc")
        self._m1_proc = m1_proc
        self._request_wids = list(self._m1_proc.allocation_substrate_wids)

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
        del timestep, states
        if not bool(self._m1_proc.use_allocator_budget):
            return {"requests": {self._m1_proc.name: {wid: 0.0 for wid in self._request_wids}}}

        requests = {
            wid: max(0.0, float(self._m1_proc._last_allocation_demand.get(wid, 0.0)))
            for wid in self._request_wids
        }
        return {"requests": {self._m1_proc.name: requests}}


__all__ = [
    "RequestCalculatorD2",
    "RequestCalculatorPD",
    "RequestCalculatorRibAsm",
    "RequestCalculatorTRNA",
    "RequestCalculatorRNAPathway",
    "RequestCalculatorProteinPathway",
    "RequestCalculatorTranscription",
    "RequestCalculatorTranslation",
    "RequestCalculatorMetabolism",
]
