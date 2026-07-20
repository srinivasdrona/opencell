from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import h5py
import numpy as np


TRACE_PATH = Path("data/m1_sources/karr_native/dnadamage_fullcycle/DNADamage_32400ticks.mat")

CHROM_FIELDS = (
    "polymerizedRegions",
    "linkingNumbers",
    "monomerBoundSites",
    "complexBoundSites",
    "gapSites",
    "abasicSites",
    "damagedSugarPhosphates",
    "damagedBases",
    "intrastrandCrossLinks",
    "strandBreaks",
    "hollidayJunctions",
)

DAMAGE_FIELDS = (
    "gapSites",
    "abasicSites",
    "damagedSugarPhosphates",
    "damagedBases",
    "intrastrandCrossLinks",
    "strandBreaks",
)


def tick_ref(dataset: h5py.Dataset, tick: int) -> h5py.Reference:
    if dataset.shape[0] == 1:
        return dataset[0, tick]
    return dataset[tick, 0]


def edge_count(group: h5py.Group, field: str) -> int:
    ds = group[field]["positions"]
    if int(ds.attrs.get("MATLAB_empty", 0)) == 1:
        return 0
    return int(ds.size)


def load_triplet(group: h5py.Group, field: str) -> dict[str, object]:
    field_group = group[field]

    def read_array(name: str, dtype: np.dtype) -> np.ndarray:
        ds = field_group[name]
        if int(ds.attrs.get("MATLAB_empty", 0)) == 1:
            return np.zeros(0, dtype=dtype)
        return np.asarray(ds[()], dtype=dtype).reshape(-1)

    error = ""
    if "error" in field_group:
        raw = field_group["error"][()]
        if isinstance(raw, bytes):
            error = raw.decode("utf-8", errors="replace")
        elif np.isscalar(raw):
            error = str(raw)
        else:
            error = str(np.asarray(raw))

    return {
        "positions": read_array("positions", np.int64),
        "strands": read_array("strands", np.int8),
        "values": read_array("values", np.int32),
        "shape": tuple(int(v) for v in np.asarray(field_group["shape"][()]).reshape(-1)[:2]),
        "error": error,
    }


def triplet_equal(lhs: dict[str, object], rhs: dict[str, object]) -> bool:
    return (
        lhs["shape"] == rhs["shape"]
        and lhs["error"] == rhs["error"]
        and np.array_equal(lhs["positions"], rhs["positions"])
        and np.array_equal(lhs["strands"], rhs["strands"])
        and np.array_equal(lhs["values"], rhs["values"])
    )


def chromosome_groups_equal(before_group: h5py.Group, after_group: h5py.Group) -> tuple[bool, list[str]]:
    mismatches: list[str] = []
    if int(np.asarray(before_group["sequenceLen"][()]).reshape(-1)[0]) != int(
        np.asarray(after_group["sequenceLen"][()]).reshape(-1)[0]
    ):
        mismatches.append("sequenceLen")
    if int(np.asarray(before_group["nCompartments"][()]).reshape(-1)[0]) != int(
        np.asarray(after_group["nCompartments"][()]).reshape(-1)[0]
    ):
        mismatches.append("nCompartments")
    for field in CHROM_FIELDS:
        if not triplet_equal(load_triplet(before_group, field), load_triplet(after_group, field)):
            mismatches.append(field)
    return (len(mismatches) == 0, mismatches)


def values_histogram(group: h5py.Group, field: str) -> dict[str, int]:
    ds = group[field]["values"]
    if int(ds.attrs.get("MATLAB_empty", 0)) == 1:
        return {}
    values = np.asarray(ds[()], dtype=np.int32).reshape(-1)
    counts = Counter(int(v) for v in values.tolist())
    return {str(k): int(v) for k, v in sorted(counts.items())}


def compress_ticks(ticks: list[int]) -> list[str]:
    if not ticks:
        return []
    ranges: list[str] = []
    start = ticks[0]
    prev = ticks[0]
    for tick in ticks[1:]:
        if tick == prev + 1:
            prev = tick
            continue
        ranges.append(f"{start}" if start == prev else f"{start}-{prev}")
        start = prev = tick
    ranges.append(f"{start}" if start == prev else f"{start}-{prev}")
    return ranges


def main() -> None:
    if not TRACE_PATH.exists():
        raise SystemExit(f"Trace not found: {TRACE_PATH}")

    with h5py.File(TRACE_PATH, "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
        before_dataset = trace["states_before/chromosome"]
        after_dataset = trace["states_after/chromosome"]
        sample_ticks = tuple(sorted(set([0, 1, 2, n_ticks - 1] + list(range(0, n_ticks, 4000)))))

        before_counts = np.zeros(n_ticks, dtype=np.int32)
        polymerized_counts = np.zeros(n_ticks, dtype=np.int32)

        for tick in range(n_ticks):
            before_group = trace[tick_ref(before_dataset, tick)]
            before_counts[tick] = edge_count(before_group, "damagedBases")
            polymerized_counts[tick] = edge_count(before_group, "polymerizedRegions")

        sample_equalities: list[dict[str, object]] = []
        for tick in sample_ticks:
            before_group = trace[tick_ref(before_dataset, tick)]
            after_group = trace[tick_ref(after_dataset, tick)]
            equal, mismatches = chromosome_groups_equal(before_group, after_group)
            sample_equalities.append(
                {
                    "tick": tick,
                    "chromosome_equal": equal,
                    "mismatch_fields": mismatches,
                    "damagedBases_edges": int(before_counts[tick]),
                    "damagedBases_values": values_histogram(before_group, "damagedBases"),
                    "other_damage_edges": {
                        field: edge_count(before_group, field)
                        for field in DAMAGE_FIELDS
                        if field != "damagedBases"
                    },
                }
            )

        deltas = np.diff(before_counts)
        polymerized_deltas = np.diff(polymerized_counts)
        increment_ticks = [int(i) for i, delta in enumerate(deltas.tolist()) if delta > 0]
        increment_deltas = [int(delta) for delta in deltas.tolist() if delta > 0]
        polymerized_change_ticks = [int(i) for i, delta in enumerate(polymerized_deltas.tolist()) if delta > 0]

        report = {
            "trace_path": str(TRACE_PATH),
            "n_ticks": n_ticks,
            "sample_ticks": list(sample_ticks),
            "sampled_chromosome_exact_equal_all_ticks": all(
                item["chromosome_equal"] for item in sample_equalities
            ),
            "sample_chromosome_equalities": sample_equalities,
            "damagedBases_before_edge_samples": {
                str(tick): int(before_counts[tick]) for tick in sample_ticks
            },
            "damagedBases_initial_edges": int(before_counts[0]),
            "damagedBases_final_edges": int(before_counts[-1]),
            "damagedBases_total_increase": int(before_counts[-1] - before_counts[0]),
            "damagedBases_increment_tick_count": len(increment_ticks),
            "damagedBases_increment_ticks": increment_ticks,
            "damagedBases_increment_tick_ranges": compress_ticks(increment_ticks),
            "damagedBases_increment_deltas_summary": {
                "min": min(increment_deltas) if increment_deltas else 0,
                "max": max(increment_deltas) if increment_deltas else 0,
                "sum": int(sum(increment_deltas)),
            },
            "polymerizedRegions_change_tick_count": len(polymerized_change_ticks),
            "damaged_increment_ticks_all_overlap_polymerized_change": set(increment_ticks).issubset(
                set(polymerized_change_ticks)
            ),
            "damaged_increment_not_polymerized_change_ticks_head": sorted(
                set(increment_ticks) - set(polymerized_change_ticks)
            )[:20],
            "damagedBases_value_histograms": {
                "tick0": values_histogram(trace[tick_ref(before_dataset, 0)], "damagedBases"),
                "tick32399": values_histogram(trace[tick_ref(before_dataset, n_ticks - 1)], "damagedBases"),
            },
        }

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
