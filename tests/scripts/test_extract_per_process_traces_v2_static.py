"""Static/parse-only regression tests for
`scripts/matlab/extract_per_process_traces_v2.m` (M4 fixed/anchor
event-window extractor).

This file NEVER invokes MATLAB, Octave, or any simulation/bootstrap code.
That is a deliberate choice, not an oversight: a throwaway probe during
this task's development showed that Octave's `source()` (and simply
running the `.m` file) auto-*calls* a file that consists of nothing but a
single top-level function definition -- there is no safe "parse only, do
not execute" invocation path available in this environment. Since
`extract_per_process_traces_v2()` called with zero arguments immediately
falls into `karr_bootstrap()` (a real WholeCell simulation bootstrap),
using Octave here would violate the "no simulation/bootstrap/extraction"
constraint. The regression this guards against -- the Opus 5-identified
MATLAB syntax error from a chained dynamic-field-access expression,
`target_proc.(anchor_opts.signal_property).(anchor_opts.signal_field)`,
which MATLAB/Octave cannot parse as a single expression -- is instead
guarded with a plain-text static check: a regex that would catch any
reintroduction of that exact chained-access pattern, plus a lightweight
block-keyword balance check as a broader static parse sanity net.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTRACTOR_PATH = REPO_ROOT / "scripts" / "matlab" / "extract_per_process_traces_v2.m"

# The exact defect class Opus 5 flagged: two consecutive dynamic-field
# accesses chained directly onto one expression, e.g. `a.(b).(c)` or
# `obj.(x.y).(x.z)`. MATLAB/Octave's parser rejects this as a single
# expression -- it must be split into validated temporary variables
# (see `merge_event_observables`'s `container = mod.(container_name);`
# followed by a *separate* `container.pinchedDiameter` / `container.(field_name)`
# dereference).
_CHAINED_DYNAMIC_ACCESS_RE = re.compile(r"\.\([^()]*\)\.\(")

_BLOCK_OPENERS = re.compile(r"\b(function|if|for|while|switch|try)\b")
_STANDALONE_END_LINE_RE = re.compile(r"^\s*end\s*;?\s*$")


def _read_source() -> str:
    assert EXTRACTOR_PATH.is_file(), f"missing {EXTRACTOR_PATH}"
    return EXTRACTOR_PATH.read_text(encoding="utf-8")


def _strip_comments_and_strings(source: str) -> str:
    """Best-effort removal of `%`-comments and single-quoted string
    literals so keyword/pattern counts below aren't confused by the word
    "end" or a literal ".()." appearing inside a comment or a string
    (e.g. this file's own docstring-style header comments)."""
    out_lines = []
    for line in source.splitlines():
        # Drop a trailing %-comment (MATLAB has no block comments in this
        # file; %{ %} pairs are not used here). This is intentionally
        # simple -- it does not need to handle a % inside a string
        # literal correctly for this file, which contains none.
        code_part = line.split("%", 1)[0]
        # Collapse single-quoted string literals (including MATLAB's
        # '' escaped-quote convention) to a placeholder so their content
        # can never match the chained-access or block-keyword regexes.
        code_part = re.sub(r"'([^']|'')*'", "''", code_part)
        out_lines.append(code_part)
    return "\n".join(out_lines)


def test_extractor_file_exists_and_is_nonempty():
    source = _read_source()
    assert len(source) > 0


def test_no_chained_dynamic_field_access_regression():
    """Regression guard for the Opus 5-identified MATLAB parse defect:
    `target_proc.(anchor_opts.signal_property).(anchor_opts.signal_field)`
    (two chained dynamic-field accesses in one expression) must never
    reappear. The fix (`merge_event_observables`) always dereferences a
    validated temporary variable first (`container = mod.(container_name);`)
    and only then does a second, separate dereference."""
    code = _strip_comments_and_strings(_read_source())
    matches = _CHAINED_DYNAMIC_ACCESS_RE.findall(code)
    assert not matches, (
        f"found {len(matches)} chained dynamic-field-access expression(s) "
        "(pattern `).(...).(` ) -- MATLAB/Octave cannot parse this as a "
        "single expression; replace with a validated temporary variable "
        "and a separate dereference (see merge_event_observables)."
    )


def test_block_keyword_balance():
    """Lightweight static parse sanity check: every block-opening keyword
    (`function`/`if`/`for`/`while`/`switch`/`try`) must be matched by a
    standalone `end` statement (MATLAB's `case`/`otherwise`/`catch`/
    `else`/`elseif` do not open a new `end`-terminated block of their
    own; and an `end` used as an array/cell index shorthand, e.g.
    `tokens{end + 1}` or `wid(k:end)`, is never a block closer -- it is
    only counted here when it is the sole token on its line). This does
    not replace a real MATLAB parser, but it is a real static check that
    would fail loudly if an edit dropped or added an unbalanced block --
    the same class of defect underlying the original syntax error."""
    code = _strip_comments_and_strings(_read_source())
    openers = len(_BLOCK_OPENERS.findall(code))
    closers = sum(1 for line in code.splitlines() if _STANDALONE_END_LINE_RE.match(line))
    assert openers == closers, (
        f"block-keyword balance mismatch: {openers} opener(s) "
        f"(function/if/for/while/switch/try) vs {closers} standalone "
        "'end' statement(s) -- static evidence of an unbalanced/malformed "
        "block."
    )


def test_merge_event_observables_uses_two_step_dereference():
    """Positive-form check complementing the chained-access regex above:
    the fixed `merge_event_observables` must dereference the signal
    container into a named temporary (`container = mod.(container_name);`)
    before reading any field off of it."""
    source = _read_source()
    assert "container = mod.(container_name);" in source
    # And the two real per-observable dereferences must be against that
    # temporary, never re-chained through `mod.(...)` a second time.
    assert "container.pinchedDiameter" in source
    assert "container.(field_name)" in source
