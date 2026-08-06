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


def test_no_production_oracle_trace_read_rule_8_regression() -> None:
    """Regression for the Rule 8 violation flagged in review: production
    must never read a per-tick Karr oracle trace (DNADamage_100ticks.mat
    or any other trace) to derive kind_rates_per_s. The prior
    `_load_trace_kind_rates`/`trace_path`/`use_trace_rates_if_available`
    mechanism was silently inert only because scipy.io.loadmat cannot
    parse the v7.3/HDF5 trace format -- a latent violation, not an
    absent one. This test asserts the mechanism has been removed
    entirely, not merely left dormant.
    """
    import inspect

    from opencell.vivarium import karr_dna_damage as module

    process = KarrDNADamageProcess({})

    # No trace-derived parameters/attributes remain on the process.
    assert "trace_path" not in KarrDNADamageProcess.defaults
    assert "use_trace_rates_if_available" not in KarrDNADamageProcess.defaults
    assert not hasattr(process, "trace_kind_rates_per_s")
    assert not hasattr(process, "used_trace_rates")
    assert not hasattr(process, "_load_trace_kind_rates")
    assert not hasattr(module, "_DEFAULT_TRACE_PATH")

    # Source-text scan: no oracle per-tick trace path/filename string
    # remains reachable from production code.
    source = inspect.getsource(module)
    assert "_100ticks" not in source
    assert "per_process_traces" not in source
    assert "DNADamage_100ticks.mat" not in source

    # kind_rates_per_s is always exactly the canonical default, or an
    # explicit caller-supplied override -- passing an unrelated `trace_path`
    # kwarg (e.g. a caller still on old code) must be silently ignored by
    # Process's parameter merging, never trigger a trace read.
    default_process = KarrDNADamageProcess({})
    from opencell.vivarium.karr_dna_damage import _DEFAULT_KIND_RATES_PER_S

    assert default_process.kind_rates_per_s == _DEFAULT_KIND_RATES_PER_S

    override_process = KarrDNADamageProcess({"kind_rates_per_s": {"uv_like": 3.0}})
    assert override_process.kind_rates_per_s["uv_like"] == 3.0
    assert override_process.kind_rates_per_s["oxidative"] == _DEFAULT_KIND_RATES_PER_S["oxidative"]
