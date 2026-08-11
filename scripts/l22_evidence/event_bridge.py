"""Bridge existing L2.event authority into an L2.2 `latest_event/` bundle.

This module is intentionally narrow: it materializes ONE process-local
event-class authority bundle for `RibosomeAssembly` from the already
computed, hash-bound `docs/phase_f/l2_event/evidence_bundle/
RibosomeAssembly/` artifacts. It does not regenerate the shared tracked
`docs/phase_f/l2_2_design_a/evidence_index.json`; the coordinator owns that
final regeneration step.

The bridge keeps the L2.2 authority contract intact:

* writes the full `latest_event/` mandatory file set
  (`result.json`, `input_manifest.json`, `provenance.json`,
  `thresholds.json`, `null_calibration.json`, `SUMMARY.json`,
  `analytical_check.json`, `sweep_provenance.json`)
* never trusts or copies the source bundle's stored process/channel verdict
  strings as authority
* gives `scripts/l22_evidence/generator.py` raw metric fields it can
  mechanically re-derive
* binds staleness to the event-path source files + the upstream event bundle,
  not to the Design-A harness.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_BOOTSTRAP))

from scripts.l22_evidence import catalog as cat  # noqa: E402
from scripts.l22_evidence import schema  # noqa: E402
from scripts.l22_evidence import sweep  # noqa: E402
from scripts.l22_evidence import verdict as vd  # noqa: E402
from scripts.l22_evidence.populate import _git_dirty, _git_sha  # noqa: E402

PROCESS = "RibosomeAssembly"
SOURCE_EVENT_BUNDLE_DIR = (
    cat.REPO_ROOT / "docs" / "phase_f" / "l2_event" / "evidence_bundle" / PROCESS
)
SOURCE_REQUIRED_FILES = (
    "result.json",
    "input_manifest.json",
    "provenance.json",
    "null_calibration.json",
    "SUMMARY.json",
)

BRIDGE_CHANNEL_MAP = {
    "count": "complexs",
    "timing": "timing",
    "payload": "payload",
}
PRIMARY_SOURCE_CHANNEL = "count"


class BridgeError(RuntimeError):
    """Raised when the upstream event bundle cannot be bridged honestly."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BridgeError(f"missing required source file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BridgeError(f"invalid JSON in source file {path}: {exc}") from exc


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return sweep._sha256_file(path) or ""


def _entry() -> cat.ProcessEntry:
    try:
        return cat.in_scope_processes()[PROCESS]
    except KeyError as exc:
        raise BridgeError(f"{PROCESS} is not present in PROCESS_CATALOG.yaml in-scope entries") from exc


def _load_source_bundle(bundle_dir: Path) -> dict[str, dict[str, Any]]:
    missing = [fname for fname in SOURCE_REQUIRED_FILES if not (bundle_dir / fname).is_file()]
    if missing:
        raise BridgeError(f"source event bundle is incomplete at {bundle_dir}: missing {missing}")
    return {fname: _read_json(bundle_dir / fname) for fname in SOURCE_REQUIRED_FILES}


def _source_inputs(
    *,
    bundle_dir: Path,
    source_manifest: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[int], list[int], list[float]]:
    inputs = source_manifest.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise BridgeError("source input_manifest.json has no non-empty 'inputs' list")

    bridge_inputs: list[dict[str, Any]] = []
    seeds: list[int] = []
    n_ticks_values: list[int] = []
    tick_offsets: list[float] = []

    for fname in SOURCE_REQUIRED_FILES:
        source_file = bundle_dir / fname
        bridge_inputs.append(
            {
                "kind": "source_event_bundle",
                "path": cat.relative_to_repo(source_file),
                "sha256": _sha256(source_file),
            }
        )

    for record in inputs:
        path_str = record.get("path")
        sha256 = record.get("sha256")
        seed = record.get("seed")
        n_ticks = record.get("n_ticks")
        tick_offset = record.get("tick_offset")
        if not path_str or not sha256 or seed is None or n_ticks is None:
            raise BridgeError(f"malformed source input_manifest record: {record!r}")
        bridge_inputs.append(
            {
                "kind": "oracle_data",
                "path": str(path_str),
                "sha256": str(sha256),
                "seed": int(seed),
                "n_ticks": int(n_ticks),
                "tick_offset": tick_offset,
                "trace_kind": record.get("trace_kind"),
            }
        )
        seeds.append(int(seed))
        n_ticks_values.append(int(n_ticks))
        if tick_offset is not None:
            tick_offsets.append(float(tick_offset))

    return bridge_inputs, sorted(seeds), sorted(set(n_ticks_values)), sorted(set(tick_offsets))


def _result_channels(source_result: dict[str, Any], entry: cat.ProcessEntry) -> dict[str, dict[str, Any]]:
    channels = source_result.get("channels")
    if not isinstance(channels, list) or not channels:
        raise BridgeError("source result.json has no non-empty 'channels' list")

    bridged: dict[str, dict[str, Any]] = {}
    source_names = {str(channel.get("channel")) for channel in channels}
    if set(BRIDGE_CHANNEL_MAP) - source_names:
        raise BridgeError(
            f"source result.json channel set {sorted(source_names)!r} does not cover "
            f"required {sorted(BRIDGE_CHANNEL_MAP)!r}"
        )

    for source_channel in channels:
        source_name = str(source_channel.get("channel"))
        if source_name not in BRIDGE_CHANNEL_MAP:
            continue
        target_name = BRIDGE_CHANNEL_MAP[source_name]
        statistic_value = source_channel.get("statistic_value")
        threshold = source_channel.get("threshold")
        q95_null = source_channel.get("q95_null")
        n_nonzero_oc = source_channel.get("n_nonzero_oc")
        n_nonzero_karr = source_channel.get("n_nonzero_karr")
        if any(
            value is None for value in (statistic_value, threshold, q95_null, n_nonzero_oc, n_nonzero_karr)
        ):
            raise BridgeError(f"source channel {source_name!r} is missing raw metric field(s)")

        bridged[target_name] = {
            "aggregation": "per_tick_vector_w1_mean",
            "is_primary": source_name == PRIMARY_SOURCE_CHANNEL,
            "is_event_channel": False,
            "w1_oc_vs_karr": statistic_value,
            "threshold": threshold,
            "q95_null": q95_null,
            "n_nonzero_oc": n_nonzero_oc,
            "n_nonzero_karr": n_nonzero_karr,
            "source_event_channel": source_name,
            "source_statistic_name": source_channel.get("statistic_name"),
            "k_eng": source_channel.get("k_eng"),
            "k_eng_provenance": source_channel.get("k_eng_provenance"),
            "standardized_ratio": source_channel.get("standardized_ratio"),
            "extra": source_channel.get("extra", {}),
            "per_component": source_channel.get("per_component", []),
        }

    expected_primary = entry.primary_channel or ""
    if expected_primary not in bridged:
        raise BridgeError(
            f"bridge did not produce catalog primary channel {expected_primary!r}; "
            f"got {sorted(bridged)!r}"
        )
    return bridged


def build_bridge_payloads(
    *,
    source_bundle_dir: Path = SOURCE_EVENT_BUNDLE_DIR,
    entry: cat.ProcessEntry | None = None,
) -> dict[str, dict[str, Any]]:
    if entry is None:
        entry = _entry()
    if entry.harness_type != "event_class":
        raise BridgeError(f"{PROCESS} harness_type is {entry.harness_type!r}, expected 'event_class'")

    source = _load_source_bundle(source_bundle_dir)
    source_result = source["result.json"]
    source_manifest = source["input_manifest.json"]
    source_provenance = source["provenance.json"]
    source_null = source["null_calibration.json"]
    source_summary = source["SUMMARY.json"]

    if str(source_result.get("process")) != PROCESS:
        raise BridgeError(f"source result.json process={source_result.get('process')!r}, expected {PROCESS!r}")
    if str(source_manifest.get("process")) != PROCESS:
        raise BridgeError(
            f"source input_manifest.json process={source_manifest.get('process')!r}, expected {PROCESS!r}"
        )

    inputs, resolved_seeds, source_n_ticks, source_tick_offsets = _source_inputs(
        bundle_dir=source_bundle_dir,
        source_manifest=source_manifest,
    )
    expected_seeds = list(range(entry.n_seeds))
    if resolved_seeds != expected_seeds:
        raise BridgeError(
            f"source bundle seeds {resolved_seeds!r} do not cover expected 0..{entry.n_seeds - 1}"
        )
    channels = _result_channels(source_result, entry)

    bridged_result = {
        "process": PROCESS,
        "seeds": expected_seeds,
        "ticks": entry.m_ticks,
        "channels": channels,
        "warnings": list(source_result.get("warnings", [])),
        "event_bridge": {
            "source_bundle_dir": cat.relative_to_repo(source_bundle_dir),
            "source_adapter_id": source_result.get("adapter_id") or source_provenance.get("adapter_id"),
            "source_event_timing_model": source_result.get("event_timing_model"),
            "source_scope_caveat": source_summary.get("scope_caveat") or source_result.get("scope_caveat"),
            "source_window_n_ticks": source_n_ticks,
            "source_tick_offsets": source_tick_offsets,
            "source_git_sha": source_provenance.get("git_sha"),
        },
    }

    bridged_manifest = {
        "process": PROCESS,
        "resolved_seeds": expected_seeds,
        "m_ticks": entry.m_ticks,
        "inputs": inputs,
        "source_event_window_n_ticks": source_n_ticks,
        "source_event_tick_offsets": source_tick_offsets,
    }

    bridged_provenance = {
        "process": PROCESS,
        "generated_at": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(cat.REPO_ROOT),
        "git_dirty": _git_dirty(cat.REPO_ROOT),
        "bridge_kind": "l2_event_to_l22_latest_event",
        "source_bundle_dir": cat.relative_to_repo(source_bundle_dir),
        "source_bundle_hashes": {fname: _sha256(source_bundle_dir / fname) for fname in SOURCE_REQUIRED_FILES},
        "source_event_provenance": {
            "adapter_id": source_provenance.get("adapter_id"),
            "adapter_module": source_provenance.get("adapter_module"),
            "git_sha": source_provenance.get("git_sha"),
            "registry_sha256": source_provenance.get("registry_sha256"),
            "karr_source": source_provenance.get("karr_source"),
        },
    }

    bridged_thresholds = {
        "process": PROCESS,
        "source_bundle_dir": cat.relative_to_repo(source_bundle_dir),
        "channels": {
            channel_name: {
                "threshold": payload["threshold"],
                "q95_null": payload["q95_null"],
                "statistic_name": payload.get("source_statistic_name"),
                "k_eng": payload.get("k_eng"),
                "source_event_channel": payload.get("source_event_channel"),
            }
            for channel_name, payload in channels.items()
        },
    }

    bridged_null = {
        "process": PROCESS,
        "schema_version": source_null.get("schema_version"),
        "cluster_unit": source_null.get("cluster_unit"),
        "b_resamples": source_null.get("b_resamples"),
        "channels": [
            {
                "channel": BRIDGE_CHANNEL_MAP.get(str(channel.get("channel")), str(channel.get("channel"))),
                "source_event_channel": channel.get("channel"),
                "statistic_name": channel.get("statistic_name"),
                "statistic_value": channel.get("statistic_value"),
                "q95_null": channel.get("q95_null"),
                "k_eng": channel.get("k_eng"),
                "threshold": channel.get("threshold"),
            }
            for channel in source_null.get("channels", [])
            if str(channel.get("channel")) in BRIDGE_CHANNEL_MAP
        ],
    }

    bridged_summary = {
        "process": PROCESS,
        "mode": "l22_event_bridge",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_bundle_dir": cat.relative_to_repo(source_bundle_dir),
        "source_summary_mode": source_summary.get("mode"),
        "source_summary_channels": source_summary.get("channels"),
        "source_summary_reasons": source_summary.get("reasons", []),
        "scope_caveat": source_summary.get("scope_caveat") or source_result.get("scope_caveat"),
        "expected_generator_primary_channel": entry.primary_channel,
    }

    analytical_check = {
        "applicable": False,
        "reason": "event_class bridge carries no L2.2 analytical evaluator; authority is the bridged event-class raw metric set",
    }

    return {
        "result.json": bridged_result,
        "input_manifest.json": bridged_manifest,
        "provenance.json": bridged_provenance,
        "thresholds.json": bridged_thresholds,
        "null_calibration.json": bridged_null,
        "SUMMARY.json": bridged_summary,
        "analytical_check.json": analytical_check,
    }


def _sweep_provenance(output_dir: Path, *, entry: cat.ProcessEntry) -> dict[str, Any]:
    sidecar_hashes = {
        fname: sweep._sha256_file(output_dir / fname)
        for fname in schema.SWEEP_PROVENANCE_SIDECAR_FILES
        if (output_dir / fname).is_file()
    }
    return {
        "schema_version": schema.SWEEP_PROVENANCE_SCHEMA_VERSION,
        "process": entry.name,
        "n_seeds": entry.n_seeds,
        "m_ticks": entry.m_ticks,
        "completion_status": schema.COMPLETION_STATUS_COMPLETE,
        "git_sha": _git_sha(cat.REPO_ROOT),
        "git_dirty": _git_dirty(cat.REPO_ROOT),
        "source_hashes": sweep.current_source_hashes(
            entry.oc_module,
            process=entry.name,
            harness_type=entry.harness_type,
        ),
        "sidecar_hashes": sidecar_hashes,
        "inputs_verified": True,
        "evaluator_schema_version": vd.EVALUATOR_SCHEMA_VERSION,
        "result_schema_version": schema.RESULT_SCHEMA_VERSION,
        "written_at": datetime.now(UTC).isoformat(),
    }


def write_bridge_bundle(
    *,
    output_root: Path = schema.BUNDLE_ROOT,
    source_bundle_dir: Path = SOURCE_EVENT_BUNDLE_DIR,
) -> Path:
    entry = _entry()
    output_dir = output_root / PROCESS / schema.EVENT_CLASS_SUBDIR
    payloads = build_bridge_payloads(source_bundle_dir=source_bundle_dir, entry=entry)
    for fname, payload in payloads.items():
        _write_json(output_dir / fname, payload)
    _write_json(output_dir / schema.SWEEP_PROVENANCE_FILE, _sweep_provenance(output_dir, entry=entry))
    return output_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        default=str(schema.BUNDLE_ROOT),
        help="Root that will receive <Process>/latest_event/ (default: tracked evidence_bundle).",
    )
    parser.add_argument(
        "--source-bundle-dir",
        default=str(SOURCE_EVENT_BUNDLE_DIR),
        help="Source L2.event bundle directory to bridge.",
    )
    args = parser.parse_args(argv)

    output_dir = write_bridge_bundle(
        output_root=Path(args.output_root),
        source_bundle_dir=Path(args.source_bundle_dir),
    )
    print(f"wrote bridged latest_event bundle at {cat.relative_to_repo(output_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
