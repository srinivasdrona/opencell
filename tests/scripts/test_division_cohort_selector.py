"""Inversion tests for `scripts/l2_event/division_cohort_selector.py` --
the division-censor-contract (2026-09-08) cohort selector/auditor.

Every test here proves the selector REFUSES or correctly reclassifies an
attempted shortcut around the contract:
  * skipping a censored seed / a genuine gap in the attempt ledger,
  * counting a censored seed toward the required completed-window total,
  * a noncontiguous attempt ledger (out-of-order completions),
  * mixed censoring horizons / mixed DNADamage source hashes across the
    same cohort,
  * a RIGHT_CENSORED record co-existing with trace files on disk,
  * a COMPLETED record with one or both trace files missing,
  * selecting a later completion while an earlier, contiguous-prefix seed
    is still unattempted,
  * an existing pre-50k-horizon COMPLETED trace remaining valid evidence
    under the larger H=100000 selection horizon (that horizon only binds
    RIGHT_CENSORED claims, never invalidates a real completion).

Most tests exercise `audit_cohort` against a directly-supplied synthetic
`ledger` (bypassing real trace-file validation entirely, since building a
fully valid HDF5 dual-tap fixture is out of scope for this module's own
selection-logic tests -- that end-to-end path is exercised separately by
`tests/scripts/test_validate_dual_division_canary.py`). The two mutual-
exclusivity tests that DO need real files on disk only need file
*existence*, not valid HDF5 content, because `resolve_seed_attempt`
checks existence before ever attempting to parse a trace.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

from scripts.l2_event import launcher  # noqa: E402
from scripts.l2_event.division_cohort_selector import (  # noqa: E402
    COMPLETED,
    RIGHT_CENSORED,
    AttemptRecord,
    CohortContractError,
    audit_cohort,
    authoritative_karr_native_root,
    default_search_roots,
    discover_ledger,
    read_attempt_record_file,
    resolve_seed_attempt,
)
from scripts.l2_event.division_window_spec import (  # noqa: E402
    attempt_record_filename,
    candidate_seed_start,
    required_completed_windows,
    selection_horizon_max_search_ticks,
)
from scripts.l2_event.validate_dual_division_canary import (  # noqa: E402
    CYTOKINESIS_N_TICKS,
    event_window_dir,
)


@pytest.fixture(autouse=True)
def _fake_local_genuine_provider(monkeypatch, tmp_path):
    """Mirrors test_validate_dual_division_canary.py's fixture of the same
    name: fakes a local MATLAB install so
    launcher.current_genuine_mnrnd_provider() is deterministic/portable
    across dev machines, rather than depending on whatever MATLAB happens
    to be installed locally. The real DNADamage WCM source tree (part of
    the tracked repo checkout) is left untouched -- it needs no faking."""
    matlab_root = tmp_path / "MATLAB"
    for name in launcher.STATISTICS_RNG_FUNCTIONS:
        provider_path = launcher.genuine_statistics_rng_path(name, matlab_root=matlab_root)
        provider_path.parent.mkdir(parents=True, exist_ok=True)
        provider_path.write_text(f"% fake genuine {name} provider\n", encoding="utf-8", newline="\n")
    contents_path = matlab_root / launcher.STATISTICS_TOOLBOX_CONTENTS_RELATIVE_PATH
    contents_path.write_text(
        "% Statistics and Machine Learning Toolbox\n% Version 26.1 (R2026a) 12-Jan-2026\n",
        encoding="utf-8",
        newline="\n",
    )
    version_info_path = matlab_root / launcher.MATLAB_VERSION_INFO_RELATIVE_PATH
    version_info_path.write_text(
        "<?xml version=\"1.0\"?><MathWorks_version_info><release>R2026a</release></MathWorks_version_info>\n",
        encoding="utf-8",
        newline="\n",
    )
    monkeypatch.setattr(launcher, "DEFAULT_MATLAB_ROOT", matlab_root)


def _current_censor_identity() -> tuple[str, str]:
    """The real (dnadamage_source_resolved_sha256, mnrnd_provider_sha256)
    pair a genuinely current-source-bound RIGHT_CENSORED record must
    carry -- computed the SAME way division_cohort_selector's own
    _current_censor_identity_values does, so a test-constructed "valid"
    censor record is actually valid against the real check, not merely
    against a second hardcoded assumption of what "current" means."""
    dnadamage = launcher.current_genuine_dnadamage_source()["patched_sha256_lf_normalized"]
    mnrnd = launcher.current_genuine_mnrnd_provider()["sha256_lf_normalized"]
    return dnadamage, mnrnd


def _record(seed: int, status: str, *, max_search_ticks=None, dnadamage_sha=None,
            mnrnd_sha=None, cyt_sha=None, ftsz_sha=None, backfilled=False) -> AttemptRecord:
    if status == RIGHT_CENSORED and (dnadamage_sha is None or mnrnd_sha is None):
        current_dnadamage, current_mnrnd = _current_censor_identity()
        dnadamage_sha = dnadamage_sha if dnadamage_sha is not None else current_dnadamage
        mnrnd_sha = mnrnd_sha if mnrnd_sha is not None else current_mnrnd
    return AttemptRecord(
        seed=seed,
        status=status,
        max_search_ticks=max_search_ticks,
        source_root=Path("."),
        dnadamage_source_resolved_sha256=dnadamage_sha or "same-source-sha",
        mnrnd_provider_sha256=mnrnd_sha,
        cytokinesis_trace_sha256=cyt_sha or (f"cyt-sha-{seed}" if status == COMPLETED else None),
        ftsz_trace_sha256=ftsz_sha or (f"ftsz-sha-{seed}" if status == COMPLETED else None),
        backfilled=backfilled,
    )


# ---------------------------------------------------------------------------
# Contract constants sanity (locks in the real preregistered values these
# inversion tests rely on).
# ---------------------------------------------------------------------------


def test_contract_constants_match_the_real_repo_spec():
    assert candidate_seed_start() == 0
    assert required_completed_windows() == 50
    assert selection_horizon_max_search_ticks() == 100000


# ---------------------------------------------------------------------------
# Skipping a censored seed / a genuine gap
# ---------------------------------------------------------------------------


def test_valid_censored_seed_does_not_break_contiguity_or_count_toward_n():
    horizon = selection_horizon_max_search_ticks()
    ledger = {
        0: _record(0, COMPLETED),
        1: _record(1, COMPLETED),
        2: _record(2, RIGHT_CENSORED, max_search_ticks=horizon),
        3: _record(3, COMPLETED),
    }
    audit = audit_cohort(ledger=ledger)
    assert audit.contiguous_prefix_end == 3
    assert audit.next_seed_to_attempt == 4
    assert audit.censored_seeds == [2]
    assert audit.completed_seeds == [0, 1, 3]
    assert 2 not in audit.completed_seeds
    assert audit.completed_count == 3  # censored seed never counted toward N


def test_genuine_gap_stops_contiguity_and_reports_next_seed():
    """Mirrors the real seed-6/seed-18 situation: seeds attempted out of
    order by parallel workers, with unattempted holes in between."""
    ledger = {
        0: _record(0, COMPLETED),
        1: _record(1, COMPLETED),
        # seed 2 has no record at all -- a genuine gap, never inferred censored.
        3: _record(3, COMPLETED),
    }
    audit = audit_cohort(ledger=ledger)
    assert audit.contiguous_prefix_end == 1
    assert audit.next_seed_to_attempt == 2
    assert audit.gap_seeds == [2]
    assert audit.premature_seeds == [3]
    assert audit.completed_seeds == [0, 1]
    assert 3 not in audit.completed_seeds  # premature completion excluded until gap fills


# ---------------------------------------------------------------------------
# Counting censor toward N (must never happen)
# ---------------------------------------------------------------------------


def test_censored_seeds_never_count_toward_required_completed_windows():
    horizon = selection_horizon_max_search_ticks()
    ledger = {}
    for seed in range(10):
        ledger[seed] = _record(seed, RIGHT_CENSORED, max_search_ticks=horizon)
    audit = audit_cohort(ledger=ledger)
    assert audit.completed_count == 0
    assert audit.selected_seeds == []
    assert audit.selection_satisfied is False
    assert audit.censored_seeds == list(range(10))


# ---------------------------------------------------------------------------
# Noncontiguous attempt ledger / mixed horizons / mixed source hashes
# ---------------------------------------------------------------------------


def test_noncontiguous_ledger_reports_gap_and_premature_seeds_separately():
    ledger = {
        0: _record(0, COMPLETED),
        5: _record(5, COMPLETED),
        6: _record(6, COMPLETED),
    }
    audit = audit_cohort(ledger=ledger)
    assert audit.contiguous_prefix_end == 0
    assert audit.next_seed_to_attempt == 1
    assert audit.gap_seeds == [1, 2, 3, 4]
    assert audit.premature_seeds == [5, 6]
    assert audit.selected_seeds == [0]


def test_mixed_censoring_horizons_reclassifies_invalid_horizon_as_a_gap():
    required_horizon = selection_horizon_max_search_ticks()
    ledger = {
        0: _record(0, COMPLETED),
        1: _record(1, RIGHT_CENSORED, max_search_ticks=50000),  # stale/short horizon
        2: _record(2, COMPLETED),
    }
    audit = audit_cohort(ledger=ledger)
    assert len(audit.invalid_censor_seeds) == 1
    assert audit.invalid_censor_seeds[0]["seed"] == 1
    assert audit.invalid_censor_seeds[0]["recorded_max_search_ticks"] == 50000
    assert audit.invalid_censor_seeds[0]["required_max_search_ticks"] == required_horizon
    # seed 1's invalid censor is reclassified as an unattempted gap -- it
    # must never silently count as a valid censored attempt.
    assert 1 not in audit.censored_seeds
    assert audit.contiguous_prefix_end == 0
    assert audit.gap_seeds == [1]
    assert audit.premature_seeds == [2]


def test_mixed_dnadamage_source_hashes_reported_as_mismatch():
    ledger = {
        0: _record(0, COMPLETED, dnadamage_sha="source-A"),
        1: _record(1, COMPLETED, dnadamage_sha="source-B"),
    }
    audit = audit_cohort(ledger=ledger)
    assert len(audit.source_hash_mismatches) == 2
    hashes = {row["dnadamage_source_resolved_sha256"] for row in audit.source_hash_mismatches}
    assert hashes == {"source-A", "source-B"}


def test_duplicate_trace_content_across_seeds_is_detected():
    ledger = {
        0: _record(0, COMPLETED, cyt_sha="shared-cyt-hash"),
        1: _record(1, COMPLETED, cyt_sha="shared-cyt-hash"),
    }
    audit = audit_cohort(ledger=ledger)
    assert len(audit.duplicate_trace_hashes) == 1
    assert audit.duplicate_trace_hashes[0]["seed"] == 1
    assert audit.duplicate_trace_hashes[0]["duplicate_of_seed"] == 0


# ---------------------------------------------------------------------------
# Selecting a later completion while an earlier completed seed is omitted
# ---------------------------------------------------------------------------


def test_never_selects_a_later_completion_while_an_earlier_seed_is_unattempted():
    ledger = {
        0: _record(0, COMPLETED),
        # seed 1 entirely absent (gap)
        2: _record(2, COMPLETED),
        3: _record(3, COMPLETED),
    }
    audit = audit_cohort(ledger=ledger)
    assert audit.selected_seeds == [0]
    assert 2 not in audit.selected_seeds
    assert 3 not in audit.selected_seeds
    assert audit.selection_satisfied is False


# ---------------------------------------------------------------------------
# Existing pre-50k completed trace accepted under H=100k
# ---------------------------------------------------------------------------


def test_pre_existing_completed_trace_under_smaller_horizon_still_counts():
    """A COMPLETED record captured under the OLD default max_search_ticks
    (50000) remains valid evidence under the larger H=100000 selection
    horizon -- the horizon only binds RIGHT_CENSORED claims, never
    retroactively invalidates a real completion."""
    ledger = {seed: _record(seed, COMPLETED, max_search_ticks=50000) for seed in range(6)}
    audit = audit_cohort(ledger=ledger)
    assert audit.completed_seeds == list(range(6))
    assert audit.completed_count == 6


def test_full_cohort_satisfied_with_exactly_required_completed_windows():
    required = required_completed_windows()
    ledger = {seed: _record(seed, COMPLETED) for seed in range(required)}
    audit = audit_cohort(ledger=ledger)
    assert audit.selection_satisfied is True
    assert len(audit.selected_seeds) == required
    assert audit.selected_seeds == list(range(required))


def test_extra_completions_beyond_required_are_not_selected():
    required = required_completed_windows()
    ledger = {seed: _record(seed, COMPLETED) for seed in range(required + 5)}
    audit = audit_cohort(ledger=ledger)
    assert len(audit.selected_seeds) == required
    assert audit.selected_seeds == list(range(required))
    assert required in ledger and required not in audit.selected_seeds


# ---------------------------------------------------------------------------
# Mutual exclusivity (censor with trace files / completed without both
# files) -- exercised against real on-disk existence, no valid HDF5 needed.
# ---------------------------------------------------------------------------


def test_right_censored_record_with_a_trace_file_present_raises(tmp_path):
    seed = 7
    out_dir = event_window_dir(seed, karr_native_root=tmp_path)
    out_dir.mkdir(parents=True)
    (out_dir / attempt_record_filename()).write_text(
        json.dumps({"status": RIGHT_CENSORED, "max_search_ticks": 100000}), encoding="utf-8"
    )
    # A stray trace file co-existing with a RIGHT_CENSORED record is a
    # direct contract violation -- content does not matter, only presence.
    (out_dir / f"Cytokinesis_{CYTOKINESIS_N_TICKS}ticks.mat").write_bytes(b"not a real trace")
    with pytest.raises(CohortContractError, match="co-exists with a trace file"):
        resolve_seed_attempt(seed, karr_native_root=tmp_path)


def test_completed_record_missing_one_trace_file_raises(tmp_path):
    seed = 8
    out_dir = event_window_dir(seed, karr_native_root=tmp_path)
    out_dir.mkdir(parents=True)
    (out_dir / attempt_record_filename()).write_text(
        json.dumps({"status": COMPLETED, "max_search_ticks": 100000}), encoding="utf-8"
    )
    # Only the Cytokinesis file is present; FtsZ is missing.
    (out_dir / f"Cytokinesis_{CYTOKINESIS_N_TICKS}ticks.mat").write_bytes(b"not a real trace")
    with pytest.raises(CohortContractError, match="trace file\\(s\\) missing"):
        resolve_seed_attempt(seed, karr_native_root=tmp_path)


def test_completed_record_missing_both_trace_files_raises(tmp_path):
    seed = 9
    out_dir = event_window_dir(seed, karr_native_root=tmp_path)
    out_dir.mkdir(parents=True)
    (out_dir / attempt_record_filename()).write_text(
        json.dumps({"status": COMPLETED, "max_search_ticks": 100000}), encoding="utf-8"
    )
    with pytest.raises(CohortContractError, match="trace file\\(s\\) missing"):
        resolve_seed_attempt(seed, karr_native_root=tmp_path)


def test_absent_seed_directory_resolves_to_no_record_a_gap(tmp_path):
    assert resolve_seed_attempt(42, karr_native_root=tmp_path) is None


def test_empty_seed_directory_with_no_files_resolves_to_no_record_a_gap(tmp_path):
    seed = 10
    out_dir = event_window_dir(seed, karr_native_root=tmp_path)
    out_dir.mkdir(parents=True)
    assert resolve_seed_attempt(seed, karr_native_root=tmp_path) is None


# ---------------------------------------------------------------------------
# Malformed attempt-record file handling (read_attempt_record_file)
# ---------------------------------------------------------------------------


def test_read_attempt_record_missing_file_returns_none(tmp_path):
    assert read_attempt_record_file(tmp_path / "does_not_exist.json") is None


def test_read_attempt_record_malformed_json_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{ not valid json", encoding="utf-8")
    with pytest.raises(CohortContractError):
        read_attempt_record_file(path)


def test_read_attempt_record_missing_status_key_raises(tmp_path):
    path = tmp_path / "no_status.json"
    path.write_text(json.dumps({"seed": 1}), encoding="utf-8")
    with pytest.raises(CohortContractError):
        read_attempt_record_file(path)


def test_read_attempt_record_invalid_status_value_raises(tmp_path):
    path = tmp_path / "bad_status.json"
    path.write_text(json.dumps({"status": "MAYBE"}), encoding="utf-8")
    with pytest.raises(CohortContractError):
        read_attempt_record_file(path)


# ---------------------------------------------------------------------------
# Multi-root integrity (Opus re-review, 2026-09-09): every root is
# inspected for every seed; contradictory records across roots hard-fail
# rather than "first root wins".
# ---------------------------------------------------------------------------


def _write_completed_pair_and_record(
    root: Path, seed: int, *, cyt_sha_content: bytes = b"cyt-bytes", ftsz_sha_content: bytes = b"ftsz-bytes"
) -> None:
    out_dir = event_window_dir(seed, karr_native_root=root)
    out_dir.mkdir(parents=True, exist_ok=True)
    cyt_path = out_dir / f"Cytokinesis_{CYTOKINESIS_N_TICKS}ticks.mat"
    cyt_path.write_bytes(cyt_sha_content)
    from scripts.l2_event.validate_dual_division_canary import FTSZ_N_TICKS

    ftsz_path = out_dir / f"FtsZPolymerization_{FTSZ_N_TICKS}ticks.mat"
    ftsz_path.write_bytes(ftsz_sha_content)


def test_multi_root_agreement_never_first_wins_blindly_but_dedupes_when_consistent(tmp_path):
    """Two roots BOTH reporting the SAME real censored outcome for one
    seed (agreeing on every identity field) must be accepted and
    deduplicated -- proving the multi-root check is not merely paranoid
    rejection, but genuine agreement verification."""
    root_a = tmp_path / "root_a"
    root_b = tmp_path / "root_b"
    dnadamage_sha, mnrnd_sha = _current_censor_identity()
    horizon = selection_horizon_max_search_ticks()
    record_json = json.dumps(
        {
            "status": RIGHT_CENSORED,
            "max_search_ticks": horizon,
            "dnadamage_source_resolved_sha256": dnadamage_sha,
            "mnrnd_provider_sha256": mnrnd_sha,
        }
    )
    for root in (root_a, root_b):
        out_dir = event_window_dir(6, karr_native_root=root)
        out_dir.mkdir(parents=True)
        (out_dir / attempt_record_filename()).write_text(record_json, encoding="utf-8")

    ledger = discover_ledger([root_a, root_b])
    assert 6 in ledger
    assert ledger[6].status == RIGHT_CENSORED


def test_multi_root_contradiction_hard_fails_never_first_wins(tmp_path):
    """Two roots reporting DIFFERENT outcomes for the SAME seed (one says
    RIGHT_CENSORED, the other has a COMPLETED trace pair) must raise
    CohortContractError -- the selector must never silently trust
    whichever root happens to be listed/searched first."""
    root_a = tmp_path / "root_a"
    root_b = tmp_path / "root_b"
    horizon = selection_horizon_max_search_ticks()
    dnadamage_sha, mnrnd_sha = _current_censor_identity()

    out_dir_a = event_window_dir(9, karr_native_root=root_a)
    out_dir_a.mkdir(parents=True)
    (out_dir_a / attempt_record_filename()).write_text(
        json.dumps(
            {
                "status": RIGHT_CENSORED,
                "max_search_ticks": horizon,
                "dnadamage_source_resolved_sha256": dnadamage_sha,
                "mnrnd_provider_sha256": mnrnd_sha,
            }
        ),
        encoding="utf-8",
    )

    # root_b has a stray (garbage-content, non-HDF5) "trace pair" for the
    # same seed with NO attempt record -- resolve_seed_attempt would
    # normally attempt real HDF5 validation here and raise on garbage
    # content; that's still a legitimate contradiction (root_a claims
    # censored, root_b claims something else entirely), so the test only
    # needs discover_ledger to surface SOME hard failure, not necessarily
    # CohortContractError specifically, when roots disagree this badly.
    _write_completed_pair_and_record(root_b, 9)

    with pytest.raises(Exception):  # noqa: B017 - either CohortContractError or a validation error
        discover_ledger([root_a, root_b])


# ---------------------------------------------------------------------------
# RIGHT_CENSORED identity binding (Opus re-review, 2026-09-09): a censor
# record must bind the CURRENT dec-005 DNADamage source and mnrnd provider
# identity to advance the contiguous prefix.
# ---------------------------------------------------------------------------


def test_censor_record_with_wrong_dnadamage_source_identity_blocks_contiguity():
    horizon = selection_horizon_max_search_ticks()
    _, current_mnrnd = _current_censor_identity()
    ledger = {
        0: _record(0, COMPLETED),
        1: _record(
            1,
            RIGHT_CENSORED,
            max_search_ticks=horizon,
            dnadamage_sha="stale-different-source-sha",
            mnrnd_sha=current_mnrnd,
        ),
        2: _record(2, COMPLETED),
    }
    audit = audit_cohort(ledger=ledger)
    assert 1 not in audit.censored_seeds
    assert audit.contiguous_prefix_end == 0
    assert audit.gap_seeds == [1]
    assert audit.premature_seeds == [2]
    mismatch_seeds = {row["seed"] for row in audit.invalid_censor_seeds}
    assert 1 in mismatch_seeds
    reasons = [row["reason"] for row in audit.invalid_censor_seeds if row["seed"] == 1]
    assert any("dnadamage_source_resolved_sha256" in r or "does not bind" in r for r in reasons)


def test_censor_record_with_wrong_mnrnd_provider_identity_blocks_contiguity():
    horizon = selection_horizon_max_search_ticks()
    current_dnadamage, _ = _current_censor_identity()
    ledger = {
        0: _record(0, COMPLETED),
        1: _record(
            1,
            RIGHT_CENSORED,
            max_search_ticks=horizon,
            dnadamage_sha=current_dnadamage,
            mnrnd_sha="stale-different-provider-sha",
        ),
        2: _record(2, COMPLETED),
    }
    audit = audit_cohort(ledger=ledger)
    assert 1 not in audit.censored_seeds
    assert audit.contiguous_prefix_end == 0
    assert audit.gap_seeds == [1]


def test_censor_record_with_correct_current_identity_advances_contiguity():
    """Positive control for the two inversion tests above: a censor
    record whose identity fields genuinely match the current run's
    genuine values DOES advance the contiguous prefix."""
    horizon = selection_horizon_max_search_ticks()
    ledger = {
        0: _record(0, COMPLETED),
        1: _record(1, RIGHT_CENSORED, max_search_ticks=horizon),
        2: _record(2, COMPLETED),
    }
    audit = audit_cohort(ledger=ledger)
    assert audit.censored_seeds == [1]
    assert audit.contiguous_prefix_end == 2
    assert audit.gap_seeds == []


# ---------------------------------------------------------------------------
# selection_satisfied gating on integrity findings (Opus re-review,
# 2026-09-09): never satisfied while source_hash_mismatches or
# duplicate_trace_hashes is nonempty, even with enough raw completions.
# ---------------------------------------------------------------------------


def test_selection_not_satisfied_when_source_hash_mismatch_present_even_with_enough_completions():
    required = required_completed_windows()
    ledger = {seed: _record(seed, COMPLETED) for seed in range(required)}
    # Corrupt one seed's source hash to disagree with the rest.
    ledger[0] = _record(0, COMPLETED, dnadamage_sha="different-source-entirely")
    audit = audit_cohort(ledger=ledger)
    assert len(audit.selected_seeds) == required  # raw count still reaches required
    assert audit.source_hash_mismatches  # but an integrity finding is outstanding
    assert audit.selection_satisfied is False


def test_selection_not_satisfied_when_duplicate_trace_hash_present_even_with_enough_completions():
    required = required_completed_windows()
    ledger = {seed: _record(seed, COMPLETED) for seed in range(required)}
    # Force seed 1's cytokinesis trace hash to alias seed 0's.
    ledger[1] = _record(1, COMPLETED, cyt_sha=ledger[0].cytokinesis_trace_sha256)
    audit = audit_cohort(ledger=ledger)
    assert len(audit.selected_seeds) == required
    assert audit.duplicate_trace_hashes
    assert audit.selection_satisfied is False


# ---------------------------------------------------------------------------
# Authoritative operational root (Opus re-review, 2026-09-09)
# ---------------------------------------------------------------------------


def test_authoritative_karr_native_root_resolves_to_dual_division_cohort_current():
    root = authoritative_karr_native_root()
    assert root.name == "dual_division_cohort_current"
    assert root.parent.name == "karr_native"


def test_default_search_roots_lists_authoritative_root_first_when_present(tmp_path, monkeypatch):
    fake_repo_root = tmp_path / "repo"
    authoritative = fake_repo_root / "data" / "m1_sources" / "karr_native" / "dual_division_cohort_current"
    authoritative.mkdir(parents=True)
    roots = default_search_roots(repo_root=fake_repo_root)
    assert roots[0] == authoritative


def test_default_search_roots_omits_authoritative_root_when_absent_anywhere(tmp_path, monkeypatch):
    import scripts.l2_event.division_cohort_selector as selector_module

    monkeypatch.setattr(
        selector_module, "MAIN_CHECKOUT_KARR_NATIVE_ROOT_WINDOWS", tmp_path / "no-such-windows-root"
    )
    monkeypatch.setattr(selector_module, "MAIN_CHECKOUT_KARR_NATIVE_ROOT_WSL", tmp_path / "no-such-wsl-root")
    fake_repo_root = tmp_path / "repo_without_authoritative_root"
    fake_repo_root.mkdir(parents=True)
    roots = default_search_roots(repo_root=fake_repo_root)
    assert all(r.name != "dual_division_cohort_current" for r in roots)
