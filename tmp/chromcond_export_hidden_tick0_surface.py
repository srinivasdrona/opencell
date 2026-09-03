from __future__ import annotations

# ruff: noqa: E402,I001,ANN001,B009

import sys
from pathlib import Path

import h5py
import numpy as np
from scipy.io import loadmat, savemat

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
TESTS = REPO / "tests" / "vivarium"
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

from l2_2_replay_common_v2 import _PROCESS_SPECS, _build_context, _inject_hidden_read_surface, _project_trace_vector
from l2_replay_common import build_state_template, overlay_observable_into_state, refresh_allocator_views, resolve_trace_path
from opencell.state.chromosome_store import CHROMOSOME_FIELDS, ChromosomeStore


def _load_postwarmup_rng_state() -> int:
    artifact = loadmat(
        REPO / "tmp" / "chromcond_postwarmup_state.mat",
        squeeze_me=True,
        struct_as_record=False,
    )["artifact"]
    return int(getattr(artifact, "post").randStreamState)


def _triplet_to_matlab_struct(triplet) -> dict[str, np.ndarray]:
    positions = np.asarray(triplet.positions, dtype=np.int64).reshape(-1, 1) + 1
    strands = np.asarray(triplet.strands, dtype=np.int8).reshape(-1, 1) + 1
    values = np.asarray(triplet.values).reshape(-1, 1)
    if values.dtype.kind == "b":
        values = values.astype(np.bool_, copy=False)
    else:
        values = values.astype(np.int32, copy=False)
    return {
        "positions": positions,
        "strands": strands,
        "values": values,
        "shape": np.asarray(triplet.shape, dtype=np.int64).reshape(1, -1),
        "error": "",
    }


def main() -> int:
    name = "ChromosomeCondensation"
    spec = _PROCESS_SPECS[name]
    with h5py.File(resolve_trace_path(name), "r") as handle:
        ctx = _build_context(name=name, rng_seed=0, handle=handle)
        process = ctx.process
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

    store = ChromosomeStore.from_state_mapping(state["chromosome"], shape=process.chromosome_shape)
    chrom = {
        "sequenceLen": np.int64(process.chromosome_shape[0]),
        "nCompartments": np.int8(process.chromosome_shape[1]),
    }
    for field_name in CHROMOSOME_FIELDS:
        chrom[field_name] = _triplet_to_matlab_struct(store.get_field(field_name))

    out = {
        "artifact": {
            "metadata": {
                "tick": np.int64(0),
                "process": name,
            },
            "postwarmup": {
                "randStreamState": np.int64(_load_postwarmup_rng_state()),
            },
            "hidden": {
                "substrates": np.asarray(
                    [state["substrates"].get(wid, 0.0) for wid in process.substrate_wids],
                    dtype=np.float64,
                ).reshape(1, -1),
                "enzymes": np.asarray(
                    [state["enzymes"].get(wid, 0.0) for wid in process.enzyme_wids],
                    dtype=np.float64,
                ).reshape(1, -1),
                "boundEnzymes": np.asarray(
                    [state["boundEnzymes"].get(wid, 0.0) for wid in process.enzyme_wids],
                    dtype=np.float64,
                ).reshape(1, -1),
                "chromosome": chrom,
            },
        }
    }
    out_path = REPO / "tmp" / "chromcond_hidden_tick0_exact_surface.mat"
    savemat(out_path, out)
    print(f"saved {out_path}")
    print("postwarmup_randStreamState", int(out["artifact"]["postwarmup"]["randStreamState"]))
    print("hidden_substrates", out["artifact"]["hidden"]["substrates"].reshape(-1).tolist())
    print("hidden_enzymes", out["artifact"]["hidden"]["enzymes"].reshape(-1).tolist())
    print("hidden_boundEnzymes", out["artifact"]["hidden"]["boundEnzymes"].reshape(-1).tolist())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
