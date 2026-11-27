"""Cell mass aggregator over the M1+M2+M3 chassis state.

Computes:

  cell_dry_mass_g = (substrate_mass + rna_mass + protein_mass) / N_A

where each component is a sum over its molecule class:

  substrate_mass = sum_i  count_substrate[i] * mw_substrate[i]   (Da)
  rna_mass       = sum_form,i count_rna[form][i] * mw_rna[form][i] (Da)
  protein_mass   = sum_form,p,comp count_protein[form][p][comp]
                  * mw_protein[form][p]                       (Da)

MW provenance:

  mw_substrate -- m1.substrate_molecular_weight (Karr metabolism dump,
                  shape (585,)).
  mw_rna       -- Rna_flat.mat global form rows, projected onto the actual
                  nascent/processed/intergenic, mature and aminoacylated
                  stores. Non-overlapping legacy gene keys retain the
                  existing m2.rna_molecular_weight representation.
  mw_protein   -- ProteinMonomer_flat.mat form rows. Migrated flat mature
                  views are excluded when the canonical pool is present;
                  existing nonmigrated queues and physical activation pools
                  retain their source form weights. Existing ProteinComplex
                  mature and physical activation stocks use their own rows.

Returns grams (not Daltons) so the result can be compared directly
against Karr's State_Mass.cellDry value (~3.94e-15 g for M. genitalium).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat

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
    np.load(
        m1.raw["matrix_npz"].replace("data/karr_fixtures/", "data/karr_fixtures/")
    ) if False else None  # no-op; placeholder kept for clarity
    # Re-load the npz directly to pick up the v2 substrate_molecular_weight
    # field without expanding KarrMetabolismModel's dataclass surface.
    from pathlib import Path

    npz_path = Path(__file__).resolve().parents[2] / "data" / "karr_fixtures" / "karr_native_m1.npz"
    z = np.load(npz_path)
    if "substrate_molecular_weight" not in z.files:
        raise RuntimeError(
            "M1 fixture missing substrate_molecular_weight (need karr_native_m1__v2)."
        )
    arr = np.asarray(z["substrate_molecular_weight"], dtype=float).reshape(-1)
    if arr.size != len(sub_ids):
        raise RuntimeError(
            f"substrate_molecular_weight size {arr.size} != substrate_wcm_585 size {len(sub_ids)}"
        )
    return dict(zip(sub_ids, arr.tolist(), strict=False))


def _load_rna_mw(m2: tx.KarrTranscriptionModel) -> dict[str, float]:
    from pathlib import Path

    npz_path = Path(__file__).resolve().parents[2] / "data" / "karr_fixtures" / "karr_native_m2.npz"
    z = np.load(npz_path)
    if "rna_molecular_weight" not in z.files:
        raise RuntimeError("M2 fixture missing rna_molecular_weight (need karr_native_m2__v2).")
    arr = np.asarray(z["rna_molecular_weight"], dtype=float).reshape(-1)
    if arr.size != len(m2.gene_wcm_ids):
        raise RuntimeError(
            f"rna_molecular_weight size {arr.size} != gene_wcm_ids size {len(m2.gene_wcm_ids)}"
        )
    return dict(zip(m2.gene_wcm_ids, arr.tolist(), strict=False))


def load_rna_form_mw(m2: tx.KarrTranscriptionModel) -> dict[str, dict[str, float]]:
    """Map existing RNA stores to Rna.m's global form-row molecular weights."""
    legacy = _load_rna_mw(m2)
    path = Path(__file__).resolve().parents[2] / "data/karr_fixtures/per_process/Rna_flat.mat"
    fx = loadmat(str(path), simplify_cells=True)["data"]["fixture"]
    wids = [str(wid) for wid in np.atleast_1d(fx["wholeCellModelIDs"])]
    weights = np.asarray(fx["molecularWeights"], dtype=float).reshape(-1)
    if len(wids) != weights.size or not np.all(np.isfinite(weights) & (weights > 0)):
        raise RuntimeError("Rna fixture molecular weights do not match its global rows.")

    def form_weights(form: str) -> dict[str, float]:
        rows = np.asarray(fx[f"{form}Indexs"], dtype=int).reshape(-1) - 1
        keys = [
            f"intergenic::{row + 1}" if form == "intergenic" else wids[row]
            for row in rows
        ]
        if len(keys) != len(set(keys)):
            raise RuntimeError(f"Rna {form} keys do not uniquely identify source rows.")
        return dict(zip(keys, weights[rows].tolist(), strict=True))

    nascent = form_weights("nascent")
    # Match RP/RM's shared counts authority without merging nascent and processed forms.
    processed = {
        f"processed::{wid}" if wid in nascent else wid: mw
        for wid, mw in form_weights("processed").items()
    }
    return {
        "counts": {**legacy, **nascent, **processed, **form_weights("intergenic")},
        "modified_counts": {**legacy, **form_weights("mature")},
        "aminoacylated_counts": {**legacy, **form_weights("aminoacylated")},
    }


def _load_protein_mw(m3: tl.KarrTranslationModel) -> dict[str, float]:
    arr = np.asarray(m3.molecular_weight, dtype=float).reshape(-1)
    if arr.size != len(m3.protein_wcm_ids):
        raise RuntimeError(
            f"protein molecular_weight size {arr.size} != "
            f"protein_wcm_ids size {len(m3.protein_wcm_ids)}"
        )
    return dict(zip(m3.protein_wcm_ids, arr.tolist(), strict=False))


def _protein_fixture(
    name: str, source_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    path = Path(__file__).resolve().parents[2] / "data/karr_fixtures/per_process" / f"{name}_flat.mat"
    payload = path.read_bytes()
    if source_hashes is not None:
        source_hashes[str(path.resolve())] = hashlib.sha256(payload).hexdigest()
    # Parse the exact bytes bound above, not a second potentially changed read.
    return loadmat(BytesIO(payload), simplify_cells=True)["data"]["fixture"]


def _fixture_wids(fixture: dict[str, Any], field: str) -> list[str]:
    return [str(wid) for wid in np.atleast_1d(fixture[field]).reshape(-1)]


def _mass_da(counts: dict[str, Any], weights: dict[str, float]) -> tuple[float, int]:
    total = 0.0
    seen = 0
    for wid, count in counts.items():
        mw = weights.get(wid)
        if mw is not None and mw >= 0.0:
            total += float(count) * mw
            seen += 1
    return total, seen


@dataclass(frozen=True)
class CellMassProjection:
    """Cached source weights and ownership; every projection reads live counts.

    ProteinMonomer.m:95-130 defines the form rows; existing protein producers
    define the legacy queues. ProteinActivation's incumbent regulated monomers
    own active noncytosol and inactive pools, not additional activity views.
    ProteinComplex.m:101-120 supplies existing mature/inactivated complex rows.
    """

    substrate_mw: dict[str, float]
    rna_mw_by_store: dict[str, dict[str, float]]
    protein_mw: dict[str, float]
    migrated_wids: frozenset[str]
    protein_compartments: tuple[str, ...]
    protein_form_mw: dict[str, dict[str, float]]
    protein_queue_mw: dict[str, dict[str, float]]
    activation_mw_by_store: dict[str, dict[str, float]]
    activation_compartments: dict[str, tuple[str, ...]]
    complex_mw: dict[str, float]
    complex_activation_mw_by_store: dict[str, dict[str, float]]
    complex_activation_compartments: dict[str, tuple[str, ...]]
    source_hashes: dict[str, str]

    @classmethod
    def build(
        cls,
        m1: km.KarrMetabolismModel,
        m2: tx.KarrTranscriptionModel,
        m3: tl.KarrTranslationModel,
    ) -> CellMassProjection:
        # Lazy ownership imports avoid the vivarium package/observer import cycle.
        from opencell.vivarium.karr_protein_activation import (
            _ACTIVE_NONCYTOSOL_COUNTS,
            _INACTIVE_COUNTS,
            _REGULATED_PROTEINS,
        )
        from opencell.vivarium.protein_state import COMPARTMENTS, MIGRATED_WIDS

        source_hashes: dict[str, str] = {}
        fx = _protein_fixture("ProteinMonomer", source_hashes)
        wids = _fixture_wids(fx, "wholeCellModelIDs")
        mw = np.asarray(fx["molecularWeights"], dtype=float).reshape(-1)
        if len(wids) != mw.size or not np.all(np.isfinite(mw) & (mw >= 0)):
            raise RuntimeError("ProteinMonomer weights do not match its source rows.")
        if np.asarray(fx["counts"]).shape != (len(wids), len(COMPARTMENTS)):
            raise RuntimeError("ProteinMonomer source compartment axes do not match.")
        fields = {
            "nascent": "nascentIndexs",
            "processed_i": "processedIIndexs",
            "processed_ii": "processedIIIndexs",
            "signal_sequence": "signalSequenceIndexs",
            "folded": "foldedIndexs",
            "mature": "matureIndexs",
            "inactivated": "inactivatedIndexs",
            "bound": "boundIndexs",
            "misfolded": "misfoldedIndexs",
            "damaged": "damagedIndexs",
        }
        rows = {
            form: np.asarray(fx[field], dtype=int).reshape(-1) - 1
            for form, field in fields.items()
        }
        forms = {}
        for form, indices in rows.items():
            keys = [wids[row] for row in indices]
            if len(keys) != len(set(keys)):
                raise RuntimeError(f"ProteinMonomer {form} WIDs do not identify source rows.")
            forms[form] = dict(zip(keys, mw[indices].tolist(), strict=True))
        migrated = frozenset(MIGRATED_WIDS)
        queue_sources = {
            "unprocessed_counts": ("ProteinProcessingI", "unprocessedMonomerWholeCellModelIDs", "nascent"),
            "processed_counts": ("ProteinProcessingII", "unprocessedMonomerWholeCellModelIDs", "processed_i"),
            "unfolded_counts": ("ProteinProcessingII", "processedMonomerWholeCellModelIDs", "processed_ii"),
            "signal_sequence_counts": ("ProteinProcessingII", "signalSequenceMonomerWholeCellModelIDs", "signal_sequence"),
            "unmodified_counts": ("ProteinModification", "unmodifiedMonomerWholeCellModelIDs", "folded"),
            "modified_counts": ("ProteinModification", "modifiedMonomerWholeCellModelIDs", "mature"),
        }
        fixtures = {
            name: _protein_fixture(name, source_hashes)
            for name in {source[0] for source in queue_sources.values()}
        }
        queues = {
            store: {
                wid: forms[form][wid]
                for wid in _fixture_wids(fixtures[name], field)
                if wid not in migrated
            }
            for store, (name, field, form) in queue_sources.items()
        }
        activation = _protein_fixture("ProteinActivation", source_hashes)
        activation_wids = _fixture_wids(activation, "substrateWholeCellModelIDs")
        local_rows = np.asarray(activation["substrateMonomerLocalIndexs"], dtype=int).reshape(-1) - 1
        global_rows = np.asarray(activation["substrateMonomerGlobalIndexs"], dtype=int) - 1
        compartments = np.asarray(activation["substrateMonomerCompartmentIndexs"], dtype=int) - 1
        owners = {}
        for local, global_row, by_comp in zip(local_rows, global_rows, compartments, strict=True):
            wid = activation_wids[local]
            if not np.all(global_row == global_row[0]) or wids[rows["mature"][global_row[0]]] != wid:
                raise RuntimeError(f"ProteinActivation monomer source-row mismatch: {wid}")
            if wid in _REGULATED_PROTEINS and wid not in migrated:
                owners[wid] = tuple(str(comp) for comp in by_comp)
        if owners and len(set(owners.values())) != 1:
            raise RuntimeError("ProteinActivation monomer compartment axes disagree.")
        compartment_keys = next(iter(owners.values()), ())
        complex_fx = _protein_fixture("ProteinComplex", source_hashes)
        complex_wids = _fixture_wids(complex_fx, "wholeCellModelIDs")
        complex_mw = np.asarray(complex_fx["molecularWeights"], dtype=float).reshape(-1)
        if len(complex_wids) != complex_mw.size or not np.all(np.isfinite(complex_mw) & (complex_mw >= 0)):
            raise RuntimeError("ProteinComplex weights do not match its source rows.")
        if np.asarray(complex_fx["counts"]).shape != (len(complex_wids), len(COMPARTMENTS)):
            raise RuntimeError("ProteinComplex source compartment axes do not match.")
        complex_rows = {
            form: np.asarray(complex_fx[field], dtype=int).reshape(-1) - 1
            for form, field in (("mature", "matureIndexs"), ("inactivated", "inactivatedIndexs"))
        }
        complex_forms = {}
        for form, indices in complex_rows.items():
            keys = [complex_wids[row] for row in indices]
            if len(keys) != len(set(keys)):
                raise RuntimeError(f"ProteinComplex {form} WIDs do not identify source rows.")
            complex_forms[form] = dict(zip(keys, complex_mw[indices].tolist(), strict=True))
        complex_owners = {}
        for local, global_row, by_comp in zip(
            np.asarray(activation["substrateComplexLocalIndexs"], dtype=int).reshape(-1) - 1,
            np.asarray(activation["substrateComplexGlobalIndexs"], dtype=int) - 1,
            np.asarray(activation["substrateComplexCompartmentIndexs"], dtype=int) - 1,
            strict=True,
        ):
            wid = activation_wids[local]
            if not np.all(global_row == global_row[0]) or complex_wids[complex_rows["mature"][global_row[0]]] != wid:
                raise RuntimeError(f"ProteinActivation complex source-row mismatch: {wid}")
            if wid in _REGULATED_PROTEINS:
                complex_owners[wid] = tuple(str(comp) for comp in by_comp)
        if complex_owners and len(set(complex_owners.values())) != 1:
            raise RuntimeError("ProteinActivation complex compartment axes disagree.")
        complex_compartments = next(iter(complex_owners.values()), ())
        return cls(
            substrate_mw=_load_substrate_mw(m1),
            rna_mw_by_store=load_rna_form_mw(m2),
            protein_mw=_load_protein_mw(m3),
            migrated_wids=migrated,
            protein_compartments=COMPARTMENTS,
            protein_form_mw=forms,
            protein_queue_mw=queues,
            activation_mw_by_store={
                _ACTIVE_NONCYTOSOL_COUNTS: {wid: forms["mature"][wid] for wid in owners},
                _INACTIVE_COUNTS: {wid: forms["inactivated"][wid] for wid in owners},
            },
            activation_compartments={
                _ACTIVE_NONCYTOSOL_COUNTS: compartment_keys[1:],
                _INACTIVE_COUNTS: compartment_keys,
            },
            complex_mw={
                wid: weight for wid, weight in complex_forms["mature"].items()
                if wid not in forms["mature"]
            },
            complex_activation_mw_by_store={
                _ACTIVE_NONCYTOSOL_COUNTS: {
                    wid: complex_forms["mature"][wid] for wid in complex_owners
                },
                _INACTIVE_COUNTS: {
                    wid: complex_forms["inactivated"][wid] for wid in complex_owners
                },
            },
            complex_activation_compartments={
                _ACTIVE_NONCYTOSOL_COUNTS: complex_compartments[1:],
                _INACTIVE_COUNTS: complex_compartments,
            },
            source_hashes=source_hashes,
        )

    def compute(self, state: dict[str, Any]) -> CellMassBreakdown:
        """Project only existing physical owners; never use phenotype hints."""
        substrates = state.get("substrates") or {}
        rna = state.get("rna") or {}
        protein = state.get("protein") or {}
        sub_da, sub_seen = _mass_da(substrates, self.substrate_mw)
        rna_parts = [
            _mass_da(rna.get(store) or {}, weights)
            for store, weights in self.rna_mw_by_store.items()
        ]
        rna_da = sum(part[0] for part in rna_parts)
        rna_seen = sum(part[1] for part in rna_parts)
        canonical = protein.get("compartment_counts") or {}
        migrated = self.migrated_wids
        flat = {
            wid: count for wid, count in (protein.get("counts") or {}).items()
            if not canonical or wid not in migrated
        }
        prot_da, prot_seen = _mass_da(flat, self.protein_mw)
        prot_total = len(flat)
        for form, by_wid in canonical.items():
            weights = self.protein_form_mw.get(form, {})
            for wid, by_comp in by_wid.items():
                if wid not in migrated or wid not in weights:
                    continue
                counts = {
                    comp: count for comp, count in by_comp.items()
                    if comp in self.protein_compartments
                }
                mass, seen = _mass_da(counts, dict.fromkeys(counts, weights[wid]))
                prot_da += mass
                prot_seen += seen
                prot_total += len(counts)
        for store, weights in self.protein_queue_mw.items():
            counts = protein.get(store) or {}
            mass, seen = _mass_da(counts, weights)
            prot_da += mass
            prot_seen += seen
            prot_total += len(counts)
        for store, weights in self.activation_mw_by_store.items():
            for wid, by_comp in (protein.get(store) or {}).items():
                if wid not in weights:
                    continue
                counts = {
                    comp: count for comp, count in by_comp.items()
                    if comp in self.activation_compartments[store]
                }
                mass, seen = _mass_da(counts, dict.fromkeys(counts, weights[wid]))
                prot_da += mass
                prot_seen += seen
                prot_total += len(counts)
        monomer_da = prot_da
        complex_state = state.get("complex") or {}
        complex_da, complex_seen = _mass_da(complex_state.get("counts") or {}, self.complex_mw)
        prot_total += len(complex_state.get("counts") or {})
        for store, weights in self.complex_activation_mw_by_store.items():
            for wid, by_comp in (complex_state.get(store) or {}).items():
                if wid not in weights:
                    continue
                counts = {
                    comp: count for comp, count in by_comp.items()
                    if comp in self.complex_activation_compartments[store]
                }
                mass, seen = _mass_da(counts, dict.fromkeys(counts, weights[wid]))
                complex_da += mass
                complex_seen += seen
                prot_total += len(counts)
        prot_da += complex_da
        prot_seen += complex_seen
        sub_g, rna_g, prot_g = (value / AVOGADRO for value in (sub_da, rna_da, prot_da))
        return CellMassBreakdown(
            substrate_mass_g=sub_g,
            rna_mass_g=rna_g,
            protein_mass_g=prot_g,
            total_g=sub_g + rna_g + prot_g,
            extra={
                "substrate_da": sub_da,
                "rna_da": rna_da,
                "protein_da": prot_da,
                "protein_monomer_da": monomer_da,
                "protein_complex_da": complex_da,
                "source_hashes": dict(self.source_hashes),
                "n_substrates_with_mw": sub_seen,
                "n_rnas_with_mw": rna_seen,
                "n_proteins_with_mw": prot_seen,
                "n_substrates_total": len(substrates),
                "n_rnas_total": sum(len(rna.get(store) or {}) for store in self.rna_mw_by_store),
                "n_proteins_total": prot_total,
            },
        )


def compute_cell_mass(
    state: dict[str, Any],
    m1: km.KarrMetabolismModel,
    m2: tx.KarrTranscriptionModel,
    m3: tl.KarrTranslationModel,
) -> CellMassBreakdown:
    """Return physical substrate/RNA/protein grams from a live engine state.

    Counts are molecules per cell; weights are source Daltons. Repeated readers
    can build a CellMassProjection once without caching any mutable counts.
    """
    return CellMassProjection.build(m1, m2, m3).compute(state)


__all__ = [
    "AVOGADRO",
    "CellMassBreakdown",
    "CellMassProjection",
    "compute_cell_mass",
    "load_rna_form_mw",
]
