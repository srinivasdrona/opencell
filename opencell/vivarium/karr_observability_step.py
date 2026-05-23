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

from opencell.analysis.cell_mass import AVOGADRO
from opencell.m1 import karr_metabolism as km
from opencell.m2 import transcription as tx
from opencell.m3 import translation as tl


def _load_rna_mw(m2_model: tx.KarrTranscriptionModel) -> dict[str, float]:
    npz_path = Path(__file__).resolve().parents[2] / "data" / "karr_fixtures" / "karr_native_m2.npz"
    payload = np.load(npz_path)
    if "rna_molecular_weight" not in payload.files:
        raise RuntimeError("M2 fixture missing rna_molecular_weight.")
    arr = np.asarray(payload["rna_molecular_weight"], dtype=float).reshape(-1)
    if arr.size != len(m2_model.gene_wcm_ids):
        raise RuntimeError(
            f"rna_molecular_weight size {arr.size} != gene_wcm_ids size {len(m2_model.gene_wcm_ids)}"
        )
    return dict(zip(m2_model.gene_wcm_ids, arr.tolist(), strict=False))


def _mass_from_counts(counts: dict[str, Any], mw_by_wid: dict[str, float]) -> float:
    total_da = 0.0
    for wid, raw_count in counts.items():
        mw = mw_by_wid.get(wid)
        if mw is None or mw <= 0.0:
            continue
        total_da += float(raw_count) * mw
    return float(total_da / AVOGADRO)


def _load_protein_mw(m3_model: tl.KarrTranslationModel) -> dict[str, float]:
    arr = np.asarray(m3_model.molecular_weight, dtype=float).reshape(-1)
    if arr.size != len(m3_model.protein_wcm_ids):
        raise RuntimeError(
            "protein molecular_weight size "
            f"{arr.size} != protein_wcm_ids size {len(m3_model.protein_wcm_ids)}"
        )
    return dict(zip(m3_model.protein_wcm_ids, arr.tolist(), strict=False))


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
        self.rna_mw_by_wid = _load_rna_mw(self.m2_model)
        self.protein_mw_by_wid = _load_protein_mw(self.m3_model)
        self._rna_wids = tuple(self.m2_model.gene_wcm_ids)
        self._protein_wids = tuple(self.m3_model.protein_wcm_ids)
        self.cell_dry_mass_reference_g = float(self.m1_model.stored_runtime["cell_dry_total_mass_g"])
        configured_dna_mass_fraction = self.parameters.get("dna_mass_fraction")
        if configured_dna_mass_fraction is None:
            configured_dna_mass_fraction = _load_dna_mass_fraction_default()
        self.dna_mass_fraction = float(configured_dna_mass_fraction)
        self.genome_half_bp = max(float(self.parameters.get("genome_half_bp", 290_038.0)), 1.0)
        self._base_dna_mass_g = self.cell_dry_mass_reference_g * self.dna_mass_fraction

    def ports_schema(self) -> dict[str, Any]:
        counts_schema = {
            wid: {
                "_default": 0.0,
                "_updater": "accumulate",
                "_emit": False,
            }
            for wid in self._rna_wids
        }
        return {
            "rna": {
                "counts": counts_schema,
                "aminoacylated_counts": counts_schema,
                "modified_counts": counts_schema,
            },
            "protein": {
                "counts": {
                    wid: {
                        "_default": 0.0,
                        "_updater": "accumulate",
                        "_emit": False,
                    }
                    for wid in self._protein_wids
                }
            },
            "chromosome": {
                "replication_state": {"_default": "idle", "_updater": "set", "_emit": False},
                "fork_position_bp": {
                    "left": {"_default": 0.0, "_updater": "accumulate", "_emit": False},
                    "right": {"_default": 0.0, "_updater": "accumulate", "_emit": False},
                },
            },
            "phenotype_observables": {
                "rna_mass_g": {"_default": 0.0, "_updater": "set", "_emit": True},
                "protein_mass_g": {"_default": 0.0, "_updater": "set", "_emit": True},
                "dna_mass_g": {"_default": self._base_dna_mass_g, "_updater": "set", "_emit": True},
                "cell_dry_mass_reference_g": {
                    "_default": self.cell_dry_mass_reference_g,
                    "_updater": "set",
                    "_emit": True,
                },
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del timestep
        rna = states.get("rna", {})
        rna_counts = rna.get("counts", {})
        aminoacylated_counts = rna.get("aminoacylated_counts", {})
        modified_counts = rna.get("modified_counts", {})
        protein_counts = states.get("protein", {}).get("counts", {})
        chromosome = states.get("chromosome", {})

        rna_mass_g = (
            _mass_from_counts(rna_counts, self.rna_mw_by_wid)
            + _mass_from_counts(aminoacylated_counts, self.rna_mw_by_wid)
            + _mass_from_counts(modified_counts, self.rna_mw_by_wid)
        )
        protein_mass_g = _mass_from_counts(protein_counts, self.protein_mw_by_wid)
        fork = chromosome.get("fork_position_bp", {})
        left_fork = abs(float(fork.get("left", 0.0)))
        right_fork = abs(float(fork.get("right", 0.0)))
        fork_progress = float(np.clip(max(left_fork, right_fork) / self.genome_half_bp, 0.0, 1.0))
        replication_state = str(chromosome.get("replication_state", "idle")).strip().lower()
        if replication_state == "complete":
            fork_progress = 1.0
        dna_mass_g = self._base_dna_mass_g * (1.0 + fork_progress)

        return {
            "phenotype_observables": {
                "rna_mass_g": float(rna_mass_g),
                "protein_mass_g": float(protein_mass_g),
                "dna_mass_g": float(dna_mass_g),
                "cell_dry_mass_reference_g": float(self.cell_dry_mass_reference_g),
            }
        }


__all__ = ["KarrObservabilityStep"]
