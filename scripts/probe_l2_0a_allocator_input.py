"""L2.0a allocator-input gate against the extracted Karr allocation oracle.

This gate isolates allocator arithmetic only:
  Karr pool_before + Karr requirements -> OC KarrAllocationStep -> compare to Karr allocations

The runtime step accepts arbitrary string keys for substrates/requests, so this
probe feeds the full flattened metabolite-compartment matrix through synthetic
keys like ``ATP[c]``. Reporting is then projected back to per-process substrate
WIDs from `data/schemas/per_process/*.toml` only where that mapping is
unambiguous.
"""

from __future__ import annotations

import argparse
import math
import tomllib
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np

from opencell.vivarium.karr_allocation_step import KarrAllocationStep

REPO = Path(__file__).resolve().parents[1]
ORACLE_PATH = REPO / "data" / "m1_sources" / "karr_native" / "l2_0a_allocator_oracle_s000.mat"
SCHEMA_DIR = REPO / "data" / "schemas" / "per_process"
INTEGRAL_TOL = 1e-9


@dataclass(frozen=True)
class AllocatorOracle:
    process_names: tuple[str, ...]
    metabolite_wids: tuple[str, ...]
    compartment_wids: tuple[str, ...]
    counts_shape: tuple[int, int]
    pool_before: np.ndarray
    requirements: np.ndarray
    allocations: np.ndarray


@dataclass(frozen=True)
class WidMapping:
    process_name: str
    wid: str
    flat_index: int
    metabolite_wid: str
    compartment_wid: str
    mc_key: str
    mapping_reason: str


@dataclass(frozen=True)
class UnmappedWid:
    process_name: str
    wid: str
    reason: str
    candidate_mc_keys: tuple[str, ...]


@dataclass(frozen=True)
class CellVerdict:
    process_name: str
    wid: str
    mc_key: str
    expected: int
    observed: int
    request: float
    pool: float
    total_demand: float
    oversupply: bool
    match: bool


@dataclass(frozen=True)
class ProcessSummary:
    process_name: str
    checked: int
    passed: int
    failed: int
    unmapped: int


@dataclass(frozen=True)
class GateResult:
    returncode: int
    summary_message: str
    checked_count: int
    passed_count: int
    failed_count: int
    unmapped_count: int
    oversupply_fail_count: int
    other_fail_count: int
    verdicts: tuple[CellVerdict, ...]
    failures: tuple[CellVerdict, ...]
    unmapped_wids: tuple[UnmappedWid, ...]
    process_summaries: tuple[ProcessSummary, ...]
    failure_examples: tuple[str, ...]


def _decode_cellstrs(handle: h5py.File, dataset_name: str) -> tuple[str, ...]:
    refs = handle[dataset_name][()]
    out: list[str] = []
    for ref in refs.reshape(-1):
        arr = np.asarray(handle[ref][()]).reshape(-1)
        text = "".join(chr(int(value)) for value in arr if int(value) != 0)
        out.append(text)
    return tuple(out)


def _read_singleton_cell(handle: h5py.File, dataset_name: str) -> np.ndarray:
    refs = handle[dataset_name]
    if refs.shape != (1, 1):
        raise ValueError(f"{dataset_name} must be a 1x1 MAT cell, got {refs.shape}")
    ref = refs[0, 0]
    return np.asarray(handle[ref][()], dtype=np.float64)


def load_allocator_oracle(path: Path = ORACLE_PATH) -> AllocatorOracle:
    with h5py.File(path, "r") as handle:
        process_names = _decode_cellstrs(handle, "process_names")
        metabolite_wids = _decode_cellstrs(handle, "metabolite_wids")
        compartment_wids = _decode_cellstrs(handle, "compartment_wids")
        counts_shape_arr = np.asarray(handle["counts_shape"][()], dtype=np.float64).reshape(-1)
        if counts_shape_arr.size != 2:
            raise ValueError(f"counts_shape must have two entries, got {counts_shape_arr.tolist()}")
        counts_shape = (int(counts_shape_arr[0]), int(counts_shape_arr[1]))
        pool_before = _read_singleton_cell(handle, "pool_before").reshape(-1)
        requirements = _read_singleton_cell(handle, "requirements")
        allocations = _read_singleton_cell(handle, "allocations")

    if requirements.shape != allocations.shape:
        raise ValueError(
            "requirements/allocations shape mismatch: "
            f"{requirements.shape} vs {allocations.shape}"
        )
    if requirements.shape[0] != len(process_names):
        raise ValueError(
            "process count mismatch: "
            f"len(process_names)={len(process_names)} requirements_rows={requirements.shape[0]}"
        )
    flat_size = counts_shape[0] * counts_shape[1]
    if pool_before.size != flat_size:
        raise ValueError(f"pool_before size mismatch: {pool_before.size} vs {flat_size}")
    if requirements.shape[1] != flat_size:
        raise ValueError(f"requirements width mismatch: {requirements.shape[1]} vs {flat_size}")

    return AllocatorOracle(
        process_names=process_names,
        metabolite_wids=metabolite_wids,
        compartment_wids=compartment_wids,
        counts_shape=counts_shape,
        pool_before=pool_before.astype(np.float64, copy=False),
        requirements=requirements.astype(np.float64, copy=False),
        allocations=allocations.astype(np.float64, copy=False),
    )


def load_process_substrate_wids(schema_dir: Path = SCHEMA_DIR) -> dict[str, tuple[str, ...]]:
    out: dict[str, tuple[str, ...]] = {}
    for schema_path in sorted(schema_dir.glob("*.toml")):
        data = tomllib.loads(schema_path.read_text(encoding="utf-8"))
        process_name = str(data["process"]["name"])
        raw_wids = data.get("state_groups", {}).get("substrates", [])
        out[process_name] = tuple(str(wid) for wid in raw_wids)
    return out


def mc_key_for_flat_index(oracle: AllocatorOracle, flat_index: int) -> str:
    met_count = oracle.counts_shape[0]
    met_idx = flat_index % met_count
    comp_idx = flat_index // met_count
    return f"{oracle.metabolite_wids[met_idx]}[{oracle.compartment_wids[comp_idx]}]"


def flat_index_candidates(oracle: AllocatorOracle, wid: str) -> tuple[int, ...]:
    try:
        met_idx = oracle.metabolite_wids.index(wid)
    except ValueError:
        return tuple()
    met_count = oracle.counts_shape[0]
    return tuple(met_idx + comp_idx * met_count for comp_idx in range(len(oracle.compartment_wids)))


def build_wid_mappings(
    oracle: AllocatorOracle,
    process_substrate_wids: dict[str, tuple[str, ...]],
) -> tuple[dict[tuple[str, str], WidMapping], tuple[UnmappedWid, ...]]:
    process_index = {name: idx for idx, name in enumerate(oracle.process_names)}
    active_mask = (
        (oracle.pool_before != 0.0)
        | (oracle.requirements.sum(axis=0) != 0.0)
        | (oracle.allocations.sum(axis=0) != 0.0)
    )
    mappings: dict[tuple[str, str], WidMapping] = {}
    unmapped: list[UnmappedWid] = []

    for process_name in oracle.process_names:
        process_wids = process_substrate_wids.get(process_name, ())
        proc_idx = process_index[process_name]
        for wid in process_wids:
            candidates = flat_index_candidates(oracle, wid)
            if not candidates:
                unmapped.append(
                    UnmappedWid(
                        process_name=process_name,
                        wid=wid,
                        reason="wid_missing_from_oracle_metabolite_list",
                        candidate_mc_keys=tuple(),
                    )
                )
                continue

            local_hits = tuple(
                idx
                for idx in candidates
                if oracle.requirements[proc_idx, idx] != 0.0 or oracle.allocations[proc_idx, idx] != 0.0
            )
            if len(local_hits) == 1:
                flat_index = local_hits[0]
                mapping_reason = "single_local_nonzero_candidate"
            elif len(local_hits) > 1:
                unmapped.append(
                    UnmappedWid(
                        process_name=process_name,
                        wid=wid,
                        reason="multiple_local_nonzero_candidates",
                        candidate_mc_keys=tuple(mc_key_for_flat_index(oracle, idx) for idx in local_hits),
                    )
                )
                continue
            else:
                active_hits = tuple(idx for idx in candidates if active_mask[idx])
                if len(active_hits) == 1:
                    flat_index = active_hits[0]
                    mapping_reason = "single_active_candidate"
                elif len(active_hits) > 1:
                    unmapped.append(
                        UnmappedWid(
                            process_name=process_name,
                            wid=wid,
                            reason="multiple_active_compartment_candidates",
                            candidate_mc_keys=tuple(
                                mc_key_for_flat_index(oracle, idx) for idx in active_hits
                            ),
                        )
                    )
                    continue
                else:
                    unmapped.append(
                        UnmappedWid(
                            process_name=process_name,
                            wid=wid,
                            reason="no_active_compartment_candidate",
                            candidate_mc_keys=tuple(
                                mc_key_for_flat_index(oracle, idx) for idx in candidates
                            ),
                        )
                    )
                    continue

            met_count = oracle.counts_shape[0]
            met_idx = flat_index % met_count
            comp_idx = flat_index // met_count
            mappings[(process_name, wid)] = WidMapping(
                process_name=process_name,
                wid=wid,
                flat_index=flat_index,
                metabolite_wid=oracle.metabolite_wids[met_idx],
                compartment_wid=oracle.compartment_wids[comp_idx],
                mc_key=mc_key_for_flat_index(oracle, flat_index),
                mapping_reason=mapping_reason,
            )

    return mappings, tuple(unmapped)


def _count_to_int(value: float, *, label: str) -> int:
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite, got {value}")
    nearest = int(round(value))
    if abs(value - nearest) > INTEGRAL_TOL:
        raise ValueError(f"{label} must be integral, got {value}")
    return nearest


def run_allocator_full_matrix(oracle: AllocatorOracle) -> dict[str, dict[str, float]]:
    mc_keys = [mc_key_for_flat_index(oracle, idx) for idx in range(oracle.pool_before.size)]
    substrates = {
        mc_key: float(oracle.pool_before[idx]) for idx, mc_key in enumerate(mc_keys)
    }
    requests: dict[str, dict[str, float]] = {}
    for proc_idx, process_name in enumerate(oracle.process_names):
        reqs: dict[str, float] = {}
        for flat_idx, mc_key in enumerate(mc_keys):
            value = float(oracle.requirements[proc_idx, flat_idx])
            if value != 0.0:
                reqs[mc_key] = value
        requests[process_name] = reqs

    step = KarrAllocationStep(
        {
            "consumer_processes": [(process_name, []) for process_name in oracle.process_names],
            "substrate_wids": mc_keys,
        }
    )
    update = step.next_update(
        1.0,
        {
            "substrates": substrates,
            "requests": requests,
        },
    )
    return update["substrates_allocated"]


def evaluate_allocator_gate(
    oracle: AllocatorOracle,
    process_substrate_wids: dict[str, tuple[str, ...]],
) -> GateResult:
    allocations_by_process = run_allocator_full_matrix(oracle)
    mappings, unmapped_wids = build_wid_mappings(oracle, process_substrate_wids)
    process_index = {name: idx for idx, name in enumerate(oracle.process_names)}
    total_demand = oracle.requirements.sum(axis=0)

    verdicts: list[CellVerdict] = []
    for process_name in oracle.process_names:
        proc_idx = process_index[process_name]
        process_allocs = allocations_by_process.get(process_name, {})
        for wid in process_substrate_wids.get(process_name, ()):
            mapping = mappings.get((process_name, wid))
            if mapping is None:
                continue
            flat_index = mapping.flat_index
            expected = _count_to_int(
                float(oracle.allocations[proc_idx, flat_index]),
                label=f"oracle allocations[{process_name}][{mapping.mc_key}]",
            )
            observed = _count_to_int(
                float(process_allocs.get(mapping.mc_key, 0.0)),
                label=f"oc allocations[{process_name}][{mapping.mc_key}]",
            )
            demand = float(oracle.requirements[proc_idx, flat_index])
            pool = float(oracle.pool_before[flat_index])
            demand_total = float(total_demand[flat_index])
            oversupply = demand_total > 0.0 and pool > demand_total
            verdicts.append(
                CellVerdict(
                    process_name=process_name,
                    wid=wid,
                    mc_key=mapping.mc_key,
                    expected=expected,
                    observed=observed,
                    request=demand,
                    pool=pool,
                    total_demand=demand_total,
                    oversupply=oversupply,
                    match=(expected == observed),
                )
            )

    failures = [verdict for verdict in verdicts if not verdict.match]
    oversupply_fail_count = sum(
        1
        for verdict in failures
        if verdict.oversupply
        and verdict.observed == int(math.floor(max(0.0, verdict.request)))
        and verdict.expected >= verdict.observed
    )
    other_fail_count = len(failures) - oversupply_fail_count

    process_summaries: list[ProcessSummary] = []
    for process_name in oracle.process_names:
        checked = sum(1 for verdict in verdicts if verdict.process_name == process_name)
        failed = sum(
            1 for verdict in failures if verdict.process_name == process_name
        )
        unmapped = sum(
            1 for item in unmapped_wids if item.process_name == process_name
        )
        process_summaries.append(
            ProcessSummary(
                process_name=process_name,
                checked=checked,
                passed=checked - failed,
                failed=failed,
                unmapped=unmapped,
            )
        )

    failure_examples = tuple(
        (
            f"{verdict.process_name}/{verdict.wid}->{verdict.mc_key}: "
            f"expected={verdict.expected} observed={verdict.observed} "
            f"request={verdict.request:.6g} pool={verdict.pool:.6g} "
            f"total_demand={verdict.total_demand:.6g} oversupply={verdict.oversupply}"
        )
        for verdict in failures
    )
    checked_count = len(verdicts)
    failed_count = len(failures)
    passed_count = checked_count - failed_count
    unmapped_count = len(unmapped_wids)
    if failed_count:
        summary_message = (
            "L2.0a ALLOCATOR INPUT GATE: FAIL "
            f"({passed_count}/{checked_count} checked cells matched, "
            f"{failed_count} diverged, {unmapped_count} unmapped WIDs; "
            f"oversupply-cap mismatches={oversupply_fail_count}, other_mismatches={other_fail_count})"
        )
        returncode = 1
    else:
        summary_message = (
            "L2.0a ALLOCATOR INPUT GATE: PASS "
            f"({passed_count}/{checked_count} checked cells matched, "
            f"{unmapped_count} unmapped WIDs)"
        )
        returncode = 0

    return GateResult(
        returncode=returncode,
        summary_message=summary_message,
        checked_count=checked_count,
        passed_count=passed_count,
        failed_count=failed_count,
        unmapped_count=unmapped_count,
        oversupply_fail_count=oversupply_fail_count,
        other_fail_count=other_fail_count,
        verdicts=tuple(verdicts),
        failures=tuple(failures),
        unmapped_wids=unmapped_wids,
        process_summaries=tuple(process_summaries),
        failure_examples=failure_examples,
    )


def format_gate_report(result: GateResult) -> str:
    lines = [result.summary_message, ""]
    lines.append("Per-process summary:")
    for summary in result.process_summaries:
        lines.append(
            f"  {summary.process_name:26s} checked={summary.checked:3d} "
            f"pass={summary.passed:3d} fail={summary.failed:3d} unmapped={summary.unmapped:3d}"
        )

    if result.unmapped_wids:
        lines.append("")
        lines.append("Unmapped WID reasons:")
        reason_counts: dict[str, int] = {}
        for item in result.unmapped_wids:
            reason_counts[item.reason] = reason_counts.get(item.reason, 0) + 1
        for reason in sorted(reason_counts):
            lines.append(f"  {reason}: {reason_counts[reason]}")

        lines.append("")
        lines.append("Sample unmapped WIDs:")
        for item in result.unmapped_wids[:20]:
            candidates = ", ".join(item.candidate_mc_keys) if item.candidate_mc_keys else "none"
            lines.append(
                f"  {item.process_name}/{item.wid}: reason={item.reason} candidates={candidates}"
            )

    if result.failures:
        lines.append("")
        lines.append("Divergence cells:")
        for example in result.failure_examples:
            lines.append(f"  {example}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle", type=Path, default=ORACLE_PATH)
    args = parser.parse_args(argv)

    if not args.oracle.exists():
        try:
            shown = args.oracle.relative_to(REPO)
        except ValueError:
            shown = args.oracle
        print(
            "L2.0a ALLOCATOR INPUT GATE: SKIPPED — oracle absent at "
            f"{shown} (gitignored local artifact)."
        )
        return 0

    process_substrate_wids = load_process_substrate_wids()
    oracle = load_allocator_oracle(args.oracle)
    result = evaluate_allocator_gate(oracle, process_substrate_wids)
    print(format_gate_report(result))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
