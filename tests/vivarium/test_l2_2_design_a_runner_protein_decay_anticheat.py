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


def test_protein_decay_tick_does_not_feed_after_hint_back_into_primary_channels() -> None:
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

    assert not np.array_equal(result["substrates"], state["oracle_after_substrates"])
    assert not np.array_equal(result["monomers"], state["oracle_after_monomers"])
    assert not np.array_equal(result["complexs"], state["oracle_after_complexs"])


def test_protein_decay_laundering_flows_through_trace_hint_replay_not_store_alias() -> None:
    if hasattr(runner_helpers._protein_decay_process, "cache_clear"):
        runner_helpers._protein_decay_process.cache_clear()

    process = runner_helpers._protein_decay_process(34567)
    runtime_state = runner_helpers.build_state_template(process)
    substrate_wids = list(process.substrate_wids)
    enzyme_wids = list(process.enzyme_wids)
    monomer_wids = list(process.protein_wids)
    complex_wids = list(process.complex_wids)
    bound_enzymes_before = np.zeros(len(enzyme_wids), dtype=np.float64)

    runner_helpers.overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="substrates",
        vector=np.zeros(len(substrate_wids), dtype=np.float64),
        wids=substrate_wids,
    )
    runner_helpers.overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="enzymes",
        vector=np.zeros(len(enzyme_wids), dtype=np.float64),
        wids=enzyme_wids,
    )
    runner_helpers.overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="monomers",
        vector=np.zeros(len(monomer_wids), dtype=np.float64),
        wids=monomer_wids,
    )
    runner_helpers.overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="complexs",
        vector=np.zeros(len(complex_wids), dtype=np.float64),
        wids=complex_wids,
    )
    runner_helpers.overlay_trace_after_hint(
        state=runtime_state,
        observable="substrates",
        vector=np.full(len(substrate_wids), 17.0, dtype=np.float64),
        wids=substrate_wids,
    )
    runner_helpers.overlay_trace_after_hint(
        state=runtime_state,
        observable="monomers",
        vector=np.full(len(monomer_wids), 100.0, dtype=np.float64),
        wids=monomer_wids,
    )
    runner_helpers.overlay_trace_after_hint(
        state=runtime_state,
        observable="complexs",
        vector=np.full(len(complex_wids), 23.0, dtype=np.float64),
        wids=complex_wids,
    )

    projected_before = runner_helpers.project_observable_from_state(
        process=process,
        state=runtime_state,
        observable="monomers",
        wids=monomer_wids,
        bound_enzymes_before=bound_enzymes_before,
    )
    assert np.array_equal(projected_before, np.zeros(len(monomer_wids), dtype=np.float64))

    update = process.next_update(1.0, runtime_state)

    assert "substrates" in update
    assert "protein" in update
    assert "complex" in update

    runner_helpers.apply_count_update(runtime_state, update)

    projected_after = runner_helpers.project_observable_from_state(
        process=process,
        state=runtime_state,
        observable="monomers",
        wids=monomer_wids,
        bound_enzymes_before=bound_enzymes_before,
    )
    assert np.array_equal(projected_after, np.full(len(monomer_wids), 100.0, dtype=np.float64))


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
