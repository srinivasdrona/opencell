"""Stride-1, fully enumerated event-window loader (D1).

Loads a single per-seed ``<Process>_100ticks.mat`` event-window trace (the
same v7.3/h5py container format ``tests/vivarium/l2_replay_common.py``
already reads) and refuses anything that is not a complete, dense,
event-window grid.

Discriminator between an event-window trace and a standard mid-cycle
per-tick trace (requirement 4, "refuse ... mid-cycle standard traces"):
verified empirically against both trace families on disk --

* event-window traces (``per_process_traces_v2_event_s{seed:03d}/``) carry
  ``metadata/tick_offset`` (float, ticks-from-division/reference anchor).
* standard mid-cycle traces (``per_process_traces_v2_s{seed:03d}/`` and the
  canonical ``per_process_traces_v2/`` seed-0 copies) do **not** have a
  ``tick_offset`` key in ``metadata`` at all.

This is a structural fact about the two extractor generations, not a
heuristic filename check, so it survives a file being renamed or moved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np

from scripts.l2_event.schema import RefusalReason

# Metadata keys the loader requires on *every* trace, event-window or not.
_REQUIRED_METADATA_KEYS = ("n_ticks", "process_name", "rng_seed")

# The key present only on event-window traces.
_EVENT_WINDOW_METADATA_KEY = "tick_offset"

_EVENT_WINDOW_DIR_RE = re.compile(r"per_process_traces_v2_event_s(\d+)")
_STANDARD_DIR_RE = re.compile(r"per_process_traces_v2(?:_s(\d+))?$")


class EventWindowRefused(Exception):
    """Raised when a trace fails a D1/requirement-4 refusal check.

    ``reason`` is one of :data:`scripts.l2_event.schema.RefusalReason` so
    callers (the runner) can map it to a stable exit code / status string
    without string-matching the message.
    """

    def __init__(self, reason: RefusalReason, message: str) -> None:
        super().__init__(message)
        self.reason: RefusalReason = reason


@dataclass(frozen=True)
class WindowGrid:
    """A fully enumerated, stride-1 per-tick event-window grid for one
    (process, seed) trace file."""

    process_name: str
    seed: int
    n_ticks: int
    tick_offset: float
    trace_path: Path
    observables: tuple[str, ...]
    states_before: dict[str, np.ndarray]
    states_after: dict[str, np.ndarray]

    def before(self, observable: str, tick: int) -> np.ndarray:
        return self.states_before[observable][tick]

    def after(self, observable: str, tick: int) -> np.ndarray:
        return self.states_after[observable][tick]


def _decode_char_metadata(raw: np.ndarray) -> str:
    """Decode a MATLAB char-array metadata field (stored as a uint16 column
    vector of code points) back to a Python string."""
    codes = np.asarray(raw).reshape(-1)
    return "".join(chr(int(c)) for c in codes)


def _cell_series(dataset: h5py.Dataset, handle: h5py.File) -> np.ndarray:
    """Materialize a MATLAB cell-array-of-vectors dataset (shape (1, n) of
    HDF5 object references, or a plain numeric (1, n) array) into an
    ``(n_ticks, k)`` numpy array, one row per tick."""
    if dataset.dtype == object:
        rows, cols = dataset.shape
        n = max(rows, cols)
        out: list[np.ndarray] = []
        for i in range(n):
            ref = dataset[0, i] if rows == 1 else dataset[i, 0]
            out.append(np.asarray(handle[ref][()]).reshape(-1))
        return np.stack(out, axis=0)
    # Plain numeric array already shaped (1, n_ticks) or (n_ticks, 1).
    arr = np.asarray(dataset[()])
    if arr.ndim == 2 and 1 in arr.shape:
        arr = arr.reshape(-1, 1) if arr.shape[0] != 1 else arr.T
        return arr
    raise ValueError(f"Unrecognized cell-series dataset shape: {dataset.shape}")


def classify_trace_dir(path: Path) -> str:
    """Best-effort human-readable classification of a trace's parent
    directory, for error messages and input_manifest.json's ``trace_kind``.
    Not used for the refusal decision itself (that is metadata-based)."""
    parent = path.parent.name
    if _EVENT_WINDOW_DIR_RE.search(parent):
        return "event_window"
    if _STANDARD_DIR_RE.search(parent) or parent == "per_process_traces_v2":
        return "standard_mid_cycle"
    return "unknown"


def load_event_window(
    trace_path: Path,
    *,
    required_observables: tuple[str, ...],
) -> WindowGrid:
    """Load and validate one event-window trace file.

    Raises :class:`EventWindowRefused` for every requirement-4 refusal case
    this module is responsible for:

    * ``MISSING_WINDOW`` -- file does not exist.
    * ``NOT_EVENT_WINDOW_TRACE`` -- metadata lacks ``tick_offset`` (i.e. this
      is a standard mid-cycle trace, not an event-window trace).
    * ``INCOMPLETE_WINDOW`` -- declared ``n_ticks`` does not match the
      per-observable dataset length for any requested observable, i.e. the
      grid is sparse/partial rather than a fully enumerated stride-1 window.
    """
    trace_path = Path(trace_path)
    if not trace_path.exists():
        raise EventWindowRefused(
            "MISSING_WINDOW", f"Event-window trace not found: {trace_path}"
        )

    with h5py.File(trace_path, "r") as handle:
        if "metadata" not in handle:
            raise EventWindowRefused(
                "NOT_EVENT_WINDOW_TRACE",
                f"{trace_path}: no 'metadata' group; not a recognized trace file.",
            )
        metadata = handle["metadata"]
        for key in _REQUIRED_METADATA_KEYS:
            if key not in metadata:
                raise EventWindowRefused(
                    "NOT_EVENT_WINDOW_TRACE",
                    f"{trace_path}: metadata missing required key '{key}'.",
                )
        if _EVENT_WINDOW_METADATA_KEY not in metadata:
            raise EventWindowRefused(
                "NOT_EVENT_WINDOW_TRACE",
                f"{trace_path}: metadata has no 'tick_offset' key -- this is a "
                "standard mid-cycle trace (per_process_traces_v2[_s*]), not an "
                "event-window trace. Day-28 audit: 0/50 seeds of these standard "
                "traces have substrate-change events for either target process; "
                "L2.event requires a stride-1 grid extracted over the declared "
                "firing window instead (spec §4 fact 8).",
            )

        n_ticks = int(np.asarray(metadata["n_ticks"][()]).reshape(-1)[0])
        tick_offset = float(np.asarray(metadata[_EVENT_WINDOW_METADATA_KEY][()]).reshape(-1)[0])
        rng_seed = int(np.asarray(metadata["rng_seed"][()]).reshape(-1)[0])
        process_name = _decode_char_metadata(np.asarray(metadata["process_name"][()]))

        if "states_before" not in handle or "states_after" not in handle:
            raise EventWindowRefused(
                "NOT_EVENT_WINDOW_TRACE",
                f"{trace_path}: missing 'states_before'/'states_after' groups.",
            )

        states_before: dict[str, np.ndarray] = {}
        states_after: dict[str, np.ndarray] = {}
        for observable in required_observables:
            for group_name, sink in (("states_before", states_before), ("states_after", states_after)):
                group = handle[group_name]
                if observable not in group:
                    raise EventWindowRefused(
                        "INCOMPLETE_WINDOW",
                        f"{trace_path}: observable '{observable}' missing from "
                        f"'{group_name}'.",
                    )
                series = _cell_series(group[observable], handle)
                if series.shape[0] != n_ticks:
                    raise EventWindowRefused(
                        "INCOMPLETE_WINDOW",
                        f"{trace_path}: observable '{observable}' in "
                        f"'{group_name}' has {series.shape[0]} tick rows, "
                        f"expected the fully enumerated n_ticks={n_ticks} "
                        "(stride-1, no gaps). A sparse/partial grid cannot "
                        "support event-window timing or count claims (D1).",
                    )
                sink[observable] = series

    return WindowGrid(
        process_name=process_name,
        seed=rng_seed,
        n_ticks=n_ticks,
        tick_offset=tick_offset,
        trace_path=trace_path,
        observables=tuple(required_observables),
        states_before=states_before,
        states_after=states_after,
    )
