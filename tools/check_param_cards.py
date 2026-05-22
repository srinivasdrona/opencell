"""Smoke test: load and audit parameter cards."""

from __future__ import annotations

import sys
from pathlib import Path

from opencell.data.verification import (
    audit_parameters,
    ci_gate_check,
    load_cards_from_yaml,
)


def main() -> int:
    yaml_path = Path("data/params/micro_model_thattai2001.yaml")
    cards = load_cards_from_yaml(yaml_path)
    print(f"Loaded {len(cards)} cards from {yaml_path}")
    print()

    report = audit_parameters(cards)
    print(report.summary())
    print()

    ok, msg = ci_gate_check(cards)
    print(f"CI gate: {'PASS' if ok else 'FAIL'}")
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
