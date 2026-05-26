#!/usr/bin/env python3
"""Convert canary CSV artifacts into a Phase E.2 phenotype-scorecard fixture."""

from __future__ import annotations

import argparse
import csv
import json
import math
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_REFERENCE_FIXTURE = Path("data/phase_e/v6_trajectory_32400s.pkl")
DEFAULT_SNAPSHOT_STRIDE = 100

_NON_POOL_COLUMNS = {
    "tick",
    "time_s",
    "total_rna_count",
    "total_protein_count",
    "cell_dry_mass_g",
    "cell_total_mass_g",
    "cell_volume_L",
}

_REQUIRED_KEY_COLUMNS = {
    "tick",
    "time_s",
    "ATP",
    "GTP",
    "DATP",
    "DGTP",
    "DCTP",
    "DTTP",
    "dNTP_total",
    "total_rna_count",
    "total_protein_count",
    "cell_dry_mass_g",
}

_REQUIRED_REPLICATION_COLUMNS = {
    "tick",
    "time_s",
    "replication_state",
    "fork_max_abs_bp",
    "replication_complete_flag",
}


@dataclass(frozen=True)
class ReplicationPoint:
    tick: int
    state: str
    fork_max_abs_bp: float
    replication_complete_flag: float


@dataclass(frozen=True)
class HeaderInspection:
    key_substrates: list[str]
    replication_events: list[str]
    conservation: list[str]
    process_traces: dict[str, list[str]]


def _to_float(value: Any, default: float = float("nan")) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _to_int(value: Any, default: int = 0) -> int:
    as_float = _to_float(value, default=float(default))
    if not math.isfinite(as_float):
        return int(default)
    return int(round(as_float))


def _read_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        return next(reader)


def inspect_headers(input_dir: Path) -> HeaderInspection:
    process_traces_dir = input_dir / "process_traces"
    key_header = _read_header(input_dir / "key_substrates.csv")
    repl_header = _read_header(input_dir / "replication_events.csv")
    cons_header = _read_header(input_dir / "conservation.csv")

    process_headers: dict[str, list[str]] = {}
    if process_traces_dir.exists():
        for path in sorted(process_traces_dir.glob("*.csv")):
            name = path.name
            if name in {"karr_transcription.csv", "karr_translation.csv", "karr_replication.csv", "karr_cell_cycle_coordinator.csv"}:
                process_headers[name] = _read_header(path)

    return HeaderInspection(
        key_substrates=key_header,
        replication_events=repl_header,
        conservation=cons_header,
        process_traces=process_headers,
    )


def _validate_headers(headers: HeaderInspection) -> None:
    key_missing = sorted(_REQUIRED_KEY_COLUMNS - set(headers.key_substrates))
    if key_missing:
        raise ValueError(f"key_substrates.csv missing required columns: {key_missing}")

    repl_missing = sorted(_REQUIRED_REPLICATION_COLUMNS - set(headers.replication_events))
    if repl_missing:
        raise ValueError(f"replication_events.csv missing required columns: {repl_missing}")


def _load_key_rows(path: Path) -> dict[int, dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows: dict[int, dict[str, str]] = {}
        for row in reader:
            tick = _to_int(row.get("tick"), default=-1)
            if tick < 0:
                continue
            rows[tick] = {str(k): str(v) for k, v in row.items() if k is not None}
    if not rows:
        raise ValueError(f"No key substrate rows found in {path}")
    return rows


def _load_replication_points(path: Path) -> list[ReplicationPoint]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        points: list[ReplicationPoint] = []
        for row in reader:
            tick = _to_int(row.get("tick"), default=-1)
            if tick < 0:
                continue
            points.append(
                ReplicationPoint(
                    tick=tick,
                    state=str(row.get("replication_state", "idle")).strip().lower(),
                    fork_max_abs_bp=_to_float(row.get("fork_max_abs_bp"), default=0.0),
                    replication_complete_flag=_to_float(row.get("replication_complete_flag"), default=0.0),
                )
            )
    points.sort(key=lambda p: p.tick)
    return points


def _replication_state_code(state: str, complete_flag: float) -> int:
    if complete_flag > 0.0:
        return 3
    normalized = state.strip().lower()
    if normalized in {"complete", "completed"}:
        return 3
    if normalized in {"elongating", "replicating", "active"}:
        return 2
    if normalized in {"initiating", "initiation", "started"}:
        return 1
    return 0


def _build_replication_lookup(points: list[ReplicationPoint], ticks: list[int]) -> dict[int, tuple[int, float]]:
    if not ticks:
        return {}

    max_fork_abs = max((abs(p.fork_max_abs_bp) for p in points), default=0.0)
    idx = 0
    current_state = "idle"
    current_fork_abs = 0.0
    current_complete_flag = 0.0

    lookup: dict[int, tuple[int, float]] = {}
    for tick in ticks:
        while idx < len(points) and points[idx].tick <= tick:
            current_state = points[idx].state
            current_fork_abs = points[idx].fork_max_abs_bp
            current_complete_flag = points[idx].replication_complete_flag
            idx += 1
        code = _replication_state_code(current_state, current_complete_flag)
        fork_norm = (abs(current_fork_abs) / max_fork_abs) if max_fork_abs > 0.0 else 0.0
        lookup[tick] = (code, float(fork_norm))
    return lookup


def _load_division_event(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return raw if isinstance(raw, dict) else {}


def _division_detected(payload: dict[str, Any]) -> bool:
    candidates = (
        payload.get("division_reached"),
        payload.get("division_detected"),
        payload.get("division_occurred"),
    )
    return any(bool(value) for value in candidates)


def _select_snapshot_ticks(available_ticks: list[int], reference_fixture: Path) -> list[int]:
    ordered = sorted(set(int(t) for t in available_ticks))
    if not ordered:
        return []

    reference_ticks: list[int] = []
    if reference_fixture.exists():
        try:
            with reference_fixture.open("rb") as f:
                payload = pickle.load(f)
            raw_snaps = payload.get("snapshots", []) if isinstance(payload, dict) else []
            for snap in raw_snaps:
                if isinstance(snap, dict):
                    tick = _to_int(snap.get("tick"), default=-1)
                    if tick >= 0:
                        reference_ticks.append(tick)
        except Exception:
            reference_ticks = []

    if reference_ticks:
        available_set = set(ordered)
        selected = [tick for tick in reference_ticks if tick in available_set]
    else:
        selected = [tick for tick in ordered if tick % DEFAULT_SNAPSHOT_STRIDE == 0]

    if not selected:
        selected = [ordered[0]]
    if selected[0] != ordered[0]:
        selected.insert(0, ordered[0])
    if selected[-1] != ordered[-1]:
        selected.append(ordered[-1])
    return selected


def _infer_snapshot_stride(snapshot_ticks: list[int]) -> int:
    if len(snapshot_ticks) < 2:
        return DEFAULT_SNAPSHOT_STRIDE
    deltas = [snapshot_ticks[i + 1] - snapshot_ticks[i] for i in range(len(snapshot_ticks) - 1)]
    positive = [d for d in deltas if d > 0]
    return int(min(positive)) if positive else DEFAULT_SNAPSHOT_STRIDE


def _schema_for_payload(payload: dict[str, Any]) -> dict[str, list[str]]:
    snapshots = payload.get("snapshots", [])
    first_snapshot = snapshots[0] if isinstance(snapshots, list) and snapshots else {}
    state = first_snapshot.get("state", {}) if isinstance(first_snapshot, dict) else {}
    return {
        "top_level_keys": sorted(payload.keys()),
        "snapshot_keys": sorted(first_snapshot.keys()) if isinstance(first_snapshot, dict) else [],
        "state_keys": sorted(state.keys()) if isinstance(state, dict) else [],
    }


def load_pickle_schema(path: Path) -> dict[str, list[str]]:
    with path.open("rb") as f:
        payload = pickle.load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected dict payload in {path}")
    return _schema_for_payload(payload)


def build_e2_payload(input_dir: Path, *, reference_fixture: Path = DEFAULT_REFERENCE_FIXTURE) -> dict[str, Any]:
    headers = inspect_headers(input_dir)
    _validate_headers(headers)

    key_rows = _load_key_rows(input_dir / "key_substrates.csv")
    replication_points = _load_replication_points(input_dir / "replication_events.csv")
    division_payload = _load_division_event(input_dir / "division_event.json")

    all_ticks = sorted(key_rows)
    snapshot_ticks = _select_snapshot_ticks(all_ticks, reference_fixture)
    replication_lookup = _build_replication_lookup(replication_points, snapshot_ticks)

    pool_columns = [col for col in headers.key_substrates if col not in _NON_POOL_COLUMNS]

    division_reached = _division_detected(division_payload)
    division_tick = _to_int(division_payload.get("division_tick"), default=-1)
    division_time_s = _to_float(division_payload.get("division_time_s"), default=float("nan"))

    snapshots: list[dict[str, Any]] = []
    for tick in snapshot_ticks:
        row = key_rows[tick]
        rep_code, fork_norm = replication_lookup.get(tick, (0, 0.0))

        division_timestamp_s = float("nan")
        if division_reached and math.isfinite(division_time_s):
            if division_tick < 0 or tick >= division_tick:
                division_timestamp_s = float(division_time_s)

        metabolite_pools: dict[str, float] = {}
        for col in pool_columns:
            value = _to_float(row.get(col), default=float("nan"))
            if math.isfinite(value):
                metabolite_pools[col] = float(value)

        state = {
            "cell_dry_mass_g": _to_float(row.get("cell_dry_mass_g"), default=float("nan")),
            "replication_state_code": int(rep_code),
            "fork_position_norm": float(fork_norm),
            "mrna_total_count_estimate": _to_int(row.get("total_rna_count"), default=0),
            "protein_total_count_estimate": _to_int(row.get("total_protein_count"), default=0),
            "atp_pool": _to_float(row.get("ATP"), default=float("nan")),
            "gtp_pool": _to_float(row.get("GTP"), default=float("nan")),
            "dntp_pool_total": _to_float(row.get("dNTP_total"), default=float("nan")),
            "division_event_timestamp_s": float(division_timestamp_s),
            "cytokinesis_start_tick_s": float("nan"),
            "cytokinesis_complete_tick_s": float("nan"),
            "dna_mass_g": float("nan"),
            "rna_mass_g": float("nan"),
            "protein_mass_g": float("nan"),
            "cell_dry_mass_reference_g": _to_float(row.get("cell_dry_mass_g"), default=float("nan")),
            "metabolite_pools": metabolite_pools,
        }

        snapshots.append(
            {
                "tick": int(tick),
                "time_s": _to_float(row.get("time_s"), default=float(tick)),
                "state": state,
            }
        )

    ticks_completed = int(max(all_ticks))
    wall_time_s = 0.0
    manifest_path = input_dir / "manifest.json"
    if manifest_path.exists():
        try:
            with manifest_path.open("r", encoding="utf-8") as f:
                manifest = json.load(f)
            wall_time_s = _to_float(manifest.get("wall_time_s"), default=0.0)
            if not math.isfinite(wall_time_s):
                wall_time_s = 0.0
        except Exception:
            wall_time_s = 0.0

    payload = {
        "chassis": "v6",
        "schema_version": 1,
        "snapshots": snapshots,
        "wall_time_s": float(wall_time_s),
        "ticks_completed": ticks_completed,
        "division_detected": bool(division_reached),
        "snapshot_stride_ticks": int(_infer_snapshot_stride(snapshot_ticks)),
        "max_ticks_requested": ticks_completed,
    }
    return payload


def write_payload(payload: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as f:
        pickle.dump(payload, f)


def run_cli(input_dir: Path, output_path: Path) -> None:
    payload = build_e2_payload(input_dir)
    write_payload(payload, output_path)

    # Schema self-test against the pre-banked fixture.
    reference_schema = load_pickle_schema(DEFAULT_REFERENCE_FIXTURE)
    output_schema = _schema_for_payload(payload)

    print(f"Reference schema ({DEFAULT_REFERENCE_FIXTURE}):")
    print(f"  top_level_keys={reference_schema['top_level_keys']}")
    print(f"  snapshot_keys={reference_schema['snapshot_keys']}")
    print(f"  state_keys={reference_schema['state_keys']}")
    print(f"Output schema ({output_path}):")
    print(f"  top_level_keys={output_schema['top_level_keys']}")
    print(f"  snapshot_keys={output_schema['snapshot_keys']}")
    print(f"  state_keys={output_schema['state_keys']}")

    print(
        f"Wrote {output_path}: {len(payload['snapshots'])} snapshots, "
        f"ticks_completed={payload['ticks_completed']}, division={payload['division_detected']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv_dir", type=Path)
    parser.add_argument("output_pkl", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_cli(args.input_csv_dir, args.output_pkl)


if __name__ == "__main__":
    main()
