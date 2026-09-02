"""Stride-1, fully enumerated event-window loader (D1).

Loads a single per-seed ``<Process>_100ticks.mat`` event-window trace (the
same v7.3/h5py container format ``tests/vivarium/l2_replay_common.py``
already reads) and refuses anything that is not a complete, dense,
event-window grid.

Discriminator between an event-window trace and a standard mid-cycle
per-tick trace (requirement 4, "refuse ... mid-cycle standard traces"):
verified empirically against both trace families on disk --

* event-window traces (``per_process_traces_v2_event_s{seed:03d}/``) carry
  ``metadata/tick_offset`` (float): for ``window_contract='fixed'`` this is
  the caller-supplied burn-in tick COUNT (``tick_start == tick_offset + 1``,
  a single absolute 1-based simulation-tick coordinate system -- see
  ``WindowGrid.absolute_tick``); for ``window_contract='anchor'`` it is
  always 0 (no burn-in exists for an anchor window; the window's own
  ``tick_start``/``window_anchor``/``onset_tick`` are separately discovered,
  see below). ``tick_offset`` is never timing arithmetic on its own.
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

# M4 (Opus5 review): the stride/window-boundary metadata contract a future
# extractor must satisfy for a trace to be usable by a real (non-smoke)
# gate computation. `stride` must be present and == 1 (fully enumerated,
# no skipped ticks); `tick_start` must be present; and at least one of
# `tick_end`/`window_anchor` must be present ("as applicable" -- a fixed
# window records tick_end, a division-anchored window may instead record
# window_anchor). None of the two real event MATs on disk today (RA/RNAM
# seed 000) carry any of these three -- see
# docs/phase_f/l2_event/EVENT_WINDOW_EXTRACTOR_CONTRACT.md.
_STRIDE_CONTRACT_STRIDE_KEY = "stride"
_STRIDE_CONTRACT_START_KEY = "tick_start"
_STRIDE_CONTRACT_END_KEYS = ("tick_end", "window_anchor")

# The real, observed TIMING anchor for a 'diameter_decrease'-style anchor
# window (ratified Cytokinesis decision, 2026-08-02): the first strict
# pinchedDiameter decrease. Distinct from `window_anchor`, which remains the
# CAPTURE-boundary (completion) tick the fixed n_ticks window ends at.
# Optional: absent for 'boolean_transition' (single-event, no interval)
# anchor windows and for all fixed windows.
_ONSET_TICK_KEY = "onset_tick"

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


def _read_optional_scalar(metadata: h5py.Group, key: str) -> tuple[float | None, str | None]:
    """Read an optional scalar numeric metadata field.

    Returns ``(value, problem)``:

    * key absent -> ``(None, None)`` -- absence alone is not a problem here;
      callers (``_check_stride_contract``) decide whether a given key is
      required.
    * key present but not scalar, not numeric-castable, or non-finite (NaN/
      inf) -> ``(None, "<problem message>")``.
    * key present and a finite scalar -> ``(float(value), None)``.

    Never raises -- this is the single choke point that turns a malformed
    metadata field into a human-readable refusal reason instead of an
    uncaught exception.
    """
    if key not in metadata:
        return None, None
    try:
        raw = np.asarray(metadata[key][()])
        flat = raw.reshape(-1)
        if flat.size != 1:
            return None, f"metadata '{key}' is not scalar (shape {raw.shape})"
        value = float(flat[0])
    except (TypeError, ValueError) as exc:
        return None, f"metadata '{key}' is not numeric-castable ({exc})"
    if not np.isfinite(value):
        return None, f"metadata '{key}'={value} is not finite"
    return value, None


def _parse_window_bounds(metadata: h5py.Group) -> dict[str, int | None]:
    """Best-effort parse of the M4 tick_start/tick_end/window_anchor/
    onset_tick metadata keys, for populating :class:`WindowGrid` regardless
    of stride-contract compliance. A key that is absent or fails to parse as
    a finite scalar maps to ``None`` here (never raises); ``load_event_window``
    separately decides whether that absence/malformation is fatal via
    ``_check_stride_contract``."""
    result: dict[str, int | None] = {}
    for key in (_STRIDE_CONTRACT_START_KEY, "tick_end", "window_anchor", _ONSET_TICK_KEY):
        value, problem = _read_optional_scalar(metadata, key)
        result[key] = int(value) if (value is not None and problem is None) else None
    return result


def _check_stride_contract(metadata: h5py.Group) -> list[str]:
    """Return a list of human-readable problems against the M4 stride/
    window-boundary metadata contract (empty list = fully compliant).
    Never raises -- callers decide whether to treat this as fatal
    (``require_stride_contract=True``, the default) or advisory-only (the
    structural smoke path, which explicitly opts out)."""
    problems: list[str] = []
    if _STRIDE_CONTRACT_STRIDE_KEY not in metadata:
        problems.append(f"metadata missing required key '{_STRIDE_CONTRACT_STRIDE_KEY}'")
    else:
        stride_val, problem = _read_optional_scalar(metadata, _STRIDE_CONTRACT_STRIDE_KEY)
        if problem:
            problems.append(problem)
        elif int(stride_val) != 1:
            problems.append(f"metadata '{_STRIDE_CONTRACT_STRIDE_KEY}'={int(stride_val)}, expected 1 (D1 fully enumerated stride-1 window)")

    tick_start_val: float | None = None
    if _STRIDE_CONTRACT_START_KEY not in metadata:
        problems.append(f"metadata missing required key '{_STRIDE_CONTRACT_START_KEY}'")
    else:
        tick_start_val, problem = _read_optional_scalar(metadata, _STRIDE_CONTRACT_START_KEY)
        if problem:
            problems.append(problem)

    if not any(key in metadata for key in _STRIDE_CONTRACT_END_KEYS):
        problems.append(
            f"metadata missing both '{_STRIDE_CONTRACT_END_KEYS[0]}' and "
            f"'{_STRIDE_CONTRACT_END_KEYS[1]}' (at least one required, 'as applicable')"
        )

    tick_end_val: float | None = None
    if "tick_end" in metadata:
        tick_end_val, problem = _read_optional_scalar(metadata, "tick_end")
        if problem:
            problems.append(problem)
    window_anchor_val: float | None = None
    if "window_anchor" in metadata:
        window_anchor_val, problem = _read_optional_scalar(metadata, "window_anchor")
        if problem:
            problems.append(problem)

    if tick_start_val is not None and tick_end_val is not None and tick_end_val < tick_start_val:
        problems.append(f"metadata 'tick_end' ({tick_end_val}) < 'tick_start' ({tick_start_val})")
    if tick_start_val is not None and window_anchor_val is not None and window_anchor_val < tick_start_val:
        problems.append(f"metadata 'window_anchor' ({window_anchor_val}) < 'tick_start' ({tick_start_val})")

    if _ONSET_TICK_KEY in metadata:
        onset_val, problem = _read_optional_scalar(metadata, _ONSET_TICK_KEY)
        if problem:
            problems.append(problem)
        elif onset_val is not None:
            if window_anchor_val is None:
                problems.append(
                    f"metadata has '{_ONSET_TICK_KEY}' but no 'window_anchor' (completion) -- an onset "
                    "TIMING anchor without a completion CAPTURE-boundary is not a valid anchor window"
                )
            else:
                if tick_start_val is not None and onset_val < tick_start_val:
                    problems.append(
                        f"metadata '{_ONSET_TICK_KEY}' ({onset_val}) precedes 'tick_start' ({tick_start_val})"
                    )
                if onset_val >= window_anchor_val:
                    problems.append(
                        f"metadata '{_ONSET_TICK_KEY}' ({onset_val}) does not strictly precede "
                        f"'window_anchor' ({window_anchor_val}) -- onset_tick is the observed TIMING "
                        "anchor and must strictly precede the CAPTURE-boundary completion tick"
                    )
    return problems


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
    #: M4 stride/window-boundary metadata contract problems. Empty when the
    #: trace is fully compliant. Only ever non-empty when the caller passed
    #: ``require_stride_contract=False`` (otherwise a non-empty list would
    #: have raised ``EventWindowRefused`` instead of returning a grid).
    stride_contract_problems: tuple[str, ...] = ()
    #: Absolute 1-based simulation tick the grid's row 0 corresponds to
    #: (row i -> tick_start + i, see ``absolute_tick``). ``None`` if the
    #: trace never declared ``metadata/tick_start`` (pre-M4 traces).
    tick_start: int | None = None
    #: Fixed-window boundary (mutually informative with ``window_anchor``,
    #: never both meaningfully required at once). ``None`` for anchor
    #: windows and pre-M4 traces.
    tick_end: int | None = None
    #: Anchor-window CAPTURE boundary: the observed completion tick the
    #: fixed n_ticks window ends at. ``None`` for fixed windows and pre-M4
    #: traces. Aliased as ``completion_tick`` below -- this is the single
    #: persisted field; there is no redundant second completion key.
    window_anchor: int | None = None
    #: Anchor-window TIMING anchor: the observed first strict
    #: ``pinchedDiameter`` decrease (ratified Cytokinesis decision,
    #: 2026-08-02). ``None`` for fixed windows, 'boolean_transition'-kind
    #: anchor windows (single event, no interval), and pre-M4 traces.
    #: ``tick_offset`` is never a substitute for this field.
    onset_tick: int | None = None

    @property
    def stride_contract_ok(self) -> bool:
        return len(self.stride_contract_problems) == 0

    @property
    def completion_tick(self) -> int | None:
        """Alias for ``window_anchor`` -- the observed completion/capture-
        boundary tick. Derived, not persisted, so the metadata contract
        never carries a redundant second completion field."""
        return self.window_anchor

    def absolute_tick(self, row: int) -> int:
        """Map a 0-based local grid row to its absolute 1-based simulation
        tick: ``tick_start + row`` (the single coordinate system every M4
        tick field -- tick_start/tick_end/window_anchor/onset_tick -- shares).
        Raises ``ValueError`` if this trace never declared ``tick_start``."""
        if self.tick_start is None:
            raise ValueError(
                f"{self.trace_path}: cannot map row {row} to an absolute tick -- "
                "metadata has no 'tick_start' (pre-M4 trace)."
            )
        return self.tick_start + row

    def before(self, observable: str, tick: int) -> np.ndarray:
        return self.states_before[observable][tick]

    def after(self, observable: str, tick: int) -> np.ndarray:
        return self.states_after[observable][tick]


def _decode_char_metadata(raw: np.ndarray) -> str:
    """Decode a MATLAB char-array metadata field (stored as a uint16 column
    vector of code points) back to a Python string."""
    codes = np.asarray(raw).reshape(-1)
    return "".join(chr(int(c)) for c in codes)


def _materialize_group_payload(group: h5py.Group) -> dict[str, object]:
    """Recursively copy an HDF5 group payload into plain Python/numpy data.

    Real chromosome snapshots are stored as MATLAB cell entries that point at
    HDF5 groups, not numeric datasets. `load_event_window` closes the file
    before returning, so we must materialize those payloads eagerly rather
    than returning live h5py objects tied to a soon-to-be-closed handle.
    """
    out: dict[str, object] = {}
    for key, value in group.items():
        if isinstance(value, h5py.Dataset):
            out[key] = np.asarray(value[()])
        elif isinstance(value, h5py.Group):
            out[key] = _materialize_group_payload(value)
        else:
            raise ValueError(f"Unsupported HDF5 object {type(value).__name__} at {value.name}")
    return out


def _materialize_cell_payload(payload: h5py.Dataset | h5py.Group) -> np.ndarray:
    """Normalize one MATLAB cell entry to a stable per-tick numpy row."""
    if isinstance(payload, h5py.Dataset):
        return np.asarray(payload[()]).reshape(-1)
    if isinstance(payload, h5py.Group):
        return np.array([_materialize_group_payload(payload)], dtype=object)
    raise ValueError(f"Unsupported cell payload type: {type(payload).__name__}")


def _cell_series(dataset: h5py.Dataset, handle: h5py.File) -> np.ndarray:
    """Materialize a MATLAB cell-array-of-vectors dataset (shape (1, n) of
    HDF5 object references, or a plain numeric (1, n) array) into an
    ``(n_ticks, k)`` numpy array, one row per tick.

    Some real observables, notably chromosome snapshots for chromosome-primary
    processes, store each tick as a reference to an HDF5 group rather than a
    numeric dataset. Those payloads are recursively copied into plain Python
    dicts so the returned series remains valid after the file handle closes.
    """
    if dataset.dtype == object:
        rows, cols = dataset.shape
        n = max(rows, cols)
        out: list[np.ndarray] = []
        for i in range(n):
            ref = dataset[0, i] if rows == 1 else dataset[i, 0]
            out.append(_materialize_cell_payload(handle[ref]))
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
    require_stride_contract: bool = True,
    require_scalar_finite_observables: tuple[str, ...] = (),
) -> WindowGrid:
    """Load and validate one event-window trace file.

    Raises :class:`EventWindowRefused` for every requirement-4 refusal case
    this module is responsible for:

    * ``MISSING_WINDOW`` -- file does not exist.
    * ``NOT_EVENT_WINDOW_TRACE`` -- metadata lacks ``tick_offset`` (i.e. this
      is a standard mid-cycle trace, not an event-window trace).
    * ``INCOMPLETE_WINDOW`` -- declared ``n_ticks`` does not match the
      per-observable dataset length for any requested observable, i.e. the
      grid is sparse/partial rather than a fully enumerated stride-1 window;
      (M4) the trace fails the ``stride``/``tick_start``/``tick_end``-or-
      ``window_anchor``/``onset_tick`` metadata contract and
      ``require_stride_contract`` is ``True`` (the default); or an
      observable named in ``require_scalar_finite_observables`` is missing,
      non-scalar, non-numeric/logical, or non-finite (NaN/inf) for any tick.

    ``require_scalar_finite_observables`` (must be a subset of
    ``required_observables``) is for the flattened numeric event-observable
    projection an anchor-window extraction adds (e.g. Cytokinesis's
    ``pinchedDiameter``/``ftsZRing_*`` witnesses) -- these must be present,
    scalar, and finite for every tick for onset/completion timing claims to
    be meaningful; a generic caller with no such observables passes ``()``
    (the default) and gets no additional checks beyond the existing per-
    observable tick-count check below.

    ``require_stride_contract=False`` is for read-only structural-smoke
    callers ONLY (see ``scripts/l2_event/runner.run_structural_smoke``):
    instead of raising, any M4 contract problems are attached to the
    returned grid's ``stride_contract_problems``/``stride_contract_ok`` so
    the caller can surface them as an explicit INCOMPLETE annotation
    without ever claiming the smoke satisfies a real gate's window
    requirements.
    """
    if not set(require_scalar_finite_observables) <= set(required_observables):
        raise ValueError(
            "require_scalar_finite_observables must be a subset of required_observables; "
            f"got {require_scalar_finite_observables!r} not <= {required_observables!r}"
        )

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

        stride_problems = _check_stride_contract(metadata)
        if stride_problems and require_stride_contract:
            raise EventWindowRefused(
                "INCOMPLETE_WINDOW",
                f"{trace_path}: fails the stride/window-boundary metadata "
                f"contract (M4, docs/phase_f/l2_event/"
                f"EVENT_WINDOW_EXTRACTOR_CONTRACT.md): {'; '.join(stride_problems)}.",
            )

        window_bounds = _parse_window_bounds(metadata)

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
                if observable in require_scalar_finite_observables:
                    if series.shape[1] != 1:
                        raise EventWindowRefused(
                            "INCOMPLETE_WINDOW",
                            f"{trace_path}: observable '{observable}' in "
                            f"'{group_name}' is not scalar-per-tick (shape "
                            f"{series.shape}) -- required for a numeric "
                            "event-observable projection.",
                        )
                    numeric_series = series.astype(float, copy=False)
                    if not np.all(np.isfinite(numeric_series)):
                        raise EventWindowRefused(
                            "INCOMPLETE_WINDOW",
                            f"{trace_path}: observable '{observable}' in "
                            f"'{group_name}' has a non-finite (NaN/inf) value "
                            "-- an event-observable projection must be finite "
                            "for every tick.",
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
        stride_contract_problems=tuple(stride_problems),
        tick_start=window_bounds[_STRIDE_CONTRACT_START_KEY],
        tick_end=window_bounds["tick_end"],
        window_anchor=window_bounds["window_anchor"],
        onset_tick=window_bounds[_ONSET_TICK_KEY],
    )
