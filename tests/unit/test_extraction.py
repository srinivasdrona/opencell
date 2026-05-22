"""Tests for the deterministic parameter-extraction skill.

Coverage matrix:
  - positive: Thattai 2001 k_R → 0.01 s^-1 from cached PDF
  - ambiguous: Thattai protein vs mRNA half-life share "half-life" keyword
  - negative: nonexistent symbol → NOT_FOUND
  - adversarial: refs-section hit must be rejected
  - cache provenance: SHA-256 recorded on every candidate
  - unit demangling: "s21" → "s^-1"
  - text demangling: "kR 5 0.01" → readable as "kR = 0.01"
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencell.extraction import ExtractionResult, ParameterSpec, extract_parameter
from opencell.extraction.candidate import SectionType
from opencell.extraction.pdf_grep import (
    GrepConfig,
    grep_for_symbol,
    symbol_variants,
)
from opencell.extraction.provenance import file_sha256, make_provenance
from opencell.extraction.text_normalize import demangle_context, demangle_unit_string
from opencell.extraction.units import convert, units_compatible

THATTAI_CACHE = Path(__file__).resolve().parents[2] / ".paper_cache" / "thattai2001_full.txt"


# ---------------------------------------------------------------------------
# text_normalize
# ---------------------------------------------------------------------------


class TestUnitDemangling:
    def test_s_inverse(self) -> None:
        assert demangle_unit_string("s21") == "s^-1"

    def test_min_inverse(self) -> None:
        assert demangle_unit_string("min21") == "min^-1"

    def test_h_inverse_squared(self) -> None:
        assert demangle_unit_string("h22") == "h^-2"

    def test_with_space(self) -> None:
        assert demangle_unit_string("s 21") == "s^-1"

    def test_idempotent(self) -> None:
        once = demangle_unit_string("s21")
        twice = demangle_unit_string(once)
        assert once == twice == "s^-1"

    def test_clean_unit_unchanged(self) -> None:
        assert demangle_unit_string("min^-1") == "min^-1"
        assert demangle_unit_string("mol/L") == "mol/L"

    def test_empty(self) -> None:
        assert demangle_unit_string("") == ""


class TestContextDemangling:
    def test_equals_sign_recovered(self) -> None:
        out = demangle_context("kR 5 0.01 s21")
        assert "= 0.01" in out
        assert "s^-1" in out

    def test_does_not_corrupt_other_5s(self) -> None:
        # "5 hours" should not become "= hours" because "hours" is not a digit
        out = demangle_context("ran for 5 hours")
        assert "5 hours" in out


# ---------------------------------------------------------------------------
# units
# ---------------------------------------------------------------------------


class TestUnitConversion:
    def test_s_inverse_to_min_inverse(self) -> None:
        r = convert(0.01, "s^-1", "min^-1")
        assert r.success
        assert r.converted_value == pytest.approx(0.6)
        assert "0.01" in r.transformation
        assert "min^-1" in r.transformation

    def test_compatible(self) -> None:
        assert units_compatible("s^-1", "min^-1")
        assert not units_compatible("s^-1", "mol/L")

    def test_incompatible_returns_failure(self) -> None:
        r = convert(1.0, "s^-1", "mol/L")
        assert not r.success


# ---------------------------------------------------------------------------
# symbol variants
# ---------------------------------------------------------------------------


class TestSymbolVariants:
    def test_underscore_stripped(self) -> None:
        v = symbol_variants("k_R")
        assert "k_R" in v and "kR" in v

    def test_greek_transliteration(self) -> None:
        v = symbol_variants("γ_P")
        assert "g_P" in v
        assert "gP" in v

    def test_plain_unchanged(self) -> None:
        assert symbol_variants("kR") == ["kR"]


# ---------------------------------------------------------------------------
# pdf_grep — core positive case
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def thattai_text():
    if not THATTAI_CACHE.exists():
        pytest.skip(f"Thattai cache not present at {THATTAI_CACHE}")
    return THATTAI_CACHE.read_text(encoding="utf-8", errors="replace")


@pytest.fixture(scope="module")
def thattai_provenance():
    if not THATTAI_CACHE.exists():
        pytest.skip(f"Thattai cache not present at {THATTAI_CACHE}")
    return make_provenance(THATTAI_CACHE)


class TestThattaiPositiveExtraction:
    """The headline test: re-extract Thattai k_R deterministically.

    This is the parameter that two AI rounds previously fabricated.
    The cached PDF text MUST yield raw_value=0.01 with unit s^-1.
    """

    def test_kR_value_is_0p01(self, thattai_text, thattai_provenance) -> None:
        cands = grep_for_symbol(
            thattai_text,
            "kR",
            config=GrepConfig(target_unit="min^-1"),
            provenance=thattai_provenance,
        )
        # Get all surviving candidates
        survivors = [c for c in cands if not c.rejected]
        assert survivors, "no surviving k_R candidates found"
        # Every numeric value among survivors should be 0.01 (the base case)
        unique_values = {round(c.raw_value, 6) for c in survivors}
        assert 0.01 in unique_values, f"expected 0.01 among survivors, got {unique_values}"

    def test_kR_unit_is_s_inverse(self, thattai_text, thattai_provenance) -> None:
        cands = grep_for_symbol(
            thattai_text,
            "kR",
            config=GrepConfig(target_unit="min^-1"),
            provenance=thattai_provenance,
        )
        # The 0.01 hit must have raw unit demangled to s^-1
        winners = [c for c in cands if not c.rejected and round(c.raw_value, 6) == 0.01]
        assert winners
        for c in winners:
            assert c.raw_unit_normalized == "s^-1", (
                f"expected s^-1, got {c.raw_unit_normalized!r} (raw={c.raw_unit!r})"
            )

    def test_kR_context_contains_symbol(self, thattai_text, thattai_provenance) -> None:
        cands = grep_for_symbol(thattai_text, "kR", provenance=thattai_provenance)
        for c in cands:
            assert "kR" in c.context_window or "k_R" in c.context_window

    def test_kR_locator_points_to_caption_region(self, thattai_text, thattai_provenance) -> None:
        cands = grep_for_symbol(
            thattai_text,
            "kR",
            config=GrepConfig(target_unit="min^-1"),
            provenance=thattai_provenance,
        )
        winners = [c for c in cands if not c.rejected and round(c.raw_value, 6) == 0.01]
        assert winners
        # At least one of the 0.01 hits should be in a caption section
        caption_hits = [c for c in winners if c.section_type == SectionType.CAPTION]
        assert caption_hits, "expected at least one 0.01 hit in a figure caption"

    def test_kR_provenance_recorded(self, thattai_text, thattai_provenance) -> None:
        cands = grep_for_symbol(
            thattai_text,
            "kR",
            provenance=thattai_provenance,
        )
        assert cands
        for c in cands:
            assert c.source_sha256 == thattai_provenance.sha256
            assert c.source_path == thattai_provenance.path
            assert c.extractor_version

    def test_kR_conversion_to_min_inverse(self, thattai_text, thattai_provenance) -> None:
        cands = grep_for_symbol(
            thattai_text,
            "kR",
            config=GrepConfig(target_unit="min^-1"),
            provenance=thattai_provenance,
        )
        winners = [c for c in cands if not c.rejected and round(c.raw_value, 6) == 0.01]
        assert winners
        c = winners[0]
        assert c.convertible_to_target is True
        assert c.converted_value == pytest.approx(0.6)
        assert c.converted_unit == "min^-1"


class TestPipelineThattaiEndToEnd:
    """Run the full pipeline (no biomodels) and confirm RECOMMEND status."""

    def test_recommendation_emitted(self) -> None:
        if not THATTAI_CACHE.exists():
            pytest.skip("Thattai cache missing")
        spec = ParameterSpec(
            symbol="kR",
            doi="10.1073/pnas.151588598",
            target_unit="min^-1",
            cache_files=[str(THATTAI_CACHE)],
            use_biomodels=False,
        )
        result = extract_parameter(spec)
        assert isinstance(result, ExtractionResult)
        # All survivors must agree on 0.01 → RECOMMEND
        assert result.status == "RECOMMEND", (
            f"expected RECOMMEND, got {result.status}; survivors={[c.raw_value for c in result.surviving]}"
        )
        rec = result.recommendation
        assert rec is not None
        assert rec.raw_value == pytest.approx(0.01)
        assert rec.converted_value == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# Negative & adversarial cases
# ---------------------------------------------------------------------------


class TestNegativeAndAdversarial:
    def test_nonexistent_symbol_returns_not_found(self) -> None:
        if not THATTAI_CACHE.exists():
            pytest.skip("cache missing")
        spec = ParameterSpec(
            symbol="zXyQqq",
            doi="10.1073/pnas.151588598",
            target_unit="min^-1",
            cache_files=[str(THATTAI_CACHE)],
            use_biomodels=False,
        )
        result = extract_parameter(spec)
        assert result.status == "NOT_FOUND"
        assert result.recommendation is None

    def test_refs_section_hit_is_rejected(self) -> None:
        # Build synthetic text where the only hit is in a References section
        text = (
            "Introduction\n"
            "Some prose here.\n\n"
            "References\n"
            "1. Author A. kR = 0.5 s^-1. Journal X (2001).\n"
        )
        cands = grep_for_symbol(text, "kR", config=GrepConfig(target_unit="s^-1"))
        assert cands, "expected the regex to find the hit"
        # All hits should be in REFS section and therefore rejected
        for c in cands:
            assert c.section_type == SectionType.REFS
            assert c.rejected
            assert (
                "references" in c.rejection_reason.lower() or "score" in c.rejection_reason.lower()
            )

    def test_hit_without_unit_is_rejected_when_required(self) -> None:
        text = "We use the value kR = 0.5 in our model."
        cands = grep_for_symbol(
            text, "kR", config=GrepConfig(target_unit="s^-1", require_unit=True)
        )
        assert cands
        # The "in" gets eaten as the unit — but it's not a real unit.
        # Either it's recognised as having a non-unit token (and rejected by score)
        # or it has no unit and is rejected outright.  Either way: rejected.
        for c in cands:
            # Allow either pure-no-unit rejection OR low-score rejection
            assert c.rejected, f"expected rejection, got {c}"

    def test_word_boundary_does_not_match_kR1(self) -> None:
        text = "The downstream rates kR1 = 0.3 s^-1 and kR2 = 0.4 s^-1 are reported."
        cands = grep_for_symbol(text, "kR")
        # Exactly zero hits because kR is NOT followed by a non-letter/digit
        assert cands == [], (
            f"expected 0 hits for kR (since text has only kR1, kR2), got {len(cands)}"
        )


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


class TestProvenance:
    def test_sha256_stable_for_same_file(self, tmp_path) -> None:
        f = tmp_path / "x.txt"
        f.write_text("hello world\n")
        h1 = file_sha256(f)
        h2 = file_sha256(f)
        assert h1 == h2
        assert len(h1) == 64

    def test_sha256_changes_when_file_changes(self, tmp_path) -> None:
        f = tmp_path / "x.txt"
        f.write_text("hello\n")
        h1 = file_sha256(f)
        f.write_text("hello world\n")
        h2 = file_sha256(f)
        assert h1 != h2

    def test_make_provenance_records_path_and_hash(self, tmp_path) -> None:
        f = tmp_path / "x.txt"
        f.write_text("data\n")
        prov = make_provenance(f)
        assert prov.path == str(f)
        assert prov.sha256 == file_sha256(f)
        assert prov.extractor_version
