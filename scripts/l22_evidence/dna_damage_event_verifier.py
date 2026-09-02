"""Replay the accepted genuine DNADamage stimulus cohort into tracked L2.2 authority.

This module is the DNADamage event-class counterpart to
`scripts/l22_evidence/event_bridge.py`: it does not launch MATLAB or
re-extract Karr. Instead, it validates the accepted local genuine
stimulus-conditioned Karr corpus, replays the FIXED OpenCell DNADamage
process against the recorded `states_before` windows, computes the catalog's
primary chromosome hurdle metric, and writes a tracked
`docs/phase_f/l2_2_design_a/evidence_bundle/DNADamage/latest_event/`
authority bundle plus tracked canary/full verifier JSONs.

The accepted corpus (`genuine_signedzero_canary_v4` / `genuine_signedzero_full_v2`,
re-extracted 2026-09-02 after the karr_bootstrap.m raw-byte overlay-hash fix)
carries `dnadamage_source_*_sha256`/`_resolved_path` overlay-hash metadata on
every trace. This module requires those fields to be present on every trace
and fails closed (raises `VerifierError`) if any are missing -- it never
silently tolerates a legacy/unhashed corpus as an acceptable input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import h5py
import numpy as np

_REPO_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
for _extra in (
    _REPO_ROOT_BOOTSTRAP,
    _REPO_ROOT_BOOTSTRAP / "tests" / "vivarium",
):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from l2_replay_common import (  # noqa: E402
    apply_count_update,
    assert_delta_integral,
    build_state_template,
    cell_vector,
    collect_count_delta_dicts,
    infer_wids_for_observable,
    overlay_observable_into_state,
    refresh_allocator_views,
)

from opencell.state.chromosome_store import ChromosomeStore, SparseTriplet  # noqa: E402
from opencell.vivarium.karr_dna_damage import KarrDNADamageProcess  # noqa: E402
from scripts.l2_event import dna_damage_stimulus_cohort as cohort  # noqa: E402
from scripts.l22_evidence import catalog as cat  # noqa: E402
from scripts.l22_evidence import schema, sweep  # noqa: E402
from scripts.l22_evidence import verdict as vd  # noqa: E402
from scripts.l22_evidence.populate import _git_dirty, _git_sha  # noqa: E402
from tests.vivarium._l2_2_design_a_projections import (  # noqa: E402
    hurdle_event_rate_plus_conditional_scaled_distance,
)

PROCESS = "DNADamage"
CONDITION = "uvb_mechanism"
TRACE_FILENAME = f"{PROCESS}_20ticks.mat"
CANARY_ROOT = (
    cat.REPO_ROOT
    / "data"
    / "m1_sources"
    / "karr_native"
    / "genuine_signedzero_canary_v4"
    / cohort.CONDITION_ROOT_DIRNAME
    / CONDITION
)
FULL_ROOT = (
    cat.REPO_ROOT
    / "data"
    / "m1_sources"
    / "karr_native"
    / "genuine_signedzero_full_v2"
    / cohort.CONDITION_ROOT_DIRNAME
    / CONDITION
)
PRIMARY_PROJECTION = (
    "damage_event_present",
    "damagedBases.delta_nnz",
    "abasicSites.delta_nnz",
    "strandBreaks.delta_nnz",
    "damagedSugarPhosphates.delta_nnz",
    "intrastrandCrossLinks.delta_nnz",
    "hollidayJunctions.delta_nnz",
    "gapSites.delta_nnz",
)
PRIMARY_FIELDS = tuple(token.split(".", 1)[0] for token in PRIMARY_PROJECTION[1:])
OBSERVABLES = ("substrates", "enzymes", "boundEnzymes")
OBSERVABLE_TO_WIDS_ATTR = {
    "substrates": "substrate_wids",
    "enzymes": "enzyme_wids",
    "boundEnzymes": "enzyme_wids",
}
REQUIRED_OVERLAY_HASH_FIELDS = (
    "dnadamage_source_original_sha256",
    "dnadamage_source_patched_sha256",
    "dnadamage_source_resolved_sha256",
    "dnadamage_source_resolved_path",
)
# Classification constant, not a biology parameter: any accepted stimulus
# trace should vastly exceed this floor relative to the frozen injected dose.
STIMULUS_CLASSIFICATION_MIN_DOSE_FRACTION = 0.01


class VerifierError(RuntimeError):
    """Raised when the accepted corpus or replay bundle is not trustworthy."""


def _entry() -> cat.ProcessEntry:
    try:
        return cat.in_scope_processes()[PROCESS]
    except KeyError as exc:
        raise VerifierError(f"{PROCESS} is not present in PROCESS_CATALOG.yaml in-scope entries") from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(payload))


def _relative(path: Path) -> str:
    return cat.relative_to_repo(path)


def _decode_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    arr = np.asarray(value)
    if arr.dtype.kind in {"U", "S"}:
        flat = arr.reshape(-1)
        if arr.dtype.kind == "S":
            return b"".join(
                bytes(item) if isinstance(item, (bytes, bytearray)) else str(item).encode("utf-8")
                for item in flat
            ).decode("utf-8", errors="replace").rstrip("\x00")
        return "".join(str(item) for item in flat).rstrip("\x00")
    if arr.dtype.kind in {"u", "i"}:
        return "".join(chr(int(code)) for code in arr.reshape(-1) if int(code) != 0)
    return str(value)


def _metadata_text(handle: h5py.File, key: str) -> str | None:
    meta = handle.get("metadata")
    if meta is None or key not in meta:
        return None
    return _decode_text(meta[key][()])


def _metadata_int(handle: h5py.File, key: str) -> int | None:
    meta = handle.get("metadata")
    if meta is None or key not in meta:
        return None
    arr = np.asarray(meta[key][()]).reshape(-1)
    if arr.size == 0:
        return None
    return int(arr[0])


def _chromosome_store_for_tick(handle: h5py.File, group: str, tick: int) -> ChromosomeStore:
    dataset = handle[f"{group}/chromosome"]
    ref = dataset[0, tick] if dataset.shape[0] == 1 else dataset[tick, 0]
    return ChromosomeStore.from_hdf5_group(handle[ref])


def _overlay_chromosome_state(state: dict[str, Any], store: ChromosomeStore) -> None:
    chrom_state = state.setdefault("chromosome", {})
    if not isinstance(chrom_state, dict):
        raise TypeError("state['chromosome'] must be a dict")
    chrom_state.update(store.to_state())


def _apply_update(
    state: dict[str, Any],
    update: dict[str, Any],
    process: KarrDNADamageProcess,
) -> None:
    for label, deltas in collect_count_delta_dicts(update):
        assert_delta_integral(label, deltas)
    apply_count_update(state, update)

    chrom_update = update.get("chromosome", {})
    if not isinstance(chrom_update, dict):
        return
    chrom_state = state.setdefault("chromosome", {})
    if not isinstance(chrom_state, dict):
        raise TypeError("state['chromosome'] must be a dict")

    if "damage_events_cumulative" in chrom_update:
        existing = chrom_state.get("damage_events_cumulative", [])
        if not isinstance(existing, list):
            existing = []
        chrom_state["damage_events_cumulative"] = existing + list(chrom_update["damage_events_cumulative"])
    if "repair_events_cumulative" in chrom_update:
        existing = chrom_state.get("repair_events_cumulative", [])
        if not isinstance(existing, list):
            existing = []
        chrom_state["repair_events_cumulative"] = existing + list(chrom_update["repair_events_cumulative"])
    if "replication_stall_flag" in chrom_update:
        chrom_state["replication_stall_flag"] = float(
            float(chrom_state.get("replication_stall_flag", 0.0))
            + float(chrom_update["replication_stall_flag"])
        )
    if "replication_state" in chrom_update:
        chrom_state["replication_state"] = str(chrom_update["replication_state"])
    if "fork_position_bp" in chrom_update:
        chrom_state["fork_position_bp"] = dict(chrom_update["fork_position_bp"])
    for field in PRIMARY_FIELDS:
        if field in chrom_update:
            chrom_state[field] = SparseTriplet.from_state(
                chrom_update[field],
                shape=process.chromosome_shape,
            ).to_state()


def _projection_from_stores(
    before_store: ChromosomeStore,
    after_store: ChromosomeStore,
    *,
    allowed_fields: tuple[str, ...],
) -> tuple[np.ndarray, list[str]]:
    deltas: list[float] = []
    positive_fields: list[str] = []
    for field in PRIMARY_FIELDS:
        delta_nnz = after_store.calc_num_edges(field) - before_store.calc_num_edges(field)
        if delta_nnz < 0:
            raise VerifierError(f"{field} unexpectedly decreased (delta_nnz={delta_nnz})")
        deltas.append(float(delta_nnz))
        if delta_nnz > 0:
            positive_fields.append(field)
    event_present = float(any(field in allowed_fields for field in positive_fields))
    return np.asarray([event_present] + deltas, dtype=np.float64), positive_fields


def _expected_trace_paths(root: Path, seed_labels: list[int]) -> list[Path]:
    return [root / f"per_process_traces_v2_event_s{seed}" / TRACE_FILENAME for seed in seed_labels]


def _validate_root_layout(root: Path, seed_labels: list[int]) -> list[Path]:
    if not root.is_dir():
        raise VerifierError(f"accepted corpus root is missing: {root}")
    expected = _expected_trace_paths(root, seed_labels)
    missing = [path for path in expected if not path.is_file()]
    if missing:
        raise VerifierError(f"accepted corpus {root} is missing expected trace(s): {[str(p) for p in missing]}")
    found = sorted(root.glob(f"per_process_traces_v2_event_s*/{TRACE_FILENAME}"))
    found_set = {path.resolve() for path in found}
    expected_set = {path.resolve() for path in expected}
    extra = sorted(found_set - expected_set)
    if extra:
        raise VerifierError(f"accepted corpus {root} has unexpected extra trace(s): {[str(p) for p in extra]}")
    return expected


def _trace_max_radiation_values(handle: h5py.File) -> dict[str, float]:
    process = KarrDNADamageProcess({})
    uvb_idx = process.substrate_wids.index("UVB_radiation")
    gamma_idx = process.substrate_wids.index("gamma_radiation")
    maxima = {"UVB_radiation": 0.0, "gamma_radiation": 0.0}
    n_ticks = _metadata_int(handle, "n_ticks")
    if n_ticks is None:
        raise VerifierError("trace metadata missing n_ticks")
    for tick in range(n_ticks):
        vec = cell_vector(handle, "states_before", "substrates", tick)
        if uvb_idx < vec.size:
            maxima["UVB_radiation"] = max(maxima["UVB_radiation"], float(vec[uvb_idx]))
        if gamma_idx < vec.size:
            maxima["gamma_radiation"] = max(maxima["gamma_radiation"], float(vec[gamma_idx]))
    return maxima


def _identity_payload_matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(actual.get(key) == expected_value for key, expected_value in expected.items())


def _seed_index(seed_label: int, expected_seed_labels: list[int]) -> int:
    try:
        return expected_seed_labels.index(seed_label)
    except ValueError as exc:
        raise VerifierError(f"seed label {seed_label} is not in expected corpus seed set {expected_seed_labels!r}") from exc


def verify_corpus(
    *,
    root: Path,
    expected_seed_labels: list[int],
) -> dict[str, Any]:
    spec = cohort.load_stimulus_spec()
    expected_identity = cohort.condition_identity_payload(spec, CONDITION)
    expected_paths = _validate_root_layout(root, expected_seed_labels)
    expected_dose_uvb = float(spec["conditions"]["uvb_mechanism"]["injected_radiation_value"])
    expected_dose_gamma = float(spec["conditions"]["gamma_mechanism"]["injected_radiation_value"])
    allowed_fields = tuple(str(field) for field in expected_identity["allowed_chromosome_fields"])

    karr_projections: list[np.ndarray] = []
    oc_projections: list[np.ndarray] = []
    trace_classifications: list[dict[str, Any]] = []
    identity_validation_failures: list[dict[str, Any]] = []
    metadata_hash_field_present_counts = {field: 0 for field in REQUIRED_OVERLAY_HASH_FIELDS}
    run_labels: set[str] = set()
    condition_labels: set[str] = set()
    provider_kind_values: set[str] = set()
    statistics_rng_provider_values: set[str] = set()
    input_records: list[dict[str, Any]] = []

    for expected_path in expected_paths:
        trace_sha = _sha256_file(expected_path)
        with h5py.File(expected_path, "r") as handle:
            seed_label = _metadata_int(handle, "rng_seed")
            if seed_label is None:
                raise VerifierError(f"trace {expected_path} is missing metadata/rng_seed")
            expected_seed = expected_seed_labels[_seed_index(seed_label, expected_seed_labels)]
            if seed_label != expected_seed:
                raise VerifierError(
                    f"trace {expected_path} reports rng_seed={seed_label}, expected {expected_seed}"
                )
            n_ticks = _metadata_int(handle, "n_ticks")
            if n_ticks != _entry().m_ticks:
                raise VerifierError(f"trace {expected_path} n_ticks={n_ticks} != expected {_entry().m_ticks}")
            condition_label = _metadata_text(handle, "condition_label") or ""
            if condition_label != CONDITION:
                identity_validation_failures.append(
                    {
                        "path": _relative(expected_path),
                        "reason": f"condition_label {condition_label!r} != expected {CONDITION!r}",
                    }
                )
            condition_labels.add(condition_label)
            extraction_identity_json = _metadata_text(handle, "extraction_identity_json")
            if extraction_identity_json is None:
                raise VerifierError(f"trace {expected_path} is missing metadata/extraction_identity_json")
            try:
                actual_identity = json.loads(extraction_identity_json)
            except json.JSONDecodeError as exc:
                raise VerifierError(f"trace {expected_path} metadata/extraction_identity_json is invalid JSON: {exc}") from exc
            if not _identity_payload_matches(actual_identity, expected_identity):
                identity_validation_failures.append(
                    {
                        "path": _relative(expected_path),
                        "reason": "current cohort contract fields do not match accepted trace identity payload",
                        "expected_subset": expected_identity,
                        "actual_identity": actual_identity,
                    }
                )
            evidence_run_label = actual_identity.get("evidence_run_label")
            if isinstance(evidence_run_label, str) and evidence_run_label:
                run_labels.add(evidence_run_label)
            provider_kind = _metadata_text(handle, "mnrnd_provider_kind")
            if provider_kind:
                provider_kind_values.add(provider_kind)
            statistics_rng_provider = _metadata_text(handle, "statistics_rng_provider_identity_json")
            if statistics_rng_provider:
                statistics_rng_provider_values.add(statistics_rng_provider)
            overlay_hash_missing_fields = [
                field for field in REQUIRED_OVERLAY_HASH_FIELDS if _metadata_text(handle, field) is None
            ]
            if overlay_hash_missing_fields:
                raise VerifierError(
                    f"trace {expected_path} is missing required overlay-hash provenance field(s) "
                    f"{overlay_hash_missing_fields!r} -- item 7/8 (Sept-2 review) requires every "
                    "DNADamage trace to carry original/patched/resolved overlay hashes; re-extract "
                    "with the hardened karr_bootstrap.m rather than accepting a legacy-corpus trace"
                )
            for field in REQUIRED_OVERLAY_HASH_FIELDS:
                metadata_hash_field_present_counts[field] += 1

            maxima = _trace_max_radiation_values(handle)
            is_stimulus_conditioned = (
                maxima["UVB_radiation"] >= expected_dose_uvb * STIMULUS_CLASSIFICATION_MIN_DOSE_FRACTION
                or maxima["gamma_radiation"] >= expected_dose_gamma * STIMULUS_CLASSIFICATION_MIN_DOSE_FRACTION
            )
            trace_classifications.append(
                {
                    "path": _relative(expected_path),
                    "classification": "stimulus_conditioned" if is_stimulus_conditioned else "vacuous_no_stimulus",
                    "observed_max_UVB_radiation": maxima["UVB_radiation"],
                    "observed_max_gamma_radiation": maxima["gamma_radiation"],
                    "spec_uvb_mechanism_injected_dose": expected_dose_uvb,
                    "spec_gamma_mechanism_injected_dose": expected_dose_gamma,
                }
            )

            process = KarrDNADamageProcess({"rng_seed": int(seed_label)})
            state_template = build_state_template(process)
            wids_by_observable: dict[str, list[str]] = {}
            for observable in OBSERVABLES:
                before_vec = cell_vector(handle, "states_before", observable, 0)
                wids_by_observable[observable] = infer_wids_for_observable(
                    process,
                    state_template,
                    observable,
                    karr_len=int(before_vec.shape[0]),
                    explicit_attr=OBSERVABLE_TO_WIDS_ATTR[observable],
                )

            karr_seed_projection = np.zeros((n_ticks, len(PRIMARY_PROJECTION)), dtype=np.float64)
            oc_seed_projection = np.zeros((n_ticks, len(PRIMARY_PROJECTION)), dtype=np.float64)
            for tick in range(n_ticks):
                state = build_state_template(process)
                before_vectors = {
                    observable: cell_vector(handle, "states_before", observable, tick)
                    for observable in OBSERVABLES
                }
                for observable in OBSERVABLES:
                    overlay_observable_into_state(
                        process=process,
                        state=state,
                        observable=observable,
                        vector=before_vectors[observable],
                        wids=wids_by_observable[observable],
                    )
                before_store = _chromosome_store_for_tick(handle, "states_before", tick)
                after_store = _chromosome_store_for_tick(handle, "states_after", tick)
                _overlay_chromosome_state(state, before_store)
                refresh_allocator_views(process, state)
                update = process.next_update(1.0, state)
                _apply_update(state, update, process)
                oc_store = ChromosomeStore.from_state_mapping(
                    state.get("chromosome", {}),
                    shape=process.chromosome_shape,
                )
                karr_projection, _ = _projection_from_stores(before_store, after_store, allowed_fields=allowed_fields)
                oc_projection, _ = _projection_from_stores(before_store, oc_store, allowed_fields=allowed_fields)
                karr_seed_projection[tick, :] = karr_projection
                oc_seed_projection[tick, :] = oc_projection

            karr_projections.append(karr_seed_projection)
            oc_projections.append(oc_seed_projection)
            input_records.append(
                {
                    "kind": "oracle_data",
                    "path": _relative(expected_path),
                    "sha256": trace_sha,
                    "seed": int(seed_label),
                    "seed_index": _seed_index(seed_label, expected_seed_labels),
                    "n_ticks": int(n_ticks),
                    "condition": CONDITION,
                    "trace_kind": "event_window",
                }
            )

    if len(karr_projections) != len(expected_seed_labels):
        raise VerifierError(
            f"verified {len(karr_projections)} traces but expected {len(expected_seed_labels)} for {root}"
        )

    karr_projection = np.stack(karr_projections, axis=0)
    oc_projection = np.stack(oc_projections, axis=0)
    hurdle_payload = hurdle_event_rate_plus_conditional_scaled_distance(oc_projection, karr_projection)
    mechanical_verdict, mechanical_reasons = vd.rederive_channel(
        "chromosome",
        {
            "aggregation": "hurdle_event_rate_plus_conditional_scaled_distance",
            "hurdle": hurdle_payload,
        },
        is_primary=True,
    )
    expected_pooled_fire_ticks = float(spec["conditions"][CONDITION]["expected_pooled_fire_ticks"]) * (
        (len(expected_seed_labels) * _entry().m_ticks) / (_entry().n_seeds * _entry().m_ticks)
    )
    component_summary: list[dict[str, Any]] = []
    for idx, token in enumerate(PRIMARY_PROJECTION):
        component_summary.append(
            {
                "token": token,
                "karr_nonzero_count": int(np.count_nonzero(karr_projection[:, :, idx])),
                "karr_sum": float(np.sum(karr_projection[:, :, idx])),
                "oc_nonzero_count": int(np.count_nonzero(oc_projection[:, :, idx])),
                "oc_sum": float(np.sum(oc_projection[:, :, idx])),
            }
        )

    run_label = ""
    if len(run_labels) == 1:
        run_label = next(iter(run_labels))
    elif run_labels:
        identity_validation_failures.append(
            {
                "path": _relative(root),
                "reason": f"multiple evidence_run_label values observed: {sorted(run_labels)}",
            }
        )

    return {
        "condition": CONDITION,
        "root_label": root.parent.parent.name,
        "run_label": run_label,
        "output_root": _relative(root),
        "seed_count": len(expected_seed_labels),
        "seed_start": int(expected_seed_labels[0]),
        "seed_end": int(expected_seed_labels[-1]),
        "expected_pooled_fire_ticks_scaled_from_spec": expected_pooled_fire_ticks,
        "identity_validation_total": len(expected_seed_labels),
        "identity_validation_ok_count": len(expected_seed_labels) - len(identity_validation_failures),
        "identity_validation_failures": identity_validation_failures,
        "stimulus_conditioned_trace_count": sum(
            1 for item in trace_classifications if item["classification"] == "stimulus_conditioned"
        ),
        "trace_classifications": trace_classifications,
        "karr_projection_shape": list(karr_projection.shape),
        "oc_projection_shape": list(oc_projection.shape),
        "primary_projection": list(PRIMARY_PROJECTION),
        "primary_projection_component_summary": component_summary,
        "hurdle_payload": hurdle_payload,
        "mechanical_verdict": mechanical_verdict,
        "mechanical_reasons": mechanical_reasons,
        "condition_label_values": sorted(condition_labels),
        "mnrnd_provider_kind_values": sorted(provider_kind_values),
        "statistics_rng_provider_identity_json_values": sorted(statistics_rng_provider_values),
        "overlay_hash_metadata_provenance": {
            "all_traces_carry_overlay_hashes": all(
                count == len(expected_seed_labels) for count in metadata_hash_field_present_counts.values()
            ),
            "present_counts_by_field": metadata_hash_field_present_counts,
            "required_fields": list(REQUIRED_OVERLAY_HASH_FIELDS),
            "note": (
                "Every trace in this corpus was re-extracted (Sept-2 review item 8) with the "
                "raw-byte-hashing karr_bootstrap.m (item 7) and carries "
                "dnadamage_source_original_sha256 / patched_sha256 / resolved_sha256 / resolved_path "
                "metadata; verify_corpus() raises VerifierError on any trace missing a required field "
                "rather than tolerating it as a legacy-corpus caveat."
            ),
        },
        "input_records": input_records,
    }


def _validate_accepted_verification(payload: dict[str, Any], *, require_full_support: bool) -> None:
    if payload["identity_validation_ok_count"] != payload["identity_validation_total"]:
        raise VerifierError(
            f"{payload['root_label']} identity validation failed for "
            f"{payload['identity_validation_total'] - payload['identity_validation_ok_count']} trace(s)"
        )
    if payload["stimulus_conditioned_trace_count"] != payload["identity_validation_total"]:
        raise VerifierError(
            f"{payload['root_label']} includes non-stimulus traces: "
            f"{payload['stimulus_conditioned_trace_count']} / {payload['identity_validation_total']} conditioned"
        )
    if require_full_support and payload["mechanical_verdict"] != schema.STATUS_PASS:
        raise VerifierError(
            f"{payload['root_label']} replay remains non-green: "
            f"{payload['mechanical_verdict']} ({payload['mechanical_reasons']})"
        )


def _component_name_map() -> dict[str, str]:
    return {f"component_{idx}": PRIMARY_PROJECTION[idx] for idx in range(1, len(PRIMARY_PROJECTION))}


def build_bundle_payloads(
    *,
    canary_verify: dict[str, Any],
    full_verify: dict[str, Any],
    output_dir: Path,
) -> dict[str, dict[str, Any]]:
    entry = _entry()
    canary_ref = _relative(output_dir / "canary_verify.json")
    full_ref = _relative(output_dir / "full_verify.json")
    verify_file_hashes = {
        "canary_verify.json": _sha256_bytes(_json_bytes(canary_verify)),
        "full_verify.json": _sha256_bytes(_json_bytes(full_verify)),
    }
    all_input_records = [
        {
            "kind": "tracked_verifier_output",
            "path": canary_ref,
            "sha256": verify_file_hashes["canary_verify.json"],
        },
        {
            "kind": "tracked_verifier_output",
            "path": full_ref,
            "sha256": verify_file_hashes["full_verify.json"],
        },
        {
            "kind": "verifier_source",
            "path": _relative(Path(__file__)),
            "sha256": _sha256_file(Path(__file__)),
        },
        {
            "kind": "cohort_contract",
            "path": _relative(Path(cohort.__file__)),
            "sha256": _sha256_file(Path(cohort.__file__)),
        },
        {
            "kind": "spec",
            "path": _relative(cohort.SPEC_PATH),
            "sha256": _sha256_file(cohort.SPEC_PATH),
        },
    ] + canary_verify["input_records"] + full_verify["input_records"]
    warnings: list[str] = []
    if not full_verify["overlay_hash_metadata_provenance"]["all_traces_carry_overlay_hashes"]:
        # verify_corpus() already raises VerifierError on any missing overlay-hash
        # field, so this branch is unreachable by construction -- kept only as a
        # defense-in-depth guard against a future refactor accidentally
        # softening that check back into a silent caveat.
        raise VerifierError(
            "full_verify overlay_hash_metadata_provenance reports missing fields; "
            "verify_corpus() should have already raised -- refusing to build a bundle "
            "from a corpus with incomplete overlay-hash provenance"
        )

    result = {
        "process": PROCESS,
        "timestamp": datetime.now(UTC).isoformat(),
        "bucket": entry.bucket,
        "canonical_seed_count": entry.n_seeds,
        "channels": {
            "chromosome": {
                "aggregation": "hurdle_event_rate_plus_conditional_scaled_distance",
                "is_primary": True,
                "is_event_channel": False,
                "verdict": full_verify["mechanical_verdict"],
                "w1_oc_vs_karr": 0.0,
                "hurdle": full_verify["hurdle_payload"],
                "condition": CONDITION,
                "primary_projection": list(PRIMARY_PROJECTION),
                "component_name_map": _component_name_map(),
                "primary_projection_component_summary": full_verify["primary_projection_component_summary"],
            }
        },
        "process_seed_labels": list(range(full_verify["seed_start"], full_verify["seed_end"] + 1)),
        "seeds": list(range(entry.n_seeds)),
        "ticks": entry.m_ticks,
        "verdict": full_verify["mechanical_verdict"],
        "warnings": warnings,
        "dna_damage_event_verifier": {
            "mode": "genuine_stimulus_replay",
            "condition": CONDITION,
            "canary_verify_ref": canary_ref,
            "full_verify_ref": full_ref,
            "canary_verify_sha256": verify_file_hashes["canary_verify.json"],
            "full_verify_sha256": verify_file_hashes["full_verify.json"],
            "overlay_hash_metadata_provenance": full_verify["overlay_hash_metadata_provenance"],
        },
    }
    input_manifest = {
        "process": PROCESS,
        "condition": CONDITION,
        "resolved_seeds": list(range(entry.n_seeds)),
        "m_ticks": entry.m_ticks,
        "trace_seed_labels": list(range(full_verify["seed_start"], full_verify["seed_end"] + 1)),
        "inputs": all_input_records,
    }
    provenance = {
        "process": PROCESS,
        "generated_at": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(cat.REPO_ROOT),
        "git_dirty": _git_dirty(cat.REPO_ROOT),
        "verifier_kind": "l22_dna_damage_event_verifier",
        "condition": CONDITION,
        "canary_verify_ref": canary_ref,
        "full_verify_ref": full_ref,
        "source_corpora": {
            "canary": {
                "root": canary_verify["output_root"],
                "seed_count": canary_verify["seed_count"],
                "trace_input_count": len(canary_verify["input_records"]),
            },
            "full": {
                "root": full_verify["output_root"],
                "seed_count": full_verify["seed_count"],
                "trace_input_count": len(full_verify["input_records"]),
            },
        },
        "overlay_hash_metadata_provenance": full_verify["overlay_hash_metadata_provenance"],
    }
    thresholds = {
        "process": PROCESS,
        "condition": CONDITION,
        "channels": {
            "chromosome": {
                "aggregation": "hurdle_event_rate_plus_conditional_scaled_distance",
                "event_rate_threshold": full_verify["hurdle_payload"]["event_rate_threshold"],
                "conditional_scaled_distance_threshold": full_verify["hurdle_payload"][
                    "conditional_scaled_distance_threshold"
                ],
                "component_name_map": _component_name_map(),
            }
        },
    }
    null_calibration = {
        "process": PROCESS,
        "condition": CONDITION,
        "mode": "fixed_metric_contract",
        "note": (
            "DNADamage latest_event authority uses the fixed hurdle metric contract from "
            "tests/vivarium/_l2_2_design_a_projections.py rather than a separate bootstrap null. "
            "The raw authority is the stored hurdle payload plus the tracked full/canary verifier JSONs."
        ),
        "channels": [
            {
                "channel": "chromosome",
                "aggregation": "hurdle_event_rate_plus_conditional_scaled_distance",
                "event_rate_threshold": full_verify["hurdle_payload"]["event_rate_threshold"],
                "conditional_scaled_distance_threshold": full_verify["hurdle_payload"][
                    "conditional_scaled_distance_threshold"
                ],
            }
        ],
    }
    summary = {
        "process": PROCESS,
        "mode": "l22_dna_damage_event_verifier",
        "generated_at": datetime.now(UTC).isoformat(),
        "condition": CONDITION,
        "mechanical_verdict": full_verify["mechanical_verdict"],
        "mechanical_reasons": full_verify["mechanical_reasons"],
        "canary_verify_ref": canary_ref,
        "full_verify_ref": full_ref,
        "canary_support_verdict": canary_verify["mechanical_verdict"],
        "overlay_hash_metadata_provenance": full_verify["overlay_hash_metadata_provenance"],
    }
    analytical_check = {
        "applicable": True,
        "mode": "dna_damage_support_cross_check",
        "condition": CONDITION,
        "canary": {
            "expected_pooled_fire_ticks_scaled_from_spec": canary_verify["expected_pooled_fire_ticks_scaled_from_spec"],
            "observed_pooled_fire_ticks_karr": canary_verify["hurdle_payload"]["n_events_karr"],
            "observed_pooled_fire_ticks_oc": canary_verify["hurdle_payload"]["n_events_oc"],
            "mechanical_verdict": canary_verify["mechanical_verdict"],
        },
        "full": {
            "expected_pooled_fire_ticks_scaled_from_spec": full_verify["expected_pooled_fire_ticks_scaled_from_spec"],
            "observed_pooled_fire_ticks_karr": full_verify["hurdle_payload"]["n_events_karr"],
            "observed_pooled_fire_ticks_oc": full_verify["hurdle_payload"]["n_events_oc"],
            "mechanical_verdict": full_verify["mechanical_verdict"],
        },
    }
    return {
        "result.json": result,
        "input_manifest.json": input_manifest,
        "provenance.json": provenance,
        "thresholds.json": thresholds,
        "null_calibration.json": null_calibration,
        "SUMMARY.json": summary,
        "analytical_check.json": analytical_check,
    }


def _build_sweep_provenance(output_dir: Path) -> dict[str, Any]:
    entry = _entry()
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


def write_latest_event_bundle(
    *,
    output_root: Path = schema.BUNDLE_ROOT,
    canary_root: Path = CANARY_ROOT,
    full_root: Path = FULL_ROOT,
) -> Path:
    canary_verify = verify_corpus(root=canary_root, expected_seed_labels=list(range(2000, 2005)))
    full_verify = verify_corpus(root=full_root, expected_seed_labels=list(range(2000, 2050)))
    _validate_accepted_verification(canary_verify, require_full_support=False)
    _validate_accepted_verification(full_verify, require_full_support=True)

    output_dir = output_root / PROCESS / schema.EVENT_CLASS_SUBDIR
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "canary_verify.json", canary_verify)
    _write_json(output_dir / "full_verify.json", full_verify)
    for fname, payload in build_bundle_payloads(
        canary_verify=canary_verify,
        full_verify=full_verify,
        output_dir=output_dir,
    ).items():
        _write_json(output_dir / fname, payload)
    _write_json(output_dir / schema.SWEEP_PROVENANCE_FILE, _build_sweep_provenance(output_dir))
    return output_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        default=str(schema.BUNDLE_ROOT),
        help="Root that will receive DNADamage/latest_event/.",
    )
    parser.add_argument(
        "--canary-root",
        default=str(CANARY_ROOT),
        help="Accepted genuine canary corpus root.",
    )
    parser.add_argument(
        "--full-root",
        default=str(FULL_ROOT),
        help="Accepted genuine full corpus root.",
    )
    args = parser.parse_args(argv)

    output_dir = write_latest_event_bundle(
        output_root=Path(args.output_root),
        canary_root=Path(args.canary_root),
        full_root=Path(args.full_root),
    )
    print(f"wrote DNADamage latest_event bundle at {_relative(output_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
