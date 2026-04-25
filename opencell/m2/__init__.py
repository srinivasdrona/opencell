"""M2 - Karr-native transcription (Karr-prescribed rates).

See `opencell.m2.transcription` for the v1/v2 staging note.
"""
from .transcription import (
    KarrTranscriptionModel,
    load_default,
    step_analytical,
    ntp_consumption_per_s,
    DEFAULT_FIXTURE_JSON,
)

__all__ = [
    "KarrTranscriptionModel",
    "load_default",
    "step_analytical",
    "ntp_consumption_per_s",
    "DEFAULT_FIXTURE_JSON",
]
