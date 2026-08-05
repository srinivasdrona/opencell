"""Read-only survey of the Cytokinesis onset-to-completion span across
however many seed event-window traces currently exist on disk under
``data/m1_sources/karr_native/per_process_traces_v2_event_s*/Cytokinesis_*ticks.mat``.

Purpose: this is the tool the catalog owner should run, once ALL 50
seeds of the required event-window ensemble exist, to determine the
COHORT-WIDE MAXIMUM onset-to-completion span before authorizing an
N=50 sweep -- see ``docs/phase_f/l2_event/event_registry.yaml``'s
Cytokinesis notes and ``docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml``'s
Cytokinesis ``M_ticks``/``seed_window`` fields (reconciled 2026-08-05 to
the seed-0 LOWER BOUND, `blocked_on` this survey for the real
cohort-wide maximum).

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


def discover_traces() -> dict[int, Path]:
    """Map seed -> trace path for every Cytokinesis event-window trace
    that currently exists on disk (any n_ticks capture size). Reads
    `TRACE_ROOT` at call time so tests can monkeypatch it to a temp
    directory without touching the real data tree."""
    found: dict[int, Path] = {}
    if not TRACE_ROOT.exists():
        return found
    for seed_dir in sorted(TRACE_ROOT.glob("per_process_traces_v2_event_s*")):
        match = _SEED_DIR_RE.search(seed_dir.name)
        if not match:
            continue
        seed = int(match.group(1))
        for candidate in sorted(seed_dir.glob("Cytokinesis_*ticks.mat")):
            if _TRACE_NAME_RE.match(candidate.name):
                found[seed] = candidate
    return found


def onset_span_for_trace(trace_path: Path) -> tuple[int, int, int]:
    """Returns ``(onset_tick, completion_tick, span)`` for one trace,
    computed purely from the trace's own `pinchedDiameter` before/after
    sequence (the same ratified onset/completion definition used
    throughout this task -- never from a labeled/derived field)."""
    window = load_event_window(trace_path, required_observables=REQUIRED_OBSERVABLES)
    before, after = karr_pinched_diameter_sequence(window)
    onset_offset = find_onset_tick(before, after)
    completion_offset = find_completion_tick(before, after)
    if onset_offset is None or completion_offset is None:
        raise ValueError(f"{trace_path}: no detectable onset/completion transition in this trace")
    onset_abs = window.absolute_tick(onset_offset)
    completion_abs = window.absolute_tick(completion_offset)
    return onset_abs, completion_abs, completion_abs - onset_abs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    traces = discover_traces()
    if not traces:
        print("No Cytokinesis event-window traces found on disk; nothing to survey.")
        return 1

    spans: dict[int, int] = {}
    for seed, path in sorted(traces.items()):
        onset_abs, completion_abs, span = onset_span_for_trace(path)
        spans[seed] = span
        print(f"seed={seed:03d} onset_tick={onset_abs} completion_tick={completion_abs} span={span}")

    n_present = len(spans)
    max_span = max(spans.values())
    print(f"\n{n_present}/{REQUIRED_N_SEEDS} required seeds present.")
    if n_present < REQUIRED_N_SEEDS:
        print(
            f"PARTIAL SURVEY ONLY: max observed span over these {n_present} seed(s) is "
            f"{max_span} ticks. This is a LOWER BOUND, not the cohort-wide maximum -- "
            "refusing to authorize N=50 M_ticks/seed_window reconciliation from a "
            "partial sample. Generate the remaining seeds through the established "
            "resumable/atomic launcher (scripts/l2_event/launcher.py), one at a time, "
            "before drawing any cohort-wide conclusion."
        )
        return 2
    print(f"FULL SURVEY: cohort-wide maximum onset-to-completion span is {max_span} ticks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
