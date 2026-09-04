"""Tests for `scripts/l2_event/validate_dual_division_canary.py`.

MATLAB-free: uses synthetic HDF5 event-window fixtures shaped exactly like
the real Cytokinesis/FtsZPolymerization traces
`scripts/matlab/extract_dual_division_window.m` produces, following the
same fixture-construction pattern as
`tests/scripts/test_prepare_cytokinesis_cohort.py`'s
`_write_valid_anchor_trace` (real genuine-provider identity computed via
`launcher.current_genuine_mnrnd_provider()` against a fake local MATLAB
root, never a hardcoded/fabricated provider identity).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import h5py
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event import ftsz_pre_division_evidence as ftsz_evidence  # noqa: E402
from scripts.l2_event import launcher  # noqa: E402
from scripts.l2_event.division_window_spec import (  # noqa: E402
    CYTOKINESIS_M_TICKS as CYTOKINESIS_N_TICKS,
)
from scripts.l2_event.division_window_spec import (  # noqa: E402
    FTSZ_M_TICKS as FTSZ_N_TICKS,
)
from scripts.l2_event.survey_cytokinesis_onset_span import (  # noqa: E402
    REQUIRED_OBSERVABLES as CYTOKINESIS_REQUIRED_OBSERVABLES,
)
from scripts.l2_event.validate_dual_division_canary import (  # noqa: E402
    REQUIRED_DNADAMAGE_SOURCE_SHA256,
    cytokinesis_anchor_spec,
    event_window_dir,
    validate_dual_division_canary,
)


@pytest.fixture(autouse=True)
def _fake_local_genuine_provider(monkeypatch, tmp_path):
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


def _encode_char_metadata(text: str) -> np.ndarray:
    return np.array([ord(c) for c in text], dtype=np.uint16).reshape(-1, 1)


def _provider_metadata_datasets(metadata_group, *, provider_sha256_override: str | None = None) -> None:
    provider = launcher.current_genuine_mnrnd_provider()
    provider_sha = provider_sha256_override if provider_sha256_override is not None else provider["sha256_lf_normalized"]
    metadata_group.create_dataset("mnrnd_provider_kind", data=_encode_char_metadata(provider["kind"]))
    metadata_group.create_dataset(
        "mnrnd_provider_matlab_release", data=_encode_char_metadata(provider["matlab_release"])
    )
    metadata_group.create_dataset(
        "mnrnd_provider_toolbox_version", data=_encode_char_metadata(provider["toolbox_version"])
    )
    metadata_group.create_dataset(
        "mnrnd_provider_path_relative_to_matlabroot",
        data=_encode_char_metadata(provider["provider_path_relative_to_matlabroot"]),
    )
    metadata_group.create_dataset("mnrnd_provider_sha256", data=_encode_char_metadata(provider_sha))
    metadata_group.create_dataset(
        "statistics_rng_provider_identity_json",
        data=_encode_char_metadata(
            json.dumps(launcher.current_genuine_statistics_rng_provider(), sort_keys=True, separators=(",", ":"))
        ),
    )


def _write_cytokinesis_trace(
    out_dir: Path,
    *,
    seed: int,
    completion_tick: int,
    onset_tick: int,
    tick_start: int,
    provider_sha256_override: str | None = None,
    corrupt_completion: bool = False,
    dnadamage_source_sha256: str | None = REQUIRED_DNADAMAGE_SOURCE_SHA256,
    omit_dnadamage_source_metadata: bool = False,
) -> Path:
    path = out_dir / f"Cytokinesis_{CYTOKINESIS_N_TICKS}ticks.mat"
    path.parent.mkdir(parents=True, exist_ok=True)
    n_ticks = CYTOKINESIS_N_TICKS

    onset_row = onset_tick - tick_start
    completion_row = completion_tick - tick_start
    before_pinched = np.full(n_ticks, 10.0, dtype=float)
    after_pinched = np.full(n_ticks, 10.0, dtype=float)
    n_steps = max(1, completion_row - onset_row)
    step = 10.0 / n_steps
    current = 10.0
    for row in range(onset_row, completion_row + 1):
        before_pinched[row] = current
        current = max(0.0, current - step)
        after_pinched[row] = current
    after_pinched[completion_row] = 0.0 if not corrupt_completion else 1.0
    before_pinched[completion_row + 1 :] = 0.0
    after_pinched[completion_row + 1 :] = 0.0

    with h5py.File(path, "w") as handle:
        metadata = handle.create_group("metadata")
        metadata.create_dataset("n_ticks", data=np.array([n_ticks]))
        metadata.create_dataset("process_name", data=_encode_char_metadata("Cytokinesis"))
        metadata.create_dataset("rng_seed", data=np.array([seed]))
        metadata.create_dataset("tick_offset", data=np.array([0.0]))
        metadata.create_dataset("stride", data=np.array([1]))
        metadata.create_dataset("tick_start", data=np.array([tick_start]))
        metadata.create_dataset("window_anchor", data=np.array([completion_tick]))
        metadata.create_dataset("onset_tick", data=np.array([onset_tick]))
        metadata.create_dataset("signal_kind", data=_encode_char_metadata("diameter_decrease"))
        metadata.create_dataset("signal_property", data=_encode_char_metadata("geometry"))
        metadata.create_dataset("signal_field", data=_encode_char_metadata("pinchedDiameter"))
        metadata.create_dataset("max_search_ticks", data=np.array([launcher.DEFAULT_MAX_SEARCH_TICKS]))
        metadata.create_dataset(
            "event_observable_projection_version",
            data=np.array([launcher.EVENT_OBSERVABLE_PROJECTION_VERSION]),
        )
        _provider_metadata_datasets(metadata, provider_sha256_override=provider_sha256_override)
        if not omit_dnadamage_source_metadata:
            # decisions/dec-005 full-simulation source-hash binding:
            # defaults to the CURRENT worktree's expected value so
            # happy-path fixtures validate; tests exercising the
            # mismatch/missing inversion pass an explicit override or
            # omit_dnadamage_source_metadata=True instead.
            metadata.create_dataset(
                "dnadamage_source_resolved_sha256", data=_encode_char_metadata(dnadamage_source_sha256)
            )

        states_before = handle.create_group("states_before")
        states_after = handle.create_group("states_after")
        for observable in CYTOKINESIS_REQUIRED_OBSERVABLES:
            if observable == "pinchedDiameter":
                before, after = before_pinched, after_pinched
            elif observable == "chromosome_segregated":
                before = after = np.ones(n_ticks, dtype=float)
            else:
                before = after = np.zeros(n_ticks, dtype=float)
            states_before.create_dataset(observable, data=before.reshape(1, -1))
            states_after.create_dataset(observable, data=after.reshape(1, -1))
    return path


def _write_ftsz_trace(
    out_dir: Path,
    *,
    seed: int,
    completion_tick: int,
    tick_start: int,
    provider_sha256_override: str | None = None,
    dnadamage_source_sha256: str | None = REQUIRED_DNADAMAGE_SOURCE_SHA256,
    omit_dnadamage_source_metadata: bool = False,
) -> Path:
    path = out_dir / f"FtsZPolymerization_{FTSZ_N_TICKS}ticks.mat"
    path.parent.mkdir(parents=True, exist_ok=True)
    n_ticks = FTSZ_N_TICKS

    with h5py.File(path, "w") as handle:
        metadata = handle.create_group("metadata")
        metadata.create_dataset("n_ticks", data=np.array([n_ticks]))
        metadata.create_dataset("process_name", data=_encode_char_metadata("FtsZPolymerization"))
        metadata.create_dataset("rng_seed", data=np.array([seed]))
        metadata.create_dataset("tick_offset", data=np.array([0.0]))
        metadata.create_dataset("stride", data=np.array([1]))
        metadata.create_dataset("tick_start", data=np.array([tick_start]))
        metadata.create_dataset("window_anchor", data=np.array([completion_tick]))
        _provider_metadata_datasets(metadata, provider_sha256_override=provider_sha256_override)
        if not omit_dnadamage_source_metadata:
            metadata.create_dataset(
                "dnadamage_source_resolved_sha256", data=_encode_char_metadata(dnadamage_source_sha256)
            )

        states_before = handle.create_group("states_before")
        states_after = handle.create_group("states_after")
        for observable in ftsz_evidence.GATE_CHANNELS:
            before = after = np.zeros(n_ticks, dtype=float)
            states_before.create_dataset(observable, data=before.reshape(1, -1))
            states_after.create_dataset(observable, data=after.reshape(1, -1))
    return path


def _write_matched_pair(root: Path, *, seed: int = 49) -> Path:
    out_dir = event_window_dir(seed, karr_native_root=root)
    completion_tick = 31427
    onset_tick = 27556
    _write_cytokinesis_trace(
        out_dir,
        seed=seed,
        completion_tick=completion_tick,
        onset_tick=onset_tick,
        tick_start=completion_tick - CYTOKINESIS_N_TICKS + 1,
    )
    _write_ftsz_trace(
        out_dir,
        seed=seed,
        completion_tick=completion_tick,
        tick_start=completion_tick - FTSZ_N_TICKS + 1,
    )
    return root


def test_matched_pair_passes_both_validators_and_all_dual_tap_checks(tmp_path):
    root = _write_matched_pair(tmp_path)
    report = validate_dual_division_canary(49, karr_native_root=root)

    assert report.cytokinesis_valid is True, report.cytokinesis_reason
    assert report.ftsz_valid is True, report.ftsz_reason
    assert report.distinct_paths is True
    assert report.distinct_content is True
    assert report.same_completion_tick is True
    assert report.provider_sha256_match is True
    assert report.status == "PASS"
    assert report.reasons == []


def test_missing_ftsz_file_fails_closed_never_reports_partial_pass(tmp_path):
    out_dir = event_window_dir(49, karr_native_root=tmp_path)
    completion_tick = 31427
    _write_cytokinesis_trace(
        out_dir,
        seed=49,
        completion_tick=completion_tick,
        onset_tick=27556,
        tick_start=completion_tick - CYTOKINESIS_N_TICKS + 1,
    )
    # No FtsZ trace written at all.

    report = validate_dual_division_canary(49, karr_native_root=tmp_path)

    assert report.cytokinesis_valid is True
    assert report.ftsz_valid is False
    assert report.status == "FAIL"
    assert any("ftsz" in reason for reason in report.reasons)


def test_mismatched_completion_tick_fails_the_dual_tap_cross_check(tmp_path):
    """Both files individually pass their own single-process validator, but
    the dual-tap-specific same-completion-tick cross-check must still
    fail the combined verdict."""
    root = tmp_path
    seed = 49
    out_dir = event_window_dir(seed, karr_native_root=root)
    cyt_completion = 31427
    ftsz_completion = 31400  # deliberately different
    _write_cytokinesis_trace(
        out_dir,
        seed=seed,
        completion_tick=cyt_completion,
        onset_tick=27556,
        tick_start=cyt_completion - CYTOKINESIS_N_TICKS + 1,
    )
    _write_ftsz_trace(
        out_dir,
        seed=seed,
        completion_tick=ftsz_completion,
        tick_start=ftsz_completion - FTSZ_N_TICKS + 1,
    )

    report = validate_dual_division_canary(seed, karr_native_root=root)

    assert report.cytokinesis_valid is True
    assert report.ftsz_valid is True
    assert report.same_completion_tick is False
    assert report.status == "FAIL"
    assert any("window_anchor mismatch" in reason for reason in report.reasons)


def test_provider_sha256_mismatch_fails_the_dual_tap_cross_check(tmp_path):
    """Even if both files individually validate against the CURRENT local
    provider (each independently matches launcher.current_genuine_mnrnd_provider()),
    a dual-tap run must have used the SAME provider for both taps -- a
    provider_sha256 mismatch between the two files is itself a red flag
    that they were not produced by one run, so it must fail even though
    the per-file validators can't see each other."""
    root = tmp_path
    seed = 49
    out_dir = event_window_dir(seed, karr_native_root=root)
    completion_tick = 31427
    _write_cytokinesis_trace(
        out_dir,
        seed=seed,
        completion_tick=completion_tick,
        onset_tick=27556,
        tick_start=completion_tick - CYTOKINESIS_N_TICKS + 1,
    )
    _write_ftsz_trace(
        out_dir,
        seed=seed,
        completion_tick=completion_tick,
        tick_start=completion_tick - FTSZ_N_TICKS + 1,
        provider_sha256_override="0" * 64,
    )

    report = validate_dual_division_canary(seed, karr_native_root=root)

    # Note: overriding mnrnd_provider_sha256 alone (while every OTHER
    # provider field stays genuine) also makes the FtsZ file's own
    # provider-sha field internally inconsistent with the real current
    # provider hash IF the underlying Cytokinesis-side validator checked
    # it -- but validate_seed_window (FtsZ path) does not check provider
    # metadata at all, so ftsz_valid should still be True here; only the
    # dual-tap cross-check should fail.
    assert report.ftsz_valid is True
    assert report.provider_sha256_match is False
    assert report.status == "FAIL"
    assert any("mnrnd_provider_sha256 mismatch" in reason for reason in report.reasons)


def test_dnadamage_source_mismatch_fails_the_dual_tap_cross_check_and_cytokinesis_validation(tmp_path):
    """decisions/dec-005: a mismatched dnadamage_source_resolved_sha256
    between the two taps must fail BOTH the dual-tap cross-check AND
    Cytokinesis's own cohort validation (which independently requires the
    hash to match the CURRENT worktree's karr_bootstrap.m resolution) --
    this is the exact confound (two different DNADamage.m source
    variants) that produced the seed-36 conventional-vs-dual discrepancy
    this task's evidence describes."""
    root = tmp_path
    seed = 49
    out_dir = event_window_dir(seed, karr_native_root=root)
    completion_tick = 31427
    _write_cytokinesis_trace(
        out_dir,
        seed=seed,
        completion_tick=completion_tick,
        onset_tick=27556,
        tick_start=completion_tick - CYTOKINESIS_N_TICKS + 1,
        dnadamage_source_sha256="1" * 64,  # deliberately wrong / stale
    )
    _write_ftsz_trace(
        out_dir,
        seed=seed,
        completion_tick=completion_tick,
        tick_start=completion_tick - FTSZ_N_TICKS + 1,
        dnadamage_source_sha256=REQUIRED_DNADAMAGE_SOURCE_SHA256,
    )

    report = validate_dual_division_canary(seed, karr_native_root=root)

    assert report.cytokinesis_valid is False
    assert "dnadamage_source_resolved_sha256" in report.cytokinesis_reason
    assert report.dnadamage_source_match is False
    assert report.status == "FAIL"
    assert any("dnadamage_source_resolved_sha256 mismatch" in reason for reason in report.reasons)


def test_dnadamage_source_missing_fails_closed_never_silently_skipped(tmp_path):
    """A trace produced before this metadata existed (e.g. every preserved
    M_ticks=4000 trace) must fail closed on cohort validation with an
    explicit 'missing' reason -- never silently treated as 'no check
    needed' just because the key is absent."""
    root = tmp_path
    seed = 49
    out_dir = event_window_dir(seed, karr_native_root=root)
    completion_tick = 31427
    _write_cytokinesis_trace(
        out_dir,
        seed=seed,
        completion_tick=completion_tick,
        onset_tick=27556,
        tick_start=completion_tick - CYTOKINESIS_N_TICKS + 1,
        omit_dnadamage_source_metadata=True,
    )
    _write_ftsz_trace(
        out_dir,
        seed=seed,
        completion_tick=completion_tick,
        tick_start=completion_tick - FTSZ_N_TICKS + 1,
    )

    report = validate_dual_division_canary(seed, karr_native_root=root)

    assert report.cytokinesis_valid is False
    assert "dnadamage_source_resolved_sha256 is missing" in report.cytokinesis_reason
    assert report.dnadamage_source_match is False
    assert report.cytokinesis_dnadamage_source_sha256 is None
    assert report.status == "FAIL"


def test_byte_identical_outputs_fail_the_distinctness_check(tmp_path):
    import shutil

    root = _write_matched_pair(tmp_path)
    out_dir = event_window_dir(49, karr_native_root=root)
    cyt_path = out_dir / f"Cytokinesis_{CYTOKINESIS_N_TICKS}ticks.mat"
    ftsz_path = out_dir / f"FtsZPolymerization_{FTSZ_N_TICKS}ticks.mat"
    shutil.copyfile(cyt_path, ftsz_path)

    report = validate_dual_division_canary(49, karr_native_root=root)

    assert report.distinct_content is False
    assert report.status == "FAIL"
    assert any("byte-identical" in reason for reason in report.reasons)


def test_main_returns_nonzero_exit_on_fail(tmp_path, capsys):
    from scripts.l2_event.validate_dual_division_canary import main

    exit_code = main(["--seed", "49", "--karr-native-root", str(tmp_path)])
    assert exit_code != 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["status"] == "FAIL"


def test_main_returns_zero_exit_on_pass(tmp_path, capsys):
    from scripts.l2_event.validate_dual_division_canary import main

    root = _write_matched_pair(tmp_path)
    exit_code = main(["--seed", "49", "--karr-native-root", str(root)])
    assert exit_code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["status"] == "PASS"


# ---------------------------------------------------------------------------
# 2026-09-04 Cytokinesis window preregistration fix: contract tests proving
# the new M_ticks=5000 accepts the real overrun span (4076 ticks, seed 36
# equivalence run) that failed closed under M_ticks=4000, that a span one
# tick larger than the new M still fails closed (never silently truncated
# or tuned), and that traces captured under the OLD M_ticks=4000 are
# rejected outright for the new cohort rather than silently reused.
# ---------------------------------------------------------------------------


def test_span_4076_ticks_is_accepted_under_the_new_m_ticks_contract(tmp_path):
    """The real overrun span discovered on the fresh seed-36 equivalence
    run (onset_tick=27918, completion_tick=31993 -- an INCLUSIVE
    onset-to-completion span of 4076 ticks, i.e. completion-onset+1;
    completion-onset itself is 4075, the "difference" convention
    scripts/l2_event/survey_cytokinesis_onset_span.py's own `span` field
    uses) must fit inside -- and be accepted by -- the new preregistered
    M_ticks=5000 window with room to spare (5000 - 4076 = 924 tick margin,
    matching docs/phase_f/l2_event/division_window_spec.json's evidence
    block, which records the value in the same inclusive convention)."""
    assert CYTOKINESIS_N_TICKS == 5000, "this test's fixed 924-tick margin assumption assumes M_ticks=5000"
    out_dir = event_window_dir(36, karr_native_root=tmp_path)
    onset_tick = 27918
    completion_tick = 31993
    inclusive_span = completion_tick - onset_tick + 1
    assert inclusive_span == 4076
    assert completion_tick - onset_tick == 4075

    trace_path = _write_cytokinesis_trace(
        out_dir,
        seed=36,
        completion_tick=completion_tick,
        onset_tick=onset_tick,
        tick_start=completion_tick - CYTOKINESIS_N_TICKS + 1,
    )

    ok, reason = launcher.validate_existing_event_window(trace_path, cytokinesis_anchor_spec(36))
    assert ok is True, reason


def test_span_m_plus_1_ticks_fails_closed(tmp_path):
    """An INCLUSIVE onset-to-completion span one tick larger than the
    preregistered M_ticks (5001 ticks for M_ticks=5000 -- i.e. the
    smallest span that no longer fits in a fixed M_ticks-length window)
    must fail closed -- the onset necessarily precedes the captured
    window's tick_start by exactly one tick, so window_loader's
    stride-contract check (mirroring capture_dual_anchor_windows' own
    ``onset_tick < tick_start_a`` MATLAB guard) refuses the trace. This
    must never be silently truncated, padded, or accepted by loosening the
    contract -- a real span this large must instead trigger a fresh
    preregistration (a new, larger M_ticks), never a quiet tolerance
    widening."""
    out_dir = event_window_dir(36, karr_native_root=tmp_path)
    completion_tick = 31993
    inclusive_span = CYTOKINESIS_N_TICKS + 1  # 5001 for M_ticks=5000
    onset_tick = completion_tick - (inclusive_span - 1)  # completion - onset difference = inclusive_span - 1
    tick_start = completion_tick - CYTOKINESIS_N_TICKS + 1
    assert onset_tick == tick_start - 1, "fixture must violate the onset-inside-window invariant by exactly 1 tick"
    assert onset_tick < tick_start, "fixture must actually violate the onset-inside-window invariant"

    path = out_dir / f"Cytokinesis_{CYTOKINESIS_N_TICKS}ticks.mat"
    path.parent.mkdir(parents=True, exist_ok=True)
    n_ticks = CYTOKINESIS_N_TICKS
    with h5py.File(path, "w") as handle:
        metadata = handle.create_group("metadata")
        metadata.create_dataset("n_ticks", data=np.array([n_ticks]))
        metadata.create_dataset("process_name", data=_encode_char_metadata("Cytokinesis"))
        metadata.create_dataset("rng_seed", data=np.array([36]))
        metadata.create_dataset("tick_offset", data=np.array([0.0]))
        metadata.create_dataset("stride", data=np.array([1]))
        metadata.create_dataset("tick_start", data=np.array([tick_start]))
        metadata.create_dataset("window_anchor", data=np.array([completion_tick]))
        metadata.create_dataset("onset_tick", data=np.array([onset_tick]))
        metadata.create_dataset("signal_kind", data=_encode_char_metadata("diameter_decrease"))
        metadata.create_dataset("signal_property", data=_encode_char_metadata("geometry"))
        metadata.create_dataset("signal_field", data=_encode_char_metadata("pinchedDiameter"))
        metadata.create_dataset("max_search_ticks", data=np.array([launcher.DEFAULT_MAX_SEARCH_TICKS]))
        metadata.create_dataset(
            "event_observable_projection_version",
            data=np.array([launcher.EVENT_OBSERVABLE_PROJECTION_VERSION]),
        )
        _provider_metadata_datasets(metadata)
        states_before = handle.create_group("states_before")
        states_after = handle.create_group("states_after")
        for observable in CYTOKINESIS_REQUIRED_OBSERVABLES:
            before = after = np.zeros(n_ticks, dtype=float)
            states_before.create_dataset(observable, data=before.reshape(1, -1))
            states_after.create_dataset(observable, data=after.reshape(1, -1))

    ok, reason = launcher.validate_existing_event_window(path, cytokinesis_anchor_spec(36))
    assert ok is False
    assert "onset_tick" in reason and "tick_start" in reason


def test_stale_4000_tick_trace_is_rejected_for_the_new_cohort(tmp_path):
    """A trace captured under the OLD (pre-2026-09-04) M_ticks=4000
    contract must be rejected outright when validated against the new
    M_ticks=5000 spec -- never silently reused or treated as if it were
    part of the new authoritative cohort. The 34 preserved M_ticks=4000
    traces on disk are exactly this scenario in production."""
    out_dir = event_window_dir(9, karr_native_root=tmp_path)
    old_n_ticks = 4000
    completion_tick = 29076
    onset_tick = 25307  # real seed-009 span=3769, from the 35-trace survey
    tick_start = completion_tick - old_n_ticks + 1

    path = out_dir / f"Cytokinesis_{old_n_ticks}ticks.mat"
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as handle:
        metadata = handle.create_group("metadata")
        metadata.create_dataset("n_ticks", data=np.array([old_n_ticks]))
        metadata.create_dataset("process_name", data=_encode_char_metadata("Cytokinesis"))
        metadata.create_dataset("rng_seed", data=np.array([9]))
        metadata.create_dataset("tick_offset", data=np.array([0.0]))
        metadata.create_dataset("stride", data=np.array([1]))
        metadata.create_dataset("tick_start", data=np.array([tick_start]))
        metadata.create_dataset("window_anchor", data=np.array([completion_tick]))
        metadata.create_dataset("onset_tick", data=np.array([onset_tick]))
        metadata.create_dataset("signal_kind", data=_encode_char_metadata("diameter_decrease"))
        metadata.create_dataset("signal_property", data=_encode_char_metadata("geometry"))
        metadata.create_dataset("signal_field", data=_encode_char_metadata("pinchedDiameter"))
        metadata.create_dataset("max_search_ticks", data=np.array([launcher.DEFAULT_MAX_SEARCH_TICKS]))
        metadata.create_dataset(
            "event_observable_projection_version",
            data=np.array([launcher.EVENT_OBSERVABLE_PROJECTION_VERSION]),
        )
        _provider_metadata_datasets(metadata)
        states_before = handle.create_group("states_before")
        states_after = handle.create_group("states_after")
        for observable in CYTOKINESIS_REQUIRED_OBSERVABLES:
            before = after = np.zeros(old_n_ticks, dtype=float)
            states_before.create_dataset(observable, data=before.reshape(1, -1))
            states_after.create_dataset(observable, data=after.reshape(1, -1))

    # Validate against the CURRENT (new) spec, which expects n_ticks=5000
    # (CYTOKINESIS_N_TICKS) at a path this old file does not even occupy
    # (Cytokinesis_5000ticks.mat) -- validate_existing_event_window is
    # called directly against the stale path to prove the metadata-level
    # rejection, independent of the path-based "file does not exist" check
    # a real cohort-completeness scan would also hit.
    assert old_n_ticks != CYTOKINESIS_N_TICKS
    ok, reason = launcher.validate_existing_event_window(path, cytokinesis_anchor_spec(9))
    assert ok is False
    assert "n_ticks" in reason and "4000" in reason and str(CYTOKINESIS_N_TICKS) in reason


# ---------------------------------------------------------------------------
# Provisional-margin gate (Opus final review, 2026-09-04): boundary tests
# through the full validate_dual_division_canary() pipeline. A real on-disk
# window has exactly CYTOKINESIS_N_TICKS rows, so the inclusive span
# (window_anchor - onset_tick + 1) can never exceed CYTOKINESIS_N_TICKS for
# a structurally well-formed trace -- the M+1 (genuine overrun) case is
# therefore only constructible at the pure-function level, covered by
# test_division_window_spec.py::test_margin_gate_rejects_span_one_tick_above_m_ticks.
# These two tests cover the two cases a real trace CAN exhibit: M-1 margin
# (accepted) and exactly-M (zero margin, rejected).
# ---------------------------------------------------------------------------


def test_canary_accepts_span_one_tick_below_m_ticks(tmp_path):
    """M-1 margin: inclusive_span == CYTOKINESIS_N_TICKS - 1 must PASS
    the full combined canary (both single-process validators plus all
    dual-tap cross-checks, including the new margin_ok gate)."""
    seed = 49
    out_dir = event_window_dir(seed, karr_native_root=tmp_path)
    completion_tick = 31993
    onset_tick = completion_tick - (CYTOKINESIS_N_TICKS - 1) + 1  # inclusive_span == N_TICKS - 1
    inclusive_span = completion_tick - onset_tick + 1
    assert inclusive_span == CYTOKINESIS_N_TICKS - 1

    _write_cytokinesis_trace(
        out_dir,
        seed=seed,
        completion_tick=completion_tick,
        onset_tick=onset_tick,
        tick_start=completion_tick - CYTOKINESIS_N_TICKS + 1,
    )
    _write_ftsz_trace(
        out_dir,
        seed=seed,
        completion_tick=completion_tick,
        tick_start=completion_tick - FTSZ_N_TICKS + 1,
    )

    report = validate_dual_division_canary(seed, karr_native_root=tmp_path)
    assert report.margin_ok is True
    assert report.inclusive_span_ticks == CYTOKINESIS_N_TICKS - 1
    assert report.status == "PASS", report.reasons


def test_canary_rejects_span_exactly_equal_to_m_ticks(tmp_path):
    """Exactly-M (zero margin): inclusive_span == CYTOKINESIS_N_TICKS must
    FAIL the combined canary via the margin_ok gate, even though every
    other check (both single-process validators, all other cross-checks)
    independently passes -- a zero-margin observation must never be
    silently accepted as 'just barely fits.'"""
    seed = 49
    out_dir = event_window_dir(seed, karr_native_root=tmp_path)
    completion_tick = 31993
    onset_tick = completion_tick - CYTOKINESIS_N_TICKS + 1  # inclusive_span == N_TICKS exactly
    inclusive_span = completion_tick - onset_tick + 1
    assert inclusive_span == CYTOKINESIS_N_TICKS

    _write_cytokinesis_trace(
        out_dir,
        seed=seed,
        completion_tick=completion_tick,
        onset_tick=onset_tick,
        tick_start=completion_tick - CYTOKINESIS_N_TICKS + 1,
    )
    _write_ftsz_trace(
        out_dir,
        seed=seed,
        completion_tick=completion_tick,
        tick_start=completion_tick - FTSZ_N_TICKS + 1,
    )

    report = validate_dual_division_canary(seed, karr_native_root=tmp_path)
    assert report.margin_ok is False
    assert report.inclusive_span_ticks == CYTOKINESIS_N_TICKS
    assert report.status == "FAIL"
    assert any("provisional-margin gate" in reason for reason in report.reasons)
    # Every OTHER check must independently still pass -- proving the FAIL
    # is attributable specifically to the margin gate, not a side effect.
    assert report.cytokinesis_valid is True
    assert report.ftsz_valid is True
    assert report.same_completion_tick is True
    assert report.provider_sha256_match is True
    assert report.dnadamage_source_match is True


def test_prepare_cytokinesis_cohort_and_canary_validator_agree_with_the_shared_spec():
    """scripts/l2_event/prepare_cytokinesis_cohort.py's AUTHORITATIVE_N_TICKS
    and this module's CYTOKINESIS_N_TICKS/FTSZ_N_TICKS must all resolve to
    the SAME docs/phase_f/l2_event/division_window_spec.json values -- this
    is the driver/validator agreement the task requires (catalog agreement
    is covered separately by
    test_extract_dual_division_window_static.test_catalog_and_spec_agree_on_cytokinesis_m_ticks)."""
    from scripts.l2_event import prepare_cytokinesis_cohort
    from scripts.l2_event.division_window_spec import CYTOKINESIS_M_TICKS, FTSZ_M_TICKS

    assert CYTOKINESIS_N_TICKS == CYTOKINESIS_M_TICKS
    assert FTSZ_N_TICKS == FTSZ_M_TICKS
    assert prepare_cytokinesis_cohort.AUTHORITATIVE_N_TICKS == CYTOKINESIS_M_TICKS
