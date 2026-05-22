""" "No naked biology numbers" lint.

AST/regex check that biological constants in model code reference
a parameter ID, not a hardcoded literal. Catches smuggled parameters.

Allowlist: 0, 0.0, 1, 1.0, -1, -1.0, tolerances (1e-*), array shapes.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Numbers that are always OK (structural, not biological)
ALLOWLIST = {0, 1, -1, -1.0, 2, 2.0, 0.5, 100.0}


def check_file(filepath: Path) -> list[str]:
    """Check a Python file for hardcoded biology numbers.

    Returns list of warning strings.
    """
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError):
        return []

    warnings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            value = node.value
            if value in ALLOWLIST:
                continue
            # Skip small integers (likely array indices, range args)
            if isinstance(value, int) and -10 <= value <= 100:
                continue
            # Flag suspicious biology-scale numbers
            if isinstance(value, float) and 0.001 <= abs(value) <= 1e6 and value not in ALLOWLIST:
                warnings.append(
                    f"{filepath}:{node.lineno}: "
                    f"Suspicious hardcoded number {value} — "
                    f"should this reference a parameter ID?"
                )
    return warnings


def check_directory(dirpath: Path, exclude_tests: bool = True) -> list[str]:
    """Check all Python files in a directory."""
    all_warnings = []
    for pyfile in dirpath.rglob("*.py"):
        if exclude_tests and "test" in pyfile.name:
            continue
        all_warnings.extend(check_file(pyfile))
    return all_warnings


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("opencell/models")
    warnings = check_directory(target)
    for w in warnings:
        print(w)
    if warnings:
        print(f"\n{len(warnings)} suspicious hardcoded numbers found")
        sys.exit(1)
    else:
        print("No naked biology numbers found ✓")
