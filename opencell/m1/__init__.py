"""M1 — central carbon + adenylate energy module.

All numeric inputs are loaded from `data/karr_fixtures/iPS189_m1.json`
which is produced by `scripts/karr_a4f_ingest_m1.py` directly from
upstream sources (Suthers 2009 SBML, Karr WholeCellKB, Karr
parameters.json). No values are hard-coded in this module.
"""
from .central_carbon import (
    CentralCarbonModel,
    pfba,
    load_default,
    DEFAULT_FIXTURE_PATH,
)

__all__ = [
    "CentralCarbonModel",
    "pfba",
    "load_default",
    "DEFAULT_FIXTURE_PATH",
]
