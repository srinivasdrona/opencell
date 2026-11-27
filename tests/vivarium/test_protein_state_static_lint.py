from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_c10_no_updater_override_escape_on_protein_port() -> None:
    """Claim C10: No production module under opencell/vivarium/ may emit a dict

    containing '_updater' anywhere inside an update destined for the 'protein' port.
    Prevents defeating the rejecting callable updater via vivarium's store.py:745 override hole.
    Scoped strictly to values routed to the 'protein' port.
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
                    # Identify variables routed to update["protein"]
                    protein_vars: set[str] = set()
                    for sub in ast.walk(method):
                        if isinstance(sub, ast.Assign):
                            for target in sub.targets:
                                if (
                                    isinstance(target, ast.Subscript)
                                    and isinstance(target.slice, ast.Constant)
                                    and target.slice.value == "protein"
                                    and isinstance(sub.value, ast.Name)
                                ):
                                    protein_vars.add(sub.value.id)

                    # Check dict literals assigned directly under protein port or to protein_vars
                    for sub in ast.walk(method):
                        if isinstance(sub, ast.Assign):
                            for target in sub.targets:
                                is_protein_target = (
                                    isinstance(target, ast.Subscript)
                                    and isinstance(target.slice, ast.Constant)
                                    and target.slice.value == "protein"
                                )
                                is_protein_var_target = (
                                    isinstance(target, ast.Name) and target.id in protein_vars
                                )
                                if is_protein_target or is_protein_var_target:
                                    for inner in ast.walk(sub.value):
                                        if isinstance(inner, ast.Dict):
                                            for key in inner.keys:
                                                if isinstance(key, ast.Constant) and key.value == "_updater":
                                                    violations.append(
                                                        f"{py_file.name}::{node.name}::{method.name} emits '_updater' on protein port"
                                                    )
                        elif (
                            isinstance(sub, ast.Subscript)
                            and isinstance(sub.slice, ast.Constant)
                            and sub.slice.value == "_updater"
                        ):
                            chain: list[str] = []
                            curr = sub.value
                            while isinstance(curr, ast.Subscript):
                                if isinstance(curr.slice, ast.Constant) and isinstance(curr.slice.value, str):
                                    chain.append(curr.slice.value)
                                curr = curr.value
                            if isinstance(curr, ast.Name) and (curr.id in protein_vars or "protein" in chain):
                                violations.append(
                                    f"{py_file.name}::{node.name}::{method.name} assigns '_updater' under protein port"
                                )

    assert not violations, (
        "Claim C10 violation: production code must not emit '_updater' under protein port:\n"
        + "\n".join(violations)
    )


def test_c11_biological_compartment_ids_only() -> None:
    """Claim C11: Every compartment key in production source under compartment_counts

    must belong to ('c', 'd', 'e', 'm', 'tc', 'tm').
    Scoped to TOA (finding TOA-COMPARTMENT-PROJECTION) and all compartment_counts updates/schemas.
    """
    vivarium_dir = _REPO_ROOT / "opencell" / "vivarium"
    violations: list[str] = []

    # 1. TOA must not project source/destination to generic compartment_0 / compartment_1
    toa_file = vivarium_dir / "karr_terminal_organelle_assembly.py"
    if toa_file.exists():
        toa_text = toa_file.read_text(encoding="utf-8")
        if "compartment_0" in toa_text or "compartment_1" in toa_text:
            violations.append(
                "karr_terminal_organelle_assembly.py contains legacy generic compartment labels "
                "('compartment_0' or 'compartment_1'); must resolve biological tm/m, tc/c from fixture"
            )

    # 2. Any compartment_counts schema or update literal across vivarium must use biological compartments only
    for py_file in sorted(vivarium_dir.glob("*.py")):
        if py_file.name.startswith(("_", "test")):
            continue
        source_text = py_file.read_text(encoding="utf-8")
        if "compartment_counts" not in source_text:
            continue
        tree = ast.parse(source_text, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for key, val in zip(node.keys, node.values, strict=False):
                    if isinstance(key, ast.Constant) and key.value == "compartment_counts":
                        # Check keys inside the compartment_counts structure
                        for sub in ast.walk(val):
                            if (
                                isinstance(sub, ast.Constant)
                                and isinstance(sub.value, str)
                                and sub.value in ("compartment_0", "compartment_1")
                            ):
                                violations.append(
                                    f"{py_file.name} uses generic compartment label {sub.value!r} under compartment_counts"
                                )

    assert not violations, (
        "Claim C11 violation: generic compartment labels found in production code:\n"
        + "\n".join(violations)
    )
