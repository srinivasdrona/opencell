"""M3 - Karr-native translation (Karr-prescribed rates).

See `opencell.m3.translation` for the v1/v2 staging note.
"""
from .translation import (
    KarrTranslationModel,
    load_default,
    step_analytical,
    aa_consumption_per_s,
    DEFAULT_FIXTURE_JSON,
)

__all__ = [
    "KarrTranslationModel",
    "load_default",
    "step_analytical",
    "aa_consumption_per_s",
    "DEFAULT_FIXTURE_JSON",
]
