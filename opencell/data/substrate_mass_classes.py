"""Fixture-backed substrate mass lookup and polymer-class assignment.

This module builds two maps used by CSV bridge tooling:

* molecular weight (g/mol) by substrate WID
* polymer class by substrate WID (dna/rna/protein/other)

The lookup is intentionally conservative:

* RNA classes come from authoritative M2 gene types.
* Protein classes come from authoritative M3 protein WIDs.
* DNA class is only assigned to explicit chromosome-like WIDs to avoid
  misclassifying protein complexes such as ``DNA_GYRASE``.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

AVOGADRO = 6.02214076e23
PolymerClass = Literal["dna", "rna", "protein", "other"]

_RNA_GENE_TYPES = {"mrna", "trna", "rrna", "srna"}
_DNA_FALLBACK_PATTERNS = (
    re.compile(r"^CHROMOSOME(?:_|$)", re.IGNORECASE),
    re.compile(r"^DNA_CHROM", re.IGNORECASE),
    re.compile(r"^DNA_STRAND", re.IGNORECASE),
)
_RNA_FALLBACK_PATTERNS = (
    re.compile(r"^TU_", re.IGNORECASE),
    re.compile(r"^RNA_", re.IGNORECASE),
    re.compile(r"_RNA$", re.IGNORECASE),
)
_PROTEIN_FALLBACK_PATTERNS = (
    re.compile(r"_MONOMER(?:_.*)?$", re.IGNORECASE),
    re.compile(r"_(?:DI|TRI|TETRA|PENTA|HEXA)MER(?:_.*)?$", re.IGNORECASE),
    re.compile(r"^RIBOSOME_", re.IGNORECASE),
    re.compile(r"^DNA_GYRASE$", re.IGNORECASE),
)


@dataclass(frozen=True)
class SubstrateMassClassLookup:
    """Resolved lookup for substrate MW and polymer class."""

    mw_by_substrate: dict[str, float]
    class_by_substrate: dict[str, PolymerClass]

    def mw_g_per_mol(self, wid: str) -> float:
        value = self.mw_by_substrate.get(str(wid), float("nan"))
        return float(value) if math.isfinite(value) else float("nan")

    def polymer_class(self, wid: str) -> PolymerClass:
        sid = str(wid)
        explicit = self.class_by_substrate.get(sid)
        if explicit is not None:
            return explicit
        if _matches_any(sid, _DNA_FALLBACK_PATTERNS):
            return "dna"
        if _matches_any(sid, _RNA_FALLBACK_PATTERNS):
            return "rna"
        if _matches_any(sid, _PROTEIN_FALLBACK_PATTERNS):
            return "protein"
        return "other"


def _matches_any(value: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(value) for pattern in patterns)


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected dict JSON payload at {path}")
    return payload


def _load_npz_array(path: Path, key: str) -> np.ndarray:
    payload = np.load(path, allow_pickle=False)
    if key not in payload.files:
        raise KeyError(f"{path} missing required array: {key}")
    return np.asarray(payload[key], dtype=float).reshape(-1)


def build_substrate_mass_class_lookup(repo_root: Path | None = None) -> SubstrateMassClassLookup:
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    fixtures = root / "data" / "karr_fixtures"

    m1_json = _load_json(fixtures / "karr_native_m1.json")
    m2_json = _load_json(fixtures / "karr_native_m2.json")
    m3_json = _load_json(fixtures / "karr_native_m3.json")

    m1_ids = [str(x) for x in m1_json["ids"]["substrate_wcm_585"]]
    m2_ids = [str(x) for x in m2_json["ids"]["gene_wcm_525"]]
    m2_types = [str(x) for x in m2_json["ids"]["gene_types_525"]]
    m3_ids = [str(x) for x in m3_json["ids"]["protein_wcm_482"]]

    m1_mw = _load_npz_array(fixtures / "karr_native_m1.npz", "substrate_molecular_weight")
    m2_mw = _load_npz_array(fixtures / "karr_native_m2.npz", "rna_molecular_weight")
    m3_mw = _load_npz_array(fixtures / "karr_native_m3.npz", "molecular_weight")

    if len(m1_ids) != m1_mw.size:
        raise ValueError(f"M1 substrate ID/MW size mismatch: {len(m1_ids)} vs {m1_mw.size}")
    if len(m2_ids) != m2_mw.size:
        raise ValueError(f"M2 gene ID/MW size mismatch: {len(m2_ids)} vs {m2_mw.size}")
    if len(m2_ids) != len(m2_types):
        raise ValueError(f"M2 gene ID/type size mismatch: {len(m2_ids)} vs {len(m2_types)}")
    if len(m3_ids) != m3_mw.size:
        raise ValueError(f"M3 protein ID/MW size mismatch: {len(m3_ids)} vs {m3_mw.size}")

    mw_by_substrate: dict[str, float] = {}
    for wid, mw in zip(m1_ids, m1_mw, strict=False):
        mw_by_substrate[wid] = float(mw)
    for wid, mw in zip(m2_ids, m2_mw, strict=False):
        mw_by_substrate[wid] = float(mw)
    for wid, mw in zip(m3_ids, m3_mw, strict=False):
        mw_by_substrate[wid] = float(mw)

    class_by_substrate: dict[str, PolymerClass] = {}
    for wid, gene_type in zip(m2_ids, m2_types, strict=False):
        if gene_type.strip().lower() in _RNA_GENE_TYPES:
            class_by_substrate[wid] = "rna"
    for wid in m3_ids:
        if wid not in class_by_substrate:
            class_by_substrate[wid] = "protein"

    # No explicit DNA list is available in the fixture IDs; assign DNA
    # class only to explicit chromosome-like identifiers by pattern.
    for wid in m1_ids:
        if wid in class_by_substrate:
            continue
        if _matches_any(wid, _DNA_FALLBACK_PATTERNS):
            class_by_substrate[wid] = "dna"

    return SubstrateMassClassLookup(
        mw_by_substrate=mw_by_substrate,
        class_by_substrate=class_by_substrate,
    )


__all__ = [
    "AVOGADRO",
    "PolymerClass",
    "SubstrateMassClassLookup",
    "build_substrate_mass_class_lookup",
]
