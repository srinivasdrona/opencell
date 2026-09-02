from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from scipy.io import loadmat

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

from opencell.state.chromosome_store import ChromosomeStore, SparseTriplet
from opencell.vivarium.chromosome_views import current_damage_sites
from opencell.vivarium.karr_dna_damage import KarrDNADamageProcess

_SPARSE_FIELDS = (
    "damagedBases",
    "strandBreaks",
    "gapSites",
    "abasicSites",
    "damagedSugarPhosphates",
    "intrastrandCrossLinks",
    "hollidayJunctions",
)


def _empty_sparse(shape: tuple[int, int]) -> dict[str, object]:
    return SparseTriplet.empty(*shape).to_state()


def _base_state(
    replication_state: str = "idle",
    fork_position_bp: dict[str, int | None] | None = None,
    uv_dose: float = 1.0,
    gamma_dose: float = 1.0,
) -> dict[str, Any]:
    shape = (ChromosomeStore.DEFAULT_SEQUENCE_LEN, ChromosomeStore.DEFAULT_N_COMPARTMENTS)
    return {
        "chromosome": {
            **{field: _empty_sparse(shape) for field in _SPARSE_FIELDS},
            "damage_events_cumulative": [],
            "repair_events_cumulative": [],
            "fork_position_bp": fork_position_bp or {"left": None, "right": None},
            "replication_stall_flag": 0.0,
            "replication_state": replication_state,
        },
        "substrates": {
            "H2O": 1.0e9,
            "UVB_radiation": uv_dose,
            "gamma_radiation": gamma_dose,
        },
        "substrates_allocated": {
            "karr_dna_damage": {
                "H2O": 1.0e9,
                "UVB_radiation": uv_dose,
                "gamma_radiation": gamma_dose,
            }
        },
    }


def _apply_update(state: dict[str, Any], update: dict[str, Any], process: KarrDNADamageProcess) -> None:
    chrom_update = update.get("chromosome", {})
    if "damage_events_cumulative" in chrom_update:
        state["chromosome"]["damage_events_cumulative"].extend(
            list(chrom_update["damage_events_cumulative"])
        )
    for field in _SPARSE_FIELDS:
        if field in chrom_update:
            state["chromosome"][field] = SparseTriplet.from_state(
                chrom_update[field],
                shape=process.chromosome_shape,
            ).to_state()
    if "replication_stall_flag" in chrom_update:
        state["chromosome"]["replication_stall_flag"] = float(
            state["chromosome"]["replication_stall_flag"] + float(chrom_update["replication_stall_flag"])
        )
    for wid, delta in update.get("substrates", {}).items():
        state["substrates"][wid] = float(state["substrates"].get(wid, 0.0)) + float(delta)


def _trace_path_candidates() -> list[Path]:
    """Test-side-only oracle trace lookup (Rule 8 permits tests reading
    oracle data for cross-checks; production code must never do this --
    see karr_dna_damage.py's removal of the former trace_path parameter).
    """
    rel = Path("data") / "m1_sources" / "karr_native" / "per_process_traces" / "DNADamage_100ticks.mat"
    return [
        _REPO_ROOT / rel,
        Path("E:/opencell") / rel,
        Path("/mnt/e/opencell") / rel,
    ]


def _trace_total_if_available(process: KarrDNADamageProcess) -> float | None:
    trace_path = next((p for p in _trace_path_candidates() if p.exists()), None)
    if trace_path is None:
        return None

    try:
        mat = loadmat(str(trace_path), squeeze_me=True, struct_as_record=False)
    except Exception:
        return None

    def _cumulative_total(arr: np.ndarray) -> float:
        flat = np.asarray(arr, dtype=np.float64).reshape(-1)
        if flat.size <= 0:
            return 0.0
        if flat.size == 1:
            return float(flat[0])
        return float(flat[-1] - flat[0])

    total = 0.0
    found_kind_series = False
    for kind in process.damage_kinds:
        for key in (kind, f"{kind}_events", f"{kind}_count", f"{kind}_counts", f"damage_{kind}"):
            if key in mat:
                total += _cumulative_total(np.asarray(mat[key]))
                found_kind_series = True
                break
    if found_kind_series:
        return total

    for key in ("damage_sites_count", "total_damage_count", "n_damage_sites", "damage_count"):
        if key in mat:
            return _cumulative_total(np.asarray(mat[key]))

    return None


def test_instantiates_with_defaults() -> None:
    process = KarrDNADamageProcess({})
    assert process.name == "karr_dna_damage"
    assert process.sequence_length_nt > 100_000
    assert process.damage_kinds == ["uv_like", "oxidative", "alkylation", "depurination"]
    # Item 4: the lumped per-kind rate override no longer exists at all.
    assert not hasattr(process, "kind_rates_per_s")
    assert not hasattr(process, "_kind_rate_override_active")
    assert not hasattr(process, "_scaled_reaction_rates_from_kind_override")
    assert "kind_rates_per_s" not in KarrDNADamageProcess.defaults
    # Item 3: the WholeCellKB monomer/complex DNA-footprint arrays that
    # feed the literal nAccessibleSites formula are genuinely loaded.
    assert process.monomer_dna_footprints.size > 0
    assert process.complex_dna_footprints.size > 0


def test_calc_expected_reaction_rates_matches_accepted_uv_aggregate() -> None:
    # calcExpectedReactionRates()/calcNumberVulnerableSites() are Karr's own
    # FBA resource-request formulas (DNADamage.m::calcResourceRequirements_*)
    # -- untouched by the item-3 firing-law fix, which only changes
    # next_update()'s own selectionProbability/stochasticRound path.
    process = KarrDNADamageProcess({})
    state = _base_state()
    state["substrates"]["UVB_radiation"] = 1.0
    state["substrates"]["gamma_radiation"] = 0.0
    state["substrates_allocated"][process.name]["UVB_radiation"] = 1.0
    state["substrates_allocated"][process.name]["gamma_radiation"] = 0.0

    rates = process.calcExpectedReactionRates(state)
    uv_local_idx = process.substrate_wids.index("UVB_radiation") + 1
    observed = float(np.sum(rates[process.reaction_radiation == uv_local_idx]))
    assert observed == pytest.approx(0.013379543476309085, rel=0.0, abs=1e-15)


def test_selection_probability_is_literal_stepsize_reactionbounds_and_radiation_substrate() -> None:
    """Item 3: firing must use Karr's own evolveState formula --
    `selectionProbability = stepSizeSec * reactionBounds(j,2) *
    substrates(radiationLclIdx)` (or without the substrate factor when
    reactionRadiation(j) == 0) -- never calcExpectedReactionRates().
    """
    process = KarrDNADamageProcess({})
    uv_idx = process.reaction_ids.index("DNADamage_CSNCSN_cyclobutane_CSNCSN_UVB_radiation")
    base_loss_idx = process.reaction_ids.index("DNADamage_SpontaneousBaseLoss_adenine")

    dt = 3.0
    dose = 5.0
    working_substrates = {wid: 0.0 for wid in process.substrate_wids}
    uv_wid_idx = int(process.reaction_radiation[uv_idx]) - 1
    working_substrates[process.substrate_wids[uv_wid_idx]] = dose

    uv_prob = process._selection_probability(uv_idx, dt, working_substrates)
    expected_uv = dt * float(process.reaction_bounds[uv_idx, 1]) * dose
    assert uv_prob == pytest.approx(expected_uv, rel=0.0, abs=1e-15)

    # Non-radiation-gated reaction: no substrate factor at all.
    assert int(process.reaction_radiation[base_loss_idx]) == 0
    base_loss_prob = process._selection_probability(base_loss_idx, dt, working_substrates)
    expected_base_loss = dt * float(process.reaction_bounds[base_loss_idx, 1])
    assert base_loss_prob == pytest.approx(expected_base_loss, rel=0.0, abs=1e-15)

    # Zero dose -> zero probability for the radiation-gated reaction.
    working_substrates[process.substrate_wids[uv_wid_idx]] = 0.0
    assert process._selection_probability(uv_idx, dt, working_substrates) == 0.0


def test_stochastic_round_is_unbiased() -> None:
    """Karr randStream.stochasticRound: floor(x) + Bernoulli(frac(x)),
    E[stochasticRound(x)] == x exactly."""
    process = KarrDNADamageProcess({"rng_seed": 42})
    value = 2.3
    draws = [process._stochastic_round(value) for _ in range(20_000)]
    assert set(draws) <= {2, 3}
    assert np.mean(draws) == pytest.approx(value, abs=0.02)
    assert process._stochastic_round(0.0) == 0
    assert process._stochastic_round(-1.0) == 0
    assert process._stochastic_round(5.0) == 5


def test_n_accessible_sites_subtracts_footprints_and_damaged_nnz() -> None:
    """Literal Karr Chromosome.m::sampleAccessibleSites nAccessibleSites =
    collapse(polymerizedRegions) - sum(monomerDNAFootprints(boundMonomers))
    - sum(complexDNAFootprints(boundComplexs)) - nnz(damagedSites)."""
    process = KarrDNADamageProcess({})
    chromosome_state = _base_state()["chromosome"]
    store = process._resolve_chromosome_store(chromosome_state)
    baseline = process._n_accessible_sites(store, chromosome_state)
    assert baseline > 0.0

    # Bind one monomer (global index 1) at a site -- baseline must shrink
    # by exactly that monomer's footprint.
    bound_state = dict(chromosome_state)
    bound_state["monomerBoundSites"] = SparseTriplet(
        positions=np.asarray([100], dtype=np.int64),
        strands=np.asarray([0], dtype=np.int64),
        values=np.asarray([1], dtype=np.int64),
        shape=process.chromosome_shape,
    ).to_state()
    store_bound = process._resolve_chromosome_store(bound_state)
    with_monomer = process._n_accessible_sites(store_bound, bound_state)
    assert with_monomer == pytest.approx(baseline - float(process.monomer_dna_footprints[0]))

    # Adding one damaged site subtracts exactly one more (nnz), independent
    # of the damage-product value.
    damaged_state = dict(chromosome_state)
    damaged_state["damagedBases"] = SparseTriplet(
        positions=np.asarray([200], dtype=np.int64),
        strands=np.asarray([0], dtype=np.int64),
        values=np.asarray([1], dtype=np.int64),
        shape=process.chromosome_shape,
    ).to_state()
    store_damaged = process._resolve_chromosome_store(damaged_state)
    with_damage = process._n_accessible_sites(store_damaged, damaged_state)
    assert with_damage == pytest.approx(baseline - 1.0)


def test_reaction_damage_field_fails_closed_on_unknown_field() -> None:
    """Item 6: an unknown/out-of-range damage field must raise, never
    silently default to 'damagedBases'."""
    process = KarrDNADamageProcess({})
    # Out of range.
    with pytest.raises(ValueError):
        process._reaction_damage_field(len(process.reaction_damage_types) + 10)
    # Corrupt/unknown field name.
    process.reaction_damage_types = list(process.reaction_damage_types)
    process.reaction_damage_types[0] = "notARealChromosomeField"
    with pytest.raises(ValueError):
        process._reaction_damage_field(0)


def test_max_reactions_signed_zero_safe() -> None:
    """Signed-zero regression: a +0.0 stoichiometry entry must never poison
    the maxReactions floor(min(...)) via -0.0 -> -inf division."""
    process = KarrDNADamageProcess({})
    process.reaction_small_molecule_stoich = np.asarray(
        [[0.0], [-2.0]], dtype=np.float64
    )
    process.substrate_wids = ["ZeroStoichSubstrate", "RealSubstrate"]
    working_substrates = {"ZeroStoichSubstrate": 1.0, "RealSubstrate": 10.0}
    max_reactions = process._max_reactions_for_reaction(0, working_substrates=working_substrates)
    assert max_reactions == 5
    assert np.isfinite(max_reactions)


def test_one_tick_damage_delta_sign() -> None:
    process = KarrDNADamageProcess({"rng_seed": 10})
    state = _base_state(uv_dose=200.0, gamma_dose=200.0)
    new_sites: list[dict[str, Any]] = []
    for _ in range(30):
        update = process.next_update(1.0, state)
        new_sites.extend(update.get("chromosome", {}).get("damage_events_cumulative", []))
        _apply_update(state, update, process)
    assert len(new_sites) > 0
    for site in new_sites:
        assert int(site["position"]) > 0
        assert int(site["position"]) <= process.sequence_length_nt
        assert str(site["kind"]) in set(process.damage_kinds)
        assert str(site["reaction_id"]).startswith("DNADamage_")
        assert str(site["damage_field"]) in _SPARSE_FIELDS
        assert int(site["damage_product"]) > 0
        assert int(site["age_ticks"]) == 0


def test_emits_substrate_requests_from_vulnerable_site_rates() -> None:
    process = KarrDNADamageProcess({"rng_seed": 1})
    schema = process.ports_schema()
    assert "requests" in schema
    assert "substrates_allocated" in schema
    assert process.name in schema["requests"]
    assert process.name in schema["substrates_allocated"]
    for field in _SPARSE_FIELDS:
        assert field in schema["chromosome"]

    update = process.next_update(1.0, _base_state())
    assert "requests" in update
    emitted = update["requests"][process.name]
    assert set(emitted) == set(process.allocation_substrate_wids)
    assert all(float(v) >= 0.0 for v in emitted.values())


def test_replication_stall_flag_on_fork_hit() -> None:
    process = KarrDNADamageProcess({"rng_seed": 7})
    reaction_index = process.reaction_ids.index("DNADamage_CSNCSN_cyclobutane_CSNCSN_UVB_radiation")

    def _selection_probability(rxn_idx: int, dt: float, working_substrates: dict[str, float]) -> float:
        _ = dt, working_substrates
        return 1.0 if int(rxn_idx) == reaction_index else 0.0

    process._selection_probability = _selection_probability  # type: ignore[method-assign]
    process._stochastic_round = lambda value: 1 if value > 0 else 0  # type: ignore[method-assign]
    # 0-based (position, strand) pair; final reported "position" is 1-based
    # (zero_based_pos + 1), so 10100 here reproduces the fork-hit position
    # 10101 the old strand-agnostic-position stub used.
    process._sample_literal_motif_sites = lambda **kwargs: [(10100, 0)]  # type: ignore[method-assign]
    state = _base_state(
        replication_state="elongating",
        fork_position_bp={"left": 10101, "right": 250000},
    )
    update = process.next_update(1.0, state)
    assert update["chromosome"]["replication_stall_flag"] == 1.0
    assert update["chromosome"]["damage_events_cumulative"][0]["position"] == 10101


def test_sparse_writeback_uses_reaction_field_and_product_semantics() -> None:
    process = KarrDNADamageProcess({"rng_seed": 3})
    uv_idx = process.reaction_ids.index("DNADamage_CSNCSN_cyclobutane_CSNCSN_UVB_radiation")
    base_loss_idx = process.reaction_ids.index("DNADamage_SpontaneousBaseLoss_adenine")

    def _selection_probability(rxn_idx: int, dt: float, working_substrates: dict[str, float]) -> float:
        _ = dt, working_substrates
        return 1.0 if int(rxn_idx) in (uv_idx, base_loss_idx) else 0.0

    process._selection_probability = _selection_probability  # type: ignore[method-assign]
    process._stochastic_round = lambda value: 1 if value > 0 else 0  # type: ignore[method-assign]
    # Force a deterministic (ascending) reaction visitation order so the
    # sample-position queue below can be paired to reactions positionally,
    # matching Karr's real per-reaction loop semantics (order is random in
    # production; only fixed here for test determinism).
    process._reaction_order = lambda n: np.arange(int(n), dtype=np.int64)  # type: ignore[method-assign]
    ordered_reaction_indices = sorted((uv_idx, base_loss_idx))
    # 0-based (position, strand) pairs returned directly by the literal
    # sampler (no further conversion happens in _sample_reaction_coords).
    sample_by_index = {uv_idx: [(10, 0)], base_loss_idx: [(16, 0)]}
    queue = [sample_by_index[idx] for idx in ordered_reaction_indices]

    def _sample_literal_motif_sites(**kwargs: Any) -> list[tuple[int, int]]:
        _ = kwargs
        if not queue:
            return []
        return queue.pop(0)

    process._sample_literal_motif_sites = _sample_literal_motif_sites  # type: ignore[method-assign]
    state = _base_state()
    state["substrates"]["gamma_radiation"] = 0.0
    state["substrates_allocated"][process.name]["gamma_radiation"] = 0.0
    update = process.next_update(1.0, state)
    chrom_update = update["chromosome"]
    assert len(chrom_update["damage_events_cumulative"]) == 2

    uv_triplet = SparseTriplet.from_state(
        chrom_update["intrastrandCrossLinks"],
        shape=process.chromosome_shape,
    )
    assert uv_triplet.positions.tolist() == [10]
    assert uv_triplet.values.tolist() == [process.reaction_dna_products[uv_idx]]
    assert 0 <= int(uv_triplet.strands[0]) < process.chromosome_shape[1]

    abasic_triplet = SparseTriplet.from_state(
        chrom_update["abasicSites"],
        shape=process.chromosome_shape,
    )
    assert abasic_triplet.positions.tolist() == [16]
    assert abasic_triplet.values.tolist() == [process.reaction_dna_products[base_loss_idx]]

    # Item 5: substrate writeback must be reflected as an actual port
    # update (`update["substrates"]`), not just internal bookkeeping.
    assert "substrates" in update
    stoich_col_uv = process.reaction_small_molecule_stoich[:, uv_idx]
    stoich_col_bl = process.reaction_small_molecule_stoich[:, base_loss_idx]
    for sub_idx, wid in enumerate(process.substrate_wids):
        expected_delta = float(stoich_col_uv[sub_idx]) + float(stoich_col_bl[sub_idx])
        if expected_delta != 0.0:
            assert update["substrates"][wid] == pytest.approx(expected_delta)


def test_sparse_occupied_sites_prevent_reuse_when_unique_enabled() -> None:
    process = KarrDNADamageProcess({"rng_seed": 5, "enforce_unique_positions": True})
    reaction_index = process.reaction_ids.index("DNADamage_CSNCSN_cyclobutane_CSNCSN_UVB_radiation")

    def _selection_probability(rxn_idx: int, dt: float, working_substrates: dict[str, float]) -> float:
        _ = dt, working_substrates
        return 1.0 if int(rxn_idx) == reaction_index else 0.0

    process._selection_probability = _selection_probability  # type: ignore[method-assign]
    process._stochastic_round = lambda value: 1 if value > 0 else 0  # type: ignore[method-assign]
    state = _base_state()
    state["chromosome"]["intrastrandCrossLinks"] = SparseTriplet(
        positions=np.asarray([0], dtype=np.int64),
        strands=np.asarray([0], dtype=np.int64),
        values=np.asarray([1], dtype=np.int64),
        shape=process.chromosome_shape,
    ).to_state()

    update = process.next_update(1.0, state)
    events = update["chromosome"]["damage_events_cumulative"]
    assert len(events) == 1
    assert int(events[0]["position"]) != 1


def test_literal_single_tick_event_count_matches_selfconsistent_expectation() -> None:
    """Self-consistency regression for the item-3 literal law: over many
    seeds, the mean fired-event count for a single undamaged tick must
    match the analytically expected sum (unbiased stochasticRound) computed
    directly from the same per-reaction selectionProbability/nAccessibleSites
    /candidate-count formulas next_update() itself uses. This intentionally
    does NOT compare against calcExpectedReactionRates() (Karr's separate,
    non-firing FBA resource-request formula) -- see
    scripts/dna_damage_mechanism_canary.py for why those two Karr formulas
    are expected to diverge.
    """
    template = KarrDNADamageProcess({})
    state = _base_state()
    chromosome_state = state["chromosome"]
    store = template._resolve_chromosome_store(chromosome_state)
    n_accessible_sites = template._n_accessible_sites(store, chromosome_state)
    working_substrates = {
        wid: state["substrates_allocated"][template.name].get(wid, state["substrates"].get(wid, 0.0))
        for wid in template.substrate_wids
    }

    expected_total = 0.0
    n_reactions = int(template.reaction_bounds.shape[0])
    for rxn_idx in range(n_reactions):
        max_reactions = template._max_reactions_for_reaction(rxn_idx, working_substrates=working_substrates)
        if max_reactions is not None and max_reactions <= 0:
            continue
        prob = template._selection_probability(rxn_idx, 1.0, working_substrates)
        if prob <= 0.0:
            continue
        motif = template.reaction_vulnerable_motifs[rxn_idx]
        if isinstance(motif, str):
            gc = float(template.sequence_gc_content)
            n_gc = sum(1 for base in motif if base in ("G", "C"))
            n_complement = len(motif) - n_gc
            gc_term = (gc / 2.0) ** n_gc * ((1.0 - gc) / 2.0) ** n_complement
            raw = n_accessible_sites * prob * gc_term
        else:
            candidates = template._reaction_candidate_coords(chromosome_state, rxn_idx)
            raw = len(candidates) * prob
        capped = raw if max_reactions is None else min(raw, float(max_reactions))
        expected_total += max(0.0, capped)

    totals: list[float] = []
    for seed in range(200):
        process = KarrDNADamageProcess({"rng_seed": seed})
        update = process.next_update(1.0, _base_state())
        totals.append(float(len(update.get("chromosome", {}).get("damage_events_cumulative", []))))

    observed = float(np.mean(np.asarray(totals, dtype=np.float64)))
    tolerance = max(0.5, 0.25 * max(1.0, expected_total))
    assert abs(observed - expected_total) <= tolerance


def test_no_nan_no_negative_regression() -> None:
    process = KarrDNADamageProcess({"rng_seed": 99})
    state = _base_state(uv_dose=50.0, gamma_dose=50.0)
    previous_count = 0
    for _ in range(100):
        update = process.next_update(1.0, state)
        _apply_update(state, update, process)
        sites = current_damage_sites(state)
        assert len(sites) >= previous_count
        previous_count = len(sites)

    for site in current_damage_sites(state):
        pos = float(site["position"])
        assert np.isfinite(pos)
        assert int(pos) > 0
        assert int(pos) <= process.sequence_length_nt
        assert str(site["kind"]) in set(process.damage_kinds)
        assert int(site["age_ticks"]) >= 0

    assert np.isfinite(float(state["chromosome"]["replication_stall_flag"]))
    assert float(state["chromosome"]["replication_stall_flag"]) >= 0.0
    for wid, amount in state["substrates"].items():
        assert np.isfinite(amount), wid


def test_no_kind_rate_override_mechanism_exists() -> None:
    """Item 4 regression: the lumped per-kind rate override
    (`kind_rates_per_s`/`_kind_rate_override_active`/
    `_scaled_reaction_rates_from_kind_override`/`_DEFAULT_KIND_RATES_PER_S`)
    must be removed entirely, not merely left dormant. Firing is governed
    solely by the literal per-reaction selectionProbability/stochasticRound
    law (item 3); there is no re-entry path that can override it.
    """
    import inspect

    from opencell.vivarium import karr_dna_damage as module

    process = KarrDNADamageProcess({})

    assert "kind_rates_per_s" not in KarrDNADamageProcess.defaults
    assert "trace_path" not in KarrDNADamageProcess.defaults
    assert "use_trace_rates_if_available" not in KarrDNADamageProcess.defaults
    assert not hasattr(process, "kind_rates_per_s")
    assert not hasattr(process, "_kind_rate_override_active")
    assert not hasattr(process, "_scaled_reaction_rates_from_kind_override")
    assert not hasattr(process, "trace_kind_rates_per_s")
    assert not hasattr(process, "used_trace_rates")
    assert not hasattr(process, "_load_trace_kind_rates")
    assert not hasattr(module, "_DEFAULT_TRACE_PATH")
    assert not hasattr(module, "_DEFAULT_KIND_RATES_PER_S")

    source = inspect.getsource(module)
    assert "_100ticks" not in source
    assert "per_process_traces" not in source
    assert "DNADamage_100ticks.mat" not in source
    assert "kind_rates_per_s" not in source
    assert "_DEFAULT_KIND_RATES_PER_S" not in source

    # An unrecognized legacy kwarg (e.g. a stale caller still on old code)
    # must be silently ignored by Process's parameter merging, never
    # resurrect a rate-override code path.
    legacy_caller_process = KarrDNADamageProcess({"kind_rates_per_s": {"uv_like": 3.0}})
    assert not hasattr(legacy_caller_process, "kind_rates_per_s")
