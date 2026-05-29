from __future__ import annotations

import importlib
import inspect
import json
import math
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import h5py
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.vivarium.l2_replay_common import (
    build_state_template,
    cell_vector,
    collect_count_delta_dicts,
    infer_wids_for_observable,
    overlay_observable_into_state,
    project_karr_vector,
    refresh_allocator_views,
    resolve_trace_path,
)

TEST_GLOB = "test_karr_*_l2_replay.py"
DOCS_DIR = REPO_ROOT / "docs" / "phase_e"
JSON_OUT = DOCS_DIR / "PATTERN_B_CENSUS.json"
MD_OUT = DOCS_DIR / "PATTERN_B_CENSUS.md"


@dataclass
class DeltaRecord:
    tick: int
    store: str
    wid: str
    delta: float


def _fmt_float(value: float | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, float) and math.isnan(value):
        return "nan"
    return f"{value:.16g}"


def _discover_modules() -> list[str]:
    test_dir = REPO_ROOT / "tests" / "vivarium"
    paths = sorted(test_dir.glob(TEST_GLOB))
    return [f"tests.vivarium.{path.stem}" for path in paths]


def _resolve_process_class(mod: Any) -> type[Any]:
    candidates: list[type[Any]] = []
    for _, obj in vars(mod).items():
        if not inspect.isclass(obj):
            continue
        if not str(getattr(obj, "__name__", "")).endswith("Process"):
            continue
        if not str(getattr(obj, "__module__", "")).startswith("opencell.vivarium"):
            continue
        candidates.append(obj)

    if len(candidates) == 1:
        return candidates[0]

    trace_name = str(getattr(mod, "_TRACE_PROCESS_NAME", "")).lower()
    if trace_name:
        for candidate in candidates:
            if trace_name in candidate.__name__.lower():
                return candidate

    names = ", ".join(c.__name__ for c in candidates) or "<none>"
    raise RuntimeError(
        f"Could not uniquely resolve process class in {mod.__name__}; candidates={names}"
    )


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _process_row(
    *,
    module_name: str,
    process_name: str,
    total_nonintegral_deltas: int | str,
    first: DeltaRecord | None,
    worst: DeltaRecord | None,
    samples: list[DeltaRecord],
    error: str | None,
) -> dict[str, Any]:
    return {
        "module": module_name,
        "process": process_name,
        "total_nonintegral_deltas": total_nonintegral_deltas,
        "first_tick": None if first is None else first.tick,
        "first_store": None if first is None else first.store,
        "first_wid": None if first is None else first.wid,
        "first_delta": None if first is None else first.delta,
        "worst_magnitude": (
            None
            if worst is None
            else {
                "abs_delta": abs(worst.delta),
                "tick": worst.tick,
                "store": worst.store,
                "wid": worst.wid,
                "delta": worst.delta,
            }
        ),
        "sample_nonintegral_deltas": [
            {"tick": s.tick, "store": s.store, "wid": s.wid, "delta": s.delta}
            for s in samples
        ],
        "error": error,
    }


def _run_one(module_name: str) -> dict[str, Any]:
    mod = importlib.import_module(module_name)
    process_name = str(getattr(mod, "_TRACE_PROCESS_NAME", module_name.rsplit(".", 1)[-1]))
    observables = tuple(getattr(mod, "_OBSERVABLES", ()))
    pass_through = set(getattr(mod, "_PASS_THROUGH", ()))
    observable_to_wids_attr = _as_mapping(getattr(mod, "_OBSERVABLE_TO_WIDS_ATTR", {}))
    canonical_wids = _as_mapping(getattr(mod, "_CANONICAL_WIDS", {}))
    store_path_override = _as_mapping(getattr(mod, "_STORE_PATH_OVERRIDE", {}))
    index_projection_attr = _as_mapping(getattr(mod, "_INDEX_PROJECTION_ATTR", {}))
    index_projection_literal = _as_mapping(getattr(mod, "_INDEX_PROJECTION_LITERAL", {}))

    # Keep behavior aligned with L2 replay tests: pass-through observables are still
    # overlaid from states_before to ensure process reads are faithful.
    _ = pass_through

    process_cls = _resolve_process_class(mod)
    process = process_cls({"rng_seed": 0})
    state_template = build_state_template(process)

    trace_path = resolve_trace_path(process_name)
    nonintegral_total = 0
    first_record: DeltaRecord | None = None
    worst_record: DeltaRecord | None = None
    samples: list[DeltaRecord] = []

    with h5py.File(trace_path, "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
        tick_count = min(100, n_ticks)

        wids_by_observable: dict[str, list[str]] = {}
        for observable in observables:
            karr_before = project_karr_vector(
                process,
                observable,
                cell_vector(trace, "states_before", observable, 0),
                index_projection_attr=index_projection_attr,
                index_projection_literal=index_projection_literal,
            )
            explicit_attr = observable_to_wids_attr.get(observable)
            wids_by_observable[observable] = infer_wids_for_observable(
                process,
                state_template,
                observable,
                karr_len=int(karr_before.shape[0]),
                explicit_attr=explicit_attr,
                canonical_wids_override=canonical_wids,
            )

        for tick in range(tick_count):
            state = build_state_template(process)
            before_vectors: dict[str, np.ndarray] = {}
            for observable in observables:
                before_vectors[observable] = project_karr_vector(
                    process,
                    observable,
                    cell_vector(trace, "states_before", observable, tick),
                    index_projection_attr=index_projection_attr,
                    index_projection_literal=index_projection_literal,
                )

            for observable in observables:
                overlay_observable_into_state(
                    process=process,
                    state=state,
                    observable=observable,
                    vector=before_vectors[observable],
                    wids=wids_by_observable[observable],
                    store_path_override=store_path_override,
                )
            refresh_allocator_views(process, state)

            update = process.next_update(1.0, state)
            for store_label, deltas in collect_count_delta_dicts(update):
                for wid, delta in deltas.items():
                    delta_f = float(delta)
                    if abs(delta_f - round(delta_f)) > 0:
                        record = DeltaRecord(tick=tick, store=store_label, wid=str(wid), delta=delta_f)
                        nonintegral_total += 1
                        if first_record is None:
                            first_record = record
                        if worst_record is None or abs(delta_f) > abs(worst_record.delta):
                            worst_record = record
                        if len(samples) < 5:
                            samples.append(record)

    return _process_row(
        module_name=module_name,
        process_name=process_name,
        total_nonintegral_deltas=nonintegral_total,
        first=first_record,
        worst=worst_record,
        samples=samples,
        error=None,
    )


def _row_to_markdown(row: dict[str, Any]) -> str:
    process_name = row["process"]
    if row["error"]:
        return (
            f"| {process_name} | ERROR: {row['error']} | - | - | - | - | - |"
        )

    total = row["total_nonintegral_deltas"]
    first_tick = row["first_tick"] if row["first_tick"] is not None else "-"
    first_wid = row["first_wid"] if row["first_wid"] is not None else "-"
    first_delta = _fmt_float(row["first_delta"])

    worst = row["worst_magnitude"]
    if worst is None:
        worst_text = "-"
    else:
        worst_text = (
            f"{_fmt_float(worst['abs_delta'])} "
            f"(tick={worst['tick']}, store={worst['store']}, wid={worst['wid']}, delta={_fmt_float(worst['delta'])})"
        )

    sample = row["sample_nonintegral_deltas"]
    if not sample:
        sample_text = "-"
    else:
        sample_text = "; ".join(
            f"(tick={item['tick']}, store={item['store']}, wid={item['wid']}, delta={_fmt_float(float(item['delta']))})"
            for item in sample
        )

    return (
        f"| {process_name} | {total} | {first_tick} | {first_wid} | {first_delta} | {worst_text} | {sample_text} |"
    )


def main() -> int:
    started = time.perf_counter()
    modules = _discover_modules()
    rows: list[dict[str, Any]] = []

    for module_name in modules:
        try:
            rows.append(_run_one(module_name))
        except Exception as exc:  # keep census going even if one process fails
            process_guess = module_name.rsplit(".", 1)[-1]
            rows.append(
                _process_row(
                    module_name=module_name,
                    process_name=process_guess,
                    total_nonintegral_deltas=f"ERROR: {exc}",
                    first=None,
                    worst=None,
                    samples=[],
                    error=f"{exc.__class__.__name__}: {exc}",
                )
            )

    rows.sort(key=lambda r: str(r["process"]))
    errored = [r for r in rows if r["error"]]
    nonintegral = [
        r
        for r in rows
        if not r["error"]
        and isinstance(r["total_nonintegral_deltas"], int)
        and int(r["total_nonintegral_deltas"]) > 0
    ]

    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    elapsed_s = time.perf_counter() - started
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "n_modules": len(modules),
        "n_rows": len(rows),
        "summary": {
            "processes_with_nonintegral_deltas": len(nonintegral),
            "processes_without_nonintegral_deltas": len(rows) - len(nonintegral) - len(errored),
            "errored_processes": len(errored),
            "runtime_seconds": elapsed_s,
        },
        "rows": rows,
    }
    JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    md_lines = [
        "# Pattern B Census",
        "",
        f"- Generated (UTC): {payload['generated_at_utc']}",
        f"- Process modules scanned: {len(modules)}",
        f"- Processes with non-integral deltas: {len(nonintegral)}",
        f"- Errored processes: {len(errored)}",
        f"- Runtime (s): {elapsed_s:.3f}",
        "",
        "| Process | total_nonintegral_deltas | first_tick | first_wid | first_delta | worst_magnitude | sample of up to 5 (tick, store, wid, delta) |",
        "|---|---:|---:|---|---:|---|---|",
    ]
    md_lines.extend(_row_to_markdown(row) for row in rows)
    MD_OUT.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"Wrote {JSON_OUT}")
    print(f"Wrote {MD_OUT}")
    print(f"Processed {len(rows)} rows in {elapsed_s:.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
