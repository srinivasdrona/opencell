"""Parameter Verification Card system v2 for OpenCell.

Prevents fabricated *and semantically mismatched* parameter values from
entering scientific simulations.  Every parameter carries rich provenance,
biological context, and uncertainty metadata.  Deterministic validators
catch common errors without relying on AI.

Lifecycle:  DRAFT → REVIEWED → APPROVED

Usage
-----
    from opencell.data.verification import (
        ParameterCard, VerificationStatus, ValidationIssue,
        validate_card, audit_parameters, ci_gate_check,
        load_cards_from_yaml, save_cards_to_yaml,
    )
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Verification status enum (3 states)
# ---------------------------------------------------------------------------

class VerificationStatus(enum.Enum):
    """Simplified three-state lifecycle.

    DRAFT    – AI-sourced, not yet checked by anyone.
    REVIEWED – A human confirmed the extraction is correct.
    APPROVED – Validated for use in scientific simulations (implies reviewed,
               context-matched, and uncertainty assessed).
    """

    DRAFT = "DRAFT"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"


# ---------------------------------------------------------------------------
# Uncertainty type
# ---------------------------------------------------------------------------

VALID_UNCERTAINTY_TYPES = {"range", "std", "95ci", "order_of_magnitude"}

# ---------------------------------------------------------------------------
# Source type
# ---------------------------------------------------------------------------

VALID_SOURCE_TYPES = {"measured", "fitted", "borrowed", "assumed", "derived"}

# ---------------------------------------------------------------------------
# DOI regex (simplified but catches format errors)
# ---------------------------------------------------------------------------

_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")


# ---------------------------------------------------------------------------
# Parameter card dataclass
# ---------------------------------------------------------------------------

@dataclass
class ParameterCard:
    """Provenance + context metadata for a single numeric parameter.

    The context fields (organism, condition, compartment, gene_or_enzyme)
    are the primary defence against semantic mismatch — a perfectly cited
    value from the wrong organism or condition is just as dangerous as a
    fabricated one.
    """

    # --- Identity ---
    parameter_id: str
    name: str = ""

    # --- Value ---
    value: float = 0.0
    unit: str = ""
    uncertainty_lower: float | None = None
    uncertainty_upper: float | None = None
    uncertainty_type: str = "range"

    # --- Provenance ---
    source_doi: str = ""
    source_type: str = "assumed"
    source_table: str = ""
    original_quote: str = ""
    original_value: float | None = None
    original_unit: str = ""
    transformation: str = ""

    # --- Biological context ---
    organism: str = ""
    condition: str = ""
    compartment: str = ""
    gene_or_enzyme: str = ""

    # --- Verification ---
    status: VerificationStatus = VerificationStatus.DRAFT
    reviewed_by: str = ""
    reviewed_date: str = ""
    approved_by: str = ""
    approved_date: str = ""

    # --- Cross-references ---
    cross_references: list[dict] = field(default_factory=list)
    selection_rationale: str = ""
    discrepancy_notes: str = ""

    # --- Gate-test usage ---
    used_in_gate_tests: bool = False
    gate_acknowledged: bool = False
    acknowledgement_reason: str = ""

    # ------------------------------------------------------------------

    def __post_init__(self) -> None:
        if not self.parameter_id:
            raise ValueError("parameter_id must not be empty")
        if isinstance(self.status, str):
            self.status = VerificationStatus(self.status)

    # --- Serialisation helpers --------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ParameterCard:
        data = dict(data)
        if "status" in data:
            data["status"] = VerificationStatus(data["status"])
        return cls(**data)


# ---------------------------------------------------------------------------
# Validation issue
# ---------------------------------------------------------------------------

class Severity(enum.Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class ValidationIssue:
    field: str
    severity: Severity
    message: str


# ---------------------------------------------------------------------------
# Deterministic validators
# ---------------------------------------------------------------------------

def _check_doi_format(card: ParameterCard) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if card.source_doi and not _DOI_RE.match(card.source_doi):
        issues.append(ValidationIssue(
            "source_doi", Severity.ERROR,
            f"DOI '{card.source_doi}' does not match expected format 10.NNNN/..."
        ))
    return issues


def _check_completeness(card: ParameterCard) -> list[ValidationIssue]:
    """Required fields for every card regardless of status."""
    issues: list[ValidationIssue] = []
    if not card.parameter_id:
        issues.append(ValidationIssue("parameter_id", Severity.ERROR, "parameter_id is required"))
    if not card.name:
        issues.append(ValidationIssue("name", Severity.WARNING, "name should be set"))
    if not card.unit:
        issues.append(ValidationIssue("unit", Severity.ERROR, "unit is required"))
    if not card.source_doi:
        issues.append(ValidationIssue("source_doi", Severity.WARNING, "source_doi is missing"))
    return issues


def _check_value_range(card: ParameterCard) -> list[ValidationIssue]:
    """Basic physical sanity: concentrations ≥ 0, rates finite, etc."""
    issues: list[ValidationIssue] = []
    import math
    if math.isnan(card.value) or math.isinf(card.value):
        issues.append(ValidationIssue("value", Severity.ERROR, "value must be finite"))
    if card.uncertainty_lower is not None and card.uncertainty_upper is not None:
        if card.uncertainty_lower > card.uncertainty_upper:
            issues.append(ValidationIssue(
                "uncertainty_lower", Severity.ERROR,
                "uncertainty_lower must be ≤ uncertainty_upper"
            ))
    return issues


def _check_uncertainty_type(card: ParameterCard) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if card.uncertainty_type not in VALID_UNCERTAINTY_TYPES:
        issues.append(ValidationIssue(
            "uncertainty_type", Severity.ERROR,
            f"uncertainty_type '{card.uncertainty_type}' not in {VALID_UNCERTAINTY_TYPES}"
        ))
    return issues


def _check_source_type(card: ParameterCard) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if card.source_type not in VALID_SOURCE_TYPES:
        issues.append(ValidationIssue(
            "source_type", Severity.ERROR,
            f"source_type '{card.source_type}' not in {VALID_SOURCE_TYPES}"
        ))
    return issues


def _check_context(card: ParameterCard) -> list[ValidationIssue]:
    """Organism and condition must be set for REVIEWED and APPROVED cards."""
    issues: list[ValidationIssue] = []
    if card.status in (VerificationStatus.REVIEWED, VerificationStatus.APPROVED):
        if not card.organism:
            issues.append(ValidationIssue(
                "organism", Severity.ERROR,
                "organism is required for REVIEWED/APPROVED parameters"
            ))
        if not card.condition:
            issues.append(ValidationIssue(
                "condition", Severity.ERROR,
                "condition is required for REVIEWED/APPROVED parameters"
            ))
    return issues


def _check_reviewed_fields(card: ParameterCard) -> list[ValidationIssue]:
    """REVIEWED+ cards must have reviewer info."""
    issues: list[ValidationIssue] = []
    if card.status in (VerificationStatus.REVIEWED, VerificationStatus.APPROVED):
        if not card.reviewed_by:
            issues.append(ValidationIssue(
                "reviewed_by", Severity.ERROR,
                "reviewed_by is required for REVIEWED/APPROVED parameters"
            ))
        if not card.reviewed_date:
            issues.append(ValidationIssue(
                "reviewed_date", Severity.ERROR,
                "reviewed_date is required for REVIEWED/APPROVED parameters"
            ))
    return issues


def _check_approved_fields(card: ParameterCard) -> list[ValidationIssue]:
    """APPROVED cards must have uncertainty bounds, cross-references, and approver."""
    issues: list[ValidationIssue] = []
    if card.status is VerificationStatus.APPROVED:
        if card.uncertainty_lower is None or card.uncertainty_upper is None:
            issues.append(ValidationIssue(
                "uncertainty_lower", Severity.ERROR,
                "APPROVED parameters must have uncertainty bounds"
            ))
        if not card.cross_references:
            issues.append(ValidationIssue(
                "cross_references", Severity.WARNING,
                "APPROVED parameters should have ≥1 cross-reference"
            ))
        if not card.approved_by:
            issues.append(ValidationIssue(
                "approved_by", Severity.ERROR,
                "approved_by is required for APPROVED parameters"
            ))
        if not card.approved_date:
            issues.append(ValidationIssue(
                "approved_date", Severity.ERROR,
                "approved_date is required for APPROVED parameters"
            ))
    return issues


def _check_transformation(card: ParameterCard) -> list[ValidationIssue]:
    """If original_value is set, transformation must also be documented."""
    issues: list[ValidationIssue] = []
    if card.original_value is not None:
        if not card.transformation:
            issues.append(ValidationIssue(
                "transformation", Severity.WARNING,
                "original_value is set but transformation is not documented"
            ))
        if not card.original_unit:
            issues.append(ValidationIssue(
                "original_unit", Severity.WARNING,
                "original_value is set but original_unit is missing"
            ))
    return issues


def validate_card(card: ParameterCard) -> list[ValidationIssue]:
    """Run all deterministic checks on a parameter card."""
    issues: list[ValidationIssue] = []
    issues.extend(_check_completeness(card))
    issues.extend(_check_doi_format(card))
    issues.extend(_check_value_range(card))
    issues.extend(_check_uncertainty_type(card))
    issues.extend(_check_source_type(card))
    issues.extend(_check_context(card))
    issues.extend(_check_reviewed_fields(card))
    issues.extend(_check_approved_fields(card))
    issues.extend(_check_transformation(card))
    return issues


# ---------------------------------------------------------------------------
# YAML I/O
# ---------------------------------------------------------------------------

def save_cards_to_yaml(cards: list[ParameterCard], path: str | Path) -> None:
    """Write a list of parameter cards to a YAML file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [card.to_dict() for card in cards]
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, default_flow_style=False, sort_keys=False)


def load_cards_from_yaml(path: str | Path) -> list[ParameterCard]:
    """Load parameter cards from a YAML file."""
    path = Path(path)
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError(f"Expected a YAML list in {path}, got {type(data).__name__}")
    return [ParameterCard.from_dict(entry) for entry in data]


# ---------------------------------------------------------------------------
# Audit report
# ---------------------------------------------------------------------------

@dataclass
class AuditReport:
    """Verification coverage report across all parameter cards."""

    total: int = 0
    draft: int = 0
    reviewed: int = 0
    approved: int = 0

    validation_issues: list[tuple[str, ValidationIssue]] = field(default_factory=list)

    # Gate-test params that are not APPROVED
    gate_violations: list[str] = field(default_factory=list)
    # Gate-test params that are REVIEWED but not APPROVED
    gate_warnings: list[str] = field(default_factory=list)
    # Explicitly acknowledged non-approved gate params
    gate_acknowledged: list[str] = field(default_factory=list)

    cross_ref_coverage: int = 0  # how many cards have ≥1 cross-ref

    @property
    def coverage_pct(self) -> float:
        """Percentage of parameters that are APPROVED."""
        if self.total == 0:
            return 100.0
        return 100.0 * self.approved / self.total

    def summary(self) -> str:
        lines = [
            "=== Parameter Verification Audit (v2) ===",
            f"Total parameters : {self.total}",
            f"DRAFT            : {self.draft}",
            f"REVIEWED         : {self.reviewed}",
            f"APPROVED         : {self.approved}",
            f"Approved coverage: {self.coverage_pct:.1f}%",
            f"Cross-ref coverage: {self.cross_ref_coverage}/{self.total}",
        ]
        errors = [(pid, iss) for pid, iss in self.validation_issues if iss.severity is Severity.ERROR]
        if errors:
            lines.append("")
            lines.append(f"✗ Validation errors: {len(errors)}")
            for pid, iss in errors[:10]:
                lines.append(f"  - {pid}: [{iss.field}] {iss.message}")
            if len(errors) > 10:
                lines.append(f"  ... and {len(errors) - 10} more")
        if self.gate_violations:
            lines.append("")
            lines.append("⚠ GATE VIOLATIONS (DRAFT params in gate tests without acknowledgement):")
            for pid in self.gate_violations:
                lines.append(f"  - {pid}")
        if self.gate_warnings:
            lines.append("")
            lines.append("ℹ GATE WARNINGS (REVIEWED but not APPROVED params in gate tests):")
            for pid in self.gate_warnings:
                lines.append(f"  - {pid}")
        if self.gate_acknowledged:
            lines.append("")
            lines.append("ℹ Acknowledged non-approved params in gate tests:")
            for pid in self.gate_acknowledged:
                lines.append(f"  - {pid}")
        return "\n".join(lines)


def audit_parameters(cards: list[ParameterCard]) -> AuditReport:
    """Generate a verification coverage report."""
    report = AuditReport(total=len(cards))

    for card in cards:
        if card.status is VerificationStatus.DRAFT:
            report.draft += 1
        elif card.status is VerificationStatus.REVIEWED:
            report.reviewed += 1
        elif card.status is VerificationStatus.APPROVED:
            report.approved += 1

        if card.cross_references:
            report.cross_ref_coverage += 1

        # Run validators
        issues = validate_card(card)
        for iss in issues:
            report.validation_issues.append((card.parameter_id, iss))

        # Gate-test analysis
        if card.used_in_gate_tests:
            if card.status is VerificationStatus.APPROVED:
                pass  # OK
            elif card.gate_acknowledged:
                report.gate_acknowledged.append(card.parameter_id)
            elif card.status is VerificationStatus.REVIEWED:
                report.gate_warnings.append(card.parameter_id)
            else:  # DRAFT
                report.gate_violations.append(card.parameter_id)

    return report


# ---------------------------------------------------------------------------
# CI gate check
# ---------------------------------------------------------------------------

def ci_gate_check(cards: list[ParameterCard]) -> tuple[bool, str]:
    """Return (pass, message) for CI integration.

    Fails if:
    - Any card has required-field errors (missing unit, etc.)
    - Any DRAFT param is used in gate tests without acknowledgement
    - Any APPROVED param has validation errors

    Warns (but passes) if:
    - REVIEWED (but not APPROVED) params exist in gate tests
    """
    report = audit_parameters(cards)
    messages: list[str] = []
    fail = False

    # Check for required-field errors on any card
    errors = [(pid, iss) for pid, iss in report.validation_issues if iss.severity is Severity.ERROR]

    # APPROVED params with errors → fail
    approved_ids = {c.parameter_id for c in cards if c.status is VerificationStatus.APPROVED}
    approved_errors = [(pid, iss) for pid, iss in errors if pid in approved_ids]
    if approved_errors:
        fail = True
        messages.append(f"FAIL: {len(approved_errors)} validation error(s) on APPROVED parameters")

    # Missing required fields (unit) on any card → fail
    missing_required = [(pid, iss) for pid, iss in errors
                        if iss.field in ("parameter_id", "unit")]
    if missing_required:
        fail = True
        messages.append(f"FAIL: {len(missing_required)} card(s) missing required fields")

    # DRAFT in gate tests without ack → fail
    if report.gate_violations:
        fail = True
        messages.append(
            f"FAIL: {len(report.gate_violations)} DRAFT param(s) in gate tests "
            f"without acknowledgement: {', '.join(report.gate_violations)}"
        )

    # REVIEWED in gate tests → warn
    if report.gate_warnings:
        messages.append(
            f"WARN: {len(report.gate_warnings)} REVIEWED (not APPROVED) param(s) "
            f"in gate tests: {', '.join(report.gate_warnings)}"
        )

    if not messages:
        messages.append("PASS: All parameter cards OK")

    return (not fail, "\n".join(messages))
