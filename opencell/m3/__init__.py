"""M3 - Karr-native translation (Karr-prescribed rates + ribosome oracle).

See `opencell.m3.translation` for the v1/v2 staging note.
"""

from . import translation_v2
from .translation import (
    DEFAULT_FIXTURE_JSON,
    KarrTranslationModel,
    aa_consumption_per_s,
    load_default,
    step_analytical,
)
from .translation_v2 import (
    RibosomeMechanismInputs,
    fraction_active_from_occupancies,
    predict_synthesis_per_s,
    total_aa_polymerization_per_s,
)
from .translation_v2 import (
    load_default as load_default_v2,
)

__all__ = [
    "KarrTranslationModel",
    "load_default",
    "step_analytical",
    "aa_consumption_per_s",
    "DEFAULT_FIXTURE_JSON",
    "translation_v2",
    "RibosomeMechanismInputs",
    "load_default_v2",
    "predict_synthesis_per_s",
    "total_aa_polymerization_per_s",
    "fraction_active_from_occupancies",
]

__all__ = [
    "KarrTranslationModel",
    "load_default",
    "step_analytical",
    "aa_consumption_per_s",
    "DEFAULT_FIXTURE_JSON",
]
