"""Data classes for extraction candidates and results."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class SectionType(enum.Enum):
    """Where in the source artifact the hit was located."""

    CAPTION = "caption"
    TABLE = "table"
    BODY = "body"
    SBML = "sbml"
    REFS = "refs"
    UNKNOWN = "unknown"


@dataclass
class ExtractionCandidate:
    """One possible value found in the source.

    All fields are derived deterministically from the cached source text;
    no field is filled by inference or LLM rewriting.
    """

    raw_value: float
    raw_unit: str
    raw_unit_normalized: str

    method: str
    locator: str
    context_window: str
    section_type: SectionType = SectionType.UNKNOWN

    score: float = 0.0
    score_components: dict[str, float] = field(default_factory=dict)
    rejection_reason: str = ""

    convertible_to_target: bool | None = None
    converted_value: float | None = None
    converted_unit: str = ""
    transformation: str = ""

    source_path: str = ""
    source_sha256: str = ""
    extractor_version: str = ""

    @property
    def rejected(self) -> bool:
        return bool(self.rejection_reason)

    def to_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items()}
        d["section_type"] = self.section_type.value
        return d


@dataclass
class ExtractionResult:
    """Outcome of a parameter-extraction run.

    Always returns *all* candidates (rejected and surviving), so the human
    has a full audit trail.
    """

    parameter_symbol: str
    parameter_doi: str
    target_unit: str

    candidates: list[ExtractionCandidate] = field(default_factory=list)
    cache_files: list[str] = field(default_factory=list)
    methods_attempted: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def surviving(self) -> list[ExtractionCandidate]:
        return [c for c in self.candidates if not c.rejected]

    @property
    def rejected(self) -> list[ExtractionCandidate]:
        return [c for c in self.candidates if c.rejected]

    @property
    def status(self) -> str:
        n = len(self.surviving)
        if n == 0:
            return "NOT_FOUND" if not self.candidates else "ALL_REJECTED"
        values = {round(c.raw_value, 12) for c in self.surviving}
        if n == 1 or len(values) == 1:
            best = max(self.surviving, key=lambda c: c.score)
            return "RECOMMEND" if best.score >= 0.6 else "AMBIGUOUS"
        return "AMBIGUOUS"

    @property
    def recommendation(self) -> ExtractionCandidate | None:
        """Single best candidate iff uniqueness is *semantic* (score >= 0.6
        AND all surviving candidates agree on raw_value)."""
        survivors = self.surviving
        if not survivors:
            return None
        values = {round(c.raw_value, 12) for c in survivors}
        if len(values) > 1:
            return None
        best = max(survivors, key=lambda c: c.score)
        if best.score < 0.6:
            return None
        return best
