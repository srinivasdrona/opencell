from __future__ import annotations

import sys
from pathlib import Path

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
    CHASSIS_V6_RUNTIME_IDENTITY_EXPECTED_CLASS_QUALNAMES,
    CHASSIS_V6_RUNTIME_IDENTITY_EXPECTED_CLASSES,
    assert_chassis_runtime_identity,
    build_karr_chassis_v6,
)


def test_v6_runtime_identity_matches_v3_bindings() -> None:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    assert_chassis_runtime_identity(composite)

    processes = composite["processes"]
    for key, expected_cls in CHASSIS_V6_RUNTIME_IDENTITY_EXPECTED_CLASSES.items():
        observed_cls = processes[key].__class__
        assert observed_cls is expected_cls
        assert observed_cls.__qualname__ == CHASSIS_V6_RUNTIME_IDENTITY_EXPECTED_CLASS_QUALNAMES[key]
    assert "karr_transcription_v3" not in processes
    assert "karr_translation_v3" not in processes
    assert "karr_transcription" not in composite["steps"]
    assert "karr_translation" not in composite["steps"]


def test_runtime_identity_guardrail_raises_on_class_drift() -> None:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    drifted = {"processes": dict(composite["processes"])}
    fake_translation_cls = type("KarrTranslationV3Process", (), {})
    drifted["processes"]["karr_translation"] = fake_translation_cls()

    with pytest.raises(AssertionError, match="karr_translation: expected class "):
        assert_chassis_runtime_identity(drifted)
