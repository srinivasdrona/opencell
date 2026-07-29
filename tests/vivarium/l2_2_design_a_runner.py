from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from functools import lru_cache
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
import yaml
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
from _l2_2_design_a_projections import (  # noqa: E402
    extract_projection,
    hurdle_event_rate_plus_conditional_scaled_distance,
    per_component_scaled_distance,
)
from opencell.m1 import calc_flux_bounds as cfb  # noqa: E402
from opencell.m1.fva import (  # noqa: E402
    fva_range,
    new_fva_solver_telemetry,
    substrate_delta_range_from_fva,
)


HARNESS_VERSION = "design_a_v1_3"
# v1.4 adds optional primary-channel `per_component` / `hurdle` diagnostic blocks
# while preserving the existing top-level channel schema.
SUMMARY_SCHEMA_VERSION = "1.4"
DEFAULT_BOOTSTRAP_B = 1000
_METABOLISM_FVA_BIG = 1e6
_METABOLISM_FVA_TOL = 2.0
_METABOLISM_FVA_PASS_FRACTION = 0.99
_PROCESS_K_ENG = {
    "TRIVIAL_RNG": runner_helpers.TRIVIAL_RNG_K_ENG,
    "ALGORITHMIC_SHALLOW": runner_helpers.ALGORITHMIC_SHALLOW_K_ENG,
    "ALGORITHMIC_DEEP": runner_helpers.ALGORITHMIC_DEEP_K_ENG,
}
_PROCESS_CATALOG_PATH = _REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "PROCESS_CATALOG.yaml"
_CHANNEL_NAME_ALIASES = {
    "mrnas": "mRNAs",
    "rnas": "RNAs",
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


def _normalize_channel_name(name: str) -> str:
    channel = str(name)
    return _CHANNEL_NAME_ALIASES.get(channel.lower(), channel)


def _normalize_catalog_entry(
    entry: dict[str, Any],
    bucket_rationale: str | None,
    bucket_harness_type: str | None = None,
) -> dict[str, Any]:
    normalized = dict(entry)
    for key in ("event_channels", "input_channels", "output_channels"):
        channels = normalized.get(key)
        if channels is not None:
            normalized[key] = tuple(_normalize_channel_name(channel) for channel in channels)
    primary_channel = normalized.get("primary_channel")
    if primary_channel is not None:
        normalized["primary_channel"] = _normalize_channel_name(str(primary_channel))
    normalized["_bucket_rationale"] = bucket_rationale
    normalized["_bucket_harness_type"] = bucket_harness_type
    return normalized


@lru_cache(maxsize=1)
def _load_catalog_document(path: Path | None = None) -> dict[str, Any]:
    catalog_path = Path(path) if path is not None else _PROCESS_CATALOG_PATH
    payload = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid process catalog payload in {catalog_path}")
    return payload


@lru_cache(maxsize=1)
def _load_catalog(path: Path | None = None) -> dict[str, dict]:
    document = _load_catalog_document(path)
    buckets = document.get("buckets", {})
    processes = document.get("processes", ())
    catalog: dict[str, dict[str, Any]] = {}
    for raw_entry in processes:
        if not isinstance(raw_entry, dict):
            continue
        if not raw_entry.get("in_scope_L2_2"):
            continue
        name = str(raw_entry["name"])
        bucket_name = str(raw_entry.get("bucket", ""))
        bucket_rationale = None
        bucket_harness_type = None
        if isinstance(buckets, dict):
            bucket_meta = buckets.get(bucket_name, {})
            if isinstance(bucket_meta, dict):
                rationale = bucket_meta.get("rationale")
                if rationale is not None:
                    bucket_rationale = str(rationale)
                ht = bucket_meta.get("harness_type")
                if ht is not None:
                    bucket_harness_type = str(ht)
        catalog[name] = _normalize_catalog_entry(raw_entry, bucket_rationale, bucket_harness_type)
    return catalog


@lru_cache(maxsize=1)
def _load_catalog_all(path: Path | None = None) -> dict[str, dict[str, Any]]:
    document = _load_catalog_document(path)
    buckets = document.get("buckets", {})
    processes = document.get("processes", ())
    catalog: dict[str, dict[str, Any]] = {}
    for raw_entry in processes:
        if not isinstance(raw_entry, dict):
            continue
        name = str(raw_entry["name"])
        bucket_name = str(raw_entry.get("bucket", ""))
        bucket_rationale = None
        bucket_harness_type = None
        if isinstance(buckets, dict):
            bucket_meta = buckets.get(bucket_name, {})
            if isinstance(bucket_meta, dict):
                rationale = bucket_meta.get("rationale")
                if rationale is not None:
                    bucket_rationale = str(rationale)
                ht = bucket_meta.get("harness_type")
                if ht is not None:
                    bucket_harness_type = str(ht)
        catalog[name] = _normalize_catalog_entry(raw_entry, bucket_rationale, bucket_harness_type)
    return catalog


def _implemented_processes() -> frozenset[str]:
    return frozenset(str(name) for name in runner_helpers._tick_dispatch())


_CATALOG_IN_SCOPE = _load_catalog()
SUPPORTED_PROCESSES = frozenset(name for name in _CATALOG_IN_SCOPE if name in _implemented_processes())
_PROCESS_BUCKET = {name: str(entry["bucket"]) for name, entry in _CATALOG_IN_SCOPE.items() if name in SUPPORTED_PROCESSES}
_PROCESS_OUTPUT_CHANNELS = {
    name: tuple(str(channel) for channel in entry["output_channels"])
    for name, entry in _CATALOG_IN_SCOPE.items()
    if name in SUPPORTED_PROCESSES
}
_PROCESS_PRIMARY_CHANNEL = {
    name: str(entry["primary_channel"])
    for name, entry in _CATALOG_IN_SCOPE.items()
    if name in SUPPORTED_PROCESSES
}
_PROCESS_ANALYTICAL_CHECK_REASON = {
    name: f"{name} has no closed-form per-tick check"
    for name in SUPPORTED_PROCESSES
}
_PROCESS_EVENT_CHANNELS = {
    name: tuple(str(channel) for channel in entry.get("event_channels", ()))
    for name, entry in _CATALOG_IN_SCOPE.items()
    if name in SUPPORTED_PROCESSES
}
_PROCESS_JOINT_CHECK = {
    name: bool(entry.get("joint_check", False))
    for name, entry in _CATALOG_IN_SCOPE.items()
    if name in SUPPORTED_PROCESSES
}
_PROCESS_PRIMARY_PROJECTION = {
    name: tuple(str(component) for component in entry.get("primary_projection", ()))
    for name, entry in _CATALOG_IN_SCOPE.items()
    if name in SUPPORTED_PROCESSES
}
_PROCESS_PRIMARY_DISTANCE = {
    name: str(entry.get("primary_distance", "per_tick_vector_w1_mean"))
    for name, entry in _CATALOG_IN_SCOPE.items()
    if name in SUPPORTED_PROCESSES
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
    if arr.ndim < 3:
        raise ValueError(f"Expected oracle tensor with shape (seed, tick, ...); got {arr.shape}")
    if m_ticks > arr.shape[1]:
        raise ValueError(f"Requested {m_ticks} ticks, but oracle only provides {arr.shape[1]}.")
    if arr.shape[0] == 1:
        return np.repeat(arr[:, :m_ticks, ...], len(seeds), axis=0)
    if max(seeds) >= arr.shape[0]:
        raise ValueError(
            f"Requested seed index {max(seeds)} but oracle only provides {arr.shape[0]} seed slices."
        )
    return np.stack([arr[int(seed), :m_ticks, ...] for seed in seeds], axis=0)


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
    """Detect oracle laundering on the primary channel for any in-scope process.

    Generalized 2026-06-12: previously scoped to RNAs primary on 5 RNA processes.
    Empirical anchor: PPI/PPII (monomers primary) and MacromolecularComplexation
    (complexs primary) all shipped W1=0.0 vs Karr where the Karr-vs-Karr null
    bootstrap shows q95~=0.001, proving OC could not honestly match without
    reading from the same source. The sibling
    `_primary_channel_oracle_determinism_legitimate_warning` continues to
    suppress this when before==after (genuinely deterministic biology).
    """
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
    """Informational only. Does not gate any verdict.

    Diagonal seed alignment is not a meaningful comparison for cross-engine
    ensembles (numpy vs MATLAB rand produce different sequences for the same
    integer seed).
    """
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
        "SEED_ALIGNMENT_DIAGNOSTIC: OC outputs align better to a shifted Karr seed index "
        f"on channel={channel_name} (shift=+{best_shift}, observed_w1={observed:.6f}, shifted_w1={best_shift_w1:.6f})."
    )


def _result_payload(
    *,
    process: str,
    bucket: str,
    seeds: list[int],
    m_ticks: int,
    canonical_seed_count: int,
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
        "canonical_seed_count": int(canonical_seed_count),
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
    n_event_deferred = int(sum(verdict_name == "EVENT_CHANNEL_DEFERRED" for verdict_name in channel_verdicts.values()))
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
                "n_event_deferred": n_event_deferred,
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


def _process_event_channels(process: str) -> tuple[str, ...]:
    return _PROCESS_EVENT_CHANNELS.get(process, ())


def _process_joint_check(process: str) -> bool:
    return _PROCESS_JOINT_CHECK.get(process, False)


def _process_primary_projection(process: str) -> tuple[str, ...]:
    return _PROCESS_PRIMARY_PROJECTION.get(process, ())


def _process_primary_distance(process: str) -> str:
    return _PROCESS_PRIMARY_DISTANCE.get(process, "per_tick_vector_w1_mean")


def _process_catalog_entry(process: str) -> dict[str, Any]:
    catalog = _load_catalog_all()
    entry = catalog.get(process)
    if entry is None:
        raise ValueError(f"Unsupported process {process!r}; supported={sorted(SUPPORTED_PROCESSES)}")
    return entry


def _validate_process_request(process: str) -> None:
    entry = _process_catalog_entry(process)
    if not entry.get("in_scope_L2_2"):
        bucket = entry.get("bucket", "unknown")
        rationale = entry.get("_bucket_rationale") or entry.get("notes") or "no rationale provided"
        raise ValueError(
            f"Process {process!r} is out of L2.2 scope: bucket={bucket}; rationale={rationale}"
        )
    # v3 harness routing: refuse processes not destined for this harness.
    # design_a_per_tick is the only harness this runner implements.
    harness_type = entry.get("harness_type") or entry.get("_bucket_harness_type")
    if harness_type and harness_type != "design_a_per_tick":
        bucket = entry.get("bucket", "unknown")
        raise ValueError(
            f"Process {process!r} requires harness_type={harness_type!r} but this runner "
            f"only implements design_a_per_tick. bucket={bucket}. "
            f"Catalog entry's notes field for the rationale. "
            f"In particular, EVENT_CLASS processes (event_density:sparse + seed_window) "
            f"silently produce zero-W1 fake PASSes through this harness because their "
            f"sparse events do not fire in the 100-tick replay window. The L2.event "
            f"harness needs to be built; until then, do not gate these processes here."
        )
    if process not in SUPPORTED_PROCESSES:
        bucket = entry.get("bucket", "unknown")
        raise ValueError(
            f"Process {process!r} is in scope in PROCESS_CATALOG.yaml (bucket={bucket}) "
            f"but this runner currently supports only {sorted(SUPPORTED_PROCESSES)}."
        )


def _projection_component_scales(
    projection_spec: tuple[str, ...],
    karr_projection_vectors: np.ndarray,
) -> dict[str, float]:
    scales: dict[str, float] = {}
    for idx, component_name in enumerate(projection_spec):
        values = np.asarray(karr_projection_vectors[:, :, idx], dtype=np.float64).reshape(-1)
        nonzero = np.abs(values[np.abs(values) > 1e-12])
        if nonzero.size == 0:
            scale = 1.0
        else:
            scale = float(max(np.percentile(nonzero, 95), 1.0))
        scales[str(component_name)] = scale
    return scales


def _process_sample_process(process: str) -> Any:
    if process == "Metabolism":
        return runner_helpers._metabolism_process(0)
    if process == "Translation":
        return runner_helpers._translation_process(0)
    if process == "Transcription":
        return runner_helpers._transcription_process(0)
    if process == "RNADecay":
        return runner_helpers._rna_decay_process(0)
    if process == "RNAProcessing":
        return runner_helpers._rna_processing_process(0)
    if process == "RNAModification":
        return runner_helpers._rna_modification_process(0)
    if process == "tRNAAminoacylation":
        return runner_helpers._trna_aminoacylation_process(0)
    if process == "ProteinModification":
        return runner_helpers._protein_modification_process(0)
    if process == "ProteinFolding":
        return runner_helpers._protein_folding_process(0)
    if process == "ProteinTranslocation":
        return runner_helpers._protein_translocation_process(0)
    if process == "ProteinDecay":
        return runner_helpers._protein_decay_process(0)
    if process == "ProteinProcessingI":
        return runner_helpers._protein_processing_i_process(0)
    if process == "ProteinProcessingII":
        return runner_helpers._protein_processing_ii_process(0)
    if process == "RibosomeAssembly":
        return runner_helpers._ribosome_assembly_process(0)
    if process == "MacromolecularComplexation":
        return runner_helpers._macromol_process(0)
    if process == "Cytokinesis":
        return runner_helpers._cytokinesis_process(0)
    if process == "DNASupercoiling":
        return runner_helpers._dna_supercoiling_process(0)
    if process == "Replication":
        return runner_helpers._replication_process(0)
    if process == "DNARepair":
        return runner_helpers._dna_repair_process(0)
    if process == "ReplicationInitiation":
        return runner_helpers._replication_initiation_process(0)
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
    if process in {
        "RNADecay",
        "Transcription",
        "RNAProcessing",
        "RNAModification",
        "tRNAAminoacylation",
    }:
        rna_ids = getattr(
            sample_process,
            "rna_primary_wids",
            getattr(sample_process, "gene_ids", getattr(sample_process, "rna_wids", ())),
        )
        mapping["RNAs"] = [str(x) for x in rna_ids]
    if process in {"ProteinModification", "ProteinFolding", "ProteinTranslocation"}:
        mapping["monomers"] = [str(x) for x in getattr(sample_process, "monomer_wids", ())]
    if process in {"ProteinDecay", "MacromolecularComplexation"}:
        monomer_ids = getattr(sample_process, "protein_wids", getattr(sample_process, "monomer_wids", ()))
        mapping["monomers"] = [str(x) for x in monomer_ids]
        mapping["complexs"] = [str(x) for x in getattr(sample_process, "complex_wids", ())]
    if process in {"ProteinProcessingI", "ProteinProcessingII"}:
        monomer_ids = getattr(
            sample_process,
            "monomer_wids",
            getattr(sample_process, "unprocessed_monomer_wids", ()),
        )
        mapping["monomers"] = [str(x) for x in monomer_ids]
    if process == "RibosomeAssembly":
        mapping["monomers"] = [str(x) for x in getattr(sample_process, "monomer_subunit_wids", ())]
        mapping["complexs"] = [str(x) for x in getattr(sample_process, "complex_wids", ())]
        mapping["RNAs"] = [str(x) for x in getattr(sample_process, "rna_subunit_wids", ())]
    if process == "Cytokinesis":
        # SUT's _substrate_wids includes GTP (4 WIDs); the Karr oracle snapshot has
        # only the 3 fixture substrate WIDs (PI, H2O, H). Use fixture WIDs for the
        # comparison surface; the tick dispatcher projects SUT output down to these.
        mapping["substrates"] = [str(x) for x in getattr(sample_process, "fixture_substrate_wids", ())]
        mapping["enzymes"] = [str(x) for x in getattr(sample_process, "fixture_enzyme_wids", ())]
        mapping["boundEnzymes"] = [str(x) for x in getattr(sample_process, "fixture_enzyme_wids", ())]
    if process == "ReplicationInitiation":
        # complexs is aliased from boundEnzymes (per _format_ensemble_oracle); the
        # complex WIDs are therefore the enzyme WIDs of the 15-element DnaA-state array.
        mapping["complexs"] = [str(x) for x in getattr(sample_process, "enzyme_wids", ())]
    return mapping


def _effective_metric_type(
    *,
    process: str,
    requested: Literal["w1", "fva_feasibility"],
    sample_process: Any,
) -> Literal["w1", "fva_feasibility"]:
    if requested not in {"w1", "fva_feasibility"}:
        raise ValueError(
            f"Unsupported metric_type={requested!r}; expected 'w1' or 'fva_feasibility'."
        )
    if process != "Metabolism":
        if requested != "w1":
            raise ValueError(
                "metric_type='fva_feasibility' is currently supported only for process='Metabolism'."
            )
        return "w1"

    if requested == "fva_feasibility":
        return "fva_feasibility"

    # Factory opt-in: Metabolism defaults to fva_feasibility unless caller overrides.
    preferred = str(getattr(sample_process, "l2_2_metric_type", "w1"))
    if preferred == "fva_feasibility":
        return "fva_feasibility"
    return "w1"


def _metabolism_bounds_for_fva(
    *,
    pre_sub_585x3: np.ndarray,
    pre_enz_104: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    model = runner_helpers._metabolism_model()
    dyn = runner_helpers._metabolism_dynamics()
    fba_reaction_bounds = np.column_stack([model.lb, model.ub]).astype(np.float64)
    bounds = cfb.compute_bounds(
        substrates=np.asarray(pre_sub_585x3, dtype=np.float64),
        enzymes=np.asarray(pre_enz_104, dtype=np.float64),
        cell_dry_mass=dyn.cell_dry_mass,
        step_size_sec=dyn.step_size_sec,
        catalysis=model.catalysis,
        enz_bounds=model.enz_bounds,
        fba_reaction_bounds=fba_reaction_bounds,
        dyn=dyn,
        apply_protein_bounds=False,
    )
    lb = np.where(np.isfinite(bounds[:, 0]), bounds[:, 0], -_METABOLISM_FVA_BIG)
    ub = np.where(np.isfinite(bounds[:, 1]), bounds[:, 1], _METABOLISM_FVA_BIG)
    lb = np.clip(lb, -_METABOLISM_FVA_BIG, _METABOLISM_FVA_BIG).astype(np.float64)
    ub = np.clip(ub, -_METABOLISM_FVA_BIG, _METABOLISM_FVA_BIG).astype(np.float64)
    infeasible = lb > ub
    if np.any(infeasible):
        midpoint = 0.5 * (lb[infeasible] + ub[infeasible])
        lb[infeasible] = midpoint
        ub[infeasible] = midpoint
    return lb, ub


def _metabolism_fva_sample_feasibility(
    *,
    pre_sub_585x3: np.ndarray,
    post_sub_585x3: np.ndarray,
    pre_enz_104: np.ndarray,
    telemetry: dict[str, Any] | None = None,
) -> tuple[int, int]:
    model = runner_helpers._metabolism_model()
    fixture = getattr(runner_helpers._metabolism_process(0), "_karr_writeback_fixture", None)
    if fixture is None:
        raise RuntimeError("Metabolism process missing Karr writeback fixture for FVA feasibility.")

    lb, ub = _metabolism_bounds_for_fva(
        pre_sub_585x3=np.asarray(pre_sub_585x3, dtype=np.float64),
        pre_enz_104=np.asarray(pre_enz_104, dtype=np.float64),
    )
    _v_star, info = runner_helpers.m1_karr_metabolism.solve_fba(
        model,
        use_full_objective=True,
        sense="max",
        big=_METABOLISM_FVA_BIG,
        lb_override=lb,
        ub_override=ub,
        solver="glpk",
    )
    biomass_value_star = float(info["objective_value"])
    growth_per_s = float(info["biomass_flux_per_s"])
    # Mechanical perf reduction (no biology/tolerance/threshold change): only
    # solve FVA for the reactions substrate_delta_range_from_fva actually
    # reads (fixture.fba_idx_external | fba_idx_internal). All other
    # reactions' v_min/v_max are never consumed downstream, so restricting
    # the LP sweep to this subset cannot change any d_min/d_max/feasibility
    # output -- see benchmarks/bench_fva_reaction_scope.py for the proof that
    # this is the exact and only reaction set read by substrate_delta_range_from_fva.
    fva_reaction_subset = np.union1d(
        np.asarray(fixture.fba_idx_external, dtype=np.int64),
        np.asarray(fixture.fba_idx_internal, dtype=np.int64),
    )
    v_min, v_max = fva_range(
        np.asarray(model.S, dtype=np.float64),
        np.asarray(model.RHS, dtype=np.float64),
        np.asarray(model.obj, dtype=np.float64),
        lb,
        ub,
        biomass_value_star=biomass_value_star,
        reaction_subset=fva_reaction_subset,
        telemetry=telemetry,
    )
    d_min, d_max = substrate_delta_range_from_fva(
        v_min=v_min,
        v_max=v_max,
        fixture=fixture,
        growth_per_s=growth_per_s,
        step_size_sec=float(fixture.step_size_sec),
        pre_state_585x3=np.asarray(pre_sub_585x3, dtype=np.float64),
    )
    karr_delta = np.asarray(post_sub_585x3, dtype=np.float64) - np.asarray(pre_sub_585x3, dtype=np.float64)
    in_range = (
        np.isfinite(d_min)
        & np.isfinite(d_max)
        & (karr_delta >= (d_min - _METABOLISM_FVA_TOL))
        & (karr_delta <= (d_max + _METABOLISM_FVA_TOL))
    )
    total = int(in_range.size)
    feasible = int(np.count_nonzero(in_range))
    return feasible, total


def run_design_a(
    *,
    process: str,
    seeds: list[int],
    m_ticks: int,
    out_dir: Path,
    thresholds_path: Path | None = None,
    bootstrap_B: int = DEFAULT_BOOTSTRAP_B,
    metric_type: Literal["w1", "fva_feasibility"] = "w1",
) -> dict[str, Any]:
    _validate_process_request(process)

    bucket = _process_bucket(process)
    k_eng = float(_PROCESS_K_ENG[bucket])
    output_channels = _process_output_channels(process)
    primary_channel = _process_primary_channel(process)
    event_channels = set(_process_event_channels(process))
    joint_check_enabled = _process_joint_check(process)
    primary_distance = _process_primary_distance(process)
    primary_projection = _process_primary_projection(process)
    use_projection_distance = primary_distance != "per_tick_vector_w1_mean"
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
        if _ORACLE_AFTER_KEY.get(channel) in oracle
    }
    # Catalog may list output_channels that the current oracle doesn't carry (e.g.
    # chromosome state for processes where chromosome is event-only and not
    # snapshotted as a vector). Filter those out and surface as event-deferred via
    # event_channels mechanism if applicable; otherwise just skip silently.
    gateable_output_channels = tuple(
        channel for channel in output_channels if channel in after_vectors
    )

    sample_process = _process_sample_process(process)
    effective_metric_type = _effective_metric_type(
        process=process,
        requested=metric_type,
        sample_process=sample_process,
    )
    wids_by_channel = _observable_wids(process, sample_process)
    metabolism_before_cube: np.ndarray | None = None
    metabolism_after_cube: np.ndarray | None = None
    if effective_metric_type == "fva_feasibility":
        before_cube_raw = oracle.get("before_substrates_cube")
        after_cube_raw = oracle.get("after_substrates_cube")
        if before_cube_raw is None or after_cube_raw is None:
            raise ValueError(
                "Metabolism FVA feasibility requires oracle keys "
                "`before_substrates_cube` and `after_substrates_cube`."
            )
        metabolism_before_cube = _normalize_seed_axis(
            np.asarray(before_cube_raw, dtype=np.float64),
            seeds,
            m_ticks,
        )
        metabolism_after_cube = _normalize_seed_axis(
            np.asarray(after_cube_raw, dtype=np.float64),
            seeds,
            m_ticks,
        )
        expected_shape_prefix = (len(seeds), int(m_ticks))
        if metabolism_before_cube.ndim != 4 or metabolism_after_cube.ndim != 4:
            raise ValueError(
                "Metabolism FVA feasibility requires oracle cubes "
                "`before_substrates_cube` and `after_substrates_cube` with shape "
                "(seed, tick, 585, 3)."
            )
        if tuple(metabolism_before_cube.shape[:2]) != expected_shape_prefix:
            raise ValueError(
                "Metabolism before_substrates_cube seed/tick shape mismatch: "
                f"expected prefix {expected_shape_prefix}, got {metabolism_before_cube.shape[:2]}"
            )
        if tuple(metabolism_after_cube.shape[:2]) != expected_shape_prefix:
            raise ValueError(
                "Metabolism after_substrates_cube seed/tick shape mismatch: "
                f"expected prefix {expected_shape_prefix}, got {metabolism_after_cube.shape[:2]}"
            )

    oc_vectors = {
        channel: np.zeros_like(after_vectors[channel], dtype=np.float64)
        for channel in gateable_output_channels
    }
    per_sample_w1 = {
        channel: np.zeros((len(seeds), m_ticks), dtype=np.float64)
        for channel in gateable_output_channels
    }
    oc_projection_vectors: np.ndarray | None = None
    karr_projection_vectors: np.ndarray | None = None
    chromosome_oracle: dict[str, Any] | None = None
    is_chromosome_primary = primary_channel == "chromosome"
    # Day-39: chromosome is loaded as oracle input for any process whose catalog
    # input_channels include chromosome (chromosome-primary processes need it for
    # both input overlay AND projection gating; non-primary chromosome-input
    # processes like ReplicationInitiation need it for input overlay only).
    catalog_input_channels = tuple(_process_catalog_entry(process).get("input_channels", ()))
    chromosome_in_inputs = "chromosome" in catalog_input_channels
    if use_projection_distance:
        if not primary_projection:
            raise ValueError(
                f"Process {process!r} requests primary_distance={primary_distance!r} "
                "but does not define primary_projection in PROCESS_CATALOG.yaml."
            )
        oc_projection_vectors = np.zeros((len(seeds), m_ticks, len(primary_projection)), dtype=np.float64)
        karr_projection_vectors = np.zeros_like(oc_projection_vectors)
    if chromosome_in_inputs:
        chromosome_oracle = runner_helpers.load_chromosome_oracle_for_process(
            process, list(seeds), int(m_ticks)
        )
        if is_chromosome_primary:
            # Pre-compute Karr's projection matrix from the oracle's before/after stores.
            karr_projection_vectors = runner_helpers.chromosome_projection_matrix(
                before_stores=chromosome_oracle["before_stores"],
                after_stores=chromosome_oracle["after_stores"],
                projection_spec=tuple(primary_projection),
            )
    allocator_inputs: list[dict[str, Any]] = []
    fva_feasible_pairs_total = 0
    fva_pairs_total = 0
    # C4 (non-authoritative diagnostic telemetry): a single telemetry dict
    # accumulates across every sample's FVA solves for this run -- it never
    # participates in the PASS/FAIL verdict below (which is computed purely
    # from fva_feasible_pairs_total/fva_pairs_total, unchanged), it only
    # surfaces solver-level diagnostics (fallback-cascade usage, wall time,
    # per-strategy attempt counts) for provenance/SUMMARY artifacts.
    fva_solver_telemetry = (
        new_fva_solver_telemetry() if effective_metric_type == "fva_feasibility" else None
    )
    for seed_index, seed in enumerate(seeds):
        for tick in range(m_ticks):
            sample_state = {
                "substrate_wids": wids_by_channel["substrates"],
                "oracle_before_substrates": before_vectors["substrates"][seed_index, tick],
                "oracle_after_substrates": after_vectors["substrates"][seed_index, tick],
                "oracle_after_all": after_vectors.get(primary_channel, after_vectors["substrates"]),
                "oracle_before_all": before_vectors.get(primary_channel, before_vectors["substrates"]),
                "oracle_after_by_channel": {
                    channel: after_vectors[channel]
                    for channel in gateable_output_channels
                },
                "oracle_before_by_channel": before_vectors,
            }
            if "enzymes" in before_vectors:
                sample_state["enzyme_wids"] = wids_by_channel["enzymes"]
                sample_state["oracle_before_enzymes"] = before_vectors["enzymes"][seed_index, tick]
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
            if process in {
                "RNADecay",
                "RNAProcessing",
                "RNAModification",
                "tRNAAminoacylation",
            }:
                sample_state.update(
                    {
                        "rna_wids": wids_by_channel["RNAs"],
                        "oracle_before_rnas": before_vectors["RNAs"][seed_index, tick],
                        "oracle_after_rnas": after_vectors["RNAs"][seed_index, tick],
                    }
                )
            if process in {"ProteinModification", "ProteinFolding", "ProteinTranslocation"}:
                sample_state.update(
                    {
                        "monomer_wids": wids_by_channel["monomers"],
                        "oracle_before_monomers": before_vectors["monomers"][seed_index, tick],
                    }
                )
            if process in {"ProteinProcessingI", "ProteinProcessingII"}:
                sample_state.update(
                    {
                        "monomer_wids": wids_by_channel["monomers"],
                        "oracle_before_monomers": before_vectors["monomers"][seed_index, tick],
                        "oracle_after_monomers": after_vectors["monomers"][seed_index, tick],
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
                        "monomer_wids": wids_by_channel["monomers"],
                        "complex_wids": wids_by_channel["complexs"],
                        "oracle_before_monomers": before_vectors["monomers"][seed_index, tick],
                        "oracle_before_complexs": before_vectors["complexs"][seed_index, tick],
                        "oracle_after_monomers": after_vectors["monomers"][seed_index, tick],
                        "oracle_after_complexs": after_vectors["complexs"][seed_index, tick],
                    }
                )
            if process == "RibosomeAssembly":
                sample_state.update(
                    {
                        "monomer_wids": wids_by_channel["monomers"],
                        "complex_wids": wids_by_channel["complexs"],
                        "rna_wids": wids_by_channel["RNAs"],
                        "oracle_before_monomers": before_vectors["monomers"][seed_index, tick],
                        "oracle_before_complexs": before_vectors["complexs"][seed_index, tick],
                        "oracle_before_rnas": before_vectors["RNAs"][seed_index, tick],
                    }
                )
            if "boundEnzymes" in before_vectors:
                sample_state["oracle_before_bound_enzymes"] = before_vectors["boundEnzymes"][seed_index, tick]
            if chromosome_oracle is not None:
                sample_state["oracle_before_chromosome_store"] = (
                    chromosome_oracle["before_stores"][seed_index][tick]
                )
                sample_state["enzyme_wids"] = wids_by_channel.get("enzymes", [])
            oc_result = runner_helpers.run_oc_tick(process, int(seed), int(tick), sample_state)
            if effective_metric_type == "fva_feasibility":
                assert metabolism_before_cube is not None
                assert metabolism_after_cube is not None
                feasible_pairs, total_pairs = _metabolism_fva_sample_feasibility(
                    pre_sub_585x3=metabolism_before_cube[seed_index, tick],
                    post_sub_585x3=metabolism_after_cube[seed_index, tick],
                    pre_enz_104=before_vectors["enzymes"][seed_index, tick],
                    telemetry=fva_solver_telemetry,
                )
                fva_feasible_pairs_total += int(feasible_pairs)
                fva_pairs_total += int(total_pairs)
            if is_chromosome_primary and use_projection_distance:
                # Compute OC's projection from before/after sparse-triple stores.
                # Only fires when chromosome IS the primary channel; non-primary
                # chromosome-input processes (e.g. ReplicationInitiation) just need
                # the chromosome state for input overlay, not projection gating.
                chrom_before = chromosome_oracle["before_stores"][seed_index][tick]
                chrom_after_oc = oc_result["chromosome_after_store"]
                for comp_idx, token in enumerate(primary_projection):
                    oc_projection_vectors[seed_index, tick, comp_idx] = (
                        runner_helpers._chromosome_projection_component(
                            token, chrom_before, chrom_after_oc
                        )
                    )
            elif use_projection_distance:
                oc_projection_state = oc_result.get("projection_state")
                karr_projection_state = oc_result.get("karr_projection_state")
                if oc_projection_state is None or karr_projection_state is None:
                    raise ValueError(
                        f"Process {process!r} requires projection snapshots for primary_distance={primary_distance!r}, "
                        "but run_oc_tick did not return both projection_state and karr_projection_state."
                    )
                oc_projection_vectors[seed_index, tick] = extract_projection(
                    oc_projection_state,
                    primary_projection,
                )
                karr_projection_vectors[seed_index, tick] = extract_projection(
                    karr_projection_state,
                    primary_projection,
                )
            for channel in gateable_output_channels:
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
                    "primary_channel": primary_channel,
                    "primary_sum_before": float(
                        np.sum(before_vectors.get(primary_channel, before_vectors["substrates"])[seed_index, tick])
                    ),
                }
            )
            if "enzymes" in before_vectors:
                allocator_inputs[-1]["enzymes_sum_before"] = float(
                    np.sum(before_vectors["enzymes"][seed_index, tick])
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
            if effective_metric_type == "fva_feasibility":
                allocator_inputs[-1]["fva_feasible_pairs"] = int(feasible_pairs)
                allocator_inputs[-1]["fva_pairs_total"] = int(total_pairs)
                allocator_inputs[-1]["fva_feasibility_fraction"] = float(
                    feasible_pairs / total_pairs if total_pairs else 0.0
                )

    channel_payloads: dict[str, Any] = {}
    null_payload_channels: dict[str, Any] = {}
    thresholds_channels: dict[str, Any] = {}
    primary_projection_payload: dict[str, Any] | None = None
    if use_projection_distance and oc_projection_vectors is not None and karr_projection_vectors is not None:
        if primary_distance == "per_component_scaled":
            component_scales = _projection_component_scales(primary_projection, karr_projection_vectors)
            primary_projection_payload = {
                "aggregation": primary_distance,
                "per_component": per_component_scaled_distance(
                    oc_projection_vectors,
                    karr_projection_vectors,
                    component_scales,
                ),
            }
        elif primary_distance == "hurdle_event_rate_plus_conditional_scaled_distance":
            primary_projection_payload = {
                "aggregation": primary_distance,
                "hurdle": hurdle_event_rate_plus_conditional_scaled_distance(
                    oc_projection_vectors,
                    karr_projection_vectors,
                ),
            }
        else:
            raise ValueError(f"Unsupported primary_distance {primary_distance!r} for process {process!r}.")
    for channel in gateable_output_channels:
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
            "is_event_channel": channel in event_channels,
            "aggregation": "per_tick_vector_w1_mean",
            "per_sample_w1_summary": {
                "mean": w1_oc_vs_karr,
                "max": float(np.max(per_sample_w1[channel])),
                "min": float(np.min(per_sample_w1[channel])),
            },
        }
        if (
            effective_metric_type == "fva_feasibility"
            and process == "Metabolism"
            and channel == "substrates"
        ):
            fva_fraction = float(
                fva_feasible_pairs_total / fva_pairs_total if fva_pairs_total > 0 else 0.0
            )
            channel_payloads[channel]["fva_feasibility_fraction"] = fva_fraction
            channel_payloads[channel]["fva_feasible_pairs"] = int(fva_feasible_pairs_total)
            channel_payloads[channel]["fva_pairs_total"] = int(fva_pairs_total)
            channel_payloads[channel]["fva_tolerance"] = float(_METABOLISM_FVA_TOL)
            channel_payloads[channel]["fva_threshold"] = float(_METABOLISM_FVA_PASS_FRACTION)
            channel_payloads[channel]["aggregation"] = "fva_feasibility"
            channel_payloads[channel]["verdict"] = (
                "PASS"
                if fva_fraction >= _METABOLISM_FVA_PASS_FRACTION
                else "FAIL"
            )
            if fva_solver_telemetry is not None:
                # Non-authoritative diagnostic tally only -- does not
                # participate in the "verdict" computed immediately above
                # (which is fixed purely from fva_fraction vs
                # _METABOLISM_FVA_PASS_FRACTION). Surfaces per-strategy
                # fallback-cascade usage/wall-time so a slow or degrading
                # solver can be spotted from result.json/SUMMARY without
                # re-running the sweep.
                total_solves = int(fva_solver_telemetry["total_solves"])
                channel_payloads[channel]["fva_solver_telemetry"] = {
                    "total_solves": total_solves,
                    "solves_needing_fallback": int(
                        fva_solver_telemetry["solves_needing_fallback"]
                    ),
                    "solves_needing_fallback_fraction": float(
                        fva_solver_telemetry["solves_needing_fallback"] / total_solves
                        if total_solves > 0
                        else 0.0
                    ),
                    "max_attempts_single_solve": int(
                        fva_solver_telemetry["max_attempts_single_solve"]
                    ),
                    "total_wall_time_s": float(fva_solver_telemetry["total_wall_time_s"]),
                    "strategies": {
                        name: dict(stats)
                        for name, stats in fva_solver_telemetry["strategies"].items()
                    },
                }
        if channel in event_channels:
            channel_payloads[channel]["verdict"] = "EVENT_CHANNEL_DEFERRED"
        if channel == primary_channel and primary_projection_payload is not None:
            channel_payloads[channel]["aggregation"] = str(primary_projection_payload["aggregation"])
            if "per_component" in primary_projection_payload:
                channel_payloads[channel]["per_component"] = primary_projection_payload["per_component"]
                channel_payloads[channel]["verdict"] = str(
                    primary_projection_payload["per_component"]["joint_verdict"]
                )
            if "hurdle" in primary_projection_payload:
                channel_payloads[channel]["hurdle"] = primary_projection_payload["hurdle"]
                channel_payloads[channel]["verdict"] = str(primary_projection_payload["hurdle"]["joint_verdict"])
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
    # Day-39: for chromosome-primary processes, the chromosome channel doesn't have
    # a count-vector after_vector, so it's NOT in gateable_output_channels. But it
    # IS the primary channel, so we must add a channel_payload entry that carries
    # the projection-distance verdict.
    if is_chromosome_primary and primary_projection_payload is not None:
        channel_payloads[primary_channel] = {
            "aggregation": str(primary_projection_payload["aggregation"]),
            "w1_oc_vs_karr": 0.0,  # not applicable; gate is per_component_scaled
            "is_primary": True,
            "is_event_channel": False,
        }
        if "per_component" in primary_projection_payload:
            channel_payloads[primary_channel]["per_component"] = primary_projection_payload["per_component"]
            channel_payloads[primary_channel]["verdict"] = str(
                primary_projection_payload["per_component"]["joint_verdict"]
            )
        if "hurdle" in primary_projection_payload:
            channel_payloads[primary_channel]["hurdle"] = primary_projection_payload["hurdle"]
            channel_payloads[primary_channel]["verdict"] = str(
                primary_projection_payload["hurdle"]["joint_verdict"]
            )
    warnings = list(str(warning) for warning in oracle.get("warnings", ()))
    warnings.extend(
        _warning_strings(
        process=process,
        oc_vectors_by_channel=oc_vectors,
        karr_vectors_by_channel=after_vectors,
        canonical_seed_count=int(oracle.get("canonical_seed_count", after_vectors.get(primary_channel, after_vectors.get("substrates")).shape[0])),
        requested_seed_count=len(seeds),
        )
    )
    if not is_chromosome_primary:
        primary_legitimate_determinism_warning = _primary_channel_oracle_determinism_legitimate_warning(
            process=process,
            primary_channel=primary_channel,
            oc_vectors=oc_vectors[primary_channel],
            before_vectors=before_vectors.get(primary_channel, before_vectors["substrates"]),
            karr_vectors=after_vectors[primary_channel],
        )
    else:
        # Chromosome-primary processes use the projection-distance path; primary-channel
        # determinism checks operate on count vectors that don't exist for chromosome.
        primary_legitimate_determinism_warning = None
    if primary_legitimate_determinism_warning is not None:
        warnings.append(primary_legitimate_determinism_warning)
    elif not is_chromosome_primary:
        primary_oracle_laundering_warning = _primary_channel_oracle_laundering_warning(
            process=process,
            primary_channel=primary_channel,
            oc_vectors=oc_vectors[primary_channel],
            karr_vectors=after_vectors[primary_channel],
        )
        if primary_oracle_laundering_warning is not None:
            # Consult catalog: closed_form_dominant=confirmed means the SUT's
            # deterministic closed-form path converges to Karr's stochastic output
            # by biology, not by oracle leakage. Demote FAIL -> informational.
            # See docs/phase_f/l2_2_design_a/LAUNDERING_VS_CONVERGENCE.md (H12 anchor).
            #
            # Day-37 (2026-06-23) fix: also accept `confirmed_biology_validated`
            # which is the post-Day-29 SUT-audit value the catalog uses to mark
            # processes that have been H12-probed AND biology-validated against
            # MATLAB source. The old `confirmed` is grandfathered.
            closed_form_state = str(
                _process_catalog_entry(process).get("closed_form_dominant", "false")
            )
            CONFIRMED_VALUES = {"confirmed", "confirmed_biology_validated"}
            if closed_form_state in CONFIRMED_VALUES:
                warnings.append(
                    "PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE: OC matched the Karr "
                    f"oracle exactly on primary channel={primary_channel}; per catalog "
                    f"this process has a closed_form_dominant={closed_form_state} path "
                    "that converges to Karr's stochastic output. See "
                    "docs/phase_f/l2_2_design_a/LAUNDERING_VS_CONVERGENCE.md (H12 anchor)."
                )
                # Do NOT flip the verdict to FAIL.
            else:
                warnings.append(primary_oracle_laundering_warning)
                if closed_form_state == "candidate":
                    warnings.append(
                        "LIKELY_CONVERGENCE: process is flagged closed_form_dominant: "
                        "candidate in catalog but has not been H12-probed. Run a "
                        "convergence probe before interpreting the laundering FAIL "
                        "as a real wiring issue."
                    )
                if not channel_payloads[primary_channel].get("is_event_channel", False):
                    channel_payloads[primary_channel]["verdict"] = "FAIL"
    if not is_chromosome_primary:
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
    result = _result_payload(
        process=process,
        bucket=bucket,
        seeds=seeds,
        m_ticks=m_ticks,
        canonical_seed_count=int(oracle.get("canonical_seed_count", after_vectors.get(primary_channel, after_vectors.get("substrates")).shape[0])),
        timestamp=timestamp,
        channel_payloads=channel_payloads,
        verdict=process_verdict,
        warnings=warnings,
        bootstrap_B=int(bootstrap_B),
        allocator_inputs_path=allocator_inputs_path,
        provenance_path=provenance_path,
    )
    if joint_check_enabled:
        result["joint_check"] = {"enabled": True, "verdict": None}
    summary = _summary_payload(
        process=process,
        bucket=bucket,
        timestamp=timestamp,
        verdict=result["verdict"],
        channel_payloads=channel_payloads,
        warnings=warnings,
    )
    if joint_check_enabled:
        summary["processes"][process]["joint_verdict"] = "NOT_RUN"

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
