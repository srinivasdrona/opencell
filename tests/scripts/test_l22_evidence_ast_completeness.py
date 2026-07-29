"""Tests for `tests/scripts/_l22_ast_import_audit.py` (F5): the test-only
AST import-completeness audit that mechanically verifies
`schema.PROCESS_DEPENDENCY_FILES`/`schema.HARNESS_DEPENDENCY_FILES` have no
gaps relative to the REAL, CURRENT import graph. NEVER imported/used by
any evidence-generation code path (`scripts/l22_evidence/*.py`) -- this is
a test-only completeness check on the explicit registry, not a runtime
dependency-hashing mechanism itself (see `_l22_ast_import_audit.py`'s
module docstring for the full F1-rejection/F5-correction rationale).

Run via `bin\\oc-pytest tests/scripts/test_l22_evidence_ast_completeness.py -v`.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import catalog as cat  # noqa: E402
from scripts.l22_evidence import schema  # noqa: E402

from tests.scripts._l22_ast_import_audit import (  # noqa: E402
    ImportAuditError,
    first_party_import_files,
)

_ENTRIES = cat.in_scope_processes()

# Real module-scope imports verified NOT to feed actual metric computation
# (see `schema.KARR_TRANSLATION_V3_MODULE`'s comment for the full
# justification) -- excluded here, explicitly and by name, rather than
# silently omitted.
_DOCUMENTED_EXCLUSIONS = {schema.KARR_TRANSLATION_V3_MODULE.resolve()}


def _covered_files_for(entry: cat.ProcessEntry) -> set[Path]:
    covered = {path.resolve() for path in schema.SWEEP_PROVENANCE_SOURCE_FILES.values()}
    if entry.oc_module:
        covered.add((cat.REPO_ROOT / entry.oc_module).resolve())
    for path in schema.PROCESS_DEPENDENCY_FILES.get(entry.name, {}).values():
        covered.add(path.resolve())
    for path in schema.HARNESS_DEPENDENCY_FILES.get(entry.harness_type or "", {}).values():
        covered.add(path.resolve())
    return covered


# --- Real-tree regression guard: the actual point of this module -------------


def test_zero_uncovered_first_party_imports_across_real_in_scope_processes():
    """For EVERY real in-scope catalog process, every module-scope
    first-party import its `oc_module` makes must resolve to either: the
    four shared `SWEEP_PROVENANCE_SOURCE_FILES`, that process's own
    `oc_module`, an entry in `schema.PROCESS_DEPENDENCY_FILES[process]`, an
    entry in `schema.HARNESS_DEPENDENCY_FILES[harness_type]`, or the small,
    explicitly-documented `_DOCUMENTED_EXCLUSIONS` list. Zero uncovered
    imports is asserted for the REAL, CURRENT tree -- a future edit to any
    `karr_*.py` file that adds a new first-party import without a matching
    registry entry (or documented exclusion) fails this test loudly,
    rather than silently producing an incomplete sentinel."""
    uncovered: dict[str, list[str]] = {}
    for name, entry in _ENTRIES.items():
        if not entry.oc_module:
            continue
        oc_path = (cat.REPO_ROOT / entry.oc_module).resolve()
        imports = first_party_import_files(cat.REPO_ROOT, oc_path)
        covered = _covered_files_for(entry)
        missing = sorted(
            str(p.relative_to(cat.REPO_ROOT)) for p in imports if p.resolve() not in covered and p.resolve() not in _DOCUMENTED_EXCLUSIONS
        )
        if missing:
            uncovered[name] = missing
    assert not uncovered, f"uncovered first-party imports found (registry gap): {uncovered}"


def test_documented_exclusions_are_real_first_party_imports_not_dead_entries():
    """The one documented exclusion (`karr_translation_v3.py`, nested
    inside `karr_translation.py`'s `_install_translation_v3_release_guard`,
    not a module-scope import -- so it is never even picked up by
    `first_party_import_files`'s module-scope-only scan) must at least be
    a real, on-disk file, so the exclusion list itself cannot silently
    rot into referencing a deleted file."""
    for path in _DOCUMENTED_EXCLUSIONS:
        assert path.is_file(), f"documented exclusion {path} no longer exists"


# --- Adversarial: removed dependency key must surface as "uncovered" ---------


def test_removed_dependency_key_surfaces_as_uncovered(monkeypatch):
    """If a real registry entry a process genuinely needs is deliberately
    removed, the audit must flag that process's real import as
    "uncovered" -- proving the completeness check is not vacuously always
    passing regardless of registry contents."""
    entry = _ENTRIES["DNARepair"]
    reduced_registry = {"DNARepair": {"chromosome_store_module": schema.CHROMOSOME_STORE_MODULE}}  # views key dropped
    monkeypatch.setattr(schema, "PROCESS_DEPENDENCY_FILES", reduced_registry)

    oc_path = (cat.REPO_ROOT / entry.oc_module).resolve()
    imports = first_party_import_files(cat.REPO_ROOT, oc_path)
    covered = _covered_files_for(entry)
    uncovered = {p for p in imports if p.resolve() not in covered and p.resolve() not in _DOCUMENTED_EXCLUSIONS}
    assert schema.CHROMOSOME_VIEWS_MODULE.resolve() in {p.resolve() for p in uncovered}


# --- Adversarial: read/parse failure must raise, never silently degrade -----


def test_unreadable_file_raises_import_audit_error(tmp_path):
    missing = tmp_path / "does_not_exist.py"
    with pytest.raises(ImportAuditError):
        first_party_import_files(tmp_path, missing)


def test_unparseable_file_raises_import_audit_error(tmp_path):
    broken = tmp_path / "broken.py"
    broken.write_text("def f(:\n    pass\n", encoding="utf-8")  # deliberately invalid syntax
    with pytest.raises(ImportAuditError):
        first_party_import_files(tmp_path, broken)


# --- Import-idiom fixture coverage (synthetic tmp_path packages) ------------


def _make_pkg(root: Path, *parts: str) -> Path:
    pkg_dir = root.joinpath(*parts)
    pkg_dir.mkdir(parents=True, exist_ok=True)
    for i in range(1, len(parts) + 1):
        init = root.joinpath(*parts[:i], "__init__.py")
        if not init.exists():
            init.write_text("", encoding="utf-8")
    return pkg_dir


def test_import_idiom_plain_dotted_import(tmp_path):
    """`import a.b.c` (no `from`, no alias)."""
    _make_pkg(tmp_path, "pkg", "sub")
    target = tmp_path / "pkg" / "sub" / "mod.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    caller = tmp_path / "caller.py"
    caller.write_text("import pkg.sub.mod\n", encoding="utf-8")

    resolved = first_party_import_files(tmp_path, caller)
    assert target.resolve() in {p.resolve() for p in resolved}


def test_import_idiom_aliased_import(tmp_path):
    """`import a.b.c as x`."""
    _make_pkg(tmp_path, "pkg", "sub")
    target = tmp_path / "pkg" / "sub" / "mod.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    caller = tmp_path / "caller.py"
    caller.write_text("import pkg.sub.mod as m\n", encoding="utf-8")

    resolved = first_party_import_files(tmp_path, caller)
    assert target.resolve() in {p.resolve() for p in resolved}


def test_import_idiom_from_module_import_submodule(tmp_path):
    """`from a.b import c` where `c` is itself a submodule file (not a
    bare symbol) -- must resolve to the submodule file, not the package's
    `__init__.py`."""
    _make_pkg(tmp_path, "pkg", "sub")
    target = tmp_path / "pkg" / "sub" / "mod.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    caller = tmp_path / "caller.py"
    caller.write_text("from pkg.sub import mod\n", encoding="utf-8")

    resolved = first_party_import_files(tmp_path, caller)
    assert target.resolve() in {p.resolve() for p in resolved}


def test_import_idiom_from_package_import_symbol_falls_back_to_package_init(tmp_path):
    """`from pkg import symbol` where `symbol` is NOT itself a submodule
    file -- must fall back to resolving the containing package's
    `__init__.py` (mirrors the real `from opencell.util import
    MatlabRandStream` case)."""
    _make_pkg(tmp_path, "pkg")
    (tmp_path / "pkg" / "__init__.py").write_text("from .impl import Something\n", encoding="utf-8")
    caller = tmp_path / "caller.py"
    caller.write_text("from pkg import Something\n", encoding="utf-8")

    resolved = first_party_import_files(tmp_path, caller)
    assert (tmp_path / "pkg" / "__init__.py").resolve() in {p.resolve() for p in resolved}


def test_import_idiom_relative_import_from_package(tmp_path):
    """`from . import X` inside a module belonging to a package -- resolves
    against the importing file's OWN containing package (mirrors the real
    `karr_translation.py`'s `from . import karr_translation_v3`)."""
    _make_pkg(tmp_path, "pkg")
    sibling = tmp_path / "pkg" / "sibling.py"
    sibling.write_text("VALUE = 1\n", encoding="utf-8")
    caller = tmp_path / "pkg" / "caller.py"
    caller.write_text("from . import sibling\n", encoding="utf-8")

    resolved = first_party_import_files(tmp_path, caller)
    assert sibling.resolve() in {p.resolve() for p in resolved}


def test_import_idiom_relative_import_with_submodule(tmp_path):
    """`from .foo import X`."""
    _make_pkg(tmp_path, "pkg")
    foo = tmp_path / "pkg" / "foo.py"
    foo.write_text("VALUE = 1\n", encoding="utf-8")
    caller = tmp_path / "pkg" / "caller.py"
    caller.write_text("from .foo import VALUE\n", encoding="utf-8")

    resolved = first_party_import_files(tmp_path, caller)
    assert foo.resolve() in {p.resolve() for p in resolved}


def test_import_idiom_relative_import_one_level_up(tmp_path):
    """`from .. import X` -- resolves one package level above the
    importing module's own package."""
    _make_pkg(tmp_path, "pkg", "sub")
    parent_sibling = tmp_path / "pkg" / "parent_sibling.py"
    parent_sibling.write_text("VALUE = 1\n", encoding="utf-8")
    caller = tmp_path / "pkg" / "sub" / "caller.py"
    caller.write_text("from .. import parent_sibling\n", encoding="utf-8")

    resolved = first_party_import_files(tmp_path, caller)
    assert parent_sibling.resolve() in {p.resolve() for p in resolved}


def test_import_idiom_third_party_stdlib_imports_are_never_first_party(tmp_path):
    """`import os` / `from pathlib import Path` -- neither resolves to any
    file under the (synthetic) repo root, so both are correctly excluded
    from the first-party result set (no false positives)."""
    caller = tmp_path / "caller.py"
    caller.write_text(
        textwrap.dedent(
            """
            import os
            from pathlib import Path
            import numpy as np
            """
        ),
        encoding="utf-8",
    )
    resolved = first_party_import_files(tmp_path, caller)
    assert resolved == set()


def test_import_idiom_self_import_is_excluded(tmp_path):
    """A (contrived) self-referential import of the caller's own module
    must never be reported as one of ITS OWN uncovered dependencies."""
    _make_pkg(tmp_path, "pkg")
    caller = tmp_path / "pkg" / "caller.py"
    caller.write_text("import pkg.caller\n", encoding="utf-8")

    resolved = first_party_import_files(tmp_path, caller)
    assert caller.resolve() not in {p.resolve() for p in resolved}


# --- C1: module-scope-equivalent control-flow traversal (try/if/with/loops) --


def test_import_idiom_try_guarded_import_is_detected(tmp_path):
    """`try: import X` / `except ImportError: import Y` -- both branches
    execute unconditionally at import time (exactly one of them, but
    which one is data/environment-dependent), so BOTH must be detected as
    real, module-scope-equivalent dependencies (C1)."""
    _make_pkg(tmp_path, "pkg")
    primary = tmp_path / "pkg" / "primary.py"
    primary.write_text("VALUE = 1\n", encoding="utf-8")
    fallback = tmp_path / "pkg" / "fallback.py"
    fallback.write_text("VALUE = 2\n", encoding="utf-8")
    caller = tmp_path / "pkg" / "caller.py"
    caller.write_text(
        textwrap.dedent(
            """
            try:
                from . import primary
            except ImportError:
                from . import fallback
            """
        ),
        encoding="utf-8",
    )

    resolved = {p.resolve() for p in first_party_import_files(tmp_path, caller)}
    assert primary.resolve() in resolved
    assert fallback.resolve() in resolved


def test_import_idiom_try_else_finally_import_is_detected(tmp_path):
    """Imports in a `try` block's `else`/`finally` clauses also execute
    unconditionally as part of running the module and must be detected."""
    _make_pkg(tmp_path, "pkg")
    else_mod = tmp_path / "pkg" / "else_mod.py"
    else_mod.write_text("VALUE = 1\n", encoding="utf-8")
    finally_mod = tmp_path / "pkg" / "finally_mod.py"
    finally_mod.write_text("VALUE = 2\n", encoding="utf-8")
    caller = tmp_path / "pkg" / "caller.py"
    caller.write_text(
        textwrap.dedent(
            """
            try:
                pass
            except Exception:
                pass
            else:
                from . import else_mod
            finally:
                from . import finally_mod
            """
        ),
        encoding="utf-8",
    )

    resolved = {p.resolve() for p in first_party_import_files(tmp_path, caller)}
    assert else_mod.resolve() in resolved
    assert finally_mod.resolve() in resolved


def test_import_idiom_if_guarded_import_is_detected(tmp_path):
    """`if <condition>: import X else: import Y` -- both module-scope `if`
    branches must be detected, regardless of which branch is actually live
    at any given runtime (C1)."""
    _make_pkg(tmp_path, "pkg")
    if_mod = tmp_path / "pkg" / "if_mod.py"
    if_mod.write_text("VALUE = 1\n", encoding="utf-8")
    else_mod = tmp_path / "pkg" / "else_mod.py"
    else_mod.write_text("VALUE = 2\n", encoding="utf-8")
    caller = tmp_path / "pkg" / "caller.py"
    caller.write_text(
        textwrap.dedent(
            """
            import sys
            if sys.platform == "win32":
                from . import if_mod
            else:
                from . import else_mod
            """
        ),
        encoding="utf-8",
    )

    resolved = {p.resolve() for p in first_party_import_files(tmp_path, caller)}
    assert if_mod.resolve() in resolved
    assert else_mod.resolve() in resolved


def test_import_idiom_type_checking_guarded_import_is_detected(tmp_path):
    """`if TYPE_CHECKING: import X` -- per the explicit "prefer detection
    since registry completeness is cheap" policy, a TYPE_CHECKING-guarded
    import is detected the same as any other `if`-guarded import (not
    special-cased/ignored), even though it never actually executes at
    real runtime -- registering it costs nothing and removes any doubt."""
    _make_pkg(tmp_path, "pkg")
    typing_only = tmp_path / "pkg" / "typing_only.py"
    typing_only.write_text("VALUE = 1\n", encoding="utf-8")
    caller = tmp_path / "pkg" / "caller.py"
    caller.write_text(
        textwrap.dedent(
            """
            from typing import TYPE_CHECKING
            if TYPE_CHECKING:
                from . import typing_only
            """
        ),
        encoding="utf-8",
    )

    resolved = {p.resolve() for p in first_party_import_files(tmp_path, caller)}
    assert typing_only.resolve() in resolved


def test_import_idiom_with_guarded_import_is_detected(tmp_path):
    """An import nested inside a module-scope `with` block (unusual but
    syntactically legal) must be detected."""
    _make_pkg(tmp_path, "pkg")
    target = tmp_path / "pkg" / "with_mod.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    caller = tmp_path / "pkg" / "caller.py"
    caller.write_text(
        textwrap.dedent(
            """
            from contextlib import suppress
            with suppress(Exception):
                from . import with_mod
            """
        ),
        encoding="utf-8",
    )

    resolved = {p.resolve() for p in first_party_import_files(tmp_path, caller)}
    assert target.resolve() in resolved


def test_import_idiom_loop_guarded_import_is_detected(tmp_path):
    """An import nested inside a module-scope `for` loop (unusual but
    syntactically legal -- "loops if imports possible" per the C1
    instruction) must be detected."""
    _make_pkg(tmp_path, "pkg")
    target = tmp_path / "pkg" / "loop_mod.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    caller = tmp_path / "pkg" / "caller.py"
    caller.write_text(
        textwrap.dedent(
            """
            for _ in range(1):
                from . import loop_mod
            """
        ),
        encoding="utf-8",
    )

    resolved = {p.resolve() for p in first_party_import_files(tmp_path, caller)}
    assert target.resolve() in resolved


def test_import_idiom_match_case_guarded_import_is_detected(tmp_path):
    """`match ...: case A: import X; case B: import Y` -- every `case`
    clause's own body must be descended (exactly one branch executes at
    runtime, but which is data-dependent, same reasoning as `if`/`elif`/
    `else`) -- final zero-cost delta hardening."""
    _make_pkg(tmp_path, "pkg")
    case_a = tmp_path / "pkg" / "case_a.py"
    case_a.write_text("VALUE = 1\n", encoding="utf-8")
    case_b = tmp_path / "pkg" / "case_b.py"
    case_b.write_text("VALUE = 2\n", encoding="utf-8")
    case_default = tmp_path / "pkg" / "case_default.py"
    case_default.write_text("VALUE = 3\n", encoding="utf-8")
    caller = tmp_path / "pkg" / "caller.py"
    caller.write_text(
        textwrap.dedent(
            """
            import sys
            match sys.platform:
                case "win32":
                    from . import case_a
                case "linux":
                    from . import case_b
                case _:
                    from . import case_default
            """
        ),
        encoding="utf-8",
    )

    resolved = {p.resolve() for p in first_party_import_files(tmp_path, caller)}
    assert case_a.resolve() in resolved
    assert case_b.resolve() in resolved
    assert case_default.resolve() in resolved


def test_import_idiom_trystar_guarded_import_is_detected(tmp_path):
    """`try: ... except* ValueError: import X` (`ast.TryStar`, Python
    3.11+ exception groups) -- traversed identically to a plain `ast.Try`
    (body/handlers/orelse/finalbody) -- final zero-cost delta hardening."""
    _make_pkg(tmp_path, "pkg")
    handler_mod = tmp_path / "pkg" / "trystar_handler.py"
    handler_mod.write_text("VALUE = 1\n", encoding="utf-8")
    else_mod = tmp_path / "pkg" / "trystar_else.py"
    else_mod.write_text("VALUE = 2\n", encoding="utf-8")
    finally_mod = tmp_path / "pkg" / "trystar_finally.py"
    finally_mod.write_text("VALUE = 3\n", encoding="utf-8")
    caller = tmp_path / "pkg" / "caller.py"
    caller.write_text(
        textwrap.dedent(
            """
            try:
                pass
            except* ValueError:
                from . import trystar_handler
            else:
                from . import trystar_else
            finally:
                from . import trystar_finally
            """
        ),
        encoding="utf-8",
    )

    resolved = {p.resolve() for p in first_party_import_files(tmp_path, caller)}
    assert handler_mod.resolve() in resolved
    assert else_mod.resolve() in resolved
    assert finally_mod.resolve() in resolved


def test_import_idiom_function_and_class_body_imports_still_excluded(tmp_path):
    """C1 only expands traversal into try/if/with/loop bodies -- function
    and class bodies remain OUT of scope, even though they too execute
    (a class body at class-definition/import time; a function body only
    on call), exactly as before C1. This is the control case proving C1's
    traversal expansion did not accidentally also start descending into
    function/class bodies."""
    _make_pkg(tmp_path, "pkg")
    func_target = tmp_path / "pkg" / "func_mod.py"
    func_target.write_text("VALUE = 1\n", encoding="utf-8")
    class_target = tmp_path / "pkg" / "class_mod.py"
    class_target.write_text("VALUE = 2\n", encoding="utf-8")
    caller = tmp_path / "pkg" / "caller.py"
    caller.write_text(
        textwrap.dedent(
            """
            def f():
                from . import func_mod

            class C:
                from . import class_mod
            """
        ),
        encoding="utf-8",
    )

    resolved = {p.resolve() for p in first_party_import_files(tmp_path, caller)}
    assert func_target.resolve() not in resolved
    assert class_target.resolve() not in resolved


# --- C1: invalid/unresolvable relative imports must raise, never skip -------


def test_excessive_relative_import_level_raises(tmp_path):
    """`from .. import X` used one level too many (i.e. `level - 1` would
    walk above the importing file's own package depth) must raise
    `ImportAuditError`, never silently resolve to the repo root or skip
    the import entirely."""
    _make_pkg(tmp_path, "pkg")
    caller = tmp_path / "pkg" / "caller.py"
    caller.write_text("from .. import something\n", encoding="utf-8")

    with pytest.raises(ImportAuditError):
        first_party_import_files(tmp_path, caller)


def test_bare_unresolvable_relative_import_raises(tmp_path):
    """A syntactically valid relative import whose target does not exist
    on disk at all (neither as a submodule file nor as a package `__init__.py`)
    must raise `ImportAuditError` -- a relative import can only ever name
    something first-party, so failing to resolve it is never treated as
    "must be third-party, skip it" the way an unresolved ABSOLUTE import
    legitimately is."""
    _make_pkg(tmp_path, "pkg")
    caller = tmp_path / "pkg" / "caller.py"
    caller.write_text("from .missing_subpkg import missing_symbol\n", encoding="utf-8")

    with pytest.raises(ImportAuditError):
        first_party_import_files(tmp_path, caller)
