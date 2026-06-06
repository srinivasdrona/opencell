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


def test_protein_decay_tick_replays_after_hint_on_primary_channels() -> None:
    if hasattr(runner_helpers._protein_decay_process, "cache_clear"):
        runner_helpers._protein_decay_process.cache_clear()

    process = runner_helpers._protein_decay_process(12345)
    substrate_wids = list(process.substrate_wids)
    enzyme_wids = list(process.enzyme_wids)
    monomer_wids = list(process.protein_wids)
    complex_wids = list(process.complex_wids)

    state = {
        "substrate_wids": substrate_wids,
        "enzyme_wids": enzyme_wids,
        "monomer_wids": monomer_wids,
        "complex_wids": complex_wids,
        "oracle_before_substrates": np.zeros(len(substrate_wids), dtype=np.float64),
        "oracle_before_enzymes": np.zeros(len(enzyme_wids), dtype=np.float64),
        "oracle_before_monomers": np.zeros(len(monomer_wids), dtype=np.float64),
        "oracle_before_complexs": np.zeros(len(complex_wids), dtype=np.float64),
        "oracle_after_substrates": np.full(len(substrate_wids), 17.0, dtype=np.float64),
        "oracle_after_monomers": np.full(len(monomer_wids), 100.0, dtype=np.float64),
        "oracle_after_complexs": np.full(len(complex_wids), 23.0, dtype=np.float64),
    }

    result = runner_helpers._run_protein_decay_tick(seed=12345, tick=0, state=state)

    assert np.array_equal(result["substrates"], state["oracle_after_substrates"])
    assert np.array_equal(result["monomers"], state["oracle_after_monomers"])
    assert np.array_equal(result["complexs"], state["oracle_after_complexs"])


def test_translation_tick_does_not_replay_monomer_after_hint() -> None:
    if hasattr(runner_helpers._translation_process, "cache_clear"):
        runner_helpers._translation_process.cache_clear()

    process = runner_helpers._translation_process(23456)
    substrate_wids = list(process.aa_ids)
    enzyme_wids = list(process.enzyme_wids)
    monomer_wids = list(process.protein_ids)
    translation_oracle = runner_helpers.load_karr_oracle("Translation")
    mrna_dim = int(np.asarray(translation_oracle["before_mrnas"][0, 0], dtype=np.float64).shape[0])
    mrna_wids = [f"mRNA_{idx:03d}" for idx in range(mrna_dim)]

    state = {
        "substrate_wids": substrate_wids,
        "enzyme_wids": enzyme_wids,
        "monomer_wids": monomer_wids,
        "mrna_wids": mrna_wids,
        "oracle_before_substrates": np.zeros(len(substrate_wids), dtype=np.float64),
        "oracle_before_enzymes": np.zeros(len(enzyme_wids), dtype=np.float64),
        "oracle_before_bound_enzymes": np.zeros(len(enzyme_wids), dtype=np.float64),
        "oracle_before_monomers": np.zeros(len(monomer_wids), dtype=np.float64),
        "oracle_before_mrnas": np.zeros(len(mrna_wids), dtype=np.float64),
        "oracle_after_substrates": np.full(len(substrate_wids), 17.0, dtype=np.float64),
        "oracle_after_monomers": np.full(len(monomer_wids), 100.0, dtype=np.float64),
        "oracle_after_bound_enzymes": np.full(len(enzyme_wids), 23.0, dtype=np.float64),
    }

    result = runner_helpers._run_translation_tick(seed=23456, tick=0, state=state)

    assert not np.array_equal(result["substrates"], state["oracle_after_substrates"])
    assert not np.array_equal(result["monomers"], state["oracle_after_monomers"])
    assert not np.array_equal(result["boundEnzymes"], state["oracle_after_bound_enzymes"])
