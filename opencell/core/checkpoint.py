"""Checkpoint/restart: serialize simulation state to HDF5.

Enables resuming from any saved checkpoint. Note: exact-restart
is narrowed to same JAX/Diffrax/Python versions only — cross-version
bitwise identity is not guaranteed.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import h5py
import jax.numpy as jnp
import numpy as np

logger = logging.getLogger(__name__)


def save_checkpoint(
    filepath: str | Path,
    time_s: float,
    counts: np.ndarray | jnp.ndarray,
    species_ids: list[str],
    rng_key_data: np.ndarray | jnp.ndarray,
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Save simulation state to HDF5 checkpoint.

    Args:
        filepath: Output file path
        time_s: Current simulation time
        counts: Species counts array
        species_ids: Species ID list (for labeling)
        rng_key_data: Raw RNG key data
        metadata: Additional metadata dict

    Returns:
        Path to saved checkpoint
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    with h5py.File(filepath, "w") as f:
        f.attrs["time_s"] = time_s
        f.create_dataset("counts", data=np.asarray(counts))
        f.create_dataset("rng_key", data=np.asarray(rng_key_data))

        # Store species IDs as variable-length strings
        dt = h5py.string_dtype()
        ds = f.create_dataset("species_ids", shape=(len(species_ids),), dtype=dt)
        for i, sid in enumerate(species_ids):
            ds[i] = sid

        if metadata:
            f.attrs["metadata"] = json.dumps(metadata)

    logger.info(f"Checkpoint saved: {filepath} (t={time_s:.4f}s)")
    return filepath


def load_checkpoint(
    filepath: str | Path,
) -> dict[str, Any]:
    """Load simulation state from HDF5 checkpoint.

    Returns:
        Dict with keys: time_s, counts, species_ids, rng_key, metadata
    """
    filepath = Path(filepath)

    with h5py.File(filepath, "r") as f:
        time_s = float(f.attrs["time_s"])
        counts = np.array(f["counts"])
        rng_key_data = np.array(f["rng_key"])
        species_ids = [s.decode() if isinstance(s, bytes) else s for s in f["species_ids"]]

        metadata = {}
        if "metadata" in f.attrs:
            metadata = json.loads(f.attrs["metadata"])

    logger.info(f"Checkpoint loaded: {filepath} (t={time_s:.4f}s)")

    return {
        "time_s": time_s,
        "counts": counts,
        "species_ids": species_ids,
        "rng_key": rng_key_data,
        "metadata": metadata,
    }
