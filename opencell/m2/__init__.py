"""M2 - Karr-native transcription (Karr-prescribed rates + mechanism oracle).

See `opencell.m2.transcription` for the v1/v2 staging note.
"""
from .transcription import (
    KarrTranscriptionModel,
    load_default,
    step_analytical,
    ntp_consumption_per_s,
    DEFAULT_FIXTURE_JSON,
)
from . import transcription_v2
from .transcription_v2 import (
    MechanismInputs,
    load_default as load_default_v2,
    predict_tu_synthesis_per_s,
    predict_gene_synthesis_per_s,
    total_nt_polymerization_per_s,
    compare_to_karr,
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
