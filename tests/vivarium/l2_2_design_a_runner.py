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
SUPPORTED_PROCESSES = frozenset(
    {
        "Metabolism",
        "Translation",
        "Transcription",
        "RNADecay",
        "ProteinDecay",
        "MacromolecularComplexation",
    }
)
DEFAULT_BOOTSTRAP_B = 1000
_PROCESS_BUCKET = {
    "Metabolism": "TRIVIAL_RNG",
    "Translation": "ALGORITHMIC_DEEP",
    "Transcription": "ALGORITHMIC_DEEP",
    "RNADecay": "ALGORITHMIC_SHALLOW",
    "ProteinDecay": "ALGORITHMIC_SHALLOW",
    "MacromolecularComplexation": "ALGORITHMIC_SHALLOW",
}
_PROCESS_K_ENG = {
    "TRIVIAL_RNG": runner_helpers.TRIVIAL_RNG_K_ENG,
    "ALGORITHMIC_SHALLOW": runner_helpers.ALGORITHMIC_SHALLOW_K_ENG,
    "ALGORITHMIC_DEEP": runner_helpers.ALGORITHMIC_DEEP_K_ENG,
}
_PROCESS_OUTPUT_CHANNELS = {
    "Metabolism": ("substrates",),
    "Translation": ("substrates", "monomers", "boundEnzymes"),
    "Transcription": ("substrates", "RNAs", "boundEnzymes"),
    "RNADecay": ("substrates", "RNAs"),
    "ProteinDecay": ("substrates", "monomers", "complexs"),
    "MacromolecularComplexation": ("substrates", "complexs"),
}
_PROCESS_PRIMARY_CHANNEL = {
    "Metabolism": "substrates",
    "Translation": "monomers",
    "Transcription": "RNAs",
    "RNADecay": "RNAs",
    "ProteinDecay": "monomers",
    "MacromolecularComplexation": "substrates",
}
_PROCESS_ANALYTICAL_CHECK_REASON = {
    "Metabolism": "Metabolism has no closed-form per-tick check",
    "Translation": "Translation has no closed-form per-tick check",
    "Transcription": "Transcription has no closed-form per-tick check",
    "RNADecay": "RNADecay has no closed-form per-tick check",
    "ProteinDecay": "ProteinDecay has no closed-form per-tick check",
    "MacromolecularComplexation": "MacromolecularComplexation has no closed-form per-tick check",
}
_ORACLE_BEFORE_KEY = {
    "substrates": "before_substrates",
    "enzymes": "before_enzymes",
    "boundEnzymes": "before_bound_enzymes",
    "monomers": "before_monomers",
    "complexs": "before_complexs",
    "mRNAs": "before_mrnas",
    "RNAs": "before_rnas",
}
_ORACLE_AFTER_KEY = {
    "substrates": "after_substrates",
    "boundEnzymes": "after_bound_enzymes",
    "monomers": "after_monomers",
    "complexs": "after_complexs",
    "RNAs": "after_rnas",
}


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the L2.2 Design-A replay harness.")
    parser.add_argument("--process", required=True)
    parser.add_argument("--seeds", required=True, help="Integer count or comma-separated explicit seeds.")
    parser.add_argument("--ticks", "--m-ticks", dest="ticks", required=True, type=int, help="Number of replay ticks to evaluate.")
    parser.add_argument("--output-dir", "--out", dest="output_dir", required=True, help="Output directory for Design-A artifacts.")
    parser.add_argument("--thresholds", help="Threshold snapshot output path.")
    parser.add_argument("--bootstrap-B", dest="bootstrap_B", type=int, default=DEFAULT_BOOTSTRAP_B)
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
    process: str,
    oc_vectors_by_channel: dict[str, np.ndarray],
    karr_vectors_by_channel: dict[str, np.ndarray],
    canonical_seed_count: int,
    requested_seed_count: int,
) -> list[str]:
    warnings: list[str] = []
    if canonical_seed_count == 1 and requested_seed_count > 1:
        warnings.append(
            f"KARR_SINGLE_SEED_REUSED: {process}.npz contains one canonical Karr seed; requested OC seeds reuse that oracle slice."
        )
    primary_channel = _PROCESS_PRIMARY_CHANNEL[process]
    if process == "Metabolism" and np.array_equal(
        oc_vectors_by_channel[primary_channel],
        karr_vectors_by_channel[primary_channel],
    ):
        warnings.append(
            "TRIVIAL_RNG_LEAK: OC matched the Karr oracle exactly on every requested sample; review for possible oracle laundering."
        )
    return warnings



def _primary_channel_oracle_laundering_warning(
    *,
    process: str,
    primary_channel: str,
    oc_vectors: np.ndarray,
    karr_vectors: np.ndarray,
) -> str | None:
    if primary_channel != "RNAs":
        return None
    if process not in {"RNADecay", "Transcription"}:
        return None
    if not np.array_equal(oc_vectors, karr_vectors):
        return None
    return (
        "PRIMARY_CHANNEL_ORACLE_LAUNDERING: OC matched the Karr oracle exactly on primary "
        f"channel={primary_channel}; review for oracle laundering."
    )


def _primary_channel_oracle_determinism_legitimate_warning(
    *,
    process: str,
    primary_channel: str,
    oc_vectors: np.ndarray,
    before_vectors: np.ndarray,
    karr_vectors: np.ndarray,
) -> str | None:
    if not np.array_equal(oc_vectors, karr_vectors):
        return None
    if not np.array_equal(before_vectors, karr_vectors):
        return None
    return (
        "PRIMARY_CHANNEL_ORACLE_DETERMINISM_LEGITIMATE: OC matched the Karr oracle exactly on "
        f"primary channel={primary_channel}, and the oracle itself was unchanged (before == after) "
        "for every requested sample."
    )


def _seed_alignment_warning(
    *,
    channel_name: str,
    oc_vectors: np.ndarray,
    karr_vectors: np.ndarray,
) -> str | None:
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
        f"on channel={channel_name} (shift=+{best_shift}, observed_w1={observed:.6f}, shifted_w1={best_shift_w1:.6f})."
    )


def _result_payload(
    *,
    process: str,
    bucket: str,
    seeds: list[int],
    m_ticks: int,
    timestamp: str,
    channel_payloads: dict[str, Any],
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
        "bucket": bucket,
        "k_eng": dict(_PROCESS_K_ENG),
        "channels": channel_payloads,
        "joint_check": None,
        "warnings": warnings,
        "allocator_inputs_ref": str(allocator_inputs_path),
        "provenance_ref": str(provenance_path),
    }


def _summary_payload(
    *,
    process: str,
    bucket: str,
    timestamp: str,
    verdict: str,
    channel_payloads: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    channel_verdicts = {name: str(payload["verdict"]) for name, payload in channel_payloads.items()}
    failed_channels = [name for name, verdict_name in channel_verdicts.items() if verdict_name == "FAIL"]
    return {
        "generated_at": timestamp,
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "harness_version": HARNESS_VERSION,
        "k_eng": dict(_PROCESS_K_ENG),
        "processes": {
            process: {
                "verdict": verdict,
                "latest_run": timestamp,
                "bucket": bucket,
                "failed_channels": failed_channels,
                "n_channels_gated": int(
                    sum(verdict_name not in {"EVENT_CHANNEL_DEFERRED", "INSUFFICIENT_SAMPLES"} for verdict_name in channel_verdicts.values())
                ),
                "n_event_deferred": 0,
                "n_insufficient": int(sum(verdict_name == "INSUFFICIENT_SAMPLES" for verdict_name in channel_verdicts.values())),
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


def _process_bucket(process: str) -> str:
    return _PROCESS_BUCKET[process]


def _process_output_channels(process: str) -> tuple[str, ...]:
    return _PROCESS_OUTPUT_CHANNELS[process]


def _process_primary_channel(process: str) -> str:
    return _PROCESS_PRIMARY_CHANNEL[process]


def _process_sample_process(process: str) -> Any:
    if process == "Metabolism":
        return runner_helpers._metabolism_process(0)
    if process == "Translation":
        return runner_helpers._translation_process(0)
    if process == "Transcription":
        return runner_helpers._transcription_process(0)
    if process == "RNADecay":
        return runner_helpers._rna_decay_process(0)
    if process == "ProteinDecay":
        return runner_helpers._protein_decay_process(0)
    if process == "MacromolecularComplexation":
        return runner_helpers._macromol_process(0)
    raise ValueError(f"Unsupported process {process!r}.")


def _observable_wids(process: str, sample_process: Any) -> dict[str, list[str]]:
    substrate_ids = getattr(sample_process, "_sub_ids", getattr(sample_process, "substrate_wids", ()))
    if not substrate_ids:
        substrate_ids = getattr(sample_process, "aa_ids", ())
    mapping = {
        "substrates": [str(x) for x in substrate_ids],
        "enzymes": [str(x) for x in getattr(sample_process, "enzyme_wids", ())],
        "boundEnzymes": [str(x) for x in getattr(sample_process, "enzyme_wids", ())],
    }
    if process == "Translation":
        protein_ids = [str(x) for x in getattr(sample_process, "protein_ids", ())]
        mapping["monomers"] = protein_ids
        mapping["mRNAs"] = protein_ids
    if process in {"RNADecay", "Transcription"}:
        rna_ids = getattr(sample_process, "gene_ids", getattr(sample_process, "rna_wids", ()))
        mapping["RNAs"] = [str(x) for x in rna_ids]
    if process == "ProteinDecay":
        mapping["monomers"] = [str(x) for x in getattr(sample_process, "protein_wids", ())]
        mapping["complexs"] = [str(x) for x in getattr(sample_process, "complex_wids", ())]
    if process == "MacromolecularComplexation":
        mapping["complexs"] = [str(x) for x in getattr(sample_process, "complex_wids", ())]
    return mapping


def run_design_a(
    *,
    process: str,
    seeds: list[int],
    m_ticks: int,
    out_dir: Path,
    thresholds_path: Path | None = None,
    bootstrap_B: int = DEFAULT_BOOTSTRAP_B,
) -> dict[str, Any]:
    if process not in SUPPORTED_PROCESSES:
        raise ValueError(f"Unsupported process {process!r}; supported={sorted(SUPPORTED_PROCESSES)}")

    bucket = _process_bucket(process)
    k_eng = float(_PROCESS_K_ENG[bucket])
    output_channels = _process_output_channels(process)
    primary_channel = _process_primary_channel(process)
    thresholds_output = thresholds_path or (out_dir / "thresholds.json")
    oracle = runner_helpers.load_karr_oracle(process)
    before_vectors = {
        channel: _normalize_seed_axis(oracle[_ORACLE_BEFORE_KEY[channel]], seeds, m_ticks)
        for channel in ("substrates", "enzymes", "boundEnzymes", "monomers", "complexs", "mRNAs", "RNAs")
        if _ORACLE_BEFORE_KEY.get(channel) in oracle
    }
    after_vectors = {
        channel: _normalize_seed_axis(oracle[_ORACLE_AFTER_KEY[channel]], seeds, m_ticks)
        for channel in output_channels
    }

    sample_process = _process_sample_process(process)
    wids_by_channel = _observable_wids(process, sample_process)

    oc_vectors = {
        channel: np.zeros_like(after_vectors[channel], dtype=np.float64)
        for channel in output_channels
    }
    per_sample_w1 = {
        channel: np.zeros((len(seeds), m_ticks), dtype=np.float64)
        for channel in output_channels
    }
    allocator_inputs: list[dict[str, Any]] = []
    for seed_index, seed in enumerate(seeds):
        for tick in range(m_ticks):
            sample_state = {
                "substrate_wids": wids_by_channel["substrates"],
                "enzyme_wids": wids_by_channel["enzymes"],
                "oracle_before_substrates": before_vectors["substrates"][seed_index, tick],
                "oracle_after_substrates": after_vectors["substrates"][seed_index, tick],
                "oracle_before_enzymes": before_vectors["enzymes"][seed_index, tick],
                "oracle_after_all": after_vectors[primary_channel],
                "oracle_before_all": before_vectors.get(primary_channel, before_vectors["substrates"]),
                "oracle_after_by_channel": {
                    channel: after_vectors[channel]
                    for channel in output_channels
                },
                "oracle_before_by_channel": before_vectors,
            }
            if process == "Transcription":
                sample_state.update(
                    {
                        "rna_wids": wids_by_channel["RNAs"],
                        "oracle_before_rnas": before_vectors["RNAs"][seed_index, tick],
                        "oracle_after_rnas": after_vectors["RNAs"][seed_index, tick],
                        "oracle_after_bound_enzymes": after_vectors["boundEnzymes"][seed_index, tick],
                    }
                )
            if process == "Translation":
                sample_state.update(
                    {
                        "monomer_wids": wids_by_channel["monomers"],
                        "mrna_wids": wids_by_channel["mRNAs"],
                        "oracle_before_monomers": before_vectors["monomers"][seed_index, tick],
                        "oracle_before_mrnas": before_vectors["mRNAs"][seed_index, tick],
                        "oracle_after_monomers": after_vectors["monomers"][seed_index, tick],
                        "oracle_after_bound_enzymes": after_vectors["boundEnzymes"][seed_index, tick],
                    }
                )
            if process == "RNADecay":
                sample_state.update(
                    {
                        "rna_wids": wids_by_channel["RNAs"],
                        "oracle_before_rnas": before_vectors["RNAs"][seed_index, tick],
                        "oracle_after_rnas": after_vectors["RNAs"][seed_index, tick],
                    }
                )
            if process == "ProteinDecay":
                sample_state.update(
                    {
                        "monomer_wids": wids_by_channel["monomers"],
                        "complex_wids": wids_by_channel["complexs"],
                        "oracle_before_monomers": before_vectors["monomers"][seed_index, tick],
                        "oracle_before_complexs": before_vectors["complexs"][seed_index, tick],
                        "oracle_after_monomers": after_vectors["monomers"][seed_index, tick],
                        "oracle_after_complexs": after_vectors["complexs"][seed_index, tick],
                    }
                )
            if process == "MacromolecularComplexation":
                sample_state.update(
                    {
                        "complex_wids": wids_by_channel["complexs"],
                        "oracle_before_complexs": before_vectors["complexs"][seed_index, tick],
                        "oracle_after_complexs": after_vectors["complexs"][seed_index, tick],
                    }
                )
            if "boundEnzymes" in before_vectors:
                sample_state["oracle_before_bound_enzymes"] = before_vectors["boundEnzymes"][seed_index, tick]
            oc_result = runner_helpers.run_oc_tick(process, int(seed), int(tick), sample_state)
            for channel in output_channels:
                oc_vectors[channel][seed_index, tick] = np.asarray(oc_result[channel], dtype=np.float64)
                per_sample_w1[channel][seed_index, tick] = runner_helpers.compute_w1(
                    oc_vectors[channel][seed_index, tick],
                    after_vectors[channel][seed_index, tick],
                )
            allocator_inputs.append(
                {
                    "process": process,
                    "seed": int(seed),
                    "tick": int(tick),
                    "substrates_sum_before": float(np.sum(before_vectors["substrates"][seed_index, tick])),
                    "substrates_nonzero_before": int(np.count_nonzero(before_vectors["substrates"][seed_index, tick])),
                    "enzymes_sum_before": float(np.sum(before_vectors["enzymes"][seed_index, tick])),
                    "primary_channel": primary_channel,
                    "primary_sum_before": float(
                        np.sum(before_vectors.get(primary_channel, before_vectors["substrates"])[seed_index, tick])
                    ),
                }
            )
            if "RNAs" in before_vectors:
                allocator_inputs[-1]["rnas_sum_before"] = float(np.sum(before_vectors["RNAs"][seed_index, tick]))
            if "mRNAs" in before_vectors:
                allocator_inputs[-1]["mrnas_sum_before"] = float(np.sum(before_vectors["mRNAs"][seed_index, tick]))
            if "monomers" in before_vectors:
                allocator_inputs[-1]["monomers_sum_before"] = float(np.sum(before_vectors["monomers"][seed_index, tick]))
            if "complexs" in before_vectors:
                allocator_inputs[-1]["complexs_sum_before"] = float(np.sum(before_vectors["complexs"][seed_index, tick]))
            if "boundEnzymes" in before_vectors:
                allocator_inputs[-1]["bound_enzymes_sum_before"] = float(np.sum(before_vectors["boundEnzymes"][seed_index, tick]))

    channel_payloads: dict[str, Any] = {}
    null_payload_channels: dict[str, Any] = {}
    thresholds_channels: dict[str, Any] = {}
    for channel in output_channels:
        null_stats = runner_helpers.compute_null_q95(
            karr_vectors=after_vectors[channel],
            bootstrap_B=int(bootstrap_B),
        )
        w1_oc_vs_karr = float(np.mean(per_sample_w1[channel]))
        threshold = max(runner_helpers.ABSOLUTE_FLOOR, k_eng * float(null_stats["q95_null"]))
        flat_oc = oc_vectors[channel].reshape(-1)
        flat_karr = after_vectors[channel].reshape(-1)
        ks_stat, ks_pvalue = ks_2samp(flat_oc, flat_karr)
        ci95 = _bootstrap_ci(
            oc_vectors=oc_vectors[channel],
            karr_vectors=after_vectors[channel],
            bootstrap_B=int(bootstrap_B),
            rng_seed=runner_helpers.L2_2_VALIDATION_SEED,
        )
        channel_payloads[channel] = {
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
            "is_primary": channel == primary_channel,
            "is_event_channel": False,
            "aggregation": "per_tick_vector_w1_mean",
            "per_sample_w1_summary": {
                "mean": w1_oc_vs_karr,
                "max": float(np.max(per_sample_w1[channel])),
                "min": float(np.min(per_sample_w1[channel])),
            },
        }
        null_payload_channels[channel] = {
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
        }
        thresholds_channels[channel] = {
            "q95_null": float(null_stats["q95_null"]),
            "k_eng": k_eng,
            "absolute_floor": runner_helpers.ABSOLUTE_FLOOR,
            "threshold": float(threshold),
        }
    warnings = _warning_strings(
        process=process,
        oc_vectors_by_channel=oc_vectors,
        karr_vectors_by_channel=after_vectors,
        canonical_seed_count=int(oracle.get("canonical_seed_count", after_vectors[primary_channel].shape[0])),
        requested_seed_count=len(seeds),
    )
    primary_oracle_laundering_warning = _primary_channel_oracle_laundering_warning(
        process=process,
        primary_channel=primary_channel,
        oc_vectors=oc_vectors[primary_channel],
        karr_vectors=after_vectors[primary_channel],
    )
    if primary_oracle_laundering_warning is not None:
        warnings.append(primary_oracle_laundering_warning)
        channel_payloads[primary_channel]["verdict"] = "FAIL"
    primary_legitimate_determinism_warning = _primary_channel_oracle_determinism_legitimate_warning(
        process=process,
        primary_channel=primary_channel,
        oc_vectors=oc_vectors[primary_channel],
        before_vectors=before_vectors.get(primary_channel, before_vectors["substrates"]),
        karr_vectors=after_vectors[primary_channel],
    )
    if primary_legitimate_determinism_warning is not None:
        warnings.append(primary_legitimate_determinism_warning)
    seed_alignment_warning = _seed_alignment_warning(
        channel_name=primary_channel,
        oc_vectors=oc_vectors[primary_channel],
        karr_vectors=after_vectors[primary_channel],
    )
    if seed_alignment_warning is not None:
        warnings.append(seed_alignment_warning)
    timestamp = datetime.now(UTC).isoformat()
    allocator_inputs_path = out_dir / "allocator_inputs.json"
    provenance_path = out_dir / "provenance.json"
    process_verdict = _process_verdict([str(payload["verdict"]) for payload in channel_payloads.values()])
    if seed_alignment_warning is not None and process_verdict == "PASS":
        process_verdict = "FAIL"
    result = _result_payload(
        process=process,
        bucket=bucket,
        seeds=seeds,
        m_ticks=m_ticks,
        timestamp=timestamp,
        channel_payloads=channel_payloads,
        verdict=process_verdict,
        warnings=warnings,
        bootstrap_B=int(bootstrap_B),
        allocator_inputs_path=allocator_inputs_path,
        provenance_path=provenance_path,
    )
    summary = _summary_payload(
        process=process,
        bucket=bucket,
        timestamp=timestamp,
        verdict=result["verdict"],
        channel_payloads=channel_payloads,
        warnings=warnings,
    )

    thresholds_payload = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "harness_version": HARNESS_VERSION,
        "process": process,
        "bucket": bucket,
        "channels": thresholds_channels,
    }
    oracle_path = Path(oracle["oracle_path"])
    input_manifest = {
        "generated_at": timestamp,
        "inputs": [
            {"path": str(oracle_path), "sha256": _sha256_file(oracle_path)},
            {"path": str(Path(__file__).resolve()), "sha256": _sha256_file(Path(__file__).resolve())},
            {
                "path": str((_HELPER_DIR / "_l2_2_design_a_runner_helpers.py").resolve()),
                "sha256": _sha256_file((_HELPER_DIR / "_l2_2_design_a_runner_helpers.py").resolve()),
            },
        ],
        "resolved_seeds": [int(seed) for seed in seeds],
        "m_ticks": int(m_ticks),
    }
    oracle_sidecar = oracle_path.with_suffix(".json")
    if oracle_sidecar.exists():
        input_manifest["inputs"].insert(1, {"path": str(oracle_sidecar), "sha256": _sha256_file(oracle_sidecar)})
    null_payload = {
        "generated_at": timestamp,
        "process": process,
        "bucket": bucket,
        "channels": null_payload_channels,
        "warnings": warnings,
    }
    analytical_check = {
        "applicable": False,
        "reason": _PROCESS_ANALYTICAL_CHECK_REASON[process],
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
    _write_json(thresholds_output, thresholds_payload)
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
        thresholds_path = Path(args.thresholds) if args.thresholds else None
        payload = run_design_a(
            process=args.process,
            seeds=_parse_seed_spec(args.seeds),
            m_ticks=int(args.ticks),
            out_dir=Path(args.output_dir),
            thresholds_path=thresholds_path,
            bootstrap_B=int(args.bootstrap_B),
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
    channel_bits = " ".join(
        f"{channel}={channel_payload['verdict']}@{channel_payload['w1_oc_vs_karr']:.6f}"
        for channel, channel_payload in result["channels"].items()
    )
    print(
        f"{result['process']} {result['verdict']} {channel_bits}"
    )
    return _exit_code(str(result["verdict"]))


if __name__ == "__main__":
    raise SystemExit(main())
