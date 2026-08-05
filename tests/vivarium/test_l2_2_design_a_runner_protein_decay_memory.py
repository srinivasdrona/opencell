"""Memory-scaling regression tests for the ProteinDecay Design-A tick harness.

Covers the ~0.78 GiB/min unbounded-RSS-growth defect fixed by bounding
`_protein_decay_process`'s `lru_cache` (see `_PER_TICK_PROCESS_CACHE_MAXSIZE`
in `_l2_2_design_a_runner_helpers.py`). These tests assert two deterministic,
non-flaky properties instead of wall-clock/RSS thresholds:

1. The cache is *mechanically* bounded (`cache_info().maxsize` is a small
   finite constant, and `currsize` never exceeds it however many distinct
   per-tick seeds are constructed) -- this is what actually prevents the
   unbounded growth, independent of any particular machine's timing.
2. Bounding the cache does not change any numerical output: because
   `_protein_decay_process` is a pure, side-effect-free function of `seed`,
   re-running the same seed/tick grid with the cache bounded vs. effectively
   unbounded must produce bit-identical raw channel arrays.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

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

from tests.vivarium import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402


def _build_state(process) -> dict[str, object]:
    substrate_wids = list(process.substrate_wids)
    enzyme_wids = list(process.enzyme_wids)
    monomer_wids = list(process.protein_wids)
    complex_wids = list(process.complex_wids)
    return {
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


def test_protein_decay_process_cache_has_small_finite_maxsize() -> None:
    """The lru_cache must be bounded (not `maxsize=None`) to prevent unbounded
    retention when driven by the per-(seed, tick)-unique `_sample_seed` key."""
    cache_info = runner_helpers._protein_decay_process.cache_info()
    assert cache_info.maxsize is not None
    assert cache_info.maxsize == runner_helpers._PER_TICK_PROCESS_CACHE_MAXSIZE
    assert 0 < cache_info.maxsize <= 16, (
        "Cache bound should stay small: it only needs to survive an immediate "
        "re-call with the same key, not accumulate across the sweep."
    )


def test_protein_decay_process_cache_stays_bounded_across_many_unique_seeds() -> None:
    """Driving far more unique (seed, tick) combinations than the cache's
    maxsize must never grow `currsize` past that bound -- this is the exact
    mechanism that turns the previously-unbounded ~0.78 GiB/min RSS growth
    into a flat plateau at N=50/M=200 (10,000 unique per-tick constructions)."""
    runner_helpers._protein_decay_process.cache_clear()
    maxsize = runner_helpers._protein_decay_process.cache_info().maxsize
    assert maxsize is not None

    n_unique_calls = maxsize * 20  # far more distinct keys than the bound
    for seed in range(3):
        for tick in range(n_unique_calls // 3 + 1):
            runner_helpers._protein_decay_process(runner_helpers._sample_seed(seed, tick))
            cache_info = runner_helpers._protein_decay_process.cache_info()
            assert cache_info.currsize <= maxsize, (
                f"cache currsize {cache_info.currsize} exceeded configured "
                f"maxsize {maxsize} after a unique-keyed call -- the bound "
                "that prevents unbounded RSS growth has regressed."
            )
    final_info = runner_helpers._protein_decay_process.cache_info()
    assert final_info.hits == 0, (
        "Every (seed, tick) pair yields a distinct _sample_seed value by "
        "construction, so no call in this loop should ever hit the cache; "
        "a nonzero hit count here would mean _sample_seed's uniqueness "
        "assumption (and therefore this test's premise) no longer holds."
    )
    assert final_info.misses == n_unique_calls // 3 * 3 + 3


@pytest.mark.parametrize("n_seeds,m_ticks", [(2, 5)])
def test_protein_decay_tick_outputs_identical_bounded_vs_unbounded_cache(
    n_seeds: int, m_ticks: int
) -> None:
    """Numerical equivalence: bounding the cache must not change any produced
    channel array. `_protein_decay_process` is a pure function of `seed` (no
    shared mutable state survives eviction), so replaying the same grid with
    the cache bounded (current, fixed behavior) vs. effectively unbounded
    (previous, defective behavior) must yield bit-identical results."""
    underlying = runner_helpers._protein_decay_process.__wrapped__

    def _run_grid(cached_ctor) -> list[dict[str, np.ndarray]]:
        cached_ctor.cache_clear()
        seed0_process = cached_ctor(runner_helpers._sample_seed(0, 0))
        state = _build_state(seed0_process)
        results = []
        original = runner_helpers._protein_decay_process
        runner_helpers._protein_decay_process = cached_ctor
        try:
            for seed in range(n_seeds):
                for tick in range(m_ticks):
                    results.append(
                        runner_helpers._run_protein_decay_tick(seed, tick, state)
                    )
        finally:
            runner_helpers._protein_decay_process = original
        return results

    bounded_cache = lru_cache(maxsize=runner_helpers._PER_TICK_PROCESS_CACHE_MAXSIZE)(underlying)
    unbounded_cache = lru_cache(maxsize=None)(underlying)

    bounded_results = _run_grid(bounded_cache)
    unbounded_results = _run_grid(unbounded_cache)

    assert len(bounded_results) == len(unbounded_results) == n_seeds * m_ticks
    for bounded, unbounded in zip(bounded_results, unbounded_results, strict=True):
        assert bounded["sample_seed"] == unbounded["sample_seed"]
        for channel in ("substrates", "monomers", "complexs"):
            np.testing.assert_array_equal(bounded[channel], unbounded[channel])
