"""Tests for opencell.curation.value_match (PDF↔SBML cross-check guardrail)."""

from __future__ import annotations

import pytest

from opencell.curation.value_match import (
    AGREE,
    DISAGREE,
    NO_PDF_VALUE,
    NO_SBML,
    NO_UNIT_MATCH,
    SKIPPED_SAME_SOURCE,
    cross_check,
)
from opencell.extraction.candidate import ExtractionCandidate, SectionType


def _cand(
    raw_value: float = 1.0,
    converted_value: float | None = 1.0,
    method: str = "pdf_grep",
    raw_unit: str = "min^-1",
) -> ExtractionCandidate:
    return ExtractionCandidate(
        raw_value=raw_value,
        raw_unit=raw_unit,
        raw_unit_normalized=raw_unit,
        method=method,
        locator="L1",
        context_window="ctx",
        section_type=SectionType.CAPTION,
        score=0.9,
        converted_value=converted_value,
        converted_unit="min^-1" if converted_value is not None else "",
        convertible_to_target=converted_value is not None,
        transformation="x" if converted_value is not None else "",
    )


class TestCrossCheckBasics:
    def test_agree_within_tolerance(self):
        xc = cross_check(_cand(converted_value=1.005), 1.000, rel_tol=0.01)
        assert xc.status == AGREE
        assert xc.pdf_value == pytest.approx(1.005)
        assert xc.sbml_value == 1.0
        assert xc.rel_diff is not None and xc.rel_diff < 0.01

    def test_disagree_outside_tolerance(self):
        xc = cross_check(_cand(converted_value=1.5), 1.0, rel_tol=0.01)
        assert xc.status == DISAGREE
        assert xc.disagrees
        assert xc.rel_diff == pytest.approx(0.5)

    def test_exact_match(self):
        xc = cross_check(_cand(converted_value=4.27), 4.27)
        assert xc.status == AGREE
        assert xc.rel_diff == 0.0


class TestCrossCheckEdgeCases:
    def test_no_sbml_value(self):
        xc = cross_check(_cand(), None)
        assert xc.status == NO_SBML
        assert xc.pdf_value is None

    def test_no_pdf_recommendation(self):
        xc = cross_check(None, 1.0)
        assert xc.status == NO_PDF_VALUE
        assert xc.sbml_value == 1.0

    def test_no_unit_match_when_converted_value_missing(self):
        xc = cross_check(_cand(converted_value=None), 1.0)
        assert xc.status == NO_UNIT_MATCH
        assert "not convertible" in xc.note

    def test_skipped_when_method_is_biomodels(self):
        xc = cross_check(_cand(method="biomodels_sbml", converted_value=1.0), 1.0)
        assert xc.status == SKIPPED_SAME_SOURCE
        assert "biomodels_sbml" in xc.note

    def test_zero_sbml_value_handled(self):
        # rel_diff would be inf; abs_tol decides
        xc = cross_check(_cand(converted_value=1e-15), 0.0, abs_tol=1e-12)
        assert xc.status == AGREE
        xc2 = cross_check(_cand(converted_value=0.5), 0.0, abs_tol=1e-12)
        assert xc2.status == DISAGREE

    def test_tiny_values_use_abs_tol(self):
        # Two near-zero values: rel diff is huge but abs diff tiny
        xc = cross_check(_cand(converted_value=1e-13), 5e-14, rel_tol=0.01, abs_tol=1e-12)
        assert xc.status == AGREE


class TestCrossCheckSerialization:
    def test_to_dict_strips_unset(self):
        xc = cross_check(None, None)
        d = xc.to_dict()
        assert d["status"] == NO_SBML
        assert "pdf_value" not in d
        assert "sbml_value" not in d

    def test_to_dict_includes_both_when_present(self):
        xc = cross_check(_cand(converted_value=2.0), 2.0)
        d = xc.to_dict()
        assert d["status"] == AGREE
        assert d["pdf_value"] == 2.0
        assert d["sbml_value"] == 2.0
        assert "rel_diff" in d


class TestCrossCheckTolerance:
    def test_default_tolerance_is_one_percent(self):
        # 0.99 vs 1.00 → rel_diff 0.01, just at the boundary
        xc_pass = cross_check(_cand(converted_value=1.005), 1.000)
        xc_fail = cross_check(_cand(converted_value=1.020), 1.000)
        assert xc_pass.status == AGREE
        assert xc_fail.status == DISAGREE
        assert xc_pass.rel_tol == 0.01

    def test_custom_tolerance(self):
        xc = cross_check(_cand(converted_value=1.05), 1.0, rel_tol=0.10)
        assert xc.status == AGREE
        xc2 = cross_check(_cand(converted_value=1.05), 1.0, rel_tol=0.01)
        assert xc2.status == DISAGREE
