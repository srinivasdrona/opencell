"""Cross-check guardrail: PDF-extracted value vs SBML curated value.

When both an authoritative SBML value and a PDF-extracted recommendation exist
for the same parameter, this module decides whether they agree numerically.

Design notes (responding to rubber-duck critique):
- We compare the *recommended candidate's value*, not free-text from the
  quote. Free-text contains unrelated numbers (table indices, ranges, CIs,
  neighboring params) and would produce false positives.
- We use the candidate's `converted_value` (already in the manifest entry's
  target_unit, which is the SBML's resolved unit). If unit conversion failed
  upstream, we report NO_UNIT_MATCH instead of guessing.
- DISAGREE is a *blocking* signal: callers should downgrade the outcome from
  RECOMMEND to AMBIGUOUS so the mismatch is never silently auto-approved.
- We skip when the recommendation came from BioModels SBML itself (no
  tautological self-verification).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from opencell.extraction.candidate import ExtractionCandidate


# Status constants (use strings, not Enum, to keep YAML/JSON round-trip simple)
AGREE = "AGREE"
DISAGREE = "DISAGREE"
NO_SBML = "NO_SBML"                  # manifest entry has no sbml_value to compare against
NO_PDF_VALUE = "NO_PDF_VALUE"        # no PDF-derived recommendation
NO_UNIT_MATCH = "NO_UNIT_MATCH"      # PDF candidate not convertible to entry's target_unit
SKIPPED_SAME_SOURCE = "SKIPPED_SAME_SOURCE"  # recommendation came from the SBML itself


# Method strings produced by extractors that are NOT independent of SBML.
_SBML_DERIVED_METHODS = {"biomodels_sbml"}


@dataclass
class CrossCheck:
    """Outcome of a single PDF-vs-SBML value comparison."""

    status: str
    pdf_value: Optional[float] = None
    sbml_value: Optional[float] = None
    rel_diff: Optional[float] = None     # |pdf - sbml| / |sbml|, when both present
    rel_tol: float = 0.01
    abs_tol: float = 1e-12
    note: str = ""

    @property
    def disagrees(self) -> bool:
        return self.status == DISAGREE

    def to_dict(self) -> dict:
        out: dict = {"status": self.status, "rel_tol": self.rel_tol, "abs_tol": self.abs_tol}
        if self.pdf_value is not None:
            out["pdf_value"] = self.pdf_value
        if self.sbml_value is not None:
            out["sbml_value"] = self.sbml_value
        if self.rel_diff is not None:
            out["rel_diff"] = self.rel_diff
        if self.note:
            out["note"] = self.note
        return out


def cross_check(
    candidate: ExtractionCandidate | None,
    sbml_value: float | None,
    *,
    rel_tol: float = 0.01,
    abs_tol: float = 1e-12,
) -> CrossCheck:
    """Compare a PDF-derived recommendation candidate against the SBML value.

    Args:
      candidate: the recommended ExtractionCandidate (or None if no recommendation).
      sbml_value: the curated SBML value from the manifest entry (or None).
      rel_tol: relative tolerance (default 1%).
      abs_tol: absolute tolerance floor for very small values (default 1e-12).

    Returns:
      A CrossCheck describing the outcome. Never raises; always returns a status.
    """
    if sbml_value is None:
        return CrossCheck(status=NO_SBML, rel_tol=rel_tol, abs_tol=abs_tol)
    if candidate is None:
        return CrossCheck(
            status=NO_PDF_VALUE,
            sbml_value=float(sbml_value),
            rel_tol=rel_tol,
            abs_tol=abs_tol,
        )
    # Don't verify SBML against SBML.
    if candidate.method in _SBML_DERIVED_METHODS:
        return CrossCheck(
            status=SKIPPED_SAME_SOURCE,
            pdf_value=candidate.converted_value if candidate.converted_value is not None
                      else candidate.raw_value,
            sbml_value=float(sbml_value),
            rel_tol=rel_tol,
            abs_tol=abs_tol,
            note=f"recommendation method={candidate.method!r} is derived from SBML",
        )
    pdf_value = candidate.converted_value
    if pdf_value is None:
        # No reliable conversion to entry's target unit; can't compare meaningfully.
        return CrossCheck(
            status=NO_UNIT_MATCH,
            pdf_value=candidate.raw_value,
            sbml_value=float(sbml_value),
            rel_tol=rel_tol,
            abs_tol=abs_tol,
            note=(f"PDF candidate raw_unit={candidate.raw_unit!r} not convertible "
                  f"to manifest target_unit; cannot perform numeric comparison"),
        )

    pdf_f = float(pdf_value)
    sbml_f = float(sbml_value)
    matched = math.isclose(pdf_f, sbml_f, rel_tol=rel_tol, abs_tol=abs_tol)
    rel_diff = abs(pdf_f - sbml_f) / abs(sbml_f) if sbml_f != 0 else float("inf")
    return CrossCheck(
        status=AGREE if matched else DISAGREE,
        pdf_value=pdf_f,
        sbml_value=sbml_f,
        rel_diff=rel_diff,
        rel_tol=rel_tol,
        abs_tol=abs_tol,
    )
