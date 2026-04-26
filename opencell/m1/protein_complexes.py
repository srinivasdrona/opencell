"""Karr-native protein complex composition.

Loads `data/karr_fixtures/karr_protein_complexes.json` (Karr's 201
ProteinComplex records with full composition) and provides a typed
lookup API.

Composition convention (Karr KB):
    Each complex assembles from N >= 1 ProteinMonomer subunits, plus
    optional sub-complexes, metabolites (cofactors, metal ions),
    prosthetic groups, RNAs (rRNAs in ribosomes), and chaperone
    substrates. All participant coefficients are *positive integers*
    counting copies needed per assembled complex (e.g., DNA_GYRASE
    needs 2 x MG_003_MONOMER + 2 x MG_004_MONOMER).

Used by:
    * Phase D.0+ chassis: resolve enzyme-complex demand into per-monomer
      pull on the protein pool.
    * Future: stoichiometric coupling of complex formation to the M3
      protein synthesis sub-model.

This module performs no MAT access; the JSON fixture is the sole runtime
input.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

DEFAULT_FIXTURE_JSON = (
    Path(__file__).resolve().parents[2]
    / "data" / "karr_fixtures" / "karr_protein_complexes.json"
)

SCHEMA_VERSION = "karr_protein_complexes__v1"


@dataclass(frozen=True)
class Participant:
    molecule_wid: str
    coefficient: float
    compartment_wid: str


@dataclass
class Complex:
    wid: str
    name: str
    idx_1based: int
    num_subunits: int
    num_distinct_subunits: int
    formation_compartment_wid: str
    monomers: list[Participant] = field(default_factory=list)
    subcomplexes: list[Participant] = field(default_factory=list)
    metabolites: list[Participant] = field(default_factory=list)
    prosthetic: list[Participant] = field(default_factory=list)
    chaperones: list[Participant] = field(default_factory=list)
    rnas: list[Participant] = field(default_factory=list)
    activation_rule: str = ""
    dna_footprint: int = 0
    density: float = 0.0


@dataclass
class ComplexCompositionModel:
    schema_version: str
    complexes: dict[str, Complex]
    compartment_wids: list[str]
    counts: dict
    raw: dict = field(repr=False)

    # ---- basic queries ----

    def __contains__(self, wid: str) -> bool:
        return wid in self.complexes

    def __getitem__(self, wid: str) -> Complex:
        return self.complexes[wid]

    def get(self, wid: str) -> Complex | None:
        return self.complexes.get(wid)

    def all_wids(self) -> list[str]:
        return list(self.complexes.keys())

    def composition(self, wid: str) -> dict[str, list[Participant]]:
        c = self.complexes[wid]
        return {
            "monomers": list(c.monomers),
            "subcomplexes": list(c.subcomplexes),
            "metabolites": list(c.metabolites),
            "prosthetic": list(c.prosthetic),
            "chaperones": list(c.chaperones),
            "rnas": list(c.rnas),
        }

    def formation_compartment(self, wid: str) -> str:
        return self.complexes[wid].formation_compartment_wid

    # ---- recursive resolution ----

    def flatten_to_monomers(
        self,
        wid: str,
        copies: float = 1.0,
        _stack: tuple[str, ...] = (),
    ) -> dict[str, float]:
        """Recursively expand a complex into its leaf-level ProteinMonomer
        requirements.

        Returns a dict mapping ProteinMonomer WCM ID -> total monomer
        copies required to assemble `copies` units of `wid`. Sub-complexes
        are resolved through their own `monomers`+`subcomplexes` until
        only ProteinMonomers remain. Metabolites, prosthetic groups, RNAs,
        and chaperone substrates are NOT included (use `flatten_full`
        for those).

        Raises:
            ValueError if a sub-complex cycle is detected.
            KeyError   if a sub-complex WCM ID is not in the fixture.
        """
        if wid in _stack:
            cycle = " -> ".join((*_stack, wid))
            raise ValueError(f"complex sub-complex cycle: {cycle}")
        if wid not in self.complexes:
            raise KeyError(f"unknown complex WCM ID: {wid!r}")

        c = self.complexes[wid]
        result: dict[str, float] = {}
        for p in c.monomers:
            result[p.molecule_wid] = result.get(p.molecule_wid, 0.0) + copies * p.coefficient
        for p in c.subcomplexes:
            sub = self.flatten_to_monomers(
                p.molecule_wid,
                copies=copies * p.coefficient,
                _stack=(*_stack, wid),
            )
            for m_wid, m_copies in sub.items():
                result[m_wid] = result.get(m_wid, 0.0) + m_copies
        return result

    def flatten_full(
        self,
        wid: str,
        copies: float = 1.0,
        _stack: tuple[str, ...] = (),
    ) -> dict[str, dict[str, float]]:
        """Recursively expand to leaf participants in all categories.

        Returns a dict with keys 'monomers', 'metabolites', 'prosthetic',
        'rnas', 'chaperones'. Sub-complexes are recursively expanded;
        each leaf category accumulates participants summed across the
        recursion. ProteinMonomer WCM IDs aggregate via
        `flatten_to_monomers`.
        """
        if wid in _stack:
            cycle = " -> ".join((*_stack, wid))
            raise ValueError(f"complex sub-complex cycle: {cycle}")
        if wid not in self.complexes:
            raise KeyError(f"unknown complex WCM ID: {wid!r}")

        c = self.complexes[wid]
        result = {k: {} for k in ("monomers", "metabolites", "prosthetic", "rnas", "chaperones")}

        for cat in ("monomers", "metabolites", "prosthetic", "rnas", "chaperones"):
            for p in getattr(c, cat):
                d = result[cat]
                d[p.molecule_wid] = d.get(p.molecule_wid, 0.0) + copies * p.coefficient

        for p in c.subcomplexes:
            sub = self.flatten_full(
                p.molecule_wid,
                copies=copies * p.coefficient,
                _stack=(*_stack, wid),
            )
            for cat, items in sub.items():
                d = result[cat]
                for m_wid, m_copies in items.items():
                    d[m_wid] = d.get(m_wid, 0.0) + m_copies
        return result

    def monomers_required(self, demand: dict[str, float]) -> dict[str, float]:
        """Convert a map of complex_wid->copies-needed into per-monomer
        copies-needed by recursively flattening each demanded complex."""
        out: dict[str, float] = {}
        for wid, copies in demand.items():
            for m_wid, m_copies in self.flatten_to_monomers(wid, copies).items():
                out[m_wid] = out.get(m_wid, 0.0) + m_copies
        return out


def load_default(path: str | Path | None = None) -> ComplexCompositionModel:
    p = Path(path) if path is not None else DEFAULT_FIXTURE_JSON
    if not p.exists():
        raise FileNotFoundError(
            f"Run `python scripts/karr_native_ingest_complexes.py` first; missing {p}"
        )
    raw = json.loads(p.read_text())
    if raw["schema_version"] != SCHEMA_VERSION:
        raise ValueError(
            f"Schema version mismatch: fixture={raw['schema_version']!r} "
            f"expected={SCHEMA_VERSION!r}"
        )

    complexes: dict[str, Complex] = {}
    for entry in raw["complexes"]:
        wid = entry["wid"]
        complexes[wid] = Complex(
            wid=wid,
            name=entry["name"],
            idx_1based=int(entry["idx_1based"]),
            num_subunits=int(entry["num_subunits"]),
            num_distinct_subunits=int(entry["num_distinct_subunits"]),
            formation_compartment_wid=entry.get("formation_compartment_wid", ""),
            activation_rule=entry.get("activation_rule", ""),
            dna_footprint=int(entry.get("dna_footprint", 0)),
            density=float(entry.get("density", 0.0)),
            monomers=[Participant(**p) for p in entry["monomers"]],
            subcomplexes=[Participant(**p) for p in entry["subcomplexes"]],
            metabolites=[Participant(**p) for p in entry["metabolites"]],
            prosthetic=[Participant(**p) for p in entry["prosthetic"]],
            chaperones=[Participant(**p) for p in entry["chaperones"]],
            rnas=[Participant(**p) for p in entry["rnas"]],
        )

    return ComplexCompositionModel(
        schema_version=raw["schema_version"],
        complexes=complexes,
        compartment_wids=list(raw.get("compartment_wids", [])),
        counts=dict(raw.get("counts", {})),
        raw=raw,
    )
