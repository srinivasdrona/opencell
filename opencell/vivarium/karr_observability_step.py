"""Read-only observability step for Phase E phenotype extraction.

This step computes lightweight aggregate observables from existing chassis state
without mutating any biology stores.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from vivarium.core.process import Step

from opencell.analysis.cell_mass import AVOGADRO
from opencell.m1 import karr_metabolism as km
from opencell.m2 import transcription as tx


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


class KarrObservabilityStep(Step):
    """Emit aggregate observables used by Phase E phenotype scorecards."""

    name = "karr_observability_step"
    defaults: dict[str, Any] = {
        "m1_model": None,
        "m2_model": None,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        m1_model = self.parameters.get("m1_model")
        if m1_model is None:
            m1_model = km.load_default()
        m2_model = self.parameters.get("m2_model")
        if m2_model is None:
            m2_model = tx.load_default()

        self.m1_model: km.KarrMetabolismModel = m1_model
        self.m2_model: tx.KarrTranscriptionModel = m2_model
        self.rna_mw_by_wid = _load_rna_mw(self.m2_model)
        self._rna_wids = tuple(self.m2_model.gene_wcm_ids)
        self.cell_dry_mass_reference_g = float(self.m1_model.stored_runtime["cell_dry_total_mass_g"])

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
            "phenotype_observables": {
                "rna_mass_g": {"_default": 0.0, "_updater": "set", "_emit": True},
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

        rna_mass_g = (
            _mass_from_counts(rna_counts, self.rna_mw_by_wid)
            + _mass_from_counts(aminoacylated_counts, self.rna_mw_by_wid)
            + _mass_from_counts(modified_counts, self.rna_mw_by_wid)
        )

        return {
            "phenotype_observables": {
                "rna_mass_g": float(rna_mass_g),
                "cell_dry_mass_reference_g": float(self.cell_dry_mass_reference_g),
            }
        }


__all__ = ["KarrObservabilityStep"]
