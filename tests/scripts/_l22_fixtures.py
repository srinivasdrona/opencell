"""Shared synthetic-MAT-fixture helpers for L2.2 extraction tooling tests.

Builds minimal HDF5 files that mimic the *shape* of a real
`extract_per_process_traces_v2.m` output (`states_before`/`states_after`
groups of MATLAB-style cell-array-of-object-reference channels, plus a
`metadata` group) without requiring MATLAB or any real Karr trace data.
"""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np


def write_synthetic_trace(
    path: Path,
    *,
    process_name: str,
    seed: int,
    n_ticks: int = 4,
    channel_width: int = 3,
    channels: tuple[str, ...] = ("substrates", "enzymes"),
) -> Path:
    """Write a minimal but structurally faithful synthetic trace MAT.

    Each channel is written the way MATLAB's `-v7.3` cell-array export does:
    a (1, n_ticks) array of HDF5 object references, each pointing at a small
    numeric dataset (the per-tick vector). This is exactly the layout
    `_matlab_channel_matrix`/`trace_validation._first_channel_tick_count`
    expect to walk.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    with h5py.File(path, "w") as handle:
        for section in ("states_before", "states_after"):
            group = handle.create_group(section)
            for channel in channels:
                refs = np.empty((1, n_ticks), dtype=h5py.special_dtype(ref=h5py.Reference))
                for tick in range(n_ticks):
                    vector = rng.random(channel_width)
                    dset = handle.create_dataset(f"__data/{section}/{channel}/{tick}", data=vector)
                    refs[0, tick] = dset.ref
                group.create_dataset(channel, data=refs, dtype=h5py.special_dtype(ref=h5py.Reference))

        meta = handle.create_group("metadata")
        meta.create_dataset("process_name", data=np.array([ord(c) for c in process_name], dtype=np.uint16))
        meta.create_dataset("n_ticks", data=np.array([n_ticks], dtype=np.float64))
        meta.create_dataset("rng_seed", data=np.array([seed], dtype=np.float64))
        meta.create_dataset("tick_offset", data=np.array([0], dtype=np.float64))
        timestamp = "2026-07-28 00:00:00"
        meta.create_dataset("timestamp", data=np.array([ord(c) for c in timestamp], dtype=np.uint16))
    return path
