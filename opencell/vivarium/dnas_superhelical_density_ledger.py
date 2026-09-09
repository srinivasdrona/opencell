"""Loader for the DNASupercoiling superhelical-density (sigma) input oracle.

Mirrors ``opencell.vivarium.dnas_chromosome_release_ledger``'s pattern
exactly, but for a different, previously undocumented source gap: the
canonical per-process trace (``per_process_traces_v2*/DNASupercoiling_
100ticks.mat`` -> HDF5) stores ``chromosome.linkingNumbers`` as int32. For
long-established dsDNA regions this loses no decision-relevant precision.
But for a BRAND-NEW region created by a replication-fork-like split within
the evaluation window, real MATLAB's ``DNASupercoiling.evolveState()``
reads the region's linking number as a genuinely fractional double
(``length / relaxedBasesPerTurn``, i.e. torsionally perfectly relaxed,
sigma EXACTLY 0.0). Rounding that fractional value to the nearest int32
before it ever reaches the trace shifts the reconstructed sigma away from
0.0 -- which can flip ``sigma > topoIVSigmaLimit`` from false to true,
making topoIV falsely "legal" in that region and causing spurious
activity-phase RNG draws / topoIV activity events that real MATLAB never
has.

Root-caused via ``scripts/matlab/l22_dnas_process_rng_region_probe.m``
(seed 0, tick 2): real MATLAB's sigma for the two newly-split 111bp
regions is exactly 0.0; the canonical trace's int32-rounded linkingNumbers
value of 11 reconstructs sigma = +0.0405 instead.

This ledger is a sidecar extraction
(``scripts/matlab/l22_dnas_linking_density_ledger.m`` /
``l22_dnas_linking_density_ledger_batch.m``) that captures the exact
double-precision sigma value for every positive dsDNA region, keyed by
(position, strand), for every tick of every seed in the frozen N=200 gate
corpus. It is an INPUT oracle -- ground-truth chromosome state, not a
biological decision or outcome -- and is wired in via
``ChromosomeStore``'s existing (previously unpopulated)
``superhelicalDensity`` hidden-sparse-field mechanism, exactly the
injection point ``_positive_region_sigmas_from_store`` already checks
first. No production DECISION logic changes; only ground-truth chromosome
state is supplied where it was previously reconstructed lossily.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

_DEFAULT_LEDGER_DIR = "data/l22_dnas_rare_event/linking_density_ledger"


def default_ledger_path(seed: int) -> Path:
    """Return the conventional per-seed ledger path (may not exist)."""
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / _DEFAULT_LEDGER_DIR / f"seed_{int(seed):03d}.json"


def _as_list(value: object) -> list:
    if isinstance(value, list):
        return value
    return [value]


class SuperhelicalDensityLedger:
    """Per-seed, per-tick ground-truth region-sigma ledger.

    Ledger entries store MATLAB's native 1-based ``positions``/``strands``;
    :meth:`hidden_field_for_tick` converts to the 0-based convention
    ``AuxiliarySparseField``/``ChromosomeStore`` expect (matching
    ``AuxiliarySparseField.from_hdf5_group``'s own ``- 1`` conversion for
    trace-sourced sparse fields).
    """

    def __init__(self, *, seed: int, ticks: dict[int, dict[str, list]]) -> None:
        self.seed = int(seed)
        self._ticks = ticks

    @classmethod
    def load(cls, path: str | Path) -> SuperhelicalDensityLedger:
        path = Path(path)
        raw = json.loads(path.read_text())
        seed = int(raw["seed"])
        ticks: dict[int, dict[str, list]] = {}
        for entry in raw["ticks"]:
            tick = int(entry["tick_zero_based"])
            ticks[tick] = {
                "positions": _as_list(entry.get("positions", [])),
                "strands": _as_list(entry.get("strands", [])),
                "sigmas": _as_list(entry.get("sigmas", [])),
            }
        return cls(seed=seed, ticks=ticks)

    def has_tick(self, tick: int) -> bool:
        return int(tick) in self._ticks

    def hidden_field_for_tick(self, tick: int, shape: tuple[int, int]) -> dict:
        entry = self._ticks[int(tick)]
        positions = np.asarray([int(p) - 1 for p in entry["positions"]], dtype=np.int64)
        strands = np.asarray([int(s) - 1 for s in entry["strands"]], dtype=np.int64)
        values = np.asarray([float(v) for v in entry["sigmas"]], dtype=np.float64)
        return {
            "positions": positions,
            "strands": strands,
            "values": values,
            "shape": shape,
        }

    @property
    def n_ticks(self) -> int:
        return len(self._ticks)
