"""Quiescence probe for 8 deterministic process oracles.

For each .mat (HDF5 v7.3), enumerate observables under states_before/ and
states_after/, compare per-cell per-tick. Report quiescence fraction
(triples where before == after / total triples) and which observables move.
"""
from __future__ import annotations
import sys
from pathlib import Path
import h5py
import numpy as np

# (process_name, path_to_mat) — using re-extracted files for the 7 truncated ones
OPENCELL = Path("/mnt/e/opencell")
REEXTRACT = Path("/mnt/e/opencell-worktrees/l2-matlab-reextract")

TARGETS = [
    ("ChromosomeSegregation", OPENCELL / "data/m1_sources/karr_native/per_process_traces/ChromosomeSegregation_100ticks.mat"),
    ("Cytokinesis", OPENCELL / "data/m1_sources/karr_native/per_process_traces/Cytokinesis_100ticks.mat"),
    ("Metabolism", OPENCELL / "data/m1_sources/karr_native/per_process_traces/Metabolism_100ticks.mat"),
    ("ProteinActivation", OPENCELL / "data/m1_sources/karr_native/per_process_traces/ProteinActivation_100ticks.mat"),
    ("Replication", REEXTRACT / "data/m1_sources/karr_native/per_process_traces/Replication_100ticks.mat"),
    ("TerminalOrganelleAssembly", OPENCELL / "data/m1_sources/karr_native/per_process_traces/TerminalOrganelleAssembly_100ticks.mat"),
    ("Transcription", REEXTRACT / "data/m1_sources/karr_native/per_process_traces/Transcription_100ticks.mat"),
    ("Translation", REEXTRACT / "data/m1_sources/karr_native/per_process_traces/Translation_100ticks.mat"),
]


def deref(f: h5py.File, ref):
    return np.asarray(f[ref])


def probe(name: str, path: Path) -> dict:
    if not path.exists():
        return {"name": name, "error": f"missing: {path}"}
    with h5py.File(path, "r") as f:
        # Two layouts seen in this project:
        # (A) /states_before/<obs> as group of refs (re-extracted)
        # (B) /states_before/<obs> as direct dataset (original karr_native)
        if "states_before" not in f:
            return {"name": name, "error": f"no /states_before group; top-level keys: {list(f.keys())}"}
        sb_group = f["states_before"]
        sa_group = f["states_after"]
        obs_names = list(sb_group.keys())
        per_obs = {}
        total_triples = 0
        quiescent_triples = 0
        for obs in obs_names:
            try:
                sb_ds = sb_group[obs]
                sa_ds = sa_group[obs]
                # Both layouts: collect arrays per tick
                if sb_ds.dtype == h5py.ref_dtype:
                    # Determine tick axis: pick the axis of size 100 (n_ticks);
                    # original layout is (100,1), re-extracted layout is (1,100).
                    shp = sb_ds.shape
                    if 100 in shp:
                        tick_axis = shp.index(100)
                    else:
                        tick_axis = int(np.argmax(shp))
                    n_ticks = shp[tick_axis]
                    diffs = 0
                    triples_obs = 0
                    moved_ticks = 0
                    for t in range(n_ticks):
                        idx = (t, 0) if tick_axis == 0 else (0, t)
                        a = deref(f, sb_ds[idx])
                        b = deref(f, sa_ds[idx])
                        eq = (a == b)
                        n_triples_here = eq.size
                        n_eq = int(np.sum(eq))
                        triples_obs += n_triples_here
                        diffs += (n_triples_here - n_eq)
                        if n_eq != n_triples_here:
                            moved_ticks += 1
                    per_obs[obs] = {
                        "shape_per_tick": tuple(np.asarray(deref(f, sb_ds[0, 0])).shape),
                        "n_ticks": n_ticks,
                        "triples": triples_obs,
                        "moved_triples": diffs,
                        "moved_ticks": moved_ticks,
                        "quiescence_frac": (triples_obs - diffs) / max(1, triples_obs),
                    }
                    total_triples += triples_obs
                    quiescent_triples += (triples_obs - diffs)
                else:
                    # layout B: direct dataset
                    sb_arr = np.asarray(sb_ds)
                    sa_arr = np.asarray(sa_ds)
                    eq = (sb_arr == sa_arr)
                    triples_obs = eq.size
                    n_eq = int(np.sum(eq))
                    moved_triples = triples_obs - n_eq
                    # tick axis is typically last; report moved ticks
                    # heuristic: pick the axis with smallest dim < 1000 as ticks
                    moved_ticks = 0
                    if sb_arr.ndim >= 2:
                        try:
                            tick_axis = int(np.argmin(sb_arr.shape))
                            tick_diff = np.any(sb_arr != sa_arr, axis=tuple(i for i in range(sb_arr.ndim) if i != tick_axis))
                            moved_ticks = int(np.sum(tick_diff))
                        except Exception:
                            moved_ticks = -1
                    per_obs[obs] = {
                        "shape": tuple(sb_arr.shape),
                        "dtype": str(sb_arr.dtype),
                        "triples": triples_obs,
                        "moved_triples": moved_triples,
                        "moved_ticks": moved_ticks,
                        "quiescence_frac": n_eq / max(1, triples_obs),
                    }
                    total_triples += triples_obs
                    quiescent_triples += n_eq
            except Exception as e:
                per_obs[obs] = {"error": str(e)}
        overall_q = quiescent_triples / max(1, total_triples)
        return {
            "name": name,
            "path": str(path),
            "n_obs": len(obs_names),
            "overall_quiescence": overall_q,
            "total_triples": total_triples,
            "per_observable": per_obs,
        }


if __name__ == "__main__":
    print(f"{'process':<30} {'n_obs':>5} {'q_frac':>8} {'triples':>10}  moved-observables")
    print("-" * 110)
    for name, path in TARGETS:
        r = probe(name, path)
        if "error" in r:
            print(f"{name:<30} ERROR: {r['error']}")
            continue
        moved = [
            f"{obs}({d.get('moved_triples', '?')}/{d.get('triples', '?')})"
            for obs, d in r["per_observable"].items()
            if isinstance(d, dict) and d.get("moved_triples", 0) > 0
        ]
        moved_str = ", ".join(moved) if moved else "(all quiescent)"
        print(f"{r['name']:<30} {r['n_obs']:>5} {r['overall_quiescence']:>8.3f} {r['total_triples']:>10}  {moved_str}")
