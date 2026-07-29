"""Test-only AST import-completeness audit for the L2.2 evidence
dependency registry (F5).

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
  * MODULE-SCOPE only -- direct top-level `import`/`from ... import`
    statements in a source file's AST (`ast.Module.body`), never inside a
    function/class body, even one called unconditionally at import time
    (see `karr_translation.py`'s `_install_translation_v3_release_guard()`,
    whose nested `from . import karr_translation_v3` is therefore out of
    this audit's scope by design -- it is registered anyway, defensively,
    in `schema.PROCESS_DEPENDENCY_FILES["Translation"]`, so it costs
    nothing either way).
  * ONE level deep: resolves each import statement's own target to a
    file, never recurses into what THAT file itself imports.
  * Read/parse failures raise `ImportAuditError` -- never silently
    degrade to "no imports found" (the previous mechanical-derivation
    revision's `except (SyntaxError, OSError, UnicodeDecodeError): return
    set()` swallow is exactly the kind of silent blind spot F5 replaces).
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


def first_party_import_files(repo_root: Path, source_path: Path) -> set[Path]:
    """Every file `source_path` imports, at MODULE SCOPE only, that
    resolves to a real, on-disk, first-party (i.e. under `repo_root`)
    module/package file. Handles `import a.b.c`, aliased imports
    (`import a.b.c as x` / `from a.b.c import X as y`), `from a.b.c import
    X` (disambiguating "X is a submodule" -- e.g. `from opencell.m1 import
    karr_metabolism` -- from "X is a symbol" -- e.g. `from opencell.util
    import MatlabRandStream`, which falls back to the containing package
    `opencell/util/__init__.py` -- via on-disk resolution), and relative
    imports (`from . import X` / `from .foo import X`, resolved against
    `source_path`'s own containing package). Raises `ImportAuditError` on
    any read/parse failure -- NEVER silently returns an empty set for a
    broken file."""
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

    for node in tree.body:  # module-scope only -- never nested into function/class bodies
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
                base_parts = own_package_parts[: len(own_package_parts) - up] if up < len(own_package_parts) else []
                base = ".".join(base_parts)
                module = f"{base}.{node.module}" if node.module else base
            else:
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
