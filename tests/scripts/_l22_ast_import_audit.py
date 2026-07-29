"""Test-only AST import-completeness audit for the L2.2 evidence
dependency registry (F5, hardened C1).

NEVER used by the runtime hashing/staleness path
(`scripts/l22_evidence/schema.py`/`sweep.py`/`generator.py`) -- those read
ONLY the explicit, hand-maintained `schema.PROCESS_DEPENDENCY_FILES`/
`schema.HARNESS_DEPENDENCY_FILES` registries, never this module. This
exists solely so a TEST can mechanically verify that registry has no gaps
relative to the REAL, CURRENT import graph: a registry omission fails a
test loudly, in CI, long before it could silently produce a false-green
sentinel. Deliberately not wired into any evidence-generation code path
(no import of this module from anywhere under `scripts/l22_evidence/`).

A prior revision (F1, rejected by Opus5) computed dependency hashes by
AST-scanning a process's `oc_module` source AT RUNTIME, inside the actual
hashing/staleness path. F5's correction: the runtime path must use ONLY a
small, explicit, hand-maintained registry; AST-scanning belongs here,
test-only, as a completeness CHECK on that registry -- never as the
source of gating hashes itself.

Scope, by design (not a generalized/recursive import-graph platform):
  * MODULE-SCOPE-EXECUTING statements only (C1 hardening): top-level
    `import`/`from ... import` statements, AND those nested inside
    `try`/`except`/`else`/`finally`, `if`/`elif`/`else` (including
    `if TYPE_CHECKING:` blocks -- detected, not special-cased: a
    guard-conditional import is still traversed the same as any other
    `if` body, per the "prefer detection since completeness is cheap"
    policy), `with`/`async with`, and `for`/`async for`/`while` bodies
    (loops CAN contain imports, however unusual) -- since all of these
    execute unconditionally-at-import-time control flow, unlike a
    function or class body. Function/class bodies remain OUT of scope by
    design, even one invoked unconditionally at import time (see
    `karr_translation.py`'s `_install_translation_v3_release_guard()`, a
    function-body import) or one that executes at class-definition time
    (see `ChromosomeStore`'s class-body `from opencell.m_gen_constants
    import ...` in `opencell/state/chromosome_store.py`) -- both are
    registered anyway, defensively, in `schema.PROCESS_DEPENDENCY_FILES`,
    so the exclusion costs nothing either way; see
    `_DOCUMENTED_EXCLUSIONS` in `test_l22_evidence_ast_completeness.py`.
  * ONE level deep: resolves each import statement's own target to a
    file, never recurses into what THAT file itself imports.
  * Read/parse failures raise `ImportAuditError` -- never silently
    degrade to "no imports found" (the previous mechanical-derivation
    revision's `except (SyntaxError, OSError, UnicodeDecodeError): return
    set()` swallow is exactly the kind of silent blind spot F5 replaces).
  * An UNRESOLVABLE relative import -- either because its `level` walks
    above the importing file's own package depth (e.g. `from ... import
    X` used one level too many), or because neither the submodule nor the
    containing-package fallback resolves to a real on-disk file -- also
    raises `ImportAuditError` (C1 hardening). By definition, a relative
    import can only ever target something first-party; unlike an absolute
    import (which legitimately may name a third-party/stdlib package and
    is silently excluded from the result), a relative import that fails
    to resolve indicates either a bug in this audit's resolution logic or
    genuinely broken source -- both must fail loudly, never silently
    resolve to "no dependency" or get skipped.
"""

from __future__ import annotations

import ast
from pathlib import Path


class ImportAuditError(RuntimeError):
    """Raised when a source file cannot be read or parsed. Callers must
    treat this as a hard failure -- never caught and silently converted
    into "this file has no imports"."""


def _package_of(repo_root: Path, source_path: Path) -> str:
    """Dotted package name containing `source_path` (e.g.
    "opencell.vivarium" for ".../opencell/vivarium/karr_translation.py"),
    used to resolve relative imports (`from . import X` / `from .foo
    import X`). Identical for a plain module file and its own package's
    `__init__.py` -- both live "in" the same containing package for
    relative-import purposes."""
    rel = source_path.resolve().relative_to(repo_root.resolve())
    parts = rel.parts[:-1]  # drop the filename itself
    return ".".join(parts)


def _resolve_dotted_to_file(repo_root: Path, dotted: str) -> Path | None:
    """A dotted module path (e.g. "opencell.m1.karr_metabolism") to its
    on-disk file: prefers a plain module file
    ("opencell/m1/karr_metabolism.py"), falls back to a package
    ("opencell/util/__init__.py"). Returns None if neither exists --
    third-party/stdlib target, or a symbol/attribute (not a submodule)
    import; callers fall back to resolving the containing package/module
    instead in that case."""
    if not dotted:
        return None
    rel_parts = [part for part in dotted.split(".") if part]
    if not rel_parts:
        return None
    as_module = repo_root.joinpath(*rel_parts).with_suffix(".py")
    if as_module.is_file():
        return as_module
    as_package_init = repo_root.joinpath(*rel_parts, "__init__.py")
    if as_package_init.is_file():
        return as_package_init
    return None


def _iter_module_scope_statements(body: list[ast.stmt]):
    """Yield every statement that executes at MODULE-SCOPE-EQUIVALENT time
    when `body` runs -- i.e. `body` itself, plus recursively descending
    into `try`/`except`/`else`/`finally`, `if`/`elif`/`else`,
    `with`/`async with`, and `for`/`async for`/`while` (+ their `else`)
    bodies (C1 hardening: these all execute unconditionally as part of
    running the enclosing module, so an import nested inside one of them
    -- a try-guarded fallback import, an `if TYPE_CHECKING:` guard, etc.
    -- is still a real, module-scope-equivalent import). Deliberately
    does NOT descend into `FunctionDef`/`AsyncFunctionDef`/`ClassDef`
    bodies (or lambdas) -- those only execute later (on call) or execute
    once at class-definition time but are excluded by design; see the
    module docstring and `_DOCUMENTED_EXCLUSIONS`."""
    for node in body:
        yield node
        if isinstance(node, ast.Try):
            yield from _iter_module_scope_statements(node.body)
            for handler in node.handlers:
                yield from _iter_module_scope_statements(handler.body)
            yield from _iter_module_scope_statements(node.orelse)
            yield from _iter_module_scope_statements(node.finalbody)
        elif isinstance(node, ast.If):
            yield from _iter_module_scope_statements(node.body)
            yield from _iter_module_scope_statements(node.orelse)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            yield from _iter_module_scope_statements(node.body)
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            yield from _iter_module_scope_statements(node.body)
            yield from _iter_module_scope_statements(node.orelse)
        # FunctionDef/AsyncFunctionDef/ClassDef: deliberately not descended.


def first_party_import_files(repo_root: Path, source_path: Path) -> set[Path]:
    """Every file `source_path` imports, at MODULE SCOPE (or nested inside
    module-scope-equivalent control flow -- `try`/`if`/`with`/loops; see
    `_iter_module_scope_statements`), that resolves to a real, on-disk,
    first-party (i.e. under `repo_root`) module/package file. Handles
    `import a.b.c`, aliased imports (`import a.b.c as x` / `from a.b.c
    import X as y`), `from a.b.c import X` (disambiguating "X is a
    submodule" -- e.g. `from opencell.m1 import karr_metabolism` -- from
    "X is a symbol" -- e.g. `from opencell.util import MatlabRandStream`,
    which falls back to the containing package `opencell/util/__init__.py`
    -- via on-disk resolution), and relative imports (`from . import X` /
    `from .foo import X`, resolved against `source_path`'s own containing
    package). Raises `ImportAuditError` on any read/parse failure, an
    excessive relative-import `level`, or an unresolvable relative import
    -- NEVER silently returns an empty set for a broken file or silently
    drops a relative import it could not resolve."""
    try:
        text = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ImportAuditError(f"cannot read {source_path}: {exc}") from exc
    try:
        tree = ast.parse(text, filename=str(source_path))
    except SyntaxError as exc:
        raise ImportAuditError(f"cannot parse {source_path}: {exc}") from exc

    resolved: set[Path] = set()
    own_package = _package_of(repo_root, source_path)
    own_package_parts = own_package.split(".") if own_package else []

    for node in _iter_module_scope_statements(tree.body):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = _resolve_dotted_to_file(repo_root, alias.name)
                if target is not None:
                    resolved.add(target)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                # Relative import: level=1 ("from . import X" / "from .foo
                # import X") resolves within `source_path`'s OWN containing
                # package; level=2 ("from .. import X") one package up;
                # etc.
                up = node.level - 1
                if up >= len(own_package_parts):
                    raise ImportAuditError(
                        f"{source_path}: relative import level={node.level} exceeds "
                        f"the importing file's own package depth ({own_package!r})"
                    )
                base_parts = own_package_parts[: len(own_package_parts) - up]
                base = ".".join(base_parts)
                module = f"{base}.{node.module}" if node.module else base
                for alias in node.names:
                    candidate = f"{module}.{alias.name}"
                    target = _resolve_dotted_to_file(repo_root, candidate)
                    if target is None:
                        target = _resolve_dotted_to_file(repo_root, module)
                    if target is None:
                        # A relative import can only ever name something
                        # first-party -- unlike an absolute import, there
                        # is no legitimate third-party/stdlib case here.
                        raise ImportAuditError(
                            f"{source_path}: unresolvable relative import "
                            f"'{'.' * node.level}{node.module or ''}' (alias "
                            f"{alias.name!r}) -- neither {module}.{alias.name} nor "
                            f"{module} resolves to a file under {repo_root}"
                        )
                    resolved.add(target)
                continue
            module = node.module or ""
            if not module:
                continue
            for alias in node.names:
                candidate = f"{module}.{alias.name}"
                target = _resolve_dotted_to_file(repo_root, candidate)
                if target is None:
                    target = _resolve_dotted_to_file(repo_root, module)
                if target is not None:
                    resolved.add(target)

    resolved.discard(source_path.resolve())
    return resolved

