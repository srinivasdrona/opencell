from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from scipy.io import loadmat

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
TESTS = REPO / "tests" / "vivarium"
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

from l2_2_replay_common_v2 import (  # noqa: E402
    _PROCESS_SPECS,
    _build_context,
    _inject_hidden_read_surface,
    _project_trace_vector,
    _trace_cell_payload,
)
from l2_replay_common import (  # noqa: E402
    build_state_template,
    overlay_observable_into_state,
    refresh_allocator_views,
    resolve_trace_path,
)

from opencell.state.chromosome_store import ChromosomeStore, SparseTriplet  # noqa: E402
from opencell.util.chromcond_mcg_rand import ChromCondMcgRandStream  # noqa: E402


def _mat_field_to_triplet(field: Any) -> SparseTriplet:
    positions = np.asarray(field.positions).reshape(-1).astype(np.int64, copy=False)
    strands = np.asarray(field.strands).reshape(-1).astype(np.int64, copy=False)
    values = np.asarray(field.values).reshape(-1).astype(np.int64, copy=False)
    shape_arr = np.asarray(field.shape).reshape(-1).astype(np.int64, copy=False)
    if shape_arr.size != 2:
        raise ValueError(f"unexpected sparse field shape payload: {shape_arr.tolist()}")
    if positions.size == 0:
        return SparseTriplet.empty(int(shape_arr[0]), int(shape_arr[1]))
    return SparseTriplet(
        positions=positions - 1,
        strands=strands - 1,
        values=values,
        shape=(int(shape_arr[0]), int(shape_arr[1])),
    )


def _load_prewarmup_artifact() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    artifact = loadmat(
        REPO / "tmp" / "chromcond_prewarmup_state.mat",
        squeeze_me=True,
        struct_as_record=False,
    )["artifact"]
    process = artifact.process
    chromosome = artifact.chromosome
    meta = artifact.metadata

    chromosome_state = {
        field_name: _mat_field_to_triplet(getattr(chromosome, field_name)).to_state()
        for field_name in chromosome._fieldnames
        if hasattr(getattr(chromosome, field_name), "positions")
    }
    process_state = {
        "substrates": np.asarray(process.substrates).reshape(-1).astype(np.int64).tolist(),
        "enzymes": np.asarray(process.enzymes).reshape(-1).astype(np.int64).tolist(),
        "boundEnzymes": np.asarray(process.boundEnzymes).reshape(-1).astype(np.int64).tolist(),
        "randStreamState": int(np.asarray(process.randStreamState).reshape(-1)[0]),
    }
    metadata = {
        "seed": int(np.asarray(meta.seed).reshape(-1)[0]),
        "target_slot": int(np.asarray(meta.target_init_order_slot_1based).reshape(-1)[0]),
    }
    return process_state, chromosome_state, metadata


def _apply_update(state: dict[str, Any], update: dict[str, Any]) -> None:
    for port in ("substrates", "enzymes", "boundEnzymes"):
        delta = update.get(port, {})
        if not isinstance(delta, dict):
            continue
        state_port = state.setdefault(port, {})
        for wid, change in delta.items():
            state_port[wid] = float(state_port.get(wid, 0.0) + float(change))
    chrom_update = update.get("chromosome", {})
    if isinstance(chrom_update, dict):
        chrom_state = state.setdefault("chromosome", {})
        for key, value in chrom_update.items():
            if isinstance(value, dict):
                chrom_state[key] = copy.deepcopy(value)
            else:
                chrom_state[key] = float(chrom_state.get(key, 0.0) + float(value))


def _value_counts(triplet: SparseTriplet) -> dict[int, int]:
    if triplet.calc_num_edges() == 0:
        return {}
    uniq, counts = np.unique(triplet.values.astype(np.int64, copy=False), return_counts=True)
    return {int(value): int(count) for value, count in zip(uniq, counts, strict=False)}


def _smc_site_set(store: ChromosomeStore, smc_adp_global_index: int) -> set[tuple[int, int]]:
    out: set[tuple[int, int]] = set()
    triplet = store.get_field("complexBoundSites")
    for pos, strand, value in triplet.to_regions():
        if int(value) == int(smc_adp_global_index):
            out.add((int(pos), int(strand)))
    return out


def _make_tick0_state(ctx) -> dict[str, Any]:  # noqa: ANN001
    spec = _PROCESS_SPECS[ctx.name]
    state = build_state_template(ctx.process)
    for obs in spec.observables:
        before = _project_trace_vector(ctx, "states_before", obs, 0)
        overlay_observable_into_state(
            process=ctx.process,
            state=state,
            observable=obs,
            vector=before,
            wids=ctx.wids_by_observable[obs],
            store_path_override=spec.store_path_override,
        )
    _inject_hidden_read_surface(ctx=ctx, state=state, tick=0)
    refresh_allocator_views(ctx.process, state)
    return state


def _make_warmup_state(process, chrom_state: dict[str, Any], proc_state: dict[str, Any]) -> dict[str, Any]:  # noqa: ANN001
    return {
        "chromosome": copy.deepcopy(chrom_state),
        "substrates": {
            wid: float(value)
            for wid, value in zip(process.substrate_wids, proc_state["substrates"], strict=False)
        },
        "enzymes": {
            wid: float(value)
            for wid, value in zip(process.enzyme_wids, proc_state["enzymes"], strict=False)
        },
        "boundEnzymes": {
            wid: float(value)
            for wid, value in zip(process.enzyme_wids, proc_state["boundEnzymes"], strict=False)
        },
    }


def _count_bound_smc(process, chrom_state: dict[str, Any]) -> int:  # noqa: ANN001
    store = ChromosomeStore.from_state_mapping(chrom_state, shape=process.chromosome_shape)
    return len(_smc_site_set(store, process.smc_adp_global_index))


def _warmup_evolve_state(process, warm_state: dict[str, Any]) -> dict[str, Any]:  # noqa: ANN001
    enzymes = warm_state["enzymes"]
    substrates = warm_state["substrates"]
    smc = float(enzymes.get(process.smc_wid, 0.0))
    smc_adp = float(enzymes.get(process.smc_adp_wid, 0.0))
    substrates[process.adp_wid] = float(substrates.get(process.adp_wid, 0.0) + smc_adp)
    smc += smc_adp
    smc_adp = 0.0

    atp = float(substrates.get(process.atp_wid, 0.0))
    water = float(substrates.get(process.water_wid, 0.0))
    n_binding_max = int(max(0.0, min(atp, water, smc)))
    if n_binding_max <= 0:
        enzymes[process.smc_wid] = smc
        enzymes[process.smc_adp_wid] = smc_adp
        return {"enzymes": {process.smc_wid: smc, process.smc_adp_wid: smc_adp}}

    current_bound_smc = _count_bound_smc(process, warm_state["chromosome"])
    n_bound, complex_next = process._sample_smc_binding_no_hints(
        n_binding_max=n_binding_max,
        chrom_state=warm_state["chromosome"],
        current_bound_smc=current_bound_smc,
    )
    if complex_next is not None:
        warm_state["chromosome"]["complexBoundSites"] = complex_next.to_state()
    smc -= float(n_bound)
    smc_adp += float(n_bound)
    substrates[process.atp_wid] = atp - float(n_bound)
    substrates[process.water_wid] = water - float(n_bound)
    substrates[process.pi_wid] = float(substrates.get(process.pi_wid, 0.0) + float(n_bound))
    substrates[process.hydrogen_wid] = float(substrates.get(process.hydrogen_wid, 0.0) + float(n_bound))
    enzymes[process.smc_wid] = smc
    enzymes[process.smc_adp_wid] = smc_adp
    return {
        "n_bound": n_bound,
        "enzymes": {process.smc_wid: smc, process.smc_adp_wid: smc_adp},
        "bound_smc": current_bound_smc + n_bound,
    }


def _warmup_next_update_style(process, warm_state: dict[str, Any]) -> dict[str, Any]:  # noqa: ANN001
    abundant = 1.0e12
    step_state = {
        "chromosome": warm_state["chromosome"],
        "substrates": warm_state["substrates"],
        "enzymes": warm_state["enzymes"],
        "boundEnzymes": warm_state["boundEnzymes"],
        "substrates_allocated": {
            process.name: {
                process.atp_wid: abundant,
                process.water_wid: abundant,
            }
        },
        "requests": {process.name: {process.atp_wid: 0.0, process.water_wid: 0.0}},
    }
    update = process.next_update(1.0, step_state)
    _apply_update(warm_state, update)
    return update


def main() -> int:
    proc_state, chrom_state, meta = _load_prewarmup_artifact()
    name = "ChromosomeCondensation"
    with h5py.File(resolve_trace_path(name), "r") as handle:
        ctx = _build_context(name=name, rng_seed=0, handle=handle)
        print("prewarmup_fixture_local", proc_state)
        tick0_before = _make_tick0_state(ctx)
        before_store = ChromosomeStore.from_state_mapping(
            tick0_before["chromosome"],
            shape=ctx.process.chromosome_shape,
        )
        karr_before = _smc_site_set(before_store, ctx.process.smc_adp_global_index)

        karr_after_payload = _trace_cell_payload(
            ctx=ctx,
            group="states_after",
            name="chromosome",
            tick=0,
        )
        if karr_after_payload is None:
            raise RuntimeError("missing tick-0 chromosome after payload")
        karr_after_store = ChromosomeStore.from_hdf5_group(karr_after_payload)
        karr_after = _smc_site_set(karr_after_store, ctx.process.smc_adp_global_index)
        print("prewarmup_complex_counts", _value_counts(ChromosomeStore.from_state_mapping(chrom_state, shape=ctx.process.chromosome_shape).get_field("complexBoundSites")))
        print("karr_tick0_new", sorted(karr_after - karr_before))

        scenarios = (
            ("evolveState", True, _warmup_evolve_state),
            ("evolveState", False, _warmup_evolve_state),
            ("next_update", True, _warmup_next_update_style),
            ("next_update", False, _warmup_next_update_style),
        )
        for mode_name, consume_inner, stepper in scenarios:
            warm_process = _build_context(name=name, rng_seed=0, handle=handle).process
            warm_process._rng = ChromCondMcgRandStream(meta["seed"])
            warm_process._rng.set_state(
                {
                    "generator": "mcg16807",
                    "seed": meta["seed"],
                    "mcg_state": proc_state["randStreamState"],
                }
            )
            if not consume_inner:
                warm_process._consume_inner_bind_sampling_literal = lambda **kwargs: None  # type: ignore[method-assign]
            warm_state = _make_warmup_state(warm_process, chrom_state, proc_state)
            warm_state["substrates"][warm_process.atp_wid] = 1.0e12
            warm_state["substrates"][warm_process.water_wid] = 1.0e12
            first_step = None
            last_step = None
            for step in range(20):
                out = stepper(warm_process, warm_state)
                if step == 0:
                    first_step = out
                if step == 19:
                    last_step = out

            warm_store = ChromosomeStore.from_state_mapping(
                warm_state["chromosome"],
                shape=warm_process.chromosome_shape,
            )
            replay_process = _build_context(name=name, rng_seed=0, handle=handle).process
            replay_process._rng = ChromCondMcgRandStream(meta["seed"])
            replay_process._rng.set_state(warm_process._rng.get_state())
            if not consume_inner:
                replay_process._consume_inner_bind_sampling_literal = lambda **kwargs: None  # type: ignore[method-assign]
            replay_state = _make_tick0_state(ctx)
            replay_update = replay_process.next_update(1.0, replay_state)
            _apply_update(replay_state, replay_update)
            replay_after_store = ChromosomeStore.from_state_mapping(
                replay_state["chromosome"],
                shape=replay_process.chromosome_shape,
            )
            replay_after = _smc_site_set(replay_after_store, replay_process.smc_adp_global_index)
            print(
                "scenario",
                {
                    "mode": mode_name,
                    "consume_inner": consume_inner,
                    "first_step": first_step,
                    "last_step": last_step,
                    "postwarmup_rng": warm_process._rng.get_state(),
                    "postwarmup_enzymes": warm_state["enzymes"],
                    "postwarmup_boundEnzymes": warm_state["boundEnzymes"],
                    "postwarmup_complex_counts": _value_counts(warm_store.get_field("complexBoundSites")),
                    "tick0_new": sorted(replay_after - karr_before),
                    "tick0_match": replay_after == karr_after,
                },
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
