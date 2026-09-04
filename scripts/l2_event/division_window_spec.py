"""Single source of truth loader for division-window (event-anchor) capture
sizes, replacing the scattered ``cyt_n_ticks = 4000`` / ``AUTHORITATIVE_N_TICKS
= 4000`` / ``CYTOKINESIS_N_TICKS = 4000`` literals that used to be duplicated
independently across ``scripts/l2_event/prepare_cytokinesis_cohort.py``,
``scripts/l2_event/validate_dual_division_canary.py``,
``scripts/matlab/extract_dual_division_window.m`` and
``scripts/matlab/extract_dual_division_window_seeds.m``.

The canonical values live in ``docs/phase_f/l2_event/division_window_spec.json``
(a plain JSON file so MATLAB can read it too, via ``jsondecode(fileread(...))``
in ``scripts/matlab/division_window_spec.m``). This module is the ONLY
Python entry point that should ever read that file; every other Python
consumer imports :data:`CYTOKINESIS_M_TICKS` / :data:`FTSZ_M_TICKS` (or calls
:func:`load_spec` for the full record, e.g. for provenance/evidence fields)
from here rather than re-parsing the JSON or hardcoding a literal.

Preregistration discipline (2026-09-04 Cytokinesis window fix): this module
deliberately has NO fallback default and NO silent tuning path. If the spec
file is missing, malformed, or missing a required process key, every loader
function raises -- there is no "assume 4000" or "assume the old value"
degradation, because a silently-wrong default here would defeat the entire
point of centralizing the value in one preregistered place.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SPEC_PATH = REPO_ROOT / "docs" / "phase_f" / "l2_event" / "division_window_spec.json"


class DivisionWindowSpecError(Exception):
    """Raised when the shared division-window spec is missing, malformed,
    or missing a required process entry. Never silently defaulted."""


def load_spec(spec_path: Path = SPEC_PATH) -> dict[str, Any]:
    """Load and return the full parsed spec document. Raises
    :class:`DivisionWindowSpecError` (never returns a partial/best-effort
    document) if the file cannot be read or parsed as JSON."""
    try:
        raw = spec_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DivisionWindowSpecError(f"cannot read division-window spec at {spec_path}: {exc}") from exc
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DivisionWindowSpecError(f"division-window spec at {spec_path} is not valid JSON: {exc}") from exc
    if not isinstance(doc, dict) or "processes" not in doc:
        raise DivisionWindowSpecError(
            f"division-window spec at {spec_path} is missing the required top-level 'processes' key"
        )
    return doc


def process_spec(process: str, *, spec_path: Path = SPEC_PATH) -> dict[str, Any]:
    """Return the parsed spec entry for one process name (e.g.
    'Cytokinesis'). Raises :class:`DivisionWindowSpecError` if that process
    has no entry -- never falls back to a guessed/default value."""
    doc = load_spec(spec_path)
    processes = doc["processes"]
    if process not in processes:
        raise DivisionWindowSpecError(
            f"division-window spec at {spec_path} has no entry for process {process!r}; "
            f"known processes: {sorted(processes)}"
        )
    return processes[process]


def m_ticks_for(process: str, *, spec_path: Path = SPEC_PATH) -> int:
    """Return the preregistered M_ticks (event-window capture length) for
    one process, read fresh from the shared spec file every call (no
    process-wide caching) so a test can point ``spec_path`` at a temp file
    without any import-order surprises."""
    entry = process_spec(process, spec_path=spec_path)
    if "m_ticks" not in entry:
        raise DivisionWindowSpecError(f"division-window spec entry for {process!r} has no 'm_ticks' key")
    return int(entry["m_ticks"])


def tick_range_from_division_for(process: str, *, spec_path: Path = SPEC_PATH) -> tuple[int, int]:
    entry = process_spec(process, spec_path=spec_path)
    if "tick_range_from_division" not in entry:
        raise DivisionWindowSpecError(
            f"division-window spec entry for {process!r} has no 'tick_range_from_division' key"
        )
    lo, hi = entry["tick_range_from_division"]
    return int(lo), int(hi)


class ProvisionalMarginOverrunError(DivisionWindowSpecError):
    """Raised when an observed inclusive onset-to-completion span leaves
    ZERO OR NEGATIVE margin against a preregistered ``m_ticks`` (i.e.
    ``inclusive_span >= m_ticks``).

    2026-09-04 (Opus final review, pre-bulk mechanical fix): the MATLAB
    extractor's own capture invariant (``capture_dual_anchor_windows``'s
    ``onset_tick < tick_start_a`` guard / the equivalent single-process
    ``capture_anchor_window`` check) only requires
    ``inclusive_span <= m_ticks`` -- a trace can be captured successfully
    with ZERO margin, exactly at ``inclusive_span == m_ticks``. That
    capture-time invariant is intentionally left UNCHANGED by this
    function (it is the complete-event condition, not this gate).

    This is a SEPARATE, additional, application-level check for whether
    the CURRENT (per ``m_ticks_status: PROVISIONAL`` in
    ``division_window_spec.json``) preregistered ``m_ticks`` remains
    defensible: a zero-margin observation must trigger the SAME
    escalation-policy response (a new, separate preregistration commit,
    never same-commit tuning) as a true overrun
    (``inclusive_span > m_ticks``) would. The whole point of the
    ``escalation_policy``'s explicit margin (924 ticks / 22.7% over the
    n=1 evidence this M was set from) is that a single seed consuming
    that ENTIRE margin down to zero is itself evidence the margin was
    not generous enough, and must never be silently accepted as "just
    barely fits."
    """


def check_inclusive_span_margin(onset_tick: int, completion_tick: int, m_ticks: int) -> None:
    """Raise :class:`ProvisionalMarginOverrunError` if the inclusive
    onset-to-completion span (``completion_tick - onset_tick + 1``)
    leaves zero or negative margin against ``m_ticks`` (i.e.
    ``inclusive_span >= m_ticks``). Never silently accepts a zero-margin
    observation -- see :class:`ProvisionalMarginOverrunError` for the
    full rationale. Callers: ``scripts/l2_event/survey_cytokinesis_
    onset_span.py`` (per-seed survey) and
    ``scripts/l2_event/validate_dual_division_canary.py`` (per-seed
    canary validation) both call this identically so the provisional-
    margin gate is enforced mechanically in both places, not just
    documented in prose.
    """
    inclusive_span = int(completion_tick) - int(onset_tick) + 1
    if inclusive_span >= int(m_ticks):
        raise ProvisionalMarginOverrunError(
            f"inclusive onset-to-completion span={inclusive_span} (onset_tick={onset_tick}, "
            f"completion_tick={completion_tick}) leaves ZERO OR NEGATIVE margin against "
            f"m_ticks={m_ticks} (span >= m_ticks). This seed's real division timing has consumed "
            "the entire provisional margin division_window_spec.json's escalation_policy was sized "
            "against. Per that policy: this requires a NEW, SEPARATE preregistration commit "
            "(new_m_ticks = ceil(observed_span_inclusive * 1.227 / 1000) * 1000), never same-commit "
            "tuning -- never silently accepted as 'just barely fits.'"
        )


# Module-level constants for the two callers this task touches. These are
# read ONCE at import time (matching the historical `AUTHORITATIVE_N_TICKS
# = 4000` / `CYTOKINESIS_N_TICKS = 4000` module-constant convention those
# call sites already used) -- callers who need spec changes to be visible
# without a process restart (e.g. tests exercising a monkeypatched spec
# file) should call `m_ticks_for(...)` directly instead of importing these
# constants.
CYTOKINESIS_M_TICKS: int = m_ticks_for("Cytokinesis")
FTSZ_M_TICKS: int = m_ticks_for("FtsZPolymerization")
