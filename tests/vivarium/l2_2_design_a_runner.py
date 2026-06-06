from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np


_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

from _l2_2_design_a_runner_helpers import _METABOLISM_ORACLE_PATH  # noqa: E402


HARNESS_VERSION = "design_a_v1_3"
SUMMARY_SCHEMA_VERSION = "1.3"
SUPPORTED_PROCESSES = frozenset({"Metabolism"})
OUTPUT_CHANNELS: dict[str, tuple[str, ...]] = {"Metabolism": ("substrates",)}


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the L2.2 Design-A replay harness.")
    parser.add_argument("--process", required=True)
    parser.add_argument("--seeds", required=True, help="Integer count or comma-separated explicit seeds.")
    parser.add_argument("--m-ticks", required=True, type=int, help="Number of replay ticks to evaluate.")
    parser.add_argument("--out", required=True, help="Output directory for Design-A artifacts.")
    parser.add_argument("--thresholds", required=True, help="Threshold snapshot output path.")
    return parser.parse_args(argv)


def _parse_seed_spec(spec: str) -> list[int]:
    text = spec.strip()
    if not text:
        raise ValueError("Seed spec must not be empty.")
    if "," in text:
        return [int(part.strip()) for part in text.split(",") if part.strip()]
    count = int(text)
    if count < 0:
        raise ValueError("Seed count must be non-negative.")
    return list(range(count))


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    raise TypeError(f"Unsupported JSON value: {type(value)!r}")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")


def _channel_stub(*, name: str, is_primary: bool) -> dict[str, Any]:
    return {
        "verdict": "NOT_RUN",
        "w1_oc_vs_karr": None,
        "w1_oc_vs_karr_ci95": None,
        "q95_null": None,
        "threshold": None,
        "absolute_floor": None,
        "ks_stat": None,
        "ks_pvalue": None,
        "n_nonzero_oc": 0,
        "n_nonzero_karr": 0,
        "samples_oc": None,
        "samples_karr": None,
        "is_primary": bool(is_primary),
        "is_event_channel": False,
    }


def _stub_result(*, process: str, seeds: list[int], ticks: int, timestamp: str) -> dict[str, Any]:
    channels = {
        name: _channel_stub(name=name, is_primary=(idx == 0))
        for idx, name in enumerate(OUTPUT_CHANNELS[process])
    }
    return {
        "process": process,
        "verdict": "NOT_RUN",
        "timestamp": timestamp,
        "harness_version": HARNESS_VERSION,
        "seeds": seeds,
        "ticks": int(ticks),
        "n_observations_per_channel": int(len(seeds) * ticks),
        "bootstrap_B": None,
        "k_eng": {"TRIVIAL_RNG": 2.0},
        "channels": channels,
        "joint_check": None,
        "warnings": [],
        "allocator_inputs_ref": None,
        "provenance_ref": None,
    }


def _stub_summary(*, process: str, timestamp: str) -> dict[str, Any]:
    return {
        "generated_at": timestamp,
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "harness_version": HARNESS_VERSION,
        "k_eng": {"TRIVIAL_RNG": 2.0},
        "processes": {
            process: {
                "verdict": "NOT_RUN",
                "latest_run": timestamp,
                "n_channels_gated": 0,
                "n_event_deferred": 0,
                "n_insufficient": 0,
                "joint_verdict": None,
                "n_joint_fail_pairs": 0,
                "warnings": [],
            }
        },
        "tally": {"NOT_RUN": 1},
    }


def _write_stub_artifacts(*, process: str, seeds: list[int], ticks: int, out_dir: Path, thresholds_path: Path) -> dict[str, Any]:
    timestamp = datetime.now(UTC).isoformat()
    result = _stub_result(process=process, seeds=seeds, ticks=ticks, timestamp=timestamp)
    summary = _stub_summary(process=process, timestamp=timestamp)

    _write_json(out_dir / "result.json", result)
    _write_json(out_dir / "SUMMARY.json", summary)
    _write_json(
        thresholds_path,
        {
            "schema_version": SUMMARY_SCHEMA_VERSION,
            "process": process,
            "bucket": "TRIVIAL_RNG",
            "k_eng": 2.0,
            "absolute_floor": None,
            "status": "NOT_RUN",
        },
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if args.process not in SUPPORTED_PROCESSES:
        raise ValueError(f"Unsupported process {args.process!r}; supported={sorted(SUPPORTED_PROCESSES)}")

    seeds = _parse_seed_spec(args.seeds)
    out_dir = Path(args.out)
    thresholds_path = Path(args.thresholds)

    if args.process == "Metabolism":
        if not _METABOLISM_ORACLE_PATH.exists():
            raise FileNotFoundError(f"Missing Metabolism oracle fixture: {_METABOLISM_ORACLE_PATH}")
        with np.load(_METABOLISM_ORACLE_PATH, allow_pickle=False):
            pass

    result = _write_stub_artifacts(
        process=args.process,
        seeds=seeds,
        ticks=int(args.m_ticks),
        out_dir=out_dir,
        thresholds_path=thresholds_path,
    )
    print(f"{result['process']} {result['verdict']} seeds={len(seeds)} ticks={result['ticks']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
