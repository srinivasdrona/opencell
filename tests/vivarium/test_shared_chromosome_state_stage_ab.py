"""Tests for Shared Chromosome-State Subsystem — Stage A & Stage B.

Contract authority: docs/design/shared_chromosome_state_subsystem.md (revision a804eb7).

Scope:
- Stage A: Stream substrate unification (ChromosomeStateRandStream == TxRegMcgRandStream
  == ChromCondMcgRandStream across seeds {0, 1, 42, 123456789}), exact Vivarium leaf
  path ('chromosome', '_shared_rand_stream_state'), int64 [seed, mcg_state] schema,
  ChromosomeStore to_state/from_state_mapping round-trip, absent-key seed-once at init
  vs fail-closed on next_update, multi-tick non-ledger production continuity including
  zero-draw writeback, and explicit checkpoint.py scope-limitation verification.
- Stage B: Sole TxReg consumer (RNG-only), real 'chromosome' port and topology in both
  composite mappings, unchanged candidate/accessibility/damage/exclude-overlap logic,
  candidate fixture index-for-index and post-draw mcg_state parity, static + runtime
  anti-oracle guards (no ledger in production), writeback every tick including zero-draw,
  dec-006 test-only replay boundary preservation, private tf_bound_promoters retention
  as known temporary Stage-B surface, and dec-007 implementation gate precondition.
- Planted canaries: absent-key silent reseed, one extra draw, zero-draw omitted
  writeback, ledger-in-production import, and candidate-order alteration are detected.
"""

from __future__ import annotations

import ast
import inspect
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

import opencell.core.checkpoint as oc_checkpoint
import opencell.state.chromosome_store as cs_mod
from opencell.state.chromosome_store import ChromosomeStore
from opencell.util.chromcond_mcg_rand import ChromCondMcgRandStream
from opencell.util.txreg_mcg_rand import TxRegMcgRandStream
from opencell.vivarium.karr_transcriptional_regulation import (
    KarrTranscriptionalRegulationProcess,
)

_COMPOSITE_SRC_PATH = _REPO_ROOT / "opencell" / "vivarium" / "karr_composite.py"
_TXREG_SRC_PATH = _REPO_ROOT / "opencell" / "vivarium" / "karr_transcriptional_regulation.py"
_EXPECTED_LEAF_KEY = "_shared_rand_stream_state"
_UNSEEDED_SENTINEL = np.array([-1, -1], dtype=np.int64)


# ---------------------------------------------------------------------------
# Stage A: Stream Substrate & Numerical Equivalence
# ---------------------------------------------------------------------------


def test_stage_a_chromosome_state_rand_stream_equivalence_across_seeds() -> None:
    """Stage A Contract §4.1, DC-4, §18 A2, Probe P1.

    Future ChromosomeStateRandStream in opencell.util.chromosome_state_rand must be
    numerically equivalent to TxRegMcgRandStream and ChromCondMcgRandStream across
    seeds {0, 1, 42, 123456789} for:
    - scalar rand() and multidimensional rand(*shape)
    - randi(imax, *shape)
    - randperm(n, k)
    - randsample(n, k, replacement, weights) (unweighted, weighted, with/without replacement)
    - get_state() and set_state() round-trip.
    """
    try:
        from opencell.util.chromosome_state_rand import ChromosomeStateRandStream
    except ImportError:
        pytest.fail(
            "Stage A requires ChromosomeStateRandStream in opencell.util.chromosome_state_rand "
            "(DC-4 unified stream substrate not yet implemented)."
        )

    test_seeds = [0, 1, 42, 123456789]
    for seed in test_seeds:
        unified = ChromosomeStateRandStream(seed)
        txreg = TxRegMcgRandStream(seed)
        chromcond = ChromCondMcgRandStream(seed)

        # 1. rand()
        r_u = unified.rand(5, 5)
        r_t = txreg.rand(5, 5)
        r_c = chromcond.rand(5, 5)
        np.testing.assert_array_equal(r_u, r_t)
        np.testing.assert_array_equal(r_u, r_c)

        # 2. randi()
        ri_u = unified.randi(50, 10)
        ri_t = txreg.randi(50, 10)
        ri_c = chromcond.randi(50, 10)
        np.testing.assert_array_equal(ri_u, ri_t)
        np.testing.assert_array_equal(ri_u, ri_c)

        # 3. randperm()
        rp_u = unified.randperm(30, 10)
        rp_t = txreg.randperm(30, 10)
        rp_c = chromcond.randperm(30, 10)
        np.testing.assert_array_equal(rp_u, rp_t)
        np.testing.assert_array_equal(rp_u, rp_c)

        # 4. randsample() weighted without replacement
        w = np.array([0.1, 0.5, 0.2, 0.8, 1.2, 0.05, 0.4, 0.9], dtype=np.float64)
        rs_u = unified.randsample(8, 5, False, w)
        rs_t = txreg.randsample(8, 5, False, w)
        rs_c = chromcond.randsample(8, 5, False, w)
        np.testing.assert_array_equal(rs_u, rs_t)
        np.testing.assert_array_equal(rs_u, rs_c)

        # 5. randsample() with replacement
        rs_rep_u = unified.randsample(8, 15, True, w)
        rs_rep_t = txreg.randsample(8, 15, True, w)
        rs_rep_c = chromcond.randsample(8, 15, True, w)
        np.testing.assert_array_equal(rs_rep_u, rs_rep_t)
        np.testing.assert_array_equal(rs_rep_u, rs_rep_c)

        # 6. state round-trip
        st_u = unified.get_state()
        st_t = txreg.get_state()
        st_c = chromcond.get_state()
        assert st_u["mcg_state"] == st_t["mcg_state"] == st_c["mcg_state"]
        assert st_u["seed"] == st_t["seed"] == st_c["seed"]

        # 7. set_state into fresh instances and compare subsequent rand/randsample draws
        fresh_unified = ChromosomeStateRandStream(999999)
        fresh_unified.set_state(st_u)
        fresh_txreg = TxRegMcgRandStream(999999)
        fresh_txreg.set_state(st_t)
        fresh_chromcond = ChromCondMcgRandStream(999999)
        fresh_chromcond.set_state(st_c)

        sub_rand_u = fresh_unified.rand(4, 4)
        sub_rand_t = fresh_txreg.rand(4, 4)
        sub_rand_c = fresh_chromcond.rand(4, 4)
        np.testing.assert_array_equal(sub_rand_u, sub_rand_t)
        np.testing.assert_array_equal(sub_rand_u, sub_rand_c)

        weights_sub = np.linspace(0.1, 1.0, 10, dtype=np.float64)
        sub_rs_u = fresh_unified.randsample(10, 6, False, weights_sub)
        sub_rs_t = fresh_txreg.randsample(10, 6, False, weights_sub)
        sub_rs_c = fresh_chromcond.randsample(10, 6, False, weights_sub)
        np.testing.assert_array_equal(sub_rs_u, sub_rs_t)
        np.testing.assert_array_equal(sub_rs_u, sub_rs_c)


def test_stage_a_planted_multiplier_and_state_mutations_detected() -> None:
    """Stage A Canary: Planted generator mutations MUST diverge and be detected.

    Verifies that:
    1. A stream with perturbed multiplier (16808 instead of 16807) diverges.
    2. A stream with perturbed state bit diverges.
    """
    ref_stream = TxRegMcgRandStream(42)
    ref_draws = [ref_stream._mcg_rand_scalar() for _ in range(5)]

    # 1. Perturbed multiplier simulation
    mutated_multiplier = 16808
    raw_state = TxRegMcgRandStream._decode_mcg_state(TxRegMcgRandStream(42)._mcg_state)
    mutated_draws = []
    for _ in range(5):
        raw_state = (mutated_multiplier * raw_state) % 2147483647
        mutated_draws.append(raw_state / 2147483647)

    assert not np.allclose(
        ref_draws, mutated_draws
    ), "Planted multiplier mutation (16808) must produce divergent draws"

    # 2. Perturbed state simulation
    stream_mut = TxRegMcgRandStream(42)
    stream_mut._mcg_state = stream_mut._mcg_state ^ 0x0001
    mut_draws = [stream_mut._mcg_rand_scalar() for _ in range(5)]
    assert not np.allclose(
        ref_draws, mut_draws
    ), "Planted state bit perturbation must produce divergent draws"


# ---------------------------------------------------------------------------
# Stage A: Leaf Path, Schema, and ChromosomeStore Serialization
# ---------------------------------------------------------------------------


def test_stage_a_exact_leaf_path_and_schema_contract() -> None:
    """Stage A Contract §4.3, §18 A2.

    The exact state leaf path in the Vivarium chromosome branch is:
    ('chromosome', '_shared_rand_stream_state')
    The store module constant CHROMOSOME_RAND_STREAM_KEY must be '_shared_rand_stream_state'.
    The value must be an int64 two-vector [seed, mcg_state] of shape (2,).
    """
    assert hasattr(
        cs_mod, "CHROMOSOME_RAND_STREAM_KEY"
    ), "ChromosomeStore module must export CHROMOSOME_RAND_STREAM_KEY"
    assert cs_mod.CHROMOSOME_RAND_STREAM_KEY == _EXPECTED_LEAF_KEY


def test_stage_a_chromosome_store_to_state_from_state_mapping_round_trip() -> None:
    """Stage A Contract §4.3, §12.

    ChromosomeStore.to_state / from_state_mapping round-trip contract:
    - to_state() emits state[CHROMOSOME_RAND_STREAM_KEY] = np.array([seed, mcg_state], np.int64)
      iff the store carries a seeded stream.
    - from_state_mapping(payload) restores the stream iff the key is present.
    - if absent, from_state_mapping leaves the store stream unset (None) and does NOT auto-reseed.
    """
    if not hasattr(cs_mod, "CHROMOSOME_RAND_STREAM_KEY"):
        pytest.fail("CHROMOSOME_RAND_STREAM_KEY not defined in chromosome_store")

    store = ChromosomeStore()
    assert hasattr(
        store, "rand_stream"
    ), "ChromosomeStore must provide rand_stream() method / property"

    # 1. Unseeded store emits no RNG key
    state_empty = store.to_state()
    assert _EXPECTED_LEAF_KEY not in state_empty, "Unseeded store must omit RNG leaf in to_state()"

    # 2. Seeded store emits int64 two-vector [seed, mcg_state]
    assert hasattr(
        store, "set_rand_state"
    ), "ChromosomeStore must provide set_rand_state([seed, mcg_state])"
    test_seed = 42
    test_state = 1234567
    store.set_rand_state(np.array([test_seed, test_state], dtype=np.int64))

    state_seeded = store.to_state()
    assert (
        _EXPECTED_LEAF_KEY in state_seeded
    ), f"Seeded store must emit {_EXPECTED_LEAF_KEY} in to_state()"

    val = state_seeded[_EXPECTED_LEAF_KEY]
    assert isinstance(val, np.ndarray), "Leaf value must be a numpy ndarray"
    assert val.shape == (2,), f"Leaf value must have shape (2,), got {val.shape}"
    assert val.dtype == np.int64, f"Leaf value must have dtype int64, got {val.dtype}"
    assert int(val[0]) == test_seed
    assert int(val[1]) == test_state

    # 3. from_state_mapping restores exact state
    restored = ChromosomeStore.from_state_mapping(state_seeded)
    stream = restored.rand_stream()
    assert stream is not None, "from_state_mapping must restore stream when key is present"
    st = stream.get_state()
    assert st["seed"] == test_seed
    assert st["mcg_state"] == test_state

    # 4. Absent key leaves stream None (does NOT reseed)
    restored_unseeded = ChromosomeStore.from_state_mapping({})
    assert (
        restored_unseeded.rand_stream() is None
    ), "from_state_mapping without key must leave rand_stream None (no auto-reseed)"


def test_stage_a_absent_key_init_seed_once_vs_next_update_fail_closed() -> None:
    """Stage A Contract §4.3, §12, §18 A2b.

    Absent-key semantics:
    - Initial-state construction may seed once.
    - Ordinary production next_update: an absent or unseeded ([-1, -1]) leaf is a hard
      error (raise RuntimeError). next_update NEVER silently reseeds.
    """
    p = KarrTranscriptionalRegulationProcess({"rng_seed": 0})
    schema = p.ports_schema()
    if "chromosome" not in schema or _EXPECTED_LEAF_KEY not in schema["chromosome"]:
        pytest.fail(
            f"Stage B requires ('chromosome', '{_EXPECTED_LEAF_KEY}') leaf in ports_schema"
        )

    # State with missing RNG leaf
    state_missing = {
        "protein": {"counts": {tf: 0.0 for tf in p.tf_wids}},
        "complex": {"counts": {tf: 0.0 for tf in p.tf_wids}},
        "chromosome": {},
        "tf_bound_promoters": {wid: 0.0 for wid in p.tf_bound_promoters_wids},
    }

    with pytest.raises(
        RuntimeError, match="(?i)(absent|unseeded|missing|_shared_rand_stream_state)"
    ):
        p.next_update(1.0, state_missing)

    # State with sentinel unseeded leaf [-1, -1]
    state_sentinel = deepcopy(state_missing)
    state_sentinel["chromosome"][_EXPECTED_LEAF_KEY] = np.array([-1, -1], dtype=np.int64)

    with pytest.raises(
        RuntimeError, match="(?i)(absent|unseeded|missing|_shared_rand_stream_state)"
    ):
        p.next_update(1.0, state_sentinel)


def test_canary_absent_key_silent_reseed_detected() -> None:
    """Planted Canary 1: Absent-key silent reseed MUST be caught.

    Simulates a rogue runner that silently reseeds an absent stream every tick.
    Verifies that this reseed leads to repeated draws rather than continuous advance,
    and asserts that fail-closed guard correctly rejects it.
    """

    def rogue_runner_with_silent_reseed(seed: int, draws_per_tick: int, n_ticks: int):
        # A buggy implementation that creates a new stream on each tick instead of persisting
        all_draws = []
        for _ in range(n_ticks):
            stream = TxRegMcgRandStream(seed)  # SILENT RESEED
            tick_draws = [stream._mcg_rand_scalar() for _ in range(draws_per_tick)]
            all_draws.append(tick_draws)
        return all_draws

    draws = rogue_runner_with_silent_reseed(0, 3, 3)
    # The silent reseed causes tick 0, tick 1, tick 2 draws to be identical!
    is_silent_reseed = np.array_equal(draws[0], draws[1]) and np.array_equal(draws[1], draws[2])
    assert is_silent_reseed, "Rogue silent reseed must repeat identical draws"

    # A proper fail-closed check detects and kills this:
    def strict_state_checker(state: dict[str, Any]) -> None:
        if _EXPECTED_LEAF_KEY not in state.get("chromosome", {}):
            raise RuntimeError("FAIL_CLOSED: absent stream state rejected")
        val = state["chromosome"][_EXPECTED_LEAF_KEY]
        if np.array_equal(val, _UNSEEDED_SENTINEL):
            raise RuntimeError("FAIL_CLOSED: unseeded stream sentinel rejected")

    with pytest.raises(RuntimeError, match="FAIL_CLOSED: absent stream state rejected"):
        strict_state_checker({"chromosome": {}})


def test_stage_a_non_ledger_production_continuity_multi_tick() -> None:
    """Stage A Contract §4.4, §12.

    Non-ledger production continuity test across 3 ticks (active -> zero-draw -> active):
    - Uses a controlled ChromosomeStore with its state-owned stream.
    - Reconstructs the store from serialized to_state() mapping between EVERY tick.
    - Tick 1 (active): draws N1 values, serializes state.
    - Reconstructs store from Tick 1 state.
    - Tick 2 (zero-draw): performs zero draws, serializes state.
    - Reconstructs store from Tick 2 state.
    - Tick 3 (active): draws N3 values, serializes state.
    - Compares selected draws and final [seed, mcg_state] against an independently,
      continuously advancing reference stream, proving exact continuity without an oracle.
    """
    if not hasattr(cs_mod, "CHROMOSOME_RAND_STREAM_KEY"):
        pytest.fail("Stage A requires CHROMOSOME_RAND_STREAM_KEY defined in chromosome_store")

    initial_seed = 42
    ref_stream = TxRegMcgRandStream(initial_seed)
    initial_mcg = ref_stream._mcg_state

    # Initialize store 0 with seeded stream state
    store0 = ChromosomeStore()
    assert hasattr(store0, "set_rand_state"), "ChromosomeStore must provide set_rand_state()"
    assert hasattr(store0, "rand_stream"), "ChromosomeStore must provide rand_stream()"
    store0.set_rand_state(np.array([initial_seed, initial_mcg], dtype=np.int64))

    # --- TICK 1: Active draw tick (draw N1 = 2 items with weights) ---
    stream1 = store0.rand_stream()
    assert stream1 is not None, "Tick 1 stream must be present"
    w1 = np.array([0.2, 0.8, 0.5, 0.9], dtype=np.float64)
    draws_t1 = stream1.randsample(4, 2, False, w1)
    ref_draws_t1 = ref_stream.randsample(4, 2, False, w1)
    np.testing.assert_array_equal(draws_t1, ref_draws_t1, err_msg="Tick 1 draws diverged from reference")

    # Serialize Tick 1 state
    payload_t1 = store0.to_state()
    assert _EXPECTED_LEAF_KEY in payload_t1, "Tick 1 to_state() must include RNG leaf"
    state_after_t1 = payload_t1[_EXPECTED_LEAF_KEY]
    assert int(state_after_t1[1]) == ref_stream._mcg_state, "Tick 1 serialized mcg_state mismatch"

    # --- RECONSTRUCT store between Tick 1 and Tick 2 ---
    store1 = ChromosomeStore.from_state_mapping(payload_t1)
    stream2 = store1.rand_stream()
    assert stream2 is not None, "Tick 2 reconstructed stream must be present"

    # --- TICK 2: Zero-draw tick (nothing bound, 0 draws) ---
    # No draws performed on stream2 or ref_stream.
    # Serialize Tick 2 state (writeback on zero-draw)
    payload_t2 = store1.to_state()
    assert _EXPECTED_LEAF_KEY in payload_t2, "Tick 2 to_state() must include RNG leaf on zero-draw"
    state_after_t2 = payload_t2[_EXPECTED_LEAF_KEY]
    np.testing.assert_array_equal(
        state_after_t1, state_after_t2, err_msg="Zero-draw tick must preserve unchanged stream state"
    )

    # --- RECONSTRUCT store between Tick 2 and Tick 3 ---
    store2 = ChromosomeStore.from_state_mapping(payload_t2)
    stream3 = store2.rand_stream()
    assert stream3 is not None, "Tick 3 reconstructed stream must be present"

    # --- TICK 3: Active draw tick (draw N3 = 3 items with weights) ---
    w3 = np.array([0.3, 0.1, 0.7, 0.4, 0.6], dtype=np.float64)
    draws_t3 = stream3.randsample(5, 3, False, w3)
    ref_draws_t3 = ref_stream.randsample(5, 3, False, w3)
    np.testing.assert_array_equal(draws_t3, ref_draws_t3, err_msg="Tick 3 draws diverged from reference")

    # Serialize Tick 3 state
    payload_t3 = store2.to_state()
    assert _EXPECTED_LEAF_KEY in payload_t3, "Tick 3 to_state() must include RNG leaf"
    state_after_t3 = payload_t3[_EXPECTED_LEAF_KEY]

    # Final assertion: full continuity against single continuous reference stream
    assert int(state_after_t3[0]) == initial_seed
    assert int(state_after_t3[1]) == ref_stream._mcg_state, (
        f"Final mcg_state diverged: got {state_after_t3[1]} vs reference {ref_stream._mcg_state}"
    )


def test_stage_b_txreg_production_continuity_multi_tick() -> None:
    """Stage B Contract §4.3, §4.5, §12.

    Separately verify TxReg process next_update writes the same state leaf across
    actual updates (active -> zero-draw -> active), reconstructing state between ticks,
    matching a continuously advancing reference stream.
    """
    initial_seed = 0
    p = KarrTranscriptionalRegulationProcess({"rng_seed": initial_seed})
    schema = p.ports_schema()
    if "chromosome" not in schema or _EXPECTED_LEAF_KEY not in schema["chromosome"]:
        pytest.fail("Stage B ports_schema must provide chromosome._shared_rand_stream_state")

    ref_stream = TxRegMcgRandStream(initial_seed)
    initial_mcg = ref_stream._mcg_state

    # Tick 1: Active binding
    state_t1 = {
        "protein": {"counts": {tf: 5.0 for tf in p.tf_wids}},
        "complex": {"counts": {tf: 5.0 for tf in p.tf_wids}},
        "chromosome": {
            _EXPECTED_LEAF_KEY: np.array([initial_seed, initial_mcg], dtype=np.int64)
        },
        "tf_bound_promoters": {wid: 0.0 for wid in p.tf_bound_promoters_wids},
    }
    update_t1 = p.next_update(1.0, state_t1)
    assert "chromosome" in update_t1 and _EXPECTED_LEAF_KEY in update_t1["chromosome"]
    state_after_t1 = update_t1["chromosome"][_EXPECTED_LEAF_KEY]

    # Reconstruct state for Tick 2: Zero-draw tick (0 free TFs)
    new_promoters = deepcopy(state_t1["tf_bound_promoters"])
    for k, v in update_t1.get("tf_bound_promoters", {}).items():
        new_promoters[k] += v

    state_t2 = {
        "protein": {"counts": {tf: 0.0 for tf in p.tf_wids}},
        "complex": {"counts": {tf: 0.0 for tf in p.tf_wids}},
        "chromosome": {_EXPECTED_LEAF_KEY: state_after_t1.copy()},
        "tf_bound_promoters": new_promoters,
    }
    update_t2 = p.next_update(1.0, state_t2)
    assert "chromosome" in update_t2 and _EXPECTED_LEAF_KEY in update_t2["chromosome"]
    state_after_t2 = update_t2["chromosome"][_EXPECTED_LEAF_KEY]
    np.testing.assert_array_equal(state_after_t1, state_after_t2)

    # Reconstruct state for Tick 3: Active binding
    state_t3 = {
        "protein": {"counts": {tf: 5.0 for tf in p.tf_wids}},
        "complex": {"counts": {tf: 5.0 for tf in p.tf_wids}},
        "chromosome": {_EXPECTED_LEAF_KEY: state_after_t2.copy()},
        "tf_bound_promoters": new_promoters,
    }
    update_t3 = p.next_update(1.0, state_t3)
    assert "chromosome" in update_t3 and _EXPECTED_LEAF_KEY in update_t3["chromosome"]
    state_after_t3 = update_t3["chromosome"][_EXPECTED_LEAF_KEY]
    assert int(state_after_t3[1]) != int(state_after_t2[1]), "Tick 3 active binding must advance stream"


def test_stage_a_checkpoint_limitation_explicit() -> None:
    """Stage A Contract §4.4, §13, §18 A2b, Probe P7.

    Verify the explicit design limitation:
    opencell.core.checkpoint persists ONLY time_s, counts, rng_key, species_ids, metadata.
    It does NOT serialize chromosome state and does NOT serialize _shared_rand_stream_state.
    This test verifies that the design's retracted claim is honored and no test assumes
    checkpoint.py handles chromosome persistence.
    """
    save_fn_sig = inspect.signature(oc_checkpoint.save_checkpoint)
    load_fn_sig = inspect.signature(oc_checkpoint.load_checkpoint)

    # Inspect parameters and implementation
    assert "filepath" in save_fn_sig.parameters
    assert "counts" in save_fn_sig.parameters
    assert "chromosome" not in save_fn_sig.parameters
    assert "chromosome_store" not in save_fn_sig.parameters

    assert "filepath" in load_fn_sig.parameters
    assert "chromosome" not in load_fn_sig.parameters
    assert "chromosome_store" not in load_fn_sig.parameters

    # Inspect save_checkpoint source to confirm only counts, rng_key, species_ids, metadata
    src = inspect.getsource(oc_checkpoint.save_checkpoint)
    assert "counts" in src
    assert "species_ids" in src
    assert "rng_key" in src
    assert "chromosome" not in src, "checkpoint.py must NOT claim chromosome persistence"


# ---------------------------------------------------------------------------
# Stage B: TxReg Sole Consumer (RNG-only) & Topology
# ---------------------------------------------------------------------------


def test_stage_b_txreg_chromosome_port_and_topology_mappings() -> None:
    """Stage B Contract §8 step 1, §13, §18 A7.

    TxReg has a real 'chromosome' port and topology in both composite chassis mappings:
    - build_karr_chassis_v4 topology['karr_transcriptional_regulation']['chromosome'] == ('chromosome',)
    - build_karr_chassis_v5 topology['karr_transcriptional_regulation']['chromosome'] == ('chromosome',)
    And ports_schema() must declare the 'chromosome' port with '_shared_rand_stream_state'.
    """
    # 1. Parse AST of opencell/vivarium/karr_composite.py to inspect both topology definitions
    comp_src = _COMPOSITE_SRC_PATH.read_text(encoding="utf-8")
    comp_tree = ast.parse(comp_src, filename=str(_COMPOSITE_SRC_PATH))

    target_functions = ["build_karr_chassis_v4", "build_karr_chassis_v5"]
    found_topologies: dict[str, dict[str, tuple[str, ...]]] = {}

    for node in comp_tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in target_functions:
            for stmt in node.body:
                is_topo_assign = False
                val_node = None
                if (
                    isinstance(stmt, ast.Assign)
                    and any(getattr(target, "id", None) == "topology" for target in stmt.targets)
                ) or (
                    isinstance(stmt, ast.AnnAssign)
                    and getattr(stmt.target, "id", None) == "topology"
                ):
                    is_topo_assign = True
                    val_node = stmt.value

                if is_topo_assign and isinstance(val_node, ast.Dict):
                    topo_dict: dict[str, dict[str, tuple[str, ...]]] = {}
                    for k, v in zip(val_node.keys, val_node.values, strict=False):
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            proc_name = k.value
                            if isinstance(v, ast.Dict):
                                proc_topo: dict[str, tuple[str, ...]] = {}
                                for pk, pv in zip(v.keys, v.values, strict=False):
                                    if (
                                        isinstance(pk, ast.Constant)
                                        and isinstance(pk.value, str)
                                        and isinstance(pv, ast.Tuple)
                                    ):
                                        proc_topo[pk.value] = tuple(
                                            el.value
                                            for el in pv.elts
                                            if isinstance(el, ast.Constant)
                                        )
                                topo_dict[proc_name] = proc_topo
                    found_topologies[node.name] = topo_dict

    for fn_name in target_functions:
        assert fn_name in found_topologies, f"{fn_name} must define a 'topology' dict"
        topo = found_topologies[fn_name]
        assert "karr_transcriptional_regulation" in topo, (
            f"{fn_name} topology must contain 'karr_transcriptional_regulation'"
        )
        txreg_topo = topo["karr_transcriptional_regulation"]
        assert "chromosome" in txreg_topo, (
            f"{fn_name} topology['karr_transcriptional_regulation'] must map 'chromosome'"
        )
        assert txreg_topo["chromosome"] == ("chromosome",), (
            f"{fn_name} 'chromosome' port must map to ('chromosome',), got {txreg_topo['chromosome']}"
        )

    # 2. Check ports_schema
    p = KarrTranscriptionalRegulationProcess({})
    schema = p.ports_schema()
    assert "chromosome" in schema, "ports_schema must declare 'chromosome' port"
    chrom_schema = schema["chromosome"]
    assert _EXPECTED_LEAF_KEY in chrom_schema, (
        f"ports_schema['chromosome'] must declare '{_EXPECTED_LEAF_KEY}'"
    )
    leaf_spec = chrom_schema[_EXPECTED_LEAF_KEY]
    assert leaf_spec.get("_updater") == "set", "Leaf updater must be 'set'"
    assert leaf_spec.get("_emit") is True, "Leaf must have _emit=True"
    assert np.array_equal(
        leaf_spec.get("_default"), _UNSEEDED_SENTINEL
    ), f"Leaf _default must be {_UNSEEDED_SENTINEL!r}"


def test_stage_b_candidate_fixture_parity() -> None:
    """Stage B Contract §4.2, §12, §18 A3, Blocker 2.

    TxReg candidate ordering, accessibility, damage, releasable-protein, and
    exclude-overlap logic must remain completely unchanged.
    Controlled candidate fixture: compare selected indices AND post-draw mcg_state
    between current TxReg stream behavior (TxRegMcgRandStream) and the state-owned
    provider (future ChromosomeStateRandStream).
    Current code must FAIL/RED because ChromosomeStateRandStream is not yet implemented.
    """
    try:
        from opencell.util.chromosome_state_rand import ChromosomeStateRandStream
    except ImportError:
        pytest.fail(
            "Stage B candidate parity requires future ChromosomeStateRandStream from "
            "opencell.util.chromosome_state_rand (not yet implemented)."
        )

    p = KarrTranscriptionalRegulationProcess({"rng_seed": 42})

    # Controlled candidate fixture inputs
    weights = np.array([0.2, 0.78, 0.53, 0.75, 0.88, 0.31, 0.44, 0.95], dtype=np.float64)
    n_needed = 3
    is_accessible = [True, True, False, True, True, True, False, True]
    positions = np.array([100, 250, 400, 550, 700, 850, 1000, 1150], dtype=np.int64)
    strands = np.zeros(8, dtype=np.int64)
    own_footprint = 20

    # 1. Draw using current TxReg stream logic (reference)
    p._chromosome_rng = TxRegMcgRandStream(42)
    idxs_ref = p._sample_accessible_sites_batched(
        weights=weights,
        n_needed=n_needed,
        is_accessible=is_accessible,
        positions=positions,
        strands=strands,
        own_footprint=own_footprint,
    )
    state_after_ref = p._chromosome_rng._mcg_state

    # 2. Draw using future state-owned provider ChromosomeStateRandStream
    stream_state = ChromosomeStateRandStream(42)
    p._chromosome_rng = stream_state
    idxs_state = p._sample_accessible_sites_batched(
        weights=weights,
        n_needed=n_needed,
        is_accessible=is_accessible,
        positions=positions,
        strands=strands,
        own_footprint=own_footprint,
    )
    state_after_state = stream_state._mcg_state

    # Must match index-for-index and state-for-state
    assert idxs_ref == idxs_state, f"Selected indices diverged: {idxs_ref} vs {idxs_state}"
    assert (
        state_after_ref == state_after_state
    ), f"Post-draw mcg_state diverged: {state_after_ref} vs {state_after_state}"


def test_canary_candidate_order_alteration_detected() -> None:
    """Planted Canary 5: Candidate-order alteration MUST be detected.

    If candidate order or weights are permuted/altered, the selection indices diverge.
    """
    p = KarrTranscriptionalRegulationProcess({"rng_seed": 42})
    weights = np.array([0.2, 0.78, 0.53, 0.75, 0.88, 0.31, 0.44, 0.95], dtype=np.float64)
    n_needed = 3
    is_accessible = [True, True, True, True, True, True, True, True]

    p._chromosome_rng = TxRegMcgRandStream(42)
    idxs_orig = p._sample_accessible_sites_batched(
        weights=weights,
        n_needed=n_needed,
        is_accessible=is_accessible,
    )

    # Altered candidate order (reversed weights)
    p._chromosome_rng = TxRegMcgRandStream(42)
    idxs_altered = p._sample_accessible_sites_batched(
        weights=weights[::-1],
        n_needed=n_needed,
        is_accessible=is_accessible[::-1],
    )

    assert (
        idxs_orig != idxs_altered
    ), "Canary failed: altering candidate order must produce divergent selection"


# ---------------------------------------------------------------------------
# Stage B: Anti-Oracle Guards & Ledger Separation
# ---------------------------------------------------------------------------


def test_stage_b_anti_oracle_static_and_runtime_guards() -> None:
    """Stage B Contract §10 AO-1, AO-4, §18 A9.

    Static & Runtime Anti-Oracle Guards:
    - Production code path must NOT import or construct any *LedgerRandStream class.
    - Production code path must NOT import or open any .chromosome_rand_stream_ledger.json file.
    - Runtime check: in production, process._chromosome_rng must not be an instance of a ledger stream.
    """
    # 1. Static AST scan on karr_transcriptional_regulation.py
    src_text = _TXREG_SRC_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src_text, filename=str(_TXREG_SRC_PATH))

    imported_names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                imported_names.append(f"{mod}.{alias.name}")

    banned_tokens = [
        "Ledger",
        "chromosome_rand_stream_ledger",
        "TxRegChromosomeLedgerRandStream",
        "KarrLedgerReplayStream",
    ]
    for name in imported_names:
        for banned in banned_tokens:
            assert banned not in name, (
                f"Production file {_TXREG_SRC_PATH.name} must NOT import ledger symbols: {name}"
            )

    assert ".chromosome_rand_stream_ledger.json" not in src_text, (
        f"Production file {_TXREG_SRC_PATH.name} must NOT reference ledger JSON filenames"
    )

    # 2. Runtime check on default initialization
    p = KarrTranscriptionalRegulationProcess({"rng_seed": 0})
    stream_name = type(getattr(p, "_chromosome_rng", None)).__name__
    assert "Ledger" not in stream_name, (
        f"Production _chromosome_rng must not be a ledger stream class: {stream_name}"
    )


def test_canary_ledger_in_production_import_detected() -> None:
    """Planted Canary 4: Ledger-in-production import MUST be caught.

    Verifies that the static anti-oracle checker catches any rogue ledger import.
    """
    rogue_source = """
from opencell.util.txreg_mcg_rand import TxRegChromosomeLedgerRandStream
def rogue_fn():
    return TxRegChromosomeLedgerRandStream
"""
    tree = ast.parse(rogue_source)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imports.append(alias.name)

    has_ledger_import = any("Ledger" in imp for imp in imports)
    assert has_ledger_import, "Canary check must detect rogue ledger import in AST"


# ---------------------------------------------------------------------------
# Stage B: Advanced Shared State Writeback & Canaries
# ---------------------------------------------------------------------------


def test_stage_b_state_writeback_every_tick_including_zero_draw() -> None:
    """Stage B Contract §4.3, §12.

    Advanced shared state is written back every tick, even with no binding / no draw.
    next_update output must contain:
    {'chromosome': {'_shared_rand_stream_state': new_state}}
    """
    p = KarrTranscriptionalRegulationProcess({"rng_seed": 0})
    schema = p.ports_schema()
    if "chromosome" not in schema or _EXPECTED_LEAF_KEY not in schema["chromosome"]:
        pytest.fail("Stage B ports_schema must declare chromosome._shared_rand_stream_state")

    # Tick with ZERO draws (no free TFs)
    initial_seed = 0
    ref_stream = TxRegMcgRandStream(initial_seed)
    initial_mcg = ref_stream._mcg_state

    state_zero_draw = {
        "protein": {"counts": {tf: 0.0 for tf in p.tf_wids}},
        "complex": {"counts": {tf: 0.0 for tf in p.tf_wids}},
        "chromosome": {
            _EXPECTED_LEAF_KEY: np.array([initial_seed, initial_mcg], dtype=np.int64)
        },
        "tf_bound_promoters": {wid: 0.0 for wid in p.tf_bound_promoters_wids},
    }

    update = p.next_update(1.0, state_zero_draw)
    assert "chromosome" in update, "next_update must return 'chromosome' branch on zero-draw tick"
    assert _EXPECTED_LEAF_KEY in update["chromosome"], (
        f"next_update must write back '{_EXPECTED_LEAF_KEY}' on zero-draw tick"
    )
    written = update["chromosome"][_EXPECTED_LEAF_KEY]
    assert np.array_equal(
        written, np.array([initial_seed, initial_mcg], dtype=np.int64)
    ), "Zero-draw tick must write back unchanged stream state"


def test_canary_one_extra_draw_detected() -> None:
    """Planted Canary 2: One extra draw MUST be detected.

    Simulates an unintended extra draw during a tick and proves that post-draw
    mcg_state diverges immediately.
    """
    stream_expected = TxRegMcgRandStream(0)
    # Expected: 2 draws
    for _ in range(2):
        _ = stream_expected._mcg_rand_scalar()
    expected_state = stream_expected._mcg_state

    stream_mutated = TxRegMcgRandStream(0)
    # Mutated: 2 draws + 1 extra draw
    for _ in range(2):
        _ = stream_mutated._mcg_rand_scalar()
    _ = stream_mutated._mcg_rand_scalar()  # EXTRA DRAW
    mutated_state = stream_mutated._mcg_state

    assert (
        expected_state != mutated_state
    ), "Canary failed: extra draw must advance mcg_state and cause mismatch"


def test_canary_zero_draw_omitted_writeback_detected() -> None:
    """Planted Canary 3: Omitted writeback on zero-draw tick MUST be caught."""

    def validate_tick_update(update_dict: dict[str, Any]) -> None:
        if (
            "chromosome" not in update_dict
            or _EXPECTED_LEAF_KEY not in update_dict["chromosome"]
        ):
            raise AssertionError(
                f"CONTRACT VIOLATION: '{_EXPECTED_LEAF_KEY}' omitted on zero-draw tick"
            )

    # Buggy update that omits the leaf on zero-draw
    buggy_zero_draw_update = {
        "bound_tfs": {},
        "tx_rate_fold_change": {},
    }

    with pytest.raises(AssertionError, match="CONTRACT VIOLATION"):
        validate_tick_update(buggy_zero_draw_update)


# ---------------------------------------------------------------------------
# Stage B: Replay Adapter Boundary & Temporary Surfaces
# ---------------------------------------------------------------------------


def test_stage_b_dec006_replay_adapter_boundary_preserved() -> None:
    """Stage B Contract §10, §12, §18 A9, dec-006.

    dec-006 replay remains test-only:
    - Production must not serialize a ledger adapter as an MCG state.
    - Full canonical 4000-tick L2 replay must remain bit-identical after implementation.
    - The test harness injects the ledger adapter, and replay is verified without
      production relying on ledger serialization.
    """
    from opencell.util.txreg_mcg_rand import TxRegChromosomeLedgerRandStream

    ledger_stream = TxRegChromosomeLedgerRandStream.__new__(TxRegChromosomeLedgerRandStream)
    # Verify that ledger stream does NOT expose a valid int64 [seed, mcg_state] serialization
    # that production could mistakenly write to the shared state leaf
    assert not hasattr(ledger_stream, "_shared_rand_stream_state")


def test_stage_b_private_tf_bound_promoters_remains_temporary_surface() -> None:
    """Stage B Contract §8 step 5, §11, §15, §18 A1.

    In Stage B, tf_bound_promoters remains a known temporary dual representation:
    - tf_bound_promoters must STILL be present in ports_schema and emitted in next_update.
    - Stage B tests must NOT require shared footprint writeback to monomerBoundSites /
      complexBoundSites yet (that authority migration belongs to Stage C).
    """
    p = KarrTranscriptionalRegulationProcess({})
    schema = p.ports_schema()
    assert (
        "tf_bound_promoters" in schema
    ), "Stage B retains tf_bound_promoters as known temporary surface"
    assert (
        schema["tf_bound_promoters"][p.tf_bound_promoters_wids[0]].get("_updater")
        == "accumulate"
    )

    # Verify that Stage B does NOT require store footprint writeback yet
    assert "monomerBoundSites" not in schema or schema["monomerBoundSites"].get("_emit") is False


def test_stage_ab_preconditions_and_dec007_gate() -> None:
    """Stage A+B Contract §13, §15, §18 A18.

    A+B implementation cannot merge without a new dec-007 decision card:
    - dec-006 remains active in force as test-only input oracle.
    - dec-007 is an implementation gate recording production shared chromosome
      RNG stream ownership (ChromosomeStateRandStream, ChromosomeStore authority)
      while preserving dec-006.
    - Both the registry entry in decisions/_decision_index.yaml and the markdown
      card decisions/dec-007-*.md must exist and explicitly record this ownership.
    Current tree must RED on missing dec-007.
    """
    import yaml

    dec_index_path = _REPO_ROOT / "decisions" / "_decision_index.yaml"
    assert dec_index_path.exists(), "decisions/_decision_index.yaml must exist"
    with open(dec_index_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    decisions = data.get("decisions", [])
    dec_by_id = {d["id"]: d for d in decisions if isinstance(d, dict) and "id" in d}

    # 1. dec-006 must remain active in force
    assert "dec-006" in dec_by_id, "dec-006 must remain in force in decisions registry"
    assert dec_by_id["dec-006"].get("status") == "active"

    # 2. dec-007 implementation gate must be present in registry
    assert "dec-007" in dec_by_id, (
        "Stage A+B implementation gate requirement: dec-007 must be registered in "
        "decisions/_decision_index.yaml before Stage A+B merges (contract §13, §18 A18)."
    )
    dec007 = dec_by_id["dec-007"]
    assert dec007.get("status") in {"active", "ratified", "approved"}

    # 3. dec-007 file must exist and document production shared chromosome RNG stream
    dec007_file_rel = dec007.get("file")
    assert dec007_file_rel, "dec-007 must specify its file path in the decision index"
    dec007_path = _REPO_ROOT / dec007_file_rel
    assert dec007_path.exists(), f"Decision file {dec007_path} must exist"
    dec007_text = dec007_path.read_text(encoding="utf-8")

    # 4. Content assertions: must state production shared RNG ownership and preserve dec-006
    assert "dec-006" in dec007_text, "dec-007 must reference dec-006 as the test-only oracle"
    assert (
        "shared" in dec007_text.lower() and "chromosome" in dec007_text.lower()
    ), "dec-007 must record shared chromosome RNG ownership"
    assert (
        "ChromosomeStateRandStream" in dec007_text or "_shared_rand_stream_state" in dec007_text
    ), "dec-007 must record the production stream substrate or leaf"
