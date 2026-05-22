"""Vivarium Step helpers that compute per-tick allocation requests."""
from __future__ import annotations

from typing import Any

import numpy as np
from vivarium.core.process import Step


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
        self._zero_requests = {
            wid: 0.0 for wid in self._d2_real_proc.substrate_wids
        }

    def ports_schema(self) -> dict[str, Any]:
        return {
            "complex": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self._d2_real_proc.complex_wids
                }
            },
            "requests": {
                "karr_d2_real": {
                    wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                    for wid in self._d2_real_proc.substrate_wids
                }
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del timestep, states
        return {"requests": {"karr_d2_real": dict(self._zero_requests)}}


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
            return {
                "requests": {
                    "karr_protein_decay_light": {"ATP": 0.0, "H2O": 0.0}
                }
            }

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


__all__ = ["RequestCalculatorD2", "RequestCalculatorPD"]
