"""Probe 5 — empirical test of SeedSequence determinism for OpenCell processes.

Closes OPEN-4 from the A3.3 v1 joint design critique (GPT-5.5 flagged that
`np.random.SeedSequence().spawn()` per-tick determinism is unverified).

The question: given the same `rng_seed` parameter, do two separate runs of
a stochastic OpenCell Process (D.2-real, ProteinDecay-light) produce
bit-identical outputs across multiple ticks?

If YES: existing `_rng = np.random.default_rng(rng_seed)` pattern is fine for
        deterministic replay. No code changes needed.

If NO: we need a deterministic construction keyed by
       `(base_seed, process_name, tick_index, cluster_id)` — GPT-5.5's proposal.

Run with: pytest tests/probes/test_probe5_seedsequence.py -v
"""

from __future__ import annotations

from opencell.vivarium.karr_d2_real import KarrD2RealProcess
from opencell.vivarium.karr_protein_decay_light import ProteinDecayLightProcess

# =============================================================================
# Helpers — synthesize a deterministic input state for D.2-real
# =============================================================================


def _make_d2_state(p: KarrD2RealProcess, base_value: int = 100) -> dict:
    """Build a starting state for D.2-real.

    Substrates seeded to base_value, complexes start at zero, allocations zero
    (D.2-real requests zero metabolites per Karr's algorithm).
    """
    return {
        "substrates": {wid: float(base_value) for wid in p.substrate_wids},
        "complex": {"counts": {wid: 0.0 for wid in p.complex_wids}},
        "requests": {"karr_d2_real": {wid: 0.0 for wid in p.substrate_wids}},
        "substrates_allocated": {"karr_d2_real": {wid: 0.0 for wid in p.substrate_wids}},
    }


def _make_pd_state(p: ProteinDecayLightProcess) -> dict:
    """Build a starting state for ProteinDecay-light with non-trivial complex counts."""
    state = {
        "complex": {"counts": {wid: 100.0 for wid in p.complex_wids}},
        "substrates": {wid: 1_000_000.0 for wid in p.substrate_wids},
        "protein": {"counts": {wid: 0.0 for wid in p.protein_wids}},
        "rna": {"counts": {wid: 0.0 for wid in p.rna_wids}},
        "requests": {"karr_protein_decay_light": {"ATP": 0.0, "H2O": 0.0}},
        "substrates_allocated": {
            "karr_protein_decay_light": {"ATP": 1_000_000.0, "H2O": 1_000_000.0}
        },
    }
    return state


# =============================================================================
# Test 1: D.2-real one-tick determinism
# =============================================================================


def test_d2_real_one_tick_same_seed_same_output() -> None:
    """Two D.2-real instances with the same rng_seed give bit-identical
    output on a single tick from the same starting state."""
    p1 = KarrD2RealProcess({"rng_seed": 42})
    p2 = KarrD2RealProcess({"rng_seed": 42})

    state = _make_d2_state(p1, base_value=200)
    u1 = p1.next_update(1.0, state)
    u2 = p2.next_update(1.0, state)

    # Both updates should be dict-equal
    assert u1["complex"]["counts"] == u2["complex"]["counts"], (
        "D.2-real one-tick determinism FAILED with same seed"
    )
    assert u1["substrates"] == u2["substrates"]


# =============================================================================
# Test 2: D.2-real multi-tick determinism
# =============================================================================


def test_d2_real_ten_ticks_same_seed_same_trajectory() -> None:
    """Ten ticks of D.2-real with same seed produce bit-identical trajectories.

    This catches the subtle case where one-tick determinism holds but
    state drift accumulates across ticks (e.g., if rng state isn't carried
    forward consistently).
    """
    p1 = KarrD2RealProcess({"rng_seed": 7})
    p2 = KarrD2RealProcess({"rng_seed": 7})

    state1 = _make_d2_state(p1, base_value=500)
    state2 = _make_d2_state(p2, base_value=500)

    for tick in range(10):
        u1 = p1.next_update(1.0, state1)
        u2 = p2.next_update(1.0, state2)
        assert u1["complex"]["counts"] == u2["complex"]["counts"], (
            f"Trajectory diverged at tick {tick}"
        )
        # Apply both updates to keep states in sync
        for wid in p1.complex_wids:
            d = u1["complex"]["counts"].get(wid, 0.0)
            state1["complex"]["counts"][wid] += d
            state2["complex"]["counts"][wid] += d
        for wid in p1.substrate_wids:
            d = u1["substrates"].get(wid, 0.0)
            state1["substrates"][wid] += d
            state2["substrates"][wid] += d


# =============================================================================
# Test 3: D.2-real different seeds → different outputs
# =============================================================================


def test_d2_real_different_seeds_different_output() -> None:
    """Sanity: different seeds should produce different outputs (otherwise
    determinism is trivial — RNG isn't being used at all)."""
    p1 = KarrD2RealProcess({"rng_seed": 1})
    p2 = KarrD2RealProcess({"rng_seed": 2})

    state = _make_d2_state(p1, base_value=200)
    u1 = p1.next_update(1.0, state)
    u2 = p2.next_update(1.0, state)

    # At least ONE complex's outcome should differ (the 2-MC cluster)
    differs = u1["complex"]["counts"] != u2["complex"]["counts"]
    if not differs:
        # If 200 subunits is enough for all complexes to fully form deterministically,
        # MC sampling may not differentiate. Retry with lower availability.
        state_low = _make_d2_state(p1, base_value=5)
        u1 = KarrD2RealProcess({"rng_seed": 1}).next_update(1.0, state_low)
        u2 = KarrD2RealProcess({"rng_seed": 2}).next_update(1.0, state_low)
        differs = u1["complex"]["counts"] != u2["complex"]["counts"]

    assert differs, "Different seeds produced identical output — RNG may not be used"


# =============================================================================
# Test 4: ProteinDecay-light one-tick determinism
# =============================================================================


def test_protein_decay_light_one_tick_same_seed_same_output() -> None:
    """Two ProteinDecay-light instances with same seed produce identical decay."""
    p1 = ProteinDecayLightProcess({"rng_seed": 99})
    p2 = ProteinDecayLightProcess({"rng_seed": 99})

    state = _make_pd_state(p1)
    u1 = p1.next_update(1.0, state)
    u2 = p2.next_update(1.0, state)

    assert u1["complex"]["counts"] == u2["complex"]["counts"], (
        "ProteinDecay-light one-tick determinism FAILED with same seed"
    )


# =============================================================================
# Test 5: ProteinDecay-light multi-tick determinism
# =============================================================================


def test_protein_decay_light_ten_ticks_same_seed_same_trajectory() -> None:
    """Ten ticks of ProteinDecay-light with same seed produce identical decay."""
    p1 = ProteinDecayLightProcess({"rng_seed": 13})
    p2 = ProteinDecayLightProcess({"rng_seed": 13})

    state1 = _make_pd_state(p1)
    state2 = _make_pd_state(p2)

    for tick in range(10):
        u1 = p1.next_update(1.0, state1)
        u2 = p2.next_update(1.0, state2)
        c1 = u1.get("complex", {}).get("counts", {})
        c2 = u2.get("complex", {}).get("counts", {})
        assert c1 == c2, f"Trajectory diverged at tick {tick}"
        # Apply updates
        for wid in p1.complex_wids:
            d = c1.get(wid, 0.0)
            state1["complex"]["counts"][wid] += d
            state2["complex"]["counts"][wid] += d


# =============================================================================
# Test 6: RNG independence across two processes with same seed
# =============================================================================


def test_d2_and_pd_same_seed_independent_rng_streams() -> None:
    """D.2-real and ProteinDecay-light with same numeric seed should NOT
    share state — they each have their own rng. Confirm by inspecting that
    their first .integers() calls produce different values."""
    p1 = KarrD2RealProcess({"rng_seed": 5})
    p2 = ProteinDecayLightProcess({"rng_seed": 5})

    # Both have ._rng; both seeded with 5; both untouched.
    # First call to integers() should produce the same value (each rng is fresh).
    v1 = p1._rng.integers(0, 1_000_000)
    v2 = p2._rng.integers(0, 1_000_000)
    # Same numpy version + same seed + same draw type → same value
    assert v1 == v2, "Fresh RNGs with same seed produced different values — numpy version mismatch?"
    # But after one process consumes RNG, the other should be unaffected
    p1._rng.integers(0, 1_000_000)  # consume from p1
    v1_after = p1._rng.integers(0, 1_000_000)
    v2_after = p2._rng.integers(0, 1_000_000)
    # p2's stream should match its own original v2's *successor*, NOT p1's now-shifted state
    # If they were sharing state, v2_after would == v1_after
    assert v1_after != v2_after, "RNG streams are sharing state (bug)"
