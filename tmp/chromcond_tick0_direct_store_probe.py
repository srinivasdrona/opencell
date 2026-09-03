from __future__ import annotations

import sys
import types
from pathlib import Path

import h5py

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
from scipy.io import loadmat  # noqa: E402

from opencell.state.chromosome_store import ChromosomeStore  # noqa: E402
from opencell.util.chromcond_mcg_rand import ChromCondMcgRandStream  # noqa: E402


def _smc_sites(store: ChromosomeStore, smc_adp_global_index: int) -> set[tuple[int, int]]:
    return {
        (int(pos), int(strand))
        for pos, strand, value in store.get_field("complexBoundSites").to_regions()
        if int(value) == int(smc_adp_global_index)
    }


def _load_postwarmup_rng_state() -> int:
    artifact = loadmat(
        REPO / "tmp" / "chromcond_postwarmup_state.mat",
        squeeze_me=True,
        struct_as_record=False,
    )["artifact"]
    return int(artifact.post.randStreamState)


def _triplets(store: ChromosomeStore, field_name: str) -> set[tuple[int, int, int]]:
    triplet = store.get_field(field_name)
    return {
        (int(pos), int(strand), int(value))
        for pos, strand, value in triplet.to_regions()
    }


def main() -> int:
    name = "ChromosomeCondensation"
    spec = _PROCESS_SPECS[name]
    with h5py.File(resolve_trace_path(name), "r") as handle:
        ctx = _build_context(name=name, rng_seed=0, handle=handle)
        process = ctx.process
        process._rng = ChromCondMcgRandStream(0)
        process._rng.set_state(
            {
                "generator": "mcg16807",
                "seed": 0,
                "mcg_state": _load_postwarmup_rng_state(),
            }
        )

        def _direct_positions(self, *, bound_centroids, bound_strands, sequence_len):
            del self, bound_strands, sequence_len
            return [int(pos) for pos in bound_centroids]

        process._smc_centroids_to_start_positions = types.MethodType(  # type: ignore[method-assign]
            _direct_positions,
            process,
        )

        state = build_state_template(process)
        for obs in spec.observables:
            before = _project_trace_vector(ctx, "states_before", obs, 0)
            overlay_observable_into_state(
                process=process,
                state=state,
                observable=obs,
                vector=before,
                wids=ctx.wids_by_observable[obs],
                store_path_override=spec.store_path_override,
            )
        _inject_hidden_read_surface(ctx=ctx, state=state, tick=0)
        refresh_allocator_views(process, state)

        before_store = ChromosomeStore.from_state_mapping(
            state["chromosome"],
            shape=process.chromosome_shape,
        )
        before_sites = _smc_sites(before_store, process.smc_adp_global_index)

        update = process.next_update(1.0, state)
        after_store = ChromosomeStore.from_state_mapping(
            update.get("chromosome", {}),
            shape=process.chromosome_shape,
        )
        after_sites = _smc_sites(after_store, process.smc_adp_global_index)
        oc_new = sorted(after_sites - before_sites)

        after_payload = _trace_cell_payload(ctx=ctx, group="states_after", name="chromosome", tick=0)
        if after_payload is None:
            raise RuntimeError("missing Karr chromosome payload")
        karr_store = ChromosomeStore.from_hdf5_group(after_payload)
        karr_new = sorted(
            _smc_sites(karr_store, process.smc_adp_global_index)
            - _smc_sites(before_store, process.smc_adp_global_index)
        )

        print("tick0_new_sites_direct_store", oc_new)
        print("tick0_new_sites_karr", karr_new)
        print(
            "complex_bound_matches_karr",
            _triplets(after_store, "complexBoundSites") == _triplets(karr_store, "complexBoundSites"),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
