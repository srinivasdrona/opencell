"""Static source-inspection guards for
``scripts/matlab/run_ribosome_seeds_batch.m`` (Opus review, 2026-08-05).

This batch script cannot be unit-tested by actually running it (it
requires a real MATLAB license + the Karr fitted simulation and takes on
the order of an hour for 48 seeds), so -- mirroring the established
source-inspection pattern already used for other MATLAB scripts in this
repo (see e.g. ``test_h12_perturbation.py``'s
``test_run_ppii_scenario_b_matlab_uses_lossless_dlmwrite_not_csvwrite``
and ``test_probe_matlab_environment_m_writes_json_before_erroring_on_overall_pass_false``)
-- these tests statically assert the presence and relative ordering of
the specific patterns that make the script resumable and non-destructive:

  1. failures are accumulated across seeds (not swallowed per-seed), and
     the script exits nonzero if ANY seed failed;
  2. an existing final output file is structurally validated (not merely
     checked for existence) before being trusted and skipped;
  3. a freshly extracted file is written to a temp path, validated there,
     and only THEN atomically moved into the real final path -- so a
     failed/incomplete extraction can never destroy previously-good
     evidence, and a truncated file can never be permanently mistaken for
     complete evidence.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

BATCH_SCRIPT_PATH = REPO_ROOT / "scripts" / "matlab" / "run_ribosome_seeds_batch.m"


def _source() -> str:
    return BATCH_SCRIPT_PATH.read_text(encoding="utf-8")


def test_batch_script_exists():
    assert BATCH_SCRIPT_PATH.exists()


def test_batch_script_accumulates_failures_across_seeds():
    source = _source()
    assert "failed_seeds = {}" in source
    # Both the extraction try/catch AND the post-extraction validation
    # failure must append to the SAME accumulator, not just one of them.
    assert source.count("failed_seeds{end + 1}") >= 2


def test_batch_script_exits_nonzero_if_any_seed_failed():
    source = _source()
    guard_idx = source.index("if n_failed > 0")
    exit1_idx = source.index("exit(1)")
    exit0_idx = source.index("exit(0)")
    assert guard_idx < exit1_idx, "exit(1) must be inside the n_failed > 0 guard"
    # The unconditional success exit(0) must come strictly AFTER the
    # failure guard (and thus after exit(1)) in the script's control flow,
    # so a caller can never observe exit(0) while failed_seeds is nonempty.
    assert exit1_idx < exit0_idx


def test_batch_script_validates_existing_output_before_skipping_not_existence_only():
    source = _source()
    exist_check_idx = source.index("if exist(final_path, 'file')")
    validate_call_idx = source.index("ribosome_batch_validate_seed_mat(final_path, s)")
    skip_idx = source.index("existing output already validated, skipping")
    assert exist_check_idx < validate_call_idx < skip_idx, (
        "an existing final_path must be independently validated BEFORE the "
        "'already validated, skipping' branch is reached -- bare existence "
        "must never itself justify skipping."
    )
    # The invalid-existing-file branch must fall through to re-extraction
    # (never silently skip, never delete the old file itself).
    assert "FAILED validation" in source
    assert "re-extracting to a temp path" in source


def test_batch_script_extracts_to_temp_path_and_atomically_moves_into_place():
    source = _source()
    tempname_idx = source.index("tempname()")
    extract_call_idx = source.index("extract_per_process_traces_v2({process_name}, tmp_subdir")
    tmp_validate_idx = source.index("ribosome_batch_validate_seed_mat(tmp_path, s)")
    movefile_idx = source.index("movefile(tmp_path, final_path")
    assert tempname_idx < extract_call_idx, "a fresh unique temp subdir must be allocated before extraction"
    assert extract_call_idx < tmp_validate_idx, "the freshly extracted temp file must be validated after extraction"
    assert tmp_validate_idx < movefile_idx, (
        "the temp file must be validated BEFORE being moved into the final path -- "
        "an unvalidated (possibly truncated) file must never reach final_path."
    )


def test_batch_script_never_calls_save_directly_on_final_path():
    """The script itself must never write directly to final_path -- all
    writes go through extract_per_process_traces_v2 targeting a temp
    subdir, followed by an atomic movefile. A direct `save(final_path, ...)`
    call in this script would defeat the whole atomic-write contract."""
    source = _source()
    assert "save(final_path" not in source
    assert "save(out_path" not in source


def test_batch_script_movefile_uses_force_flag_for_atomic_overwrite():
    """The 'f' force flag is required so a KNOWN-invalid existing
    final_path (already independently confirmed invalid earlier in the
    same iteration) can be overwritten by the newly-validated temp file."""
    source = _source()
    assert "movefile(tmp_path, final_path, 'f')" in source


def test_validate_seed_mat_helper_checks_required_variables_and_rng_seed():
    source = _source()
    assert "function [ok, reason] = ribosome_batch_validate_seed_mat" in source
    assert "states_before" in source
    assert "states_after" in source
    assert "metadata.rng_seed" in source or "loaded.metadata.rng_seed" in source
    # Truncated/corrupt files must be caught via try/catch around the
    # actual load, not merely via exist().
    validate_fn_idx = source.index("function [ok, reason] = ribosome_batch_validate_seed_mat")
    try_idx = source.index("try", validate_fn_idx)
    catch_idx = source.index("catch err", validate_fn_idx)
    assert validate_fn_idx < try_idx < catch_idx


def test_batch_script_does_not_hardcode_a_naive_existence_only_skip():
    """Regression guard for the specific defect this fix addresses: the
    pre-fix script's skip branch was reached directly from
    `exist(out_path, 'file')` with no intervening validation call. The
    fixed script's `exist(final_path, 'file')` check must always be
    followed by a call into the validation helper before any 'skipping'
    log line -- already asserted precisely by
    test_batch_script_validates_existing_output_before_skipping_not_existence_only
    above; this test additionally guards against a regression where a
    SECOND, unguarded skip path is reintroduced elsewhere in the file."""
    source = _source()
    assert source.count("skipping") == 1
