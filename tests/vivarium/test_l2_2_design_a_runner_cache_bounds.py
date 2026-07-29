"""Memory-scaling regression tests for scope-C1: bounding *every* per-tick
process factory in the Design-A hardened harness, not just ProteinDecay's.

Background: `tests/vivarium/test_l2_2_design_a_runner_protein_decay_memory.py`
covers the originally-diagnosed ProteinDecay leak (commit 8eaa927). Opus5's
review of that fix flagged scope C1: 17 *other* `@lru_cache(maxsize=None)`
factories in `_l2_2_design_a_runner_helpers.py` share the exact same defect
shape -- each is keyed on `_sample_seed(seed, tick)`, which is unique per
(seed, tick) pair by construction, so an unbounded cache on any of them is a
guaranteed-miss accumulator that retains one live process instance per tick
ever executed (10,000 for a full N=50/M=200 sweep).

All 18 per-tick factories (17 fixed here + `_protein_decay_process` fixed
previously) are now bounded to the shared `_PER_TICK_PROCESS_CACHE_MAXSIZE`
constant. These tests assert the same two deterministic, non-flaky
properties as the ProteinDecay-specific test, applied mechanically across
the full set, plus a full-pipeline numerical-equivalence check for one
additional representative "shared singleton dependency" process
(MacromolecularComplexation, which -- like Metabolism -- depends on a
separate `maxsize=1` metadata cache staying correctly shared across
per-tick reconstructions).

Deliberately NOT covered here (see the rationale comment above
`_PER_TICK_PROCESS_CACHE_MAXSIZE` in the helper module for the full
classification):
  - Zero-argument caches (`_metabolism_model`, `_metabolism_dynamics`,
    `_translation_model`): a 0-arg function can only ever hold one cache
    entry regardless of `maxsize`, so bounding them further is a no-op.
  - `maxsize=1` metadata/projection-input caches: already bounded to 1
    (metadata caches take no arguments; projection-input caches always
    call their process factory with a fixed `seed=0`, never
    `_sample_seed`), so they were never part of the leak.
  - `_protein_processing_i_process` / `_protein_processing_ii_process`:
    have no `@lru_cache` at all -- every call is immediately eligible for
    GC once its calling tick function returns, so there is nothing to
    retain (a performance cost, not a memory leak, and out of scope for
    this fix).
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


# All 18 per-tick process factories keyed on `_sample_seed(seed, tick)`,
# including `_protein_decay_process` (bound in the prior commit) so this
# suite mechanically covers the complete scope-C1 inventory in one place.
PER_TICK_FACTORY_NAMES: tuple[str, ...] = (
    "_metabolism_process",
    "_transcription_process",
    "_translation_process",
    "_rna_decay_process",
    "_rna_processing_process",
    "_rna_modification_process",
    "_trna_aminoacylation_process",
    "_protein_decay_process",
    "_protein_modification_process",
    "_protein_folding_process",
    "_protein_translocation_process",
    "_ribosome_assembly_process",
    "_macromol_process",
    "_cytokinesis_process",
    "_dna_supercoiling_process",
    "_replication_process",
    "_dna_repair_process",
    "_replication_initiation_process",
)

# Generic, deterministic "identity" attributes to compare when checking that
# reconstructing a process (post-eviction) reproduces the exact same
# construction recipe. Not every process class has every attribute; the
# comparison only runs for attributes that are actually present.
_IDENTITY_ATTR_CANDIDATES: tuple[str, ...] = (
    "substrate_wids",
    "enzyme_wids",
    "complex_wids",
    "protein_wids",
    "monomer_wids",
    "monomer_indices",
    "rna_wids",
    "mrna_wids",
    "gene_ids",
    "aa_ids",
)


@pytest.fixture(autouse=True)
def _clear_all_per_tick_caches():
    """Isolate each test from cache state left behind by any other test."""
    for name in PER_TICK_FACTORY_NAMES:
        getattr(runner_helpers, name).cache_clear()
    yield
    for name in PER_TICK_FACTORY_NAMES:
        getattr(runner_helpers, name).cache_clear()


@pytest.mark.parametrize("factory_name", PER_TICK_FACTORY_NAMES)
def test_per_tick_factory_cache_has_small_finite_maxsize(factory_name: str) -> None:
    """Every per-tick factory must be bounded (not `maxsize=None`) to prevent
    unbounded retention when driven by the per-(seed, tick)-unique
    `_sample_seed` key -- this is scope-C1's exact defect shape, mechanically
    checked across the full inventory rather than just ProteinDecay."""
    factory = getattr(runner_helpers, factory_name)
    cache_info = factory.cache_info()
    assert cache_info.maxsize is not None, (
        f"{factory_name} still has an unbounded lru_cache (maxsize=None); "
        "this is the scope-C1 defect."
    )
    assert cache_info.maxsize == runner_helpers._PER_TICK_PROCESS_CACHE_MAXSIZE
    assert 0 < cache_info.maxsize <= 16, (
        f"{factory_name}'s cache bound should stay small: it only needs to "
        "survive an immediate re-call with the same key, not accumulate "
        "across the sweep."
    )


@pytest.mark.parametrize("factory_name", PER_TICK_FACTORY_NAMES)
def test_per_tick_factory_cache_stays_bounded_across_many_unique_seeds(
    factory_name: str,
) -> None:
    """Driving far more unique (seed, tick) combinations than the cache's
    maxsize must never grow `currsize` past that bound for any of the 18
    factories -- this is the exact mechanism that turns the previously
    -unbounded RSS growth into a flat plateau at N=50/M=200."""
    factory = getattr(runner_helpers, factory_name)
    maxsize = factory.cache_info().maxsize
    assert maxsize is not None

    n_unique_calls = maxsize + 8  # far more distinct keys than the bound
    for tick in range(n_unique_calls):
        factory(runner_helpers._sample_seed(0, tick))
        cache_info = factory.cache_info()
        assert cache_info.currsize <= maxsize, (
            f"{factory_name} cache currsize {cache_info.currsize} exceeded "
            f"configured maxsize {maxsize} after a unique-keyed call -- the "
            "bound that prevents unbounded RSS growth has regressed."
        )

    final_info = factory.cache_info()
    assert final_info.hits == 0, (
        f"{factory_name}: every (seed, tick) pair yields a distinct "
        "_sample_seed value by construction, so no call in this loop should "
        "ever hit the cache; a nonzero hit count here would mean "
        "_sample_seed's uniqueness assumption (and therefore this test's "
        "premise) no longer holds."
    )
    assert final_info.misses == n_unique_calls


@pytest.mark.parametrize("factory_name", PER_TICK_FACTORY_NAMES)
def test_per_tick_factory_reconstruction_after_eviction_is_attribute_equivalent(
    factory_name: str,
) -> None:
    """Forcing eviction (by exceeding maxsize) and then reconstructing the
    same seed must reproduce an equivalent process: same class, and every
    deterministic fixture-derived identity attribute the runner actually
    reads (wid lists etc.) must match the pre-eviction instance. This is the
    generic, mechanically-sound equivalence check that applies uniformly to
    all 18 factories without needing a full per-family tick pipeline."""
    factory = getattr(runner_helpers, factory_name)
    maxsize = factory.cache_info().maxsize
    assert maxsize is not None

    seed0 = runner_helpers._sample_seed(0, 0)
    first_instance = factory(seed0)

    # Evict seed0's entry by filling the cache with other unique keys.
    # lru_cache doesn't expose keys directly, so eviction is confirmed
    # indirectly below: `first_instance is not second_instance` proves
    # seed0 was actually reconstructed rather than served from cache.
    for tick in range(1, maxsize + 2):
        factory(runner_helpers._sample_seed(0, tick))

    second_instance = factory(seed0)

    assert type(first_instance) is type(second_instance)
    assert first_instance is not second_instance, (
        f"{factory_name}: expected a genuinely new instance after eviction, "
        "not an object that somehow survived the bound cache."
    )
    for attr in _IDENTITY_ATTR_CANDIDATES:
        if hasattr(first_instance, attr) and hasattr(second_instance, attr):
            first_value = getattr(first_instance, attr)
            second_value = getattr(second_instance, attr)
            if isinstance(first_value, np.ndarray) or isinstance(second_value, np.ndarray):
                np.testing.assert_array_equal(first_value, second_value)
            else:
                assert list(first_value) == list(second_value), (
                    f"{factory_name}.{attr} differs between the pre-eviction "
                    "and post-eviction (reconstructed) instances -- bounding "
                    "the cache must not change what gets built for a given "
                    "seed."
                )


# ---------------------------------------------------------------------
# Targeted full-pipeline numerical equivalence: MacromolecularComplexation.
#
# ProteinDecay already has a dedicated full-pipeline equivalence test
# (test_l2_2_design_a_runner_protein_decay_memory.py). Macromol is added
# here as the second targeted "high-risk" process: like Metabolism, its
# per-tick factory depends on a *separate* `maxsize=1` metadata cache
# (`_macromol_channel_metadata`) staying correctly shared across
# reconstructions, so it exercises the "process factory cache interacting
# with another cache" risk shape that the generic tests above cannot catch
# on their own. Unlike the DNA-family processes, it needs no chromosome
# store, so a synthetic all-zero state can be built with the same low risk
# as ProteinDecay's existing test.
# ---------------------------------------------------------------------


def _build_macromol_state(process) -> dict[str, object]:
    substrate_wids = list(process.substrate_wids)
    monomer_wids = list(process.monomer_wids)
    complex_wids = list(process.complex_wids)
    return {
        "substrate_wids": substrate_wids,
        "monomer_wids": monomer_wids,
        "complex_wids": complex_wids,
        "oracle_before_substrates": np.zeros(len(substrate_wids), dtype=np.float64),
        "oracle_before_monomers": np.zeros(len(monomer_wids), dtype=np.float64),
        "oracle_before_complexs": np.zeros(len(complex_wids), dtype=np.float64),
    }


@pytest.mark.parametrize("n_seeds,m_ticks", [(2, 5)])
def test_macromol_tick_outputs_identical_bounded_vs_unbounded_cache(
    n_seeds: int, m_ticks: int
) -> None:
    """Numerical equivalence for MacromolecularComplexation: bounding
    `_macromol_process`'s cache must not change any produced channel array,
    including when the process factory's other dependency
    (`_macromol_channel_metadata`, a separate `maxsize=1` cache left
    untouched by this fix) stays shared across reconstructions."""
    underlying = runner_helpers._macromol_process.__wrapped__

    def _run_grid(cached_ctor) -> list[dict[str, np.ndarray]]:
        cached_ctor.cache_clear()
        seed0_process = cached_ctor(runner_helpers._sample_seed(0, 0))
        state = _build_macromol_state(seed0_process)
        results = []
        original = runner_helpers._macromol_process
        runner_helpers._macromol_process = cached_ctor
        try:
            for seed in range(n_seeds):
                for tick in range(m_ticks):
                    results.append(
                        runner_helpers._run_macromol_tick(seed, tick, state)
                    )
        finally:
            runner_helpers._macromol_process = original
        return results

    bounded_cache = lru_cache(maxsize=runner_helpers._PER_TICK_PROCESS_CACHE_MAXSIZE)(underlying)
    unbounded_cache = lru_cache(maxsize=None)(underlying)

    bounded_results = _run_grid(bounded_cache)
    unbounded_results = _run_grid(unbounded_cache)

    assert len(bounded_results) == len(unbounded_results) == n_seeds * m_ticks
    for bounded, unbounded in zip(bounded_results, unbounded_results):
        assert bounded["sample_seed"] == unbounded["sample_seed"]
        for channel in ("substrates", "monomers", "complexs"):
            np.testing.assert_array_equal(bounded[channel], unbounded[channel])


def test_per_tick_factory_inventory_is_complete() -> None:
    """Guard against silent drift: if a new per-tick factory is ever added
    to the helper module without being added to this suite's inventory (or
    an existing one is renamed/removed), fail loudly instead of letting
    scope-C1 coverage quietly go stale."""
    import inspect
    from functools import _lru_cache_wrapper  # type: ignore[attr-defined]

    all_lru_cached = {
        name
        for name, obj in vars(runner_helpers).items()
        if isinstance(obj, _lru_cache_wrapper)
    }
    # Factories keyed on _sample_seed(seed, tick) take exactly one positional
    # parameter named "seed" with no default -- this mirrors the mechanical
    # inventory performed by hand and catches drift without re-deriving it.
    single_seed_arg_factories = set()
    for name in all_lru_cached:
        wrapped = getattr(runner_helpers, name).__wrapped__
        params = list(inspect.signature(wrapped).parameters.values())
        if len(params) == 1 and params[0].name == "seed" and params[0].default is inspect.Parameter.empty:
            single_seed_arg_factories.add(name)

    assert single_seed_arg_factories == set(PER_TICK_FACTORY_NAMES), (
        "The set of single-`seed`-argument lru_cache factories in "
        "_l2_2_design_a_runner_helpers.py no longer matches this suite's "
        "PER_TICK_FACTORY_NAMES inventory. If a factory was added/renamed, "
        "update PER_TICK_FACTORY_NAMES (and confirm it is bounded to "
        "_PER_TICK_PROCESS_CACHE_MAXSIZE, not maxsize=None) rather than "
        "silently losing coverage.\n"
        f"In helpers but not in suite: {single_seed_arg_factories - set(PER_TICK_FACTORY_NAMES)}\n"
        f"In suite but not in helpers: {set(PER_TICK_FACTORY_NAMES) - single_seed_arg_factories}"
    )
