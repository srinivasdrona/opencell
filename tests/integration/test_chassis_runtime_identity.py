from __future__ import annotations

from pathlib import Path
import sys

import pytest

# Ensure pytest imports from this worktree even if another editable install exists.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

from opencell.vivarium.karr_composite import (
    assert_chassis_runtime_identity,
    build_karr_chassis_v6,
)
from opencell.vivarium.karr_transcription_v3 import KarrTranscriptionV3Process
from opencell.vivarium.karr_translation_v3 import KarrTranslationV3Process


def test_v6_runtime_identity_matches_v3_bindings() -> None:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    assert_chassis_runtime_identity(composite)

    processes = composite["processes"]
    assert isinstance(processes["karr_transcription"], KarrTranscriptionV3Process)
    assert isinstance(processes["karr_translation"], KarrTranslationV3Process)
    assert "karr_transcription_v3" not in processes
    assert "karr_translation_v3" not in processes
    assert "karr_transcription" not in composite["steps"]
    assert "karr_translation" not in composite["steps"]


def test_runtime_identity_guardrail_raises_on_class_drift() -> None:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    drifted = {"processes": dict(composite["processes"])}
    drifted["processes"]["karr_translation"] = object()

    with pytest.raises(AssertionError, match="karr_translation"):
        assert_chassis_runtime_identity(drifted)
