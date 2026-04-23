"""Manifest loader & validator.

Manifest schema (YAML):

    model_slug: thattai2001
    manifest_version: "0.1"
    paper:
      doi: 10.1073/pnas.151588598
      organism: generic prokaryotic gene
      condition: Thattai 2001 base case
    cache_files:
      - .paper_cache/thattai2001_full.txt
    parameters:
      - parameter_id: thattai2001-k1-transcription-rate
        symbol: kR
        target_unit: min^-1
        name: Transcription initiation rate
        # optional per-entry overrides:
        organism: ...
        condition: ...
        compartment: ...
        gene_or_enzyme: ...
        cache_files: [...]   # entry-level overrides paper-level
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ManifestValidationError(ValueError):
    """Raised when a manifest fails schema or semantic validation."""


@dataclass
class ManifestParameter:
    parameter_id: str
    symbol: str
    target_unit: str = ""
    name: str = ""
    organism: str = ""
    condition: str = ""
    compartment: str = ""
    gene_or_enzyme: str = ""
    cache_files: list[str] = field(default_factory=list)
    notes: str = ""
    sbml_value: float | None = None     # cross-check anchor from BioModels SBML
    sbml_id: str = ""                    # original SBML id (audit trail)
    sbml_kind: str = ""                  # global_parameter | local_parameter | species_initial


@dataclass
class CurationManifest:
    model_slug: str
    doi: str
    organism: str = ""
    condition: str = ""
    cache_files: list[str] = field(default_factory=list)
    parameters: list[ManifestParameter] = field(default_factory=list)
    cache_file_sha256: dict[str, str] = field(default_factory=dict)
    manifest_version: str = "0.1"
    source_manifest_path: str = ""
    pubmed_id: str = ""
    biomodels_id: str = ""
    verification: dict = field(default_factory=dict)  # paper.verification block

    def cache_files_for(self, p: ManifestParameter) -> list[str]:
        """Per-entry cache files override paper-level."""
        return p.cache_files if p.cache_files else self.cache_files


# ---------------------------------------------------------------------------
# Loading + validation
# ---------------------------------------------------------------------------

_REQUIRED_PARAM_FIELDS = ("parameter_id", "symbol")


def _validate_dict(d: Any, path: str) -> dict:
    if not isinstance(d, dict):
        raise ManifestValidationError(f"{path}: expected mapping, got {type(d).__name__}")
    return d


def _hash_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(path: str | Path) -> CurationManifest:
    """Load and validate a manifest YAML, hashing all referenced cache files.

    Raises ManifestValidationError on any structural issue.
    """
    p = Path(path)
    if not p.exists():
        raise ManifestValidationError(f"manifest not found: {p}")
    raw = yaml.safe_load(p.read_text()) or {}
    raw = _validate_dict(raw, "<root>")

    if "model_slug" not in raw or not raw["model_slug"]:
        raise ManifestValidationError("manifest missing required field: model_slug")
    paper = _validate_dict(raw.get("paper") or {}, "paper")
    paper_doi = paper.get("doi") or ""
    # NOTE: doi MAY be empty in a draft manifest (verifier or human fills it
    # before extraction). The runner refuses to extract when doi is empty.

    raw_params = raw.get("parameters") or []
    if not isinstance(raw_params, list) or not raw_params:
        raise ManifestValidationError("manifest must have non-empty parameters list")

    seen_ids: set[str] = set()
    parameters: list[ManifestParameter] = []
    for i, entry in enumerate(raw_params):
        e = _validate_dict(entry, f"parameters[{i}]")
        for f in _REQUIRED_PARAM_FIELDS:
            if not e.get(f):
                raise ManifestValidationError(
                    f"parameters[{i}]: missing required field {f!r}"
                )
        pid = e["parameter_id"]
        if pid in seen_ids:
            raise ManifestValidationError(
                f"parameters[{i}]: duplicate parameter_id {pid!r}"
            )
        seen_ids.add(pid)
        parameters.append(ManifestParameter(
            parameter_id=pid,
            symbol=e["symbol"],
            target_unit=e.get("target_unit", "") or "",
            name=e.get("name", "") or "",
            organism=e.get("organism", "") or paper.get("organism", "") or "",
            condition=e.get("condition", "") or paper.get("condition", "") or "",
            compartment=e.get("compartment", "") or "",
            gene_or_enzyme=e.get("gene_or_enzyme", "") or "",
            cache_files=list(e.get("cache_files") or []),
            notes=e.get("notes", "") or "",
            sbml_value=(e.get("sbml_value") if e.get("sbml_value") is not None else None),
            sbml_id=e.get("sbml_id", "") or "",
            sbml_kind=e.get("sbml_kind", "") or "",
        ))

    # Cache files: prefer top-level cache_files; fall back to paper.pdf_cache
    # (the biomodels_manifest emitter writes the latter form).
    paper_caches = list(raw.get("cache_files") or paper.get("pdf_cache") or [])
    manifest = CurationManifest(
        model_slug=raw["model_slug"],
        doi=paper_doi,
        organism=paper.get("organism", "") or "",
        condition=paper.get("condition", "") or "",
        cache_files=paper_caches,
        parameters=parameters,
        manifest_version=str(raw.get("manifest_version", "0.1")),
        source_manifest_path=str(p),
        pubmed_id=str(paper.get("pubmed_id", "") or ""),
        biomodels_id=str(paper.get("biomodels_id", "") or ""),
        verification=dict(paper.get("verification") or {}),
    )

    # Hash all referenced cache files upfront.
    all_caches = set(paper_caches)
    for entry in parameters:
        all_caches.update(entry.cache_files)
    for cf in sorted(all_caches):
        cfp = Path(cf)
        if cfp.exists():
            manifest.cache_file_sha256[cf] = _hash_file(cfp)

    return manifest
