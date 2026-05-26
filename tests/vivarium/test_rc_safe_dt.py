from __future__ import annotations

import sys
from pathlib import Path

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

from opencell.vivarium.karr_request_calculators import (
    RequestCalculatorTranscription,
    RequestCalculatorTranslation,
)
from opencell.vivarium.karr_transcription_v3 import KarrTranscriptionV3Process
from opencell.vivarium.karr_translation_v3 import KarrTranslationV3Process


def test_request_calculator_translation_safe_dt_with_zero_step_timestep() -> None:
    tl_proc = KarrTranslationV3Process({"use_allocator_budget": True, "time_step": 1.0})
    calc = RequestCalculatorTranslation({"translation_proc": tl_proc})

    state = {
        "complex": {
            "counts": {
                "RIBOSOME_70S": max(1.0, float(tl_proc._fallback_n_active_ribosomes))
            }
        }
    }
    update = calc.next_update(0.0, state)
    requests = update["requests"][tl_proc.name]
    assert any(float(value) > 0.0 for value in requests.values())


def test_request_calculator_transcription_safe_dt_with_zero_step_timestep() -> None:
    tx_proc = KarrTranscriptionV3Process({"use_allocator_budget": True, "time_step": 1.0})
    calc = RequestCalculatorTranscription({"transcription_proc": tx_proc})

    state = {
        "complex": {
            "counts": {
                "RNA_POLYMERASE": max(1.0, float(tx_proc._fallback_n_active_rnap))
            }
        }
    }
    update = calc.next_update(0.0, state)
    requests = update["requests"][tx_proc.name]
    assert any(float(value) > 0.0 for value in requests.values())
