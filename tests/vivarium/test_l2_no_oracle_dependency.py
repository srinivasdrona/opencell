"""L2.1 oracle-leak contract test.

Forbids L2 process source files from depending on the L2.1 replay oracle.
This is the structural defense against the "output = oracle" cheat where a
process source file directly opens the trace .mat file and emits
`states_after - states_before` as its update, trivially passing L2.1 while
implementing zero biology.

Rules enforced:
  1. No `import h5py` (banned) in `opencell/vivarium/karr_*.py`.
  2. No string constant containing oracle path tokens or trace channel names.
  3. No attribute / function name suggesting trace replay machinery.

Allowlist exists for two legacy modules with documented borderline usage.
That allowlist is technical debt — each entry should be eliminated; the test
captures the debt explicitly rather than silently.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROCESS_DIR = _REPO_ROOT / "opencell" / "vivarium"

# Tokens that, if found in a process-source string literal, indicate the file
# references the L2 oracle. The trace layout is well-known and predictable so
# any reference is grounds for failure.
_BANNED_STRING_TOKENS: tuple[str, ...] = (
    "per_process_traces",          # covers both per_process_traces and _v2
    "_100ticks.mat",
    "states_before",
    "states_after",
)

# Modules forbidden in process source. h5py is the only practical way to read
# the v7.3 oracle .mat files, so banning it shuts down direct oracle reads.
# Sub-modules (e.g. h5py.File) are caught by name resolution at import time.
_BANNED_IMPORTS: frozenset[str] = frozenset({"h5py"})

# Pre-existing legacy oracle readers in process source. Each is technical debt:
# they read trace metadata at __init__ time (not per-tick), so they don't
# implement the "output = oracle" cheat the test primarily defends against,
# but they DO violate the clean SUT/oracle separation and should be migrated
# to non-oracle fixtures.
#
# To remove an entry: refactor the module to read its anchor data from a
# non-oracle fixture (e.g. data/karr_fixtures/per_process/...) or from
# process config, then drop the entry. Do NOT add new entries without a
# documented justification reviewed against this comment.
_ALLOWLIST: frozenset[str] = frozenset({
    # Reads metadata/n_ticks ONLY (a scalar). Used to size internal counters.
    # Should be migrated to a non-oracle source (config or fixture).
    "karr_cytokinesis.py",
    # Reads states_before/boundEnzymes[0] at __init__ time as a "trace anchor"
    # for default condensation level. This is borderline — the per-tick
    # update path does NOT consult the oracle, but the init-time read still
    # violates SUT/oracle separation. Currently L2.1 RED; refactor when fixing.
    "karr_chromosome_condensation.py",
    # Reads trace ONLY at __init__ to calibrate per-kind damage rates (one read,
    # no per-tick oracle access). L2.1 GREEN. Borderline: rates inferred from
    # oracle skew toward replay fidelity. Migrate to a non-oracle calibration
    # fixture.
    "karr_dna_damage.py",
    # Same pattern as karr_dna_damage.py: init-time _extract_trace_rates to
    # set bind/unbind rates. L2.1 GREEN. Borderline; migrate to non-oracle
    # calibration source.
    "karr_host_interaction.py",
})


def _is_process_source(path: Path) -> bool:
    """Return True for files we expect to be L2-process source."""
    name = path.name
    return (
        name.startswith("karr_")
        and name.endswith(".py")
        and not name.startswith("karr_request_calculators")  # helpers, not a process
        and not name.startswith("karr_composite")            # orchestration, not a process
    )


def _process_source_files() -> list[Path]:
    return sorted(p for p in _PROCESS_DIR.glob("karr_*.py") if _is_process_source(p))


def _allowed(path: Path) -> bool:
    return path.name in _ALLOWLIST


@pytest.mark.parametrize(
    "source_path",
    _process_source_files(),
    ids=lambda p: p.name,
)
def test_l2_process_source_does_not_depend_on_replay_oracle(source_path: Path) -> None:
    """A process source file must not read or reference the L2.1 oracle.

    Triggers on:
      - any `import h5py` or `from h5py import ...`
      - any string literal containing an oracle path token

    Allowlist (in this module) documents pre-existing legacy violations. The
    allowlist is asserted "still in violation" to keep the debt visible; if
    you fix a module, REMOVE it from the allowlist in the same change.
    """
    text = source_path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(source_path))

    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _BANNED_IMPORTS:
                    violations.append(f"import {alias.name} (line {node.lineno})")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in _BANNED_IMPORTS:
                violations.append(f"from {node.module} import ... (line {node.lineno})")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for token in _BANNED_STRING_TOKENS:
                if token in node.value:
                    violations.append(
                        f"string literal contains {token!r} (line {node.lineno}): "
                        f"{node.value[:80]!r}"
                    )

    if _allowed(source_path):
        # Legacy debt entry. Assert still in violation so the allowlist can't
        # silently rot. If a refactor cleared the violations, remove the file
        # from _ALLOWLIST in the same commit.
        if not violations:
            pytest.fail(
                f"{source_path.name} is on the legacy allowlist but no longer "
                f"violates the oracle-dependency rule. Remove it from _ALLOWLIST "
                f"in {__file__}."
            )
        return

    if violations:
        pytest.fail(
            f"{source_path.name} depends on the L2 replay oracle. This is the "
            f"'output = oracle' anti-pattern and makes L2.1 GREEN meaningless. "
            f"Violations:\n  - " + "\n  - ".join(violations)
            + "\n\nFix: remove the oracle dependency. Process source must compute "
            "deltas from biology, reading only `states` (which the L2.1 harness "
            "overlays with oracle data on its behalf). See "
            "tests/vivarium/l2_replay_common.py for the contract."
        )


def test_allowlist_files_exist() -> None:
    """Sanity check: every allowlisted file must exist (catches typos)."""
    missing = [name for name in _ALLOWLIST if not (_PROCESS_DIR / name).exists()]
    if missing:
        pytest.fail(
            "Allowlist references non-existent files (typo or renamed?): "
            + ", ".join(missing)
        )
