"""Enforce the Day-3 (2026-04-24) decision: JAX/Diffrax is removed from the
OpenCell simulation runtime.

Rationale: at whole-cell scale JAX dispatch overhead exceeds the integration
work (profiled and confirmed on Day 2). JAX was removed on Day 3, then silently
drifted back in via ``opencell/solvers/stochastic.py`` (``import jax.numpy``),
which ``opencell/vivarium/__init__.py`` eagerly imports through
``processes.py`` -- so every Karr process import force-loaded ~208 JAX modules
for zero benefit (the Karr processes are pure numpy). This guard prevents that
recurrence.

Two layers:
  1. Runtime: import the full Karr vivarium surface in a *clean* subprocess and
     assert no ``jax``/``jaxlib`` module ended up in ``sys.modules``. This
     catches transitive leaks that a static scan of one directory would miss --
     which is exactly how the original drift happened.
  2. Static: scan the runtime source surface for direct ``import jax`` /
     ``import diffrax`` statements, so a reviewer gets a precise file:line.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

# The runtime surface that must stay JAX-free: the Karr vivarium processes,
# the state/chromosome layer they use, and the stochastic solver they call.
_RUNTIME_DIRS = (
    _REPO_ROOT / "opencell" / "vivarium",
    _REPO_ROOT / "opencell" / "state",
)
_RUNTIME_FILES = (
    _REPO_ROOT / "opencell" / "solvers" / "stochastic.py",
)

_JAX_IMPORT_RE = re.compile(
    r"^\s*(?:import\s+(?:jax|jaxlib|diffrax)\b|from\s+(?:jax|jaxlib|diffrax)\b)",
    re.MULTILINE,
)


def test_karr_runtime_import_loads_no_jax() -> None:
    """Importing the full Karr vivarium surface must not load JAX."""
    code = (
        "import sys\n"
        "import opencell.vivarium  # eager: composite, metabolism, processes\n"
        "import opencell.vivarium.karr_dna_repair\n"
        "import opencell.vivarium.karr_transcription\n"
        "leaked = sorted(m for m in sys.modules if m == 'jax' "
        "or m.startswith('jax.') or m == 'jaxlib' or m.startswith('jaxlib.') "
        "or m == 'diffrax' or m.startswith('diffrax.'))\n"
        "assert not leaked, "
        "'JAX leaked into the Karr runtime (Day-3 decision violated): ' "
        "+ ', '.join(leaked[:8])\n"
        "print('OK: Karr runtime is JAX-free')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        "Karr runtime import pulled in JAX (or failed to import).\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_runtime_source_has_no_direct_jax_imports() -> None:
    """Static guard: no `import jax|jaxlib|diffrax` in the runtime surface."""
    offenders: list[str] = []
    py_files: list[Path] = list(_RUNTIME_FILES)
    for d in _RUNTIME_DIRS:
        py_files.extend(sorted(d.rglob("*.py")))
    for path in py_files:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for m in _JAX_IMPORT_RE.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            rel = path.relative_to(_REPO_ROOT)
            offenders.append(f"{rel}:{line_no}: {m.group(0).strip()}")
    assert not offenders, (
        "JAX/Diffrax imports found in the JAX-free runtime surface "
        "(Day-3 decision):\n" + "\n".join(offenders)
    )
