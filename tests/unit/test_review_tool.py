"""Tests for tools/review_param.py — the interactive parameter review CLI."""

from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from unittest import mock

# Make tools/ importable.
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "tools"))

import review_param  # noqa: E402

from opencell.data.verification import (  # noqa: E402
    ParameterCard,
    VerificationStatus,
    load_cards_from_yaml,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_draft(**overrides) -> ParameterCard:
    defaults = dict(
        parameter_id="p-test-1",
        name="Test parameter",
        value=1.0,
        unit="1/s",
        uncertainty_lower=0.5,
        uncertainty_upper=2.0,
        uncertainty_type="range",
        source_doi="10.1000/example",
        source_type="measured",
        source_table="Table 1",
        original_quote="k = 1.0 1/s",
        organism="E. coli",
        condition="exponential growth",
        compartment="cytoplasm",
        gene_or_enzyme="generic",
        status=VerificationStatus.DRAFT,
        cross_references=[
            {
                "source_doi": "10.1000/other",
                "value": 1.2,
                "unit": "1/s",
                "agrees": True,
                "note": "ok",
            }
        ],
        selection_rationale="Used as published.",
    )
    defaults.update(overrides)
    return ParameterCard(**defaults)


def _make_reviewed(**overrides) -> ParameterCard:
    base = dict(
        status=VerificationStatus.REVIEWED,
        reviewed_by="Alice",
        reviewed_date="2024-01-01",
    )
    base.update(overrides)
    return _make_draft(**base)


def _write_yaml(tmp_path: Path, cards: list[ParameterCard], header: str = "") -> Path:
    p = tmp_path / "params.yaml"
    review_param._save_cards(cards, p, header=header)
    return p


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_shows_all_cards(tmp_path, capsys) -> None:
    cards = [
        _make_draft(parameter_id="p-1"),
        _make_draft(parameter_id="p-2"),
        _make_reviewed(parameter_id="p-3"),
    ]
    p = _write_yaml(tmp_path, cards)
    rc = review_param.main(["list", str(p)])
    out = capsys.readouterr().out
    assert rc == 0
    for pid in ("p-1", "p-2", "p-3"):
        assert pid in out
    assert "DRAFT" in out
    assert "REVIEWED" in out


def test_list_status_filter(tmp_path, capsys) -> None:
    cards = [
        _make_draft(parameter_id="p-1"),
        _make_reviewed(parameter_id="p-2"),
    ]
    p = _write_yaml(tmp_path, cards)
    rc = review_param.main(["list", str(p), "--status", "DRAFT"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "p-1" in out
    assert "p-2" not in out


def test_list_gate_only_filter(tmp_path, capsys) -> None:
    cards = [
        _make_draft(
            parameter_id="p-gate",
            used_in_gate_tests=True,
            gate_acknowledged=True,
            acknowledgement_reason="solver test",
        ),
        _make_draft(parameter_id="p-nogate"),
    ]
    p = _write_yaml(tmp_path, cards)
    rc = review_param.main(["list", str(p), "--gate-only"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "p-gate" in out
    assert "p-nogate" not in out


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


def test_show_formats_all_fields(tmp_path, capsys) -> None:
    cards = [_make_draft()]
    p = _write_yaml(tmp_path, cards)
    rc = review_param.main(["show", str(p), "p-test-1"])
    out = capsys.readouterr().out
    assert rc == 0
    for label in ("Identity", "Value", "Provenance", "Context", "Verification", "Cross-refs"):
        assert label in out
    assert "p-test-1" in out
    assert "10.1000/example" in out
    assert "E. coli" in out


def test_show_reports_validation_issues(tmp_path, capsys) -> None:
    # missing unit → ERROR
    card = _make_draft(unit="")
    p = _write_yaml(tmp_path, [card])
    rc = review_param.main(["show", str(p), "p-test-1"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Validation issues" in out
    assert "unit" in out


def test_show_unknown_param_id(tmp_path, capsys) -> None:
    p = _write_yaml(tmp_path, [_make_draft()])
    rc = review_param.main(["show", str(p), "no-such-id"])
    assert rc == 2


# ---------------------------------------------------------------------------
# review
# ---------------------------------------------------------------------------


def test_review_happy_path(tmp_path, capsys) -> None:
    p = _write_yaml(tmp_path, [_make_draft()])
    answers = ["y", "y", "y", "y", "Bob"]
    with mock.patch("builtins.input", side_effect=answers):
        rc = review_param.main(["review", str(p), "p-test-1"])
    assert rc == 0
    cards = load_cards_from_yaml(p)
    assert cards[0].status is VerificationStatus.REVIEWED
    assert cards[0].reviewed_by == "Bob"
    assert cards[0].reviewed_date == _dt.date.today().isoformat()


def test_review_aborts_on_no_quote(tmp_path, capsys) -> None:
    p = _write_yaml(tmp_path, [_make_draft()])
    # DOI=y, quote=n → abort
    answers = ["y", "n"]
    with mock.patch("builtins.input", side_effect=answers):
        rc = review_param.main(["review", str(p), "p-test-1"])
    assert rc == 1
    cards = load_cards_from_yaml(p)
    assert cards[0].status is VerificationStatus.DRAFT
    assert cards[0].reviewed_by == ""


def test_review_updates_reviewed_fields(tmp_path) -> None:
    p = _write_yaml(tmp_path, [_make_draft()])
    with mock.patch("builtins.input", side_effect=["y", "y", "y", "y", "Carol"]):
        rc = review_param.main(["review", str(p), "p-test-1"])
    assert rc == 0
    cards = load_cards_from_yaml(p)
    assert cards[0].reviewed_by == "Carol"
    assert cards[0].reviewed_date == _dt.date.today().isoformat()


def test_review_aborts_on_unknown_param(tmp_path) -> None:
    p = _write_yaml(tmp_path, [_make_draft()])
    rc = review_param.main(["review", str(p), "no-such"])
    assert rc == 2


def test_review_skips_already_reviewed(tmp_path, capsys) -> None:
    p = _write_yaml(tmp_path, [_make_reviewed()])
    rc = review_param.main(["review", str(p), "p-test-1"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "already" in out.lower()


# ---------------------------------------------------------------------------
# approve
# ---------------------------------------------------------------------------


def test_approve_refuses_if_draft(tmp_path, capsys) -> None:
    p = _write_yaml(tmp_path, [_make_draft()])
    rc = review_param.main(["approve", str(p), "p-test-1"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "REVIEWED" in err


def test_approve_happy_path(tmp_path) -> None:
    # Reviewed card with real uncertainty bounds and cross-refs already present
    p = _write_yaml(tmp_path, [_make_reviewed()])
    # organism=y, role=y, approver=Dave
    answers = ["y", "y", "Dave"]
    with mock.patch("builtins.input", side_effect=answers):
        rc = review_param.main(["approve", str(p), "p-test-1"])
    assert rc == 0
    cards = load_cards_from_yaml(p)
    assert cards[0].status is VerificationStatus.APPROVED
    assert cards[0].approved_by == "Dave"
    assert cards[0].approved_date == _dt.date.today().isoformat()


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------


def test_audit_exit_code_zero_on_clean_cards(tmp_path) -> None:
    # All-APPROVED card; not gate-tested so no gate violations.
    card = _make_reviewed(
        status=VerificationStatus.APPROVED,
        approved_by="Eve",
        approved_date="2024-02-02",
    )
    p = _write_yaml(tmp_path, [card])
    rc = review_param.main(["audit", str(p)])
    assert rc == 0


def test_audit_exit_code_one_on_gate_violation(tmp_path, capsys) -> None:
    # DRAFT card used in gate tests without acknowledgement → CI gate fails.
    card = _make_draft(used_in_gate_tests=True, gate_acknowledged=False)
    p = _write_yaml(tmp_path, [card])
    rc = review_param.main(["audit", str(p)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAIL" in out


# ---------------------------------------------------------------------------
# YAML round-trip
# ---------------------------------------------------------------------------


def test_yaml_roundtrip_preserves_all_fields(tmp_path) -> None:
    original = _make_draft(
        original_value=1.0,
        original_unit="1/s",
        transformation="none",
        discrepancy_notes="see notes",
        used_in_gate_tests=True,
        gate_acknowledged=True,
        acknowledgement_reason="solver test",
    )
    header = "# leading comment\n# more\n\n"
    p = _write_yaml(tmp_path, [original], header=header)

    text = p.read_text(encoding="utf-8")
    assert text.startswith("# leading comment")

    loaded = load_cards_from_yaml(p)
    assert len(loaded) == 1
    rt = loaded[0]
    assert rt.to_dict() == original.to_dict()
