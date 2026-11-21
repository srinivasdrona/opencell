"""Read-only observability step for Phase E phenotype extraction.

This step computes lightweight aggregate observables from existing chassis state
without mutating any biology stores.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from vivarium.core.process import Step

from opencell.analysis.cell_mass import CellMassProjection
from opencell.m1 import karr_metabolism as km
from opencell.m2 import transcription as tx
from opencell.m3 import translation as tl
from opencell.vivarium.protein_state import MIGRATED_WIDS, flat_counts_schema


def _load_dna_mass_fraction_default() -> float:
    params_path = Path(__file__).resolve().parents[2] / "data" / "karr_fixtures" / "parameters.json"
    with params_path.open(encoding="utf-8") as f:
        raw = json.load(f)
    return float(raw["states"]["Mass"]["dryWeightFractionDNA"])


class KarrObservabilityStep(Step):
    """Emit aggregate observables used by Phase E phenotype scorecards."""

    name = "karr_observability_step"
    defaults: dict[str, Any] = {
        "m1_model": None,
        "m2_model": None,
        "m3_model": None,
        "genome_half_bp": 290_038.0,
        "dna_mass_fraction": None,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        m1_model = self.parameters.get("m1_model")
        if m1_model is None:
            m1_model = km.load_default()
        m2_model = self.parameters.get("m2_model")
        if m2_model is None:
            m2_model = tx.load_default()
        m3_model = self.parameters.get("m3_model")
        if m3_model is None:
            m3_model = tl.load_default()

        self.m1_model: km.KarrMetabolismModel = m1_model
        self.m2_model: tx.KarrTranscriptionModel = m2_model
        self.m3_model: tl.KarrTranslationModel = m3_model
        self._mass_projection = CellMassProjection.build(m1_model, m2_model, m3_model)
        self._rna_mw_by_store = self._mass_projection.rna_mw_by_store
        self.rna_mw_by_wid = self._rna_mw_by_store["counts"]
        self.protein_mw_by_wid = self._mass_projection.protein_mw
        self._rna_wids = tuple(self.rna_mw_by_wid)
        self._protein_wids = tuple(self.m3_model.protein_wcm_ids)
        self._substrate_wids = tuple(str(wid) for wid in self.m1_model.raw["ids"]["substrate_wcm_585"])
        self.cell_dry_mass_reference_g = float(self.m1_model.stored_runtime["cell_dry_total_mass_g"])
        configured_dna_mass_fraction = self.parameters.get("dna_mass_fraction")
        if configured_dna_mass_fraction is None:
            configured_dna_mass_fraction = _load_dna_mass_fraction_default()
        self.dna_mass_fraction = float(configured_dna_mass_fraction)
        self.genome_half_bp = max(float(self.parameters.get("genome_half_bp", 290_038.0)), 1.0)
        self._base_dna_mass_g = self.cell_dry_mass_reference_g * self.dna_mass_fraction
        self._elapsed_s = 0.0
        self._cytokinesis_start_s = float("nan")
        self._cytokinesis_complete_s = float("nan")

    def ports_schema(self) -> dict[str, Any]:
        return {
            "rna": {
                store: {
                    wid: {
                        "_default": 0.0,
                        "_updater": "accumulate",
                        "_emit": False,
                    }
                    for wid in weights
                }
                for store, weights in self._rna_mw_by_store.items()
            },
            "protein": {
                # Share the projection owner's rejecting updater without
                # writing its derived flat leaves.
                "counts": {
                    **{
                        wid: {
                            "_default": 0.0,
                            "_updater": "accumulate",
                            "_emit": False,
                        }
                        for wid in self._protein_wids
                        if wid not in MIGRATED_WIDS
                    },
                    **{
                        wid: schema
                        for wid, schema in flat_counts_schema(MIGRATED_WIDS).items()
                        if wid in self._protein_wids
                    },
                },
                # Engine's deep read selector adds no defaults/updaters: an
                # absent canonical pool stays empty in flat-only inputs.
                "compartment_counts": "**",
                **{store: "**" for store in self._mass_projection.protein_queue_mw},
                **{store: "**" for store in self._mass_projection.activation_mw_by_store},
            },
            "complex": {
                "counts": "**",
                **{store: "**" for store in self._mass_projection.complex_activation_mw_by_store},
            },
            "chromosome": {
                "replication_state": {"_default": "idle", "_updater": "set", "_emit": False},
                "fork_position_bp": {
                    "left": {"_default": 0.0, "_updater": "accumulate", "_emit": False},
                    "right": {"_default": 0.0, "_updater": "accumulate", "_emit": False},
                },
            },
            "cell": {
                "cycle_phase": {"_default": "idle", "_updater": "set", "_emit": False},
                "division_progress": {"_default": 0.0, "_updater": "accumulate", "_emit": False},
                "division_complete": {"_default": False, "_updater": "set", "_emit": False},
            },
            "substrates": {
                wid: {
                    "_default": 0.0,
                    "_updater": "accumulate",
                    "_emit": False,
                }
                for wid in self._substrate_wids
            },
            "phenotype_observables": {
                "rna_mass_g": {"_default": 0.0, "_updater": "set", "_emit": True},
                "protein_mass_g": {"_default": 0.0, "_updater": "set", "_emit": True},
                "cell_dry_mass_g": {"_default": 0.0, "_updater": "set", "_emit": True},
                "dna_mass_g": {"_default": self._base_dna_mass_g, "_updater": "set", "_emit": True},
                "cytokinesis_start_tick_s": {"_default": float("nan"), "_updater": "set", "_emit": True},
                "cytokinesis_complete_tick_s": {
                    "_default": float("nan"),
                    "_updater": "set",
                    "_emit": True,
                },
                "metabolite_pools": {
                    wid: {
                        "_default": 0.0,
                        "_updater": "set",
                        "_emit": False,
                    }
                    for wid in self._substrate_wids
                },
                "cell_dry_mass_reference_g": {
                    "_default": self.cell_dry_mass_reference_g,
                    "_updater": "set",
                    "_emit": True,
                },
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        dt = max(float(timestep), 0.0)
        current_time_s = self._elapsed_s + dt
        chromosome = states.get("chromosome", {})
        cell = states.get("cell", {})
        substrates = states.get("substrates", {})

        mass = self._mass_projection.compute(states)
        fork = chromosome.get("fork_position_bp", {})
        left_fork = abs(float(fork.get("left", 0.0)))
        right_fork = abs(float(fork.get("right", 0.0)))
        fork_progress = float(np.clip(max(left_fork, right_fork) / self.genome_half_bp, 0.0, 1.0))
        replication_state = str(chromosome.get("replication_state", "idle")).strip().lower()
        if replication_state == "complete":
            fork_progress = 1.0
        dna_mass_g = self._base_dna_mass_g * (1.0 + fork_progress)
        division_progress = float(cell.get("division_progress", 0.0))
        division_complete = bool(cell.get("division_complete", False))
        cycle_phase = str(cell.get("cycle_phase", "idle")).strip().lower()
        cytokinesis_started = (cycle_phase == "dividing") or (division_progress > 0.0)
        if not np.isfinite(self._cytokinesis_start_s) and cytokinesis_started:
            self._cytokinesis_start_s = float(current_time_s)
        cytokinesis_complete = division_complete or (cycle_phase == "divided")
        if (
            np.isfinite(self._cytokinesis_start_s)
            and (not np.isfinite(self._cytokinesis_complete_s))
            and cytokinesis_complete
        ):
            self._cytokinesis_complete_s = float(current_time_s)
        self._elapsed_s = current_time_s
        metabolite_pools = {wid: float(substrates.get(wid, 0.0)) for wid in self._substrate_wids}

        return {
            "phenotype_observables": {
                "rna_mass_g": mass.rna_mass_g,
                "protein_mass_g": mass.protein_mass_g,
                "cell_dry_mass_g": mass.total_g,
                "dna_mass_g": float(dna_mass_g),
                "cytokinesis_start_tick_s": float(self._cytokinesis_start_s),
                "cytokinesis_complete_tick_s": float(self._cytokinesis_complete_s),
                "metabolite_pools": metabolite_pools,
                "cell_dry_mass_reference_g": float(self.cell_dry_mass_reference_g),
            }
        }


__all__ = ["KarrObservabilityStep"]
