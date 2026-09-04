"""Read-only survey of the Cytokinesis onset-to-completion span across
however many seed event-window traces currently exist on disk under
``data/m1_sources/karr_native/per_process_traces_v2_event_s*/Cytokinesis_*ticks.mat``.

Purpose: this is the tool the catalog owner should run, once ALL 50
seeds of the required event-window ensemble exist, to determine the
COHORT-WIDE MAXIMUM onset-to-completion span before authorizing an
N=50 sweep -- see ``docs/phase_f/l2_event/event_registry.yaml``'s
Cytokinesis notes and ``docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml``'s
Cytokinesis ``M_ticks``/``seed_window`` fields (reconciled 2026-08-05 to
the seed-0 LOWER BOUND, `event_sweep_blocked_on` (formerly `blocked_on`)
pending this survey for the real cohort-wide maximum).

Hard rule: this script NEVER launches a MATLAB extraction itself. It
only reads whatever traces already exist. If fewer than 50 seeds are
present it reports the partial survey and explicitly REFUSES to claim a
cohort-wide maximum (only a lower bound over the seeds actually
present) -- inventing/interpolating a full-cohort number from a partial
sample would be exactly the kind of unauthorized N=50 shortcut this
project's hard rules forbid. Generating the missing seeds must go
through the established resumable/atomic launcher
(``scripts/l2_event/launcher.py``), one seed at a time, under
supervision -- never as an uncontrolled bulk run started by this
script.

2026-09-04 (Cytokinesis window fix, corrective pass): this script now
filters strictly to ONE preregistered ``M_ticks`` value at a time
(``--m-ticks``, default read from the single-source-of-truth
``docs/phase_f/l2_event/division_window_spec.json``) so a cohort that
mixes traces preregistered under different ``M_ticks`` values (e.g. the
34 preserved-but-non-authoritative M_ticks=4000 traces alongside a new
M_ticks=5000 trace) can never be silently averaged/max'd together as if
they were one comparable population. A trace whose FILENAME encodes the
requested ``M_ticks`` but whose own on-disk ``metadata.n_ticks`` disagrees
is a fail-closed error (a corrupted/mislabeled file), never a silent
skip.

2026-09-04 (Opus final review, pre-bulk mechanical fix -- the
"provisional-margin gate"): this script ALSO fails closed if any
surveyed seed's real inclusive onset-to-completion span
(``completion_tick - onset_tick + 1``) leaves zero or negative margin
against ``m_ticks`` (i.e. ``inclusive_span >= m_ticks``) -- see
``scripts.l2_event.division_window_spec.check_inclusive_span_margin``/
``ProvisionalMarginOverrunError``. This is a stricter, additional,
application-level check independent of the MATLAB extractor's own
capture-completeness invariant (which is left unchanged and still only
requires ``inclusive_span <= m_ticks``): as long as
``m_ticks_status: PROVISIONAL`` in ``division_window_spec.json``, a
zero-margin observation must trigger the same escalation-policy response
a true overrun would, never be silently accepted as "just barely fits."
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event.adapters.cytokinesis import (  # noqa: E402
    find_completion_tick,
    find_onset_tick,
    karr_pinched_diameter_sequence,
)
from scripts.l2_event.division_window_spec import (  # noqa: E402
    ProvisionalMarginOverrunError,
    check_inclusive_span_margin,
    m_ticks_for,
)
from scripts.l2_event.window_loader import load_event_window  # noqa: E402

REQUIRED_OBSERVABLES = (
    "substrates",
    "enzymes",
    "boundEnzymes",
    "pinchedDiameter",
    "ftsZRing_numEdgesOneStraight",
    "ftsZRing_numEdgesTwoStraight",
    "ftsZRing_numEdgesTwoBent",
    "ftsZRing_numResidualBent",
    "chromosome_segregated",
)

TRACE_ROOT = REPO_ROOT / "data" / "m1_sources" / "karr_native"
REQUIRED_N_SEEDS = 50

_SEED_DIR_RE = re.compile(r"_s(\d+)$")
_TRACE_NAME_RE = re.compile(r"^Cytokinesis_(\d+)ticks\.mat$")


class MTicksMetadataMismatchError(ValueError):
    """Raised when a trace's filename-encoded n_ticks and its own on-disk
    metadata.n_ticks disagree. This is always a fail-closed error, never a
    silent skip -- a filename and its own file's metadata disagreeing means
    the file is mislabeled or corrupted, not merely "a different cohort"."""


def discover_traces(*, m_ticks: int) -> dict[int, Path]:
    """Map seed -> trace path for every Cytokinesis event-window trace on
    disk whose FILENAME encodes exactly ``m_ticks`` (e.g.
    ``Cytokinesis_5000ticks.mat`` for ``m_ticks=5000``) -- traces
    preregistered under a DIFFERENT M_ticks (e.g. the preserved
    M_ticks=4000 cohort) are never included, so a survey can never mix
    two non-comparable cohorts into one max/lower-bound claim. Reads
    `TRACE_ROOT` at call time so tests can monkeypatch it to a temp
    directory without touching the real data tree."""
    found: dict[int, Path] = {}
    if not TRACE_ROOT.exists():
        return found
    expected_name = f"Cytokinesis_{int(m_ticks)}ticks.mat"
    for seed_dir in sorted(TRACE_ROOT.glob("per_process_traces_v2_event_s*")):
        match = _SEED_DIR_RE.search(seed_dir.name)
        if not match:
            continue
        seed = int(match.group(1))
        candidate = seed_dir / expected_name
        if candidate.is_file():
            found[seed] = candidate
    return found


def onset_span_for_trace(trace_path: Path, *, m_ticks: int | None = None) -> tuple[int, int, int]:
    """Returns ``(onset_tick, completion_tick, span)`` for one trace,
    computed purely from the trace's own `pinchedDiameter` before/after
    sequence (the same ratified onset/completion definition used
    throughout this task -- never from a labeled/derived field).

    If ``m_ticks`` is given:

    * the trace's own on-disk ``metadata.n_ticks`` must equal it exactly
      -- a filename that encodes ``m_ticks`` but whose own metadata
      disagrees raises :class:`MTicksMetadataMismatchError` (fail-closed;
      never silently trusted or silently skipped).
    * the trace's real inclusive onset-to-completion span
      (``completion_tick - onset_tick + 1``) must leave a strictly
      positive margin against ``m_ticks`` -- a zero-or-negative margin
      (``inclusive_span >= m_ticks``) raises
      :class:`~scripts.l2_event.division_window_spec.ProvisionalMarginOverrunError`
      (the provisional-margin gate; see that class's docstring). The
      MATLAB extractor's own capture-completeness invariant is left
      UNCHANGED by this check -- this is a stricter, additional,
      application-level gate evaluated here, at survey time."""
    window = load_event_window(trace_path, required_observables=REQUIRED_OBSERVABLES)
    if m_ticks is not None and window.n_ticks != int(m_ticks):
        raise MTicksMetadataMismatchError(
            f"{trace_path}: filename encodes M_ticks={m_ticks} but on-disk metadata.n_ticks="
            f"{window.n_ticks!r} -- refusing to survey a mislabeled/corrupted trace"
        )
    before, after = karr_pinched_diameter_sequence(window)
    onset_offset = find_onset_tick(before, after)
    completion_offset = find_completion_tick(before, after)
    if onset_offset is None or completion_offset is None:
        raise ValueError(f"{trace_path}: no detectable onset/completion transition in this trace")
    onset_abs = window.absolute_tick(onset_offset)
    completion_abs = window.absolute_tick(completion_offset)
    if m_ticks is not None:
        check_inclusive_span_margin(onset_abs, completion_abs, m_ticks)
    return onset_abs, completion_abs, completion_abs - onset_abs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--m-ticks",
        type=int,
        default=None,
        help=(
            "Cytokinesis M_ticks cohort to survey (filename-filtered, e.g. "
            "Cytokinesis_5000ticks.mat for --m-ticks 5000). Defaults to the "
            "currently-preregistered value in "
            "docs/phase_f/l2_event/division_window_spec.json. Traces "
            "preregistered under a DIFFERENT M_ticks are never included in the "
            "same survey -- pass this explicitly to survey a specific (e.g. "
            "preserved, non-authoritative) prior cohort instead."
        ),
    )
    args = parser.parse_args(argv)
    m_ticks = args.m_ticks if args.m_ticks is not None else m_ticks_for("Cytokinesis")

    traces = discover_traces(m_ticks=m_ticks)
    if not traces:
        print(f"No Cytokinesis_{m_ticks}ticks.mat event-window traces found on disk; nothing to survey.")
        return 1

    spans: dict[int, int] = {}
    for seed, path in sorted(traces.items()):
        try:
            onset_abs, completion_abs, span = onset_span_for_trace(path, m_ticks=m_ticks)
        except ProvisionalMarginOverrunError as exc:
            print(
                f"MARGIN OVERRUN (M_ticks={m_ticks}, seed={seed:03d}): {exc}\n"
                "Refusing to continue the survey past a zero-or-negative-margin observation -- "
                "see docs/phase_f/l2_event/division_window_spec.json's escalation_policy."
            )
            return 3
        spans[seed] = span
        print(
            f"seed={seed:03d} onset_tick={onset_abs} completion_tick={completion_abs} span={span}"
        )

    n_present = len(spans)
    max_span = max(spans.values())
    print(f"\nM_ticks={m_ticks}: {n_present}/{REQUIRED_N_SEEDS} required seeds present.")
    if n_present < REQUIRED_N_SEEDS:
        print(
            f"PARTIAL SURVEY ONLY (M_ticks={m_ticks}): max observed span over these {n_present} "
            f"seed(s) is {max_span} ticks. This is a LOWER BOUND, not the cohort-wide maximum -- "
            "refusing to authorize N=50 M_ticks/seed_window reconciliation from a "
            "partial sample. Generate the remaining seeds through the established "
            "resumable/atomic launcher (scripts/l2_event/launcher.py), one at a time, "
            "before drawing any cohort-wide conclusion."
        )
        return 2
    print(f"FULL SURVEY (M_ticks={m_ticks}): cohort-wide maximum onset-to-completion span is {max_span} ticks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
