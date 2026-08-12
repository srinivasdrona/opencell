"""Process-local active-window validation for ProteinProcessingII.

This module isolates the useful per-seed active-window work from the reverted
shared-`h12.py` experiment. It does NOT modify or monkeypatch
`scripts/l22_evidence/h12.py`; instead it:

1. parses a PPII-only manifest of source-faithful trace windows;
2. hash-binds each source trace and slices the requested 20-tick window;
3. reuses the unchanged shared H12 predictor / compare / verdict logic from
   `h12.py`; and
4. emits a NON-GATING validation report showing whether the supplied manifest
   is sufficient to cover the dormant `transferase_fires` branch.

The current tracked manifest is intentionally partial (`covered28`): it
validates the 28 seeds already covered by existing 100-tick natural traces and
records the remaining 22 seeds as an explicit real-MATLAB extraction gap.
Because this report is partial-coverage evidence, it is NOT consumed by the
shared H12 evidence index or by `verdict.py`.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import h5py
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import h12  # noqa: E402
from scripts.l22_extraction.trace_validation import validate_structural  # noqa: E402

PROCESS = "ProteinProcessingII"
MANIFEST_SCHEMA_VERSION = "h12_trace_window_manifest_v1"
ARTIFACT_KIND = "ppii_h12_active_window_validation"
ARTIFACT_VERSION = "1.0.0"
CLASSIFICATION = "PPII_ACTIVE_WINDOW_VALIDATION"
GENERATOR_SOURCE_PATH = "scripts/l22_evidence/ppii_active_windows.py"
DEFAULT_MANIFEST_PATH = (
    REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "h12" / "ProteinProcessingII_active_window_manifest.covered28.json"
)
DEFAULT_OUT_PATH = (
    REPO_ROOT
    / "docs"
    / "phase_f"
    / "l2_2_design_a"
    / "h12"
    / "active_windows"
    / "ProteinProcessingII_active_window_validation.covered28.json"
)
EXPECTED_NOT_CONSUMED_BY = [
    "scripts/l22_evidence/verdict.py",
    "scripts/l22_evidence/generator.py",
    "docs/phase_f/l2_2_design_a/h12/h12_evidence_index.json",
    "docs/phase_f/l2_2_design_a/evidence_index.json",
    "docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml",
]
NON_GATING_NOTE = (
    "NON_GATING until a full 50-seed manifest exists; this report validates only the supplied "
    "active-window cohort and is not consumed by shared H12 gates or indexes."
)


@dataclass(frozen=True)
class TraceWindowEntry:
    seed: int
    process: str
    trace_path: Path
    trace_sha256: str
    trace_schema: str
    trace_tick_start: int
    trace_tick_end: int
    window_tick_start: int
    window_tick_end: int
    window_length_ticks: int
    first_regime_valid_transferase_tick: int | None = None
    window_selection: str | None = None

    @property
    def trace_length_ticks(self) -> int:
        return self.trace_tick_end - self.trace_tick_start + 1

    @property
    def slice_start_0b(self) -> int:
        return self.window_tick_start - self.trace_tick_start

    @property
    def slice_stop_0b(self) -> int:
        return self.slice_start_0b + self.window_length_ticks

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "process": self.process,
            "trace_path": _path_for_record(self.trace_path),
            "trace_sha256": self.trace_sha256,
            "trace_schema": self.trace_schema,
            "trace_tick_start": self.trace_tick_start,
            "trace_tick_end": self.trace_tick_end,
            "window_tick_start": self.window_tick_start,
            "window_tick_end": self.window_tick_end,
            "window_length_ticks": self.window_length_ticks,
            "first_regime_valid_transferase_tick": self.first_regime_valid_transferase_tick,
            "window_selection": self.window_selection,
        }


def _path_for_record(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _oracle_manifest_relative_path(trace_path: Path) -> str | None:
    parts = trace_path.resolve().parts
    marker = ("data", "m1_sources", "karr_native")
    for idx in range(len(parts) - len(marker) + 1):
        if tuple(parts[idx : idx + len(marker)]) == marker:
            return Path(*parts[idx + len(marker) :]).as_posix()
    return None


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _require_plain_positive_int(value: Any, *, field_name: str) -> int:
    if not (h12._is_plain_nonneg_int(value) and value >= 1):  # noqa: SLF001 - shared validator helper
        raise ValueError(f"{field_name} must be a positive integer (got {value!r})")
    return int(value)


def _load_oracle_slice(path: Path, start_0b: int, n_ticks: int) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    before: dict[str, np.ndarray] = {}
    after: dict[str, np.ndarray] = {}
    with h5py.File(path, "r") as handle:
        avail_ticks = int(np.asarray(handle["metadata"]["n_ticks"][()]).ravel()[0])
        if start_0b < 0 or n_ticks < 0 or start_0b + n_ticks > avail_ticks:
            raise ValueError(
                f"requested slice [{start_0b}:{start_0b + n_ticks}) lies outside source trace with {avail_ticks} ticks"
            )
        for phase_name, phase_dict in (("states_before", before), ("states_after", after)):
            group = handle[phase_name]
            for channel in group:
                refs = group[channel][0, start_0b : start_0b + n_ticks]
                rows = [np.asarray(handle[ref][()]).ravel() for ref in refs]
                phase_dict[channel] = np.stack(rows, axis=0)
    return before, after


def load_trace_window_manifest(manifest_path: Path) -> tuple[dict[int, TraceWindowEntry], dict[str, Any]]:
    payload = _load_json(manifest_path)
    if payload.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"trace-window manifest schema_version must be {MANIFEST_SCHEMA_VERSION!r} "
            f"(got {payload.get('schema_version')!r})"
        )
    if payload.get("process") != PROCESS:
        raise ValueError(
            f"trace-window manifest process must be {PROCESS!r} (got {payload.get('process')!r})"
        )
    manifest_window_ticks = payload.get("window_length_ticks")
    catalog_window_ticks = h12.CATALOG_N_M[PROCESS][1]
    if manifest_window_ticks != catalog_window_ticks:
        raise ValueError(
            f"trace-window manifest window_length_ticks must equal catalog M_ticks={catalog_window_ticks} "
            f"(got {manifest_window_ticks!r})"
        )
    entries_payload = payload.get("entries")
    if not isinstance(entries_payload, dict) or not entries_payload:
        raise ValueError("trace-window manifest entries must be a non-empty dict keyed by seed")

    entries: dict[int, TraceWindowEntry] = {}
    for seed_key, entry_payload in entries_payload.items():
        if not isinstance(entry_payload, dict):
            raise ValueError(f"trace-window entry for seed key {seed_key!r} is not an object")

        seed = entry_payload.get("seed")
        if not h12._is_plain_nonneg_int(seed):  # noqa: SLF001 - shared validator helper
            raise ValueError(f"trace-window entry {seed_key!r} has invalid seed {seed!r}")
        if str(seed) != str(seed_key):
            raise ValueError(f"trace-window entry key/seed mismatch: key={seed_key!r} seed={seed!r}")
        if entry_payload.get("process") != PROCESS:
            raise ValueError(
                f"trace-window entry seed={seed} process {entry_payload.get('process')!r} "
                f"does not match manifest process {PROCESS!r}"
            )

        trace_path_value = entry_payload.get("trace_path")
        if not isinstance(trace_path_value, str) or not trace_path_value:
            raise ValueError(f"trace-window entry seed={seed} trace_path must be a non-empty string")
        trace_path = Path(trace_path_value)
        if not trace_path.is_absolute():
            trace_path = (manifest_path.parent / trace_path).resolve()
        if not trace_path.is_file():
            raise FileNotFoundError(f"trace-window entry seed={seed} source trace missing: {trace_path}")

        trace_sha256 = entry_payload.get("trace_sha256")
        if not (isinstance(trace_sha256, str) and h12._SHA256_HEX_RE.fullmatch(trace_sha256)):  # noqa: SLF001
            raise ValueError(f"trace-window entry seed={seed} trace_sha256 is not a lowercase hex sha256")

        trace_schema = entry_payload.get("trace_schema")
        if not isinstance(trace_schema, str) or not trace_schema:
            raise ValueError(f"trace-window entry seed={seed} trace_schema must be a non-empty string")

        trace_tick_start = _require_plain_positive_int(entry_payload.get("trace_tick_start"), field_name="trace_tick_start")
        trace_tick_end = _require_plain_positive_int(entry_payload.get("trace_tick_end"), field_name="trace_tick_end")
        window_tick_start = _require_plain_positive_int(
            entry_payload.get("window_tick_start"), field_name="window_tick_start"
        )
        window_tick_end = _require_plain_positive_int(entry_payload.get("window_tick_end"), field_name="window_tick_end")
        window_length_ticks = _require_plain_positive_int(
            entry_payload.get("window_length_ticks"), field_name="window_length_ticks"
        )

        if trace_tick_end < trace_tick_start:
            raise ValueError(f"trace-window entry seed={seed} trace_tick_end precedes trace_tick_start")
        if window_tick_end < window_tick_start:
            raise ValueError(f"trace-window entry seed={seed} window_tick_end precedes window_tick_start")
        if window_length_ticks != catalog_window_ticks:
            raise ValueError(
                f"trace-window entry seed={seed} window_length_ticks={window_length_ticks} "
                f"!= catalog M_ticks={catalog_window_ticks}"
            )
        if window_tick_end - window_tick_start + 1 != window_length_ticks:
            raise ValueError(
                f"trace-window entry seed={seed} window span {window_tick_end - window_tick_start + 1} "
                f"!= window_length_ticks {window_length_ticks}"
            )
        if window_tick_start < trace_tick_start or window_tick_end > trace_tick_end:
            raise ValueError(
                f"trace-window entry seed={seed} window [{window_tick_start}, {window_tick_end}] "
                f"lies outside source trace [{trace_tick_start}, {trace_tick_end}]"
            )

        first_tick_raw = entry_payload.get("first_regime_valid_transferase_tick")
        first_tick = None
        if first_tick_raw is not None:
            first_tick = _require_plain_positive_int(
                first_tick_raw, field_name="first_regime_valid_transferase_tick"
            )
            if not (trace_tick_start <= first_tick <= trace_tick_end):
                raise ValueError(
                    f"trace-window entry seed={seed} first_regime_valid_transferase_tick {first_tick} "
                    "lies outside the source trace"
                )
            if not (window_tick_start <= first_tick <= window_tick_end):
                raise ValueError(
                    f"trace-window entry seed={seed} first_regime_valid_transferase_tick {first_tick} "
                    "lies outside the chosen window"
                )

        window_selection = entry_payload.get("window_selection")
        if window_selection is not None and not isinstance(window_selection, str):
            raise ValueError(f"trace-window entry seed={seed} window_selection must be a string if present")

        if seed in entries:
            raise ValueError(f"trace-window manifest contains duplicate seed entry {seed}")
        entries[seed] = TraceWindowEntry(
            seed=int(seed),
            process=PROCESS,
            trace_path=trace_path,
            trace_sha256=trace_sha256,
            trace_schema=trace_schema,
            trace_tick_start=trace_tick_start,
            trace_tick_end=trace_tick_end,
            window_tick_start=window_tick_start,
            window_tick_end=window_tick_end,
            window_length_ticks=window_length_ticks,
            first_regime_valid_transferase_tick=first_tick,
            window_selection=window_selection,
        )

    return entries, payload


def load_seed_window(entry: TraceWindowEntry) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], str]:
    structural = validate_structural(
        entry.trace_path,
        expected_process=PROCESS,
        expected_seed=entry.seed,
        expected_n_ticks=entry.trace_length_ticks,
        compute_hash=True,
    )
    if not structural.ok:
        raise ValueError(
            f"trace-window entry seed={entry.seed} failed structural validation: {'; '.join(structural.errors)}"
        )
    assert structural.sha256 is not None
    if structural.sha256 != entry.trace_sha256:
        raise ValueError(
            f"trace-window entry seed={entry.seed} source hash mismatch: "
            f"manifest={entry.trace_sha256} disk={structural.sha256}"
        )
    before, after = _load_oracle_slice(entry.trace_path, entry.slice_start_0b, entry.window_length_ticks)
    return before, after, structural.sha256


def _load_full_source_trace(entry: TraceWindowEntry) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    return _load_oracle_slice(entry.trace_path, 0, entry.trace_length_ticks)


def _derive_first_regime_valid_transferase_tick(
    entry: TraceWindowEntry,
    fixture: dict[str, Any],
) -> int | None:
    before, _after = _load_full_source_trace(entry)
    predictor = h12.PREDICTORS[PROCESS]
    predictions = predictor(entry.seed, before, fixture)
    first_tick = None
    for prediction in predictions:
        if prediction.regime_valid and "transferase_fires" in prediction.branch_tags:
            candidate = entry.trace_tick_start + int(prediction.tick)
            if first_tick is None or candidate < first_tick:
                first_tick = candidate
    return first_tick


def _seed_report_status(entry: TraceWindowEntry, compare_result: dict[str, Any], derived_first_tick: int | None) -> dict[str, Any]:
    confirmed_branches = set(compare_result["branches_confirmed"])
    transferase_confirmed = "transferase_fires" in confirmed_branches
    return {
        "seed": entry.seed,
        "trace_path": _path_for_record(entry.trace_path),
        "trace_sha256": entry.trace_sha256,
        "trace_tick_start": entry.trace_tick_start,
        "trace_tick_end": entry.trace_tick_end,
        "window_tick_start": entry.window_tick_start,
        "window_tick_end": entry.window_tick_end,
        "window_length_ticks": entry.window_length_ticks,
        "recorded_first_regime_valid_transferase_tick": entry.first_regime_valid_transferase_tick,
        "derived_first_regime_valid_transferase_tick": derived_first_tick,
        "window_contains_confirmed_transferase_fires": transferase_confirmed,
        "exact_match_count": compare_result["exact_match_count"],
        "nontrivial_sample_count": compare_result["nontrivial_sample_count"],
        "branches_confirmed": sorted(confirmed_branches),
        "branches_observed": sorted(compare_result["branches_observed"]),
        "oracle_manifest_cross_check": "pending",
    }


def build_active_window_validation_artifact(
    manifest_path: Path,
    *,
    require_full_catalog: bool = False,
) -> dict[str, Any]:
    entries, manifest_payload = load_trace_window_manifest(manifest_path)
    fixture = h12.load_fixture(PROCESS)
    predictor = h12.PREDICTORS[PROCESS]
    required_branches = h12.REQUIRED_BRANCHES[PROCESS]
    catalog_n_seeds, catalog_m_ticks = h12.CATALOG_N_M[PROCESS]
    manifest_lookup = h12._load_oracle_manifest()  # noqa: SLF001 - shared oracle provenance helper

    all_predictions: list[h12.UnitPrediction] = []
    preds_by_seed: dict[int, list[h12.UnitPrediction]] = {}
    prediction_hash_parts: list[str] = []
    window_seed_source_sha256: dict[str, str] = {}
    oracle_manifest_cross_check: dict[str, str] = {}
    seed_windows_verified: dict[str, Any] = {}

    for seed in sorted(entries):
        entry = entries[seed]
        before, after, sha = load_seed_window(entry)
        derived_first_tick = _derive_first_regime_valid_transferase_tick(entry, fixture)
        if derived_first_tick is None:
            raise ValueError(
                f"trace-window entry seed={seed} did not re-derive any regime-valid transferase tick from the current trace"
            )
        if entry.first_regime_valid_transferase_tick is not None and derived_first_tick != entry.first_regime_valid_transferase_tick:
            raise ValueError(
                f"trace-window entry seed={seed} first_regime_valid_transferase_tick mismatch: "
                f"manifest={entry.first_regime_valid_transferase_tick} derived={derived_first_tick}"
            )

        preds = predictor(seed, before, fixture)
        all_predictions.extend(preds)
        preds_by_seed[seed] = preds
        for prediction in preds:
            prediction_hash_parts.append(
                f"{prediction.seed}:{prediction.tick}:{prediction.unit}:{prediction.regime_valid}:{prediction.nontrivial}:"
                + ",".join(
                    f"{channel}={h12._sha256_array(delta)}"  # noqa: SLF001 - shared artifact hash helper
                    for channel, delta in sorted(prediction.predicted_delta.items())
                    if isinstance(delta, np.ndarray)
                )
            )

        compare_result = h12.compare_predictions(PROCESS, preds, after, before)
        seed_report = _seed_report_status(entry, compare_result, derived_first_tick)
        rel_trace = _oracle_manifest_relative_path(entry.trace_path)
        if rel_trace is None:
            cross_check = "accepted_external_fixture"
        else:
            manifest_rel_trace = f"per_process_traces_v2/{rel_trace}" if rel_trace.startswith(f"{PROCESS}_") else rel_trace
            cross_check = h12.cross_check_oracle_manifest(PROCESS, manifest_rel_trace, sha, manifest_lookup)
            if cross_check != "match":
                raise ValueError(
                    f"trace-window entry seed={seed} oracle population cross-check failed: {cross_check}"
                )
        seed_report["oracle_manifest_cross_check"] = cross_check
        if not seed_report["window_contains_confirmed_transferase_fires"]:
            raise ValueError(
                f"trace-window entry seed={seed} does not actually confirm transferase_fires inside the chosen window"
            )

        window_seed_source_sha256[str(seed)] = sha
        oracle_manifest_cross_check[str(seed)] = cross_check
        seed_windows_verified[str(seed)] = seed_report

    raw_prediction_hash = h12._sha256_bytes("\n".join(prediction_hash_parts).encode("utf-8"))  # noqa: SLF001

    total = nontrivial = exact_match = trivial_checked = trivial_mismatch_count = 0
    mismatches: list[dict[str, Any]] = []
    trivial_mismatches: list[dict[str, Any]] = []
    branches_confirmed: set[str] = set()
    branches_observed: set[str] = set()
    for seed in sorted(entries):
        entry = entries[seed]
        before, after, _sha = load_seed_window(entry)
        result = h12.compare_predictions(PROCESS, preds_by_seed[seed], after, before)
        total += result["total_sample_count"]
        nontrivial += result["nontrivial_sample_count"]
        exact_match += result["exact_match_count"]
        trivial_checked += result["trivial_checked_count"]
        trivial_mismatch_count += result["trivial_mismatch_count"]
        branches_confirmed |= result["branches_confirmed"]
        branches_observed |= result["branches_observed"]
        if len(mismatches) < 10:
            mismatches.extend(result["mismatch_examples"][: 10 - len(mismatches)])
        if len(trivial_mismatches) < 10:
            trivial_mismatches.extend(result["trivial_mismatch_examples"][: 10 - len(trivial_mismatches)])

    exact_match_rate = (exact_match / nontrivial) if nontrivial > 0 else None
    window_verdict, window_verdict_reason = h12.decide_verdict(
        nontrivial,
        exact_match,
        exact_match_rate,
        trivial_mismatch_count,
        branches_confirmed,
        required_branches,
    )

    missing_catalog_seeds = sorted(set(range(catalog_n_seeds)) - set(entries))
    shared_h12_promotion_ready = not missing_catalog_seeds and window_verdict == "H12_CONFIRMED"
    promotion_blockers: list[str] = []
    if missing_catalog_seeds:
        promotion_blockers.append(
            f"manifest covers {len(entries)}/{catalog_n_seeds} seeds; remaining seeds require real-MATLAB extraction"
        )
    if window_verdict != "H12_CONFIRMED":
        promotion_blockers.append(f"window_verdict={window_verdict}")
    if require_full_catalog and missing_catalog_seeds:
        promotion_blockers.append("require_full_catalog=True")

    shared_h12_path = REPO_ROOT / h12.EXPECTED_PREDICTOR_SOURCE_PATH
    generator_path = REPO_ROOT / GENERATOR_SOURCE_PATH
    artifact = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_version": ARTIFACT_VERSION,
        "classification": CLASSIFICATION,
        "gating": NON_GATING_NOTE,
        "process": PROCESS,
        "not_consumed_by": list(EXPECTED_NOT_CONSUMED_BY),
        "manifest_ref": {
            "path": _path_for_record(manifest_path),
            "sha256_lf_normalized": h12._sha256_lf_normalized(manifest_path),  # noqa: SLF001
            "schema_version": manifest_payload["schema_version"],
        },
        "generator_source_path": GENERATOR_SOURCE_PATH,
        "generator_source_sha256_lf_normalized": h12._sha256_lf_normalized(generator_path),  # noqa: SLF001
        "shared_h12_predictor_source_path": h12.EXPECTED_PREDICTOR_SOURCE_PATH,
        "shared_h12_predictor_source_sha256_lf_normalized": h12._sha256_lf_normalized(shared_h12_path),  # noqa: SLF001
        "karr_source_citation": h12.karr_source_citation(PROCESS),
        "fixture_path": fixture["__fixture_path__"],
        "fixture_sha256": fixture["__fixture_sha256__"],
        "manifest_seed_count": len(entries),
        "catalog_n_seeds": catalog_n_seeds,
        "window_length_ticks": catalog_m_ticks,
        "missing_catalog_seeds": missing_catalog_seeds,
        "license_blocked_missing_seeds": missing_catalog_seeds,
        "window_seed_source_sha256": window_seed_source_sha256,
        "oracle_manifest_cross_check": oracle_manifest_cross_check,
        "seed_windows_verified": seed_windows_verified,
        "total_sample_count": total,
        "nontrivial_sample_count": nontrivial,
        "exact_match_count": exact_match,
        "exact_match_rate": exact_match_rate,
        "trivial_checked_count": trivial_checked,
        "trivial_mismatch_count": trivial_mismatch_count,
        "mismatch_examples": mismatches,
        "trivial_mismatch_examples": trivial_mismatches,
        "required_branches": sorted(required_branches),
        "branches_confirmed": sorted(branches_confirmed),
        "branches_observed": sorted(branches_observed),
        "missing_required_branches": sorted(required_branches - branches_confirmed),
        "raw_prediction_hash": raw_prediction_hash,
        "window_verdict": window_verdict,
        "window_verdict_reason": window_verdict_reason,
        "shared_h12_promotion_ready": shared_h12_promotion_ready,
        "shared_h12_promotion_blockers": promotion_blockers,
        "generated_at": datetime.now(UTC).isoformat(),
        "anti_laundering_attestation": {
            "predictor_inputs": ["states_before", "static_fixture_params"],
            "states_after_access": "compare_phase_only",
            "no_sut_import": True,
            "no_result_json_access": True,
            "shared_h12_source_unchanged": True,
        },
    }
    return artifact


def validate_active_window_artifact(payload: dict[str, Any], *, repo_root: Path = REPO_ROOT) -> str | None:
    if payload.get("artifact_kind") != ARTIFACT_KIND:
        return f"artifact_kind != {ARTIFACT_KIND!r} (got {payload.get('artifact_kind')!r})"
    if payload.get("artifact_version") != ARTIFACT_VERSION:
        return f"artifact_version != {ARTIFACT_VERSION!r} (got {payload.get('artifact_version')!r})"
    if payload.get("classification") != CLASSIFICATION:
        return f"classification != {CLASSIFICATION!r} (got {payload.get('classification')!r})"
    if payload.get("process") != PROCESS:
        return f"process != {PROCESS!r} (got {payload.get('process')!r})"
    if payload.get("not_consumed_by") != EXPECTED_NOT_CONSUMED_BY:
        return "not_consumed_by drifted from the pinned shared-index isolation contract"

    manifest_ref = payload.get("manifest_ref") or {}
    manifest_path = repo_root / manifest_ref.get("path", "")
    if manifest_ref.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        return f"manifest_ref.schema_version != {MANIFEST_SCHEMA_VERSION!r}"
    if not manifest_path.is_file():
        return f"manifest_ref.path does not exist on disk: {manifest_ref.get('path')!r}"
    current_manifest_hash = h12._sha256_lf_normalized(manifest_path)  # noqa: SLF001
    if manifest_ref.get("sha256_lf_normalized") != current_manifest_hash:
        return (
            "manifest_ref sha256 is stale/tampered: "
            f"recorded={manifest_ref.get('sha256_lf_normalized')!r} current={current_manifest_hash!r}"
        )

    generator_path = payload.get("generator_source_path")
    if generator_path != GENERATOR_SOURCE_PATH:
        return f"generator_source_path != {GENERATOR_SOURCE_PATH!r} (got {generator_path!r})"
    current_generator_hash = h12._sha256_lf_normalized(repo_root / GENERATOR_SOURCE_PATH)  # noqa: SLF001
    if payload.get("generator_source_sha256_lf_normalized") != current_generator_hash:
        return "generator_source_sha256_lf_normalized is stale/tampered"

    shared_h12_path = payload.get("shared_h12_predictor_source_path")
    if shared_h12_path != h12.EXPECTED_PREDICTOR_SOURCE_PATH:
        return (
            "shared_h12_predictor_source_path drifted from the pinned shared H12 module "
            f"(got {shared_h12_path!r})"
        )
    current_shared_h12_hash = h12._sha256_lf_normalized(repo_root / h12.EXPECTED_PREDICTOR_SOURCE_PATH)  # noqa: SLF001
    if payload.get("shared_h12_predictor_source_sha256_lf_normalized") != current_shared_h12_hash:
        return "shared_h12_predictor_source_sha256_lf_normalized is stale/tampered"

    fixture_path_recorded = payload.get("fixture_path")
    fixture_sha_recorded = payload.get("fixture_sha256")
    fixture_path = repo_root / fixture_path_recorded
    if not fixture_path.is_file():
        return f"fixture_path does not exist on disk: {fixture_path_recorded!r}"
    if fixture_sha_recorded != h12._sha256_file(fixture_path):  # noqa: SLF001
        return "fixture_sha256 is stale/tampered"

    expected_karr = h12.karr_source_citation(PROCESS)
    recorded_karr = payload.get("karr_source_citation") or {}
    if recorded_karr != expected_karr:
        return "karr_source_citation drifted from the current shared H12 citation registry"

    seed_hashes = payload.get("window_seed_source_sha256")
    seed_windows = payload.get("seed_windows_verified")
    if not isinstance(seed_hashes, dict) or not seed_hashes:
        return "window_seed_source_sha256 missing/empty"
    if not isinstance(seed_windows, dict) or set(seed_windows) != set(seed_hashes):
        return "seed_windows_verified missing/empty or not aligned with window_seed_source_sha256"
    for seed, recorded_hash in seed_hashes.items():
        entry = seed_windows[seed]
        trace_path = repo_root / entry["trace_path"]
        if not trace_path.is_file():
            return f"seed {seed} trace_path missing on disk: {entry['trace_path']!r}"
        current_hash = h12._sha256_file(trace_path)  # noqa: SLF001
        if current_hash != recorded_hash:
            return f"seed {seed} source trace hash stale/tampered"

    if payload.get("shared_h12_promotion_ready") is True:
        if payload.get("manifest_seed_count") != h12.CATALOG_N_M[PROCESS][0]:
            return "shared_h12_promotion_ready cannot be True on partial seed coverage"
        if payload.get("window_verdict") != "H12_CONFIRMED":
            return "shared_h12_promotion_ready cannot be True unless window_verdict is H12_CONFIRMED"

    attestation = payload.get("anti_laundering_attestation") or {}
    if attestation.get("no_sut_import") is not True:
        return "anti_laundering_attestation.no_sut_import is not True"
    if attestation.get("no_result_json_access") is not True:
        return "anti_laundering_attestation.no_result_json_access is not True"
    if attestation.get("states_after_access") != "compare_phase_only":
        return "anti_laundering_attestation.states_after_access != 'compare_phase_only'"
    if attestation.get("shared_h12_source_unchanged") is not True:
        return "anti_laundering_attestation.shared_h12_source_unchanged is not True"

    return None


def write_artifact(payload: dict[str, Any], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=False)
        fh.write("\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate ProteinProcessingII active-window manifests without editing shared h12.py")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_PATH)
    parser.add_argument(
        "--require-full-catalog",
        action="store_true",
        help="Exit nonzero unless the manifest covers all 50 seeds and the shared H12 predictor confirms every required branch.",
    )
    args = parser.parse_args(argv)

    artifact = build_active_window_validation_artifact(
        args.manifest,
        require_full_catalog=args.require_full_catalog,
    )
    out_path = write_artifact(artifact, args.out)
    validation_error = validate_active_window_artifact(artifact)
    if validation_error is not None:
        print(f"[ppii-active-windows] self-validation failed: {validation_error}", file=sys.stderr)
        return 2

    print(
        f"[ppii-active-windows] seeds={artifact['manifest_seed_count']}/{artifact['catalog_n_seeds']} "
        f"window_verdict={artifact['window_verdict']} promotion_ready={artifact['shared_h12_promotion_ready']} "
        f"-> {out_path}",
        file=sys.stderr,
    )
    if args.require_full_catalog and not artifact["shared_h12_promotion_ready"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
