"""Static/parse-only regression tests for
`scripts/matlab/extract_ftsz_pre_division_window_seeds.m` (the resumable
per-seed FtsZ division-anchored extraction driver used by
`scripts/l2_event/ftsz_pre_division_evidence.py`).

This file never invokes MATLAB/Octave against the real driver's normal
entry point (calling it with default arguments would fall straight into a
real `extract_per_process_traces_v2` -> `karr_bootstrap()` WholeCell
simulation bootstrap -- forbidden by the "no simulation/bootstrap/
extraction" constraint this branch operates under). It reuses the same two
independent static-check techniques already proven out in
`tests/scripts/test_extract_per_process_traces_v2_static.py` for the
sibling extractor:

* A lightweight, dependency-free block-keyword-balance heuristic (always
  runs, no MATLAB/Octave required).
* An OPTIONAL, environment-gated real parse-only probe using Octave
  (skipped cleanly if Octave/MATLAB is unavailable, e.g. in cloud CI).

Plus source-text assertions proving the three Opus 5 review fixes this
driver received are actually present in the file (not just described in a
commit message):

1. Per-seed failures are accumulated into `failed_seeds` and a single
   aggregating `error(...)` is thrown after the loop if any seed failed --
   replacing the earlier `catch ME; fprintf(...); end` swallow that let the
   function return normally (implicit exit 0) even when every seed failed.
2. `force_seeds` is an explicit third parameter that deletes and
   re-extracts only the named already-on-disk seeds -- the safe,
   opt-in overwrite path for seeds flagged invalid/duplicate by
   `ftsz_pre_division_evidence.py`'s audit.
3. `repo_root` is resolved via `mfilename('fullpath')` + `fileparts()`
   (identical to `extract_per_process_traces_v2.m`'s own resolution),
   never via `pwd`, so output/report paths cannot diverge depending on the
   caller's current working directory.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DRIVER_PATH = REPO_ROOT / "scripts" / "matlab" / "extract_ftsz_pre_division_window_seeds.m"

_BLOCK_OPENERS = re.compile(r"\b(function|if|for|while|switch|try)\b")
_STANDALONE_END_LINE_RE = re.compile(r"^\s*end\s*;?\s*$")


def _read_source() -> str:
    assert DRIVER_PATH.is_file(), f"missing {DRIVER_PATH}"
    return DRIVER_PATH.read_text(encoding="utf-8")


def _strip_comments_and_strings(source: str) -> str:
    """Best-effort removal of `%`-comments and single-quoted string
    literals (honoring MATLAB's `''` escaped-quote convention) so the
    block-keyword-balance heuristic below is never confused by the word
    "end"/"for"/"if" appearing inside a comment or a string literal -- see
    the identical helper (and its own regression history) in
    test_extract_per_process_traces_v2_static.py."""
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


def test_driver_file_exists_and_is_nonempty():
    source = _read_source()
    assert len(source) > 0


def test_block_keyword_balance():
    code = _strip_comments_and_strings(_read_source())
    openers = len(_BLOCK_OPENERS.findall(code))
    closers = sum(1 for line in code.splitlines() if _STANDALONE_END_LINE_RE.match(line))
    assert openers == closers, (
        f"block-keyword balance mismatch: {openers} opener(s) "
        f"(function/if/for/while/switch/try) vs {closers} standalone "
        "'end' statement(s) -- static evidence of an unbalanced/malformed "
        "block."
    )


def test_repo_root_resolved_from_mfilename_never_pwd():
    """Fix #3: repo_root must be resolved from this file's own location
    (three fileparts() calls up from scripts/matlab/<file>.m), identical to
    extract_per_process_traces_v2.m's own resolution -- never from pwd,
    which made output/report paths depend on the caller's cwd."""
    source = _read_source()
    assert "this_file = mfilename('fullpath');" in source
    assert "matlab_dir = fileparts(this_file);" in source
    assert "scripts_dir = fileparts(matlab_dir);" in source
    assert "repo_root = fileparts(scripts_dir);" in source

    # The old cwd-dependent resolution, and the ad hoc cd()-based WholeCell
    # path setup it required, must both be gone.
    assert "repo_root = pwd" not in source
    assert re.search(r"\bcd\(", source) is None, (
        "driver must never cd() -- extract_per_process_traces_v2 already "
        "sets up WholeCell runtime paths internally on every invocation"
    )


def test_failures_are_accumulated_and_raise_after_the_loop_not_swallowed():
    """Fix #1: per-seed failures must be accumulated into a list and must
    cause a single aggregating error(...) after the loop when non-empty --
    the earlier `catch ME; fprintf(...); end` swallow (which let the
    function return normally / exit 0 even when every seed failed) must be
    gone."""
    source = _read_source()

    assert "failed_seeds = {};" in source
    assert "failed_seeds{end + 1} = sprintf(" in source

    # The final aggregation block: a guard on failed_seeds followed by an
    # error(...) call that is never itself inside a try/catch (so it
    # propagates uncaught out of the function -- MATLAB's `-batch` mode
    # exits nonzero for an uncaught error).
    tail_match = re.search(
        r"if ~isempty\(failed_seeds\)\n(.*?)\nend\n?\Z",
        source,
        re.DOTALL,
    )
    assert tail_match is not None, "could not locate the trailing failed_seeds aggregation block"
    tail_body = tail_match.group(1)
    assert "error(" in tail_body
    assert "extraction_failed" in tail_body
    assert "numel(failed_seeds)" in tail_body

    # This aggregation block must be the LAST statement(s) in the file --
    # i.e. it must appear after the main per-seed for-loop, not inside it,
    # and it must not itself be wrapped in a try/catch (which would
    # swallow it and defeat the whole fix).
    assert source.rstrip().endswith("end")
    catch_around_error = re.search(
        r"try\s*\n(?:(?!\bend\b).)*?if ~isempty\(failed_seeds\)", source, re.DOTALL
    )
    assert catch_around_error is None, (
        "failed_seeds aggregation must not be nested inside a try block"
    )

    # The old swallow-and-continue pattern (bare fprintf with no
    # accumulation) must not remain as the ONLY per-seed failure handling.
    assert (
        "catch ME\n    fprintf('[ftsz-extract] seed %d FAILED: %s\\n', s, ME.message);\nend"
        not in source
    )


def test_force_seeds_parameter_deletes_and_reextracts_named_seeds_only():
    """Fix #2 (driver side): force_seeds is an explicit third parameter.
    An already-on-disk seed named in force_seeds must be deleted then
    re-extracted; every seed NOT named in force_seeds must keep the plain
    skip-if-exists behavior (never blanket-overwritten)."""
    source = _read_source()

    func_sig_match = re.search(
        r"function extract_ftsz_pre_division_window_seeds\(([^)]*)\)", source
    )
    assert func_sig_match is not None
    params = [p.strip() for p in func_sig_match.group(1).split(",")]
    assert params == ["seed_start", "seed_end", "force_seeds"]

    assert re.search(
        r"if nargin < 3 \|\| isempty\(force_seeds\)\s*\n\s*force_seeds = \[\];\s*\n\s*end",
        source,
    )
    assert "force_this = ismember(s, force_seeds);" in source
    assert "delete(out_path);" in source

    # The skip-if-exists branch must be conditioned on NOT force_this, so a
    # seed not named in force_seeds is never touched even if present.
    assert "if ~force_this" in source


def _assert_post_delete_existence_recheck_bails_out(source: str) -> None:
    """Final-fix static assertion: `delete(out_path)` must be immediately
    followed (still inside the `force_this` branch, before anything else
    runs) by an `if exist(out_path, 'file')` recheck whose body records the
    seed as failed and `continue`s -- it must NEVER fall through to
    mkdir/extract_per_process_traces_v2, and must never print a DONE line.
    `delete()` can silently fail to remove a file (permissions, another
    process holding it open, a read-only attribute, a network-share quirk)
    without MATLAB raising an error, so `exist()` is the only reliable
    post-condition check; skipping it would let a stale invalid/duplicate
    file masquerade as a successful re-extraction.

    Raises ``AssertionError`` (via a plain ``assert``) if the check is
    missing, malformed, or the recheck's failure path is not reached
    before the extraction call further down the function -- this is a
    shared helper so the exact same logic can be run against both the real
    driver source (must pass) and a deliberately mutated copy with the
    recheck stripped out (must fail -- see
    test_post_delete_existence_recheck_removal_is_caught_by_this_test
    below)."""
    delete_idx = source.index("delete(out_path);")
    tail = source[delete_idx + len("delete(out_path);") :]
    recheck_match = re.search(
        r"\A\s*\n\s*if exist\(out_path, 'file'\)\n(.*?)\n\s*end\n",
        tail,
        re.DOTALL,
    )
    assert recheck_match is not None, (
        "delete(out_path) must be immediately followed by an "
        "if exist(out_path, 'file') post-delete recheck block"
    )
    recheck_body = recheck_match.group(1)
    assert "failed_seeds{end + 1} = sprintf(" in recheck_body, (
        "post-delete recheck must record the seed as failed"
    )
    assert "continue;" in recheck_body, "post-delete recheck must bail out via continue"
    assert "extract_per_process_traces_v2(" not in recheck_body, (
        "post-delete recheck must never itself call the extractor"
    )
    assert "[ftsz-extract] seed %d DONE:" not in recheck_body, (
        "post-delete recheck must never print the DONE success line"
    )

    # The recheck's guard block must sit strictly BEFORE the try/extract
    # call further down the function -- i.e. a still-present file after
    # delete() can never reach the extraction call at all.
    try_idx = source.index("try\n        extract_per_process_traces_v2(")
    recheck_end_idx = delete_idx + len("delete(out_path);") + recheck_match.end()
    assert recheck_end_idx < try_idx, (
        "post-delete recheck must precede the extraction call in the function body"
    )


def test_post_delete_existence_recheck_present_and_bails_out_before_extraction():
    """Positive check: the real driver source has the post-delete
    existence recheck, and it is structurally wired to bail out before any
    extraction call."""
    _assert_post_delete_existence_recheck_bails_out(_read_source())


def test_post_delete_existence_recheck_removal_is_caught_by_this_test():
    """Adversarial proof (not just a description): take the real source,
    mechanically strip out exactly the post-delete recheck block (the
    smallest edit that reverts to the pre-fix behavior of trusting
    delete() unconditionally), and prove
    _assert_post_delete_existence_recheck_bails_out raises on the mutated
    copy. This demonstrates the regression this fix closes is actually
    detectable by this test suite, not merely asserted in prose."""
    source = _read_source()
    mutated, n_subs = re.subn(
        r"(delete\(out_path\);\n)\s*if exist\(out_path, 'file'\)\n.*?\n\s*end\n",
        r"\1",
        source,
        count=1,
        flags=re.DOTALL,
    )
    assert n_subs == 1, (
        "mutation did not remove the post-delete recheck block -- test setup is broken"
    )
    assert mutated != source

    with pytest.raises(AssertionError):
        _assert_post_delete_existence_recheck_bails_out(mutated)


def _octave_executable() -> str | None:
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
    Octave is available. Same `1;` script-shim technique as the sibling
    extractor's static test file: makes every `function ... end` in the
    file a local function within a script, so Octave's `source()` parses
    the whole file (raising a genuine syntax error for a malformed one)
    without ever calling `extract_ftsz_pre_division_window_seeds` or any
    helper it references."""
    octave = _octave_executable()
    assert octave is not None  # narrowed by skipif above

    source = _read_source()
    probe_path = tmp_path / "extract_ftsz_pre_division_window_seeds_parse_probe.m"
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
        "octave failed to parse extract_ftsz_pre_division_window_seeds.m "
        f"(exit {result.returncode}); stderr:\n{result.stderr}"
    )
    assert sentinel in result.stdout, (
        f"expected parse-success sentinel missing from octave stdout (stdout: {result.stdout!r})"
    )
    # extract_per_process_traces_v2 (reachable from this file's per-seed
    # call) must never actually execute -- its distinctive bootstrap log
    # banner must never appear.
    assert "karr_bootstrap" not in result.stdout
    assert "karr_bootstrap" not in result.stderr
