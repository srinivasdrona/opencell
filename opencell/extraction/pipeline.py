"""Pipeline orchestrator: combine PDF grep + BioModels into one ExtractionResult."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .candidate import ExtractionResult
from .pdf_grep import GrepConfig, grep_file


@dataclass
class ParameterSpec:
    """Inputs for a single extraction run."""

    symbol: str                         # symbol as written in the paper, e.g. "k_R"
    doi: str = ""
    target_unit: str = ""               # the unit you want the final value in
    name: str = ""                      # human-readable parameter name
    organism: str = ""
    condition: str = ""
    cache_files: list[str] = field(default_factory=list)  # PDF text caches
    use_biomodels: bool = True


def extract_parameter(spec: ParameterSpec) -> ExtractionResult:
    """Run the full extraction pipeline for one parameter.

    Sources are queried *in parallel* (collect from all): BioModels
    corroborates PDF, never replaces it.  All hits — including rejected
    ones — are returned for audit.
    """
    result = ExtractionResult(
        parameter_symbol=spec.symbol,
        parameter_doi=spec.doi,
        target_unit=spec.target_unit,
    )
    cfg = GrepConfig(target_unit=spec.target_unit)

    # 1) PDF grep across all provided cache files
    for cache_path in spec.cache_files:
        p = Path(cache_path)
        if not p.exists():
            result.notes.append(f"cache file not found: {cache_path}")
            continue
        result.cache_files.append(str(p))
        result.methods_attempted.append(f"pdf_grep({p.name})")
        result.candidates.extend(grep_file(p, spec.symbol, config=cfg))

    # 2) BioModels corroboration (best-effort, network may be down)
    if spec.use_biomodels and spec.doi:
        result.methods_attempted.append("biomodels_sbml")
        try:
            from .biomodels import extract_from_biomodels
            result.candidates.extend(extract_from_biomodels(spec.doi, spec.symbol))
        except Exception as e:  # pragma: no cover — defensive
            result.notes.append(f"biomodels lookup failed: {e}")

    return result
