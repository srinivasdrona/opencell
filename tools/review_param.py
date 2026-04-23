"""Interactive parameter review CLI for OpenCell.

Walks a human reviewer through promoting parameter cards along the
DRAFT → REVIEWED → APPROVED lifecycle defined in
``opencell.data.verification``.

The tool intentionally requires explicit human input for every status
promotion. There is no batch-approve mode by design.

Usage::

    python tools/review_param.py list   data/params/foo.yaml
    python tools/review_param.py show   data/params/foo.yaml <param_id>
    python tools/review_param.py review data/params/foo.yaml <param_id>
    python tools/review_param.py approve data/params/foo.yaml <param_id>
    python tools/review_param.py audit  data/params/foo.yaml
    python tools/review_param.py audit-all
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys
from dataclasses import fields as _dc_fields
from pathlib import Path
from typing import Iterable, Sequence

import yaml

# Make `import opencell...` work when running as a script.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from opencell.data.verification import (  # noqa: E402
    ParameterCard,
    Severity,
    VerificationStatus,
    audit_parameters,
    ci_gate_check,
    load_cards_from_yaml,
    validate_card,
)


# ---------------------------------------------------------------------------
# Colour helpers (ANSI; auto-disabled when not a TTY or NO_COLOR is set)
# ---------------------------------------------------------------------------

def _color_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


_C = {
    "reset":  "\033[0m",
    "bold":   "\033[1m",
    "red":    "\033[31m",
    "green":  "\033[32m",
    "yellow": "\033[33m",
    "blue":   "\033[34m",
    "cyan":   "\033[36m",
    "grey":   "\033[90m",
}


def c(text: str, color: str) -> str:
    if not _color_enabled():
        return text
    return f"{_C.get(color, '')}{text}{_C['reset']}"


# ---------------------------------------------------------------------------
# YAML preservation
# ---------------------------------------------------------------------------

def _read_header_comments(path: Path) -> str:
    """Return the leading block of ``#`` comments / blank lines from a file.

    These are preserved verbatim when we round-trip the YAML so that human
    notes at the top of a file are not lost.
    """
    if not path.exists():
        return ""
    lines: list[str] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            stripped = line.lstrip()
            if stripped.startswith("#") or stripped == "" or stripped == "\n":
                lines.append(line)
                continue
            break
    return "".join(lines)


def _save_cards(cards: list[ParameterCard], path: Path, header: str = "") -> None:
    """Write cards to ``path``, preserving an optional leading comment header."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [card.to_dict() for card in cards]
    body = yaml.dump(data, default_flow_style=False, sort_keys=False,
                     allow_unicode=True)
    with open(path, "w", encoding="utf-8") as fh:
        if header:
            fh.write(header)
            if not header.endswith("\n"):
                fh.write("\n")
        fh.write(body)


# ---------------------------------------------------------------------------
# Common helpers
# ---------------------------------------------------------------------------

def _find_card(cards: list[ParameterCard], param_id: str) -> ParameterCard | None:
    for card in cards:
        if card.parameter_id == param_id:
            return card
    return None


def _status_color(status: VerificationStatus) -> str:
    return {
        VerificationStatus.DRAFT:    "yellow",
        VerificationStatus.REVIEWED: "cyan",
        VerificationStatus.APPROVED: "green",
    }[status]


def _ask(prompt: str) -> str:
    """Wrapper around input() so tests can patch it cleanly."""
    return input(prompt)


def _ask_yes_no(prompt: str) -> bool:
    while True:
        ans = _ask(f"{prompt} [y/n] ").strip().lower()
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        print("Please answer y or n.")


def _ask_yes_no_edit(prompt: str) -> str:
    while True:
        ans = _ask(f"{prompt} [y/n/edit] ").strip().lower()
        if ans in ("y", "yes"):
            return "y"
        if ans in ("n", "no"):
            return "n"
        if ans in ("e", "edit"):
            return "edit"
        print("Please answer y, n, or edit.")


# ---------------------------------------------------------------------------
# `list` subcommand
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> int:
    cards = load_cards_from_yaml(args.yaml_file)

    if args.status:
        wanted = VerificationStatus(args.status)
        cards = [c_ for c_ in cards if c_.status is wanted]
    if args.gate_only:
        cards = [c_ for c_ in cards if c_.used_in_gate_tests]

    if not cards:
        print("(no cards match)")
        return 0

    # Determine column widths
    rows = [
        (card.parameter_id, card.status.value, str(card.value),
         card.unit, card.organism)
        for card in cards
    ]
    headers = ("parameter_id", "status", "value", "unit", "organism")
    widths = [
        max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)
    ]

    def fmt(parts: Sequence[str]) -> str:
        return "  ".join(p.ljust(widths[i]) for i, p in enumerate(parts))

    print(c(fmt(headers), "bold"))
    print(c("  ".join("-" * w for w in widths), "grey"))
    for card, row in zip(cards, rows):
        colored = list(row)
        colored[1] = c(row[1], _status_color(card.status))
        # use raw (uncoloured) widths for layout, then patch in colour
        line = fmt(row)
        line = line.replace(row[1], c(row[1], _status_color(card.status)), 1)
        print(line)
    return 0


# ---------------------------------------------------------------------------
# `show` subcommand
# ---------------------------------------------------------------------------

_GROUPS: list[tuple[str, tuple[str, ...]]] = [
    ("Identity", ("parameter_id", "name")),
    ("Value", ("value", "unit", "uncertainty_lower", "uncertainty_upper",
               "uncertainty_type")),
    ("Provenance", ("source_doi", "source_type", "source_table",
                    "original_quote", "original_value", "original_unit",
                    "transformation")),
    ("Context", ("organism", "condition", "compartment", "gene_or_enzyme")),
    ("Verification", ("status", "reviewed_by", "reviewed_date",
                      "approved_by", "approved_date")),
    ("Cross-refs", ("cross_references", "selection_rationale",
                    "discrepancy_notes")),
    ("Gate", ("used_in_gate_tests", "gate_acknowledged",
              "acknowledgement_reason")),
]


def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    if isinstance(value, (list, dict)) and len(value) == 0:
        return True
    return False


def _format_value(value) -> str:
    if isinstance(value, VerificationStatus):
        return value.value
    if isinstance(value, list):
        if not value:
            return "[]"
        return yaml.dump(value, default_flow_style=False,
                         sort_keys=False).rstrip()
    return str(value)


def _print_card(card: ParameterCard) -> None:
    print(c(f"=== {card.parameter_id} ===", "bold"))
    status_str = c(card.status.value, _status_color(card.status))
    print(f"  status: {status_str}")
    print()
    for group_name, field_names in _GROUPS:
        if group_name == "Verification":
            # status already printed at top, keep here too for grouping
            pass
        print(c(f"[{group_name}]", "bold"))
        for fname in field_names:
            value = getattr(card, fname)
            display = _format_value(value)
            if _is_empty(value):
                print(f"  {fname}: " + c("(empty)", "yellow"))
            else:
                if "\n" in display:
                    print(f"  {fname}:")
                    for line in display.splitlines():
                        print(f"    {line}")
                else:
                    print(f"  {fname}: {display}")
        print()


def cmd_show(args: argparse.Namespace) -> int:
    cards = load_cards_from_yaml(args.yaml_file)
    card = _find_card(cards, args.param_id)
    if card is None:
        print(c(f"error: no card with parameter_id={args.param_id!r}", "red"),
              file=sys.stderr)
        return 2

    _print_card(card)

    issues = validate_card(card)
    if not issues:
        print(c("Validation: OK (no issues)", "green"))
    else:
        print(c(f"Validation issues ({len(issues)}):", "bold"))
        for iss in issues:
            color = {"ERROR": "red", "WARNING": "yellow",
                     "INFO": "blue"}[iss.severity.value]
            tag = c(f"[{iss.severity.value}]", color)
            print(f"  {tag} {iss.field}: {iss.message}")
    return 0


# ---------------------------------------------------------------------------
# `review` subcommand
# ---------------------------------------------------------------------------

def _ask_multiline(prompt: str) -> str:
    """Read a multi-line block. Terminate with a single ``.`` on its own line
    or an EOF.
    """
    print(prompt + " (end with a single '.' on its own line)")
    lines: list[str] = []
    while True:
        try:
            line = _ask("")
        except EOFError:
            break
        if line.strip() == ".":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def _abort(reason: str) -> int:
    print(c(f"ABORTED: {reason}", "red"))
    print("Card status left unchanged.")
    return 1


def cmd_review(args: argparse.Namespace) -> int:
    path = Path(args.yaml_file)
    cards = load_cards_from_yaml(path)
    card = _find_card(cards, args.param_id)
    if card is None:
        print(c(f"error: no card with parameter_id={args.param_id!r}", "red"),
              file=sys.stderr)
        return 2

    _print_card(card)

    if card.status is not VerificationStatus.DRAFT:
        print(c(f"Card is already {card.status.value}; nothing to review.",
                "yellow"))
        return 0

    print(c("--- REVIEW CHECKLIST ---", "bold"))

    # (a) DOI opened
    if not _ask_yes_no(
        f"Did you open the source DOI ({card.source_doi or '<missing>'})?"
    ):
        return _abort("Reviewer did not open the source DOI.")

    # (b) Original quote matches
    quote_choice = _ask_yes_no_edit(
        "Does the original_quote match the paper exactly?"
    )
    if quote_choice == "n":
        return _abort("original_quote does not match the paper.")
    if quote_choice == "edit":
        new_quote = _ask_multiline("Paste the corrected original_quote")
        if not new_quote:
            return _abort("Empty replacement quote.")
        card.original_quote = new_quote

    # (c) Value
    val_choice = _ask_yes_no_edit(
        f"Is value={card.value} {card.unit} correct as stated in the source?"
    )
    if val_choice == "n":
        return _abort("Value does not match the source.")
    if val_choice == "edit":
        raw = _ask("New value: ").strip()
        try:
            card.value = float(raw)
        except ValueError:
            return _abort(f"Could not parse new value {raw!r} as a float.")

    # (d) Unit
    unit_choice = _ask_yes_no_edit("Is the unit correct?")
    if unit_choice == "n":
        return _abort("Unit is incorrect.")
    if unit_choice == "edit":
        print(c("WARNING: changing the unit is the most common source of "
                "fabricated parameters. Make sure the new unit matches the "
                "paper exactly.", "yellow"))
        new_unit = _ask("New unit: ").strip()
        if not new_unit:
            return _abort("Empty replacement unit.")
        card.unit = new_unit

    # (e) Reviewer name
    reviewer = _ask("Your name (for reviewed_by): ").strip()
    if not reviewer:
        return _abort("Reviewer name is required.")

    # Promote
    card.status = VerificationStatus.REVIEWED
    card.reviewed_by = reviewer
    card.reviewed_date = _dt.date.today().isoformat()

    issues = validate_card(card)
    errors = [i for i in issues if i.severity is Severity.ERROR]
    if errors:
        # Roll back in-memory before saving
        card.status = VerificationStatus.DRAFT
        card.reviewed_by = ""
        card.reviewed_date = ""
        print(c("Validation errors after review — not saving:", "red"))
        for iss in errors:
            print(f"  - {iss.field}: {iss.message}")
        return 1

    header = _read_header_comments(path)
    _save_cards(cards, path, header=header)
    print(c(f"OK: {card.parameter_id} promoted DRAFT → REVIEWED "
            f"by {reviewer} on {card.reviewed_date}.", "green"))
    return 0


# ---------------------------------------------------------------------------
# `approve` subcommand
# ---------------------------------------------------------------------------

def cmd_approve(args: argparse.Namespace) -> int:
    path = Path(args.yaml_file)
    cards = load_cards_from_yaml(path)
    card = _find_card(cards, args.param_id)
    if card is None:
        print(c(f"error: no card with parameter_id={args.param_id!r}", "red"),
              file=sys.stderr)
        return 2

    if card.status is not VerificationStatus.REVIEWED:
        print(c(f"Must be REVIEWED first (current status: {card.status.value}).",
                "red"), file=sys.stderr)
        return 1

    _print_card(card)

    print(c("--- APPROVAL CHECKLIST ---", "bold"))

    if not _ask_yes_no(
        f"Does organism={card.organism!r} match the model context this "
        f"will be used in?"
    ):
        return _abort("Organism mismatch with target model.")

    if not _ask_yes_no(
        f"Does the parameter's mathematical role match what the model needs? "
        f"Source says source_type={card.source_type}."
    ):
        return _abort("Mathematical role does not match the model.")

    # Uncertainty bounds check
    needs_real_bounds = (
        card.uncertainty_lower is None
        or card.uncertainty_upper is None
        or (card.uncertainty_lower == card.value
            and card.uncertainty_upper == card.value)
    )
    if needs_real_bounds:
        print(c("Uncertainty bounds are missing or trivial (== value). "
                "Please provide real bounds.", "yellow"))
        try:
            lower = float(_ask("uncertainty_lower: ").strip())
            upper = float(_ask("uncertainty_upper: ").strip())
        except ValueError:
            return _abort("Could not parse uncertainty bounds as floats.")
        if lower > upper:
            return _abort("uncertainty_lower must be ≤ uncertainty_upper.")
        card.uncertainty_lower = lower
        card.uncertainty_upper = upper

    # Cross references
    if not card.cross_references:
        print(c("No cross_references on this card. Please add at least one.",
                "yellow"))
        xref_doi = _ask("cross_reference DOI: ").strip()
        try:
            xref_value = float(_ask("cross_reference value: ").strip())
        except ValueError:
            return _abort("Cross-reference value must be a float.")
        xref_unit = _ask("cross_reference unit: ").strip()
        agrees = _ask_yes_no("Does the cross-reference agree with this value?")
        xref_note = _ask("cross_reference note: ").strip()
        card.cross_references.append({
            "source_doi": xref_doi,
            "value": xref_value,
            "unit": xref_unit,
            "agrees": agrees,
            "note": xref_note,
        })

    # Selection rationale
    if not card.selection_rationale.strip():
        print(c("selection_rationale is empty. Please provide one.", "yellow"))
        rationale = _ask_multiline("Selection rationale")
        if not rationale:
            return _abort("Empty selection_rationale.")
        card.selection_rationale = rationale

    approver = _ask("Your name (for approved_by): ").strip()
    if not approver:
        return _abort("Approver name is required.")

    card.status = VerificationStatus.APPROVED
    card.approved_by = approver
    card.approved_date = _dt.date.today().isoformat()

    issues = validate_card(card)
    errors = [i for i in issues if i.severity is Severity.ERROR]
    if errors:
        card.status = VerificationStatus.REVIEWED
        card.approved_by = ""
        card.approved_date = ""
        print(c("Validation errors after approval — not saving:", "red"))
        for iss in errors:
            print(f"  - {iss.field}: {iss.message}")
        return 1

    ok, msg = ci_gate_check(cards)
    if not ok:
        card.status = VerificationStatus.REVIEWED
        card.approved_by = ""
        card.approved_date = ""
        print(c("CI gate check failed after approval — not saving:", "red"))
        print(msg)
        return 1

    header = _read_header_comments(path)
    _save_cards(cards, path, header=header)
    print(c(f"OK: {card.parameter_id} promoted REVIEWED → APPROVED "
            f"by {approver} on {card.approved_date}.", "green"))
    return 0


# ---------------------------------------------------------------------------
# `audit` and `audit-all`
# ---------------------------------------------------------------------------

def _coverage_bar(approved: int, total: int, width: int = 20) -> str:
    if total == 0:
        filled = width
        pct = 100.0
    else:
        pct = 100.0 * approved / total
        filled = int(round(width * approved / total))
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {approved}/{total} APPROVED ({pct:.0f}%)"


def cmd_audit(args: argparse.Namespace) -> int:
    cards = load_cards_from_yaml(args.yaml_file)
    report = audit_parameters(cards)
    print(report.summary())
    print()
    print(_coverage_bar(report.approved, report.total))
    print()
    ok, msg = ci_gate_check(cards)
    print(c(f"CI gate: {'PASS' if ok else 'FAIL'}", "green" if ok else "red"))
    print(msg)
    return 0 if ok else 1


def cmd_audit_all(args: argparse.Namespace) -> int:
    root = Path(args.root)
    files = sorted(root.glob("**/*.yaml"))
    if not files:
        print(f"(no YAML files found under {root})")
        return 0

    headers = ("file", "total", "DRAFT", "REVIEWED", "APPROVED", "gate")
    rows: list[tuple[str, ...]] = []
    total = approved = draft = reviewed = 0
    overall_ok = True

    for f in files:
        try:
            cards = load_cards_from_yaml(f)
        except Exception as exc:  # pragma: no cover - defensive
            rows.append((str(f.relative_to(root)), "ERR", "-", "-", "-",
                         f"load failed: {exc}"))
            overall_ok = False
            continue
        report = audit_parameters(cards)
        ok, _ = ci_gate_check(cards)
        if not ok:
            overall_ok = False
        total += report.total
        approved += report.approved
        draft += report.draft
        reviewed += report.reviewed
        rows.append((
            str(f.relative_to(root)),
            str(report.total),
            str(report.draft),
            str(report.reviewed),
            str(report.approved),
            "PASS" if ok else "FAIL",
        ))

    widths = [max(len(h), *(len(r[i]) for r in rows))
              for i, h in enumerate(headers)]

    def fmt(parts: Sequence[str]) -> str:
        return "  ".join(p.ljust(widths[i]) for i, p in enumerate(parts))

    print(c(fmt(headers), "bold"))
    print(c("  ".join("-" * w for w in widths), "grey"))
    for row in rows:
        print(fmt(row))
    print()
    print(_coverage_bar(approved, total))
    print(f"DRAFT={draft}  REVIEWED={reviewed}  APPROVED={approved}  total={total}")
    print(c(f"Overall: {'PASS' if overall_ok else 'FAIL'}",
            "green" if overall_ok else "red"))
    return 0 if overall_ok else 1


# ---------------------------------------------------------------------------
# argparse wiring
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="review_param",
        description="Interactive parameter review CLI for OpenCell.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("list", help="List all cards in a YAML file.")
    pl.add_argument("yaml_file")
    pl.add_argument("--status", choices=[s.value for s in VerificationStatus])
    pl.add_argument("--gate-only", action="store_true")
    pl.set_defaults(func=cmd_list)

    ps = sub.add_parser("show", help="Pretty-print a single card.")
    ps.add_argument("yaml_file")
    ps.add_argument("param_id")
    ps.set_defaults(func=cmd_show)

    pr = sub.add_parser("review",
                        help="Interactively promote DRAFT → REVIEWED.")
    pr.add_argument("yaml_file")
    pr.add_argument("param_id")
    pr.set_defaults(func=cmd_review)

    pa = sub.add_parser("approve",
                        help="Interactively promote REVIEWED → APPROVED.")
    pa.add_argument("yaml_file")
    pa.add_argument("param_id")
    pa.set_defaults(func=cmd_approve)

    pad = sub.add_parser("audit", help="Audit a single YAML file.")
    pad.add_argument("yaml_file")
    pad.set_defaults(func=cmd_audit)

    paa = sub.add_parser("audit-all",
                         help="Audit every YAML file under data/params/.")
    paa.add_argument("--root", default="data/params")
    paa.set_defaults(func=cmd_audit_all)

    return p


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
