"""Bounded RNA-only input/projection and anti-output-laundering regressions."""

from copy import deepcopy

import _l2_2_design_a_runner_helpers as adapters
import numpy as np
import pytest
from _rna_fidelity_helpers import fixture, intergenic_keys, processed_keys, wids
from _rna_replay_inputs import assert_exact_replay, source_before_state

from opencell.vivarium.karr_rna_modification import KarrRNAModificationProcess
from opencell.vivarium.karr_rna_processing import KarrRNAProcessingProcess


class BeforeOnly(dict):
    def __getitem__(self, key) -> object:
        assert not ("after" in key or "hint" in key), f"output-answer input access: {key}"
        return super().__getitem__(key)

    def get(self, key, default=None):
        assert not ("after" in key or "hint" in key), f"output-answer input access: {key}"
        return super().get(key, default)


def adapter_input(name, live):
    fx = fixture(name)
    process = (
        KarrRNAModificationProcess if name == "RNAModification" else KarrRNAProcessingProcess
    )({"rng_seed": 0})
    if name == "RNAModification":
        channels = ("unmodifiedRNAWholeCellModelIDs", "modifiedRNAWholeCellModelIDs")
    else:
        channels = (
            "unprocessedRNAWholeCellModelIDs",
            "processedRNAWholeCellModelIDs",
            "intergenicRNAWholeCellModelIDs",
        )
    sizes = [len(wids(fx, key)) for key in channels]
    state = BeforeOnly(
        {
            "substrate_wids": wids(fx, "substrateWholeCellModelIDs"),
            "enzyme_wids": wids(fx, "enzymeWholeCellModelIDs"),
            "oracle_before_substrates": np.arange(len(process.substrate_wids)) + 101.0,
            "oracle_before_enzymes": ((np.arange(len(process.enzyme_wids)) + 1.0) * int(live)),
            "oracle_before_bound_enzymes": np.arange(len(process.enzyme_wids)) + 17.0,
            "oracle_before_rnas": np.concatenate([np.arange(size) + 1.0 for size in sizes]),
            # These values are deliberately unusable. No output answers may be read.
            "oracle_after_rnas": object(),
            "oracle_after_substrates": object(),
            "trace_hint": object(),
        }
    )
    return process, state, sizes


@pytest.mark.parametrize("name", ["RNAModification", "RNAProcessing"])
@pytest.mark.parametrize("live", [False, True], ids=["live_zero", "live_positive"])
def test_design_a_actual_source_inputs_and_full_output_projection(name, live, monkeypatch):
    process, state, sizes = adapter_input(name, live)
    fx = fixture(name)
    enzyme_ids = wids(fx, "enzymeWholeCellModelIDs")
    for field, attribute in (
        ("enzymeMonomerLocalIndexs", "monomer_enzyme_wids"),
        ("enzymeComplexLocalIndexs", "complex_enzyme_wids"),
    ):
        indices = np.atleast_1d(fx[field]).astype(int) - 1
        assert list(getattr(process, attribute)) == [enzyme_ids[index] for index in indices]
    captured = []
    original = type(process).next_update

    def observe(owner, timestep, actual_state):
        rnas, enzymes = owner._input_vectors(actual_state)
        np.testing.assert_array_equal(rnas, state["oracle_before_rnas"][: sizes[0]])
        np.testing.assert_array_equal(enzymes, state["oracle_before_enzymes"])
        np.testing.assert_array_equal(
            [
                actual_state["substrates_allocated"][process.name][wid]
                for wid in state["substrate_wids"]
            ],
            state["oracle_before_substrates"],
        )
        assert "trace_hint" not in actual_state
        assert "enzymes" not in actual_state
        captured.append(actual_state)  # inspect the actual post-update state, not expected outputs
        return original(owner, timestep, actual_state)

    monkeypatch.setattr(type(process), "next_update", observe)
    stem = "rna_modification" if name == "RNAModification" else "rna_processing"
    result = getattr(adapters, f"_run_{stem}_tick")(0, 0, state)
    assert len(captured) == 1
    actual = captured[0]
    keys = processed_keys()
    if name == "RNAModification":
        assert len(keys) == sizes[0]
        assert process.processed_rna_wids == keys
        assert process.mature_rna_wids == wids(fx, "modifiedRNAWholeCellModelIDs")
        expected = np.concatenate(
            [
                [actual["rna"]["counts"][key] for key in keys],
                [actual["rna"]["modified_counts"][key] for key in process.mature_rna_wids],
            ]
        )
        no_reaction = np.asarray(fx["reactionModificationMatrix"]).sum(axis=0) == 0
        assert np.count_nonzero(no_reaction) > 0
        assert np.all(result["RNAs"][: sizes[0]][no_reaction] == 0)
    else:
        assert process.processed_rna_wids == keys
        assert process.intergenic_rna_keys == intergenic_keys()
        expected = np.array(
            [
                actual["rna"]["counts"][key]
                for key in process.unprocessed_rna_wids + keys + intergenic_keys()
            ]
        )
    np.testing.assert_array_equal(result["RNAs"], expected)
    assert result["RNAs"].shape == (sum(sizes),)
    assert np.any(result["RNAs"] != state["oracle_before_rnas"]), "nontrivial mutation required"
    np.testing.assert_array_equal(
        result["substrates"], [actual["substrates"][wid] for wid in process.substrate_wids]
    )


def test_design_a_rp_intergenic_global_rows_are_actual_outputs_not_cached_before():
    process, state, sizes = adapter_input("RNAProcessing", True)
    fx = fixture("RNAProcessing")
    target = int(np.atleast_1d(fx["unprocessedRNAIndexs_rRNA"])[0]) - 1
    composition = np.asarray(fixture("Rna")["nascentRNAMatureRNAComposition"], dtype=float)
    fragments = np.asarray(fixture("Rna")["intergenicRNAMatrix"], dtype=float)
    stoich = np.asarray(fx["reactantByproductMatrix"], dtype=float)
    catalysis = np.asarray(fx["catalysisMatrix"], dtype=float)
    state["oracle_before_rnas"] = np.zeros(sum(sizes))
    state["oracle_before_rnas"][target] = 1
    state["oracle_before_rnas"][-sizes[-1] :] = np.arange(sizes[-1]) + 1
    state["oracle_before_enzymes"] = np.ceil(catalysis[:, target]) + 1
    state["oracle_before_substrates"] = np.maximum(0, -stoich[:, target])
    result = adapters._run_rna_processing_tick(0, 0, state)
    expected_fragments = state["oracle_before_rnas"][-sizes[-1] :] + fragments[:, target]
    assert np.count_nonzero(fragments[:, target]) > 1
    np.testing.assert_array_equal(result["RNAs"][-sizes[-1] :], expected_fragments)
    np.testing.assert_array_equal(result["RNAs"][sizes[0] : -sizes[-1]], composition[:, target])
    np.testing.assert_array_equal(
        result["substrates"], state["oracle_before_substrates"] + stoich[:, target]
    )


def _rng_state(owner):
    rng = owner._rng
    if isinstance(rng, np.random.Generator):
        return deepcopy(rng.bit_generator.state)
    return deepcopy(rng.get_state())


@pytest.mark.parametrize("name", ["RNAModification", "RNAProcessing"])
@pytest.mark.parametrize("history", ["repeat", "interleave", "advanced_metadata_owner"])
def test_design_a_rna_sample_is_independent_of_cached_execution_history(
    name, history, monkeypatch
):
    """Design-A seeds belong to samples; cached metadata must not own execution."""
    process, state, _ = adapter_input(name, True)
    process_class = type(process)
    stem = "rna_modification" if name == "RNAModification" else "rna_processing"
    run = getattr(adapters, f"_run_{stem}_tick")
    factory = getattr(adapters, f"_{stem}_process")
    key = (0, 0)
    sample_seed = adapters._sample_seed(*key)
    expected_state = _rng_state(process_class({"rng_seed": sample_seed}))
    poisoned_owner = None
    if history == "advanced_metadata_owner":
        poisoned_owner = factory(sample_seed)
        poisoned_owner._rng.random(13)

    seen = []
    original = process_class.next_update

    def observe(owner, timestep, actual_state):
        seen.append((owner, _rng_state(owner)))
        return original(owner, timestep, actual_state)

    monkeypatch.setattr(process_class, "next_update", observe)
    keys = [key, (1, 1), key] if history == "interleave" else [key, key]
    outputs = [run(seed, tick, state) for seed, tick in keys]
    assert len(seen) == len(keys), "observe the actual public evolution owner"
    first, last = outputs[0], outputs[-1]
    assert np.any(first["RNAs"] != state["oracle_before_rnas"]), "nonzero source transition"
    for channel in ("substrates", "RNAs"):
        np.testing.assert_array_equal(first[channel], last[channel])
        assert np.array_equal(first[channel], np.rint(first[channel]))
    assert first["sample_seed"] == last["sample_seed"] == sample_seed
    np.testing.assert_equal(seen[0][1], expected_state)
    np.testing.assert_equal(seen[-1][1], expected_state)
    assert seen[0][0] is not seen[-1][0], "each sample must have a fresh execution owner"
    if poisoned_owner is not None:
        assert all(owner is not poisoned_owner for owner, _ in seen)


def test_full_rm_replay_cannot_silently_reduce_to_active_38_api():
    process, state, sizes = adapter_input("RNAModification", False)
    assert sizes[0] > len(process.unmodified_rna_wids)
    before = {
        "substrates": state["oracle_before_substrates"],
        "enzymes": state["oracle_before_enzymes"],
        "boundEnzymes": state["oracle_before_bound_enzymes"],
        "unmodifiedRNAs": np.zeros(len(process.unmodified_rna_wids)),
        "modifiedRNAs": np.zeros(len(process.modified_rna_wids)),
    }
    with pytest.raises(AssertionError, match="input length drift"):
        source_before_state(process, before)


@pytest.mark.parametrize("actual,expected", [(2, 1), (1.1, 1), (1.1, 1.1)])
def test_rna_identity_is_integer_exact_even_if_shared_tolerances_enabled(
    actual, expected, monkeypatch
):
    monkeypatch.setenv("L2_USE_CALIBRATED_TOLERANCES", "1")
    with pytest.raises(AssertionError):
        assert_exact_replay(0, "RNAs", np.array([actual]), np.array([expected]))


@pytest.mark.parametrize("name", ["RNAProcessing", "RNAModification"])
def test_rna_loader_rejects_missing_source_family_without_legacy_backfill(name):
    required_before, required_after = adapters._required_ensemble_keys(name)
    before = {key: np.zeros((1, 100, 1)) for key in required_before}
    after = {key: np.zeros((1, 100, 1)) for key in required_after}
    del before[required_before[-1]]
    with pytest.raises(ValueError, match="missing RNA source families"):
        adapters._format_ensemble_oracle(
            process_name=name,
            oracle_path=adapters._REPO_ROOT,
            seed_paths=[adapters._REPO_ROOT],
            before_channels=before,
            after_channels=after,
        )
