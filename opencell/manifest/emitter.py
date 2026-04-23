"""Manifest emitter: turn parsed SBML entities into a YAML manifest.

The manifest format is the input contract for the upcoming
``biology-curator`` agent.  Each entry is one parameter the curator
will attempt to extract via the ``param-extractor`` skill.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable

import yaml

from .sbml import SbmlEntity


# ---------------------------------------------------------------------------
# Manifest data classes
# ---------------------------------------------------------------------------

@dataclass
class ManifestHeader:
    """Paper-level metadata; applies to all entries unless overridden."""

    doi: str = ""
    biomodels_id: str = ""
    pubmed_id: str = ""              # structured; verifier uses this directly
    pdf_cache: list[str] = field(default_factory=list)
    organism: str = ""
    condition: str = ""
    notes: str = ""


@dataclass
class ManifestEntry:
    """One parameter the curator will try to extract."""

    parameter_id: str
    symbol: str                # symbol as written in paper (defaults to sbml_id; humans should refine)
    name: str = ""
    target_unit: str = ""      # resolved unit string from SBML
    sbml_id: str = ""          # the original SBML id (audit trail)
    sbml_value: float | None = None  # the curated SBML value (cross-check anchor)
    sbml_kind: str = ""        # global_parameter | local_parameter | species_initial
    parent_reaction: str = ""
    compartment: str = ""
    gene_or_enzyme: str = ""

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if v not in ("", None, [])}
        # Ensure parameter_id, symbol, target_unit always present (even if empty)
        for required in ("parameter_id", "symbol", "target_unit"):
            d.setdefault(required, getattr(self, required))
        return d


# ---------------------------------------------------------------------------
# Conversions
# ---------------------------------------------------------------------------

def _slugify(s: str) -> str:
    """Normalize SBML id into a parameter_id-friendly slug."""
    return "".join(c if c.isalnum() else "_" for c in s).strip("_").lower()


def entity_to_entry(entity: SbmlEntity, *, model_slug: str) -> ManifestEntry:
    """Turn one SbmlEntity into a draft ManifestEntry."""
    pid = f"{model_slug}-{_slugify(entity.sbml_id)}"
    return ManifestEntry(
        parameter_id=pid,
        symbol=entity.sbml_id,
        name=entity.name,
        target_unit=entity.units_resolved,
        sbml_id=entity.sbml_id,
        sbml_value=entity.value,
        sbml_kind=entity.kind,
        parent_reaction=entity.parent_reaction,
        compartment=entity.compartment,
    )


def build_manifest(
    entities: Iterable[SbmlEntity],
    *,
    header: ManifestHeader,
    model_slug: str,
) -> dict:
    """Assemble the full manifest dict ready for YAML serialization."""
    entries = [entity_to_entry(e, model_slug=model_slug) for e in entities]
    # Deduplicate by parameter_id (local kinetic params can collide across reactions
    # if SBML reuses ids; we disambiguate by appending the reaction id)
    seen: dict[str, ManifestEntry] = {}
    for e in entries:
        if e.parameter_id in seen and e.parent_reaction:
            e.parameter_id = f"{e.parameter_id}-{_slugify(e.parent_reaction)}"
        seen[e.parameter_id] = e

    return {
        "manifest_version": "0.1",
        "generated_on": date.today().isoformat(),
        "generator": "opencell.manifest/0.1",
        "model_slug": model_slug,
        "paper": {
            "doi": header.doi,
            "biomodels_id": header.biomodels_id,
            "pubmed_id": header.pubmed_id,
            "pdf_cache": header.pdf_cache,
            "organism": header.organism,
            "condition": header.condition,
            "notes": header.notes,
        },
        "parameters": [e.to_dict() for e in seen.values()],
    }


def write_manifest_yaml(manifest: dict, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        yaml.dump(manifest, fh, default_flow_style=False, sort_keys=False)
