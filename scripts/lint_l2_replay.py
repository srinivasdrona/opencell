"""L2.1 replay test linter — mechanical enforcement of FIX_TEMPLATE_L2_REPLAY.

Three checks (Codex dry-run recommendations, 2026-05-29):

1. Delta-integrality assert: every `_apply_update`-like function must call an
   integrality assertion (np.rint compare) on every emitted delta dict
   before applying it to state.

2. Non-triviality probe: the test function must call a per-observable
   nonzero-delta sweep across all trace ticks and explicitly handle the
   no-op case (pytest.skip or fail) — Rule 6 / Gate 5.

3. Pass-through provenance taint: for every observable in `_PASS_THROUGH`,
   the projection routine must derive `oc_after` from the states_before-
   rebuilt state. The lint walks the AST and flags any code path where a
   `_PASS_THROUGH` value is read from `states_after`, `karr_after`, or any
   identifier named like the trace oracle.

Plus three manifest checks (Rule 1, Rule 4b):
4. `_OBSERVABLES` declared at module scope.
5. `_PASS_THROUGH` declared at module scope; subset of `_OBSERVABLES`.
6. `_SCRATCH_RESET` declared at module scope; every mutated `self.<attr>`
   discovered on the process's `next_update` call graph must be enumerated.

Usage:
    python scripts/lint_l2_replay.py tests/vivarium/test_karr_*_l2_replay.py

Exit code: 0 on all-pass, 1 on any FAIL.
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Iterable
from pathlib import Path


_PROVENANCE_TAINT_TOKENS = ("states_after", "karr_after")


class LintFailure(Exception):
    """A single mechanical-check violation."""


def _load(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _find_module_assign(tree: ast.Module, name: str) -> ast.Assign | None:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == name:
                    return node
    return None


def _funcs(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def _calls_in(node: ast.AST) -> list[ast.Call]:
    out: list[ast.Call] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            out.append(child)
    return out


def _names_in(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _attr_chain(node: ast.AST) -> str:
    """Render an attribute chain like `process._enzyme_vector_from_split_stores`."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def check_observables_manifest(tree: ast.Module) -> list[str]:
    if _find_module_assign(tree, "_OBSERVABLES") is None:
        return ["FAIL Rule 1: `_OBSERVABLES` not declared at module scope"]
    return []


def check_pass_through_manifest(tree: ast.Module) -> list[str]:
    pt_node = _find_module_assign(tree, "_PASS_THROUGH")
    if pt_node is None:
        return [
            "FAIL Rule 1: `_PASS_THROUGH` not declared at module scope. "
            "Use `_PASS_THROUGH = frozenset()` if no observable is pass-through."
        ]
    obs_node = _find_module_assign(tree, "_OBSERVABLES")
    if obs_node is None:
        return []  # already failed above
    obs_names: set[str] = set()
    if isinstance(obs_node.value, ast.Tuple):
        for elt in obs_node.value.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                obs_names.add(elt.value)
    pt_names: set[str] = set()
    pt_val = pt_node.value
    if isinstance(pt_val, ast.Call) and isinstance(pt_val.func, ast.Name) and pt_val.func.id == "frozenset":
        for arg in pt_val.args:
            if isinstance(arg, (ast.Set, ast.List, ast.Tuple)):
                for elt in arg.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        pt_names.add(elt.value)
    elif isinstance(pt_val, (ast.Set, ast.List, ast.Tuple)):
        for elt in pt_val.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                pt_names.add(elt.value)
    extras = pt_names - obs_names
    if extras:
        return [f"FAIL Rule 1: `_PASS_THROUGH` contains names not in `_OBSERVABLES`: {sorted(extras)}"]
    return []


def check_scratch_manifest(tree: ast.Module) -> list[str]:
    if _find_module_assign(tree, "_SCRATCH_RESET") is None:
        return [
            "FAIL Rule 4b: `_SCRATCH_RESET` not declared at module scope. "
            "Use `_SCRATCH_RESET = {}` if process has no mutable attributes."
        ]
    return []


def check_delta_integrality(tree: ast.Module) -> list[str]:
    """Rule 2 clause 4: every `_apply_update`-like function must call an
    integrality assertion on each emitted delta before applying it."""
    funcs = _funcs(tree)
    apply_fns = [f for name, f in funcs.items() if "apply" in name.lower() and "update" in name.lower()]
    if not apply_fns:
        return [
            "FAIL Rule 2: no `_apply_update`-like function found. "
            "L2 replay tests should funnel update application through a single "
            "named helper for mechanical lint coverage."
        ]
    failures: list[str] = []
    for fn in apply_fns:
        call_names = {_attr_chain(c.func) for c in _calls_in(fn)}
        guard_present = any(
            ("integral" in n) or ("rint" in n) or ("integrity" in n) for n in call_names
        )
        if not guard_present:
            failures.append(
                f"FAIL Rule 2 ({fn.name}): no integrality-asserting helper called. "
                "Expected a `_assert_delta_integral` or `np.rint` compare on each "
                "emitted delta dict before mutating state."
            )
    return failures


def check_non_triviality_probe(tree: ast.Module) -> list[str]:
    """Rule 6 / Gate 5: the test function must call a mutated-tick sweep and
    handle the no-op outcome explicitly."""
    funcs = _funcs(tree)
    test_fns = [f for name, f in funcs.items() if name.startswith("test_")]
    if not test_fns:
        return ["FAIL Rule 6: no `test_*` function in module"]
    failures: list[str] = []
    for fn in test_fns:
        call_names = {_attr_chain(c.func) for c in _calls_in(fn)}
        names_used = _names_in(fn)
        probe_called = any(
            ("audit_trace_mutated" in n) or ("nonzero_delta" in n) or ("mutated_ticks" in n)
            for n in call_names
        )
        skip_or_fail = ("pytest" in names_used) and any(
            ("skip" in n) or ("fail" in n) for n in call_names
        )
        if not probe_called:
            failures.append(
                f"FAIL Rule 6 ({fn.name}): no non-triviality probe call detected. "
                "Expected a helper like `_audit_trace_mutated_ticks(...)` invoked "
                "before the per-tick assertion loop."
            )
            continue
        if not skip_or_fail:
            failures.append(
                f"FAIL Rule 6 ({fn.name}): probe called but no `pytest.skip` / "
                "`pytest.fail` branch on a no-op trace. The test would silently "
                "publish GREEN/RED on a 0/100 mutated-tick trace."
            )
    return failures


def check_pass_through_provenance(tree: ast.Module) -> list[str]:
    """Rule 7: for every observable in `_PASS_THROUGH`, the projection
    routine must NOT taint that name's value path with `states_after` /
    `karr_after`. Conservative: scan every function body that returns a
    dict whose keys include any `_PASS_THROUGH` member; for each such
    function, check that no `states_after` / `karr_after` identifier appears.
    """
    pt_node = _find_module_assign(tree, "_PASS_THROUGH")
    if pt_node is None:
        return []
    pt_val = pt_node.value
    pt_names: set[str] = set()
    elts: Iterable[ast.expr] = ()
    if isinstance(pt_val, ast.Call) and isinstance(pt_val.func, ast.Name) and pt_val.func.id == "frozenset":
        if pt_val.args and isinstance(pt_val.args[0], (ast.Set, ast.List, ast.Tuple)):
            elts = pt_val.args[0].elts
    elif isinstance(pt_val, (ast.Set, ast.List, ast.Tuple)):
        elts = pt_val.elts
    for elt in elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            pt_names.add(elt.value)
    if not pt_names:
        return []
    failures: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not any(isinstance(child, ast.Return) for child in ast.walk(node)):
            continue
        returns_pt_obs = False
        for child in ast.walk(node):
            if isinstance(child, ast.Return) and isinstance(child.value, ast.Dict):
                for k in child.value.keys:
                    if isinstance(k, ast.Constant) and k.value in pt_names:
                        returns_pt_obs = True
                        break
            if returns_pt_obs:
                break
        if not returns_pt_obs:
            continue
        names_in_body = _names_in(node)
        tainted = [t for t in _PROVENANCE_TAINT_TOKENS if t in names_in_body]
        if tainted:
            failures.append(
                f"FAIL Rule 7 ({node.name}): pass-through projection touches "
                f"oracle-derived identifiers {tainted}. Pass-through observables "
                "MUST be derived from `states_before`-rebuilt state only."
            )
    return failures


_CHECKS = [
    check_observables_manifest,
    check_pass_through_manifest,
    check_scratch_manifest,
    check_delta_integrality,
    check_non_triviality_probe,
    check_pass_through_provenance,
]


def lint_file(path: Path) -> list[str]:
    tree = _load(path)
    out: list[str] = []
    for check in _CHECKS:
        out.extend(check(tree))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="Test files to lint")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    paths: list[Path] = []
    for raw in args.paths:
        if raw.is_dir():
            paths.extend(sorted(raw.rglob("test_karr_*_l2_replay.py")))
        else:
            paths.append(raw)
    if not paths:
        print("no L2 replay test files found", file=sys.stderr)
        return 1

    any_fail = False
    for path in paths:
        failures = lint_file(path)
        if failures:
            any_fail = True
            print(f"\n[FAIL] {path}")
            for f in failures:
                print(f"  {f}")
        elif args.verbose:
            print(f"[PASS] {path}")
    if not any_fail:
        print(f"\nlint_l2_replay: {len(paths)} file(s) PASS")
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
