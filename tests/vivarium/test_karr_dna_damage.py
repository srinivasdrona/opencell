from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
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
)


class _FixedPoissonRng:
    def __init__(self, n_events: int) -> None:
        self.n_events = int(n_events)

    def poisson(self, lam: float) -> int:
        _ = lam
        return self.n_events

    def integers(
        self,
        low: int,
        high: int,
        size: int | None = None,
        dtype: type[np.int64] = np.int64,
    ) -> np.ndarray | np.int64:
        _ = high
        if size is None:
            return np.int64(low)
        return np.full(size, low, dtype=dtype)


def _empty_sparse(shape: tuple[int, int]) -> dict[str, object]:
    return SparseTriplet.empty(*shape).to_state()


def _base_state(
    replication_state: str = "idle",
    fork_position_bp: dict[str, int | None] | None = None,
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
            "UVB_radiation": 1.0,
            "gamma_radiation": 1.0,
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


def _trace_total_if_available(process: KarrDNADamageProcess) -> float | None:
    trace_path = Path(process.parameters["trace_path"])
    if not trace_path.exists():
        trace_path = _REPO_ROOT / trace_path
    if not trace_path.exists():
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
    assert all(process.kind_rates_per_s[k] >= 0.0 for k in process.damage_kinds)


def test_one_tick_damage_delta_sign() -> None:
    process = KarrDNADamageProcess(
        {
            "rng_seed": 10,
            "kind_rates_per_s": {
                "uv_like": 2.0,
                "oxidative": 2.0,
                "alkylation": 2.0,
                "depurination": 2.0,
            },
        }
    )
    update = process.next_update(1.0, _base_state())
    new_sites = update.get("chromosome", {}).get("damage_events_cumulative", [])
    assert len(new_sites) > 0
    for site in new_sites:
        assert int(site["position"]) > 0
        assert int(site["position"]) <= process.sequence_length_nt
        assert str(site["kind"]) in set(process.damage_kinds)
        assert int(site["age_ticks"]) == 0


def test_no_substrate_allocation_contract() -> None:
    process = KarrDNADamageProcess({"rng_seed": 1})
    schema = process.ports_schema()
    assert "requests" not in schema
    assert "substrates_allocated" not in schema
    for field in _SPARSE_FIELDS:
        assert field in schema["chromosome"]

    update = process.next_update(1.0, _base_state())
    assert "requests" not in update
    assert "substrates_allocated" not in update


def test_replication_stall_flag_on_fork_hit() -> None:
    process = KarrDNADamageProcess(
        {
            "kind_rates_per_s": {
                "uv_like": 1.0,
                "oxidative": 0.0,
                "alkylation": 0.0,
                "depurination": 0.0,
            },
            "rng_seed": 7,
        }
    )
    process._rng = _FixedPoissonRng(1)  # deterministic one event per active kind
    process._sample_positions = lambda n_events, occupied_positions: np.asarray(  # type: ignore[method-assign]
        [10101], dtype=np.int64
    )
    state = _base_state(
        replication_state="elongating",
        fork_position_bp={"left": 10101, "right": 250000},
    )
    update = process.next_update(1.0, state)
    assert update["chromosome"]["replication_stall_flag"] == 1.0
    assert update["chromosome"]["damage_events_cumulative"][0]["position"] == 10101


def test_sparse_writeback_uses_mapped_chromosome_field() -> None:
    process = KarrDNADamageProcess(
        {
            "kind_rates_per_s": {
                "uv_like": 1.0,
                "oxidative": 0.0,
                "alkylation": 0.0,
                "depurination": 0.0,
            },
            "rng_seed": 3,
        }
    )
    process._rng = _FixedPoissonRng(1)
    process._sample_positions = lambda n_events, occupied_positions: np.asarray([11], dtype=np.int64)  # type: ignore[method-assign]

    update = process.next_update(1.0, _base_state())
    chrom_update = update["chromosome"]
    assert len(chrom_update["damage_events_cumulative"]) == 1
    triplet = SparseTriplet.from_state(
        chrom_update["intrastrandCrossLinks"],
        shape=process.chromosome_shape,
    )
    assert triplet.positions.tolist() == [10]
    assert triplet.values.tolist() == [1]
    assert 0 <= int(triplet.strands[0]) < process.chromosome_shape[1]


def test_sparse_occupied_sites_prevent_reuse_when_unique_enabled() -> None:
    process = KarrDNADamageProcess(
        {
            "kind_rates_per_s": {
                "uv_like": 1.0,
                "oxidative": 0.0,
                "alkylation": 0.0,
                "depurination": 0.0,
            },
            "rng_seed": 5,
            "enforce_unique_positions": True,
        }
    )
    process._rng = _FixedPoissonRng(1)
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


def test_100_tick_total_damage_within_20_percent_of_expectation() -> None:
    template = KarrDNADamageProcess({})
    expected_from_trace = _trace_total_if_available(template)
    expected = (
        float(expected_from_trace)
        if expected_from_trace is not None
        else float(sum(template.kind_rates_per_s.values()) * 100.0)
    )

    totals: list[float] = []
    for seed in range(64):
        process = KarrDNADamageProcess({"rng_seed": seed})
        state = _base_state()
        total = 0.0
        for _ in range(100):
            update = process.next_update(1.0, state)
            total += float(len(update.get("chromosome", {}).get("damage_events_cumulative", [])))
            _apply_update(state, update, process)
        totals.append(total)

    observed = float(np.mean(np.asarray(totals, dtype=np.float64)))
    tolerance = max(1.0, 0.2 * max(1.0, expected))
    assert abs(observed - expected) <= tolerance


def test_no_nan_no_negative_regression() -> None:
    process = KarrDNADamageProcess(
        {
            "rng_seed": 99,
            "kind_rates_per_s": {
                "uv_like": 1.2,
                "oxidative": 0.8,
                "alkylation": 0.4,
                "depurination": 0.5,
            },
        }
    )
    state = _base_state()
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

