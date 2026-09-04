"""Static/parse-only regression tests for the one-pass dual-tap
`scripts/matlab/extract_dual_division_window.m` extractor and its
resumable driver `scripts/matlab/extract_dual_division_window_seeds.m`.

Mirrors `tests/scripts/test_extract_per_process_traces_v2_static.py`'s
approach exactly: this file never invokes MATLAB/Octave/karr_bootstrap
against the real extractor (calling `extract_dual_division_window()` with
real arguments would fall straight into a real ~5h+ whole-cell simulation
bootstrap, forbidden here) -- every check is either a lightweight,
dependency-free static assertion on the source text, or an OPTIONAL
Octave parse-only probe (skipped cleanly when Octave/MATLAB is
unavailable).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event.evidence import _translate_windows_gitdir  # noqa: E402

EXTRACTOR_PATH = REPO_ROOT / "scripts" / "matlab" / "extract_dual_division_window.m"
DRIVER_PATH = REPO_ROOT / "scripts" / "matlab" / "extract_dual_division_window_seeds.m"
SINGLE_PROCESS_EXTRACTOR_PATH = REPO_ROOT / "scripts" / "matlab" / "extract_per_process_traces_v2.m"
SINGLE_PROCESS_FTSZ_DRIVER_PATH = REPO_ROOT / "scripts" / "matlab" / "extract_ftsz_pre_division_window_seeds.m"

_BLOCK_OPENERS = re.compile(r"\b(function|if|for|while|switch|try)\b")
_STANDALONE_END_LINE_RE = re.compile(r"^\s*end\s*;?\s*$")


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def _strip_comments_and_strings(source: str) -> str:
    """Identical technique to
    test_extract_per_process_traces_v2_static.py's own helper: strip
    `%`-comments and single-quoted string literals (honoring MATLAB's `''`
    escaped-quote convention) so keyword/`end` counts are never confused by
    a keyword-shaped token appearing inside a comment or string literal."""
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


def _block_balance(source: str) -> tuple[int, int]:
    code = _strip_comments_and_strings(source)
    openers = len(_BLOCK_OPENERS.findall(code))
    closers = sum(1 for line in code.splitlines() if _STANDALONE_END_LINE_RE.match(line))
    return openers, closers

def _function_body(source: str, start_marker: str) -> str:
    """Extract one function's full body (from just after its signature to
    just before the NEXT top-level `function` declaration, or end of file)
    by locating `start_marker` (a literal, must appear exactly once) and
    scanning forward to the next line that begins a new function
    definition. This is more robust than a non-greedy `.*?\\nend\\n` regex,
    which incorrectly stops at the FIRST nested if/for/while block's own
    closing `end` rather than the function's own final `end`."""
    assert source.count(start_marker) == 1, f"expected exactly one occurrence of {start_marker!r}"
    start = source.index(start_marker) + len(start_marker)
    next_fn = re.search(r"^function ", source[start:], re.MULTILINE)
    return source[start : start + next_fn.start()] if next_fn else source[start:]


# ---------------------------------------------------------------------------
# Existence + parse sanity
# ---------------------------------------------------------------------------


def test_extractor_and_driver_files_exist_and_are_nonempty():
    assert len(_read(EXTRACTOR_PATH)) > 0
    assert len(_read(DRIVER_PATH)) > 0


def test_extractor_block_keyword_balance():
    openers, closers = _block_balance(_read(EXTRACTOR_PATH))
    assert openers == closers, (
        f"extract_dual_division_window.m block-keyword balance mismatch: {openers} opener(s) "
        f"vs {closers} standalone 'end' statement(s)"
    )


def test_driver_block_keyword_balance():
    openers, closers = _block_balance(_read(DRIVER_PATH))
    assert openers == closers, (
        f"extract_dual_division_window_seeds.m block-keyword balance mismatch: {openers} opener(s) "
        f"vs {closers} standalone 'end' statement(s)"
    )


# ---------------------------------------------------------------------------
# Existing single-process scripts remain unchanged (fallback requirement)
# ---------------------------------------------------------------------------


def test_existing_single_process_scripts_are_untouched_by_this_change():
    """Task requirement: 'existing single-process scripts remain unchanged
    as fallback'. Proven here by asserting the git-tracked HEAD content of
    both single-process scripts is byte-identical to their current
    on-disk content -- if a future edit to this branch modified either
    file, this test fails loudly rather than relying on a reviewer to
    notice an unrelated diff."""
    for path in (SINGLE_PROCESS_EXTRACTOR_PATH, SINGLE_PROCESS_FTSZ_DRIVER_PATH):
        assert path.is_file(), f"missing {path}"
        rel = path.relative_to(REPO_ROOT).as_posix()
        result = subprocess.run(
            ["git", "show", f"HEAD:{rel}"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            # A WSL-hosted git cannot resolve a linked worktree's
            # Windows-style `gitdir:` gitlink directly (see
            # scripts/l2_event/evidence.py's _translate_windows_gitdir
            # docstring / write_cytokinesis_canary_d_evidence.py's
            # _resolve_git_dir_args, the same fallback this test mirrors).
            git_file = REPO_ROOT / ".git"
            translated = None
            if git_file.is_file():
                content = git_file.read_text().strip()
                if content.startswith("gitdir:"):
                    translated = _translate_windows_gitdir(content.split(":", 1)[1].strip())
            if translated is None:
                pytest.skip(f"git show HEAD:{rel} failed ({result.stderr.strip()}); skipping unchanged-file check")
            result = subprocess.run(
                ["git", f"--git-dir={translated}", "show", f"HEAD:{rel}"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                pytest.skip(f"git show HEAD:{rel} failed ({result.stderr.strip()}); skipping unchanged-file check")
        assert result.stdout == path.read_text(encoding="utf-8"), (
            f"{rel} differs from its committed HEAD content -- this task must never modify "
            "the existing single-process extraction scripts"
        )


# ---------------------------------------------------------------------------
# One sim bootstrap / one seed per seed
# ---------------------------------------------------------------------------


def test_exactly_one_karr_bootstrap_call_and_one_seed_call():
    source = _read(EXTRACTOR_PATH)
    assert source.count("[sim, mnrnd_provider, ~] = karr_bootstrap();") == 1, (
        "extract_dual_division_window.m must call karr_bootstrap() exactly once per seed "
        "(one trajectory shared by both taps), not once per process"
    )
    assert source.count("seed_simulation(sim, seed);") == 1


def test_dual_tap_never_calls_the_single_process_extractor():
    """The whole point of this extractor is to avoid delegating each
    process to extract_per_process_traces_v2 (which would re-run a full
    trajectory per process). Statically prove it never calls that
    function."""
    source = _read(EXTRACTOR_PATH)
    assert "extract_per_process_traces_v2(" not in source


# ---------------------------------------------------------------------------
# Both taps captured in one scheduler pass
# ---------------------------------------------------------------------------


def test_single_scheduler_loop_taps_both_target_indices():
    source = _read(EXTRACTOR_PATH)
    assert source.count("function [sim, before_a, after_a, before_b, after_b] = ") == 1
    assert "evolve_state_with_dual_tap(sim, idx_a, props_a, idx_b, props_b, anchor_opts)" in source

    # Exactly one for-loop over processes performs BOTH taps (proc_idx ==
    # idx_a / proc_idx == idx_b), never two separate loops.
    assert source.count("for i = 1:nProcesses") == 2  # one for calcResourceRequirements, one for the tap loop
    assert "if proc_idx == idx_a" in source
    assert "elseif proc_idx == idx_b" in source

    # Completion/onset detection reads ONLY process A's tap.
    tap_loop_body = _function_body(
        source,
        "function [sim, before_a, after_a, before_b, after_b] = ...\n"
        "    evolve_state_with_dual_tap(sim, idx_a, props_a, idx_b, props_b, anchor_opts)\n",
    )
    assert "before_a = merge_event_observables(before_a, mod, anchor_opts);" in tap_loop_body
    assert "after_a = merge_event_observables(after_a, mod, anchor_opts);" in tap_loop_body
    # process B is only ever plain-snapshotted, never merged with the
    # event-observable projection (it has no pinchedDiameter/ftsZRing/
    # chromosome properties of its own).
    assert "before_b = merge_event_observables" not in source
    assert "after_b = merge_event_observables" not in source


def test_completion_detected_solely_from_process_a():
    source = _read(EXTRACTOR_PATH)
    body = _function_body(
        source,
        "function [states_before_a, states_after_a, tick_start_a, completion_tick, onset_tick, ...\n"
        "          states_before_b, states_after_b, tick_start_b, ok, error_message] = ...\n"
        "    capture_dual_anchor_windows(sim, idx_a, props_a, n_ticks_a, idx_b, props_b, n_ticks_b, anchor_opts)\n",
    )
    assert "before_val = before_a.pinchedDiameter;" in body
    assert "after_val = after_a.pinchedDiameter;" in body
    # process B's snapshot must never appear in the onset/completion predicate.
    assert "before_b.pinchedDiameter" not in body
    assert "after_b.pinchedDiameter" not in body


# ---------------------------------------------------------------------------
# Exact window lengths / anchor arithmetic
# ---------------------------------------------------------------------------


def test_catalog_window_lengths_are_hardcoded_from_the_authoritative_catalog():
    source = _read(EXTRACTOR_PATH)
    assert "cyt_n_ticks = 4000;   % catalog M_ticks (Cytokinesis)" in source
    assert "ftsz_n_ticks = 200;   % catalog M_ticks (FtsZPolymerization)" in source


def test_both_windows_end_at_the_same_completion_tick():
    source = _read(EXTRACTOR_PATH)
    # Cytokinesis's own window_anchor IS the discovered completion_tick.
    assert "cyt_metadata.window_anchor = int32(completion_tick);" in source
    # FtsZ's window_anchor must be the SAME completion_tick value, never a
    # separately discovered or offset value.
    assert "ftsz_metadata.window_anchor = int32(completion_tick);" in source


def test_span_self_check_present_for_both_windows():
    source = _read(EXTRACTOR_PATH)
    assert "(completion_tick - cyt_tick_start + 1) ~= cyt_n_ticks" in source
    assert "(completion_tick - ftsz_tick_start + 1) ~= ftsz_n_ticks" in source


def test_tick_start_arithmetic_in_capture_function():
    source = _read(EXTRACTOR_PATH)
    assert "tick_start_a = completion_tick - n_ticks_a + 1;" in source
    assert "tick_start_b = completion_tick - n_ticks_b + 1;" in source


# ---------------------------------------------------------------------------
# Provider metadata
# ---------------------------------------------------------------------------


def test_provider_metadata_written_for_both_outputs_from_the_same_provider():
    source = _read(EXTRACTOR_PATH)
    assert source.count("cyt_metadata = add_genuine_provider_metadata(cyt_metadata, mnrnd_provider);") == 1
    assert source.count("ftsz_metadata = add_genuine_provider_metadata(ftsz_metadata, mnrnd_provider);") == 1
    # Both calls pass the SAME mnrnd_provider variable (returned by the
    # single karr_bootstrap() call) -- never two independently-resolved
    # provider structs.
    assert "[sim, mnrnd_provider, ~] = karr_bootstrap();" in source

    helper_match = re.search(
        r"function metadata = add_genuine_provider_metadata\(metadata, mnrnd_provider\)\n(.*?)\nend\n",
        source,
        re.DOTALL,
    )
    assert helper_match is not None
    body = helper_match.group(1)
    for field in (
        "mnrnd_provider_kind",
        "mnrnd_provider_matlab_release",
        "mnrnd_provider_toolbox_version",
        "mnrnd_provider_path_relative_to_matlabroot",
        "mnrnd_provider_sha256",
        "statistics_rng_provider_identity_json",
    ):
        assert f"metadata.{field}" in body


# ---------------------------------------------------------------------------
# Atomic / fail-closed writes
# ---------------------------------------------------------------------------


def test_atomic_write_uses_temp_paths_and_verifies_before_promoting():
    source = _read(EXTRACTOR_PATH)
    assert "cyt_tmp_path = fullfile(out_root, sprintf('.tmp-%s-%s_%dticks.mat', token, cyt_process_name, cyt_n_ticks));" in source
    assert "ftsz_tmp_path = fullfile(out_root, sprintf('.tmp-%s-%s_%dticks.mat', token, ftsz_process_name, ftsz_n_ticks));" in source
    assert "cleanup_temps = onCleanup(@() remove_if_exists({cyt_tmp_path, ftsz_tmp_path}));" in source

    # Both temp files must be verified BEFORE either movefile call.
    verify_idx_cyt = source.index("verify_temp_output(cyt_tmp_path")
    verify_idx_ftsz = source.index("verify_temp_output(ftsz_tmp_path")
    move_idx_cyt = source.index("movefile(cyt_tmp_path, cyt_out_path);")
    move_idx_ftsz = source.index("movefile(ftsz_tmp_path, ftsz_out_path);")
    assert verify_idx_cyt < move_idx_cyt
    assert verify_idx_ftsz < move_idx_cyt
    assert move_idx_cyt < move_idx_ftsz


def test_partial_output_guard_refuses_a_lone_existing_file():
    source = _read(EXTRACTOR_PATH)
    assert "extract_dual_division_window:partial_output_exists" in source
    assert "if cyt_exists || ftsz_exists" in source


def test_no_output_canonicalized_on_capture_failure():
    """Every failure path inside capture_dual_anchor_windows sets ok=false
    and returns BEFORE any buffer replay/metadata/save/movefile code runs
    -- proven here by asserting the main function raises immediately on
    `~ok` before any metadata struct is built."""
    source = _read(EXTRACTOR_PATH)
    guard_idx = source.index("if ~ok\n    error('extract_dual_division_window:capture_failed'")
    first_metadata_idx = source.index("cyt_metadata = struct(")
    assert guard_idx < first_metadata_idx


def test_verify_temp_output_checked_before_movefile_reads_from_disk_not_memory():
    """verify_temp_output must re-`load()` the just-written file rather
    than trusting the in-memory struct, so a save() that silently
    corrupted/truncated the file on disk is caught pre-promotion."""
    source = _read(EXTRACTOR_PATH)
    body = _function_body(
        source,
        "function verify_temp_output(tmp_path, expected_process_name, expected_n_ticks, expected_seed)\n",
    )
    assert "loaded = load(tmp_path, 'states_before', 'states_after', 'metadata');" in body
    assert "isfield(metadata, 'window_anchor')" in body
    assert "isfield(metadata, 'tick_end')" in body


# ---------------------------------------------------------------------------
# Resumable driver
# ---------------------------------------------------------------------------


def test_driver_skips_only_when_both_outputs_exist():
    source = _read(DRIVER_PATH)
    assert "both_exist = exist(cyt_out_path, 'file') == 2 && exist(ftsz_out_path, 'file') == 2;" in source
    assert "if both_exist && ~force_this" in source


def test_driver_force_seeds_rechecks_deletion_before_reextracting():
    source = _read(DRIVER_PATH)
    assert "delete_if_exists(cyt_out_path);" in source
    assert "delete_if_exists(ftsz_out_path);" in source
    assert "if exist(cyt_out_path, 'file') == 2 || exist(ftsz_out_path, 'file') == 2" in source


def test_driver_aggregates_and_throws_on_any_seed_failure():
    source = _read(DRIVER_PATH)
    assert "failed_seeds{end + 1}" in source
    assert "error('extract_dual_division_window_seeds:extraction_failed'" in source


def test_driver_calls_the_dual_extractor_not_the_single_process_one():
    source = _read(DRIVER_PATH)
    assert "extract_dual_division_window(uint32(s));" in source
    assert "extract_per_process_traces_v2(" not in source
    assert "extract_ftsz_pre_division_window_seeds(" not in source


# ---------------------------------------------------------------------------
# Optional real parse-only probe (Octave)
# ---------------------------------------------------------------------------


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
@pytest.mark.parametrize("path", [EXTRACTOR_PATH, DRIVER_PATH])
def test_real_parse_only_probe_via_octave(tmp_path: Path, path: Path):
    """Same technique as
    test_extract_per_process_traces_v2_static.py::test_real_parse_only_probe_via_octave:
    prepend `1;` so every `function ... end` becomes a local function in a
    script, letting Octave's `source()` parse (but never call) the entire
    file."""
    octave = _octave_executable()
    assert octave is not None

    source = _read(path)
    probe_path = tmp_path / f"{path.stem}_parse_probe.m"
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
        f"octave failed to parse {path.name} (exit {result.returncode}); stderr:\n{result.stderr}"
    )
    assert sentinel in result.stdout
    assert "karr_bootstrap" not in result.stdout
    assert "karr_bootstrap" not in result.stderr
