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
    # KarrCytokinesisProcess uses non-standard (private/fixture-prefixed)
    # attribute names instead of the generic "substrate_wids"/"enzyme_wids"
    # above, so without these it would silently fall through to an
    # identity-only comparison. See karr_cytokinesis.py lines 155-185.
    "_substrate_wids",
    "fixture_substrate_wids",
    "fixture_enzyme_wids",
    "gtp_wid",
    "pi_wid",
    "water_wid",
    "hydrogen_wid",
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
    for bounded, unbounded in zip(bounded_results, unbounded_results, strict=True):
        assert bounded["sample_seed"] == unbounded["sample_seed"]
        for channel in ("substrates", "monomers", "complexs"):
            np.testing.assert_array_equal(bounded[channel], unbounded[channel])


# ---------------------------------------------------------------------
# Targeted next_update before/after-eviction equivalence: Cytokinesis.
#
# Cytokinesis was flagged in review because its identity attributes use
# non-standard names (`_substrate_wids`, `fixture_enzyme_wids`, ...), which
# meant the generic attribute-equivalence test above previously degraded
# to an identity-only (`is`/`is not`) check for this one process -- it never
# actually compared any fixture-derived content. The attribute names have
# now been added to `_IDENTITY_ATTR_CANDIDATES` (so the generic test is no
# longer degenerate for Cytokinesis either), and this test goes further: it
# drives the real `_run_cytokinesis_tick` pipeline (not just attribute
# introspection) against a pre-eviction instance and a reconstructed
# post-eviction instance for the same seed, and asserts the produced
# `next_update`-derived substrate channel is bit-for-bit identical.
# ---------------------------------------------------------------------


def _build_cytokinesis_state(process) -> dict[str, object]:
    substrate_wids = list(process._substrate_wids)
    enzyme_wids = list(process.fixture_enzyme_wids)
    return {
        "substrate_wids": substrate_wids,
        "enzyme_wids": enzyme_wids,
        "oracle_before_substrates": np.zeros(len(substrate_wids), dtype=np.float64),
        "oracle_before_enzymes": np.zeros(len(enzyme_wids), dtype=np.float64),
        "oracle_before_bound_enzymes": np.zeros(len(enzyme_wids), dtype=np.float64),
    }


def test_cytokinesis_reconstruction_after_eviction_matches_next_update() -> None:
    """Numerical (not just attribute) equivalence for Cytokinesis: run
    `_run_cytokinesis_tick` for seed=0,tick=0 against a fresh instance,
    force eviction of that cache entry, reconstruct for the same seed, and
    confirm the reconstructed instance's `next_update`-driven substrate
    output is identical to the pre-eviction instance's output. This is the
    non-degenerate replacement for the previous identity-only comparison."""
    underlying = runner_helpers._cytokinesis_process.__wrapped__
    maxsize = runner_helpers._PER_TICK_PROCESS_CACHE_MAXSIZE
    cached_ctor = lru_cache(maxsize=maxsize)(underlying)

    seed0 = runner_helpers._sample_seed(0, 0)
    pre_eviction_process = cached_ctor(seed0)
    state = _build_cytokinesis_state(pre_eviction_process)

    original = runner_helpers._cytokinesis_process
    runner_helpers._cytokinesis_process = cached_ctor
    try:
        before_result = runner_helpers._run_cytokinesis_tick(0, 0, state)

        # Force eviction of seed0's entry, then reconstruct for the same
        # seed/tick -- `is not` proves the object was really rebuilt.
        for tick in range(1, maxsize + 2):
            cached_ctor(runner_helpers._sample_seed(0, tick))
        post_eviction_process = cached_ctor(seed0)
        assert post_eviction_process is not pre_eviction_process

        after_result = runner_helpers._run_cytokinesis_tick(0, 0, state)
    finally:
        runner_helpers._cytokinesis_process = original

    assert before_result["sample_seed"] == after_result["sample_seed"]
    np.testing.assert_array_equal(before_result["substrates"], after_result["substrates"])


# ---------------------------------------------------------------------
# Documented caveat: RNG-continuity-after-eviction for external stress
# scripts that intentionally reuse `_sample_seed(seed, tick)` keys.
#
# The main sweep never reuses a `(seed, tick)` key, so bounding these
# caches is retention-only there -- fixed above. But
# `tests/vivarium/_substrate_stress/trnaaa_stress_v2.py` is a script
# *outside* this harness fix's scope (per task instructions, no code
# workaround) whose outer loop over ALPHAS re-runs the exact same
# (seed, tick) grid once per alpha, calling
# `runner_helpers._trna_aminoacylation_process(_sample_seed(seed, tick))`
# each time. Under the old maxsize=None cache, a same-key call recurring
# across alpha passes was a cache *hit*: it returned the instance left
# over from a *previous* alpha's `next_update()` call, i.e. an instance
# whose internal RNG had already advanced -- an unintentional (and
# arguably incorrect) RNG-state leak across nominally-independent alpha
# conditions. Under the new bounded cache (maxsize=4), with 500+ distinct
# keys intervening between recurrences of the same key, that entry is long
# evicted by the time the next alpha pass reaches it, so each alpha now
# gets a fresh, independently-seeded reconstruction instead.
#
# This test proves the underlying mechanism directly: an instance that has
# been perturbed (via one `next_update()` call) and then evicted must not
# influence a same-seed reconstruction -- the reconstruction is bit-for-bit
# identical to a pristine, never-perturbed instance. This is exactly the
# eviction behavior `trnaaa_stress_v2.py`'s cross-alpha reuse now relies on
# to get independent RNG streams per alpha (more correct than the old
# leaking behavior, but numerically different from it for that one script).
# No fix is made to the stress script; this documents the caveat only.
# ---------------------------------------------------------------------


def _build_trna_state(process) -> dict[str, object]:
    metadata = runner_helpers._trna_aminoacylation_channel_metadata()
    substrate_wids = list(process.substrate_wids)
    enzyme_wids = list(process.enzyme_wids)
    n_rnas = len(metadata["free_wids"]) + len(metadata["aminoacylated_wids"])
    return {
        "substrate_wids": substrate_wids,
        "enzyme_wids": enzyme_wids,
        "oracle_before_substrates": np.zeros(len(substrate_wids), dtype=np.float64),
        "oracle_before_enzymes": np.zeros(len(enzyme_wids), dtype=np.float64),
        "oracle_before_bound_enzymes": np.zeros(len(enzyme_wids), dtype=np.float64),
        "oracle_before_rnas": np.zeros(n_rnas, dtype=np.float64),
    }


def test_trna_aminoacylation_reconstruction_after_eviction_ignores_prior_perturbation() -> None:
    """A same-seed instance perturbed by a prior `next_update()` call, once
    evicted, must reconstruct identically to a pristine instance that was
    never perturbed -- proving eviction yields independence from whatever
    happened to the discarded evicted instance. This is the concrete
    mechanism underlying the `trnaaa_stress_v2.py` caveat documented above:
    it is what makes bounding the cache change cross-alpha reuse from
    "continue the previous alpha's advanced RNG stream" (old, unbounded) to
    "start a fresh, independently-seeded stream" (new, bounded)."""
    underlying = runner_helpers._trna_aminoacylation_process.__wrapped__
    maxsize = runner_helpers._PER_TICK_PROCESS_CACHE_MAXSIZE

    seed0 = runner_helpers._sample_seed(0, 0)

    # Pristine control: never perturbed, fresh cache, single reconstruction.
    pristine_cache = lru_cache(maxsize=maxsize)(underlying)
    pristine_process = pristine_cache(seed0)
    state = _build_trna_state(pristine_process)
    original = runner_helpers._trna_aminoacylation_process
    runner_helpers._trna_aminoacylation_process = pristine_cache
    try:
        pristine_result = runner_helpers._run_trna_aminoacylation_tick(0, 0, state)
    finally:
        runner_helpers._trna_aminoacylation_process = original

    # Perturbed-then-evicted: run a tick against seed0 (advancing its RNG
    # state and thus perturbing the cached instance), then evict and
    # reconstruct for the same seed before running the "real" comparison
    # tick again.
    perturbed_cache = lru_cache(maxsize=maxsize)(underlying)
    runner_helpers._trna_aminoacylation_process = perturbed_cache
    try:
        perturbed_process = perturbed_cache(seed0)
        # Perturb: advance seed0's instance state via a throwaway tick.
        runner_helpers._run_trna_aminoacylation_tick(0, 0, state)
        for tick in range(1, maxsize + 2):
            perturbed_cache(runner_helpers._sample_seed(0, tick))
        reconstructed_process = perturbed_cache(seed0)
        assert reconstructed_process is not perturbed_process

        reconstructed_result = runner_helpers._run_trna_aminoacylation_tick(0, 0, state)
    finally:
        runner_helpers._trna_aminoacylation_process = original

    assert pristine_result["sample_seed"] == reconstructed_result["sample_seed"]
    np.testing.assert_array_equal(pristine_result["substrates"], reconstructed_result["substrates"])
    np.testing.assert_array_equal(pristine_result["RNAs"], reconstructed_result["RNAs"])


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
