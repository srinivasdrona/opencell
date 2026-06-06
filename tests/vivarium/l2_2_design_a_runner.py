from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import kurtosis, ks_2samp, skew


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

import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402


HARNESS_VERSION = "design_a_v1_3"
SUMMARY_SCHEMA_VERSION = "1.3"
SUPPORTED_PROCESSES = frozenset({"Metabolism"})
DEFAULT_BOOTSTRAP_B = 1000


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
        seeds = [int(part.strip()) for part in text.split(",") if part.strip()]
    else:
        count = int(text)
        if count < 0:
            raise ValueError("Seed count must be non-negative.")
        seeds = list(range(count))
    if not seeds:
        raise ValueError("Seed spec resolved to an empty list.")
    return seeds


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"Unsupported JSON value: {type(value)!r}")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _git_sha() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode == 0:
            return completed.stdout.strip()
        return "unknown"
    except Exception:
        return "unknown"


def _normalize_seed_axis(arr: np.ndarray, seeds: list[int], m_ticks: int) -> np.ndarray:
    arr = np.asarray(arr, dtype=np.float64)
    if arr.ndim == 2:
        arr = arr[np.newaxis, :, :]
    if arr.ndim != 3:
        raise ValueError(f"Expected oracle tensor with shape (seed, tick, dim); got {arr.shape}")
    if m_ticks > arr.shape[1]:
        raise ValueError(f"Requested {m_ticks} ticks, but oracle only provides {arr.shape[1]}.")
    if arr.shape[0] == 1:
        return np.repeat(arr[:, :m_ticks, :], len(seeds), axis=0)
    if max(seeds) >= arr.shape[0]:
        raise ValueError(
            f"Requested seed index {max(seeds)} but oracle only provides {arr.shape[0]} seed slices."
        )
    return np.stack([arr[int(seed), :m_ticks, :] for seed in seeds], axis=0)


def _observable_stats(values: np.ndarray) -> dict[str, float]:
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    if arr.size == 0:
        return {
            "mean": 0.0,
            "stddev": 0.0,
            "skew": 0.0,
            "kurtosis": 0.0,
            "min": 0.0,
            "max": 0.0,
        }
    return {
        "mean": float(np.mean(arr)),
        "stddev": float(np.std(arr)),
        "skew": float(skew(arr, bias=False)) if arr.size > 2 else 0.0,
        "kurtosis": float(kurtosis(arr, fisher=True, bias=False)) if arr.size > 3 else 0.0,
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
    }


def _bootstrap_ci(
    *,
    oc_vectors: np.ndarray,
    karr_vectors: np.ndarray,
    bootstrap_B: int,
    rng_seed: int,
) -> list[float]:
    n_seeds, n_ticks, _ = oc_vectors.shape
    rng = np.random.default_rng(int(rng_seed))
    values = np.zeros(int(bootstrap_B), dtype=np.float64)
    for idx in range(int(bootstrap_B)):
        oc_idx = rng.integers(0, n_seeds, size=n_seeds)
        karr_idx = rng.integers(0, n_seeds, size=n_seeds)
        per_sample = []
        for lhs_seed, rhs_seed in zip(oc_idx, karr_idx, strict=False):
            for tick in range(n_ticks):
                per_sample.append(
                    runner_helpers.compute_w1(
                        oc_vectors[int(lhs_seed), tick],
                        karr_vectors[int(rhs_seed), tick],
                    )
                )
        values[idx] = float(np.mean(per_sample)) if per_sample else 0.0
    return [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))]


def _channel_verdict(
    *,
    w1_oc_vs_karr: float,
    q95_null: float,
    threshold: float,
    n_nonzero_oc: int,
    n_nonzero_karr: int,
) -> str:
    if n_nonzero_karr >= 30 and n_nonzero_oc == 0:
        return "FAIL"
    if n_nonzero_oc < 30 or n_nonzero_karr < 30:
        return "INSUFFICIENT_SAMPLES"
    if w1_oc_vs_karr <= q95_null:
        return "SEED_NOISE"
    if w1_oc_vs_karr <= threshold:
        return "PASS"
    return "FAIL"


def _process_verdict(channel_verdicts: list[str]) -> str:
    gateable = [verdict for verdict in channel_verdicts if verdict not in {"EVENT_CHANNEL_DEFERRED", "INSUFFICIENT_SAMPLES"}]
    if not gateable:
        return "NO_GATEABLE_CHANNELS"
    if any(verdict == "FAIL" for verdict in gateable):
        return "FAIL"
    return "PASS"


def _warning_strings(
    *,
    oc_vectors: np.ndarray,
    karr_vectors: np.ndarray,
    canonical_seed_count: int,
    requested_seed_count: int,
) -> list[str]:
    warnings: list[str] = []
    if canonical_seed_count == 1 and requested_seed_count > 1:
        warnings.append(
            "KARR_SINGLE_SEED_REUSED: Metabolism.npz contains one canonical Karr seed; requested OC seeds reuse that oracle slice."
        )
    if np.array_equal(oc_vectors, karr_vectors):
        warnings.append(
            "TRIVIAL_RNG_LEAK: OC matched the Karr oracle exactly on every requested sample; review for possible oracle laundering."
        )
    return warnings


def _seed_alignment_warning(*, oc_vectors: np.ndarray, karr_vectors: np.ndarray) -> str | None:
    if oc_vectors.shape[0] < 2 or karr_vectors.shape[0] < 2:
        return None
    observed = float(
        np.mean(
            [
                runner_helpers.compute_w1(oc_vectors[seed, tick], karr_vectors[seed, tick])
                for seed in range(oc_vectors.shape[0])
                for tick in range(oc_vectors.shape[1])
            ]
        )
    )
    best_shift: int | None = None
    best_shift_w1 = observed
    for shift in range(1, karr_vectors.shape[0]):
        shifted = float(
            np.mean(
                [
                    runner_helpers.compute_w1(
                        oc_vectors[seed, tick],
                        karr_vectors[(seed + shift) % karr_vectors.shape[0], tick],
                    )
                    for seed in range(oc_vectors.shape[0])
                    for tick in range(oc_vectors.shape[1])
                ]
            )
        )
        if shifted + 1e-12 < best_shift_w1:
            best_shift = shift
            best_shift_w1 = shifted
    if best_shift is None:
        return None
    return (
        "SEED_ALIGNMENT_MISMATCH: OC outputs align better to a shifted Karr seed index "
        f"(shift=+{best_shift}, observed_w1={observed:.6f}, shifted_w1={best_shift_w1:.6f})."
    )


def _result_payload(
    *,
    process: str,
    seeds: list[int],
    m_ticks: int,
    timestamp: str,
    channel_payload: dict[str, Any],
    verdict: str,
    warnings: list[str],
    bootstrap_B: int,
    allocator_inputs_path: Path,
    provenance_path: Path,
) -> dict[str, Any]:
    return {
        "process": process,
        "verdict": verdict,
        "timestamp": timestamp,
        "harness_version": HARNESS_VERSION,
        "seeds": [int(seed) for seed in seeds],
        "ticks": int(m_ticks),
        "n_observations_per_channel": int(len(seeds) * m_ticks),
        "bootstrap_B": int(bootstrap_B),
        "k_eng": {"TRIVIAL_RNG": runner_helpers.TRIVIAL_RNG_K_ENG},
        "channels": {"substrates": channel_payload},
        "joint_check": None,
        "warnings": warnings,
        "allocator_inputs_ref": str(allocator_inputs_path),
        "provenance_ref": str(provenance_path),
    }


def _summary_payload(
    *,
    process: str,
    timestamp: str,
    verdict: str,
    channel_verdict: str,
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "generated_at": timestamp,
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "harness_version": HARNESS_VERSION,
        "k_eng": {"TRIVIAL_RNG": runner_helpers.TRIVIAL_RNG_K_ENG},
        "processes": {
            process: {
                "verdict": verdict,
                "latest_run": timestamp,
                "n_channels_gated": int(channel_verdict not in {"EVENT_CHANNEL_DEFERRED", "INSUFFICIENT_SAMPLES"}),
                "n_event_deferred": 0,
                "n_insufficient": int(channel_verdict == "INSUFFICIENT_SAMPLES"),
                "joint_verdict": None,
                "n_joint_fail_pairs": 0,
                "warnings": warnings,
            }
        },
        "tally": {
            "PASS": int(verdict == "PASS"),
            "FAIL": int(verdict == "FAIL"),
            "BLOCKED": 0,
            "SKIPPED": 0,
            "NO_GATEABLE_CHANNELS": int(verdict == "NO_GATEABLE_CHANNELS"),
        },
    }


def run_design_a(
    *,
    process: str,
    seeds: list[int],
    m_ticks: int,
    out_dir: Path,
    thresholds_path: Path,
    bootstrap_B: int = DEFAULT_BOOTSTRAP_B,
) -> dict[str, Any]:
    if process not in SUPPORTED_PROCESSES:
        raise ValueError(f"Unsupported process {process!r}; supported={sorted(SUPPORTED_PROCESSES)}")

    oracle = runner_helpers.load_karr_oracle(process)
    before_substrates = _normalize_seed_axis(oracle["before_substrates"], seeds, m_ticks)
    after_substrates = _normalize_seed_axis(oracle["after_substrates"], seeds, m_ticks)
    before_enzymes = _normalize_seed_axis(oracle["before_enzymes"], seeds, m_ticks)
    before_bound = _normalize_seed_axis(oracle["before_bound_enzymes"], seeds, m_ticks)

    sample_process = runner_helpers._metabolism_process(0)
    substrate_wids = list(sample_process._sub_ids)
    enzyme_wids = list(sample_process.enzyme_wids)

    oc_vectors = np.zeros_like(after_substrates, dtype=np.float64)
    per_sample_w1 = np.zeros((len(seeds), m_ticks), dtype=np.float64)
    allocator_inputs: list[dict[str, Any]] = []
    for seed_index, seed in enumerate(seeds):
        for tick in range(m_ticks):
            sample_state = {
                "substrate_wids": substrate_wids,
                "enzyme_wids": enzyme_wids,
                "oracle_before_substrates": before_substrates[seed_index, tick],
                "oracle_after_substrates": after_substrates[seed_index, tick],
                "oracle_before_enzymes": before_enzymes[seed_index, tick],
                "oracle_before_bound_enzymes": before_bound[seed_index, tick],
                "oracle_after_all": after_substrates,
                "oracle_before_all": before_substrates,
            }
            oc_result = runner_helpers.run_oc_tick(int(seed), int(tick), sample_state)
            oc_vectors[seed_index, tick] = np.asarray(oc_result["substrates"], dtype=np.float64)
            per_sample_w1[seed_index, tick] = runner_helpers.compute_w1(
                oc_vectors[seed_index, tick],
                after_substrates[seed_index, tick],
            )
            allocator_inputs.append(
                {
                    "seed": int(seed),
                    "tick": int(tick),
                    "substrates_sum_before": float(np.sum(before_substrates[seed_index, tick])),
                    "substrates_nonzero_before": int(np.count_nonzero(before_substrates[seed_index, tick])),
                    "enzymes_sum_before": float(np.sum(before_enzymes[seed_index, tick])),
                    "bound_enzymes_sum_before": float(np.sum(before_bound[seed_index, tick])),
                }
            )

    null_stats = runner_helpers.compute_null_q95(
        karr_vectors=after_substrates,
        bootstrap_B=int(bootstrap_B),
    )
    w1_oc_vs_karr = float(np.mean(per_sample_w1))
    threshold = max(runner_helpers.ABSOLUTE_FLOOR, runner_helpers.TRIVIAL_RNG_K_ENG * float(null_stats["q95_null"]))
    flat_oc = oc_vectors.reshape(-1)
    flat_karr = after_substrates.reshape(-1)
    ks_stat, ks_pvalue = ks_2samp(flat_oc, flat_karr)
    ci95 = _bootstrap_ci(
        oc_vectors=oc_vectors,
        karr_vectors=after_substrates,
        bootstrap_B=int(bootstrap_B),
        rng_seed=runner_helpers.L2_2_VALIDATION_SEED,
    )

    channel_payload = {
        "verdict": _channel_verdict(
            w1_oc_vs_karr=w1_oc_vs_karr,
            q95_null=float(null_stats["q95_null"]),
            threshold=float(threshold),
            n_nonzero_oc=int(np.count_nonzero(flat_oc)),
            n_nonzero_karr=int(np.count_nonzero(flat_karr)),
        ),
        "w1_oc_vs_karr": w1_oc_vs_karr,
        "w1_oc_vs_karr_ci95": ci95,
        "q95_null": float(null_stats["q95_null"]),
        "threshold": float(threshold),
        "absolute_floor": float(runner_helpers.ABSOLUTE_FLOOR),
        "ks_stat": float(ks_stat),
        "ks_pvalue": float(ks_pvalue),
        "n_nonzero_oc": int(np.count_nonzero(flat_oc)),
        "n_nonzero_karr": int(np.count_nonzero(flat_karr)),
        "samples_oc": _observable_stats(flat_oc),
        "samples_karr": _observable_stats(flat_karr),
        "is_primary": True,
        "is_event_channel": False,
        "aggregation": "per_tick_vector_w1_mean",
        "per_sample_w1_summary": {
            "mean": w1_oc_vs_karr,
            "max": float(np.max(per_sample_w1)),
            "min": float(np.min(per_sample_w1)),
        },
    }
    warnings = _warning_strings(
        oc_vectors=oc_vectors,
        karr_vectors=after_substrates,
        canonical_seed_count=int(oracle.get("canonical_seed_count", after_substrates.shape[0])),
        requested_seed_count=len(seeds),
    )
    seed_alignment_warning = _seed_alignment_warning(
        oc_vectors=oc_vectors,
        karr_vectors=after_substrates,
    )
    if seed_alignment_warning is not None:
        warnings.append(seed_alignment_warning)
    timestamp = datetime.now(UTC).isoformat()
    allocator_inputs_path = out_dir / "allocator_inputs.json"
    provenance_path = out_dir / "provenance.json"
    process_verdict = _process_verdict([channel_payload["verdict"]])
    if seed_alignment_warning is not None and process_verdict == "PASS":
        process_verdict = "FAIL"
    result = _result_payload(
        process=process,
        seeds=seeds,
        m_ticks=m_ticks,
        timestamp=timestamp,
        channel_payload=channel_payload,
        verdict=process_verdict,
        warnings=warnings,
        bootstrap_B=int(bootstrap_B),
        allocator_inputs_path=allocator_inputs_path,
        provenance_path=provenance_path,
    )
    summary = _summary_payload(
        process=process,
        timestamp=timestamp,
        verdict=result["verdict"],
        channel_verdict=channel_payload["verdict"],
        warnings=warnings,
    )

    thresholds_payload = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "harness_version": HARNESS_VERSION,
        "process": process,
        "bucket": "TRIVIAL_RNG",
        "channels": {
            "substrates": {
                "q95_null": float(null_stats["q95_null"]),
                "k_eng": runner_helpers.TRIVIAL_RNG_K_ENG,
                "absolute_floor": runner_helpers.ABSOLUTE_FLOOR,
                "threshold": float(threshold),
            }
        },
    }
    input_manifest = {
        "generated_at": timestamp,
        "inputs": [
            {"path": str(runner_helpers._METABOLISM_ORACLE_PATH), "sha256": _sha256_file(runner_helpers._METABOLISM_ORACLE_PATH)},
            {
                "path": str(runner_helpers._METABOLISM_ORACLE_PATH.with_suffix(".json")),
                "sha256": _sha256_file(runner_helpers._METABOLISM_ORACLE_PATH.with_suffix(".json")),
            },
            {"path": str(Path(__file__).resolve()), "sha256": _sha256_file(Path(__file__).resolve())},
            {
                "path": str((_HELPER_DIR / "_l2_2_design_a_runner_helpers.py").resolve()),
                "sha256": _sha256_file((_HELPER_DIR / "_l2_2_design_a_runner_helpers.py").resolve()),
            },
        ],
        "resolved_seeds": [int(seed) for seed in seeds],
        "m_ticks": int(m_ticks),
    }
    null_payload = {
        "generated_at": timestamp,
        "process": process,
        "channel": "substrates",
        "bootstrap_B": int(null_stats["bootstrap_B"]),
        "n_karr_seeds": int(null_stats["n_karr_seeds"]),
        "n_ticks": int(null_stats["n_ticks"]),
        "q95_null": float(null_stats["q95_null"]),
        "bootstrap_values_summary": {
            "mean": float(np.mean(null_stats["bootstrap_values"])),
            "stddev": float(np.std(null_stats["bootstrap_values"])),
            "min": float(np.min(null_stats["bootstrap_values"])),
            "max": float(np.max(null_stats["bootstrap_values"])),
        },
        "warnings": warnings,
    }
    analytical_check = {
        "applicable": False,
        "reason": "Metabolism has no closed-form per-tick check",
    }
    provenance = {
        "generated_at": timestamp,
        "git_sha": _git_sha(),
        "python_version": sys.version,
        "platform": platform.platform(),
        "oracle_path": str(oracle["oracle_path"]),
        "harness_version": HARNESS_VERSION,
    }

    _write_json(out_dir / "result.json", result)
    _write_json(out_dir / "SUMMARY.json", summary)
    _write_json(allocator_inputs_path, {"records": allocator_inputs})
    _write_json(thresholds_path, thresholds_payload)
    _write_json(out_dir / "input_manifest.json", input_manifest)
    _write_json(out_dir / "null_calibration.json", null_payload)
    _write_json(out_dir / "analytical_check.json", analytical_check)
    _write_json(provenance_path, provenance)
    return {
        "result": result,
        "summary": summary,
        "null_calibration": null_payload,
        "thresholds": thresholds_payload,
    }


def _exit_code(verdict: str) -> int:
    if verdict == "FAIL":
        return 1
    if verdict == "NO_GATEABLE_CHANNELS":
        return 4
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        payload = run_design_a(
            process=args.process,
            seeds=_parse_seed_spec(args.seeds),
            m_ticks=int(args.m_ticks),
            out_dir=Path(args.out),
            thresholds_path=Path(args.thresholds),
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"HARNESS_ERROR: {exc}", file=sys.stderr)
        return 3

    result = payload["result"]
    print(
        f"{result['process']} {result['verdict']} "
        f"substrates={result['channels']['substrates']['verdict']} "
        f"w1={result['channels']['substrates']['w1_oc_vs_karr']:.6f}"
    )
    return _exit_code(str(result["verdict"]))


if __name__ == "__main__":
    raise SystemExit(main())
