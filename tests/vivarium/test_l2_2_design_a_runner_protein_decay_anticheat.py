from __future__ import annotations

import sys
from pathlib import Path

import numpy as np


_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

from tests.vivarium import _l2_2_design_a_runner_helpers as runner_helpers


def test_protein_decay_monomer_oracle_is_projected_not_raw_head_slice() -> None:
    oracle = runner_helpers.load_karr_oracle("ProteinDecay")

    with np.load(runner_helpers._PROTEIN_DECAY_ORACLE_PATH, allow_pickle=False) as payload:
        raw_before = np.asarray(payload["state_before__monomers"], dtype=np.float64)

    projected = np.asarray(oracle["before_monomers"][0, 0], dtype=np.float64)
    recalculated = runner_helpers._project_protein_decay_monomer_cube(raw_before[:1])[0]
    naive_head_slice = raw_before[0].reshape(-1)[: projected.shape[0]]

    assert projected.shape == (482,)
    assert np.array_equal(projected, recalculated)
    assert not np.array_equal(projected, naive_head_slice)
