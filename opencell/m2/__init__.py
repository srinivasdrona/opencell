"""M2 - Karr-native transcription (Karr-prescribed rates + mechanism oracle).

See `opencell.m2.transcription` for the v1/v2 staging note.
"""

from . import transcription_v2
from .transcription import (
    DEFAULT_FIXTURE_JSON,
    KarrTranscriptionModel,
    load_default,
    ntp_consumption_per_s,
    step_analytical,
)
from .transcription_v2 import (
    MechanismInputs,
    compare_to_karr,
    predict_gene_synthesis_per_s,
    predict_tu_synthesis_per_s,
    total_nt_polymerization_per_s,
)
from .transcription_v2 import (
    load_default as load_default_v2,
)

__all__ = [
    "KarrTranscriptionModel",
    "load_default",
    "step_analytical",
    "ntp_consumption_per_s",
    "DEFAULT_FIXTURE_JSON",
    "transcription_v2",
    "MechanismInputs",
    "load_default_v2",
    "predict_tu_synthesis_per_s",
    "predict_gene_synthesis_per_s",
    "total_nt_polymerization_per_s",
    "compare_to_karr",
]
