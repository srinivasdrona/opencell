"""M1 — metabolism module (Karr-native).

The module loads Karr 2012's fitted FBA snapshot directly via
:func:`opencell.m1.karr_metabolism.load_default`.  All numeric inputs
come from `data/karr_fixtures/karr_native_m1.{json,npz}`, extracted from
Karr's `sim_fitted_targeted.mat` by `scripts/karr_native_ingest_m1.py`.
No values are hard-coded in this module.

The previous iPS189 (Suthers 2009) baseline was retired on 2026-04-25
once Karr's MAT extraction shipped; see Session N+8 in
``SESSION_CONTEXT.md`` for the rationale.
"""
from .karr_metabolism import (
    KarrMetabolismModel,
    load_default,
    solve_fba,
    per_reaction_comparison,
    DEFAULT_FIXTURE_JSON,
    DEFAULT_BIG,
)

__all__ = [
    "KarrMetabolismModel",
    "load_default",
    "solve_fba",
    "per_reaction_comparison",
    "DEFAULT_FIXTURE_JSON",
    "DEFAULT_BIG",
]
