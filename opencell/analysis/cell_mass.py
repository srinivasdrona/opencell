"""Cell mass aggregator over the M1+M2+M3 chassis state.

Computes:

  cell_dry_mass_g = (substrate_mass + rna_mass + protein_mass) / N_A

where each component is a sum over its molecule class:

  substrate_mass = sum_i  count_substrate[i] * mw_substrate[i]   (Da)
  rna_mass       = sum_g  count_rna[g]      * mw_rna[g]          (Da)
  protein_mass   = sum_p  count_protein[p]  * mw_protein[p]      (Da)

MW provenance:

  mw_substrate -- m1.substrate_molecular_weight (Karr metabolism dump,
                  shape (585,)).
  mw_rna       -- m2.rna_molecular_weight (E.1b ingestion: TU MW from
                  State_Rna mature-form vector, split equally across
                  member genes; non-mRNAs fall back to length_nt * 339.5
                  Da/NT).  482/525 genes have direct TU MW; the
                  remaining 43 (tRNA / rRNA / sRNA) use the seq-length
                  fallback so rRNA mass is not dropped.
  mw_protein   -- m3.molecular_weight (Karr State_ProteinMonomer
                  matureIndexs slice, shape (482,)).

Returns grams (not Daltons) so the result can be compared directly
against Karr's State_Mass.cellDry value (~3.94e-15 g for M. genitalium).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from opencell.m1 import karr_metabolism as km
from opencell.m2 import transcription as tx
from opencell.m3 import translation as tl

AVOGADRO = 6.02214076e23


@dataclass(frozen=True)
class CellMassBreakdown:
    """Per-class mass contributions in grams, plus the total."""
    substrate_mass_g: float
    rna_mass_g: float
    protein_mass_g: float
    total_g: float
    extra: dict[str, Any]


def _load_substrate_mw(m1: km.KarrMetabolismModel) -> dict[str, float]:
    sub_ids = list(m1.raw["ids"]["substrate_wcm_585"])
    mw_arr = np.load(m1.raw["matrix_npz"].replace("data/karr_fixtures/", "data/karr_fixtures/")
                     ) if False else None  # no-op; placeholder kept for clarity
    # Re-load the npz directly to pick up the v2 substrate_molecular_weight
    # field without expanding KarrMetabolismModel's dataclass surface.
    from pathlib import Path
    npz_path = (
        Path(__file__).resolve().parents[2]
        / "data" / "karr_fixtures" / "karr_native_m1.npz"
    )
    z = np.load(npz_path)
    if "substrate_molecular_weight" not in z.files:
        raise RuntimeError(
            "M1 fixture missing substrate_molecular_weight (need karr_native_m1__v2)."
        )
    arr = np.asarray(z["substrate_molecular_weight"], dtype=float).reshape(-1)
    if arr.size != len(sub_ids):
        raise RuntimeError(
            f"substrate_molecular_weight size {arr.size} != "
            f"substrate_wcm_585 size {len(sub_ids)}"
        )
    return dict(zip(sub_ids, arr.tolist()))


def _load_rna_mw(m2: tx.KarrTranscriptionModel) -> dict[str, float]:
    from pathlib import Path
    npz_path = (
        Path(__file__).resolve().parents[2]
        / "data" / "karr_fixtures" / "karr_native_m2.npz"
    )
    z = np.load(npz_path)
    if "rna_molecular_weight" not in z.files:
        raise RuntimeError(
            "M2 fixture missing rna_molecular_weight (need karr_native_m2__v2)."
        )
    arr = np.asarray(z["rna_molecular_weight"], dtype=float).reshape(-1)
    if arr.size != len(m2.gene_wcm_ids):
        raise RuntimeError(
            f"rna_molecular_weight size {arr.size} != "
            f"gene_wcm_ids size {len(m2.gene_wcm_ids)}"
        )
    return dict(zip(m2.gene_wcm_ids, arr.tolist()))


def _load_protein_mw(m3: tl.KarrTranslationModel) -> dict[str, float]:
    arr = np.asarray(m3.molecular_weight, dtype=float).reshape(-1)
    if arr.size != len(m3.protein_wcm_ids):
        raise RuntimeError(
            f"protein molecular_weight size {arr.size} != "
            f"protein_wcm_ids size {len(m3.protein_wcm_ids)}"
        )
    return dict(zip(m3.protein_wcm_ids, arr.tolist()))


def compute_cell_mass(
    state: dict[str, Any],
    m1: km.KarrMetabolismModel,
    m2: tx.KarrTranscriptionModel,
    m3: tl.KarrTranslationModel,
) -> CellMassBreakdown:
    """Aggregate cell mass (grams) from a chassis engine state.

    ``state`` is the dict returned by ``engine.state.get_value()``; we
    read ``state['substrates']``, ``state['rna']['counts']`` and
    ``state['protein']['counts']`` directly.  Counts are molecule counts
    (already integer-valued; we tolerate floats during integrator runs).
    """
    sub_mw = _load_substrate_mw(m1)
    rna_mw = _load_rna_mw(m2)
    prot_mw = _load_protein_mw(m3)

    substrates = state.get("substrates", {})
    rna_counts = state.get("rna", {}).get("counts", {})
    prot_counts = state.get("protein", {}).get("counts", {})

    sub_da = 0.0
    sub_seen = 0
    for sid, cnt in substrates.items():
        mw = sub_mw.get(sid)
        if mw is None or mw <= 0.0:
            continue
        sub_da += float(cnt) * mw
        sub_seen += 1

    rna_da = 0.0
    rna_seen = 0
    for gid, cnt in rna_counts.items():
        mw = rna_mw.get(gid)
        if mw is None or mw <= 0.0:
            continue
        rna_da += float(cnt) * mw
        rna_seen += 1

    prot_da = 0.0
    prot_seen = 0
    for pid, cnt in prot_counts.items():
        mw = prot_mw.get(pid)
        if mw is None or mw <= 0.0:
            continue
        prot_da += float(cnt) * mw
        prot_seen += 1

    sub_g = sub_da / AVOGADRO
    rna_g = rna_da / AVOGADRO
    prot_g = prot_da / AVOGADRO
    total_g = sub_g + rna_g + prot_g
    return CellMassBreakdown(
        substrate_mass_g=sub_g,
        rna_mass_g=rna_g,
        protein_mass_g=prot_g,
        total_g=total_g,
        extra={
            "substrate_da": sub_da,
            "rna_da": rna_da,
            "protein_da": prot_da,
            "n_substrates_with_mw": sub_seen,
            "n_rnas_with_mw": rna_seen,
            "n_proteins_with_mw": prot_seen,
            "n_substrates_total": len(substrates),
            "n_rnas_total": len(rna_counts),
            "n_proteins_total": len(prot_counts),
        },
    )


__all__ = [
    "AVOGADRO",
    "CellMassBreakdown",
    "compute_cell_mass",
]
