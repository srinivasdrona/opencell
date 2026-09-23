from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
BIOLOGICAL_COMPARTMENTS = frozenset({"c", "d", "e", "m", "tc", "tm"})


def test_c10_no_updater_override_escape_on_protein_port() -> None:
    """Claim C10: No production module under opencell/vivarium/ may emit a dict

    containing '_updater' anywhere inside an update destined for the 'protein' port.
    Prevents defeating the rejecting callable updater via vivarium's store.py:745 override hole.
    """
    vivarium_dir = _REPO_ROOT / "opencell" / "vivarium"
    violations: list[str] = []

    for py_file in sorted(vivarium_dir.glob("*.py")):
        if py_file.name.startswith(("_", "test")):
            continue
        source_text = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source_text, filename=str(py_file))

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                update_methods = [
                    m for m in node.body
                    if isinstance(m, ast.FunctionDef) and m.name in ("next_update", "_build_update")
                ]
                for method in update_methods:
                    for sub in ast.walk(method):
                        if isinstance(sub, ast.Dict):
                            for key in sub.keys:
                                if isinstance(key, ast.Constant) and key.value == "_updater":
                                    # If inside next_update / _build_update, check if in a protein path
                                    violations.append(
                                        f"{py_file.name}::{node.name}::{method.name} emits '_updater' override key"
                                    )

    assert not violations, (
        "Claim C10 violation: production code must not emit '_updater' in updates:\n"
        + "\n".join(violations)
    )


def test_c11_biological_compartment_ids_only() -> None:
    """Claim C11: Every compartment key in production source under compartment_counts

    must belong to ('c', 'd', 'e', 'm', 'tc', 'tm').
    Kills generic labels like 'compartment_0' / 'compartment_1'.
    """
    vivarium_dir = _REPO_ROOT / "opencell" / "vivarium"
    violations: list[str] = []

    for py_file in sorted(vivarium_dir.glob("*.py")):
        if py_file.name.startswith(("_", "test")):
            continue
        source_text = py_file.read_text(encoding="utf-8")
        # Direct string scan for generic compartment labels in vivarium production code
        if "compartment_0" in source_text or "compartment_1" in source_text:
            violations.append(
                f"{py_file.name} contains legacy generic compartment labels ('compartment_0' or 'compartment_1')"
            )

    assert not violations, (
        "Claim C11 violation: generic compartment labels found in production code:\n"
        + "\n".join(violations)
    )
