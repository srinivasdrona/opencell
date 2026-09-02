"""Static/parse-only regression tests for
`scripts/matlab/extract_per_process_traces_v2.m` (M4 fixed/anchor
event-window extractor).

This file never invokes MATLAB, Octave, or any simulation/bootstrap code
against the real extractor's normal entry point (calling
`extract_per_process_traces_v2()` with zero/default arguments falls
straight into `karr_bootstrap()`, a real WholeCell simulation bootstrap --
forbidden by the "no simulation/bootstrap/extraction" constraint this
branch operates under).

Two independent static checks are used:

* A lightweight, dependency-free block-keyword-balance heuristic (always
  runs, no MATLAB/Octave required).
* An OPTIONAL, environment-gated real parse-only probe using Octave
  (skipped cleanly if Octave/MATLAB is unavailable, e.g. in cloud CI).
  The technique -- prepending a `1;` statement before the real source so
  every `function ... end` in it becomes a *local function* inside a
  script -- was verified empirically in a disposable scratch directory
  (never against this repository's real file) before being relied on
  here: Octave's `source()` parses the whole file, including every nested
  local function body (raising a genuine syntax error for a malformed
  one), WITHOUT ever calling any of those functions. This was confirmed
  both for a single-function file and for a multi-function file where one
  local function calls another -- the same shape as this extractor
  (`extract_per_process_traces_v2` calling several helper functions).

Earlier revisions of this file additionally asserted that MATLAB/Octave
cannot parse chained dynamic-field access (e.g. `a.(b).(c)`) as a single
expression. That premise was incorrect -- chained dynamic-field access IS
valid MATLAB/Octave syntax -- and the regression test built on it has been
removed; see docs/phase_f/l2_event/EVENT_WINDOW_EXTRACTOR_CONTRACT.md's
"Static parse checking" section for the corrected account.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTRACTOR_PATH = REPO_ROOT / "scripts" / "matlab" / "extract_per_process_traces_v2.m"

_BLOCK_OPENERS = re.compile(r"\b(function|if|for|while|switch|try)\b")
_STANDALONE_END_LINE_RE = re.compile(r"^\s*end\s*;?\s*$")


def _read_source() -> str:
    assert EXTRACTOR_PATH.is_file(), f"missing {EXTRACTOR_PATH}"
    return EXTRACTOR_PATH.read_text(encoding="utf-8")


def _strip_comments_and_strings(source: str) -> str:
    """Best-effort removal of `%`-comments and single-quoted string
    literals so keyword/pattern counts below aren't confused by the word
    "end" (or a keyword like "for"/"if") appearing inside a comment or a
    string literal.

    Scans each line character-by-character tracking whether a `'` has
    opened a string literal (honoring MATLAB's `''` escaped-quote
    convention): a `%` encountered *inside* an open string is just a
    character, never a comment start. A naive `line.split('%', 1)[0]`
    (this function's earlier, incorrect implementation) truncated any
    line containing a single-quoted string with a `%d`/`%s`-style format
    specifier at the first such `%`, silently discarding the rest of the
    line -- including any real keyword/`end` token after it. That defect
    was undetectable with this file's OLD content (no format-specifier
    string on the same physical line as a bare keyword like "for") but
    surfaced as a false block-imbalance failure once Turn 3's
    `error('...', 'extraction failed for %d of %d ...', ...)` message put
    the word "for" before a `%d` on one line -- proving the truncation bug
    (not the real extractor source) was the actual defect.
    """
    out_lines = []
    for line in source.splitlines():
        result = []
        i = 0
        n = len(line)
        while i < n:
            ch = line[i]
            if ch == "'":
                # Consume the whole single-quoted string literal (honoring
                # the '' escaped-quote convention) and replace it with a
                # placeholder -- its content (any %, for/if/end, etc.)
                # can never leak into the keyword/pattern counts below.
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
                # A real comment start (only reached when NOT inside an
                # open string, per the branch above) -- the rest of the
                # physical line is dropped.
                break
            result.append(ch)
            i += 1
        out_lines.append("".join(result))
    return "\n".join(out_lines)


def test_extractor_file_exists_and_is_nonempty():
    source = _read_source()
    assert len(source) > 0


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
    """Positive-form static check: `merge_event_observables` dereferences
    the signal container into a named temporary
    (`container = mod.(container_name);`) before reading any field off of
    it. This is a readability/validation choice (it lets the container be
    checked/validated once by name before any field access), not a parse
    requirement -- chained dynamic-field access such as
    `mod.(container_name).(field_name)` is valid MATLAB/Octave syntax."""
    source = _read_source()
    assert "container = mod.(container_name);" in source
    # And the two real per-observable dereferences must be against that
    # temporary, never re-chained through `mod.(...)` a second time.
    assert "container.pinchedDiameter" in source
    assert "container.(field_name)" in source


def test_chromosome_object_excluded_only_for_diameter_decrease_anchor():
    """Performance/sufficiency patch static proof: the full sparse
    `chromosome` snapshot property must be excluded ONLY for
    `window_contract='anchor'` + `signal_kind='diameter_decrease'`
    (Cytokinesis) -- never for a fixed window, and never for a generic
    `signal_kind='boolean_transition'` anchor (requirement: "do not remove
    chromosome snapshots for other processes/profiles")."""
    source = _read_source()

    # The exclusion helper exists and is invoked exactly once, immediately
    # after the generic pick_snapshot_properties() call -- never inlined
    # elsewhere, so there is exactly one place that can ever drop
    # 'chromosome' from the captured set.
    assert source.count("function props = exclude_chromosome_object_for_diameter_anchor(") == 1
    assert (
        "snapshot_props = exclude_chromosome_object_for_diameter_anchor(snapshot_props, window_contract, anchor_opts);"
        in source
    )

    # Extract the helper's body and prove its guard checks BOTH
    # window_contract=='anchor' AND signal_kind=='diameter_decrease' (a
    # conjunction, not just one of the two) before ever calling setdiff to
    # remove 'chromosome'.
    body_match = re.search(
        r"function props = exclude_chromosome_object_for_diameter_anchor\(.*?\n(.*?)\nend\n",
        source,
        re.DOTALL,
    )
    assert body_match is not None, "could not locate exclude_chromosome_object_for_diameter_anchor's body"
    body = body_match.group(1)
    assert "strcmp(window_contract, 'anchor')" in body
    assert "strcmp(anchor_opts.signal_kind, 'diameter_decrease')" in body
    assert "&&" in body
    assert "setdiff(props, {'chromosome'})" in body

    # merge_event_observables' 'diameter_decrease' case must flatten the
    # replacement chromosome_segregated scalar via the same validated-
    # temporary two-step dereference pattern as pinchedDiameter/FtsZRing.
    assert "chrom = mod.chromosome;" in source
    assert "snapshot.chromosome_segregated = logical(chrom.segregated);" in source

    # The 'boolean_transition' case (generic EVENT_CLASS processes) must
    # never reference the chromosome-exclusion/chromosome_segregated
    # machinery at all -- it is Cytokinesis-diameter-decrease-specific.
    boolean_case_match = re.search(
        r"case 'boolean_transition'\n(.*?)\n\s*otherwise\n",
        source,
        re.DOTALL,
    )
    assert boolean_case_match is not None, "could not locate the 'boolean_transition' case body"
    boolean_case_body = boolean_case_match.group(1)
    assert "chromosome" not in boolean_case_body


def test_genuine_mnrnd_provider_metadata_written_for_fixed_and_anchor_not_legacy():
    """Static proof of the provider-migration contract: the extractor
    must persist the genuine-provider metadata for BOTH 'fixed' and
    'anchor' windows, and must still leave the '' (no window_contract)
    legacy path untouched."""
    source = _read_source()

    assert source.count("metadata.mnrnd_provider_kind = mnrnd_provider.kind;") == 1
    assert source.count("metadata.mnrnd_provider_matlab_release = mnrnd_provider.matlab_release;") == 1
    assert source.count("metadata.mnrnd_provider_toolbox_version = mnrnd_provider.toolbox_version;") == 1
    assert (
        source.count(
            "metadata.mnrnd_provider_path_relative_to_matlabroot = mnrnd_provider.provider_path_relative_to_matlabroot;"
        )
        == 1
    )
    assert source.count("metadata.mnrnd_provider_sha256 = mnrnd_provider.sha256_lf_normalized;") == 1
    assert source.count(
        "metadata.statistics_rng_provider_identity_json = mnrnd_provider.identity_json;"
    ) == 1
    assert "mnrnd_shim" not in source

    # The single assignment site must be guarded by
    # strcmp(window_contract, 'fixed') || strcmp(window_contract, 'anchor')
    # -- not nested separately inside each branch (which could drift out
    # of sync) and not unconditional (which would corrupt the legacy ''
    # metadata shape).
    guard_match = re.search(
        r"if strcmp\(window_contract, 'fixed'\) \|\| strcmp\(window_contract, 'anchor'\)\n"
        r"(.*?)\n\s*end\n",
        source,
        re.DOTALL,
    )
    assert guard_match is not None, "could not locate the genuine-provider metadata guard block"
    guard_body = guard_match.group(1)
    assert "metadata.mnrnd_provider_kind" in guard_body
    assert "metadata.mnrnd_provider_sha256" in guard_body
    assert "[sim, mnrnd_provider, dnadamage_overlay] = karr_bootstrap();" in source


def test_dnadamage_overlay_provenance_is_written_into_trace_metadata():
    source = _read_source()

    assert source.count("metadata.dnadamage_source_original_sha256 = dnadamage_overlay.source_sha256_lf_normalized;") == 1
    assert source.count("metadata.dnadamage_source_patched_sha256 = dnadamage_overlay.patched_sha256_lf_normalized;") == 1
    assert source.count("metadata.dnadamage_source_resolved_sha256 = dnadamage_overlay.resolved_sha256_lf_normalized;") == 1
    assert source.count("metadata.dnadamage_source_resolved_path = dnadamage_overlay.resolved_path;") == 1
    assert "if strcmp(canonical_name, 'DNADamage')" in source


def test_extraction_opts_override_surface_is_wired_into_real_scheduler_path():
    """DNADamage stimulus cohorts rely on a real extractor-side override
    surface, not a filename-only relabel. Statically prove that
    `extract_per_process_traces_v2` now accepts `extraction_opts`,
    persists the identity metadata, and applies per-process substrate
    overrides both before `calcResourceRequirements_Current()` and again
    after allocation injection but before `evolveState()`."""
    source = _read_source()

    assert (
        "function extract_per_process_traces_v2(process_names, output_subdir, n_ticks, seed, tick_offset, window_contract, anchor_opts, extraction_opts)"
        in source
    )
    assert "extraction_opts = default_extraction_opts(extraction_opts);" in source
    assert "metadata.condition_label = extraction_opts.condition_label;" in source
    assert "metadata.extraction_identity_json = extraction_opts.metadata_identity_json;" in source
    assert "function opts = default_extraction_opts(opts)" in source
    assert "function mod = apply_process_substrate_overrides(mod, extraction_opts)" in source

    # The override must influence both the request calculation pass and the
    # actual evolveState pass; a single application site would still leave
    # one of the two MATLAB paths seeing the old quiescent state.
    assert source.count("mod = apply_process_substrate_overrides(mod, extraction_opts);") == 2
    assert "r = mod.calcResourceRequirements_Current();" in source
    assert "mod.substrates(lidx, :) = allocation;" in source
    assert "[sim, before_tick, after_tick] = evolve_state_with_tap(sim, target_idx, snapshot_props, [], extraction_opts);" in source
    assert (
        "[sim, before_tick, after_tick] = evolve_state_with_tap(sim, target_idx, snapshot_props, anchor_opts, extraction_opts);"
        in source
    )


def _octave_executable() -> str | None:
    """Locate an Octave CLI binary on PATH, or return None if unavailable.

    This project's canonical execution environment is WSL (see the
    project's copilot-instructions "Execution Environment" rule), so this
    looks for the binary names Octave installs there. No MATLAB/Octave
    installation is required for this test suite to pass -- absence is a
    clean skip, never a failure, so cloud CI without Octave/MATLAB is
    unaffected."""
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
    Octave is available.

    Technique (verified empirically in a disposable scratch directory
    before being relied on here, and never run against this repository's
    real file until this exact probe): prepend a bare `1;` statement
    before the extractor source. That statement makes the file a
    *script*, so every subsequent `function ... end` in it becomes a
    *local function* defined within the script rather than the file's
    single top-level function. Octave's `source()` then parses the
    *entire* file -- including every nested local function body, so a
    genuine syntax error anywhere in the file is raised -- but it never
    *calls* `extract_per_process_traces_v2` or any of its helpers, so no
    simulation/bootstrap code ever runs. A sentinel string is printed
    only after `source()` returns successfully, and the real function
    bodies never execute, so the sentinel's presence/absence combined
    with the process exit code distinguishes "parses cleanly" from "parse
    error" without ever exercising `karr_bootstrap()` or any other
    simulation/extraction side effect.
    """
    octave = _octave_executable()
    assert octave is not None  # narrowed by skipif above

    source = _read_source()
    probe_path = tmp_path / "extract_per_process_traces_v2_parse_probe.m"
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
        "octave failed to parse extract_per_process_traces_v2.m "
        f"(exit {result.returncode}); stderr:\n{result.stderr}"
    )
    assert sentinel in result.stdout, (
        "expected parse-success sentinel missing from octave stdout "
        f"(stdout: {result.stdout!r})"
    )
    # The real function bodies must never execute. `karr_bootstrap` (the
    # simulation entry point reachable from this file's default-argument
    # path) is never invoked by `source()`, so its distinctive log banner
    # must never appear here -- this is a load-bearing assertion that the
    # probe truly never runs simulation/extraction code.
    assert "karr_bootstrap" not in result.stdout
    assert "karr_bootstrap" not in result.stderr
