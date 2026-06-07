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

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

from l2_2_replay_common import _COMPOSITION_ORDER, run_integrated_replay


@pytest.mark.parametrize("rng_seed", [0], ids=["rng_seed_0"])
def test_l2_2_translation_plus_rna_processing(rng_seed: int) -> None:
    under_test = ["Translation", "RNAProcessing"]
    assert list(_COMPOSITION_ORDER[:2]) == under_test
    run_integrated_replay(under_test_processes=under_test, rng_seed=rng_seed)
