"""Multi-level simulation diff tool (Phase 4 / A5 v0.1).

Implements A6 §5 four equivalence classes (structural, invariant,
trajectory norm, phenotype). Hard prereq for M-phase work.
"""

from opencell.diff.multi_level import (
    DiffReport,
    DiffSpec,
    LevelFinding,
    build_default_invariant_suite,
    compute_default_phenotypes,
    diff_phenotypes,
    diff_structural,
    diff_trajectory,
    run_diff,
)

__all__ = [
    "DiffReport",
    "DiffSpec",
    "LevelFinding",
    "build_default_invariant_suite",
    "compute_default_phenotypes",
    "diff_phenotypes",
    "diff_structural",
    "diff_trajectory",
    "run_diff",
]
