"""Static/parse-only regression tests for
`scripts/matlab/probe_cytokinesis_randstream_state.m` (Stage-1 randStream
state probe for the L2.1 Cytokinesis active-window tick-228 residual
divergence; see STATUS_L21_CYTOKINESIS_ACTIVE_FIX.md).

Never invokes MATLAB/Octave against the real entry point (calling
`probe_cytokinesis_randstream_state()` falls straight into
`karr_bootstrap()`, a real WholeCell simulation bootstrap that free-runs
tens of thousands of ticks -- forbidden in a fast test suite and requires
a licensed MATLAB host). Uses the same block-keyword-balance heuristic as
`test_extract_per_process_traces_v2_static.py` (duplicated rather than
imported, matching this repo's convention of independent static-check
files per MATLAB script).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE_PATH = REPO_ROOT / "scripts" / "matlab" / "probe_cytokinesis_randstream_state.m"
EXTRACTOR_PATH = REPO_ROOT / "scripts" / "matlab" / "extract_per_process_traces_v2.m"

_BLOCK_OPENERS = re.compile(r"\b(function|if|for|while|switch|try)\b")
_STANDALONE_END_LINE_RE = re.compile(r"^\s*end\s*;?\s*$")

_DUPLICATED_FROM_SHA256 = "5f0f3654dc279ab78e938b5332bfb78bd60ff25e5647924acbe5a08f59644444"


def _read_source() -> str:
    assert PROBE_PATH.is_file(), f"missing {PROBE_PATH}"
    return PROBE_PATH.read_text(encoding="utf-8")


def _strip_comments_and_strings(source: str) -> str:
    """Best-effort removal of `%`-comments and single-quoted string
    literals so keyword/pattern counts aren't confused by "end"/"for"/etc.
    appearing inside a comment or string literal. See
    test_extract_per_process_traces_v2_static.py for the full rationale;
    duplicated verbatim here rather than imported (independent static
    checks per MATLAB script is this repo's established convention)."""
    out_lines = []
    for line in source.splitlines():
        result = []
        i = 0
        n = len(line)
        while i < n:
            ch = line[i]
            if ch == "'":
                j = i + 1
                while j < n:
                    if line[j] == "'":
                        if j + 1 < n and line[j + 1] == "'":
                            j += 2
                            continue
                        j += 1
                        break
                    j += 1
                result.append("''")
                i = j
                continue
            if ch == "%":
                break
            result.append(ch)
            i += 1
        out_lines.append("".join(result))
    return "\n".join(out_lines)


def test_probe_file_exists_and_is_nonempty() -> None:
    source = _read_source()
    assert len(source) > 0


def test_block_keyword_balance() -> None:
    """Lightweight static parse sanity check: every block-opening keyword
    must be matched by a standalone `end` statement."""
    code = _strip_comments_and_strings(_read_source())
    openers = len(_BLOCK_OPENERS.findall(code))
    closers = sum(1 for line in code.splitlines() if _STANDALONE_END_LINE_RE.match(line))
    assert openers == closers, (
        f"block-keyword balance mismatch: {openers} opener(s) vs "
        f"{closers} standalone 'end' statement(s)"
    )


def test_no_hardcoded_answer_shortcut() -> None:
    """Anti-cheat: this probe must derive Karr's randStream state purely
    from running the real simulation -- it must never special-case a
    specific tick number's expected OC outcome, read any OC oracle file,
    or hardcode a "correct" answer to make the comparison trivially pass.
    Checked against the comment/string-stripped source so citations in
    documentation (e.g. naming the accepted trace file for provenance)
    are not mistaken for a forbidden runtime shortcut."""
    code = _strip_comments_and_strings(_read_source())
    forbidden_patterns = (
        "oc_after", "oc_val", "karr_val==",
        "_100ticks", "_4000ticks.mat",
        "numEdgesOneStraight == 9", "numEdgesOneStraight == 1",
    )
    for pattern in forbidden_patterns:
        assert pattern not in code, f"anti-cheat: found forbidden marker {pattern!r}"


def test_tick_start_is_required_not_defaulted() -> None:
    """tick_start must be a required argument (no silent default) -- this
    probe must never guess/re-derive the accepted trace's window start;
    it is always supplied explicitly by the caller from the trace's own
    verified metadata."""
    source = _read_source()
    assert "error('probe_cytokinesis_randstream_state:missing_tick_start'" in source


def test_records_duplication_provenance_hash() -> None:
    """The probe duplicates evolve_state_with_tap (and small helpers) from
    extract_per_process_traces_v2.m verbatim (MATLAB script-local
    functions cannot be called cross-file) and must record that source
    file's SHA256 at duplication time, both in a comment and in the
    written JSON's metadata, so future drift between the two copies is
    mechanically detectable."""
    source = _read_source()
    assert _DUPLICATED_FROM_SHA256 in source
    assert source.count(_DUPLICATED_FROM_SHA256) >= 2  # doc comment + literal used in output


def test_duplicated_source_hash_is_current() -> None:
    """Fail loudly (not silently) if extract_per_process_traces_v2.m has
    changed since this probe's evolve_state_with_tap logic was duplicated
    -- the probe's scheduler/allocation semantics must then be manually
    re-synced and the recorded hash updated."""
    import hashlib

    assert EXTRACTOR_PATH.is_file(), f"missing {EXTRACTOR_PATH}"
    actual = hashlib.sha256(EXTRACTOR_PATH.read_bytes()).hexdigest()
    assert actual == _DUPLICATED_FROM_SHA256, (
        f"scripts/matlab/extract_per_process_traces_v2.m changed since "
        f"probe_cytokinesis_randstream_state.m's evolve_state_with_tap was "
        f"duplicated from it (expected sha256={_DUPLICATED_FROM_SHA256}, "
        f"got {actual}) -- re-sync the duplicated scheduler logic and "
        "update the recorded hash in both files."
    )


def test_no_source_overlay_in_stage_1() -> None:
    """Stage 1 must not touch any WCM source file or path overlay -- it
    reads this.randStream.state as a plain public-getter property. Stage
    2 (per-phase instrumentation, if ever needed) is a separate, explicitly
    hash-bound overlay under tmp/wcm_source_overlay/, never this file.
    Checked against the comment-stripped source so the doc paragraph
    describing the (not-yet-built) Stage 2 plan is not mistaken for an
    actual Stage-1 overlay invocation."""
    code = _strip_comments_and_strings(_read_source())
    assert "wcm_source_overlay" not in code
    assert "addpath(genpath" not in code


def _octave_executable() -> str | None:
    """Locate an Octave CLI binary on PATH, or return None if unavailable.
    Mirrors test_extract_per_process_traces_v2_static.py's helper exactly
    (duplicated, not imported, per this repo's per-script static-test
    convention)."""
    for name in ("octave-cli", "octave"):
        path = shutil.which(name)
        if path:
            return path
    return None


@pytest.mark.skipif(
    _octave_executable() is None,
    reason="octave-cli not available on PATH; parse-only probe skipped",
)
def test_real_parse_only_probe_via_octave(tmp_path: Path):
    """Real (not heuristic) parse-only regression check, run only when
    Octave is available. Same `1;`-prefix technique as
    test_extract_per_process_traces_v2_static.py's probe: makes every
    `function ... end` in the file a local function inside a script, so
    Octave's `source()` parses the whole file (raising on any real syntax
    error) without ever calling `karr_bootstrap()` or running any
    simulation/extraction side effect."""
    octave = _octave_executable()
    assert octave is not None  # narrowed by skipif above

    source = _read_source()
    probe_path = tmp_path / "probe_cytokinesis_randstream_state_parse_probe.m"
    probe_path.write_text("1;\n" + source, encoding="utf-8")

    sentinel = "PARSE_OK_NO_EXEC"
    result = subprocess.run(
        [
            octave,
            "--no-gui",
            "--eval",
            f"source('{probe_path.as_posix()}'); disp('{sentinel}');",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, (
        "octave failed to parse probe_cytokinesis_randstream_state.m "
        f"(exit {result.returncode}); stderr:\n{result.stderr}"
    )
    assert sentinel in result.stdout, (
        "expected parse-success sentinel missing from octave stdout "
        f"(stdout: {result.stdout!r})"
    )
    assert "karr_bootstrap" not in result.stdout
