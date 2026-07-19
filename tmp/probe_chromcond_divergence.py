from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Any

import h5py
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = REPO_ROOT / "tests" / "vivarium"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from l2_2_replay_common_v2 import (  # type: ignore
    _PROCESS_SPECS,
    _build_context,
    _inject_hidden_read_surface,
    _project_trace_vector,
    _trace_cell_payload,
    resolve_trace_path,
)
from l2_replay_common import (  # type: ignore
    apply_count_update,
    build_state_template,
    overlay_observable_into_state,
    project_observable_from_state,
    refresh_allocator_views,
)
from opencell.state.chromosome_store import ChromosomeStore


PROCESS_NAME = "ChromosomeCondensation"
MAX_TICKS_TO_REPORT = 5
MAX_MISMATCHES_PER_OBSERVABLE = 3


def _classify_numeric_difference(*, before: float, oc: float, karr: float) -> str:
    oc_delta = oc - before
    karr_delta = karr - before
    if oc == before and karr != before:
        return "missing-write"
    if oc != before and karr == before:
        return "extra-write"
    if oc_delta != 0 and karr_delta != 0:
        if np.sign(oc_delta) != np.sign(karr_delta):
            return "sign/direction"
        if abs(oc_delta) != abs(karr_delta):
            return "magnitude"
    return "magnitude"


def _vector_mismatches(
    *,
    observable: str,
    before: np.ndarray,
    oc_after: np.ndarray,
    karr_after: np.ndarray,
    wids: list[str],
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    bad = np.flatnonzero(oc_after != karr_after)
    for idx_raw in bad[:MAX_MISMATCHES_PER_OBSERVABLE]:
        idx = int(idx_raw)
        before_val = float(before[idx])
        oc_val = float(oc_after[idx])
        karr_val = float(karr_after[idx])
        mismatches.append(
            {
                "kind": "observable",
                "observable": observable,
                "index": idx,
                "wid": wids[idx] if idx < len(wids) else f"<idx:{idx}>",
                "before": before_val,
                "oc": oc_val,
                "karr": karr_val,
                "bug_class": _classify_numeric_difference(
                    before=before_val,
                    oc=oc_val,
                    karr=karr_val,
                ),
            }
        )
    return mismatches


def _triplet_counter(triplet) -> Counter[tuple[int, int, int]]:
    return Counter(
        (int(pos), int(strand), int(value))
        for pos, strand, value in triplet.to_regions()
    )


def _classify_sparse_difference(
    *,
    field: str,
    oc_only: list[tuple[int, int, int]],
    karr_only: list[tuple[int, int, int]],
) -> tuple[str, str]:
    del field
    if oc_only and not karr_only:
        pos, strand, value = oc_only[0]
        return (
            "extra-write",
            f"extra tuple at pos={pos}, strand={strand}, value={value}",
        )
    if karr_only and not oc_only:
        pos, strand, value = karr_only[0]
        return (
            "missing-write",
            f"missing tuple at pos={pos}, strand={strand}, value={value}",
        )

    oc_by_key = {(pos, strand): value for pos, strand, value in oc_only}
    karr_by_key = {(pos, strand): value for pos, strand, value in karr_only}
    shared_keys = [key for key in oc_by_key if key in karr_by_key]
    if shared_keys:
        key = shared_keys[0]
        oc_val = oc_by_key[key]
        karr_val = karr_by_key[key]
        if np.sign(oc_val) != np.sign(karr_val):
            return (
                "sign/direction",
                f"same pos/strand {key} but value sign differs: oc={oc_val}, karr={karr_val}",
            )
        return (
            "magnitude",
            f"same pos/strand {key} but value differs: oc={oc_val}, karr={karr_val}",
        )

    oc_values = Counter(value for _, _, value in oc_only)
    karr_values = Counter(value for _, _, value in karr_only)
    if oc_values == karr_values:
        oc_pos, oc_strand, oc_val = oc_only[0]
        karr_pos, karr_strand, karr_val = karr_only[0]
        return (
            "wrong index/projection",
            "value preserved but written at different position/strand: "
            f"oc=({oc_pos}, {oc_strand}, {oc_val}), "
            f"karr=({karr_pos}, {karr_strand}, {karr_val})",
        )

    oc_pos, oc_strand, oc_val = oc_only[0]
    karr_pos, karr_strand, karr_val = karr_only[0]
    return (
        "wrong index/projection",
        "different sparse tuple sets: "
        f"oc_only=({oc_pos}, {oc_strand}, {oc_val}), "
        f"karr_only=({karr_pos}, {karr_strand}, {karr_val})",
    )


def _first_sparse_mismatch(
    *,
    field: str,
    before_triplet,
    oc_triplet,
    karr_triplet,
) -> dict[str, Any] | None:
    oc_counter = _triplet_counter(oc_triplet)
    karr_counter = _triplet_counter(karr_triplet)
    if oc_counter == karr_counter:
        return None

    oc_only_counter = oc_counter - karr_counter
    karr_only_counter = karr_counter - oc_counter
    oc_only = sorted(oc_only_counter.elements())
    karr_only = sorted(karr_only_counter.elements())
    bug_class, note = _classify_sparse_difference(
        field=field,
        oc_only=oc_only,
        karr_only=karr_only,
    )

    detail: dict[str, Any] = {
        "kind": "chromosome",
        "observable": "chromosome",
        "field": field,
        "before_edges": int(before_triplet.calc_num_edges()),
        "oc_edges": int(oc_triplet.calc_num_edges()),
        "karr_edges": int(karr_triplet.calc_num_edges()),
        "bug_class": bug_class,
        "note": note,
    }
    if oc_only:
        pos, strand, value = oc_only[0]
        detail["oc_tuple"] = {"pos": pos, "strand": strand, "value": value}
    if karr_only:
        pos, strand, value = karr_only[0]
        detail["karr_tuple"] = {"pos": pos, "strand": strand, "value": value}
    return detail


def _format_observable_mismatch(entry: dict[str, Any]) -> str:
    return (
        f"observable={entry['observable']} wid={entry['wid']} idx={entry['index']} "
        f"before={entry['before']:.0f} oc={entry['oc']:.0f} karr={entry['karr']:.0f} "
        f"class={entry['bug_class']}"
    )


def _format_chromosome_mismatch(entry: dict[str, Any]) -> str:
    parts = [
        f"chromosome.{entry['field']}",
        f"before_edges={entry['before_edges']}",
        f"oc_edges={entry['oc_edges']}",
        f"karr_edges={entry['karr_edges']}",
        f"class={entry['bug_class']}",
    ]
    if "oc_tuple" in entry:
        tup = entry["oc_tuple"]
        parts.append(f"oc_tuple=({tup['pos']}, {tup['strand']}, {tup['value']})")
    if "karr_tuple" in entry:
        tup = entry["karr_tuple"]
        parts.append(f"karr_tuple=({tup['pos']}, {tup['strand']}, {tup['value']})")
    parts.append(f"note={entry['note']}")
    return " ".join(parts)


def run_probe() -> dict[str, Any]:
    spec = _PROCESS_SPECS[PROCESS_NAME]
    trace_path = resolve_trace_path(PROCESS_NAME)
    divergences: list[dict[str, Any]] = []
    first_strict_failure: dict[str, Any] | None = None
    karr_active_observables = 0
    karr_active_any = 0

    with h5py.File(trace_path, "r") as handle:
        ctx = _build_context(name=PROCESS_NAME, rng_seed=0, handle=handle)
        process = ctx.process
        observables = list(spec.observables)
        chromosome_fields = tuple(ChromosomeStore.FIELDS)

        for tick in range(ctx.n_ticks):
            state = build_state_template(process)
            before_vectors: dict[str, np.ndarray] = {}
            mismatch_entries: list[dict[str, Any]] = []

            for obs in observables:
                before = _project_trace_vector(ctx, "states_before", obs, tick)
                before_vectors[obs] = before
                overlay_observable_into_state(
                    process=process,
                    state=state,
                    observable=obs,
                    vector=before,
                    wids=ctx.wids_by_observable[obs],
                    store_path_override=spec.store_path_override,
                )

            _inject_hidden_read_surface(ctx=ctx, state=state, tick=tick)
            before_chrom_store = ChromosomeStore.from_state_mapping(state.get("chromosome"))
            refresh_allocator_views(process, state)
            update = process.next_update(1.0, state)
            apply_count_update(state, update)

            karr_max_abs_observables = 0.0
            for obs in observables:
                karr_after = _project_trace_vector(ctx, "states_after", obs, tick)
                delta = karr_after - before_vectors[obs]
                if delta.size:
                    karr_max_abs_observables = max(
                        karr_max_abs_observables, float(np.abs(delta).max())
                    )
            if karr_max_abs_observables >= 1.0:
                karr_active_observables += 1

            for obs in observables:
                oc_after = project_observable_from_state(
                    process=process,
                    state=state,
                    observable=obs,
                    wids=ctx.wids_by_observable[obs],
                    bound_enzymes_before=before_vectors.get("boundEnzymes"),
                    store_path_override=spec.store_path_override,
                ).astype(np.int64)
                karr_after = _project_trace_vector(ctx, "states_after", obs, tick).astype(np.int64)
                if not np.array_equal(oc_after, karr_after):
                    obs_mismatches = _vector_mismatches(
                        observable=obs,
                        before=before_vectors[obs].astype(np.int64),
                        oc_after=oc_after,
                        karr_after=karr_after,
                        wids=ctx.wids_by_observable[obs],
                    )
                    mismatch_entries.extend(obs_mismatches)
                    if first_strict_failure is None and obs_mismatches:
                        first_strict_failure = {"tick": tick, "mismatch": obs_mismatches[0]}

            payload = _trace_cell_payload(
                ctx=ctx,
                group="states_after",
                name="chromosome",
                tick=tick,
            )
            karr_chrom_active = False
            if isinstance(payload, h5py.Group):
                karr_store = ChromosomeStore.from_hdf5_group(payload)
                update_chromosome = update.get("chromosome", {})
                if not isinstance(update_chromosome, dict):
                    update_chromosome = {}
                for field in chromosome_fields:
                    before_triplet = before_chrom_store.get_field(field)
                    if _triplet_counter(before_triplet) != _triplet_counter(karr_store.get_field(field)):
                        karr_chrom_active = True
                    if isinstance(update_chromosome.get(field), dict):
                        oc_triplet = ChromosomeStore.from_state_mapping(
                            {field: update_chromosome[field]},
                            shape=before_triplet.shape,
                        ).get_field(field)
                    else:
                        oc_triplet = before_triplet
                    chrom_mismatch = _first_sparse_mismatch(
                        field=field,
                        before_triplet=before_triplet,
                        oc_triplet=oc_triplet,
                        karr_triplet=karr_store.get_field(field),
                    )
                    if chrom_mismatch is not None:
                        mismatch_entries.append(chrom_mismatch)

            if karr_max_abs_observables >= 1.0 or karr_chrom_active:
                karr_active_any += 1

            if mismatch_entries:
                divergences.append(
                    {
                        "tick": tick,
                        "karr_active_observables": karr_max_abs_observables >= 1.0,
                        "karr_active_any": karr_max_abs_observables >= 1.0 or karr_chrom_active,
                        "bound_smc_before": float(
                            before_vectors["boundEnzymes"][process.enzyme_index_smc_adp]
                        ),
                        "complex_bound_sites_before": int(
                            before_chrom_store.get_field("complexBoundSites").calc_num_edges()
                        ),
                        "bound_smc_delta_update": float(
                            update.get("boundEnzymes", {}).get(process.smc_adp_wid, 0.0)
                        )
                        if isinstance(update.get("boundEnzymes"), dict)
                        else 0.0,
                        "free_smc_delta_update": float(
                            update.get("enzymes", {}).get(process.smc_wid, 0.0)
                        )
                        if isinstance(update.get("enzymes"), dict)
                        else 0.0,
                        "complex_bound_sites_update_edges": int(
                            len(
                                update.get("chromosome", {})
                                .get("complexBoundSites", {})
                                .get("values", [])
                            )
                        )
                        if isinstance(update.get("chromosome"), dict)
                        and isinstance(update.get("chromosome", {}).get("complexBoundSites"), dict)
                        else None,
                        "entries": mismatch_entries,
                    }
                )
            if len(divergences) >= MAX_TICKS_TO_REPORT:
                break

    return {
        "trace_path": str(trace_path),
        "divergences": divergences,
        "first_strict_failure": first_strict_failure,
        "karr_active_observable_ticks": karr_active_observables,
        "karr_active_any_ticks": karr_active_any,
        "n_ticks": ctx.n_ticks,
    }


def main() -> int:
    result = run_probe()
    print(f"Process: {PROCESS_NAME}")
    print(f"Trace: {result['trace_path']}")
    print(
        "Karr-active ticks (standard observables only, |delta| >= 1): "
        f"{result['karr_active_observable_ticks']}/{result['n_ticks']}"
    )
    print(
        "Karr-active ticks (standard observables or chromosome sparse fields changed): "
        f"{result['karr_active_any_ticks']}/{result['n_ticks']}"
    )

    first = result["first_strict_failure"]
    if first is None:
        print("No strict-rubric observable mismatch found.")
    else:
        print(
            "First strict-rubric mismatch: "
            f"tick={first['tick']} {_format_observable_mismatch(first['mismatch'])}"
        )

    print("")
    print(f"First {len(result['divergences'])} divergent ticks:")
    for tick_record in result["divergences"]:
        print(
            f"- tick={tick_record['tick']} "
            f"karr_active_observables={'yes' if tick_record['karr_active_observables'] else 'no'} "
            f"karr_active_any={'yes' if tick_record['karr_active_any'] else 'no'} "
            f"bound_smc_before={tick_record['bound_smc_before']:.0f} "
            f"complexBoundSites_before={tick_record['complex_bound_sites_before']} "
            f"bound_delta_update={tick_record['bound_smc_delta_update']:.0f} "
            f"free_smc_delta_update={tick_record['free_smc_delta_update']:.0f} "
            f"complexBoundSites_update_edges={tick_record['complex_bound_sites_update_edges']}"
        )
        for entry in tick_record["entries"]:
            if entry["kind"] == "observable":
                print(f"  {_format_observable_mismatch(entry)}")
            else:
                print(f"  {_format_chromosome_mismatch(entry)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
