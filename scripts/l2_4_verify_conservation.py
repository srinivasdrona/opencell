"""L2.4 chassis conservation gate, Batch 1 / Part A.

Part A proves flat-per-WID store-attribution conservation on the uncapped v6
chassis: for every non-exchange substrate WID, every tick, every seed,
`after - before - proc_delta == 0` in integer arithmetic.

Batch 2 will bolt its Part B integrity checks onto the small helper seams in
this module (`evaluate_tick_part_a`, `run_seed_horizon`, `summarize_gate_runs`).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import sys
from collections import defaultdict
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.engine import Engine

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from opencell.m1.karr_metabolism_writeback import KarrWritebackFixture
from opencell.vivarium.karr_composite import build_karr_chassis_v6

DEFAULT_FIXTURE_PATH = ROOT / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
DEFAULT_OUT_DIR = ROOT / "tmp" / "l2_4_partA"
DEFAULT_TICKS = 100
DEFAULT_SEEDS = (0, 1, 2, 3)
INTEGER_TOL = 1e-9
TOP_FAILURE_ROWS = 25
PASS = "PASS"
CONSERVATION_FAIL = "CONSERVATION_FAIL"
PARTB_FAIL = "PARTB_FAIL"
STABILITY_FAIL = "STABILITY_FAIL"

try:
    from scripts.run_chassis_v6_32400t import _collect_leaf_updaters
    from scripts.run_chassis_v6_32400t import _iter_numeric_leaf_writes
    from scripts.run_chassis_v6_32400t import _nested_get
    from scripts.run_chassis_v6_32400t import _snapshot_runtime_state
    from scripts.run_chassis_v6_32400t import _to_float
    from scripts.run_chassis_v6_32400t import _topology_path_tuple
except Exception:
    # Minimal fallback copied from scripts/run_chassis_v6_32400t.py:
    # _to_float/_snapshot_runtime_state/_collect_leaf_updaters/
    # _topology_path_tuple/_iter_numeric_leaf_writes/_nested_get
    # (source lines 57-147 on 2026-07-19).
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)


    def _get_store_dict(engine: Engine, path: tuple[str, ...]) -> dict[str, Any]:
        store = engine.state.get_path(path)
        value = store.get_value() if store is not None else {}
        return value if isinstance(value, dict) else {}


    def _snapshot_runtime_state(engine: Engine) -> dict[str, Any]:
        return {
            "substrates": _get_store_dict(engine, ("substrates",)),
            "rna": _get_store_dict(engine, ("rna",)),
            "protein": _get_store_dict(engine, ("protein",)),
            "chromosome": _get_store_dict(engine, ("chromosome",)),
            "cell": _get_store_dict(engine, ("cell",)),
            "phenotype_observables": _get_store_dict(engine, ("phenotype_observables",)),
        }


    def _collect_leaf_updaters(node: Any) -> dict[str, str]:
        out: dict[str, str] = {}
        if not isinstance(node, dict):
            return out
        for key, value in node.items():
            if not isinstance(value, dict):
                continue
            if "_updater" in value:
                out[str(key)] = str(value["_updater"])
            else:
                out.update(_collect_leaf_updaters(value))
        return out


    def _topology_path_tuple(path: Any) -> tuple[str, ...]:
        if isinstance(path, (tuple, list)):
            return tuple(str(part) for part in path)
        return ()


    def _iter_numeric_leaf_writes(
        node: Any, prefix: tuple[str, ...] = ()
    ) -> list[tuple[tuple[str, ...], float]]:
        if isinstance(node, dict):
            out: list[tuple[tuple[str, ...], float]] = []
            for key, value in node.items():
                out.extend(_iter_numeric_leaf_writes(value, prefix + (str(key),)))
            return out
        if prefix and isinstance(node, (int, float, np.number)):
            return [(prefix, float(node))]
        return []


    def _nested_get(mapping: Any, path: tuple[str, ...], default: Any = 0.0) -> Any:
        current = mapping
        for key in path:
            if not isinstance(current, dict):
                return default
            if key in current:
                current = current[key]
                continue
            if key.lstrip("-").isdigit():
                int_key = int(key)
                if int_key in current:
                    current = current[int_key]
                    continue
            return default
        return current


@dataclass(frozen=True)
class TickFailure:
    seed: int
    tick: int
    wid: str
    failure_kind: str
    field: str
    observed_value: float
    rounded_value: int | None
    unattributed: int | None
    magnitude: float
    gate_part: str = "A"
    process_name: str | None = None
    consumed: int | None = None
    allocated: int | None = None


@dataclass(frozen=True)
class TickOutcome:
    seed: int
    tick: int
    exchange_wids_skipped: int
    max_abs_unattributed: int
    failures: tuple[TickFailure, ...]


@dataclass(frozen=True)
class SeedRunResult:
    seed: int
    ticks_requested: int
    ticks_completed: int
    horizon_completed: bool
    exchange_wids_skipped: int
    max_abs_unattributed: int
    failures: tuple[TickFailure, ...]


@dataclass(frozen=True)
class StabilityErrorInfo:
    seed: int
    tick: int
    exception_type: str
    message: str


@dataclass(frozen=True)
class GateSummary:
    verdict: str
    requested_ticks: int
    seeds: tuple[int, ...]
    exchange_wid_count: int
    exchange_wid_source: str
    per_seed: tuple[SeedRunResult, ...]
    total_failures: int
    part_a_failures: int
    part_b_failures: int
    max_abs_unattributed: int
    top_failures: tuple[TickFailure, ...]
    stability_failure: StabilityErrorInfo | None


class SeedStabilityError(RuntimeError):
    def __init__(self, seed: int, tick: int, exc: Exception):
        self.seed = int(seed)
        self.tick = int(tick)
        self.original_exception = exc
        super().__init__(f"seed={seed} tick={tick}: {exc.__class__.__name__}: {exc}")


class ConservationCollector:
    """Per-process substrate delta accounting lifted from the v6 prototype."""

    def __init__(self, *, composite: Any, seed: int):
        self._composite = composite
        self._current_tick = {"tick": 0}
        self.per_tick_process_sums: dict[str, float] = defaultdict(float)
        self.per_tick_process_wid_deltas: dict[str, dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        self._entities: dict[str, Any] = {}
        self._entities.update(getattr(composite, "processes", {}))
        self._entities.update(getattr(composite, "steps", {}))
        self._seed_entities(seed=seed)
        self._patch_entities()

    def set_tick(self, tick: int) -> None:
        self._current_tick["tick"] = int(tick)
        self.per_tick_process_sums.clear()
        self.per_tick_process_wid_deltas.clear()

    def _seed_entities(self, *, seed: int) -> None:
        names = sorted(self._entities.keys())
        children = np.random.SeedSequence(int(seed)).spawn(len(names))
        for idx, name in enumerate(names):
            entity = self._entities[name]
            child = children[idx]
            entity_seed = int(child.generate_state(1, dtype=np.uint32)[0])
            params = getattr(entity, "parameters", None)
            if isinstance(params, dict) and "rng_seed" in params:
                params["rng_seed"] = entity_seed
            if hasattr(entity, "_rng"):
                entity._rng = np.random.default_rng(entity_seed)

    def _patch_entities(self) -> None:
        for entity_name, entity_obj in self._entities.items():
            topology_entry = self._composite.topology.get(entity_name, {})
            shared_ports: dict[str, tuple[str, ...]] = {}
            if isinstance(topology_entry, dict):
                for port_name, store_path in topology_entry.items():
                    path_tuple = _topology_path_tuple(store_path)
                    if path_tuple:
                        shared_ports[str(port_name)] = path_tuple

            port_updaters: dict[str, dict[str, str]] = {}
            try:
                schema = entity_obj.ports_schema()
                if isinstance(schema, dict):
                    for port_name in schema:
                        port_updaters[str(port_name)] = _collect_leaf_updaters(schema.get(port_name, {}))
            except Exception:
                port_updaters = {}
            original_next_update = entity_obj.next_update

            def wrapped_next_update(
                timestep: float,
                states: dict[str, Any],
                *,
                _entity_name: str = entity_name,
                _original: Any = original_next_update,
                _shared_ports: dict[str, tuple[str, ...]] = shared_ports,
                _port_updaters: dict[str, dict[str, str]] = port_updaters,
            ) -> dict[str, Any]:
                update = _original(timestep, states)
                if update is None:
                    update = {}
                if not (isinstance(update, dict) and _shared_ports):
                    return update

                for port_name, port_update in update.items():
                    port_name_str = str(port_name)
                    store_path = _shared_ports.get(port_name_str)
                    if store_path is None or not isinstance(port_update, dict):
                        continue

                    current_port_state: dict[str, Any] = {}
                    if isinstance(states, dict):
                        raw_port_state = states.get(port_name_str, {})
                        if isinstance(raw_port_state, dict):
                            current_port_state = raw_port_state
                    updaters = _port_updaters.get(port_name_str, {})

                    for key_path, raw in _iter_numeric_leaf_writes(port_update):
                        wid_str = key_path[-1]
                        updater = updaters.get(wid_str, "accumulate")
                        if updater == "set":
                            baseline = _to_float(
                                _nested_get(current_port_state, key_path, default=0.0),
                                default=0.0,
                            )
                            delta = raw - baseline
                        else:
                            delta = raw
                        if delta == 0.0:
                            continue
                        if store_path and store_path[0] == "substrates":
                            self.per_tick_process_sums[wid_str] += float(delta)
                            self.per_tick_process_wid_deltas[_entity_name][wid_str] += float(delta)
                return update

            entity_obj.next_update = wrapped_next_update


def _parse_seeds(raw: str) -> tuple[int, ...]:
    seeds = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    if not seeds:
        raise ValueError("seed list resolved empty")
    return seeds


def _snapshot_store_dict(engine: Engine, path: tuple[str, ...]) -> dict[str, Any]:
    store = engine.state.get_path(path)
    value = store.get_value() if store is not None else {}
    return value if isinstance(value, dict) else {}


def _snapshot_substrates(engine: Engine) -> dict[str, float]:
    substrates = _snapshot_store_dict(engine, ("substrates",))
    out: dict[str, float] = {}
    if isinstance(substrates, dict):
        for wid, value in substrates.items():
            out[str(wid)] = _to_float(value, default=0.0)
    return out


def _snapshot_substrates_allocated(engine: Engine) -> dict[str, dict[str, float]]:
    allocations = _snapshot_store_dict(engine, ("substrates_allocated",))
    out: dict[str, dict[str, float]] = {}
    for process_name, wid_allocations in allocations.items():
        if not isinstance(wid_allocations, dict):
            continue
        out[str(process_name)] = {
            str(wid): _to_float(value, default=0.0) for wid, value in wid_allocations.items()
        }
    return out


def load_exchange_wids(
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
) -> tuple[frozenset[str], str]:
    mat = loadmat(str(fixture_path), squeeze_me=True, struct_as_record=False)
    fixture = mat["data"].fixture
    substrate_wids = [
        str(item) for item in np.asarray(fixture.substrateWholeCellModelIDs, dtype=object).reshape(-1)
    ]
    writeback = KarrWritebackFixture.from_mat(fixture_path)
    exchange_wids = frozenset(
        substrate_wids[int(idx)]
        for idx in np.asarray(writeback.sub_idx_external, dtype=np.int64).reshape(-1)
        if 0 <= int(idx) < len(substrate_wids)
    )
    if not exchange_wids:
        raise RuntimeError(f"exchange-WID fixture resolved zero WIDs from {fixture_path}")
    return (
        exchange_wids,
        "data/karr_fixtures/per_process/Metabolism_flat.mat via "
        "Metabolism.substrateIndexs_externalExchangedMetabolites / "
        "KarrWritebackFixture.sub_idx_external",
    )


def _integer_or_failure(
    *,
    seed: int,
    tick: int,
    wid: str,
    field: str,
    value: float,
) -> tuple[int | None, TickFailure | None]:
    if not math.isfinite(value):
        return None, TickFailure(
            seed=seed,
            tick=tick,
            wid=wid,
            failure_kind="non_finite",
            field=field,
            observed_value=float(value),
            rounded_value=None,
            unattributed=None,
            magnitude=float("inf"),
        )
    rounded = int(round(value))
    if abs(value - rounded) > INTEGER_TOL:
        return None, TickFailure(
            seed=seed,
            tick=tick,
            wid=wid,
            failure_kind="fractional",
            field=field,
            observed_value=float(value),
            rounded_value=rounded,
            unattributed=None,
            magnitude=abs(value - rounded),
        )
    return rounded, None


def _part_b_context(
    failure: TickFailure,
    *,
    process_name: str | None = None,
    consumed: int | None = None,
    allocated: int | None = None,
) -> TickFailure:
    return replace(
        failure,
        gate_part="B",
        process_name=process_name,
        consumed=consumed,
        allocated=allocated,
    )


def evaluate_tick_part_a(
    *,
    seed: int,
    tick: int,
    before: dict[str, float],
    after: dict[str, float],
    proc_delta: dict[str, float],
    exchange_wids: frozenset[str],
) -> TickOutcome:
    failures: list[TickFailure] = []
    max_abs_unattributed = 0
    exchange_wids_skipped = 0
    all_substrates = set(before) | set(after) | set(proc_delta)

    for wid in sorted(all_substrates):
        if wid in exchange_wids:
            exchange_wids_skipped += 1
            continue

        before_int, before_failure = _integer_or_failure(
            seed=seed,
            tick=tick,
            wid=wid,
            field="before",
            value=_to_float(before.get(wid, 0.0), default=0.0),
        )
        if before_failure is not None:
            failures.append(before_failure)
        after_int, after_failure = _integer_or_failure(
            seed=seed,
            tick=tick,
            wid=wid,
            field="after",
            value=_to_float(after.get(wid, 0.0), default=0.0),
        )
        if after_failure is not None:
            failures.append(after_failure)
        proc_int, proc_failure = _integer_or_failure(
            seed=seed,
            tick=tick,
            wid=wid,
            field="proc_delta",
            value=_to_float(proc_delta.get(wid, 0.0), default=0.0),
        )
        if proc_failure is not None:
            failures.append(proc_failure)

        if before_int is None or after_int is None or proc_int is None:
            continue

        unattributed = after_int - before_int - proc_int
        max_abs_unattributed = max(max_abs_unattributed, abs(unattributed))
        if unattributed != 0:
            failures.append(
                TickFailure(
                    seed=seed,
                    tick=tick,
                    wid=wid,
                    failure_kind="unattributed",
                    field="residual",
                    observed_value=float(unattributed),
                    rounded_value=unattributed,
                    unattributed=unattributed,
                    magnitude=float(abs(unattributed)),
                )
            )

    return TickOutcome(
        seed=seed,
        tick=tick,
        exchange_wids_skipped=exchange_wids_skipped,
        max_abs_unattributed=max_abs_unattributed,
        failures=tuple(failures),
    )


def evaluate_tick_part_b(
    *,
    seed: int,
    tick: int,
    after: dict[str, float],
    proc_deltas: dict[str, dict[str, float]],
    substrates_allocated: dict[str, dict[str, float]],
) -> TickOutcome:
    failures: list[TickFailure] = []

    for process_name in sorted(substrates_allocated):
        allocated_by_wid = substrates_allocated.get(process_name, {})
        if not isinstance(allocated_by_wid, dict):
            continue
        process_deltas = proc_deltas.get(process_name, {})
        if not isinstance(process_deltas, dict):
            process_deltas = {}

        for wid in sorted(allocated_by_wid):
            allocated_int, allocated_failure = _integer_or_failure(
                seed=seed,
                tick=tick,
                wid=wid,
                field="allocated",
                value=_to_float(allocated_by_wid.get(wid, 0.0), default=0.0),
            )
            if allocated_failure is not None:
                failures.append(
                    _part_b_context(
                        allocated_failure,
                        process_name=process_name,
                    )
                )

            consumed_value = max(0.0, -_to_float(process_deltas.get(wid, 0.0), default=0.0))
            consumed_int, consumed_failure = _integer_or_failure(
                seed=seed,
                tick=tick,
                wid=wid,
                field="consumed",
                value=consumed_value,
            )
            if consumed_failure is not None:
                failures.append(
                    _part_b_context(
                        consumed_failure,
                        process_name=process_name,
                    )
                )

            if allocated_int is None or consumed_int is None:
                continue

            if consumed_int > allocated_int:
                failures.append(
                    TickFailure(
                        seed=seed,
                        tick=tick,
                        wid=wid,
                        failure_kind="over_allocation",
                        field="consumed_vs_allocated",
                        observed_value=float(consumed_int),
                        rounded_value=consumed_int,
                        unattributed=None,
                        magnitude=float(consumed_int - allocated_int),
                        gate_part="B",
                        process_name=process_name,
                        consumed=consumed_int,
                        allocated=allocated_int,
                    )
                )

    for wid in sorted(after):
        after_int, after_failure = _integer_or_failure(
            seed=seed,
            tick=tick,
            wid=wid,
            field="after",
            value=_to_float(after.get(wid, 0.0), default=0.0),
        )
        if after_failure is not None:
            failures.append(_part_b_context(after_failure))
            continue
        if after_int is not None and after_int < 0:
            failures.append(
                TickFailure(
                    seed=seed,
                    tick=tick,
                    wid=wid,
                    failure_kind="negative_pool",
                    field="after",
                    observed_value=float(after_int),
                    rounded_value=after_int,
                    unattributed=None,
                    magnitude=float(abs(after_int)),
                    gate_part="B",
                )
            )

    return TickOutcome(
        seed=seed,
        tick=tick,
        exchange_wids_skipped=0,
        max_abs_unattributed=0,
        failures=tuple(failures),
    )


def run_seed_horizon(
    *,
    seed: int,
    ticks: int,
    exchange_wids: frozenset[str],
    time_step_s: float,
) -> SeedRunResult:
    composite = build_karr_chassis_v6(
        time_step_s=float(time_step_s),
        emit_step_s=float(ticks),
        enable_pool_replenishment=False,
    )
    collector = ConservationCollector(composite=composite, seed=seed)
    engine = Engine(composite=composite, emit_step=float(ticks), display_info=False)

    failures: list[TickFailure] = []
    ticks_completed = 0
    exchange_wids_skipped = 0
    max_abs_unattributed = 0

    for tick in range(1, ticks + 1):
        collector.set_tick(tick)
        before = _snapshot_substrates(engine)
        # Allocation of record for THIS tick is the value present BEFORE the
        # update — processes read substrates_allocated during their next_update.
        # Snapshotting it AFTER engine.update() captures the allocator's freshly
        # computed allocation for the NEXT tick (off-by-one) and spuriously
        # reports over_allocation once the pool depletes.
        substrates_allocated = _snapshot_substrates_allocated(engine)
        try:
            engine.update(float(time_step_s))
        except Exception as exc:
            raise SeedStabilityError(seed=seed, tick=tick, exc=exc) from exc
        after = _snapshot_substrates(engine)
        per_process_wid_deltas = {
            process_name: dict(wid_deltas)
            for process_name, wid_deltas in collector.per_tick_process_wid_deltas.items()
        }
        outcome = evaluate_tick_part_a(
            seed=seed,
            tick=tick,
            before=before,
            after=after,
            proc_delta=dict(collector.per_tick_process_sums),
            exchange_wids=exchange_wids,
        )
        part_b_outcome = evaluate_tick_part_b(
            seed=seed,
            tick=tick,
            after=after,
            proc_deltas=per_process_wid_deltas,
            substrates_allocated=substrates_allocated,
        )
        failures.extend(outcome.failures)
        failures.extend(part_b_outcome.failures)
        ticks_completed = tick
        exchange_wids_skipped += outcome.exchange_wids_skipped
        max_abs_unattributed = max(max_abs_unattributed, outcome.max_abs_unattributed)

    return SeedRunResult(
        seed=seed,
        ticks_requested=ticks,
        ticks_completed=ticks_completed,
        horizon_completed=(ticks_completed == ticks),
        exchange_wids_skipped=exchange_wids_skipped,
        max_abs_unattributed=max_abs_unattributed,
        failures=tuple(failures),
    )


def summarize_gate_runs(
    *,
    requested_ticks: int,
    seeds: tuple[int, ...],
    exchange_wids: frozenset[str],
    exchange_wid_source: str,
    per_seed: tuple[SeedRunResult, ...],
    stability_failure: StabilityErrorInfo | None = None,
) -> GateSummary:
    all_failures = [failure for seed_result in per_seed for failure in seed_result.failures]
    part_a_failures = sum(1 for failure in all_failures if failure.gate_part == "A")
    part_b_failures = sum(1 for failure in all_failures if failure.gate_part == "B")
    top_failures = tuple(
        sorted(
            all_failures,
            key=lambda item: (
                -item.magnitude,
                item.seed,
                item.tick,
                item.wid,
                item.failure_kind,
                item.field,
                item.gate_part,
                item.process_name or "",
            ),
        )[:TOP_FAILURE_ROWS]
    )
    max_abs_unattributed = max(
        [seed_result.max_abs_unattributed for seed_result in per_seed],
        default=0,
    )
    if stability_failure is not None:
        verdict = STABILITY_FAIL
    elif part_a_failures:
        verdict = CONSERVATION_FAIL
    elif part_b_failures:
        verdict = PARTB_FAIL
    else:
        verdict = PASS
    return GateSummary(
        verdict=verdict,
        requested_ticks=requested_ticks,
        seeds=seeds,
        exchange_wid_count=len(exchange_wids),
        exchange_wid_source=exchange_wid_source,
        per_seed=per_seed,
        total_failures=len(all_failures),
        part_a_failures=part_a_failures,
        part_b_failures=part_b_failures,
        max_abs_unattributed=max_abs_unattributed,
        top_failures=top_failures,
        stability_failure=stability_failure,
    )


def write_report(summary: GateSummary, *, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "summary.json"
    failures_path = out_dir / "top_failures.csv"

    payload = asdict(summary)
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    with failures_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "seed",
                "tick",
                "wid",
                "gate_part",
                "process_name",
                "failure_kind",
                "field",
                "observed_value",
                "rounded_value",
                "unattributed",
                "consumed",
                "allocated",
                "magnitude",
            ]
        )
        for failure in summary.top_failures:
            writer.writerow(
                [
                    failure.seed,
                    failure.tick,
                    failure.wid,
                    failure.gate_part,
                    "" if failure.process_name is None else failure.process_name,
                    failure.failure_kind,
                    failure.field,
                    f"{failure.observed_value:.12g}" if math.isfinite(failure.observed_value) else str(failure.observed_value),
                    "" if failure.rounded_value is None else failure.rounded_value,
                    "" if failure.unattributed is None else failure.unattributed,
                    "" if failure.consumed is None else failure.consumed,
                    "" if failure.allocated is None else failure.allocated,
                    f"{failure.magnitude:.12g}" if math.isfinite(failure.magnitude) else str(failure.magnitude),
                ]
            )


def run_part_a_gate(
    *,
    ticks: int = DEFAULT_TICKS,
    seeds: tuple[int, ...] = DEFAULT_SEEDS,
    out_dir: Path = DEFAULT_OUT_DIR,
    fresh: bool = False,
) -> GateSummary:
    out_dir = Path(out_dir)
    if fresh and out_dir.exists():
        shutil.rmtree(out_dir)

    exchange_wids, exchange_wid_source = load_exchange_wids()
    probe = build_karr_chassis_v6(enable_pool_replenishment=False)
    time_step_s = float(
        getattr(probe.processes.get("karr_metabolism"), "parameters", {}).get("time_step", 1.0)
    )

    completed: list[SeedRunResult] = []
    try:
        for seed in seeds:
            completed.append(
                run_seed_horizon(
                    seed=seed,
                    ticks=ticks,
                    exchange_wids=exchange_wids,
                    time_step_s=time_step_s,
                )
            )
    except SeedStabilityError as exc:
        summary = summarize_gate_runs(
            requested_ticks=ticks,
            seeds=seeds,
            exchange_wids=exchange_wids,
            exchange_wid_source=exchange_wid_source,
            per_seed=tuple(completed),
            stability_failure=StabilityErrorInfo(
                seed=exc.seed,
                tick=exc.tick,
                exception_type=exc.original_exception.__class__.__name__,
                message=str(exc.original_exception),
            ),
        )
        write_report(summary, out_dir=out_dir)
        return summary

    summary = summarize_gate_runs(
        requested_ticks=ticks,
        seeds=seeds,
        exchange_wids=exchange_wids,
        exchange_wid_source=exchange_wid_source,
        per_seed=tuple(completed),
    )
    write_report(summary, out_dir=out_dir)
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticks", type=int, default=DEFAULT_TICKS)
    parser.add_argument("--seeds", type=str, default="0,1,2,3")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--fresh", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    seeds = _parse_seeds(args.seeds)
    summary = run_part_a_gate(
        ticks=int(args.ticks),
        seeds=seeds,
        out_dir=Path(args.out_dir),
        fresh=bool(args.fresh),
    )
    if summary.verdict == STABILITY_FAIL:
        failure = summary.stability_failure
        assert failure is not None
        print(
            f"STABILITY_FAIL seed={failure.seed} tick={failure.tick} "
            f"{failure.exception_type}: {failure.message}",
            flush=True,
        )
        return 2
    if summary.verdict == CONSERVATION_FAIL:
        print(
            f"CONSERVATION_FAIL failures={summary.total_failures} "
            f"part_a_failures={summary.part_a_failures} "
            f"part_b_failures={summary.part_b_failures} "
            f"max_abs_unattributed={summary.max_abs_unattributed}",
            flush=True,
        )
        return 1
    if summary.verdict == PARTB_FAIL:
        print(
            f"PARTB_FAIL failures={summary.total_failures} "
            f"part_b_failures={summary.part_b_failures}",
            flush=True,
        )
        return 1
    print(
        f"PASS seeds={','.join(str(seed) for seed in summary.seeds)} "
        f"ticks={summary.requested_ticks} "
        f"exchange_wids_skipped={summary.exchange_wid_count}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
