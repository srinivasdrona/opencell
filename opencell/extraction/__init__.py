"""Deterministic parameter-extraction pipeline.

Produces an *auditable evidence set* for a requested parameter — never a
single "best guess".  Surfaces all candidate hits from cached PDF text and
optionally BioModels SBML, tags each candidate with a locator and rejection
reason, and emits a DRAFT ParameterCard only when uniqueness is *semantic*
(not merely numeric).

The whole point: zero-hallucination.  Every value emitted by this module
must be traceable to a verbatim character span in a hashed source file.
"""

from .candidate import (
    ExtractionCandidate,
    ExtractionResult,
    SectionType,
)
from .pipeline import ParameterSpec, extract_parameter

__all__ = [
    "ExtractionCandidate",
    "ExtractionResult",
    "ParameterSpec",
    "SectionType",
    "extract_parameter",
]
