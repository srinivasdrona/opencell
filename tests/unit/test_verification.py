"""Tests for the Parameter Verification Card system v2."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencell.data.verification import (
    ParameterCard,
    Severity,
    ValidationIssue,
    VerificationStatus,
    audit_parameters,
    ci_gate_check,
    load_cards_from_yaml,
    save_cards_to_yaml,
    validate_card,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _draft(**overrides) -> ParameterCard:
    """Minimal DRAFT card."""
    defaults = dict(
        parameter_id="k-cat-pfk",
        name="PFK kcat",
        value=110.0,
        unit="1/s",
        source_doi="10.1016/j.jmb.2005.06.032",
        source_type="measured",
        source_table="Table 2",
        original_quote="kcat = 110 s-1 (Table 2)",
        status=VerificationStatus.DRAFT,
    )
    defaults.update(overrides)
    return ParameterCard(**defaults)


def _reviewed(**overrides) -> ParameterCard:
    """Minimal REVIEWED card (adds context + reviewer)."""
    defaults = dict(
        organism="E. coli K-12 MG1655",
        condition="37°C, LB medium, exponential growth",
        compartment="cytoplasm",
        gene_or_enzyme="PFK-1",
        reviewed_by="A. Researcher",
        reviewed_date="2025-01-15",
        status=VerificationStatus.REVIEWED,
    )
    defaults.update(overrides)
    return _draft(**defaults)


def _approved(**overrides) -> ParameterCard:
    """Fully APPROVED card."""
    defaults = dict(
        uncertainty_lower=90.0,
        uncertainty_upper=130.0,
        uncertainty_type="range",
        cross_references=[
            {
                "source_doi": "10.1093/nar/alt",
                "value": 105.0,
                "unit": "1/s",
                "agrees": True,
                "note": "close",
            }
        ],
        selection_rationale="Most recent measurement in matching strain",
        approved_by="B. PI",
        approved_date="2025-02-01",
        status=VerificationStatus.APPROVED,
    )
    defaults.update(overrides)
    return _reviewed(**defaults)


def _has_issue(issues: list[ValidationIssue], field: str, severity: Severity | None = None) -> bool:
    """Check whether a specific field appears in the issue list."""
    for iss in issues:
        if iss.field == field and (severity is None or iss.severity is severity):
            return True
    return False


# ---------------------------------------------------------------------------
# 1. Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_draft_card(self) -> None:
        card = _draft()
        assert card.status is VerificationStatus.DRAFT
        assert card.parameter_id == "k-cat-pfk"

    def test_empty_id_raises(self) -> None:
        with pytest.raises(ValueError, match="parameter_id must not be empty"):
            ParameterCard(parameter_id="")

    def test_status_from_string(self) -> None:
        card = ParameterCard(parameter_id="x", status="REVIEWED")  # type: ignore[arg-type]
        assert card.status is VerificationStatus.REVIEWED

    def test_approved_card_has_all_context(self) -> None:
        card = _approved()
        assert card.organism != ""
        assert card.condition != ""
        assert card.approved_by != ""


# ---------------------------------------------------------------------------
# 2. All statuses round-trip
# ---------------------------------------------------------------------------


class TestStatusRoundTrip:
    @pytest.mark.parametrize("status", list(VerificationStatus), ids=lambda s: s.name)
    def test_dict_round_trip(self, status) -> None:
        card = _draft(status=status)
        d = card.to_dict()
        restored = ParameterCard.from_dict(d)
        assert restored.status is status
        assert restored.value == card.value


# ---------------------------------------------------------------------------
# 3. Validators — DOI
# ---------------------------------------------------------------------------


class TestDOIValidator:
    def test_valid_doi(self) -> None:
        issues = validate_card(_draft(source_doi="10.1016/j.jmb.2005.06.032"))
        assert not _has_issue(issues, "source_doi", Severity.ERROR)

    def test_invalid_doi(self) -> None:
        issues = validate_card(_draft(source_doi="not-a-doi"))
        assert _has_issue(issues, "source_doi", Severity.ERROR)

    def test_empty_doi_warns(self) -> None:
        issues = validate_card(_draft(source_doi=""))
        assert _has_issue(issues, "source_doi", Severity.WARNING)


# ---------------------------------------------------------------------------
# 4. Validators — value range
# ---------------------------------------------------------------------------


class TestValueRangeValidator:
    def test_nan_value(self) -> None:
        issues = validate_card(_draft(value=float("nan")))
        assert _has_issue(issues, "value", Severity.ERROR)

    def test_inf_value(self) -> None:
        issues = validate_card(_draft(value=float("inf")))
        assert _has_issue(issues, "value", Severity.ERROR)

    def test_inverted_uncertainty_bounds(self) -> None:
        issues = validate_card(_draft(uncertainty_lower=200.0, uncertainty_upper=100.0))
        assert _has_issue(issues, "uncertainty_lower", Severity.ERROR)

    def test_valid_bounds_ok(self) -> None:
        issues = validate_card(_draft(uncertainty_lower=90.0, uncertainty_upper=130.0))
        assert not _has_issue(issues, "uncertainty_lower", Severity.ERROR)


# ---------------------------------------------------------------------------
# 5. Validators — uncertainty & source type
# ---------------------------------------------------------------------------


class TestTypeValidators:
    def test_invalid_uncertainty_type(self) -> None:
        issues = validate_card(_draft(uncertainty_type="bogus"))
        assert _has_issue(issues, "uncertainty_type", Severity.ERROR)

    def test_valid_uncertainty_types(self) -> None:
        for ut in ("range", "std", "95ci", "order_of_magnitude"):
            issues = validate_card(_draft(uncertainty_type=ut))
            assert not _has_issue(issues, "uncertainty_type", Severity.ERROR)

    def test_invalid_source_type(self) -> None:
        issues = validate_card(_draft(source_type="hallucinated"))
        assert _has_issue(issues, "source_type", Severity.ERROR)

    def test_valid_source_types(self) -> None:
        for st in ("measured", "fitted", "borrowed", "assumed", "derived"):
            issues = validate_card(_draft(source_type=st))
            assert not _has_issue(issues, "source_type", Severity.ERROR)


# ---------------------------------------------------------------------------
# 6. Validators — context checks (organism/condition)
# ---------------------------------------------------------------------------


class TestContextValidator:
    def test_draft_no_context_ok(self) -> None:
        issues = validate_card(_draft(organism="", condition=""))
        assert not _has_issue(issues, "organism", Severity.ERROR)

    def test_reviewed_missing_organism(self) -> None:
        card = _reviewed(organism="")
        issues = validate_card(card)
        assert _has_issue(issues, "organism", Severity.ERROR)

    def test_reviewed_missing_condition(self) -> None:
        card = _reviewed(condition="")
        issues = validate_card(card)
        assert _has_issue(issues, "condition", Severity.ERROR)

    def test_approved_with_context_ok(self) -> None:
        card = _approved()
        issues = validate_card(card)
        assert not _has_issue(issues, "organism", Severity.ERROR)
        assert not _has_issue(issues, "condition", Severity.ERROR)


# ---------------------------------------------------------------------------
# 7. Validators — reviewed/approved field requirements
# ---------------------------------------------------------------------------


class TestStatusFieldValidators:
    def test_reviewed_missing_reviewer(self) -> None:
        card = _reviewed(reviewed_by="")
        issues = validate_card(card)
        assert _has_issue(issues, "reviewed_by", Severity.ERROR)

    def test_reviewed_missing_date(self) -> None:
        card = _reviewed(reviewed_date="")
        issues = validate_card(card)
        assert _has_issue(issues, "reviewed_date", Severity.ERROR)

    def test_approved_missing_approver(self) -> None:
        card = _approved(approved_by="")
        issues = validate_card(card)
        assert _has_issue(issues, "approved_by", Severity.ERROR)

    def test_approved_missing_uncertainty(self) -> None:
        card = _approved(uncertainty_lower=None, uncertainty_upper=None)
        issues = validate_card(card)
        assert _has_issue(issues, "uncertainty_lower", Severity.ERROR)

    def test_approved_no_cross_refs_warns(self) -> None:
        card = _approved(cross_references=[])
        issues = validate_card(card)
        assert _has_issue(issues, "cross_references", Severity.WARNING)


# ---------------------------------------------------------------------------
# 8. Validators — transformation audit
# ---------------------------------------------------------------------------


class TestTransformationValidator:
    def test_original_value_without_transformation_warns(self) -> None:
        card = _draft(original_value=110.0, transformation="", original_unit="s^-1")
        issues = validate_card(card)
        assert _has_issue(issues, "transformation", Severity.WARNING)

    def test_original_value_without_unit_warns(self) -> None:
        card = _draft(original_value=110.0, original_unit="", transformation="identity")
        issues = validate_card(card)
        assert _has_issue(issues, "original_unit", Severity.WARNING)

    def test_documented_transformation_ok(self) -> None:
        card = _draft(
            original_value=110.0, original_unit="s^-1", transformation="identity (same unit)"
        )
        issues = validate_card(card)
        assert not _has_issue(issues, "transformation", Severity.WARNING)
        assert not _has_issue(issues, "original_unit", Severity.WARNING)


# ---------------------------------------------------------------------------
# 9. Validators — completeness
# ---------------------------------------------------------------------------


class TestCompletenessValidator:
    def test_missing_unit_error(self) -> None:
        card = _draft(unit="")
        issues = validate_card(card)
        assert _has_issue(issues, "unit", Severity.ERROR)

    def test_missing_name_warns(self) -> None:
        card = _draft(name="")
        issues = validate_card(card)
        assert _has_issue(issues, "name", Severity.WARNING)


# ---------------------------------------------------------------------------
# 10. Serialisation (dict & YAML)
# ---------------------------------------------------------------------------


class TestSerialisation:
    def test_to_dict_and_back(self) -> None:
        card = _approved()
        d = card.to_dict()
        assert d["status"] == "APPROVED"
        restored = ParameterCard.from_dict(d)
        assert restored.parameter_id == card.parameter_id
        assert restored.organism == card.organism

    def test_yaml_round_trip(self, tmp_path: Path) -> None:
        cards = [_draft(parameter_id="p1"), _approved(parameter_id="p2")]
        yaml_path = tmp_path / "cards.yaml"
        save_cards_to_yaml(cards, yaml_path)

        loaded = load_cards_from_yaml(yaml_path)
        assert len(loaded) == 2
        assert loaded[0].parameter_id == "p1"
        assert loaded[0].status is VerificationStatus.DRAFT
        assert loaded[1].status is VerificationStatus.APPROVED
        assert loaded[1].organism == "E. coli K-12 MG1655"

    def test_yaml_preserves_cross_references(self, tmp_path: Path) -> None:
        card = _approved()
        yaml_path = tmp_path / "xref.yaml"
        save_cards_to_yaml([card], yaml_path)
        loaded = load_cards_from_yaml(yaml_path)
        assert len(loaded[0].cross_references) == 1
        assert loaded[0].cross_references[0]["agrees"] is True

    def test_load_empty_yaml(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "empty.yaml"
        yaml_path.write_text("", encoding="utf-8")
        assert load_cards_from_yaml(yaml_path) == []

    def test_load_invalid_yaml_raises(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "bad.yaml"
        yaml_path.write_text("key: value", encoding="utf-8")
        with pytest.raises(ValueError, match="Expected a YAML list"):
            load_cards_from_yaml(yaml_path)


# ---------------------------------------------------------------------------
# 11. Audit function
# ---------------------------------------------------------------------------


class TestAudit:
    def test_all_approved(self) -> None:
        cards = [_approved(parameter_id=f"p{i}") for i in range(3)]
        report = audit_parameters(cards)
        assert report.total == 3
        assert report.approved == 3
        assert report.coverage_pct == 100.0

    def test_mixed_statuses(self) -> None:
        cards = [
            _draft(parameter_id="d1"),
            _reviewed(parameter_id="r1"),
            _approved(parameter_id="a1"),
        ]
        report = audit_parameters(cards)
        assert report.total == 3
        assert report.draft == 1
        assert report.reviewed == 1
        assert report.approved == 1
        assert abs(report.coverage_pct - 100.0 / 3) < 0.1

    def test_empty_card_list(self) -> None:
        report = audit_parameters([])
        assert report.total == 0
        assert report.coverage_pct == 100.0

    def test_cross_ref_coverage(self) -> None:
        cards = [
            _approved(parameter_id="with-xref"),
            _draft(parameter_id="no-xref", cross_references=[]),
        ]
        report = audit_parameters(cards)
        assert report.cross_ref_coverage == 1

    def test_gate_violation_draft_in_gate(self) -> None:
        card = _draft(used_in_gate_tests=True)
        report = audit_parameters([card])
        assert card.parameter_id in report.gate_violations

    def test_gate_warning_reviewed_in_gate(self) -> None:
        card = _reviewed(used_in_gate_tests=True)
        report = audit_parameters([card])
        assert card.parameter_id in report.gate_warnings
        assert card.parameter_id not in report.gate_violations

    def test_gate_acknowledged(self) -> None:
        card = _draft(
            used_in_gate_tests=True,
            gate_acknowledged=True,
            acknowledgement_reason="only param available",
        )
        report = audit_parameters([card])
        assert card.parameter_id in report.gate_acknowledged
        assert card.parameter_id not in report.gate_violations

    def test_approved_in_gate_ok(self) -> None:
        card = _approved(used_in_gate_tests=True)
        report = audit_parameters([card])
        assert card.parameter_id not in report.gate_violations
        assert card.parameter_id not in report.gate_warnings

    def test_summary_contains_key_info(self) -> None:
        cards = [_draft(used_in_gate_tests=True, parameter_id="draft-gate")]
        report = audit_parameters(cards)
        text = report.summary()
        assert "Total parameters" in text
        assert "GATE VIOLATIONS" in text
        assert "draft-gate" in text

    def test_validation_issues_collected(self) -> None:
        card = _draft(source_doi="bad-doi", unit="")
        report = audit_parameters([card])
        fields = [iss.field for _, iss in report.validation_issues]
        assert "source_doi" in fields
        assert "unit" in fields


# ---------------------------------------------------------------------------
# 12. CI gate check
# ---------------------------------------------------------------------------


class TestCIGateCheck:
    def test_passes_all_approved(self) -> None:
        cards = [_approved(parameter_id=f"p{i}") for i in range(2)]
        ok, msg = ci_gate_check(cards)
        assert ok is True
        assert "PASS" in msg

    def test_fails_draft_in_gate(self) -> None:
        card = _draft(used_in_gate_tests=True)
        ok, msg = ci_gate_check([card])
        assert ok is False
        assert "DRAFT" in msg

    def test_passes_draft_acknowledged(self) -> None:
        card = _draft(
            used_in_gate_tests=True, gate_acknowledged=True, acknowledgement_reason="testing"
        )
        ok, msg = ci_gate_check([card])
        assert ok is True

    def test_warns_reviewed_in_gate(self) -> None:
        card = _reviewed(used_in_gate_tests=True)
        ok, msg = ci_gate_check([card])
        # REVIEWED in gate → warning, not failure
        assert ok is True
        assert "WARN" in msg

    def test_fails_approved_with_errors(self) -> None:
        # APPROVED card missing required approved_by → validation error
        card = _approved(approved_by="")
        ok, msg = ci_gate_check([card])
        assert ok is False
        assert "APPROVED" in msg

    def test_fails_missing_unit(self) -> None:
        card = _draft(unit="")
        ok, msg = ci_gate_check([card])
        assert ok is False
        assert "required fields" in msg.lower()

    def test_passes_no_gate_usage(self) -> None:
        card = _draft()  # not used in gate tests
        ok, msg = ci_gate_check([card])
        assert ok is True


# ---------------------------------------------------------------------------
# 13. Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_cross_references_structured(self) -> None:
        card = _approved()
        assert isinstance(card.cross_references[0], dict)
        assert "source_doi" in card.cross_references[0]

    def test_from_dict_with_extra_fields_raises(self) -> None:
        with pytest.raises(TypeError):
            ParameterCard.from_dict({"parameter_id": "x", "bogus": True})

    def test_negative_value_allowed(self) -> None:
        card = _draft(value=-5.0)
        issues = validate_card(card)
        assert not _has_issue(issues, "value", Severity.ERROR)

    def test_zero_value_allowed(self) -> None:
        card = _draft(value=0.0)
        issues = validate_card(card)
        assert not _has_issue(issues, "value", Severity.ERROR)

    def test_full_lifecycle_draft_to_approved(self) -> None:
        """Simulate promoting a card through all states."""
        card = _draft()
        assert card.status is VerificationStatus.DRAFT

        # Promote to REVIEWED
        card.status = VerificationStatus.REVIEWED
        card.organism = "E. coli K-12 MG1655"
        card.condition = "37°C, LB"
        card.reviewed_by = "Alice"
        card.reviewed_date = "2025-06-01"
        issues = validate_card(card)
        assert not _has_issue(issues, "organism", Severity.ERROR)

        # Promote to APPROVED
        card.status = VerificationStatus.APPROVED
        card.uncertainty_lower = 90.0
        card.uncertainty_upper = 130.0
        card.approved_by = "Bob"
        card.approved_date = "2025-06-15"
        card.cross_references = [
            {"source_doi": "10.1234/x", "value": 100.0, "unit": "1/s", "agrees": True, "note": ""}
        ]
        issues = validate_card(card)
        errors = [i for i in issues if i.severity is Severity.ERROR]
        assert len(errors) == 0
